# DMS Intelligence Layer — Implementation Plan

## Overview

Extends the existing DMS module (Core: 100% done) with 6 phases of intelligence features:
signatures, party mapping, Google Drive sync, WML extraction, RAG integration, and UI polish.

**Source Specs:**
- `docs/JARVIS_DMS_Intelligence_Layer.docx` (6-phase technical spec)
- `docs/JARVIS_DMS_CLAUDE_CODE_MASTER_PROMPT.md` (9-agent orchestration framework — aspirational)

---

## Current State (What's Built)

### Core DMS — 100% Complete
| Component | Details |
|-----------|---------|
| **Tables** | `dms_categories`, `dms_documents`, `dms_files`, `dms_relationship_types` |
| **Backend** | 4 repositories, 1 service (`DocumentService`), 4 route files (21 endpoints) |
| **Frontend** | 4 pages: `index.tsx`, `DocumentDetail.tsx`, `UploadDialog.tsx`, `CategoryManager.tsx` |
| **Features** | Full CRUD, parent/child hierarchy, dynamic categories + relationship types, file upload (local+Drive), company isolation, column preferences, pagination, search, expiry dates |

### Existing Columns in `dms_documents` (relevant to spec)
- `doc_number TEXT`, `doc_date DATE`, `expiry_date DATE`, `notify_user_id INTEGER`
- `metadata JSONB` — available for signature status, party data, etc.
- `status TEXT` — draft/active/archived (spec wants to add: signed, pending_signature, expired)

### Existing RAG Infrastructure
- `RAGSourceType` enum in `jarvis/ai_agent/models.py` (15 types, no DMS yet)
- `METADATA_DISPLAY_KEYS` in `rag_service.py` for formatted context
- Batch indexing pattern established (see CRM implementation)

---

## Phase A: Digital Signatures — 0% Done

### Goal
Wire external signature service (e.g. DocuSign, ValidSign) callbacks to track signature status on documents.

### Database Changes
**Add columns to `dms_documents`:**
```sql
ALTER TABLE dms_documents ADD COLUMN signature_status TEXT DEFAULT NULL;
-- Values: NULL (no sig), 'pending', 'sent', 'signed', 'declined', 'expired'

ALTER TABLE dms_documents ADD COLUMN signature_request_id TEXT;
ALTER TABLE dms_documents ADD COLUMN signature_requested_at TIMESTAMP;
ALTER TABLE dms_documents ADD COLUMN signature_completed_at TIMESTAMP;
ALTER TABLE dms_documents ADD COLUMN signature_provider TEXT;
-- Values: 'docusign', 'validsign', 'manual'
```

**Add index:**
```sql
CREATE INDEX idx_dms_documents_sig_status ON dms_documents(signature_status)
    WHERE signature_status IS NOT NULL;
```

### New Files
| File | Purpose |
|------|---------|
| `jarvis/dms/services/signature_service.py` | Signature provider abstraction — send for signature, check status, handle callback |
| `jarvis/dms/routes/signatures.py` | Webhook callbacks from signature providers + manual status update endpoint |

### API Endpoints
| Method | Path | Action |
|--------|------|--------|
| POST | `/api/dms/documents/:id/request-signature` | Send document for signing |
| POST | `/api/dms/webhooks/signature` | Callback from provider |
| PUT | `/api/dms/documents/:id/signature-status` | Manual status update (admin) |
| GET | `/api/dms/documents/pending-signatures` | List all pending signatures |

### Frontend Changes
- `DocumentDetail.tsx`: Add signature status badge + "Request Signature" button
- `index.tsx`: Add signature_status column to table, filter by status
- New component: `SignatureStatusBadge.tsx`

### Blockers
- **Signature service provider** not yet chosen (DocuSign? ValidSign? manual-only first?)
- Recommend: Start with `manual` provider (admin sets status), wire real providers later

### Priority: LOW (start with manual mode)

---

## Phase B: Party Mapping & Enriched List — 15% Done

### What Exists
- `expiry_date`, `doc_date` columns already on `dms_documents`
- `notify_user_id` for expiry alerts

### What's Missing

