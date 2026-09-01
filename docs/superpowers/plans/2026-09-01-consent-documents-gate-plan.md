# Consent-Documents Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Block every user on first login (web/Hub/mobile-2) until they read, acknowledge, and draw a signature on three mandatory legal documents (data-usage, GDPR, NDA), with admin-editable text and an HR compliance view.

**Architecture:** A generic consent-documents module. Two new Postgres tables (`consent_documents`, `user_consent_signatures`) keyed by `user_id` — the protected `users` table is never altered. A Flask blueprint (`consents_bp`) exposes pending/sign/admin/compliance endpoints; both `current-user` endpoints gain a `consents_complete` flag so the gate reads it with zero extra calls. One full-screen blocker component is inserted at the single auth choke point on web (`Layout.tsx`) and mobile (`ProtectedRoute`), reusing the existing `SignatureCanvas`.

**Tech Stack:** Python 3 / Flask, PostgreSQL (raw SQL via psycopg2, `%s` params), `BaseRepository`; React 19 + Vite + TS + Tailwind 4 + shadcn/ui; Capacitor (mobile-2) + Zustand + TanStack Query.

**Spec:** `docs/superpowers/specs/2026-08-26-consent-documents-gate-design.md`.

## Global Constraints

- **DB:** PostgreSQL only, raw SQL via `psycopg2`, `%s` params, **no ORM, no f-string SQL**. Repositories subclass `core.base_repository.BaseRepository` and use `query_one(sql, params)`, `query_all(sql, params)`, `execute(sql, params, returning=False)`. **No `transaction()` helper.**
- **DDL:** idempotent (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `INSERT ... ON CONFLICT DO NOTHING`), placed in `jarvis/migrations/domains/schema_incremental.py` — a **protected** file (modification already authorized for this feature). No change to `init_schema.py` (schema_incremental is already wired into it).
- **Route guards:** `@login_required` for user-facing endpoints; `@v2_permission_required(module, entity, action)` from `core/roles/decorators.py` for admin/HR endpoints. Never trust a client-supplied `user_id` — always use `current_user.id`.
- **API envelope:** backend returns wrapped objects (`{documents: [...]}`, `{pending: [...]}`); frontend unwraps before use.
- **Frontend:** target `jarvis/frontend/src/` (React SPA at `/app/*`). Reuse `components/shared/SignatureCanvas.tsx` (web) / `src/components/shared/SignatureCanvas.tsx` (mobile).
- **Rollout safeguard:** all three seed documents ship `is_active = FALSE`. The gate stays dormant until an admin finalizes copy and flips them active. Placeholder legal text must never block real staff.
- **Sign-once (v1):** editing a document's `body` does **not** force existing signers to re-sign; the gate checks *existence* of a signature per doc, not version match. `version` is bumped and stored for a future opt-in re-consent.
- **Do NOT author binding legal text.** GDPR + NDA bodies are structured placeholders marked `‹DE COMPLETAT›`.
- **Base branch:** `staging` (JARVIS/CLAUDE.md default; user held final confirmation — confirm before creating the worktree).
- **Pre-push checklist (run all, stop on any failure):**
  ```bash
  cd jarvis/frontend && npm run build          # 0 TypeScript errors
  cd ../.. && python -m pytest tests/ -x -q    # green
  python3 -m py_compile jarvis/app.py          # imports resolve
  git status                                    # no untracked source files
  ```
- **Mobile ship ritual:** prepend a `src/data/changelog.ts` entry, then `npm run build && npx cap sync android`; wait for APK CI before promoting.

---

## Phase 1 — Backend (DB + module + API). Independently testable via pytest + curl.

### Task 1: Database schema + seed

**Files:**
- Modify: `jarvis/migrations/domains/schema_incremental.py` (append inside the incremental function that already contains the `fp_vehicle_blocks` block near line 2412 — add before it returns)
- Test: `tests/consents/test_consent_schema.py` (create)

**Interfaces:**
- Produces: tables `consent_documents(id, doc_key, title, body, sort_order, requires_signature, is_mandatory, is_active, version, created_at, updated_at, updated_by)` and `user_consent_signatures(id, user_id, document_id, document_version, response, signature_image, document_hash, ip_address, user_agent, signed_at)` with `UNIQUE(user_id, document_id)`; 3 seed rows in `consent_documents` (`data_usage`, `gdpr`, `nda`) all `is_active=FALSE`.

- [ ] **Step 1: Write the failing test**

```python
# tests/consents/test_consent_schema.py
from core.base_repository import BaseRepository

def _repo():
    return BaseRepository()

def test_consent_tables_exist():
    r = _repo()
    cols = r.query_all("""
        SELECT table_name, column_name FROM information_schema.columns
        WHERE table_name IN ('consent_documents','user_consent_signatures')
    """)
    names = {(c['table_name'], c['column_name']) for c in cols}
    assert ('consent_documents', 'doc_key') in names
    assert ('user_consent_signatures', 'signature_image') in names
    assert ('user_consent_signatures', 'document_hash') in names

def test_unique_signature_per_user_doc():
    r = _repo()
    con = r.query_one("""
        SELECT COUNT(*) AS n FROM information_schema.table_constraints
        WHERE table_name = 'user_consent_signatures' AND constraint_type = 'UNIQUE'
    """)
    assert con['n'] >= 1

def test_three_docs_seeded_inactive():
    r = _repo()
    rows = r.query_all("SELECT doc_key, is_active FROM consent_documents ORDER BY sort_order")
    keys = [x['doc_key'] for x in rows]
    assert keys == ['data_usage', 'gdpr', 'nda']
    assert all(x['is_active'] is False for x in rows)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/consents/test_consent_schema.py -v`
Expected: FAIL (tables/relation do not exist).

- [ ] **Step 3: Add the DDL + seed to `schema_incremental.py`**

Append these `cursor.execute(...)` calls inside the incremental function (same style as the `fp_vehicle_blocks` block):

```python
    # ── Consent documents — mandatory first-login legal gate ──
    # Two user-keyed tables (users table is intentionally NOT altered).
    # Seeded is_active=FALSE so placeholder copy never blocks staff; an admin
    # finalizes text in Settings then flips active. See consents module.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS consent_documents (
            id                 SERIAL PRIMARY KEY,
            doc_key            TEXT NOT NULL UNIQUE,
            title              TEXT NOT NULL,
            body               TEXT NOT NULL DEFAULT '',
            sort_order         INTEGER NOT NULL DEFAULT 0,
            requires_signature BOOLEAN NOT NULL DEFAULT TRUE,
            is_mandatory       BOOLEAN NOT NULL DEFAULT TRUE,
            is_active          BOOLEAN NOT NULL DEFAULT TRUE,
            version            INTEGER NOT NULL DEFAULT 1,
            created_at         TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at         TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_by         INTEGER REFERENCES users(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_consent_signatures (
            id               SERIAL PRIMARY KEY,
            user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            document_id      INTEGER NOT NULL REFERENCES consent_documents(id) ON DELETE CASCADE,
            document_version INTEGER NOT NULL DEFAULT 1,
            response         TEXT NOT NULL DEFAULT 'accepted'
                                CHECK (response IN ('accepted','declined')),
            signature_image  TEXT,
            document_hash    TEXT,
            ip_address       TEXT,
            user_agent       TEXT,
            signed_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_user_consent UNIQUE (user_id, document_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ucs_user ON user_consent_signatures(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ucs_document ON user_consent_signatures(document_id)')

    # Seed the 3 documents (inactive). Bodies are placeholders — the data_usage
    # body is adapted from the provided Connecteam example; gdpr/nda are marked
    # for DPO/legal completion. ON CONFLICT keeps admin edits on re-run.
    cursor.execute('''
        INSERT INTO consent_documents (doc_key, title, body, sort_order, is_active)
        VALUES
          ('data_usage',
           'Acord privind utilizarea datelor de contact',
           %s, 1, FALSE),
          ('gdpr',
           'Notă de informare și acord GDPR',
           %s, 2, FALSE),
          ('nda',
           'Acord de confidențialitate (NDA)',
           %s, 3, FALSE)
        ON CONFLICT (doc_key) DO NOTHING
    ''', (_SEED_DATA_USAGE, _SEED_GDPR, _SEED_NDA))
```

