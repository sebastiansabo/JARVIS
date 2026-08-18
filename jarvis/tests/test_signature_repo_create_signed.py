from core.signatures.repositories.signature_repo import SignatureRepository


def test_create_signed_inserts_signed_row(monkeypatch):
    captured = {}
    repo = SignatureRepository()
    monkeypatch.setattr(repo, 'execute',
        lambda sql, params=None, returning=False: captured.update(sql=sql, params=params, returning=returning) or {'id': 1})
    out = repo.create_signed('leave_permit', 55, 42, 'data:image/png;base64,AAAA', ip_address='1.2.3.4')
    assert out == {'id': 1}
    assert "status" in captured['sql'] and "'signed'" in captured['sql']
    assert captured['returning'] is True
    assert captured['params'] == ('leave_permit', 55, 42, 'data:image/png;base64,AAAA', '1.2.3.4')
