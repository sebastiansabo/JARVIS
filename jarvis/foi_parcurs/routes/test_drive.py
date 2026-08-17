"""Routes for Test Drive form submission."""
import json
import re
import time
import uuid
from datetime import datetime, timezone
from ._shared import (
    foi_parcurs_bp, jsonify, request, login_required, current_user,
    logger, _fp_repo, _inspection_repo, _crm_client_repo, _vehicle_repo,
    _dealer_repo, open_session_block, is_privileged,
)
from ..services.fuel_service import parse_fuel_level

# International E.164 (+ and 7–15 digits) plus legacy RO national formats so
# existing stored numbers still validate.
_PHONE_RE = re.compile(r'^(\+\d{7,15}|07\d{8}|004\d{10})$')


def _company_gdpr_text(company_id) -> str:
    """The company's configured GDPR text ('' when unset/missing)."""
    try:
        from core.organization.repositories.company_repository import CompanyRepository
        row = CompanyRepository().get(int(company_id))
        return ((row or {}).get('gdpr_text') or '')
    except Exception:
        logger.warning('gdpr_text lookup failed at submit for company_id=%s', company_id, exc_info=True)
        return ''


def _normalize_name(name: str) -> str:
    """Lowercase + collapse whitespace for crm_clients.name_normalized (trigram-indexed)."""
    return re.sub(r'\s+', ' ', (name or '').strip().lower())


