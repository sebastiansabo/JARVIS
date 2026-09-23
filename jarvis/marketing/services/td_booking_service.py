"""Orchestration for the public (session-less) test-drive booking flow.

TdBookingService is the integration crux that wires the booking layer together:
  - submit_booking:  validate the page is open + in its [opens_at, closes_at]
    window, rate-limit by contact and by IP, re-check the slot is still live,
    insert a `pending_confirm` booking (UniqueViolation -> 409), and email a
    signed confirm/cancel link.
  - confirm_booking: read the signed token, load the still-pending booking,
    find-or-create the CRM client, resolve the car's advisor, build the PLANNED
    `foi_de_parcurs` TD row, and hand it to the race-safe atomic confirm
    (TdConflict -> 409). Notifies staff best-effort.
  - cancel_booking:  read the signed token, mark the booking cancelled, and hard
    -delete the PLANNED FP row it created (freeing the slot).
  - expire_pending_bookings: delegate to the repository's bulk expiry.

Every public method returns a ServiceResult so the route layer just maps
(status_code, data/error) onto an HTTP response.
"""
import html
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

import psycopg2

from flask import current_app
from core.base_repository import BaseRepository
from marketing.repositories.td_booking_repository import (
    TdBookingRepository, TdConflict, TdBookingNotPending,
)
from marketing.services.td_slot_service import TdSlotService
from core.approvals.booking_token import make_booking_token, read_booking_token
from core.messaging.customer_message import send_customer_message
from crm.repositories.client_repository import ClientRepository
from foi_parcurs.repositories.foi_parcurs_repository import FoiParcursRepository

logger = logging.getLogger('jarvis.marketing.td_booking')

# How long a submitted booking stays confirmable before expire_pending sweeps it.
_PENDING_TTL_MINUTES = 45
# Per-IP throttle: at most this many booking attempts in the trailing hour.
_MAX_ATTEMPTS_PER_IP_PER_HOUR = 8
# UTM keys we persist; anything else in the submitted utm blob is dropped (spec §7).
_UTM_ALLOWED_KEYS = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content'}
# Server-side E.164 guard: '+' then 7-15 digits, once spaces/dashes are stripped.
_E164_RE = re.compile(r'^\+\d{7,15}$')


def _normalize_e164(phone) -> str | None:
    """Strip spaces/dashes from a candidate phone and return it iff it is a valid
    E.164 number ('+' + 7-15 digits); otherwise None. The frontend composes E.164
    via composePhone, but this is the server-side guard so a malformed/malicious
    client can't break dedup (find_by_phone is exact-match) or store junk."""
    candidate = (phone or '').replace(' ', '').replace('-', '')
    return candidate if _E164_RE.match(candidate) else None


@dataclass
class ServiceResult:
    success: bool
    status_code: int
    data: dict | None = None
    error: str | None = None