#### New Table: `document_parties`
```sql
CREATE TABLE IF NOT EXISTS document_parties (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES dms_documents(id) ON DELETE CASCADE,
    party_role TEXT NOT NULL,
    -- Values: 'emitent' (issuer), 'beneficiar' (beneficiary), 'semnatar' (signatory), 'furnizor' (supplier), 'client'
    entity_type TEXT NOT NULL DEFAULT 'company',
    -- Values: 'company', 'person', 'external'
    entity_id INTEGER,
    -- FK to companies(id) or users(id) depending on entity_type
    entity_name TEXT NOT NULL,
    -- Denormalized for display (e.g. "SC Workleto SRL")
    entity_details JSONB DEFAULT '{}'::jsonb,
    -- Extra: CUI, address, contact person, etc.
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_document_parties_doc ON document_parties(document_id);
CREATE INDEX idx_document_parties_entity ON document_parties(entity_type, entity_id);
```

#### New Files
| File | Purpose |
|------|---------|
| `jarvis/dms/repositories/party_repository.py` | CRUD for document_parties |
| `jarvis/dms/routes/parties.py` | Party management endpoints |

#### API Endpoints
| Method | Path | Action |
|--------|------|--------|
| GET | `/api/dms/documents/:id/parties` | List parties for document |
| POST | `/api/dms/documents/:id/parties` | Add party to document |
| PUT | `/api/dms/parties/:id` | Update party |
| DELETE | `/api/dms/parties/:id` | Remove party |
| GET | `/api/dms/parties/suggest?q=...` | Auto-suggest from companies/contacts |

#### Enriched List SQL
The spec defines a mega-query with 18+ computed columns via LATERAL JOINs. Simplified version:
```sql
SELECT
    d.*,
    c.name AS category_name,
    c.icon AS category_icon,
    c.color AS category_color,
    u.full_name AS created_by_name,
    comp.name AS company_name,
    -- File count
    (SELECT COUNT(*) FROM dms_files f WHERE f.document_id = d.id) AS file_count,
    -- Child count
    (SELECT COUNT(*) FROM dms_documents ch WHERE ch.parent_id = d.id AND ch.deleted_at IS NULL) AS child_count,
    -- Primary party (first issuer)
    (SELECT entity_name FROM document_parties p WHERE p.document_id = d.id AND p.party_role = 'emitent' ORDER BY sort_order LIMIT 1) AS issuer_name,
    -- Days until expiry
    CASE WHEN d.expiry_date IS NOT NULL THEN d.expiry_date - CURRENT_DATE END AS days_until_expiry,
    -- Signature status display
    COALESCE(d.signature_status, 'none') AS sig_status
FROM dms_documents d
LEFT JOIN dms_categories c ON c.id = d.category_id
LEFT JOIN users u ON u.id = d.created_by
LEFT JOIN companies comp ON comp.id = d.company_id
WHERE d.deleted_at IS NULL AND d.parent_id IS NULL
```

**Performance note:** Add `file_count` and `child_count` as cached columns on `dms_documents` if LATERAL joins become slow (>50ms on 10K+ docs). Increment/decrement via triggers or service layer.

#### Supplier Sync
- Auto-create parties from e-factura supplier data when document is linked
- Endpoint: `POST /api/dms/documents/:id/sync-supplier` — pulls from `efactura_invoices` table

#### Frontend Changes
- `DocumentDetail.tsx`: Add "Parties" tab showing linked entities
- `index.tsx`: Show issuer_name, file_count, child_count in table columns
- New component: `PartyEditor.tsx` — inline add/edit parties with company autocomplete

### Priority: MEDIUM

---

## Phase C: Google Drive Structured Sync — 0% Done

### Goal
Two-way sync between DMS documents and a structured Google Drive folder hierarchy:
`Company / Category / Document Title / files`

### Prerequisites
- **Google service account** with Drive API access (not yet configured)
- `GOOGLE_SERVICE_ACCOUNT_JSON` env var or secret
- Shared Drive or folder ID as root