@foi_parcurs_bp.route('/api/foi-parcurs/test-drive', methods=['POST'])
@login_required
def api_submit_test_drive():
    """Submit test drive form — creates FILLED contract."""
    data = request.get_json(silent=True) or {}
    is_draft = data.get('status') == 'PLANNED'
    is_internal = bool(data.get('is_internal'))

    # `itinerary` is intentionally NOT required — the mobile Test Drive form
    # dropped the Traseu/Itinerariu field. It's still stored when provided
    # (e.g. by the web form) via data.get('itinerary', '') below.
    if is_internal:
        # Internal driving log (QuickSession) — no customer, no signature, no
        # fuel/estimate. Just the car, the driver, the times and the start km.
        required = ['company_id', 'vin', 'departure_datetime',
                    'odometer_start', 'advisor_name']
    elif is_draft:
        # Planning a session only needs the car, the client (name) and the
        # date. Odometer/fuel/advisor/signature are all deferred to activation.
        required = ['company_id', 'vin', 'client_id', 'departure_datetime']
    else:
        required = ['company_id', 'vin', 'client_id', 'odometer_start', 'estimated_km',
                    'fuel_gauge_start_level', 'departure_datetime', 'advisor_name',
                    'client_signature']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({'success': False, 'error': f'Missing: {", ".join(missing)}'}), 400

    # Block new sessions for a car locked out of the driving park — unless the
    # user explicitly overrode it (allow_locked) after confirming the warning.
    if not data.get('allow_locked'):
        _lock = _vehicle_repo.get_lock_by_vin(data['vin'])
        if _lock and _lock.get('locked_out'):
            _cat, _note = _lock.get('lockout_category'), _lock.get('lockout_note')
            msg = 'Mașină blocată în parcul auto' + (f' ({_cat})' if _cat else '') + (f': {_note}' if _note else '')
            return jsonify({'success': False, 'error': msg, 'locked_out': True}), 409

    # Single-open-session rule (Rule A): a car that already has a session out
    # (FILLED, not returned) can't start a new one — only when actually starting
    # (a PLANNED draft is fine). Admins may override with allow_open_session.
    if not is_draft:
        _priv = is_privileged()
        _osb = open_session_block(data['vin'], allow_override=data.get('allow_open_session'), privileged=_priv)
        if _osb:
            return jsonify(_osb[0]), _osb[1]

    if not is_draft and not is_internal and _company_gdpr_text(data.get('company_id')).strip() and not data.get('gdpr_consent'):
        return jsonify({'success': False, 'error': 'GDPR consent is required'}), 400

    # General conditions (per company+brand) — required only when configured.
    general_conditions_text = ''
    try:
        _veh = _vehicle_repo.get_by_vin(data['vin'])
        _brand = (_veh or {}).get('brand') or ''
        general_conditions_text = _dealer_repo.get_general_conditions(int(data['company_id']), _brand) or ''
    except Exception:
        logger.warning('general-conditions lookup failed at submit', exc_info=True)
        general_conditions_text = ''
    if not is_draft and not is_internal and general_conditions_text.strip() and not data.get('general_conditions_accepted'):
        return jsonify({'success': False, 'error': 'General conditions acceptance is required'}), 400

    contract_id = f"TD-{data['vin'][:8]}-{int(time.time())}-{uuid.uuid4().hex[:4]}"

    try:
        # Derive fuel liters from gauge levels × tank capacity (single source of truth).
        tank = int(data.get('fuel_tank_capacity_liters', 0))
        start_level = data.get('fuel_gauge_start_level') or '1'
        end_level = data.get('fuel_gauge_end_level', start_level)
        try:
            start_fraction = parse_fuel_level(str(start_level))
            end_fraction = parse_fuel_level(str(end_level))
        except ValueError:
            start_fraction, end_fraction = 1.0, 1.0
        fuel_start_liters = round(start_fraction * tank, 2)
        fuel_end_liters = round(end_fraction * tank, 2)
        fuel_consumed_liters = round(max(0.0, fuel_start_liters - fuel_end_liters), 2)

        # Client comes from the CRM (crm_clients), not the legacy fp_clients table.
        # Resolve name/phone now and store them directly on the contract so old
        # contracts (joined via fp_clients) and new ones (CRM-sourced) both resolve.
        if is_internal:
            client_id = None
            client_name = None
            client_phone = None
        else:
            client_id = int(data['client_id'])
            crm_client = _crm_client_repo.get_by_id(client_id)
            client_name = crm_client.get('display_name') if crm_client else None
            client_phone = crm_client.get('phone') if crm_client else None

        # Structured vehicle-condition report captured at handover (optional).
        departure_damage = data.get('departure_damage') or []
        if not isinstance(departure_damage, list):
            return jsonify({'success': False, 'error': 'departure_damage must be a list'}), 400

        contract_data = {
            'contract_id': contract_id,
            'vin': data['vin'],
            'registration_number': data.get('registration_number', ''),
            'company_id': int(data['company_id']),
            'client_id': client_id,
            'client_name': client_name,
            'client_phone': client_phone,
            'route_type': 'TD',
            'slot_number': 0,
            'km_start': int(data.get('odometer_start') or 0),
            'km_end': int(data.get('odometer_end') or 0) or int(data.get('odometer_start') or 0),
            'distance_km': int(data.get('estimated_km') or 0),
            'fuel_tank_capacity_liters': tank,
            'fuel_gauge_start_level': start_level,
            'fuel_gauge_end_level': end_level,
            'fuel_start_liters': fuel_start_liters,
            'fuel_end_liters': fuel_end_liters,
            'fuel_consumed_liters': fuel_consumed_liters,
            'itinerary': data.get('itinerary', ''),
            'general_observation': (data.get('general_observation') or '').strip() or None,
            'advisor_name': data.get('advisor_name', ''),
            'signature_ai_generated': data.get('advisor_signature', ''),
            'client_signature': data.get('client_signature', ''),
            'departure_datetime': data['departure_datetime'],
            'return_datetime': data.get('return_datetime'),
            'departure_damage': json.dumps(departure_damage),
            'driver_license_photo': data.get('driver_license_photo'),
            'driver_license_number': data.get('driver_license_number'),
            'driver_license_expiry': (data.get('driver_license_expiry') or '').strip() or None,
            # Live submit keeps the historical hardcoded True (GDPR is gated by the
            # validation above); a PLANNED draft stores whatever was sent (consent
            # is deferred to activation, so typically absent → False).
            'gdpr_consent': bool(data.get('gdpr_consent')) if is_draft else True,
            'inspection_acceptance': bool(data.get('inspection_acceptance')),
            'inspection_id': data.get('inspection_id'),
            # Optional link to a marketing project/campaign (nullable).
            'mkt_project_id': int(data['mkt_project_id']) if data.get('mkt_project_id') else None,
            'source': 'td_form',
            'status': 'PLANNED' if is_draft else 'FILLED',
            'is_internal': is_internal,
        }
        if not is_draft and general_conditions_text.strip():
            contract_data['general_conditions_accepted'] = True
            contract_data['general_conditions_accepted_at'] = datetime.now(timezone.utc)
            contract_data['general_conditions_text'] = general_conditions_text

        contract = _fp_repo.create_from_td_form(contract_data)

        # Keep the client's driving license on their CRM record, so it's prefilled
        # on the next test drive (front-end checks the expiry when reusing it).
        try:
            lic_no = (data.get('driver_license_number') or '').strip()
            lic_exp = (data.get('driver_license_expiry') or '').strip()
            if client_id and (lic_no or lic_exp):
                _crm_client_repo.execute(
                    "UPDATE crm_clients SET "
                    "driver_license_number = COALESCE(NULLIF(%s, ''), driver_license_number), "
                    "driver_license_expiry = COALESCE(NULLIF(%s, ''), driver_license_expiry) "
                    "WHERE id = %s",
                    (lic_no, lic_exp, client_id),
                )
        except Exception:
            logger.warning('Could not store driving license on CRM client %s', client_id, exc_info=True)

        # Generate PDFs (skipped for PLANNED drafts + internal sessions — no
        # signature/GDPR/contract captured for those)
        if not is_draft and not is_internal:
            try:
                from ..services.pdf_service import generate_legal_pdf, generate_custom_pdf
                legal_path = generate_legal_pdf(contract)
                custom_path = generate_custom_pdf(contract)
                _fp_repo.execute(
                    'UPDATE foi_de_parcurs SET pdf_legal_path = %s, pdf_custom_path = %s WHERE id = %s',
                    (legal_path, custom_path, contract['id']),
                )
                contract['pdf_legal_path'] = legal_path
                contract['pdf_custom_path'] = custom_path
            except Exception:
                logger.exception('PDF generation failed for contract %s', contract.get('contract_id'))

            # Email the client (+ consilier) the contract at the start of the drive
            # (simplified mail — contract PDF only, no review QR / offer doc).
            try:
                _autosend_contract(contract['id'], simple=True)
            except Exception:
                logger.warning('Start-of-session email failed for contract %s', contract.get('id'), exc_info=True)

        return jsonify({'success': True, 'contract': contract})

    except Exception as e:
        logger.exception('Failed to submit test drive form')
        return jsonify({'success': False, 'error': str(e)[:300]}), 500