def _as_aware(value) -> datetime:
    """Coerce a datetime that BaseRepository serialized to an ISO string (or a
    real datetime) back into a tz-aware datetime, so it can be compared against
    datetime.now(timezone.utc). timestamptz columns round-trip with an offset;
    a naive value is assumed UTC."""
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class TdBookingService:
    def __init__(self):
        self.repo = TdBookingRepository()
        self.slots = TdSlotService()
        self.crm = ClientRepository()
        self.fp = FoiParcursRepository()
        self._base = BaseRepository()

    # ---- submit ----
    def submit_booking(self, slug, slot_id, name, phone_e164, email, utm, ip,
                       user_agent, base_url, extra_answers=None):
        page = self.repo.get_page_by_slug(slug)
        if not page or page['status'] != 'open':
            return ServiceResult(False, 404, error='Booking page not available')
        now = datetime.now(timezone.utc)
        if page.get('opens_at') and now < _as_aware(page['opens_at']):
            return ServiceResult(False, 403, error='Registration not open yet')
        if page.get('closes_at') and now > _as_aware(page['closes_at']):
            return ServiceResult(False, 403, error='Registration closed')
        # Normalize/validate the phone to canonical E.164 BEFORE it drives the
        # rate limit, the insert, or (at confirm) the CRM find-or-create; storing a
        # non-E.164 value would break exact-match dedup and pollute the column.
        phone_e164 = _normalize_e164(phone_e164)
        if not phone_e164:
            return ServiceResult(False, 422, error='Invalid phone number')
        # Keep only the tracked UTM keys, coerced to strings (spec §7).
        utm = {k: str(v) for k, v in (utm or {}).items() if k in _UTM_ALLOWED_KEYS}
        # Rate limits: per contact (phone/email) and per IP.
        if self.repo.count_active_by_contact(phone_e164, email) >= page['max_bookings_per_contact']:
            return ServiceResult(False, 429, error='Booking limit reached for this contact')
        if self.repo.count_recent_by_ip(ip, now - timedelta(hours=1)) >= _MAX_ATTEMPTS_PER_IP_PER_HOUR:
            return ServiceResult(False, 429, error='Too many attempts, try later')
        # The slot must belong to this page and be live right now.
        avail = {s['id']: s for s in self.slots.available_slots(page['id'], now)}
        slot = avail.get(int(slot_id))
        if not slot:
            return ServiceResult(False, 409, error='Slot no longer available')
        # Insert the pending_confirm booking; the partial-unique active-booking
        # index maps a lost race to HTTP 409.
        booking_data = {
            'page_id': page['id'], 'slot_id': slot['id'], 'car_id': slot['car_id'],
            'customer_name': name, 'customer_phone_e164': phone_e164,
            'customer_email': email, 'utm': utm, 'ip': ip, 'user_agent': user_agent,
            'expires_at': now + timedelta(minutes=_PENDING_TTL_MINUTES),
        }
        # Legal fields (driving licence + consents) captured at submit and mapped
        # onto the fișă at confirm; the route enforces their presence (422).
        if extra_answers:
            booking_data['extra_answers'] = extra_answers
        try:
            booking = self.repo.create_booking(booking_data)
        except psycopg2.errors.UniqueViolation:
            return ServiceResult(False, 409, error='Slot just taken')
        # Email the signed confirm + cancel links.
        secret = current_app.secret_key
        confirm_token = make_booking_token(booking['id'], 'confirm', secret)
        cancel_token = make_booking_token(booking['id'], 'cancel', secret)
        confirm_link = f"{base_url}/td/confirm?token={confirm_token}"
        cancel_link = f"{base_url}/td/cancel?token={cancel_token}"
        # Escape the customer-supplied name before interpolating it into the email
        # HTML (spec §7); the raw name is fine in the DB column since React escapes
        # it in staff views, but the email body is raw HTML.
        body = (
            f"<p>Bună, {html.escape(name)}!</p>"
            f"<p>Confirmă programarea la test drive: "
            f"<a href='{confirm_link}'>Confirmă</a></p>"
            f"<p>Dacă nu mai poți ajunge, anulează: <a href='{cancel_link}'>aici</a></p>"
        )
        send_customer_message('email', email, 'Confirmă programarea la test drive', body)
        return ServiceResult(True, 201,
                             data={'booking_id': booking['id'], 'status': 'pending_confirm'})

    # ---- confirm ----
    def confirm_booking(self, token, base_url=None):
        data = read_booking_token(token, current_app.secret_key)
        if not data or data['act'] != 'confirm':
            return ServiceResult(False, 410, error='Link invalid or expired')
        booking = self.repo.get_booking(data['bid'])
        if not booking:
            return ServiceResult(False, 404, error='Booking not found')
        if booking['status'] == 'confirmed':
            # Idempotent: a re-clicked confirm link is a success, not an error.
            return ServiceResult(True, 200, data={'status': 'confirmed',
                                                  'fp_id': booking.get('foi_de_parcurs_id')})
        if booking['status'] != 'pending_confirm' or _as_aware(booking['expires_at']) < datetime.now(timezone.utc):
            return ServiceResult(False, 410, error='Booking expired or already handled')

        page = self.repo.get_page(booking['page_id'])
        car = self.repo.get_car(booking['car_id'])
        slot = self.repo.query_one('SELECT * FROM mkt_td_slots WHERE id=%s', (booking['slot_id'],))

        # Find-or-create the CRM client by normalized phone (crm_clients, not fp_clients).
        crm_client = self.crm.find_by_phone(booking['customer_phone_e164'])
        if not crm_client:
            crm_client = self.crm.create(
                display_name=booking['customer_name'],
                name_normalized=(booking['customer_name'] or '').strip().lower(),
                client_type='person',
                phone=booking['customer_phone_e164'],
                phone_raw=booking['customer_phone_e164'],
                email=booking['customer_email'],
                source_flags={'td_booking': True},
            )
        crm_client_id = crm_client['id'] if crm_client else None

        # Keep the customer's driving licence on their CRM record (mirrors the
        # staff TD flow), so it prefills on their next drive. COALESCE/NULLIF so a
        # blank never wipes an existing value; best-effort — a CRM write hiccup
        # must not fail the confirm.
        extra = booking.get('extra_answers') or {}
        lic_no = (extra.get('license') or '').strip()
        lic_exp = (extra.get('license_expiry') or '').strip()
        if crm_client_id and (lic_no or lic_exp):
            try:
                self.crm.execute(
                    "UPDATE crm_clients SET "
                    "driver_license_number = COALESCE(NULLIF(%s, ''), driver_license_number), "
                    "driver_license_expiry = COALESCE(NULLIF(%s, ''), driver_license_expiry) "
                    "WHERE id = %s",
                    (lic_no, lic_exp, crm_client_id))
            except Exception:
                logger.warning('Could not store licence on CRM client %s',
                               crm_client_id, exc_info=True)

        advisor_id = car.get('default_advisor_user_id') if car else None
        advisor_name = self._advisor_name(advisor_id)

        fp_row = self._build_fp_row(booking, page, car, slot, advisor_name)
        try:
            res = self.repo.confirm_booking_atomic(
                booking['id'], car['vin'], slot['starts_at'], slot['ends_at'], fp_row)
        except TdBookingNotPending:
            # The booking was pending when we read it, but under the advisory lock the
            # FOR-UPDATE guard saw it is no longer pending -- a racing/duplicate confirm
            # (or a cancel/expire) got there first. Re-read and respond idempotently;
            # NEVER mark 'conflict' (that would free a legitimately-held slot).
            fresh = self.repo.get_booking(booking['id'])
            if fresh and fresh['status'] == 'confirmed':
                return ServiceResult(True, 200, data={
                    'status': 'confirmed', 'fp_id': fresh.get('foi_de_parcurs_id')})
            return ServiceResult(False, 410, error='Booking expired or already handled')
        except TdConflict:
            self.repo.mark_status(booking['id'], 'conflict')
            return ServiceResult(False, 409, error='Car no longer available for this slot')

        # confirm_booking_atomic already flipped status + foi_de_parcurs_id; this
        # persists the CRM link + advisor that the atomic step doesn't know about.
        self.repo.mark_confirmed(booking['id'], crm_client_id, res['fp_id'], advisor_id)
        self._notify_staff(page, booking, advisor_id)
        return ServiceResult(True, 200, data={'status': 'confirmed', 'fp_id': res['fp_id']})

    # ---- cancel ----
    def cancel_booking(self, token):
        data = read_booking_token(token, current_app.secret_key)
        if not data or data['act'] != 'cancel':
            return ServiceResult(False, 410, error='Link invalid or expired')
        booking = self.repo.get_booking(data['bid'])
        if not booking:
            return ServiceResult(False, 404, error='Booking not found')
        if booking['status'] in ('cancelled', 'expired'):
            return ServiceResult(True, 200, data={'status': booking['status']})
        self.repo.mark_cancelled(booking['id'])
        # If confirm already created a PLANNED FP row, hard-delete it so the car /
        # slot is freed (mirrors the staff PLANNED-only discard). Never touch an FP
        # row that has already progressed past PLANNED (car handed over).
        fp_id = booking.get('foi_de_parcurs_id')
        if fp_id:
            fp = self.fp.get_contract_by_id(fp_id)
            if fp and fp.get('status') == 'PLANNED':
                self.fp.delete_contract(fp_id)
        return ServiceResult(True, 200, data={'status': 'cancelled'})

    def expire_pending_bookings(self, now):
        return self.repo.expire_pending(now)

    # ---- helpers ----
    def _build_fp_row(self, booking, page, car, slot, advisor_name) -> dict:
        """Build the PLANNED foi_de_parcurs TD row. Mirrors the draft-case of
        api_submit_test_drive's contract_data, minus FILLED-only fields, and fills
        every NOT NULL-without-default column (contract_id UNIQUE; km_*, distance_km,
        fuel_* required; fuel_gauge_*_level are varchar so use 'full', not 0).

        The legal fields the customer supplied at submit (extra_answers) map onto
        the same columns the staff TD flow uses: driving licence serie&number
        (+ expiry when given), and the GDPR / general-conditions consents captured
        at booking time (with the acceptance timestamp)."""
        extra = booking.get('extra_answers') or {}
        lic_no = (extra.get('license') or '').strip()
        lic_exp = (extra.get('license_expiry') or '').strip()
        row = {
            'contract_id': f"TDB-{booking['id']}",
            'vin': car['vin'],
            'company_id': page['company_id'],
            'client_id': None,                       # crm_clients != fp_clients; text cols carry identity
            'client_name': booking['customer_name'],
            'client_phone': booking['customer_phone_e164'],
            'route_type': 'TD',
            'advisor_name': advisor_name,            # users.name of the car's default advisor
            'departure_datetime': slot['starts_at'],
            'return_datetime': slot['ends_at'],
            'event_id': page.get('event_id'),
            'mkt_project_id': page.get('project_id'),
            'source': 'td_form',
            'status': 'PLANNED',
            'is_internal': False,
            # Consents captured at booking time (the route enforces both true).
            'gdpr_consent': bool(extra.get('gdpr_consent')),
            'general_conditions_accepted': bool(extra.get('conditions_accepted')),
            'general_conditions_accepted_at': (datetime.now(timezone.utc)
                                               if extra.get('conditions_accepted') else None),
            # NOT NULL columns without a server default:
            'km_start': 0,
            'km_end': 0,
            'distance_km': 0,
            'fuel_tank_capacity_liters': 0,
            'fuel_gauge_start_level': 'full',
            'fuel_gauge_end_level': 'full',
            'fuel_start_liters': 0,
            'fuel_end_liters': 0,
            'fuel_consumed_liters': 0,
        }
        # Driving licence (serie & number, + optional expiry) — only set when
        # present so an empty string never overwrites a column default.
        if lic_no:
            row['driver_license_number'] = lic_no
        if lic_exp:
            row['driver_license_expiry'] = lic_exp
        return row

    def _advisor_name(self, user_id):
        if not user_id:
            return ''
        row = self._base.query_one('SELECT name FROM users WHERE id=%s', (user_id,))
        return row['name'] if row else ''

    def _notify_staff(self, page, booking, advisor_id):
        """Best-effort staff notification; a failure here must never fail a confirm."""
        try:
            from core.notifications.notify import notify_with_push
            ids = list(page.get('notify_user_ids') or [])
            if advisor_id:
                ids.append(advisor_id)
            ids = list({i for i in ids if i})
            if ids:
                notify_with_push(
                    ids, 'Programare test drive nouă',
                    message=f"{booking['customer_name']} · {booking['customer_phone_e164']}",
                    category='system')
        except Exception:
            logger.warning('staff notify failed for booking %s', booking['id'], exc_info=True)
