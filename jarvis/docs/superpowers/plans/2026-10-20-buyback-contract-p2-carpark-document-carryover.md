# BuyBack Contract P2 — CarPark Document Carry-Over — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** On BuyBack→CarPark hand-off, carry buyback **documents** (document/civ/talon/contract) into the CarPark vehicle's real document store (`carpark_vehicle_documents`) with the correct MIME/extension — instead of today's behavior of re-uploading them as `.jpg` **gallery photos** (which corrupts PDFs and can make a document the vehicle's cover photo).

**Architecture:** Two surgical changes in `buyback/services/carpark_handoff.py`: (1) restrict `_carry_photos` to `photo_type='gallery'` (the repo's `get_by_record` already takes a `photo_type` filter); (2) add a best-effort `_carry_documents` that routes document-type rows to `carpark.repositories.document_repository.DocumentRepository`, preserving MIME + extension, and wire it into both hand-off paths.

**Tech Stack:** Flask + raw psycopg2; pytest with monkeypatch (no real DB needed for these unit tests).

**Spec:** `docs/superpowers/specs/2026-10-20-buyback-purchase-contract-design.md` (§7)

## Global Constraints

- Best-effort per item: a single document's Spaces fetch/upload or DB error is logged and skipped — it must NEVER fail the hand-off (the vehicle already exists by then). Mirror `_carry_photos`'s per-item try/except.
- Preserve the real MIME + file extension (a PDF stays `application/pdf` / `.pdf`), derived from the original Spaces content-type and the source key's extension — never hardcode `image/jpeg`/`.jpg` as `_carry_photos` does for gallery images.
- Documents are the set `photo_type ∈ {document, civ, talon, contract}`; everything else (`gallery`) is a photo.
- `DocumentRepository.create(vehicle_id, data)` keys must come from `DOCUMENT_FIELDS` = (document_type, title, file_url, dms_document_id, file_size, mime_type, notes, uploaded_by); `document_type` is required.
- Backend tests run with `DATABASE_URL=postgresql://localhost/defaultdb` (module harness), but these tests monkeypatch Spaces + repos so they touch no real DB.

## Review Focus

- **A carried PDF keeps its MIME/extension** (not `.jpg`/`image/jpeg`) — Task 2 test asserts `mime_type` + `file_url` extension.
- **A document never becomes the gallery cover** (`is_primary`) — Task 1 makes `_carry_photos` gallery-only, so documents never reach its `is_primary=(idx==0)` path.
- **A failing document carry doesn't break the hand-off** — Task 2 per-item try/except (asserted by a raising-fetch case).
- **Both hand-off paths carry documents** — `handoff_to_carpark` AND `handoff_to_carpark_custody` call `_carry_documents` (Task 2).
- **No gallery regression** — gallery photos still carry exactly as before (the existing `test_carpark_handoff` smoke test stays green).

---

### Task 1: `_carry_photos` carries only gallery photos

**Files:**
- Modify: `jarvis/buyback/services/carpark_handoff.py` (`_carry_photos`, line ~99)
- Test: `jarvis/tests/buyback/test_carpark_handoff.py`

**Interfaces:**
- Consumes: `_shared.photos_repo.get_by_record(record_id, photo_type=None)`.
- Produces: `_carry_photos` fetches with `photo_type='gallery'`, so document rows are excluded from the photo/`is_primary` path.

- [ ] **Step 1: Write the failing test**

```python
# append to jarvis/tests/buyback/test_carpark_handoff.py
def test_carry_photos_requests_only_gallery(monkeypatch):
    import buyback.services.carpark_handoff as ch
    seen = {}
    def fake_get(rid, ptype=None):
        seen['ptype'] = ptype
        return []
    monkeypatch.setattr(ch._shared.photos_repo, 'get_by_record', fake_get)
    ch._carry_photos(1, 2)
    assert seen['ptype'] == 'gallery'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/buyback/test_carpark_handoff.py -k carry_photos_requests_only_gallery -q`
Expected: FAIL (`seen['ptype']` is `None` — `_carry_photos` calls `get_by_record(record_id)` with no filter).

- [ ] **Step 3: Write minimal implementation**

In `carpark_handoff.py` `_carry_photos`, change:
```python
    photos = _shared.photos_repo.get_by_record(record_id)
```
to:
```python
    photos = _shared.photos_repo.get_by_record(record_id, 'gallery')
```
Also update the docstring's first line to say "every buyback **gallery** photo" (it already says gallery — no change needed if so).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/buyback/test_carpark_handoff.py -k carry_photos_requests_only_gallery -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jarvis/buyback/services/carpark_handoff.py jarvis/tests/buyback/test_carpark_handoff.py
git commit -m "fix(buyback): hand-off carries only gallery photos (documents excluded)"
```

---

### Task 2: `_carry_documents` → CarPark document store, wired into both hand-offs

**Files:**
- Modify: `jarvis/buyback/services/carpark_handoff.py` (add `_carry_documents`; call it in `handoff_to_carpark` ~line 80 and `handoff_to_carpark_custody` ~line 183)
- Test: `jarvis/tests/buyback/test_carpark_handoff.py`

**Interfaces:**
- Consumes: `_shared.photos_repo.get_by_record(record_id)`, `spaces_service.fetch/upload`, `carpark.repositories.document_repository.DocumentRepository.create(vehicle_id, data)`.
- Produces: `_carry_documents(record_id, veh_id)` — inserts one `carpark_vehicle_documents` row per buyback document, preserving MIME/extension; best-effort per document.

- [ ] **Step 1: Write the failing tests**

```python
# append to jarvis/tests/buyback/test_carpark_handoff.py
def _doc_rows():
    return [
        {'id': 1, 'url': 'private/buyback/5/img.jpg', 'photo_type': 'gallery', 'caption': None},
        {'id': 2, 'url': 'private/buyback/5/doc-a.pdf', 'photo_type': 'document', 'caption': 'CIV'},
        {'id': 3, 'url': 'private/buyback/5/con.pdf', 'photo_type': 'contract', 'caption': None},
    ]

def test_carry_documents_routes_only_docs_with_correct_mime(monkeypatch):
    import buyback.services.carpark_handoff as ch
    from carpark.repositories.document_repository import DocumentRepository
    monkeypatch.setattr(ch._shared.photos_repo, 'get_by_record', lambda rid, ptype=None: _doc_rows())
    monkeypatch.setattr(ch.spaces_service, 'fetch', lambda key: (b'%PDF-1.4 data', 'application/pdf'))
    monkeypatch.setattr(ch.spaces_service, 'upload', lambda data, key, ct: None)
    created = []
    monkeypatch.setattr(DocumentRepository, 'create',
                        lambda self, vid, data: created.append((vid, data)) or data)
    ch._carry_documents(5, 99)
    # only the document + contract rows (NOT the gallery row)
    assert [d['document_type'] for _, d in created] == ['document', 'contract']
    assert all(vid == 99 for vid, _ in created)
    assert all(d['file_url'].startswith('private/carpark/99/') and d['file_url'].endswith('.pdf')
               for _, d in created)
    assert all(d['mime_type'] == 'application/pdf' for _, d in created)

def test_carry_documents_swallows_a_failing_document(monkeypatch):
    import buyback.services.carpark_handoff as ch
    monkeypatch.setattr(ch._shared.photos_repo, 'get_by_record', lambda rid, ptype=None: _doc_rows())
    def boom(key):
        raise RuntimeError('spaces down')
    monkeypatch.setattr(ch.spaces_service, 'fetch', boom)
    # must not raise — best-effort
    ch._carry_documents(5, 99)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/buyback/test_carpark_handoff.py -k carry_documents -q`
Expected: FAIL (`_carry_documents` does not exist → AttributeError).

- [ ] **Step 3: Write minimal implementation**

In `carpark_handoff.py`, add after `_carry_photos` (before `_backlink`):
```python
_DOC_PHOTO_TYPES = ('document', 'civ', 'talon', 'contract')


def _carry_documents(record_id, veh_id):
    """Copy every buyback DOCUMENT (civ/talon/contract/other) for `record_id`
    onto the new CarPark vehicle's document store (carpark_vehicle_documents),
    preserving the real MIME + file extension — unlike _carry_photos, which is
    gallery-only and re-encodes to jpg. Best-effort per document: one bad
    document is logged and skipped, never raised."""
    from carpark.repositories.document_repository import DocumentRepository
    docs = [p for p in _shared.photos_repo.get_by_record(record_id)
            if p.get('photo_type') in _DOC_PHOTO_TYPES]
    if not docs:
        return
    repo = DocumentRepository()
    for d in docs:
        try:
            data, content_type = spaces_service.fetch(d['url'])
            name = d['url'].rsplit('/', 1)[-1]
            ext = name.rsplit('.', 1)[-1] if '.' in name else 'pdf'
            new_key = f'private/carpark/{veh_id}/doc-{uuid4().hex}.{ext}'
            spaces_service.upload(data, new_key, content_type or 'application/octet-stream')
            repo.create(veh_id, {
                'document_type': d.get('photo_type') or 'document',
                'title': d.get('caption') or (d.get('photo_type') or 'document'),
                'file_url': new_key,
                'mime_type': content_type or None,
                'file_size': len(data) if data else None,
            })
        except Exception:
            logger.warning(
                'CarPark hand-off: failed to carry document id=%s (buyback record=%s) '
                'to vehicle=%s', d.get('id'), record_id, veh_id, exc_info=True,
            )
```

Then call it in BOTH hand-off functions, right after their `_carry_photos(record['id'], veh['id'])` line:
```python
    _carry_documents(record['id'], veh['id'])
```
(once in `handoff_to_carpark`, once in `handoff_to_carpark_custody`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/buyback/test_carpark_handoff.py -q`
Expected: PASS (new unit tests + the existing hand-off smoke test — gallery path unchanged).

- [ ] **Step 5: Commit**

```bash
git add jarvis/buyback/services/carpark_handoff.py jarvis/tests/buyback/test_carpark_handoff.py
git commit -m "feat(buyback): carry documents to carpark_vehicle_documents on hand-off"
```

---

## Done-when

- `_carry_photos` requests only `gallery`; `_carry_documents` routes document/civ/talon/contract rows to `carpark_vehicle_documents` with correct MIME/extension, best-effort, wired into both hand-off paths.
- `DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/buyback/ -q` green (incl. the existing hand-off smoke test).
- A generated contract (P4/P5) stored as a `'contract'` document will now ride the VIN into CarPark automatically.