Add these module-level string constants near the top of `schema_incremental.py`:

```python
_SEED_DATA_USAGE = (
    "Pentru o comunicare directă a informațiilor dinspre companie către "
    "dumneavoastră și dinspre dumneavoastră către companie, Autoworld vă invită "
    "să utilizați aplicația JARVIS, autentificându-vă cu:\n"
    "• numele și prenumele\n"
    "• numărul de telefon\n"
    "• și/sau adresa de e-mail personală sau de firmă\n\n"
    "Aplicația NU urmărește și NU prelucrează date privind:\n"
    "• locația telefonului\n"
    "• conținutul din telefon\n"
    "• alte date personale în afara celor menționate mai sus\n\n"
    "Prin semnarea prezentului acord confirm că sunt de acord ca datele "
    "menționate să fie utilizate în cadrul aplicației JARVIS a Autoworld."
)
_SEED_GDPR = (
    "‹DE COMPLETAT DPO›\n\n"
    "Notă de informare privind prelucrarea datelor cu caracter personal\n"
    "Temei legal: Regulamentul (UE) 2016/679 (GDPR) și Legea nr. 190/2018.\n\n"
    "1. Operator de date: ‹denumire, CUI, sediu›\n"
    "2. Categoriile de date prelucrate: ‹…›\n"
    "3. Scopul prelucrării: ‹…›\n"
    "4. Durata de stocare: ‹…›\n"
    "5. Drepturile persoanei vizate: acces, rectificare, ștergere, "
    "restricționare, portabilitate, opoziție, retragerea consimțământului, "
    "plângere la ANSPDCP.\n"
    "6. Date de contact DPO: ‹…›"
)
_SEED_NDA = (
    "‹DE COMPLETAT — juridic›\n\n"
    "Acord de confidențialitate (NDA)\n\n"
    "1. Părțile\n"
    "2. Definiția informațiilor confidențiale\n"
    "3. Obligațiile de confidențialitate\n"
    "4. Durata obligațiilor\n"
    "5. Consecințele încălcării\n"
    "6. Legea aplicabilă și jurisdicția"
)
```

- [ ] **Step 4: Apply the migration to local dev DB**

The backend runs `database.init_db()` on import, which calls the incremental migration. Start the local backend once (against local dev DB — **NEVER prod**) to apply:

Run: `python -c "import jarvis.app"`  *(triggers init_db against `postgresql://localhost/defaultdb`)*
Then verify: `psql postgresql://localhost/defaultdb -c "\dt consent_documents" -c "SELECT doc_key,is_active FROM consent_documents ORDER BY sort_order;"`
Expected: table listed; 3 rows, all `f` (inactive).

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/consents/test_consent_schema.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add jarvis/migrations/domains/schema_incremental.py tests/consents/test_consent_schema.py
git commit -m "feat(consents): DB schema + seed for mandatory consent gate"
```

---

### Task 2: ConsentRepository

**Files:**
- Create: `jarvis/core/consents/__init__.py` (empty)
- Create: `jarvis/core/consents/repositories/__init__.py` (empty)
- Create: `jarvis/core/consents/repositories/consent_repository.py`
- Test: `tests/consents/test_consent_repository.py`

**Interfaces:**
- Consumes: `BaseRepository` (`query_one`, `query_all`, `execute`).
- Produces: `ConsentRepository` with `list_active_mandatory() -> list[dict]`, `list_all() -> list[dict]`, `get_by_id(int) -> dict|None`, `get_by_key(str) -> dict|None`, `create_document(...) -> dict`, `update_document(...) -> dict`, `get_user_signed_ids(int) -> list[int]`, `insert_signature(...) -> None`, `count_active_mandatory() -> int`, `count_user_accepted_mandatory(int) -> int`, `get_compliance() -> list[dict]`.

- [ ] **Step 1: Write the failing test** (integration — uses local dev DB seeded in Task 1)

```python
# tests/consents/test_consent_repository.py
import pytest
from core.consents.repositories.consent_repository import ConsentRepository

@pytest.fixture
def repo():
    return ConsentRepository()

def test_get_by_key_returns_seeded_doc(repo):
    doc = repo.get_by_key('data_usage')
    # seeded inactive -> get_by_key filters is_active=TRUE, so None until activated
    assert doc is None

def test_list_all_includes_inactive(repo):
    docs = repo.list_all()
    keys = {d['doc_key'] for d in docs}
    assert {'data_usage', 'gdpr', 'nda'}.issubset(keys)

def test_count_active_mandatory_zero_when_all_inactive(repo):
    # all seeds inactive at start
    assert repo.count_active_mandatory() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/consents/test_consent_repository.py -v`
Expected: FAIL (`ModuleNotFoundError: core.consents...`).

- [ ] **Step 3: Implement the repository**

```python
# jarvis/core/consents/repositories/consent_repository.py
"""Data access for the mandatory consent-documents gate."""
from typing import Optional, Dict, Any, List
from core.base_repository import BaseRepository