@foi_parcurs_bp.route('/api/foi-parcurs/test-drive/<int:id>/activate', methods=['PUT'])
@login_required
def api_activate_test_drive(id):
    """Activate a PLANNED draft: capture the client signature + any handover
    edits, flip to FILLED, generate the PDFs (mirrors the live-submit path)."""
    data = request.get_json(silent=True) or {}
    try:
        contract = _fp_repo.get_contract_by_id(id)
        if not contract:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        if contract.get('route_type') != 'TD' or contract.get('status') != 'PLANNED':
            return jsonify({'success': False, 'error': 'Contract is not a PLANNED draft'}), 400
        # Block activation if the car has since been locked out — unless overridden.
        if not data.get('allow_locked'):
            _lock = _vehicle_repo.get_lock_by_vin(contract.get('vin'))
            if _lock and _lock.get('locked_out'):
                _cat, _note = _lock.get('lockout_category'), _lock.get('lockout_note')
                msg = 'Mașină blocată în parcul auto' + (f' ({_cat})' if _cat else '') + (f': {_note}' if _note else '')
                return jsonify({'success': False, 'error': msg, 'locked_out': True}), 409
        # Single-open-session rule: don't activate a draft while the car is still
        # out on another session (unless an admin overrides).
        _priv = is_privileged()
        _osb = open_session_block(contract.get('vin'), exclude_id=id,
                                  allow_override=data.get('allow_open_session'), privileged=_priv)
        if _osb:
            return jsonify(_osb[0]), _osb[1]
        if not data.get('client_signature'):
            return jsonify({'success': False, 'error': 'client_signature is required'}), 400

        # General conditions (per company+brand) — required only when configured.
        # Mirrors the live-submit gate: a PLANNED draft defers this to activation.
        general_conditions_text = ''
        try:
            _veh = _vehicle_repo.get_by_vin(contract.get('vin'))
            _brand = (_veh or {}).get('brand') or ''
            general_conditions_text = _dealer_repo.get_general_conditions(int(contract['company_id']), _brand) or ''
        except Exception:
            logger.warning('general-conditions lookup failed at activation', exc_info=True)
            general_conditions_text = ''
        if general_conditions_text.strip() and not data.get('general_conditions_accepted'):
            return jsonify({'success': False, 'error': 'General conditions acceptance is required'}), 400

        tank = int(data.get('fuel_tank_capacity_liters', contract.get('fuel_tank_capacity_liters') or 0))
        start_level = data.get('fuel_gauge_start_level') or contract.get('fuel_gauge_start_level') or '1'
        try:
            start_fraction = parse_fuel_level(str(start_level))
        except ValueError:
            start_fraction = 1.0
        fuel_start_liters = round(start_fraction * tank, 2)

        update = {
            'client_signature': data['client_signature'],
            'signature_ai_generated': data.get('advisor_signature', contract.get('signature_ai_generated', '')),
            'gdpr_consent': bool(data.get('gdpr_consent', True)),
            'fuel_gauge_start_level': start_level,
            'fuel_start_liters': fuel_start_liters,
        }
        # Live-refresh the starting odometer to the car's latest reading across
        # ALL its sessions. A draft planned earlier must not start below the
        # mileage the car has actually reached since; a higher manual reading
        # (car drove further) still wins.
        _floor = _fp_repo.get_mileage_floor(contract.get('vin'), exclude_id=id)
        _provided = data.get('odometer_start')
        _base = int(_provided) if _provided is not None else (contract.get('km_start') or 0)
        update['km_start'] = max(_base, _floor)
        if data.get('departure_datetime'):
            update['departure_datetime'] = data['departure_datetime']
        if data.get('return_datetime'):
            update['return_datetime'] = data['return_datetime']
        if data.get('departure_damage') is not None:
            update['departure_damage'] = data['departure_damage']
        if data.get('general_observation') is not None:
            update['general_observation'] = (data.get('general_observation') or '').strip() or None
        if general_conditions_text.strip():
            update['general_conditions_accepted'] = True
            update['general_conditions_accepted_at'] = datetime.now(timezone.utc)
            update['general_conditions_text'] = general_conditions_text

        updated = _fp_repo.record_activation(id, update)
        # record_activation only matches PLANNED TD rows; a concurrent/duplicate
        # activation flips it to FILLED first, so a zero-row UPDATE returns falsy.
        # Report that instead of a false 200 with a null contract.
        if not (updated and updated.get('id')):
            return jsonify({'success': False, 'error': 'Contract is no longer a PLANNED draft'}), 409

        try:
            from ..services.pdf_service import generate_legal_pdf, generate_custom_pdf
            legal_path = generate_legal_pdf(updated)
            custom_path = generate_custom_pdf(updated)
            _fp_repo.execute(
                'UPDATE foi_de_parcurs SET pdf_legal_path = %s, pdf_custom_path = %s WHERE id = %s',
                (legal_path, custom_path, id),
            )
            updated['pdf_legal_path'] = legal_path
            updated['pdf_custom_path'] = custom_path
        except Exception:
            logger.exception('PDF generation failed activating contract %s', id)

        # Email the client (+ consilier) the contract as the drive starts
        # (simplified mail — contract PDF only).
        try:
            _autosend_contract(id, simple=True)
        except Exception:
            logger.warning('Start-of-session email failed for contract %s', id, exc_info=True)

        return jsonify({'success': True, 'contract': updated})
    except Exception as e:
        logger.exception('Failed to activate planned test drive %s', id)
        return jsonify({'success': False, 'error': str(e)[:300]}), 500


