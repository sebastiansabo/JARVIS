"""P3c Task 1 — the editable per-record contract columns + RecordRepository.
update_contract. DB-backed against localhost/defaultdb (require_real_db skip
guard, same as the rest of the buyback suite)."""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from buyback.repositories.record_repository import RecordRepository  # noqa: E402


def _code():
    return f'BB-CF-{os.urandom(4).hex()}'


def _vin():
    return ('WBA' + os.urandom(7).hex().upper())[:17]


def _record(**overrides):
    data = {
        'record_code': _code(), 'company_id': 1, 'vin': _vin(),
        'brand': 'BMW', 'model': '320d', 'created_by': 1,
    }
    data.update(overrides)
    return RecordRepository().create(data)


def test_fresh_record_has_null_contract_fields(require_real_db):
    rec = _record()
    for col in ('contract_title', 'contract_body', 'contract_general_conditions', 'contract_generated_at'):
        assert col in rec, f'{col} missing from record row'
        assert rec[col] is None


def test_update_contract_roundtrips_and_stamps(require_real_db):
    rec = _record()
    assert rec['contract_generated_at'] is None
    out = RecordRepository().update_contract(
        rec['id'], title='Contract achiziție', body='Linia 1\nLinia 2 cu ăâîșț',
        general_conditions='Condiții GDPR',
    )
    assert out['contract_title'] == 'Contract achiziție'
    assert out['contract_body'] == 'Linia 1\nLinia 2 cu ăâîșț'
    assert out['contract_general_conditions'] == 'Condiții GDPR'
    assert out['contract_generated_at'] is not None