### New Table: `dms_drive_sync`
```sql
CREATE TABLE IF NOT EXISTS dms_drive_sync (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES dms_documents(id) ON DELETE CASCADE,
    drive_folder_id TEXT NOT NULL,
    drive_folder_url TEXT,
    last_synced_at TIMESTAMP,
    sync_status TEXT DEFAULT 'pending',
    -- Values: 'pending', 'synced', 'error', 'deleted'
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_id)
);
```

### New Files
| File | Purpose |
|------|---------|
| `jarvis/dms/services/drive_sync_service.py` | Folder creation, file upload/download, webhook registration |
| `jarvis/dms/routes/drive_sync.py` | Sync triggers + webhook handler |

### API Endpoints
| Method | Path | Action |
|--------|------|--------|
| POST | `/api/dms/documents/:id/sync-drive` | Create Drive folder + upload files |
| POST | `/api/dms/webhooks/drive` | Google Drive push notification handler |
| GET | `/api/dms/drive-sync/status` | Overall sync health |
| POST | `/api/dms/drive-sync/batch` | Sync multiple documents |

### Drive Folder Structure
```
JARVIS DMS Root/
├── Workleto SRL/
│   ├── Contracte/
│   │   ├── Contract #001 - Servicii IT/
│   │   │   ├── contract_principal.pdf
│   │   │   └── anexa_1.pdf
│   │   └── Contract #002 - Mentenanta/
│   └── Facturi/
├── Toyota Romania/
│   └── ...
```

### Frontend Changes
- `DocumentDetail.tsx`: "Sync to Drive" button, Drive folder link
- Settings page: Google Drive configuration (root folder ID, service account status)

### Blockers
- **Google service account not provisioned** — need credentials JSON
- Need to decide: Service Account vs OAuth2 user consent flow
- Recommend: Service Account (server-to-server, no user interaction)

### Priority: LOW (blocked by infrastructure)

---

## Phase D: WML/OOXML Extraction — 0% Done

### Goal
Extract structured content from .docx/.xlsx files (WordprocessingML) for search and AI context.

### New Tables
```sql
CREATE TABLE IF NOT EXISTS document_wml (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES dms_documents(id) ON DELETE CASCADE,
    file_id INTEGER NOT NULL REFERENCES dms_files(id) ON DELETE CASCADE,
    raw_text TEXT,
    structured_json JSONB,
    -- Parsed headings, paragraphs, tables as structured data
    extraction_method TEXT DEFAULT 'mammoth',
    -- Values: 'mammoth', 'python-docx', 'openpyxl', 'pdfplumber'
    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(file_id)
);

CREATE TABLE IF NOT EXISTS document_wml_chunks (
    id SERIAL PRIMARY KEY,
    wml_id INTEGER NOT NULL REFERENCES document_wml(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    heading TEXT,
    content TEXT NOT NULL,
    token_count INTEGER,
    embedding VECTOR(1536),
    -- pgvector for semantic search (requires pgvector extension)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_wml_chunks_embedding ON document_wml_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_wml_document ON document_wml(document_id);
CREATE INDEX idx_wml_file ON document_wml(file_id);
```

### New Files
| File | Purpose |
|------|---------|
| `jarvis/dms/services/wml_extraction_service.py` | Parse .docx (mammoth/python-docx), .xlsx (openpyxl), .pdf (pdfplumber) |
| `jarvis/dms/services/chunking_service.py` | Split extracted text at heading boundaries, compute token counts |

### Extraction Pipeline
1. File uploaded → trigger extraction (async if Celery available, sync otherwise)
2. Parse document → store `raw_text` + `structured_json` in `document_wml`
3. Chunk by headings → store chunks in `document_wml_chunks`
4. Generate embeddings → store in `embedding` column (Phase E dependency)

### Supported Formats
| Format | Library | Method |
|--------|---------|--------|
| .docx | mammoth | HTML→text, preserve headings |
| .xlsx | openpyxl | Sheet→rows→text, header detection |
| .pdf | pdfplumber | Page→text extraction |
| .txt/.csv | built-in | Direct read |

### Dependencies
- `pip install mammoth python-docx openpyxl pdfplumber`
- **pgvector extension** on PostgreSQL (for embedding column)
- OpenAI/Anthropic embeddings API key (for vector generation)

