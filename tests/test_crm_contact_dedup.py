"""ContactRepository.create() must dedup on the driving-licence number.

Re-submitting the same person (same client_id + driver_license_number) — the
mobile "Adaugă persoană de contact" retry path — used to INSERT a fresh row
every time, piling up 3+ duplicate contacts for one driver. create() now
looks the person up by licence and, when found, UPDATEs in place filling only
still-empty fields (never clobbering existing data) instead of inserting.

psycopg2 is mocked by conftest; these tests patch the repo's own DB-touching
methods to drive the dedup branch deterministically.
"""
import sys, os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))


@pytest.fixture(scope='module')
def app():
    from core.config import AppConfig
    from app import create_app
    cfg = AppConfig(
        secret_key='test-secret-key-for-tests',
        database_url=os.environ.get('DATABASE_URL', 'postgresql://test:test@localhost/test'),
    )
    application = create_app(cfg)
    application.config['TESTING'] = True
    return application


def _repo():
    from crm.repositories.contact_repository import ContactRepository
    return ContactRepository()


EXISTING = {
    'id': 140, 'client_id': 30, 'full_name': 'Topan Alexandru',
    'email': None, 'phone': '+40722591124',
    'driver_license_serie': None, 'driver_license_number': 'C00776665J',
    'driver_license_photo': 'data:img', 'driver_license_expiry': None,
    'is_primary': True,
}


def test_existing_licence_updates_in_place_filling_only_empty(app):
    repo = _repo()
    repo.find_by_license = MagicMock(return_value=dict(EXISTING))
    repo.update = MagicMock(return_value=dict(EXISTING, email='alexandrutopan@yahoo.com'))
    repo.execute = MagicMock()  # INSERT must NOT happen
    # Re-add with the email now present, plus a phone that already exists.
    repo.create(30, {
        'full_name': 'Topan Alexandru', 'email': 'alexandrutopan@yahoo.com',
        'phone': '+40722591124', 'driver_license_number': 'C00776665J',
    })
    assert not repo.execute.called, 'should update, not insert a duplicate'
    repo.update.assert_called_once()
    contact_id, fill = repo.update.call_args.args[0], repo.update.call_args.args[1]
    assert contact_id == 140
    # Only the previously-empty field is filled; the already-set phone is left alone.
    assert fill == {'email': 'alexandrutopan@yahoo.com'}


def test_no_fill_needed_returns_existing_untouched(app):
    repo = _repo()
    complete = dict(EXISTING, email='a@b.ro')
    repo.find_by_license = MagicMock(return_value=complete)
    repo.update = MagicMock()
    repo.execute = MagicMock()
    out = repo.create(30, {'full_name': 'Topan Alexandru', 'driver_license_number': 'C00776665J'})
    assert out == complete
    assert not repo.update.called and not repo.execute.called


def test_new_licence_inserts(app):
    repo = _repo()
    repo.find_by_license = MagicMock(return_value=None)
    repo.query_one = MagicMock(return_value=None)   # first contact for client
    repo.execute = MagicMock(return_value={'id': 1})
    repo.create(30, {'full_name': 'Cineva Nou', 'driver_license_number': 'Z999'})
    assert repo.execute.called
    assert 'INSERT INTO crm_client_contacts' in repo.execute.call_args.args[0]


def test_no_licence_skips_dedup_and_inserts(app):
    repo = _repo()
    repo.find_by_license = MagicMock()
    repo.query_one = MagicMock(return_value=None)
    repo.execute = MagicMock(return_value={'id': 2})
    repo.create(30, {'full_name': 'Fara Permis'})
    assert not repo.find_by_license.called, 'no licence → no dedup lookup'
    assert repo.execute.called
