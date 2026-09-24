"""Route tests for the buyback offer HTTP endpoints (Task 10): posting an
offer and recording the seller's decision under
/api/buyback/records/<id>/offers[...], gated by
@v2_permission_required('buyback', 'offer'|'record', 'manage'|'edit') plus
the same cross-company IDOR guard as records.py.

Uses the real app (`client` fixture) + the `as_role(role_name, company_id)`
login helper from tests/buyback/conftest.py — NOT a `client_as` helper (see
test_routes_records.py's module docstring for why).

Per migrations/domains/schema_roles.py::_seed_buyback_permissions_v2:
  - Admin/Manager: 'all' scope + (for Admin, in this shared DB) the legacy
    can_access_settings bypass, so _guard_company always passes for Admin —
    used for happy-path record/offer creation per Ruling R4.
  - Sales: 'own' scope on record.view/create/edit, but NO offer.manage — the
    "sales-style" persona that records the seller's decision.
  - Acquisition: 'all' scope on record.view/offer.manage/record.finalize,
    but NO record.create and NO record.edit. NOTE: Acquisition is NOT used
    to exercise _guard_company's company-match branch in these tests —
    unlike Admin, it doesn't carry the can_access_settings bypass, so its
    'all'-scope boundary falls through to
    core.organization.manager_utils.get_actable_company_ids(), a live query
    against the real `users`/sincron tables. The as_role() harness's fake
    uids have no corresponding `users` row, so that lookup always returns
    empty for these test users regardless of company match — testing
    cross-company denial through Acquisition would conflate "cross-company"
    with "no org mapping for this fake user" and pass for the wrong reason.
    Acquisition is only used here to exercise its PERMISSION shape (holds
    offer.manage, lacks record.create/record.edit).

The cross-company IDOR boundary on the offers POST route (which requires
offer.manage — a permission only Admin/Manager/Acquisition hold) is instead
exercised the same way test_routes_records.py's
test_out_of_scope_company_mutation_forbidden does: authenticate as Admin (to
clear the permission decorator) and monkeypatch
_shared._permitted_company_ids to a fixed set, isolating the assertion to
_guard_company's boundary logic itself.
"""
import pytest

pytestmark = pytest.mark.usefixtures('require_real_db')


def _vin():
    import secrets
    alphabet = 'ABCDEFGHJKLMNPRSTUVWXYZ0123456789'
    return 'WBA' + ''.join(secrets.choice(alphabet) for _ in range(14))


def _payload(**overrides):
    data = {
        'vin': _vin(),
        'brand': 'BMW',
        'model': '320d',
        'acquisition_type': 'buyback',
        'client_asking_price_eur': 1000,
        'seller_email': 's@e.z',
    }
    data.update(overrides)
    return data


def _offer_payload(**overrides):
    data = {'offer_type': 'initial', 'amount_eur': 9000, 'vat_status': 'no_vat'}
    data.update(overrides)
    return data


def _make_record(client, as_role, company_id=1):
    """Create a buyback record as Admin (Admin holds record.create at 'all'
    scope + the can_access_settings bypass in this shared DB), so callers
    can then switch to whichever role/company they actually want to test
    against the freshly-created record."""
    as_role('Admin', company_id)
    r = client.post('/api/buyback/records', json=_payload())
    assert r.status_code == 201, r.get_json()
    return r.get_json()['record']['id']


# ── POST OFFER ───────────────────────────────────────────────────────────

def test_post_initial_offer_moves_record_to_initial_offer(client, as_role):
    rid = _make_record(client, as_role)
    as_role('Admin', 1)

    r = client.post(f'/api/buyback/records/{rid}/offers', json=_offer_payload())
    assert r.status_code == 201, r.get_json()
    body = r.get_json()
    assert body['success'] is True
    offer = body['offer']
    assert offer['record_id'] == rid
    assert offer['offer_type'] == 'initial'
    assert offer['client_decision'] == 'pending'
    assert float(offer['amount_eur']) == 9000

    detail = client.get(f'/api/buyback/records/{rid}').get_json()
    assert detail['record']['status'] == 'INITIAL_OFFER'


def test_post_offer_missing_offer_type_is_400(client, as_role):
    rid = _make_record(client, as_role)
    as_role('Admin', 1)
    r = client.post(f'/api/buyback/records/{rid}/offers', json={'amount_eur': 1})
    assert r.status_code == 400


def test_post_offer_invalid_offer_type_is_400(client, as_role):
    rid = _make_record(client, as_role)
    as_role('Admin', 1)
    r = client.post(f'/api/buyback/records/{rid}/offers', json=_offer_payload(offer_type='nonsense'))
    assert r.status_code == 400


