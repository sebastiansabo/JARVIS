"""Intake API routes — the HTTP surface jarvis-alpha calls to feed its
"Transport in derulare" / "ETA actualizat" / ... events into the pipeline
(`logistics.services.intake.apply_event`), plus a read-only endpoint for the
active mapping rules it's dispatched against.

Server-to-server surface — jarvis-alpha is not a logged-in JARVIS user, so
these routes are NOT behind @login_required. Auth is an optional shared
secret (see `_check_intake_auth`) instead.

No SQL here (per repo convention) — every route delegates to `apply_event`
or a Task-1 repository. Exception mapping:
  ValueError      -> 400
  PermissionError -> 403
  anything else   -> 500 (logged)
"""
import logging
import os

from flask import request, jsonify

from logistics import logistics_bp
from logistics.repositories.intake_event_repository import IntakeEventRepository
from logistics.repositories.mapping_rule_repository import MappingRuleRepository
from logistics.services.intake import apply_event

logger = logging.getLogger('jarvis.logistics')

_INTAKE_SECRET_ENV = 'LOGISTICS_INTAKE_SECRET'
_INTAKE_SECRET_HEADER = 'X-Intake-Secret'

# Set True the first time we let a request through with no shared-secret
# configured, so the "auth is unconfigured" warning only fires once per
# process instead of once per request.
_unconfigured_auth_warned = False


def _check_intake_auth():
    """Shared-secret gate for the jarvis-alpha feed.

    LOGISTICS_INTAKE_SECRET set -> the request's X-Intake-Secret header must
    match it exactly, else 401. LOGISTICS_INTAKE_SECRET unset -> every
    request is allowed through (dev mode), but we log a warning once per
    process so an unconfigured-auth deployment doesn't go unnoticed.

    Returns None when the request may proceed, or a (response, status)
    tuple to return immediately otherwise.
    """
    global _unconfigured_auth_warned
    secret = os.environ.get(_INTAKE_SECRET_ENV)
    if not secret:
        if not _unconfigured_auth_warned:
            logger.warning(
                '%s is not set — /api/logistics/intake/events is accepting '
                'requests with NO shared-secret auth (dev mode only; set '
                '%s before exposing this endpoint in any shared/prod env)',
                _INTAKE_SECRET_ENV, _INTAKE_SECRET_ENV,
            )
            _unconfigured_auth_warned = True
        return None
    if request.headers.get(_INTAKE_SECRET_HEADER) != secret:
        return jsonify({'error': 'Unauthorized'}), 401
    return None


def _is_valid_event_body(body) -> bool:
    """True when `body` has exactly the shape apply_event() needs:
    order_ref (non-empty str), code (non-empty str), event_ts (int),
    payload (dict)."""
    if not isinstance(body, dict):
        return False
    if not isinstance(body.get('order_ref'), str) or not body['order_ref']:
        return False
    if not isinstance(body.get('code'), str) or not body['code']:
        return False
    # bool is an int subclass in Python — exclude it, event_ts is a Unix ts.
    if not isinstance(body.get('event_ts'), int) or isinstance(body.get('event_ts'), bool):
        return False
    if not isinstance(body.get('payload'), dict):
        return False
    return True


def _log_ignored_attempt(body) -> None:
    """Best-effort audit row for a malformed/invalid intake POST.

    logistics_intake_events.order_ref/code/event_ts are NOT NULL columns,
    so a body that's missing one of those fields can't be logged with a
    literal None in that slot — we fall back to an empty-string/0 sentinel
    instead so the row (and the raw body, in `payload`) is always captured
    for debugging, and this never raises past "the body was bad" into "the
    DB insert blew up too".
    """
    order_ref = body.get('order_ref') if isinstance(body, dict) else None
    code = body.get('code') if isinstance(body, dict) else None
    event_ts = body.get('event_ts') if isinstance(body, dict) else None

    safe_order_ref = order_ref if isinstance(order_ref, str) else ''
    safe_code = code if isinstance(code, str) else ''
    safe_event_ts = event_ts if isinstance(event_ts, int) and not isinstance(event_ts, bool) else 0

    IntakeEventRepository().log(safe_order_ref, safe_code, body, safe_event_ts, 'ignored')


@logistics_bp.route('/api/logistics/intake/events', methods=['POST'])
def intake_events():
    """Ingest one jarvis-alpha event: {order_ref, code, event_ts, payload}.

    A malformed/incomplete/non-JSON body is never a 500 — jarvis-alpha
    retries any non-2xx response, and a permanently malformed payload would
    then retry forever. Instead it's logged to logistics_intake_events
    (result='ignored') and the response is still 200 {"result": "ignored"}.
    """
    auth_err = _check_intake_auth()
    if auth_err is not None:
        return auth_err

    body = request.get_json(silent=True)

    if not _is_valid_event_body(body):
        _log_ignored_attempt(body)
        return jsonify({'result': 'ignored'}), 200

    try:
        outcome = apply_event(body)
        return jsonify(outcome), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        logger.error(f'Intake event processing failed (order_ref={body.get("order_ref")!r}): {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500


@logistics_bp.route('/api/logistics/intake/mapping', methods=['GET'])
def intake_mapping():
    """Active mapping rules (trigger_code -> action) — the published rule
    map the intake pipeline dispatches against (Setări → Reguli Dispo)."""
    try:
        rules = MappingRuleRepository().get_active_rules()
        return jsonify({'rules': rules}), 200
    except Exception as e:
        logger.error(f'Fetching active mapping rules failed: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500