@foi_parcurs_bp.route('/api/foi-parcurs/test-drive/<int:id>/plan', methods=['PUT'])
@login_required
def api_update_plan(id):
    """Edit a PLANNED draft (date/time/vehicle/client/km/fuel) without activating.
    PLANNED-only; status stays PLANNED, no signature/PDF."""
    data = request.get_json(silent=True) or {}
    try:
        contract = _fp_repo.get_contract_by_id(id)
        if not contract:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        if contract.get('route_type') != 'TD' or contract.get('status') != 'PLANNED':
            return jsonify({'success': False, 'error': 'Only PLANNED drafts can be edited'}), 409

        update = {}
        if data.get('company_id') is not None:
            update['company_id'] = int(data['company_id'])
        if data.get('vin'):
            update['vin'] = data['vin']
        if data.get('client_id') is not None:
            cid = int(data['client_id'])
            update['client_id'] = cid
            crm = _crm_client_repo.get_by_id(cid) or {}
            update['client_name'] = crm.get('display_name')
            update['client_phone'] = crm.get('phone')
        if data.get('registration_number') is not None:
            update['registration_number'] = data.get('registration_number', '')
        if data.get('advisor_name'):
            update['advisor_name'] = data['advisor_name']
        if data.get('departure_datetime'):
            update['departure_datetime'] = data['departure_datetime']
        if 'return_datetime' in data:
            update['return_datetime'] = data.get('return_datetime')
        if data.get('odometer_start') is not None:
            update['km_start'] = int(data['odometer_start'])
        if data.get('estimated_km') is not None:
            update['distance_km'] = int(data['estimated_km'])
        if data.get('fuel_gauge_start_level'):
            level = data['fuel_gauge_start_level']
            tank = int(data.get('fuel_tank_capacity_liters', contract.get('fuel_tank_capacity_liters') or 0))
            try:
                frac = parse_fuel_level(str(level))
            except ValueError:
                frac = 1.0
            update['fuel_gauge_start_level'] = level
            update['fuel_start_liters'] = round(frac * tank, 2)
            if tank:
                update['fuel_tank_capacity_liters'] = tank
        if data.get('departure_damage') is not None:
            if not isinstance(data['departure_damage'], list):
                return jsonify({'success': False, 'error': 'departure_damage must be a list'}), 400
            update['departure_damage'] = data['departure_damage']
        if 'mkt_project_id' in data:
            update['mkt_project_id'] = int(data['mkt_project_id']) if data.get('mkt_project_id') else None

        if not update:
            return jsonify({'success': False, 'error': 'No editable fields provided'}), 400

        updated = _fp_repo.update_plan(id, update)
        if not (updated and updated.get('id')):
            return jsonify({'success': False, 'error': 'Contract is no longer a PLANNED draft'}), 409
        return jsonify({'success': True, 'contract': updated})
    except Exception as e:
        logger.exception('Failed to edit planned test drive %s', id)
        return jsonify({'success': False, 'error': str(e)[:300]}), 500