def test_post_offer_missing_record_404(client, as_role):
    as_role('Admin', 1)
    r = client.post('/api/buyback/records/999999999/offers', json=_offer_payload())
    assert r.status_code == 404


def test_post_offer_missing_amount_eur_is_400_not_500(client, as_role):
    """amount_eur is a NOT NULL NUMERIC column — a missing value flowing into
    OfferRepository.create's INSERT raises psycopg2.NotNullViolation (NOT a
    ValueError), which the route's `except ValueError` would NOT catch, giving
    a 500. The route must validate amount_eur up front and 400 instead.
    Asserts NOT 500 explicitly."""
    rid = _make_record(client, as_role)
    as_role('Admin', 1)
    r = client.post(f'/api/buyback/records/{rid}/offers',
                     json={'offer_type': 'initial', 'vat_status': 'no_vat'})
    assert r.status_code == 400, r.get_json()
    assert r.status_code != 500


def test_post_offer_non_numeric_amount_eur_is_400(client, as_role):
    rid = _make_record(client, as_role)
    as_role('Admin', 1)
    r = client.post(f'/api/buyback/records/{rid}/offers',
                     json=_offer_payload(amount_eur='not-a-number'))
    assert r.status_code == 400, r.get_json()


def test_post_offer_malformed_valid_until_is_400(client, as_role):
    """A malformed valid_until would 500 the same way (bad literal reaching
    the DATE column / COALESCE) — validate it as an ISO date up front."""
    rid = _make_record(client, as_role)
    as_role('Admin', 1)
    r = client.post(f'/api/buyback/records/{rid}/offers',
                     json=_offer_payload(valid_until='31-13-2020'))
    assert r.status_code == 400, r.get_json()


def test_post_offer_valid_until_iso_accepted(client, as_role):
    """Counterpart: a well-formed ISO valid_until still posts (proves the 400
    above is the malformed-date guard, not a blanket rejection of the field)."""
    rid = _make_record(client, as_role)
    as_role('Admin', 1)
    r = client.post(f'/api/buyback/records/{rid}/offers',
                     json=_offer_payload(valid_until='2030-01-31'))
    assert r.status_code == 201, r.get_json()


def test_post_second_pending_offer_is_409(client, as_role):
    """One-pending-offer-per-record invariant (BuyBackService.post_offer),
    surfaced as a route-level 409: posting a second offer round while the
    first is still undecided (record already moved to INITIAL_OFFER, not
    PENDING_EVALUATION) fails the round/status match too — either way it's
    the service's ValueError translated to 409."""
    rid = _make_record(client, as_role)
    as_role('Admin', 1)
    first = client.post(f'/api/buyback/records/{rid}/offers', json=_offer_payload())
    assert first.status_code == 201, first.get_json()

    second = client.post(f'/api/buyback/records/{rid}/offers', json=_offer_payload())
    assert second.status_code == 409
    assert 'error' in second.get_json()


def test_post_offer_requires_offer_manage_permission(client, as_role):
    """Sales has record.view/create/edit but NOT offer.manage — module-level
    403 from the decorator, before the route body even runs."""
    rid = _make_record(client, as_role)
    as_role('Sales', 1)
    r = client.post(f'/api/buyback/records/{rid}/offers', json=_offer_payload())
    assert r.status_code == 403


def test_post_offer_cross_company_forbidden(client, as_role, monkeypatch):
    """Mirrors test_routes_records.py's test_out_of_scope_company_mutation_forbidden:
    isolates the _guard_company boundary itself (rather than depending on a
    real org/sincron mapping for a fake harness user — see module docstring)
    by authenticating as Admin (clears the offer.manage decorator) and
    monkeypatching the permitted-company set to exclude the record's
    company."""
    import buyback.routes._shared as shared
    rid = _make_record(client, as_role, company_id=1)

    as_role('Admin', 1)
    monkeypatch.setattr(shared, '_permitted_company_ids', lambda: {2})
    r = client.post(f'/api/buyback/records/{rid}/offers', json=_offer_payload())
    assert r.status_code == 403


# ── RECORD DECISION ──────────────────────────────────────────────────────