### Priority: MEDIUM-HIGH (enables RAG)

---

## Phase E: RAG Integration — 0% Done

### Goal
Make DMS documents searchable by the AI agent via the existing RAG infrastructure.

### RAG Source Type
Add to `jarvis/ai_agent/models.py`:
```python
class RAGSourceType(Enum):
    ...
    DMS_DOCUMENT = "dms_document"
    DMS_CHUNK = "dms_chunk"
```

### New Indexing Methods in `rag_service.py`

#### Option 1: Full Document Index (no pgvector needed)
```python
def index_dms_document(self, doc_id):
    """Index a DMS document as a RAG source."""
    doc = _doc_repo.get_by_id(doc_id)
    # Content: title + description + metadata + party names + file text excerpts
    content = f"Document: {doc['title']}\nCategory: {cat_name}\nCompany: {company_name}\n..."
    metadata = {
        'doc_number': doc['doc_number'],
        'category': cat_name,
        'company': company_name,
        'status': doc['status'],
        'expiry_date': str(doc['expiry_date']),
        'parties': [p['entity_name'] for p in parties],
    }
    self._upsert_rag_source(
        source_type=RAGSourceType.DMS_DOCUMENT,
        source_id=str(doc_id),
        content=content,
        metadata=metadata,
        company_id=doc['company_id'],
    )
```

#### Option 2: Chunk-Level Index (requires pgvector — Phase D)
```python
def index_dms_chunks(self, doc_id):
    """Index WML chunks for semantic search."""
    chunks = _wml_repo.get_chunks_by_document(doc_id)
    for chunk in chunks:
        embedding = self._generate_embedding(chunk['content'])
        # Store in document_wml_chunks.embedding
```

### New AI Tool
Add to `jarvis/ai_agent/tools/definitions/dms.py`:
```python
SEARCH_DMS_DOCUMENTS = {
    "name": "search_dms_documents",
    "description": "Search DMS documents by title, content, category, company, status, date range, parties",
    "parameters": {
        "query": {"type": "string", "description": "Search text"},
        "category": {"type": "string", "description": "Category slug filter"},
        "company_id": {"type": "integer", "description": "Company filter"},
        "status": {"type": "string", "description": "Document status filter"},
        "date_from": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
        "date_to": {"type": "string", "description": "End date (YYYY-MM-DD)"},
        "has_expiry": {"type": "boolean", "description": "Filter documents with expiry dates"},
    }
}
```

### DMS System Prompt Extension
Add to AI agent's system prompt when user has DMS permission:
```
You have access to the Document Management System (DMS). You can search documents by title,
category, company, status, date range, and parties. Documents may have child documents
(annexes, estimates, proofs). Use search_dms_documents to find relevant documents.
```

### METADATA_DISPLAY_KEYS Addition
```python
'dms_document': [
    ('doc_number', 'Nr. Doc'), ('category', 'Categorie'), ('company', 'Companie'),
    ('status', 'Status'), ('expiry_date', 'Expira'), ('parties', 'Parti'),
],
```

### Implementation Strategy
- **Phase E.1** (no new dependencies): Index documents using existing RAG table (`ai_agent_rag_sources`) — keyword search only. This works TODAY.
- **Phase E.2** (requires pgvector): Enable semantic/vector search via `document_wml_chunks.embedding` column.

### Priority: HIGH (Phase E.1 is easy win, E.2 requires Phase D)

---

## Phase F: UI Polish — 20% Done

### What Exists
- Column preferences (show/hide/reorder)
- Basic responsive layout

### What's Missing

#### Skeleton Loading States
- `DocumentListSkeleton.tsx` — shimmer rows while loading
- `DocumentDetailSkeleton.tsx` — shimmer for detail view

#### Mobile Responsive
- Swipeable document cards on mobile
- Bottom sheet for filters instead of sidebar
- Touch-friendly file preview

#### Batch Operations
- Multi-select documents → batch archive/delete/move category
- Bulk export (zip download)

#### Advanced Filters
- Date range picker for `doc_date` and `expiry_date`
- Multi-select category filter
- Company filter (admin: cross-company)
- Status filter pills
- Saved filter presets