@foi_parcurs_bp.route('/api/foi-parcurs/test-drive/<int:id>/reschedule', methods=['PUT'])
@login_required
def api_reschedule_test_drive(id):
    """Reschedule a PLANNED (late) or MISSED session to a new future time,
    reviving it to PLANNED. VIN conflicts are soft-checked client-side (the
    conflicts endpoint), mirroring plan/activate — this endpoint only moves it."""
    data = request.get_json(silent=True) or {}
    departure = data.get('departure_datetime')
    if not departure:
        return jsonify({'success': False, 'error': 'departure_datetime is required'}), 400
    try:
        contract = _fp_repo.get_contract_by_id(id)
        if not contract:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        if contract.get('route_type') != 'TD' or contract.get('status') not in ('PLANNED', 'MISSED'):
            return jsonify({'success': False, 'error': 'Only planned or missed sessions can be rescheduled'}), 409
        try:
            dep_dt = datetime.fromisoformat(str(departure).replace('Z', '+00:00'))
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid departure_datetime'}), 400
        if dep_dt.date() < datetime.now(timezone.utc).date():
            return jsonify({'success': False, 'error': 'Cannot reschedule to a past date'}), 400
        ret = data.get('return_datetime')
        if ret:
            try:
                ret_dt = datetime.fromisoformat(str(ret).replace('Z', '+00:00'))
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid return_datetime'}), 400
            if ret_dt < dep_dt:
                return jsonify({'success': False, 'error': 'return_datetime cannot be before departure_datetime'}), 400
        updated = _fp_repo.reschedule_session(id, departure, data.get('return_datetime'))
        if not (updated and updated.get('id')):
            return jsonify({'success': False, 'error': 'Session is no longer reschedulable'}), 409
        return jsonify({'success': True, 'contract': updated})
    except Exception as e:
        logger.exception('Failed to reschedule test drive %s', id)
        return jsonify({'success': False, 'error': str(e)[:300]}), 500


@foi_parcurs_bp.route('/api/foi-parcurs/test-drive/<int:id>/extend', methods=['PUT'])
@login_required
def api_extend_test_drive(id):
    """Advisor extends an OPEN (FILLED) test drive's return time when the client
    keeps the car longer and the return hasn't been recorded yet. Any logged-in
    user; status/km unchanged; the overdue-return alert recomputes against the
    new time. Records who did it (corrected_by) → 'Modificat' marker."""
    data = request.get_json(silent=True) or {}
    ret = data.get('return_datetime')
    if not ret:
        return jsonify({'success': False, 'error': 'return_datetime is required'}), 400
    contract = _fp_repo.get_contract_by_id(id)
    if not contract:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    if contract.get('route_type') != 'TD' or contract.get('status') != 'FILLED':
        return jsonify({'success': False, 'error': 'Only an open (in-progress) test drive can be extended'}), 409
    try:
        ret_dt = datetime.fromisoformat(str(ret).replace('Z', '+00:00'))
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid return_datetime'}), 400
    # Normalize to naive: the frontend sends a naive datetime-local value, while
    # departure_datetime comes back tz-aware from the DB (dict_from_row) — a
    # direct naive-vs-aware comparison raises TypeError.
    if ret_dt.tzinfo:
        ret_dt = ret_dt.replace(tzinfo=None)
    dep = contract.get('departure_datetime')
    if dep:
        try:
            dep_dt = datetime.fromisoformat(str(dep).replace('Z', '+00:00'))
            if dep_dt.tzinfo:
                dep_dt = dep_dt.replace(tzinfo=None)
        except ValueError:
            dep_dt = None
        if dep_dt and ret_dt < dep_dt:
            return jsonify({'success': False,
                            'error': 'return_datetime cannot be before departure_datetime'}), 400
    updated = _fp_repo.extend_return(id, ret, getattr(current_user, 'email', None))
    if not updated:
        return jsonify({'success': False, 'error': 'Session is no longer extendable'}), 409
    logger.info('foi-parcurs TD %s return extended to %s by %s',
                id, ret, getattr(current_user, 'email', '?'))
    return jsonify({'success': True, 'contract': updated})


