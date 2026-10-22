"""Offer routes — post an offer to a buyback record's seller, and record the
seller's decision on it.

Two endpoints:
  - POST /records/<id>/offers            gated by
    @v2_permission_required('buyback', 'offer', 'manage') — opens a new offer
    round (Acquisition-style role).
  - POST /records/<id>/offers/<oid>/decision  gated by
    @v2_permission_required('buyback', 'record', 'edit') — records the
    seller's accept/decline (Sales-style role).

Both apply the SAME company-scoping/IDOR guard as records.py
(_shared._guard_company), loaded via the SAME repo the record routes use
(_shared.records_repo.get_by_id), 404 before that guard runs.

No SQL lives here — every DB access goes through buyback.routes._shared's
singleton repos/service (RecordRepository, OfferRepository, BuyBackService).
Offer invariants (round/status matching, one-pending-offer-per-record,
stale/already-decided-offer rejection) are NOT reimplemented here — they live
in BuyBackService.post_offer / record_decision (Task 8); this route only
translates their ValueError into a 409, mirroring records.py's
cancel_record/reopen_record translation of service.transition's ValueError.
"""
import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import request, jsonify
from flask_login import login_required, current_user

from buyback import buyback_bp, lifecycle
from buyback.routes import _shared
from buyback.services.contract_generation import generate_contract, NoTemplateError
from buyback.services.email import send_contract_email
from core.roles.decorators import v2_permission_required

logger = logging.getLogger('jarvis.buyback')


def _maybe_generate_contract(record_id, updated, signature):
    """After an accept that landed in BOUGHT/CONSIGNAT, best-effort auto-generate
    the contract (seller signature embedded) and email it to the advisor (P4).
    NEVER raises — it runs AFTER the already-committed transition and swallows
    everything, so a template/render/SMTP failure can't undo the accept (mirrors
    send_offer_email). Returns a non-blocking {generated, warnings} summary, or
    None when the accept didn't reach a contract-eligible status."""
    if updated.get('status') not in (lifecycle.BOUGHT, lifecycle.CONSIGNAT):
        return None
    try:
        fresh = _shared.records_repo.get_by_id(record_id)
        result = generate_contract(fresh, signature=signature)
        send_contract_email(fresh, result['pdf_bytes'])
        return {'generated': True, 'warnings': result['warnings']}
    except NoTemplateError:
        logger.info(
            'record %s: accept — no active contract template, contract not auto-generated',
            record_id)
        return {'generated': False,
                'warnings': ['Niciun model de contract activ — contract negenerat']}
    except Exception:
        logger.exception(
            'record %s: accept auto-generate/email raised — swallowed (accept preserved)',
            record_id)
        return {'generated': False, 'warnings': []}

# Offer rounds the service recognizes (BuyBackService._ROUND_REQUIRED_STATUS).
# Validated here too so a missing/garbage offer_type 400s before it reaches
# the service — the service itself also guards this (raises ValueError ->
# 409 via post_offer's `Unknown offer_type` branch), so this is a fast-path
# 400 for the common "forgot the field" case, not a substitute for that guard.
_OFFER_TYPES = ('initial', 'final')


# ═══════════════════════════════════════════════
# POST OFFER
# ═══════════════════════════════════════════════