#### Document Timeline
- Activity log per document (created, edited, file added, signed, etc.)
- Visual timeline in `DocumentDetail.tsx`

#### Print/Export
- Print-friendly document summary
- PDF export of document metadata + file list

### Priority: LOW (incremental improvements)

---

## Implementation Order (Recommended)

| Step | Phase | Effort | Dependencies | Impact |
|------|-------|--------|-------------|--------|
| 1 | **E.1 — RAG (keyword)** | 1 day | None | AI can search DMS docs |
| 2 | **B — Party Mapping** | 2 days | None | Enriched document context |
| 3 | **A — Signatures (manual)** | 1 day | None | Track signing status |
| 4 | **D — WML Extraction** | 2-3 days | mammoth, pdfplumber | Extract file content |
| 5 | **E.2 — RAG (semantic)** | 1-2 days | Phase D + pgvector | Semantic search |
| 6 | **F — UI Polish** | 2-3 days | None | Better UX |
| 7 | **C — Google Drive** | 2-3 days | Service account | Structured sync |

**Total estimate: ~12-16 days of implementation**

---

## Infrastructure Blockers

| Blocker | Required For | Resolution |
|---------|-------------|------------|
| pgvector PostgreSQL extension | Phase D+E.2 (embeddings) | `CREATE EXTENSION vector;` on staging DB — needs superuser |
| Google service account JSON | Phase C (Drive sync) | Provision in Google Cloud Console, store as env var |
| Embedding API key | Phase E.2 (vector search) | OpenAI `text-embedding-3-small` or use existing Anthropic key |
| Celery + Redis | Phase D async extraction | Optional — can do sync extraction first, add async later |
| mammoth + pdfplumber packages | Phase D | `pip install mammoth pdfplumber python-docx` |

---

## Files Inventory

### Existing (modify)
| File | Changes |
|------|---------|
| `jarvis/database.py` | Add `document_parties`, `dms_drive_sync`, `document_wml`, `document_wml_chunks` tables; add signature columns to `dms_documents` |
| `jarvis/ai_agent/models.py` | Add `DMS_DOCUMENT`, `DMS_CHUNK` to `RAGSourceType` |
| `jarvis/ai_agent/services/rag_service.py` | Add `index_dms_document()`, `index_dms_documents_batch()`, `METADATA_DISPLAY_KEYS['dms_document']` |
| `jarvis/frontend/src/pages/Dms/DocumentDetail.tsx` | Parties tab, signature badge, Drive sync button, timeline |
| `jarvis/frontend/src/pages/Dms/index.tsx` | Enriched columns, advanced filters, skeleton loading, batch operations |
| `jarvis/frontend/src/types/dms.ts` | Add `DmsParty`, `DmsSignatureStatus`, `DmsDriveSync` interfaces |
| `jarvis/frontend/src/api/dms.ts` | Add party, signature, drive-sync, RAG API methods |

### New (create)
| File | Phase |
|------|-------|
| `jarvis/dms/repositories/party_repository.py` | B |
| `jarvis/dms/routes/parties.py` | B |
| `jarvis/dms/services/signature_service.py` | A |
| `jarvis/dms/routes/signatures.py` | A |
| `jarvis/dms/services/drive_sync_service.py` | C |
| `jarvis/dms/routes/drive_sync.py` | C |
| `jarvis/dms/services/wml_extraction_service.py` | D |
| `jarvis/dms/services/chunking_service.py` | D |
| `jarvis/ai_agent/tools/definitions/dms.py` | E |
| `jarvis/frontend/src/pages/Dms/PartyEditor.tsx` | B |
| `jarvis/frontend/src/pages/Dms/SignatureStatusBadge.tsx` | A |
| `jarvis/frontend/src/pages/Dms/DocumentListSkeleton.tsx` | F |

---

## Status Tracking