def _autosend_contract(contract_id, simple=False):
    """Email the contract PDF to the client + consilier. Best-effort — recipients
    are deduped and failures are logged, never raised. Client email comes from
    crm_clients (where TD clients live), the consilier's from the users table (by
    advisor_name). `simple=True` sends the simplified start-of-session mail
    (contract PDF only); the completion auto-send keeps the full mail (review QR +
    offer doc)."""
    from .pdf import email_contract_pdf, _consilier_contact
    full = _fp_repo.get_contract_by_id(contract_id)
    if not full:
        return
    recipients = set()
    client_id = full.get('client_id')
    if client_id:
        try:
            row = _fp_repo.query_one('SELECT email FROM crm_clients WHERE id = %s', (client_id,))
            if row and (row.get('email') or '').strip():
                recipients.add(row['email'].strip())
        except Exception:
            logger.warning('crm_clients email lookup failed for client %s', client_id, exc_info=True)
    if (full.get('client_email') or '').strip():
        recipients.add(full['client_email'].strip())
    cons = _consilier_contact(full.get('advisor_name'))
    if (cons.get('email') or '').strip():
        recipients.add(cons['email'].strip())

    for addr in recipients:
        try:
            ok, err = email_contract_pdf(full, addr, simple=simple)
            if not ok:
                logger.warning('Auto-email to %s failed for contract %s: %s', addr, contract_id, err)
        except Exception:
            logger.warning('Auto-email to %s errored for contract %s', addr, contract_id, exc_info=True)


@foi_parcurs_bp.route('/api/foi-parcurs/test-drive/<int:id>/return', methods=['PUT'])
@login_required
def api_return_test_drive(id):
    """Complete a test drive by recording return data (km/fuel/damage/signatures)."""
    data = request.get_json(silent=True) or {}

    try:
        contract = _fp_repo.get_contract_by_id(id)
        if not contract:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        if contract.get('route_type') != 'TD':
            return jsonify({'success': False, 'error': 'Contract is not a Test Drive'}), 400

        advisor_signature = data.get('advisor_signature')
        client_signature = data.get('client_signature')
        if not advisor_signature or not client_signature:
            return jsonify({
                'success': False,
                'error': 'Both advisor_signature and client_signature are required',
            }), 400

        km_end = data.get('km_end')
        if km_end is None:
            return jsonify({'success': False, 'error': 'km_end is required'}), 400
        try:
            km_end = int(km_end)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'km_end must be a number'}), 400

        km_start = contract.get('km_start')
        if km_start is not None and km_end < km_start:
            return jsonify({
                'success': False,
                'error': f'km_end ({km_end}) cannot be less than km_start ({km_start})',
            }), 400

        return_damage = data.get('return_damage') or []
        if not isinstance(return_damage, list):
            return jsonify({'success': False, 'error': 'return_damage must be a list'}), 400

        update_data = {
            'km_end': km_end,
            'fuel_gauge_end_level': data.get('fuel_gauge_end_level'),
            'return_datetime': data.get('return_datetime'),
            'return_damage': return_damage,
            'return_notes': data.get('return_notes'),
            'return_advisor_signature': advisor_signature,
            'return_client_signature': client_signature,
        }

        updated = _fp_repo.record_return(id, update_data)

        # Advance the vehicle's stored odometer to the latest reading (never backwards)
        try:
            vin = contract.get('vin')
            if vin:
                veh = _vehicle_repo.get_by_vin(vin)
                if veh and (veh.get('odometer_km') is None or km_end > veh['odometer_km']):
                    _vehicle_repo.update(veh['id'], {'odometer_km': km_end})
        except Exception:
            logger.warning('Could not advance vehicle odometer after return for contract %s', id, exc_info=True)

        # On completion, auto-send the finished contract to the client + consilier.
        try:
            _autosend_contract(id)
        except Exception:
            logger.warning('Auto-send on completion failed for contract %s', id, exc_info=True)

        return jsonify({'success': True, 'contract': updated})

    except Exception as e:
        logger.exception('Failed to record test drive return for contract %s', id)
        return jsonify({'success': False, 'error': str(e)[:300]}), 500


