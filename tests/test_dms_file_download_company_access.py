"""Regression cover for DMS file download/list company isolation.

Invoice annexes are filed under the *invoice's* company (e.g. a subsidiary such
as Autoworld PREMIUM, company 11) by the invoice->DMS pipeline, while the
back-office operators who upload and manage them live on the parent holding
company (AUTOWORLD S.R.L., company 16). The document *view* endpoint has no
company isolation, so those files are visible — but the download/list/delete
routes used to reject any user whose personal company_id != doc.company_id,
producing {"error":"File not found","success":false} on download.

Decision: remove company isolation from the DMS file routes so their behaviour
matches the (unisolated) document view endpoint. These tests lock that in.
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
        database_url=os.environ.get('DATABASE_URL', 'postgresql://localhost/defaultdb'),
    )
    application = create_app(cfg)
    application.config['TESTING'] = True
    application.config['LOGIN_DISABLED'] = True
    return application


class _User:
    def __init__(self, company_id):
        self.id = 3
        self.company_id = company_id
        self.email = 'operator@example.ro'


class _GateUser:
    """Authenticated admin, patched into the permission decorator's namespace so the
    @v2_permission_required gate passes. Kept separate from the route's current_user
    so the test exercises the company-isolation logic, not the auth gate."""
    is_authenticated = True
    is_admin = True
    can_access_settings = True


DRIVE_FILE = {
    'id': 148,
    'document_id': 274,
    'file_name': 'Anexa29_YTA.pdf',
    'storage_type': 'drive',
    'storage_uri': 'https://drive.google.com/file/d/1oh0abc/view?usp=drivesdk',
}
DOC_C11 = {'id': 274, 'company_id': 11}


def _call_download(app, *, file_row, doc, user_company):
    from dms.routes import files
    from core.roles import decorators
    file_repo = MagicMock(); file_repo.get_by_id.return_value = file_row
    doc_repo = MagicMock(); doc_repo.get_by_id.return_value = doc
    with app.test_request_context():
        with patch.object(files, '_file_repo', file_repo), \
             patch.object(files, '_doc_repo', doc_repo), \
             patch.object(files, 'current_user', _User(user_company)), \
             patch.object(decorators, 'current_user', _GateUser()):
            resp = files.api_download_file(148)
    status = resp[1] if isinstance(resp, tuple) else resp.status_code
    location = getattr(resp, 'headers', {}).get('Location') if not isinstance(resp, tuple) else None
    return status, location


def _call_list(app, *, doc, files_out, user_company):
    from dms.routes import files
    from core.roles import decorators
    file_repo = MagicMock(); file_repo.get_by_document.return_value = files_out
    doc_repo = MagicMock(); doc_repo.get_by_id.return_value = doc
    with app.test_request_context():
        with patch.object(files, '_file_repo', file_repo), \
             patch.object(files, '_doc_repo', doc_repo), \
             patch.object(files, 'current_user', _User(user_company)), \
             patch.object(decorators, 'current_user', _GateUser()):
            resp = files.api_list_files(274)
    status = resp[1] if isinstance(resp, tuple) else 200
    body = (resp[0] if isinstance(resp, tuple) else resp).get_json()
    return status, body


def test_parent_company_user_can_download_subsidiary_annex(app):
    """company 16 (holding) downloading a company 11 (subsidiary) annex -> 302 redirect to Drive."""
    status, location = _call_download(app, file_row=DRIVE_FILE, doc=DOC_C11, user_company=16)
    assert status == 302
    assert location == DRIVE_FILE['storage_uri']


def test_other_subsidiary_user_can_download(app):
    """Isolation removed entirely: any DMS-view user (e.g. company 10) redirects too."""
    status, location = _call_download(app, file_row=DRIVE_FILE, doc=DOC_C11, user_company=10)
    assert status == 302


def test_missing_file_row_returns_404(app):
    status, _ = _call_download(app, file_row=None, doc=DOC_C11, user_company=16)
    assert status == 404


def test_parent_company_user_can_list_subsidiary_files(app):
    status, body = _call_list(app, doc=DOC_C11, files_out=[DRIVE_FILE], user_company=16)
    assert status == 200
    assert body['success'] is True
    assert len(body['files']) == 1