class ConsentRepository(BaseRepository):
    # ---------- documents ----------
    def list_active_mandatory(self) -> List[Dict[str, Any]]:
        return self.query_all('''
            SELECT id, doc_key, title, body, sort_order, version, requires_signature
            FROM consent_documents
            WHERE is_active = TRUE AND is_mandatory = TRUE
            ORDER BY sort_order, id
        ''')

    def list_all(self) -> List[Dict[str, Any]]:
        return self.query_all('''
            SELECT id, doc_key, title, body, sort_order, requires_signature,
                   is_mandatory, is_active, version, updated_at, updated_by
            FROM consent_documents
            ORDER BY sort_order, id
        ''')

    def get_by_id(self, doc_id: int) -> Optional[Dict[str, Any]]:
        return self.query_one('''
            SELECT id, doc_key, title, body, sort_order, requires_signature,
                   is_mandatory, is_active, version
            FROM consent_documents WHERE id = %s
        ''', (doc_id,))

    def get_by_key(self, doc_key: str) -> Optional[Dict[str, Any]]:
        return self.query_one('''
            SELECT id, doc_key, title, body, sort_order, requires_signature,
                   is_mandatory, is_active, version
            FROM consent_documents WHERE doc_key = %s AND is_active = TRUE
        ''', (doc_key,))

    def create_document(self, doc_key, title, body, sort_order,
                        requires_signature, is_mandatory, is_active, updated_by):
        return self.execute('''
            INSERT INTO consent_documents
                (doc_key, title, body, sort_order, requires_signature,
                 is_mandatory, is_active, version, updated_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1, %s)
            RETURNING id, doc_key, title, version, is_active
        ''', (doc_key, title, body, sort_order, requires_signature,
              is_mandatory, is_active, updated_by), returning=True)

    def update_document(self, doc_id, title, body, sort_order, is_active,
                        bump_version, updated_by):
        return self.execute('''
            UPDATE consent_documents
               SET title = %s, body = %s, sort_order = %s, is_active = %s,
                   version = version + %s, updated_at = NOW(), updated_by = %s
             WHERE id = %s
            RETURNING id, doc_key, title, version, is_active
        ''', (title, body, sort_order, is_active, 1 if bump_version else 0,
              updated_by, doc_id), returning=True)

    # ---------- signatures ----------
    def get_user_signed_ids(self, user_id: int) -> List[int]:
        rows = self.query_all('''
            SELECT document_id FROM user_consent_signatures
            WHERE user_id = %s AND response = 'accepted'
        ''', (user_id,))
        return [r['document_id'] for r in rows]

    def insert_signature(self, user_id, document_id, version, signature_image,
                         document_hash, ip, user_agent) -> None:
        self.execute('''
            INSERT INTO user_consent_signatures
                (user_id, document_id, document_version, response,
                 signature_image, document_hash, ip_address, user_agent)
            VALUES (%s, %s, %s, 'accepted', %s, %s, %s, %s)
            ON CONFLICT (user_id, document_id) DO NOTHING
        ''', (user_id, document_id, version, signature_image,
              document_hash, ip, user_agent))

    def count_active_mandatory(self) -> int:
        row = self.query_one('''
            SELECT COUNT(*) AS n FROM consent_documents
            WHERE is_active = TRUE AND is_mandatory = TRUE
        ''')
        return int(row['n']) if row else 0

    def count_user_accepted_mandatory(self, user_id: int) -> int:
        row = self.query_one('''
            SELECT COUNT(*) AS n
            FROM user_consent_signatures s
            JOIN consent_documents d ON d.id = s.document_id
            WHERE s.user_id = %s AND s.response = 'accepted'
              AND d.is_active = TRUE AND d.is_mandatory = TRUE
        ''', (user_id,))
        return int(row['n']) if row else 0

    def get_compliance(self) -> List[Dict[str, Any]]:
        return self.query_all('''
            SELECT u.id AS user_id, u.name, u.email, u.company,
                   d.doc_key, d.title, s.signed_at,
                   (s.id IS NOT NULL) AS signed
            FROM users u
            CROSS JOIN consent_documents d
            LEFT JOIN user_consent_signatures s
              ON s.user_id = u.id AND s.document_id = d.id
             AND s.response = 'accepted'
            WHERE d.is_active = TRUE AND d.is_mandatory = TRUE
              AND u.is_active = TRUE
            ORDER BY u.name, d.sort_order
        ''')
```

Create the two empty `__init__.py` files.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/consents/test_consent_repository.py -v`
Expected: PASS. (If `execute(..., returning=True)` returns a list vs dict in this codebase, adjust `create/update_document` to match — confirm against another repo that uses `RETURNING`.)

- [ ] **Step 5: Commit**

```bash
git add jarvis/core/consents/ tests/consents/test_consent_repository.py
git commit -m "feat(consents): ConsentRepository data access"
```

---

### Task 3: ConsentService (pure logic, DB-independent tests)

**Files:**
- Create: `jarvis/core/consents/services/__init__.py` (empty)
- Create: `jarvis/core/consents/services/consent_service.py`
- Test: `tests/consents/test_consent_service.py`

**Interfaces:**
- Consumes: `ConsentRepository` (injectable via constructor for tests).
- Produces: `ConsentService(repo=None)` with `get_pending_for_user(user_id) -> {'complete': bool, 'pending': list}`, `is_complete(user_id) -> bool`, `pending_count(user_id) -> int`, `sign(user_id, document_id, signature_image, ip, user_agent) -> {'complete': bool, 'pending_count': int}`, staticmethod `compute_hash(body) -> str`.

- [ ] **Step 1: Write the failing test** (fake repo — no DB)

```python
# tests/consents/test_consent_service.py
import pytest
from core.consents.services.consent_service import ConsentService

class FakeRepo:
    def __init__(self):
        self.docs = [
            {'id': 1, 'doc_key': 'data_usage', 'title': 'A', 'body': 'x',
             'version': 1, 'requires_signature': True, 'is_active': True, 'is_mandatory': True},
            {'id': 2, 'doc_key': 'gdpr', 'title': 'B', 'body': 'y',
             'version': 1, 'requires_signature': True, 'is_active': True, 'is_mandatory': True},
        ]
        self.signed = set()
        self.inserted = []
    def list_active_mandatory(self): return [d for d in self.docs if d['is_active'] and d['is_mandatory']]
    def get_by_id(self, i): return next((d for d in self.docs if d['id'] == i), None)
    def get_user_signed_ids(self, u): return list(self.signed)
    def count_active_mandatory(self): return len(self.list_active_mandatory())
    def count_user_accepted_mandatory(self, u): return len(self.signed)
    def insert_signature(self, u, d, v, img, h, ip, ua): self.inserted.append((u, d, h)); self.signed.add(d)

PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=='

def test_pending_lists_unsigned_in_order():
    svc = ConsentService(FakeRepo())
    res = svc.get_pending_for_user(7)
    assert res['complete'] is False
    assert [d['id'] for d in res['pending']] == [1, 2]

def test_sign_advances_and_completes():
    repo = FakeRepo(); svc = ConsentService(repo)
    r1 = svc.sign(7, 1, PNG, '1.2.3.4', 'UA')
    assert r1['complete'] is False and r1['pending_count'] == 1
    r2 = svc.sign(7, 2, PNG, '1.2.3.4', 'UA')
    assert r2['complete'] is True and r2['pending_count'] == 0
    assert len(repo.inserted) == 2

def test_sign_rejects_missing_signature():
    svc = ConsentService(FakeRepo())
    with pytest.raises(ValueError):
        svc.sign(7, 1, '', '1.2.3.4', 'UA')

def test_sign_rejects_invalid_document():
    svc = ConsentService(FakeRepo())
    with pytest.raises(ValueError):
        svc.sign(7, 999, PNG, '1.2.3.4', 'UA')

def test_hash_is_stable():
    assert ConsentService.compute_hash('abc') == ConsentService.compute_hash('abc')
    assert ConsentService.compute_hash('abc') != ConsentService.compute_hash('abd')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/consents/test_consent_service.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement the service**

```python
# jarvis/core/consents/services/consent_service.py
"""Business logic for the mandatory consent-documents gate."""
import hashlib
from typing import Dict, Any, Optional
from core.consents.repositories.consent_repository import ConsentRepository

_MAX_SIGNATURE_BYTES = 700_000  # ~500KB PNG in base64


def _valid_png(data: str) -> bool:
    return bool(data) and data.startswith('data:image/png;base64,') and len(data) < _MAX_SIGNATURE_BYTES