@foi_parcurs_bp.route('/api/foi-parcurs/test-drive/<int:id>', methods=['GET'])
@login_required
def api_get_test_drive(id):
    """Get test drive form data for a contract."""
    contract = _fp_repo.get_contract_by_id(id)
    if not contract:
        return jsonify({'success': False, 'error': 'Not found'}), 404

    inspection = None
    if contract.get('inspection_id'):
        inspection = _inspection_repo.get_latest(contract['inspection_id'])

    return jsonify({
        'success': True,
        'contract': contract,
        'inspection': inspection,
    })


@foi_parcurs_bp.route('/api/foi-parcurs/test-drive/<int:id>', methods=['DELETE'])
@login_required
def api_discard_test_drive(id):
    """Discard a PLANNED draft (any TD user). Only PLANNED rows may be deleted
    here — live/completed sessions still require the admin hard-delete route."""
    contract = _fp_repo.get_contract_by_id(id)
    if not contract:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    if contract.get('status') != 'PLANNED':
        return jsonify({'success': False, 'error': 'Only PLANNED drafts can be discarded'}), 409
    _fp_repo.delete_contract(id)
    return jsonify({'success': True})


@foi_parcurs_bp.route('/api/foi-parcurs/driver-license/ocr', methods=['POST'])
@login_required
def api_driver_license_ocr():
    """Extract structured fields from a driving-license photo via Claude vision.

    Body: {"image": "data:image/jpeg;base64,..."} (or bare base64).
    Returns {success, data: {last_name, first_name, full_name, cnp,
    license_number, birth_date, expiry_date, address, city, county}}.
    """
    data = request.get_json(silent=True) or {}
    image = data.get('image')
    if not image:
        return jsonify({'success': False, 'error': 'image is required'}), 400

    try:
        from ..services.license_ocr_service import extract_license_data
        fields = extract_license_data(image)
        return jsonify({'success': True, 'data': fields})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.exception('Driver-license OCR failed')
        return jsonify({'success': False, 'error': str(e)[:300]}), 500


@foi_parcurs_bp.route('/api/foi-parcurs/crm-clients/search', methods=['GET'])
@login_required
def api_search_crm_clients():
    """Login-gated CRM client search for the test-drive flow, so consilieri
    without full CRM (sales) access can find existing clients instead of creating
    duplicates. Mirrors the login-gated create endpoint below."""
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify({'success': True, 'clients': []})
    limit = request.args.get('limit', 20, type=int)
    try:
        rows, _ = _crm_client_repo.search(q=q, limit=min(max(limit, 1), 50))
    except Exception:
        logger.exception('CRM client search failed for q=%r', q)
        return jsonify({'success': False, 'error': 'Search failed'}), 500
    return jsonify({'success': True, 'clients': rows})


@foi_parcurs_bp.route('/api/foi-parcurs/crm-clients', methods=['POST'])
@login_required
def api_create_crm_client():
    """Create a CRM client from the mobile Test Drive form (login-gated, so the
    consilier can create one without full CRM access). Returns the new client."""
    data = request.get_json(silent=True) or {}

    display_name = (data.get('display_name') or data.get('name') or '').strip()
    if not display_name:
        return jsonify({'success': False, 'error': 'display_name is required'}), 400

    phone = (data.get('phone') or '').strip()
    phone_clean = phone.replace(' ', '').replace('-', '')
    if not _PHONE_RE.match(phone_clean):
        return jsonify({
            'success': False,
            'error': 'Invalid phone. Use international format, e.g. +40721234567',
        }), 400

    cnp = (data.get('cnp') or '').strip() or None
    address = (data.get('address') or '').strip() or None
    city = (data.get('city') or '').strip() or None
    county = (data.get('county') or '').strip() or None
    email = (data.get('email') or '').strip() or None
    is_company = bool(data.get('is_company'))
    company_name = (data.get('company_name') or '').strip() or None
    cui = (data.get('cui') or '').strip() or None

    try:
        row = _crm_client_repo.create(
            display_name=display_name,
            name_normalized=_normalize_name(display_name),
            client_type='company' if is_company else 'person',
            phone=phone_clean,
            phone_raw=phone,
            email=email,
            street=address,
            city=city,
            region=county,
            company_name=company_name,
            cui=cui,
            source_flags={'foi_parcurs': True},
        )
        new_id = row['id'] if row else None
        if new_id and cnp:
            _crm_client_repo.execute(
                'UPDATE crm_clients SET cnp = %s WHERE id = %s', (cnp, new_id)
            )
        client = _crm_client_repo.get_by_id(new_id) if new_id else None
        return jsonify({'success': True, 'client': client})
    except Exception as e:
        logger.exception('Failed to create CRM client from Test Drive form')
        return jsonify({'success': False, 'error': str(e)[:300]}), 500


