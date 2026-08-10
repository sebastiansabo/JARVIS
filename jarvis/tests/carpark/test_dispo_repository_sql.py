"""Real-DB integration tests for the CarPark Dispo repositories.

Runs against localhost/defaultdb via the probe in conftest.py (which drops
jarvis/conftest.py's psycopg2 mock and rebinds the real driver). All tests
depend on the `dispo_seed` fixture (also in conftest.py), which seeds two
vehicles under the sentinel `company_id=990001` and tears them down
(cascade-deleting all child cost/revenue/reservation/document rows) in a
`finally` block, asserting zero rows remain afterwards.

Invocation:
    DATABASE_URL=postgresql://localhost/defaultdb \
        venv/bin/python -m pytest jarvis/tests/carpark/test_dispo_repository_sql.py -v
"""
from datetime import datetime, timedelta

from carpark.repositories.dispo_repository import DispoRepository, STAGE_STATUS_MAP
from carpark.repositories.document_repository import DocumentRepository
from carpark.repositories.reservation_repository import ReservationRepository

from .conftest import TEST_COMPANY_ID


# ─────────────────────────────────────────────────────────────────────────
# DispoRepository.summary — the centerpiece query. Highest risk, tested first.
# ─────────────────────────────────────────────────────────────────────────

def test_summary_days_in_stock_unsold_vs_sold(dispo_seed):
    """days_in_stock: unsold uses (today - acquisition_date), sold uses
    (sale_date - acquisition_date)."""
    result = DispoRepository().summary(TEST_COMPANY_ID, {})
    by_vin = {row['vin']: row for row in result['rows']}

    unsold = by_vin['TESTDISPO00000001']
    sold = by_vin['TESTDISPO00000002']

    # Seeded as "today - 100 days"; recompute against *now* in case the
    # test happens to straddle a midnight rollover between seed and assert.
    expected_unsold_days = (datetime.now().date() - (dispo_seed['today'] - timedelta(days=100))).days
    assert unsold['days_in_stock'] == expected_unsold_days

    # Fully deterministic — both dates are fixed offsets from the same seed
    # anchor, independent of when the assertion runs: 150 - 10 = 140.
    assert sold['days_in_stock'] == 140


def test_summary_gross_margin(dispo_seed):
    """gross_margin = sale_price - acquisition_price - total_costs; NULL
    (not zero) for unsold vehicles, since sale_price is NULL."""
    result = DispoRepository().summary(TEST_COMPANY_ID, {})
    by_vin = {row['vin']: row for row in result['rows']}

    sold = by_vin['TESTDISPO00000002']
    assert sold['total_costs'] == 1000
    assert sold['gross_margin'] == 15000 - 12000 - 1000  # 2000
    assert sold['margin_pct'] is not None
    assert round(sold['margin_pct'], 2) == round(2000 / 15000 * 100, 2)

    unsold = by_vin['TESTDISPO00000001']
    assert unsold['total_costs'] == 2000
    assert unsold['gross_margin'] is None
    assert unsold['margin_pct'] is None


def test_summary_stage_counts_sum_correctly(dispo_seed):
    result = DispoRepository().summary(TEST_COMPANY_ID, {})
    stage_counts = result['stage_counts']

    assert stage_counts['in_stoc'] == 1   # READY_FOR_SALE
    assert stage_counts['vandut'] == 1    # SOLD
    assert stage_counts['all'] == 2
    for stage in STAGE_STATUS_MAP:
        if stage not in ('in_stoc', 'vandut'):
            assert stage_counts[stage] == 0, f'unexpected count in stage {stage!r}'
    # every bucket + 'all' accounts for every row, no double counting
    assert sum(v for k, v in stage_counts.items() if k != 'all') == stage_counts['all']


def test_summary_totals_reflect_seeded_money(dispo_seed):
    result = DispoRepository().summary(TEST_COMPANY_ID, {})
    totals = result['totals']

    assert totals['acquisition_price'] == 10000 + 12000
    assert totals['total_costs'] == 2000 + 1000
    assert totals['sale_price'] == 15000          # unsold contributes NULL, ignored by SUM
    assert totals['gross_margin'] == 2000          # only the sold row has a non-NULL margin
    assert result['total'] == 2
    assert result['page'] == 1
    assert result['per_page'] == 25


def test_summary_stage_filter_narrows_rows_but_not_stage_counts(dispo_seed):
    """Selecting a stage tab filters `rows`/`total`, but `stage_counts` must
    stay computed against every OTHER filter (not the stage itself), so tab
    counts don't collapse to zero when a tab is selected."""
    result = DispoRepository().summary(TEST_COMPANY_ID, {'stage': 'in_stoc'})

    assert result['total'] == 1
    assert [row['vin'] for row in result['rows']] == ['TESTDISPO00000001']

    assert result['stage_counts']['in_stoc'] == 1
    assert result['stage_counts']['vandut'] == 1
    assert result['stage_counts']['all'] == 2


def test_summary_search_filter(dispo_seed):
    result = DispoRepository().summary(TEST_COMPANY_ID, {'search': 'TestModelB'})
    assert result['total'] == 1
    assert result['rows'][0]['vin'] == 'TESTDISPO00000002'


def test_summary_brand_and_date_range_filters(dispo_seed):
    result = DispoRepository().summary(TEST_COMPANY_ID, {'brand': 'TestBrand'})
    assert result['total'] == 2

    result = DispoRepository().summary(TEST_COMPANY_ID, {'brand': 'NoSuchBrand'})
    assert result['total'] == 0
    assert result['rows'] == []

    today = dispo_seed['today']
    result = DispoRepository().summary(TEST_COMPANY_ID, {
        'date_from': today - timedelta(days=120),
        'date_to': today - timedelta(days=80),
    })
    assert result['total'] == 1
    assert result['rows'][0]['vin'] == 'TESTDISPO00000001'