class ConsentService:
    def __init__(self, repo: Optional[ConsentRepository] = None):
        self.repo = repo or ConsentRepository()

    @staticmethod
    def compute_hash(body: str) -> str:
        return hashlib.sha256((body or '').encode('utf-8')).hexdigest()

    def get_pending_for_user(self, user_id: int) -> Dict[str, Any]:
        docs = self.repo.list_active_mandatory()
        signed = set(self.repo.get_user_signed_ids(user_id))
        pending = [d for d in docs if d['id'] not in signed]
        return {'complete': len(pending) == 0, 'pending': pending}

    def is_complete(self, user_id: int) -> bool:
        return self.repo.count_user_accepted_mandatory(user_id) >= self.repo.count_active_mandatory()

    def pending_count(self, user_id: int) -> int:
        return max(0, self.repo.count_active_mandatory() - self.repo.count_user_accepted_mandatory(user_id))

    def sign(self, user_id: int, document_id: int, signature_image: str,
             ip: str, user_agent: str) -> Dict[str, Any]:
        doc = self.repo.get_by_id(document_id)
        if not doc or not doc.get('is_active') or not doc.get('is_mandatory'):
            raise ValueError('invalid_document')
        if doc.get('requires_signature') and not _valid_png(signature_image):
            raise ValueError('signature_required')
        self.repo.insert_signature(
            user_id, document_id, doc['version'], signature_image,
            self.compute_hash(doc['body']), ip, user_agent)
        return {'complete': self.is_complete(user_id),
                'pending_count': self.pending_count(user_id)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/consents/test_consent_service.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add jarvis/core/consents/services/ tests/consents/test_consent_service.py
git commit -m "feat(consents): ConsentService pending/sign/hash logic"
```

---

### Task 4: Routes (`consents_bp`) + blueprint registration + mobile mirror + CORS

**Files:**
- Create: `jarvis/core/consents/routes.py`
- Modify: `jarvis/app.py` (register blueprint in `_register_blueprints`; add mobile routes to `_mobile_cors` allow-methods)
- Test: `tests/consents/test_consent_routes.py`

**Interfaces:**
- Consumes: `ConsentService`, `@login_required`, `@v2_permission_required`.
- Produces: blueprint `consents_bp` with `GET /api/consents/pending`, `POST /api/consents/sign`, `GET /api/consents/documents/<doc_key>`, `GET/POST /api/consents/documents`, `PUT /api/consents/documents/<int:doc_id>`, `GET /api/consents/compliance`; plus mobile `GET /api/mobile/consents/pending`, `POST /api/mobile/consents/sign`.

- [ ] **Step 1: Write the failing test**

```python
# tests/consents/test_consent_routes.py
# Uses the app's existing test client + login fixture. If the project exposes a
# `client` and `login_as(user_id)` fixture in tests/conftest.py, reuse them;
# otherwise adapt to the existing auth-test pattern in tests/.
def test_pending_requires_auth(client):
    resp = client.get('/api/consents/pending')
    assert resp.status_code in (302, 401)  # redirect to login or unauthorized

def test_sign_uses_session_user_not_body(client, login_as):
    login_as(2)  # a normal user
    # attempt to sign on behalf of another user via body -> ignored
    resp = client.post('/api/consents/sign', json={'user_id': 999, 'document_id': 1,
                                                    'signature_image': ''})
    # no active docs seeded -> invalid_document OR signature_required, never 200 with user 999
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/consents/test_consent_routes.py -v`
Expected: FAIL (routes not registered → 404).

- [ ] **Step 3: Implement `routes.py`**

```python
# jarvis/core/consents/routes.py
"""HTTP routes for the mandatory consent-documents gate."""
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from core.consents.services.consent_service import ConsentService
from core.roles.decorators import v2_permission_required

consents_bp = Blueprint('consents', __name__)
_svc = ConsentService()


def _client_ip() -> str:
    fwd = request.headers.get('X-Forwarded-For', '')
    return (fwd.split(',')[0].strip() if fwd else '') or (request.remote_addr or '')


def _do_sign():
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(_svc.sign(
            current_user.id,
            int(data.get('document_id') or 0),
            data.get('signature_image') or '',
            _client_ip(),
            request.headers.get('User-Agent', ''),
        ))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


# ---------- user-facing (web) ----------
@consents_bp.route('/api/consents/pending')
@login_required
def pending():
    return jsonify(_svc.get_pending_for_user(current_user.id))


@consents_bp.route('/api/consents/sign', methods=['POST'])
@login_required
def sign():
    return _do_sign()


@consents_bp.route('/api/consents/documents/<doc_key>')
@login_required
def get_document(doc_key):
    doc = _svc.repo.get_by_key(doc_key)
    if not doc:
        return jsonify({'error': 'not_found'}), 404
    return jsonify({'document': doc})


# ---------- user-facing (mobile mirror) ----------
@consents_bp.route('/api/mobile/consents/pending')
@login_required
def mobile_pending():
    return jsonify(_svc.get_pending_for_user(current_user.id))


@consents_bp.route('/api/mobile/consents/sign', methods=['POST'])
@login_required
def mobile_sign():
    return _do_sign()


# ---------- admin editor (Settings) ----------
@consents_bp.route('/api/consents/documents')
@v2_permission_required('settings', 'consents', 'view')
def list_documents():
    return jsonify({'documents': _svc.repo.list_all()})


@consents_bp.route('/api/consents/documents', methods=['POST'])
@v2_permission_required('settings', 'consents', 'edit')
def create_document():
    d = request.get_json(silent=True) or {}
    if not d.get('doc_key') or not d.get('title'):
        return jsonify({'error': 'doc_key_and_title_required'}), 400
    doc = _svc.repo.create_document(
        d['doc_key'], d['title'], d.get('body', ''), int(d.get('sort_order', 0)),
        bool(d.get('requires_signature', True)), bool(d.get('is_mandatory', True)),
        bool(d.get('is_active', False)), current_user.id)
    return jsonify({'document': doc}), 201


@consents_bp.route('/api/consents/documents/<int:doc_id>', methods=['PUT'])
@v2_permission_required('settings', 'consents', 'edit')
def update_document(doc_id):
    d = request.get_json(silent=True) or {}
    existing = _svc.repo.get_by_id(doc_id)
    if not existing:
        return jsonify({'error': 'not_found'}), 404
    bump = 'body' in d and d['body'] != existing['body']
    doc = _svc.repo.update_document(
        doc_id,
        d.get('title', existing['title']),
        d.get('body', existing['body']),
        int(d.get('sort_order', existing['sort_order'])),
        bool(d.get('is_active', existing['is_active'])),
        bump, current_user.id)
    return jsonify({'document': doc})


# ---------- HR compliance ----------
@consents_bp.route('/api/consents/compliance')
@v2_permission_required('hr', 'consents', 'view')
def compliance():
    rows = _svc.repo.get_compliance()
    users = {}
    for r in rows:
        u = users.setdefault(r['user_id'], {
            'user_id': r['user_id'], 'name': r['name'],
            'email': r['email'], 'company': r['company'], 'documents': []})
        u['documents'].append({
            'doc_key': r['doc_key'], 'title': r['title'],
            'signed': bool(r['signed']), 'signed_at': r['signed_at']})
    result = list(users.values())
    if request.args.get('status') == 'pending':
        result = [u for u in result if not all(d['signed'] for d in u['documents'])]
    return jsonify({'compliance': result})
```

- [ ] **Step 4: Register the blueprint + CORS in `app.py`**

In `_register_blueprints()` (next to the other `*_bp` registrations):

```python
    from core.consents.routes import consents_bp
    app.register_blueprint(consents_bp)
```

In `_mobile_cors` (the mobile CORS handler that lists allowed paths/methods), add `POST` for the two new mobile paths so the Capacitor client isn't blocked — follow the exact shape already used for `/api/mobile/current-user` and other mobile POST endpoints.

**Permission note:** `@v2_permission_required('settings','consents',...)` and `('hr','consents','view')` require the permission entity to exist in the v2 matrix. If the matrix is seed-driven, add `consents` view/edit entries under the `settings` and `hr` modules in the permissions seed (same file/pattern as other module entities), so an Admin+HR role resolves them. Confirm the exact seed location before finalizing (grep `get_all_role_permissions` usages).

- [ ] **Step 5: Run tests + import check**

Run: `python -m pytest tests/consents/ -v && python3 -m py_compile jarvis/app.py`
Expected: PASS + clean compile.

- [ ] **Step 6: Manual smoke (local backend on :5001)**

```bash
# with the app running locally and a dev session cookie:
curl -s localhost:5001/api/consents/pending -b devcookie.txt   # -> {"complete":true,"pending":[]} when all inactive
```

- [ ] **Step 7: Commit**

```bash
git add jarvis/core/consents/routes.py jarvis/app.py tests/consents/test_consent_routes.py
git commit -m "feat(consents): routes + blueprint + mobile mirror + CORS"
```

---

### Task 5: Surface `consents_complete` on both current-user endpoints

**Files:**
- Modify: `jarvis/core/auth/routes.py` (`api_current_user`, in the returned `user` dict ~line 380-420)
- Modify: the mobile `/api/mobile/current-user` handler (locate via `grep -rn "mobile/current-user" jarvis/`)
- Test: extend `tests/consents/test_consent_routes.py`

**Interfaces:**
- Consumes: `ConsentService.is_complete`, `ConsentService.pending_count`.
- Produces: `user.consents_complete: bool` and `user.pending_consents_count: int` in both current-user payloads.

- [ ] **Step 1: Write the failing test**

```python
def test_current_user_exposes_consents_complete(client, login_as):
    login_as(2)
    resp = client.get('/api/auth/current-user')
    body = resp.get_json()
    assert 'consents_complete' in body['user']
    assert 'pending_consents_count' in body['user']
    # all docs inactive -> nothing mandatory -> complete
    assert body['user']['consents_complete'] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/consents/test_consent_routes.py::test_current_user_exposes_consents_complete -v`
Expected: FAIL (key absent).

- [ ] **Step 3: Add the flag in `api_current_user`**

At the top of `api_current_user` (inside the `if current_user.is_authenticated:` block):

```python
        from core.consents.services.consent_service import ConsentService as _ConsentSvc
        _consent = _ConsentSvc()
        _consents_complete = _consent.is_complete(current_user.id)
        _pending_consents = _consent.pending_count(current_user.id)
```

Add to the returned `user` dict:

```python
                'consents_complete': _consents_complete,
                'pending_consents_count': _pending_consents,
```

Apply the identical two keys to the `/api/mobile/current-user` handler's user payload.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/consents/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jarvis/core/auth/routes.py jarvis/<mobile current-user file> tests/consents/test_consent_routes.py
git commit -m "feat(consents): expose consents_complete on current-user (web + mobile)"
```

---

## Phase 2 — Web frontend (covers Hub). Verified via `npm run build` + Playwright/manual.

> The JARVIS web frontend has no unit-test runner in the pre-push checklist (only `npm run build` typecheck + Playwright). Each web task is verified by (a) a clean `npm run build`, and (b) a concrete manual/Playwright check using the webapp-testing skill.

### Task 6: API client + types + `useConsents` hook

**Files:**
- Create: `jarvis/frontend/src/api/consents.ts`
- Modify: `jarvis/frontend/src/types/index.ts` (or the `User` type file) — add `consents_complete?: boolean; pending_consents_count?: number`
- Create: `jarvis/frontend/src/hooks/useConsents.ts`

**Interfaces:**
- Produces: `consentsApi.getPending()`, `consentsApi.sign(documentId, signatureImage)`, `consentsApi.getDocument(docKey)`, `consentsApi.listDocuments()`, `consentsApi.createDocument(payload)`, `consentsApi.updateDocument(id, payload)`, `consentsApi.getCompliance(status?)`; hook `usePendingConsents()` returning `{data, isLoading, refetch}`; `ConsentDocument` type `{id, doc_key, title, body, sort_order, version, requires_signature}`.

- [ ] **Step 1: Implement the API client** (mirror an existing `src/api/*.ts` module's fetch wrapper + envelope-unwrap)

```ts
// jarvis/frontend/src/api/consents.ts
import { api } from './client'; // reuse the project's fetch wrapper (see src/api/auth.ts)

export interface ConsentDocument {
  id: number; doc_key: string; title: string; body: string;
  sort_order: number; version: number; requires_signature: boolean;
}

export const consentsApi = {
  getPending: () =>
    api.get<{ complete: boolean; pending: ConsentDocument[] }>('/api/consents/pending'),
  sign: (documentId: number, signatureImage: string) =>
    api.post<{ complete: boolean; pending_count: number }>('/api/consents/sign',
      { document_id: documentId, signature_image: signatureImage }),
  getDocument: (docKey: string) =>
    api.get<{ document: ConsentDocument }>(`/api/consents/documents/${docKey}`),
  listDocuments: () =>
    api.get<{ documents: (ConsentDocument & { is_active: boolean; is_mandatory: boolean })[] }>(
      '/api/consents/documents'),
  createDocument: (p: Partial<ConsentDocument> & { doc_key: string; title: string }) =>
    api.post('/api/consents/documents', p),
  updateDocument: (id: number, p: Partial<ConsentDocument> & { is_active?: boolean }) =>
    api.put(`/api/consents/documents/${id}`, p),
  getCompliance: (status?: 'pending') =>
    api.get<{ compliance: any[] }>(`/api/consents/compliance${status ? `?status=${status}` : ''}`),
};
```

*(Match the actual export/verb names in `src/api/auth.ts` — e.g. if the project uses `apiClient.get`, use that.)*

- [ ] **Step 2: Add the hook**

```ts
// jarvis/frontend/src/hooks/useConsents.ts
import { useQuery, useMutation } from '@tanstack/react-query';
import { consentsApi } from '@/api/consents';

export function usePendingConsents(enabled: boolean) {
  return useQuery({ queryKey: ['consents', 'pending'], queryFn: consentsApi.getPending, enabled });
}
export function useSignConsent() {
  return useMutation({
    mutationFn: (v: { documentId: number; signatureImage: string }) =>
      consentsApi.sign(v.documentId, v.signatureImage),
  });
}
```

*(If the web app uses Zustand + manual fetch instead of TanStack Query for auth, mirror that pattern — check `src/hooks/useAuth.ts`.)*

- [ ] **Step 3: Add the `User` type fields** — `consents_complete?: boolean; pending_consents_count?: number`.

- [ ] **Step 4: Verify build**

Run: `cd jarvis/frontend && npm run build`
Expected: 0 TS errors.

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/api/consents.ts jarvis/frontend/src/hooks/useConsents.ts jarvis/frontend/src/types/
git commit -m "feat(consents): web API client + hook + User type fields"
```

---

### Task 7: `<ConsentGate/>` blocker component (the stepper)

**Files:**
- Create: `jarvis/frontend/src/components/consents/ConsentGate.tsx`
- Create: `jarvis/frontend/src/components/consents/ConsentDocumentStep.tsx`

**Interfaces:**
- Consumes: `usePendingConsents`, `useSignConsent`, `SignatureCanvas` (`components/shared/SignatureCanvas.tsx`, `onSave: (pngDataUrl: string) => void`), `useAuth().refetch` (to clear the gate after last sign), a logout action.
- Produces: `<ConsentGate onAllSigned={() => void} />` — full-screen; renders nothing-mounts-behind until complete.

- [ ] **Step 1: Implement `ConsentDocumentStep.tsx`**

```tsx
// jarvis/frontend/src/components/consents/ConsentDocumentStep.tsx
import { useRef, useState } from 'react';
import SignatureCanvas from '@/components/shared/SignatureCanvas';
import type { ConsentDocument } from '@/api/consents';

export function ConsentDocumentStep({
  doc, index, total, onSign, submitting,
}: {
  doc: ConsentDocument; index: number; total: number;
  onSign: (signaturePng: string) => void; submitting: boolean;
}) {
  const [scrolledEnd, setScrolledEnd] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const [sig, setSig] = useState<string>('');
  const bodyRef = useRef<HTMLDivElement>(null);

  const onScroll = () => {
    const el = bodyRef.current; if (!el) return;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 24) setScrolledEnd(true);
  };
  const canSubmit = agreed && !!sig && !submitting;

  return (
    <div className="flex h-full flex-col">
      <div className="px-6 pt-6">
        <p className="text-xs font-medium text-muted-foreground">Document {index + 1} din {total}</p>
        <h2 className="mt-1 text-lg font-semibold">{doc.title}</h2>
      </div>
      <div ref={bodyRef} onScroll={onScroll}
           className="mx-6 my-4 flex-1 overflow-y-auto whitespace-pre-wrap rounded-md border bg-muted/30 p-4 text-sm leading-relaxed">
        {doc.body}
      </div>
      <div className="border-t px-6 py-4 space-y-3">
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" disabled={!scrolledEnd}
                 checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
          <span>Am citit și sunt de acord cu „{doc.title}".
            {!scrolledEnd && <em className="block text-xs text-muted-foreground">Derulați până la final pentru a continua.</em>}
          </span>
        </label>
        <div className="rounded-md border p-2">
          <SignatureCanvas onSave={setSig} />
        </div>
        <button disabled={!canSubmit} onClick={() => onSign(sig)}
                className="w-full rounded-md bg-primary py-2 text-primary-foreground disabled:opacity-50">
          {submitting ? 'Se salvează…' : 'Semnează și continuă'}
        </button>
      </div>
    </div>
  );
}
```

*(Confirm the `SignatureCanvas` prop contract in `components/shared/SignatureCanvas.tsx` — the map shows `onSave` emitting a base64 PNG. If it exposes an imperative `getSignature()` instead, wire a "confirmă semnătura" button to capture into `sig`.)*

- [ ] **Step 2: Implement `ConsentGate.tsx`**

```tsx
// jarvis/frontend/src/components/consents/ConsentGate.tsx
import { useState } from 'react';
import { usePendingConsents, useSignConsent } from '@/hooks/useConsents';
import { useAuth } from '@/hooks/useAuth';
import { ConsentDocumentStep } from './ConsentDocumentStep';

export default function ConsentGate() {
  const { refetch: refetchUser } = useAuth();
  const { data, isLoading, refetch } = usePendingConsents(true);
  const signMut = useSignConsent();
  const [idx, setIdx] = useState(0);

  if (isLoading || !data) return <FullScreen><p>Se încarcă acordurile…</p></FullScreen>;
  const pending = data.pending;
  if (!pending.length) { refetchUser(); return null; }

  const doc = pending[idx];
  const onSign = async (signaturePng: string) => {
    const res = await signMut.mutateAsync({ documentId: doc.id, signatureImage: signaturePng });
    if (res.complete) { await refetchUser(); return; }
    if (idx + 1 < pending.length) setIdx(idx + 1);
    else { await refetch(); setIdx(0); }
  };

  return (
    <FullScreen>
      <div className="mx-auto flex h-[88vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border bg-background shadow-xl">
        <ConsentDocumentStep doc={doc} index={idx} total={pending.length}
                             onSign={onSign} submitting={signMut.isPending} />
      </div>
      <button onClick={() => (window.location.href = '/logout')}
              className="mt-3 text-sm text-muted-foreground underline">Deconectează-te</button>
    </FullScreen>
  );
}

function FullScreen({ children }: { children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-[9999] flex flex-col items-center justify-center bg-black/60 p-4">
      {children}
    </div>
  );
}
```

*(Confirm the logout URL/route used elsewhere in the web app; the map shows session logout at `auth.logout`.)*

- [ ] **Step 3: Verify build**

Run: `cd jarvis/frontend && npm run build`
Expected: 0 TS errors.

- [ ] **Step 4: Commit**

```bash
git add jarvis/frontend/src/components/consents/
git commit -m "feat(consents): web ConsentGate stepper + document step"
```

---

### Task 8: Insert the gate at the auth choke point (`Layout.tsx`)

**Files:**
- Modify: `jarvis/frontend/src/components/Layout.tsx` (right after the `if (!user) → /login` redirect, before `<Outlet/>`)

**Interfaces:**
- Consumes: `user.consents_complete` from `useAuth`; `<ConsentGate/>`.

- [ ] **Step 1: Add the gate check**

```tsx
import ConsentGate from '@/components/consents/ConsentGate';
// ...after: if (!user) { window.location.href = '/login'; return null; }
if (user.consents_complete === false) {
  return <ConsentGate />;
}
```

*(Use `=== false` so an older cached `user` without the field, or a still-loading value, never blocks; the backend defaults to `true` when nothing is active.)*

- [ ] **Step 2: Verify build**

Run: `cd jarvis/frontend && npm run build`
Expected: 0 TS errors.

- [ ] **Step 3: Manual/Playwright verification** (webapp-testing skill; local backend + Vite)

Concrete check:
1. In local dev DB, activate the docs: `psql postgresql://localhost/defaultdb -c "UPDATE consent_documents SET is_active=TRUE;"` and clear any signatures for your test user: `... -c "DELETE FROM user_consent_signatures WHERE user_id=<me>;"`
2. Log in as that user → expect the full-screen gate, "Document 1 din 3", no access to Hub/Dashboard.
3. Sign all three → app renders; refresh → no gate.
4. Revert: `psql ... -c "UPDATE consent_documents SET is_active=FALSE;"`

- [ ] **Step 4: Commit**

```bash
git add jarvis/frontend/src/components/Layout.tsx
git commit -m "feat(consents): block app until consents_complete (covers Hub + all /app)"
```

---

### Task 9: Re-read route `/app/acorduri` + `/app/acord/:docKey`

**Files:**
- Create: `jarvis/frontend/src/pages/Consents/AcorduriPage.tsx` (list of the user's signed docs + links)
- Create: `jarvis/frontend/src/pages/Consents/AcordViewer.tsx` (single read-only doc)
- Modify: `jarvis/frontend/src/App.tsx` (add the two routes under the `/app` layout, lazy-imported like siblings)

**Interfaces:**
- Consumes: `consentsApi.getDocument(docKey)`, `consentsApi.getCompliance` is NOT used here; a small `GET /api/consents/pending`-style "my signed docs" is unnecessary — the viewer fetches by key. List page renders the active docs the user can re-read.

- [ ] **Step 1: Implement `AcordViewer.tsx`**

```tsx
// jarvis/frontend/src/pages/Consents/AcordViewer.tsx
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { consentsApi } from '@/api/consents';

export default function AcordViewer() {
  const { docKey = '' } = useParams();
  const { data, isLoading } = useQuery({
    queryKey: ['consent-doc', docKey],
    queryFn: () => consentsApi.getDocument(docKey),
  });
  if (isLoading) return <p className="p-6">Se încarcă…</p>;
  const doc = data?.document;
  if (!doc) return <p className="p-6">Document indisponibil.</p>;
  return (
    <div className="mx-auto max-w-2xl p-6">
      <h1 className="text-xl font-semibold">{doc.title}</h1>
      <div className="mt-4 whitespace-pre-wrap text-sm leading-relaxed">{doc.body}</div>
    </div>
  );
}
```

- [ ] **Step 2: Implement `AcorduriPage.tsx`** — lists the three docs with links to `/app/acord/:docKey` (fetch keys from `consentsApi.listDocuments` if the user has settings access, else hardcode the three known keys with titles from `getDocument`). Simplest correct v1: render three `<Link>`s to `data_usage`/`gdpr`/`nda`.

```tsx
// jarvis/frontend/src/pages/Consents/AcorduriPage.tsx
import { Link } from 'react-router-dom';
const DOCS = [
  { key: 'data_usage', label: 'Acord privind utilizarea datelor de contact' },
  { key: 'gdpr', label: 'Notă de informare și acord GDPR' },
  { key: 'nda', label: 'Acord de confidențialitate (NDA)' },
];
export default function AcorduriPage() {
  return (
    <div className="mx-auto max-w-2xl p-6">
      <h1 className="text-xl font-semibold">Acordurile mele</h1>
      <ul className="mt-4 space-y-2">
        {DOCS.map((d) => (
          <li key={d.key}>
            <Link className="text-primary underline" to={`/app/acord/${d.key}`}>{d.label}</Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 3: Register routes in `App.tsx`** under the `/app` layout (lazy import, matching sibling route style):

```tsx
<Route path="acorduri" element={<AcorduriPage />} />
<Route path="acord/:docKey" element={<AcordViewer />} />
```

- [ ] **Step 4: Verify build + click-through**

Run: `cd jarvis/frontend && npm run build` → 0 errors. Navigate to `/app/acorduri`, open each doc.

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/pages/Consents/ jarvis/frontend/src/App.tsx
git commit -m "feat(consents): read-only acorduri routes"
```

---

### Task 10: Settings editor tab ("Acorduri — documente legale")

**Files:**
- Create: `jarvis/frontend/src/pages/Settings/ConsentsTab.tsx`
- Modify: the Settings page tab list (locate the Settings container, e.g. `src/pages/Settings/index.tsx`) to add the tab, gated on settings access

**Interfaces:**
- Consumes: `consentsApi.listDocuments`, `consentsApi.updateDocument`, `consentsApi.createDocument`.

- [ ] **Step 1: Implement `ConsentsTab.tsx`** — a list of documents with an editor (title, body `<textarea>`, `is_active` toggle, `sort_order`), Save calls `updateDocument`. Include a visible warning that editing does not force re-signing in v1.

```tsx
// jarvis/frontend/src/pages/Settings/ConsentsTab.tsx
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { consentsApi } from '@/api/consents';

export default function ConsentsTab() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ['consent-docs-all'], queryFn: consentsApi.listDocuments });
  const save = useMutation({
    mutationFn: (v: { id: number; title: string; body: string; is_active: boolean; sort_order: number }) =>
      consentsApi.updateDocument(v.id, v),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['consent-docs-all'] }),
  });
  const [draft, setDraft] = useState<Record<number, any>>({});
  const docs = data?.documents ?? [];
  return (
    <div className="space-y-6">
      <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-800">
        Editarea textului NU obligă utilizatorii care au semnat deja să semneze din nou (v1).
        Activați un document doar după validarea juridică.
      </p>
      {docs.map((d) => {
        const cur = draft[d.id] ?? { title: d.title, body: d.body, is_active: d.is_active, sort_order: d.sort_order };
        const set = (patch: any) => setDraft((s) => ({ ...s, [d.id]: { ...cur, ...patch } }));
        return (
          <div key={d.id} className="rounded-lg border p-4 space-y-2">
            <div className="flex items-center justify-between">
              <input className="w-2/3 rounded border px-2 py-1 text-sm" value={cur.title}
                     onChange={(e) => set({ title: e.target.value })} />
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={cur.is_active}
                       onChange={(e) => set({ is_active: e.target.checked })} /> Activ
              </label>
            </div>
            <textarea className="h-48 w-full rounded border p-2 font-mono text-xs" value={cur.body}
                      onChange={(e) => set({ body: e.target.value })} />
            <button className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground"
                    onClick={() => save.mutate({ id: d.id, ...cur })} disabled={save.isPending}>
              {save.isPending ? 'Se salvează…' : 'Salvează'}
            </button>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Add the tab to Settings**, gated on `user.can_access_settings`. Match the existing tab-registration pattern (label "Acorduri").

- [ ] **Step 3: Verify build + manual**

Run: `cd jarvis/frontend && npm run build` → 0 errors. As an admin, edit a body, toggle Active, Save; confirm via `psql ... "SELECT doc_key,is_active,version FROM consent_documents;"` that `version` bumped on body change.

- [ ] **Step 4: Commit**

```bash
git add jarvis/frontend/src/pages/Settings/
git commit -m "feat(consents): Settings editor tab for consent documents"
```

---

### Task 11: HR compliance dashboard

**Files:**
- Create: `jarvis/frontend/src/pages/HR/ConsentComplianceTab.tsx`
- Modify: the HR page tab container to add the tab (gated on HR access)

**Interfaces:**
- Consumes: `consentsApi.getCompliance(status?)`.

- [ ] **Step 1: Implement the tab** — a table: rows = users, columns = the three docs (✓ / — with signed date on hover), a "Doar cu acorduri lipsă" filter, CSV export.

```tsx
// jarvis/frontend/src/pages/HR/ConsentComplianceTab.tsx
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { consentsApi } from '@/api/consents';

export default function ConsentComplianceTab() {
  const [pendingOnly, setPendingOnly] = useState(false);
  const { data } = useQuery({
    queryKey: ['consent-compliance', pendingOnly],
    queryFn: () => consentsApi.getCompliance(pendingOnly ? 'pending' : undefined),
  });
  const rows = data?.compliance ?? [];
  const docKeys = rows[0]?.documents?.map((d: any) => d.doc_key) ?? ['data_usage', 'gdpr', 'nda'];
  const exportCsv = () => {
    const header = ['name', 'email', 'company', ...docKeys].join(',');
    const lines = rows.map((u: any) =>
      [u.name, u.email, u.company, ...u.documents.map((d: any) => (d.signed ? d.signed_at ?? 'da' : 'nu'))].join(','));
    const blob = new Blob([[header, ...lines].join('\n')], { type: 'text/csv' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
    a.download = 'acorduri-compliance.csv'; a.click();
  };
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-4">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={pendingOnly} onChange={(e) => setPendingOnly(e.target.checked)} />
          Doar cu acorduri lipsă
        </label>
        <button className="rounded border px-3 py-1 text-sm" onClick={exportCsv}>Export CSV</button>
      </div>
      <table className="w-full text-sm">
        <thead><tr className="border-b text-left">
          <th className="py-2">Nume</th><th>Companie</th>{docKeys.map((k: string) => <th key={k}>{k}</th>)}
        </tr></thead>
        <tbody>
          {rows.map((u: any) => (
            <tr key={u.user_id} className="border-b">
              <td className="py-1.5">{u.name}</td><td>{u.company}</td>
              {u.documents.map((d: any) => (
                <td key={d.doc_key} title={d.signed_at ?? ''}>{d.signed ? '✓' : '—'}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Add the tab to HR**, gated on `user.can_access_hr`.

- [ ] **Step 3: Verify build + manual** — sign as one user, confirm ✓ appears; filter shows only users with gaps.

- [ ] **Step 4: Commit**

```bash
git add jarvis/frontend/src/pages/HR/
git commit -m "feat(consents): HR compliance dashboard tab"
```

---

### Task 12: Profile "Acorduri semnate" section

**Files:**
- Modify: the profile page (`jarvis/frontend/src/pages/Profile/*`) to add a section listing the three docs + signed state + re-view links

**Interfaces:**
- Consumes: `consentsApi.getCompliance` is HR-gated; instead reuse the user's own signed state. Add a tiny endpoint reuse: `GET /api/consents/pending` returns what's still pending → anything not pending is signed. For a clean per-user "signed at" list, add `GET /api/consents/mine` returning the current user's signatures.

- [ ] **Step 1 (backend): add `GET /api/consents/mine`** to `routes.py`:

```python
@consents_bp.route('/api/consents/mine')
@login_required
def mine():
    rows = _svc.repo.query_all('''
        SELECT d.doc_key, d.title, s.signed_at
        FROM consent_documents d
        LEFT JOIN user_consent_signatures s
          ON s.document_id = d.id AND s.user_id = %s AND s.response = 'accepted'
        WHERE d.is_active = TRUE
        ORDER BY d.sort_order
    ''', (current_user.id,))
    return jsonify({'documents': rows})
```

*(Or add a `get_user_signatures(user_id)` method on the repository and call it — preferred over `_svc.repo.query_all` reaching through. Add `consentsApi.getMine()` to the client.)*

- [ ] **Step 2 (frontend): render the section** on the profile with each doc + `signed_at` (or "Nesemnat") + a `<Link to="/app/acord/:key">Vezi</Link>`.

- [ ] **Step 3: Verify build + manual** — profile shows "Acorduri semnate" with dates.

- [ ] **Step 4: Commit**

```bash
git add jarvis/core/consents/routes.py jarvis/frontend/src/pages/Profile/ jarvis/frontend/src/api/consents.ts
git commit -m "feat(consents): profile shows signed acorduri + re-view links"
```

---

## Phase 3 — Mobile-2 (blocker + sign). Repo: `jarvis-mobile-2`. Verified via vitest + build.

### Task 13: Mobile API hooks + `User.consents_complete`

**Files:**
- Modify: `jarvis-mobile-2/src/stores/authStore.ts` (`User` interface + `extractPermissions` to surface `consents_complete`, `pending_consents_count` from `/api/mobile/current-user`)
- Modify: `jarvis-mobile-2/src/hooks/useApi.ts` (add `usePendingConsents`, `useSignConsent`)
- Test: `jarvis-mobile-2/src/hooks/__tests__/useConsents.test.ts` (vitest, mirroring existing hook tests)

**Interfaces:**
- Produces: `usePendingConsents()` → `{data:{complete,pending[]}}`; `useSignConsent()` → mutation `({documentId, signatureImage})`; `user.consents_complete: boolean`.

- [ ] **Step 1: Write the failing vitest** (mock `apiFetch`, assert `useSignConsent` POSTs to `/api/mobile/consents/sign` with `{document_id, signature_image}`). Mirror an existing `useApi` test.

- [ ] **Step 2: Run it to confirm failure** — `cd jarvis-mobile-2 && npx vitest run src/hooks/__tests__/useConsents.test.ts`.

- [ ] **Step 3: Implement** the two hooks in `useApi.ts` (TanStack Query over `apiFetch`), and add `consents_complete`/`pending_consents_count` to the `User` interface + `extractPermissions` mapping.

- [ ] **Step 4: Run test to pass.**

- [ ] **Step 5: Commit**

```bash
git add src/hooks/useApi.ts src/stores/authStore.ts src/hooks/__tests__/useConsents.test.ts
git commit -m "feat(consents): mobile hooks + consents_complete on User"
```

---

### Task 14: Mobile `<ConsentGate/>` + `ProtectedRoute` insertion

**Files:**
- Create: `jarvis-mobile-2/src/components/consents/ConsentGate.tsx` (modeled on `src/pages/Sales/TestDrive/GdprNoticeModal.tsx`, reusing `src/components/shared/SignatureCanvas.tsx`)
- Modify: `jarvis-mobile-2/src/App.tsx` (`ProtectedRoute` — block when `isAuthenticated && user.consents_complete === false`)

**Interfaces:**
- Consumes: `usePendingConsents`, `useSignConsent`, `SignatureCanvas`, `restoreSession`/user refetch, logout.

- [ ] **Step 1: Implement the mobile gate** — full-screen stepper (same UX as web Task 7): scroll → checkbox → sign → "Semnează și continuă"; only exit = Logout. On complete, refresh the user (`restoreSession`) so the gate clears.

- [ ] **Step 2: Insert in `ProtectedRoute`** (App.tsx:50):

```tsx
if (isAuthenticated && user?.consents_complete === false) return <ConsentGate />;
```

- [ ] **Step 3: Verify** — `npx vitest run` (green) and `npm run build` (0 errors). Manual: point the app at a backend with active docs + a user with no signatures → gate shows; sign 3 → clears.

- [ ] **Step 4: Commit**

```bash
git add src/components/consents/ src/App.tsx
git commit -m "feat(consents): mobile ConsentGate blocker in ProtectedRoute"
```

---

### Task 15: Changelog + build + cap sync (mobile ship ritual)

**Files:**
- Modify: `jarvis-mobile-2/src/data/changelog.ts` (prepend a new version entry describing the mandatory acorduri gate)

- [ ] **Step 1: Prepend the changelog entry** (top of the array) with the next version and a short RO description.

- [ ] **Step 2: Build + sync**

Run: `cd jarvis-mobile-2 && npm run build && npx cap sync android`
Expected: build 0 errors; sync completes.

- [ ] **Step 3: Commit** (APK CI publishes on push per project rules)

```bash
git add src/data/changelog.ts
git commit -m "chore(consents): changelog entry for mandatory acorduri gate"
```

---

## Self-Review

**Spec coverage:**
- Blocker gate (web+Hub) → Tasks 7–8. Mobile blocker → Task 14. ✓
- 3 documents / mandatory / signature → Task 1 seed (all `is_mandatory`, `requires_signature`), enforced in Tasks 3 (`sign`), 7/14 (UI). ✓
- Admin-editable text → Task 10 (+ routes Task 4). ✓
- HR compliance dashboard → Task 11 (+ route Task 4). ✓
- Re-read route ("route to the acord") → Task 9. ✓
- Profile visibility → Task 12. ✓
- `consents_complete` gate signal → Task 5. ✓
- Sign-once, no re-sign on edit → enforced by `UNIQUE(user_id,document_id)` + gate checks existence not version (Tasks 1, 3); admin warning surfaced (Task 10). ✓
- Audit (ip/ua/hash/version) → Tasks 1, 3, 4. ✓
- Rollout safeguard (`is_active=FALSE`) → Task 1 seed. ✓
- Placeholder legal text, no invented binding text → Task 1 constants. ✓

**Placeholder scan:** No `TODO`/"add error handling"/"similar to Task N" — every code step is concrete. The only intentional `‹DE COMPLETAT›` markers are the legal-copy placeholders (by design). Two flagged confirmations remain, both surfaced as explicit notes, not silent gaps: (a) `execute(returning=True)` return shape — Task 2 Step 4; (b) v2 permission seed entity names for `consents` — Task 4 Step 4.

**Type consistency:** `ConsentDocument`, `consents_complete`/`pending_consents_count`, `sign(document_id, signature_image)` → `{complete, pending_count}`, and repository/service method names are used identically across backend Tasks 2–5 and frontend Tasks 6–14. ✓

## Open confirmations before execution
1. **Base branch** — `staging` (CLAUDE.md default; held by user).
2. **v2 permission entities** — confirm `('settings','consents','view'/'edit')` and `('hr','consents','view')` seed location, or swap to reuse existing `settings`/`hr` module-access booleans.
3. **Mobile auth decorator** — confirm `/api/mobile/consents/*` uses the same guard as `/api/mobile/current-user` (JWT→session bridge makes `@login_required` valid).
