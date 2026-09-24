"""Tests for the buyback OfferRepository (Task 5): create/get/latest/pending/
record_decision against buyback_offers.

DB-backed (uses `require_real_db` from tests/buyback/conftest.py) — obtains
its connection via the repository's own `database` layer, NOT raw
psycopg2.connect, since jarvis/conftest.py mocks psycopg2 at collection time
for the rest of the suite (see tests/buyback/test_record_repository.py for
the same pattern). Each test creates its own parent buyback_records row via
RecordRepository().create() with a unique record_code + VIN, then exercises
the offer repo against it, so reruns against the shared localhost/defaultdb
never collide with leftover rows from a previous run.

Per the Task 5 brief: the one-pending-per-record and latest-offer/status
invariants are NOT asserted here — those belong to the service (Task 8).
This file only exercises the repo's raw queries.
"""
import os

from buyback.repositories.record_repository import RecordRepository
from buyback.repositories.offer_repository import OfferRepository


def _code(prefix='BB-OFFER'):
    return f'{prefix}-{os.urandom(4).hex()}'


def _vin():
    # Not checksum-valid (the schema doesn't enforce VIN format), just a
    # unique 17-char alnum string so concurrent/rerun tests never collide.
    return ('WBA' + os.urandom(7).hex().upper())[:17]


def _record(**overrides):
    data = {
        'record_code': _code(),
        'company_id': 1,
        'vin': _vin(),
        'brand': 'BMW',
        'model': '320d',
        'created_by': 1,
    }
    data.update(overrides)
    return RecordRepository().create(data)


def test_create_and_latest_and_pending(require_real_db):
    rid = _record()['id']
    repo = OfferRepository()

    offer = repo.create(rid, 'initial', 1000, 'no_vat', None, 'first offer', 1)

    assert offer['id']
    assert offer['record_id'] == rid
    assert offer['offer_type'] == 'initial'
    assert float(offer['amount_eur']) == 1000
    assert offer['client_decision'] == 'pending'
    assert offer['valid_until'] is not None  # defaulted in SQL to CURRENT_DATE + 7 days
    assert offer['decided_by'] is None
    assert offer['decided_at'] is None

    fetched = repo.get(offer['id'])
    assert fetched['id'] == offer['id']

    latest = repo.latest_for_record(rid)
    assert latest['id'] == offer['id']

    pending = repo.pending_for_record(rid)
    assert pending['id'] == offer['id']


def test_get_missing_returns_none(require_real_db):
    repo = OfferRepository()
    assert repo.get(999999999) is None


def test_create_explicit_valid_until_is_preserved(require_real_db):
    rid = _record()['id']
    repo = OfferRepository()
    offer = repo.create(rid, 'initial', 500, 'vat', '2099-01-01', None, 1)
    assert str(offer['valid_until']) == '2099-01-01'


def test_latest_for_record_picks_most_recent(require_real_db):
    rid = _record()['id']
    repo = OfferRepository()
    first = repo.create(rid, 'initial', 1000, 'no_vat', None, None, 1)
    second = repo.create(rid, 'revised', 1200, 'no_vat', None, None, 1)
    latest = repo.latest_for_record(rid)
    assert latest['id'] == second['id']
    assert latest['id'] != first['id']


def test_latest_for_record_none_when_no_offers(require_real_db):
    rid = _record()['id']
    repo = OfferRepository()
    assert repo.latest_for_record(rid) is None
    assert repo.pending_for_record(rid) is None


def test_record_decision_accepted(require_real_db):
    rid = _record()['id']
    repo = OfferRepository()
    offer = repo.create(rid, 'initial', 1000, 'no_vat', None, None, 1)

    decided = repo.record_decision(offer['id'], 'accepted', 2)

    assert decided['client_decision'] == 'accepted'
    assert decided['decided_by'] == 2
    assert decided['decided_at'] is not None
    assert decided['decline_reason'] is None
    assert repo.pending_for_record(rid) is None


def test_record_decision_declined_with_reason(require_real_db):
    rid = _record()['id']
    repo = OfferRepository()
    offer = repo.create(rid, 'initial', 1000, 'no_vat', None, None, 1)

    decided = repo.record_decision(offer['id'], 'declined', 3, decline_reason='price too low')

    assert decided['client_decision'] == 'declined'
    assert decided['decided_by'] == 3
    assert decided['decline_reason'] == 'price too low'
    assert repo.pending_for_record(rid) is None