| Phase | Status | Notes |
|-------|--------|-------|
| Core DMS | DONE | 4 tables, 21 endpoints, full CRUD |
| A — Signatures | DONE | Manual mode: 5 columns, 2 endpoints, frontend badge+edit |
| B — Party Mapping | DONE | document_parties table, 5 endpoints, frontend inline CRUD |
| C — Google Drive | DONE | dms_drive_sync table, DriveSyncService, 4 endpoints, frontend sync UI |
| D — WML Extraction | DONE | 2 tables, extraction service (docx/pdf/xlsx), 3 endpoints, chunking |
| E.1 — RAG (keyword) | DONE | DMS_DOCUMENT source type, 3 AI tools, batch indexing |
| E.2 — RAG (semantic) | DONE | search_dms_content tool (FTS on chunks) |
| F — UI Polish | DONE | Types, API methods, parties/signatures/extraction UI in DocumentDetail |

### Files Created This Session
| File | Phase |
|------|-------|
| `jarvis/dms/repositories/party_repository.py` | B |
| `jarvis/dms/repositories/wml_repository.py` | D |
| `jarvis/dms/routes/parties.py` | B |
| `jarvis/dms/routes/signatures.py` | A |
| `jarvis/dms/routes/extraction.py` | D |
| `jarvis/dms/services/wml_extraction_service.py` | D |
| `jarvis/ai_agent/tools/definitions/dms.py` | E |

### Files Modified This Session
| File | Changes |
|------|---------|
| `jarvis/database.py` | +3 tables, +5 columns on dms_documents, +6 indexes |
| `jarvis/ai_agent/models.py` | +DMS_DOCUMENT to RAGSourceType |
| `jarvis/ai_agent/services/rag_service.py` | +DMS indexing methods, +metadata keys |
| `jarvis/ai_agent/tools/definitions/__init__.py` | +dms import |
| `jarvis/dms/__init__.py` | +parties, signatures, extraction route imports |
| `jarvis/dms/repositories/__init__.py` | +PartyRepository, WmlRepository exports |
| `jarvis/frontend/src/types/dms.ts` | +DmsParty, DmsSignatureStatus, DmsWmlExtraction, DmsWmlChunk |
| `jarvis/frontend/src/api/dms.ts` | +13 API methods (parties, signatures, extraction) |
| `jarvis/frontend/src/pages/Dms/DocumentDetail.tsx` | +parties section, +sig badge, +extraction section |
| `jarvis/frontend/src/pages/Dms/index.tsx` | +sig badge in expanded row |

### Post-Deep-Test Fixes Applied
| Issue | Severity | Fix |
|-------|----------|-----|
| Frontend API path mismatch | CRITICAL | Changed backend routes to `/api/documents/...` pattern (parties, signatures, extraction) + fixed frontend standalone party paths |
| Extraction response key mismatch | CRITICAL | Backend now returns `extractions` instead of `extracted` |
| S-01: Missing company isolation on extraction routes | CRITICAL | Added `_check_doc_access()` with company_id check to all 3 extraction endpoints |
| S-02: No company isolation on AI agent DMS tools | CRITICAL | Added `_get_user_company_id()` helper, all 4 AI tools now filter by user's company |
| P-01: No GIN index for FTS on document_wml_chunks | CRITICAL | Added `idx_wml_chunks_fts` GIN index in database.py |
| S-03: No validation on entity_id, entity_details, sort_order | HIGH | Added type + range validation on both create and update party routes |
| S-04: No length check on signature_request_id | HIGH | Capped at 255 chars |
| S-05: Party suggest leaks cross-company data | HIGH | `suggest()` now accepts and filters by `company_id` |
| S-06: ILIKE unescaped wildcards | HIGH | Escaped `%` and `_` in suggest query |
| S-07: str(e) exposed in extraction errors | MEDIUM | Replaced with generic "Extraction failed" message |
| A-03: success:true even when all files fail | MEDIUM | Now returns `success: len(results) > 0 or len(errors) == 0` |
| P-02: N individual INSERTs for chunks | MEDIUM | Replaced with `execute_values()` batch insert |
| P-05: No LIMIT on pending signatures | MEDIUM | Added `LIMIT 100` |
| Deprecated datetime.utcnow() | HINT | Changed to `datetime.now(timezone.utc)` |
| Unused imports | HINT | Removed `safe_error_response`, `request` where unused |

*Last updated: 2026-02-27*