@buyback_bp.route('/records/<int:record_id>/offers', methods=['POST'])
@login_required
@v2_permission_required('buyback', 'offer', 'manage')
def post_offer(record_id):
    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return jsonify({'success': False, 'error': 'Record not found'}), 404

    err = _shared._guard_company(record)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    offer_type = data.get('offer_type')
    if offer_type not in _OFFER_TYPES:
        return jsonify({
            'success': False,
            'error': f"offer_type is required and must be one of {_OFFER_TYPES!r}",
        }), 400

    # amount_eur is a NOT NULL NUMERIC column — a missing/non-numeric value
    # would otherwise reach OfferRepository.create's INSERT and raise a
    # psycopg2 NotNullViolation/InvalidTextRepresentation (NOT a ValueError,
    # so the except-ValueError below would NOT catch it) → a 500. Validate it
    # up front, mirroring the offer_type check style: require it present and
    # coercible to a Decimal.
    amount_raw = data.get('amount_eur')
    if amount_raw is None or (isinstance(amount_raw, str) and not amount_raw.strip()):
        return jsonify({'success': False, 'error': 'amount_eur is required'}), 400
    try:
        Decimal(str(amount_raw))
    except (InvalidOperation, ValueError, TypeError):
        return jsonify({'success': False, 'error': 'amount_eur must be a number'}), 400

    # valid_until is optional, but a malformed date string would 500 the same
    # way (bad literal reaching the DATE column). When present, require it to
    # parse as an ISO date (YYYY-MM-DD). Absent → the repo defaults it to
    # CURRENT_DATE + 7 days in SQL, so a None/omitted value is fine.
    valid_until = data.get('valid_until')
    if valid_until is not None and valid_until != '':
        try:
            date.fromisoformat(str(valid_until))
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'error': 'valid_until must be an ISO date (YYYY-MM-DD)',
            }), 400

    # Optional: the acquisition team researches the retail value (Preț Piață) and
    # sets it when posting the offer. Validate like a NUMERIC field (a bad value
    # would otherwise reach the record UPDATE and 500), persist it, and refresh
    # `record` so the seller email/PDF (built from it in post_offer) carry the
    # retail price. Blank/omitted leaves the existing value untouched.
    market_raw = data.get('market_price_eur')
    if market_raw is not None and str(market_raw).strip() != '':
        try:
            market_val = Decimal(str(market_raw))
        except (InvalidOperation, ValueError, TypeError):
            return jsonify({'success': False, 'error': 'market_price_eur must be a number'}), 400
        record = _shared.records_repo.update(record_id, {'market_price_eur': market_val})

    try:
        offer = _shared.service.post_offer(record, offer_type, data, current_user.id)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 409

    return jsonify({'success': True, 'offer': _shared._serialize(offer)}), 201


# ═══════════════════════════════════════════════
# RECORD DECISION
# ═══════════════════════════════════════════════

@buyback_bp.route('/records/<int:record_id>/offers/<int:offer_id>/decision', methods=['POST'])
@login_required
@v2_permission_required('buyback', 'record', 'edit')
def record_decision(record_id, offer_id):
    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return jsonify({'success': False, 'error': 'Record not found'}), 404

    err = _shared._guard_company(record)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    decision = data.get('decision')
    signature = data.get('signature')

    try:
        updated = _shared.service.record_decision(
            record, offer_id, decision, current_user.id, data.get('decline_reason'),
        )
    except ValueError as e:
        # Includes a consignment-accept dup/invalid VIN (the hand-off's VIN
        # guard, surfaced verbatim from VehicleService.create_vehicle) — the
        # offer stays pending + record in CONSIGNMENT_OFFER, retryable. Same
        # 409 contract as custody/finalize.
        return jsonify({'success': False, 'error': str(e)}), 409
    except Exception:
        # A non-ValueError fault mid consignment-accept hand-off (e.g. a DB
        # error, or ConsignmentRepository().create()'s INSERT) can leave an
        # orphan is_consignment CarPark vehicle with no linked buyback record.
        # Log it loudly and return a clean 500 rather than a raw traceback
        # (mirrors buyback.routes.custody.transfer_to_custody's handling).
        logger.exception(
            'record_decision failed for record %s offer %s (a consignment '
            'CarPark vehicle may be orphaned)', record_id, offer_id,
        )
        return jsonify({
            'success': False,
            'error': 'Înregistrarea deciziei a eșuat (eroare internă). A fost înregistrată.',
        }), 500

    # Best-effort: auto-generate + email the contract on a successful accept.
    # Runs after the committed transition and never raises — the accept stands
    # even if generation/email fails.
    contract = _maybe_generate_contract(record_id, updated, signature)
    return jsonify({'success': True, 'record': _shared._serialize(updated), 'contract': contract})