def test_post_offer_then_decision_flow(client, as_role):
    rid = _make_record(client, as_role)
    as_role('Admin', 1)
    o = client.post(f'/api/buyback/records/{rid}/offers', json=_offer_payload())
    assert o.status_code == 201, o.get_json()
    oid = o.get_json()['offer']['id']

    as_role('Sales', 1)
    d = client.post(f'/api/buyback/records/{rid}/offers/{oid}/decision', json={'decision': 'accepted'})
    assert d.status_code == 200, d.get_json()
    assert d.get_json()['record']['status'] == 'INSPECTION'

    det = client.get(f'/api/buyback/records/{rid}').get_json()
    assert det['record']['status'] == 'INSPECTION'


def test_decision_decline_moves_record_to_lost(client, as_role):
    rid = _make_record(client, as_role)
    as_role('Admin', 1)
    oid = client.post(f'/api/buyback/records/{rid}/offers', json=_offer_payload()).get_json()['offer']['id']

    as_role('Sales', 1)
    d = client.post(f'/api/buyback/records/{rid}/offers/{oid}/decision',
                     json={'decision': 'declined', 'decline_reason': 'too low'})
    assert d.status_code == 200, d.get_json()
    rec = d.get_json()['record']
    assert rec['status'] == 'LOST'
    assert rec['lost_reason'] == 'too low'


def test_stale_offer_decision_409(client, as_role):
    """The offer's decision can only be recorded once — a replay against the
    same (now-decided) offer id must 409, not silently re-apply."""
    rid = _make_record(client, as_role)
    as_role('Admin', 1)
    oid = client.post(f'/api/buyback/records/{rid}/offers', json=_offer_payload()).get_json()['offer']['id']

    as_role('Sales', 1)
    first = client.post(f'/api/buyback/records/{rid}/offers/{oid}/decision', json={'decision': 'accepted'})
    assert first.status_code == 200, first.get_json()

    replay = client.post(f'/api/buyback/records/{rid}/offers/{oid}/decision', json={'decision': 'declined'})
    assert replay.status_code == 409
    assert 'error' in replay.get_json()


def test_decision_bogus_offer_id_on_valid_record_is_409(client, as_role):
    """RULING (fix round 1): a valid record + a nonexistent/non-latest
    offer_id folds into the "not the current decidable offer" / stale bucket —
    we deliberately do NOT distinguish "wrong id" from "stale id" for a client
    recording a decision. record_decision's `latest['id'] != offer_id` guard
    raises ValueError → the route returns 409 (not 404). Pinned here."""
    rid = _make_record(client, as_role)
    as_role('Admin', 1)
    # A real pending offer exists (so the record is in INITIAL_OFFER), but the
    # decision targets a different, nonexistent offer_id.
    real_oid = client.post(f'/api/buyback/records/{rid}/offers', json=_offer_payload()).get_json()['offer']['id']

    as_role('Sales', 1)
    r = client.post(f'/api/buyback/records/{rid}/offers/{real_oid + 999999}/decision',
                     json={'decision': 'accepted'})
    assert r.status_code == 409, r.get_json()
    assert 'error' in r.get_json()


def test_decision_missing_record_404(client, as_role):
    as_role('Sales', 1)
    r = client.post('/api/buyback/records/999999999/offers/1/decision', json={'decision': 'accepted'})
    assert r.status_code == 404


def test_decision_requires_record_edit_permission(client, as_role):
    """Acquisition holds offer.manage but NOT record.edit — module-level 403
    from the decorator on the decision route (before _guard_company/any
    org lookup even runs). The offer itself is posted as Admin (Acquisition
    posting it would additionally trip its own _guard_company org-lookup gap
    — see module docstring — which is not what this test is about)."""
    rid = _make_record(client, as_role)
    as_role('Admin', 1)
    posted = client.post(f'/api/buyback/records/{rid}/offers', json=_offer_payload())
    assert posted.status_code == 201, posted.get_json()
    oid = posted.get_json()['offer']['id']

    as_role('Acquisition', 1)
    r = client.post(f'/api/buyback/records/{rid}/offers/{oid}/decision', json={'decision': 'accepted'})
    assert r.status_code == 403


def test_decision_cross_company_forbidden(client, as_role):
    """Sales holds record.edit at 'own' scope — its permitted-company set is
    the concrete {current_user.company_id}, no org/sincron lookup needed, so
    this exercises the real cross-company boundary end-to-end."""
    rid = _make_record(client, as_role)
    as_role('Admin', 1)
    oid = client.post(f'/api/buyback/records/{rid}/offers', json=_offer_payload()).get_json()['offer']['id']

    as_role('Sales', 2)
    r = client.post(f'/api/buyback/records/{rid}/offers/{oid}/decision', json={'decision': 'accepted'})
    assert r.status_code == 403
