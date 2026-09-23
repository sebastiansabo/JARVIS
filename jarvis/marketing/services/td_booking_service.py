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
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from flask import current_app
from core.base_repository import BaseRepository
from marketing.repositories.td_booking_repository import (
    TdBookingRepository, TdConflict, TdBookingNotPending,
)
from marketing.services.td_slot_service import TdSlotService
from core.approvals.booking_token import (
    make_booking_token, make_group_token, read_booking_token,
)
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
    def submit_booking(self, slug, slot_id=None, name=None, phone_e164=None, email=None,
                       utm=None, ip=None, user_agent=None, base_url=None,
                       extra_answers=None, slot_ids=None, license_photo=None):
        """Submit a booking for one OR several (car+interval) slots as a single
        group. `slot_ids` (a list) is the multi-slot entry point; a lone
        `slot_id` still works (a group of one), so the original single-slot
        callers/tests are unchanged. Whatever the count, every requested slot
        that is still live is inserted as one group (shared group_id), ONE
        confirmation email is sent, and the response reports what was booked vs
        what was just taken.

        `license_photo` (a base64 data-URL string) is OPTIONAL: when present it
        is folded into `extra_answers` alongside the licence number/consents so
        every booking in the group carries it; when absent, extra_answers is
        left untouched and the fișă's photo column stays null at confirm."""
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
        # Resolve the requested slots (dedup, preserve order). A lone slot_id is a
        # group of one.
        raw_ids = slot_ids if slot_ids is not None else ([slot_id] if slot_id is not None else [])
        requested = []
        for sid in raw_ids:
            try:
                sid = int(sid)
            except (TypeError, ValueError):
                continue
            if sid not in requested:
                requested.append(sid)
        if not requested:
            return ServiceResult(False, 409, error='Slot no longer available')
        # Keep only the tracked UTM keys, coerced to strings (spec §7).
        utm = {k: str(v) for k, v in (utm or {}).items() if k in _UTM_ALLOWED_KEYS}
        # Rate limits: per contact (counting the whole GROUP as ONE) and per IP.
        if self.repo.count_active_groups_by_contact(phone_e164, email) >= page['max_bookings_per_contact']:
            return ServiceResult(False, 429, error='Booking limit reached for this contact')
        if self.repo.count_recent_by_ip(ip, now - timedelta(hours=1)) >= _MAX_ATTEMPTS_PER_IP_PER_HOUR:
            return ServiceResult(False, 429, error='Too many attempts, try later')
        # Filter to the slots that belong to this page and are live right now.
        avail = {s['id']: s for s in self.slots.available_slots(page['id'], now)}
        to_book = [avail[sid] for sid in requested if sid in avail]
        if not to_book:
            return ServiceResult(False, 409, error='Slot no longer available')
        # Fold the optional licence photo into extra_answers (only when given,
        # so a photo-less submit leaves extra_answers -- and later the fișă's
        # driver_license_photo column -- exactly as before).
        if license_photo:
            extra_answers = {**(extra_answers or {}), 'license_photo': license_photo}
        # One shared group_id ties the batch together for confirm/cancel.
        group_id = secrets.token_urlsafe(12)
        expires_at = now + timedelta(minutes=_PENDING_TTL_MINUTES)
        rows = []
        for slot in to_book:
            row = {
                'page_id': page['id'], 'slot_id': slot['id'], 'car_id': slot['car_id'],
                'customer_name': name, 'customer_phone_e164': phone_e164,
                'customer_email': email, 'group_id': group_id,
                'utm': utm, 'ip': ip, 'user_agent': user_agent,
                'expires_at': expires_at,
            }
            # Legal fields (licence + consents) captured at submit ride on EACH
            # booking, so each confirmed fișă carries them; route enforces (422).
            if extra_answers:
                row['extra_answers'] = extra_answers
            rows.append(row)
        # Per-row insert: a slot lost to a racing booking (UniqueViolation) is
        # skipped; the rest still commit.
        created = self.repo.create_bookings_group(rows)
        if not created:
            return ServiceResult(False, 409, error='Slot just taken')
        created_slot_ids = {b['slot_id'] for b in created}
        unavailable = [sid for sid in requested if sid not in created_slot_ids]
        booked = []
        for b in created:
            s = avail.get(b['slot_id'])
            booked.append({
                'booking_id': b['id'], 'slot_id': b['slot_id'], 'car_id': b['car_id'],
                'starts_at': s['starts_at'].isoformat() if s else None,
                'ends_at': s['ends_at'].isoformat() if s else None,
            })
        # ONE email with a group confirm + cancel link (a group of one gets the
        # same single-tap experience).
        secret = current_app.secret_key
        confirm_token = make_group_token(group_id, 'confirm', secret)
        cancel_token = make_group_token(group_id, 'cancel', secret)
        confirm_link = f"{base_url}/td/confirm?token={confirm_token}"
        cancel_link = f"{base_url}/td/cancel?token={cancel_token}"
        n = len(created)
        what = 'programarea la test drive' if n == 1 else f'cele {n} programări la test drive'
        # Escape the customer-supplied name before interpolating it into the email
        # HTML (spec §7); the raw name is fine in the DB column since React escapes
        # it in staff views, but the email body is raw HTML.
        body = (
            f"<p>Bună, {html.escape(name)}!</p>"
            f"<p>Confirmă {what} dintr-un singur click: "
            f"<a href='{confirm_link}'>Confirmă</a></p>"
            f"<p>Dacă nu mai poți ajunge, anulează: <a href='{cancel_link}'>aici</a></p>"
        )
        send_customer_message('email', email, 'Confirmă programarea la test drive', body)
        data = {'group_id': group_id, 'booked': booked, 'unavailable': unavailable}
        # Backward-compatible single-slot shape (a group of one): the original
        # callers/tests read booking_id + status directly off the response.
        if n == 1:
            data['booking_id'] = created[0]['id']
            data['status'] = 'pending_confirm'
        return ServiceResult(True, 201, data=data)

    # ---- confirm ----
    def confirm_booking(self, token, base_url=None):
        data = read_booking_token(token, current_app.secret_key)
        if not data or data['act'] != 'confirm':
            return ServiceResult(False, 410, error='Link invalid or expired')
        if data.get('gid'):
            return self._confirm_group(data['gid'])
        booking = self.repo.get_booking(data['bid'])
        if not booking:
            return ServiceResult(False, 404, error='Booking not found')
        if booking['status'] == 'confirmed':
            # Idempotent: a re-clicked confirm link is a success, not an error.
            return ServiceResult(True, 200, data={'status': 'confirmed',
                                                  'fp_id': booking.get('foi_de_parcurs_id')})
        if booking['status'] != 'pending_confirm' or _as_aware(booking['expires_at']) < datetime.now(timezone.utc):
            return ServiceResult(False, 410, error='Booking expired or already handled')

        crm_client_id = self._find_or_create_crm_client(booking)
        try:
            fp_id = self._confirm_pending(booking, crm_client_id)
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
        return ServiceResult(True, 200, data={'status': 'confirmed', 'fp_id': fp_id})

    def _confirm_group(self, group_id):
        """Confirm every still-pending booking in a group. Each booking runs the
        same race-safe atomic confirm as the single path; a per-booking conflict
        marks ONLY that one 'conflict' and the rest proceed. Idempotent: already
        -confirmed bookings are counted, not re-created. Returns
        {confirmed, conflicts}."""
        bookings = self.repo.get_group(group_id)
        if not bookings:
            return ServiceResult(False, 410, error='Link invalid or expired')
        now = datetime.now(timezone.utc)
        confirmed = conflicts = 0
        crm_client_id = None
        for booking in bookings:
            if booking['status'] == 'confirmed':
                confirmed += 1
                continue
            if booking['status'] != 'pending_confirm' or _as_aware(booking['expires_at']) < now:
                continue
            # Find-or-create the CRM client once (all bookings share the contact).
            if crm_client_id is None:
                crm_client_id = self._find_or_create_crm_client(booking)
            try:
                self._confirm_pending(booking, crm_client_id)
                confirmed += 1
            except TdBookingNotPending:
                # A racing/duplicate confirm already finished this one -- count it
                # confirmed if so, never flip a good booking to 'conflict'.
                fresh = self.repo.get_booking(booking['id'])
                if fresh and fresh['status'] == 'confirmed':
                    confirmed += 1
            except TdConflict:
                self.repo.mark_status(booking['id'], 'conflict')
                conflicts += 1
        if confirmed == 0 and conflicts == 0:
            return ServiceResult(False, 410, error='Booking expired or already handled')
        return ServiceResult(True, 200, data={'confirmed': confirmed, 'conflicts': conflicts})

    def _find_or_create_crm_client(self, booking):
        """Find-or-create the CRM client by normalized phone (crm_clients, not
        fp_clients) and mirror the customer's driving licence onto it (best-effort).
        Returns the crm_client_id (or None if creation failed)."""
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
        return crm_client_id

    def _confirm_pending(self, booking, crm_client_id):
        """Confirm ONE pending booking into a PLANNED fișă via the race-safe
        atomic confirm, then persist the CRM link + advisor and notify staff.
        Returns the new fp_id; propagates TdConflict / TdBookingNotPending to the
        caller (single vs group each handle them differently)."""
        page = self.repo.get_page(booking['page_id'])
        car = self.repo.get_car(booking['car_id'])
        slot = self.repo.query_one('SELECT * FROM mkt_td_slots WHERE id=%s', (booking['slot_id'],))
        advisor_id = car.get('default_advisor_user_id') if car else None
        advisor_name = self._advisor_name(advisor_id)

        fp_row = self._build_fp_row(booking, page, car, slot, advisor_name)
        res = self.repo.confirm_booking_atomic(
            booking['id'], car['vin'], slot['starts_at'], slot['ends_at'], fp_row)
        # confirm_booking_atomic already flipped status + foi_de_parcurs_id; this
        # persists the CRM link + advisor that the atomic step doesn't know about.
        self.repo.mark_confirmed(booking['id'], crm_client_id, res['fp_id'], advisor_id)
        self._notify_staff(page, booking, advisor_id)
        return res['fp_id']

    # ---- cancel ----
    def cancel_booking(self, token):
        data = read_booking_token(token, current_app.secret_key)
        if not data or data['act'] != 'cancel':
            return ServiceResult(False, 410, error='Link invalid or expired')
        if data.get('gid'):
            return self._cancel_group(data['gid'])
        booking = self.repo.get_booking(data['bid'])
        if not booking:
            return ServiceResult(False, 404, error='Booking not found')
        if booking['status'] in ('cancelled', 'expired'):
            return ServiceResult(True, 200, data={'status': booking['status']})
        self.repo.mark_cancelled(booking['id'])
        self._delete_planned_fp(booking)
        return ServiceResult(True, 200, data={'status': 'cancelled'})

    def _cancel_group(self, group_id):
        """Cancel every booking in a group and free each one's PLANNED fișă."""
        bookings = self.repo.get_group(group_id)
        if not bookings:
            return ServiceResult(False, 410, error='Link invalid or expired')
        for booking in bookings:
            self._delete_planned_fp(booking)
        self.repo.mark_group_cancelled(group_id)
        return ServiceResult(True, 200, data={'status': 'cancelled'})

    def _delete_planned_fp(self, booking):
        """If confirm already created a PLANNED FP row, hard-delete it so the car /
        slot is freed (mirrors the staff PLANNED-only discard). Never touch an FP
        row that has already progressed past PLANNED (car handed over)."""
        fp_id = booking.get('foi_de_parcurs_id')
        if fp_id:
            fp = self.fp.get_contract_by_id(fp_id)
            if fp and fp.get('status') == 'PLANNED':
                self.fp.delete_contract(fp_id)

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
        lic_photo = (extra.get('license_photo') or '').strip()
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
        # Licence photo is OPTIONAL (unlike serie/number above): when the
        # customer skipped it, extra_answers has no 'license_photo' key and
        # driver_license_photo is simply never set, leaving the column null.
        if lic_photo:
            row['driver_license_photo'] = lic_photo
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
