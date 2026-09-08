"""Foaie de Parcurs attachments: per-Alimentare receipts + foaie-level files
stored in DO Spaces, and a bundle ZIP (foaie PDF + all files) for download.
Spaces + the stored-sheet row are faked so no network/DB is touched.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import foi_parcurs.services.route_sheet_service as rss


class FakeSpaces:
    def __init__(self):
        self.store = {}

    def upload(self, data, key, content_type):
        self.store[key] = (data, content_type)
        return key

    def fetch(self, key):
        return self.store[key]

    def delete(self, key):
        self.store.pop(key, None)


def test_add_attachment_uploads_to_spaces_and_records(monkeypatch):
    spaces = FakeSpaces()
    monkeypatch.setattr(rss, 'spaces_service', spaces)
    monkeypatch.setattr(rss, 'list_attachments', lambda *a, **k: [])
    saved = {}
    monkeypatch.setattr(rss, '_upsert_sheet_json', lambda vin, y, m, col, val: saved.update(col=col, val=val))

    rec = rss.add_attachment('VIN1', 2026, 8, b'PDFBYTES', 'contract.pdf', 'application/pdf', user_name='Seba')
    assert rec['filename'] == 'contract.pdf'
    assert rec['content_type'] == 'application/pdf'
    assert rec['size'] == len(b'PDFBYTES')
    assert rec['key'] in spaces.store                       # uploaded
    assert rec['key'].startswith('private/foi-parcurs/route-sheets/VIN1/2026-08/')
    assert saved['col'] == 'attachments' and saved['val'][0]['key'] == rec['key']


def test_iter_attachment_files_yields_receipts_and_files(monkeypatch):
    # Reused by the per-car "download all contracts" ZIP to bundle bonuri + files.
    spaces = FakeSpaces()
    spaces.store['r1'] = (b'RECEIPT', 'image/jpeg')
    spaces.store['a1'] = (b'ANNEX', 'application/pdf')
    monkeypatch.setattr(rss, 'spaces_service', spaces)
    monkeypatch.setattr(rss, 'list_attachments', lambda *a, **k: [{'key': 'a1', 'filename': 'anexa.pdf'}])
    monkeypatch.setattr(rss, '_store', type('S', (), {
        'query_one': lambda self, *a, **k: {'alimentari': [{'receipt': {'key': 'r1', 'filename': 'bon.jpg'}}]}})())

    files = rss.iter_attachment_files('VIN1', 2026, 8)
    arc = {name: data for name, data in files}
    assert any(n.startswith('bonuri/') for n in arc)
    assert any(n.startswith('fisiere/') for n in arc)
    assert arc[next(n for n in arc if n.startswith('fisiere/'))] == b'ANNEX'
    assert arc[next(n for n in arc if n.startswith('bonuri/'))] == b'RECEIPT'


def test_remove_attachment_deletes_from_spaces(monkeypatch):
    spaces = FakeSpaces()
    spaces.store['k1'] = (b'x', 'application/pdf')
    monkeypatch.setattr(rss, 'spaces_service', spaces)
    monkeypatch.setattr(rss, 'list_attachments', lambda *a, **k: [{'key': 'k1', 'filename': 'a'}, {'key': 'k2', 'filename': 'b'}])
    saved = {}
    monkeypatch.setattr(rss, '_upsert_sheet_json', lambda vin, y, m, col, val: saved.update(val=val))

    rss.remove_attachment('VIN1', 2026, 8, 'k1')
    assert 'k1' not in spaces.store                          # deleted from Spaces
    assert [a['key'] for a in saved['val']] == ['k2']        # dropped from list


def test_remove_attachment_refuses_key_not_in_sheet(monkeypatch):
    # IDOR guard: a key that isn't recorded on THIS sheet must never be deleted
    # from Spaces (else any user could delete arbitrary cloud objects).
    spaces = FakeSpaces()
    spaces.store['private/carpark/1/photo.jpg'] = (b'x', 'image/jpeg')  # someone else's object
    monkeypatch.setattr(rss, 'spaces_service', spaces)
    monkeypatch.setattr(rss, 'list_attachments', lambda *a, **k: [{'key': 'private/foi-parcurs/route-sheets/V/2026-08/abc_a.pdf', 'filename': 'a'}])
    touched = {'upsert': False}
    monkeypatch.setattr(rss, '_upsert_sheet_json', lambda *a, **k: touched.update(upsert=True))

    rss.remove_attachment('VIN1', 2026, 8, 'private/carpark/1/photo.jpg')
    assert 'private/carpark/1/photo.jpg' in spaces.store     # NOT deleted — not ours
    assert touched['upsert'] is False                        # no write either