def test_summary_doc_types_array_reflects_uploaded_documents(dispo_seed):
    doc_repo = DocumentRepository()
    doc_repo.create(dispo_seed['vehicle_unsold'], {'document_type': 'CIV'})
    doc_repo.create(dispo_seed['vehicle_unsold'], {'document_type': 'CONTRACT'})

    result = DispoRepository().summary(TEST_COMPANY_ID, {})
    by_vin = {row['vin']: row for row in result['rows']}

    assert set(by_vin['TESTDISPO00000001']['doc_types']) == {'CIV', 'CONTRACT'}
    assert by_vin['TESTDISPO00000002']['doc_types'] == []


def test_summary_active_reservation_join_picks_most_recent(dispo_seed):
    res_repo = ReservationRepository()
    vehicle_id = dispo_seed['vehicle_unsold']
    now = datetime.utcnow()

    older = res_repo.create(vehicle_id, {
        'client_name': 'Older Client', 'status': 'active',
        'reservation_start': now - timedelta(days=5),
        'reservation_end': now + timedelta(days=1),
    })
    newer = res_repo.create(vehicle_id, {
        'client_name': 'Newer Client', 'status': 'active',
        'reservation_start': now,
        'reservation_end': now + timedelta(days=7),
    })

    result = DispoRepository().summary(TEST_COMPANY_ID, {})
    row = next(r for r in result['rows'] if r['vin'] == 'TESTDISPO00000001')

    assert row['reservation_id'] == newer['id']
    assert row['reservation_id'] != older['id']
    assert row['reservation_client_name'] == 'Newer Client'


def test_kpis_smoke(dispo_seed):
    kpis = DispoRepository().kpis(TEST_COMPANY_ID)
    expected_keys = {
        'cars_in_stock', 'reserved', 'sold_this_month', 'delivered_this_month',
        'avg_days_in_stock', 'aged_over_60', 'gross_margin_mtd',
    }
    assert expected_keys.issubset(kpis.keys())
    assert kpis['cars_in_stock'] >= 1   # the seeded READY_FOR_SALE vehicle
    assert kpis['reserved'] == 0        # neither seeded vehicle is status=RESERVED


# ─────────────────────────────────────────────────────────────────────────
# DocumentRepository
# ─────────────────────────────────────────────────────────────────────────

def test_document_has_type_and_distinct_types(dispo_seed):
    doc_repo = DocumentRepository()
    vehicle_id = dispo_seed['vehicle_sold']

    assert doc_repo.has_type(vehicle_id, 'CIV') is False
    assert doc_repo.distinct_types(vehicle_id) == []

    doc_repo.create(vehicle_id, {'document_type': 'CIV', 'file_url': 'https://example.invalid/civ.pdf'})
    doc_repo.create(vehicle_id, {'document_type': 'RCA'})

    assert doc_repo.has_type(vehicle_id, 'CIV') is True
    assert doc_repo.has_type(vehicle_id, 'NONEXISTENT') is False
    assert set(doc_repo.distinct_types(vehicle_id)) == {'CIV', 'RCA'}

    docs = doc_repo.list_for_vehicle(vehicle_id)
    assert len(docs) == 2

    fetched = doc_repo.get(docs[0]['id'])
    assert fetched is not None
    assert fetched['id'] == docs[0]['id']

    assert doc_repo.delete(docs[0]['id']) is True
    assert len(doc_repo.list_for_vehicle(vehicle_id)) == 1
    assert doc_repo.delete(docs[0]['id']) is False  # already gone


def test_document_create_requires_document_type(dispo_seed):
    doc_repo = DocumentRepository()
    try:
        doc_repo.create(dispo_seed['vehicle_sold'], {'file_url': 'https://example.invalid/x.pdf'})
        assert False, 'expected ValueError for missing document_type'
    except ValueError:
        pass


# ─────────────────────────────────────────────────────────────────────────
# ReservationRepository
# ─────────────────────────────────────────────────────────────────────────

def test_reservation_active_for_vehicle_and_expired(dispo_seed):
    res_repo = ReservationRepository()
    vehicle_id = dispo_seed['vehicle_unsold']
    now = datetime.utcnow()

    expired_res = res_repo.create(vehicle_id, {
        'client_name': 'Expired Client', 'status': 'active',
        'reservation_start': now - timedelta(days=5),
        'reservation_end': now - timedelta(days=2),
    })
    future_res = res_repo.create(vehicle_id, {
        'client_name': 'Future Client', 'status': 'active',
        'reservation_start': now,
        'reservation_end': now + timedelta(days=7),
    })

    active = res_repo.active_for_vehicle(vehicle_id)
    assert active is not None
    assert active['id'] == future_res['id']

    expired_list = res_repo.expired(now)
    expired_ids = {r['id'] for r in expired_list}
    assert expired_res['id'] in expired_ids
    assert future_res['id'] not in expired_ids

    updated = res_repo.set_status(expired_res['id'], 'cancelled')
    assert updated['status'] == 'cancelled'

    expired_list_after = res_repo.expired(now)
    assert expired_res['id'] not in {r['id'] for r in expired_list_after}


def test_reservation_create_defaults_reservation_start(dispo_seed):
    res_repo = ReservationRepository()
    created = res_repo.create(dispo_seed['vehicle_sold'], {
        'client_name': 'No Start Given', 'status': 'active',
        'reservation_end': datetime.utcnow() + timedelta(days=3),
    })
    assert created['reservation_start'] is not None