@foi_parcurs_bp.route('/api/foi-parcurs/crm-clients/<int:id>', methods=['PATCH'])
@login_required
def api_update_crm_client(id):
    """Login-gated partial update of a CRM client's contact details
    (phone/email/driver_license_number) from the mobile Test Drive form, so a
    consilier can complete OR correct a selected client's info without full CRM
    access.

    Scope note: only the three contact fields below are editable here, so the
    blast radius is bounded — a consilier can already search and view every
    client, and this lets them fix e.g. a mistyped email on the client they are
    working with. It intentionally allows overwriting existing values (needed to
    correct mistakes), unlike a fill-only endpoint."""
    data = request.get_json(silent=True) or {}

    existing = _crm_client_repo.get_by_id(id)
    if existing is None:
        return jsonify({'success': False, 'error': 'Client not found'}), 404

    update_data = {}

    if 'phone' in data:
        phone = (data.get('phone') or '').strip()
        phone_clean = phone.replace(' ', '').replace('-', '')
        if not _PHONE_RE.match(phone_clean):
            return jsonify({
                'success': False,
                'error': 'Invalid phone. Use international format, e.g. +40721234567',
            }), 400
        update_data['phone'] = phone_clean

    if 'email' in data:
        update_data['email'] = (data.get('email') or '').strip()

    if 'driver_license_number' in data:
        update_data['driver_license_number'] = (data.get('driver_license_number') or '').strip()

    if not update_data:
        return jsonify({'success': True, 'client': existing})

    # Capture old->new for the fields that actually change, for the audit trail.
    changes = {
        k: {'old': existing.get(k), 'new': v}
        for k, v in update_data.items()
        if (existing.get(k) or '') != (v or '')
    }

    try:
        client = _crm_client_repo.update(id, update_data)
    except Exception as e:
        logger.exception('Failed to update CRM client %s from Test Drive form', id)
        return jsonify({'success': False, 'error': str(e)[:300]}), 500

    # Attributable, reversible audit of the change (who, what, old->new).
    # Fail-open: a logging error must not break the legitimate edit.
    if changes:
        try:
            user_id = getattr(current_user, 'id', None)
            _crm_client_repo.execute(
                '''INSERT INTO crm_client_audit (client_id, action, changes, user_id, source)
                   VALUES (%s, %s, %s::jsonb, %s, %s)''',
                (id, 'contact_update', json.dumps(changes), user_id, 'td_form'),
            )
        except Exception:
            logger.exception('Failed to write crm_client_audit for client %s', id)

    return jsonify({'success': True, 'client': client or existing})


@foi_parcurs_bp.route('/api/foi-parcurs/mkt-projects/search', methods=['GET'])
@login_required
def api_search_mkt_projects():
    """Login-gated marketing-project (campaign) search for the test-drive flow,
    so a consilier without marketing access can attach a Test Drive to a
    campaign. Scoped to the given company (direct company_id or membership in
    company_ids) when provided; typing narrows by name/slug."""
    q = (request.args.get('q') or '').strip()
    company_id = request.args.get('company_id', type=int)
    limit = min(max(request.args.get('limit', 20, type=int), 1), 50)

    conditions = ['deleted_at IS NULL']
    params = []
    if company_id:
        conditions.append('(company_id = %s OR %s = ANY(company_ids))')
        params.extend([company_id, company_id])
    if len(q) >= 2:
        conditions.append('(name ILIKE %s OR slug ILIKE %s)')
        like = f'%{q}%'
        params.extend([like, like])
    where = ' AND '.join(conditions)
    params.append(limit)
    try:
        rows = _fp_repo.query_all(
            f'''SELECT id, name, status, company_id, brand_id
                FROM mkt_projects
                WHERE {where}
                ORDER BY updated_at DESC
                LIMIT %s''',
            tuple(params),
        )
    except Exception:
        logger.exception('MKT project search failed for q=%r company_id=%r', q, company_id)
        return jsonify({'success': False, 'error': 'Search failed'}), 500
    return jsonify({'success': True, 'projects': rows})
