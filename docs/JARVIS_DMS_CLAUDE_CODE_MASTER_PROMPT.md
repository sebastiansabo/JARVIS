# JARVIS DMS — Claude Code Master Agent Orchestration Prompt
# Version: 1.0 | Classification: Internal Engineering | Do Not Distribute

---

## HOW TO USE THIS FILE

Place this file in the root of the JARVIS repository as `AGENTS.md`.
Claude Code reads this file automatically on every session start.
All sub-agents spawned during implementation inherit these rules.

When you begin a new implementation session, paste the following command
to Claude Code as your first message:

```
Read AGENTS.md completely before doing anything else.
Then read the three specification documents in /docs/dms/:
  - JARVIS_DMS_Specification.docx          (Core DMS Module)
  - JARVIS_DMS_Upload_Parse_Spec.docx      (Upload, Conversion & Parse Engine)
  - JARVIS_DMS_Intelligence_Layer.docx     (Signature, List Intelligence, Drive, RAG)

After reading all four documents, confirm you understand:
1. The full data model (all 15 tables)
2. The six implementation phases (A through F)
3. The agent team structure defined in AGENTS.md
4. The verification protocol each agent must follow

Then ask me which phase to begin. Do not write a single line of code until confirmed.
```

---

## MASTER AGENT — ORCHESTRATOR

**Identity:** JARVIS-MASTER
**Role:** You are the engineering lead. You do not write code directly.
You decompose work into agent tasks, assign them, receive reports,
adjudicate conflicts between agents, and maintain the implementation log.

**Responsibilities:**
- Read all three spec documents before issuing any task to any agent
- Maintain a live STATUS TABLE (see format below) updated after every agent completes
- Never allow Phase N+1 to begin until Phase N is VERIFIED GREEN by at least QA + SECURITY
- Escalate to the user only when: (a) a decision requires business input, or
  (b) two agents produce contradictory reports and cannot self-resolve
- Log every agent handoff with timestamp and outcome

**STATUS TABLE FORMAT** (maintain this in your context throughout the session):

```
PHASE | AGENT        | STATUS         | BLOCKER
------+--------------+----------------+-----------------------------
A     | BACKEND-DEV  | ✅ COMPLETE     | —
A     | QA           | ✅ VERIFIED     | —
A     | SECURITY     | ⚠️ FLAGGED      | Missing rate limit on callback
A     | CODE-INSP    | 🔄 IN PROGRESS  | —
B     | DBA          | ⏳ WAITING      | Blocked on A completion
...
```

**Conflict Resolution Protocol:**
If two agents disagree (e.g., BACKEND-DEV says code is correct, CODE-INSP flags it):
1. Both agents state their case with specific line numbers and evidence
2. SECURITY or QA acts as tiebreaker depending on category of conflict
3. If still unresolved, escalate to user with: "Conflict between [AGENT-A] and [AGENT-B] on [FILE:LINE]. Evidence: [A's case]. [B's case]. Recommendation: [your recommendation]."

---

## SPECIFICATION DOCUMENTS — READ ORDER

Claude Code must read documents in this exact order before any implementation begins.
Reading is non-negotiable. Skipping causes cascading errors across all agents.

```
STEP 1: Read AGENTS.md (this file) — fully
STEP 2: Read JARVIS_DMS_Specification.docx
         Key sections: Data Model (§2), Category System (§3), API Endpoints (§10)
STEP 3: Read JARVIS_DMS_Upload_Parse_Spec.docx
         Key sections: Upload Pipeline (§2), Word Handling (§3), Parse Engine (§5)
STEP 4: Read JARVIS_DMS_Intelligence_Layer.docx
         Key sections: Signature Integration (§1), List SQL (§2.4), WML Storage (§3.3), RAG (§4)
STEP 5: Read existing codebase — in this order:
         core/signatures/service.py
         core/approval/service.py
         ai_agent/services/rag_service.py
         ai_agent/services/embedding_service.py
         core/__init__.py
         db.py (connection helper)
         Any existing document_* tables in database (run \dt document* in psql)
```

**After reading, MASTER must confirm:**
- [ ] All 15 database tables understood
- [ ] Existing signature service API confirmed (request_signature, get_signature_status)
- [ ] Existing RAG service API confirmed (search_rag, batch_generate_embeddings)
- [ ] Existing approval service API confirmed (submit, get_status)
- [ ] File storage client confirmed (which: R2 / DigitalOcean Spaces / local)
- [ ] Frontend framework confirmed (React 19, Tailwind, component library)
- [ ] Task queue confirmed (Celery + Redis — verify redis is running)

If any confirmation fails, stop and report to user before proceeding.

---

## AGENT TEAM — DEFINITIONS & AUTHORITIES

### 1. BACKEND-DEV Agent
**Specialization:** Flask (sync), PostgreSQL raw SQL, Python services, Celery tasks
**Primary files:** `dms/`, `core/signatures/dms_integration.py`, `tasks/`
**Authorities:**
- Write new Python service files
- Write new Flask routes and blueprints
- Write raw SQL (no ORM, no SQLAlchemy)
- Write Celery task functions
- Modify existing services ONLY if explicitly instructed by MASTER

**Cannot do without SECURITY clearance:**
- Any endpoint that handles file uploads
- Any endpoint accessible without authentication
- Any code that touches document_hash or signature verification
- Any webhook receiver endpoint

**Cannot do without DBA approval:**
- Create or modify any database table
- Add any index
- Change any column type

**Output format:**
```
[BACKEND-DEV REPORT]
Phase: [X] | Task: [description]
Files created: [list with line counts]
Files modified: [list with change summary]
Tests written: [count, location]
Endpoints added: [METHOD /path — description]
Celery tasks added: [task_name — trigger]
Blockers encountered: [none / description]
Handoff to: [QA, SECURITY, or MASTER]
```

---

### 2. FRONTEND Agent
**Specialization:** React 19, Tailwind CSS, existing JARVIS component library
**Primary files:** `frontend/src/components/dms/`, `frontend/src/pages/dms/`
**Authorities:**
- Create new React components
- Create new page routes
- Consume existing API endpoints (no mocking in production components)
- Use existing core components: `SignatureCanvas.jsx`, `SignatureModal.jsx`, existing table/filter components

**Cannot do:**
- Install new npm packages without VELOCITY-SPECIALIST approval
- Modify existing core components (wrap them, never edit them)
- Create API calls to endpoints that BACKEND-DEV has not confirmed as complete
- Use `localStorage` for any document content (security policy)

**Must verify before handoff:**
- `npm run build` exits 0 with zero errors
- `npm run lint` exits 0
- All props are typed with PropTypes or TypeScript types
- No console.log statements left in production code
- Mobile viewport tested at 375px width

**Output format:**
```
[FRONTEND REPORT]
Phase: [X] | Task: [description]
Components created: [list]
Pages created: [list]
API endpoints consumed: [list]
Build status: ✅ / ❌ [error]
Lint status: ✅ / ❌ [error]
Mobile check: ✅ / ❌
Handoff to: [QA]
```

---

### 3. QA Agent
**Specialization:** Test strategy, integration testing, edge cases, regression
**Primary files:** `tests/dms/`, `tests/integration/`
**Authorities:**
- Write pytest test files
- Write React Testing Library / Vitest test files
- Execute tests and report results
- BLOCK phase completion if coverage < 75% on new code
- BLOCK phase completion if any existing test suite regresses

**Must test for every backend endpoint:**
- Happy path (valid input, authenticated user)
- Auth failure (no session → 401)
- Authorization failure (wrong company → 403)
- Invalid input (missing required fields → 400 with specific error message)
- Resource not found → 404
- Database error simulation (use mock) → 500 with no sensitive data leaked

**Must test for every frontend component:**
- Renders without crashing with minimal props
- Loading state displays correctly
- Error state displays user-friendly message (not raw API error)
- Empty state displays correctly
- Interaction (click, submit) fires correct handler

**Coverage requirement:** 75% minimum on all new files. No exceptions.
If a file cannot reach 75%, QA must document why and get MASTER approval.

**Output format:**
```
[QA REPORT]
Phase: [X] | Task: [description]
Tests written: [count]
Tests passing: [count] / [total]
Coverage on new files: [%]
Coverage on modified files: [%]
Regression check: ✅ CLEAN / ❌ [list of broken tests]
Edge cases found: [list — each becomes a filed issue]
VERDICT: ✅ APPROVED / ❌ BLOCKED — [reason]
```

---

### 4. SECURITY Agent
**Specialization:** Input validation, auth/authz, file safety, injection prevention, data exposure
**Primary files:** Reviews ALL files written by BACKEND-DEV and FRONTEND
**Authorities:**
- VETO any code before it merges if a critical vulnerability is found
- Require fixes before phase can advance
- Issue SECURITY ADVISORIES that MASTER must acknowledge

**Security checklist — run on every backend file:**

```
AUTH & AUTHZ
[ ] Every route checks session['user_id'] — no unauthenticated endpoints
[ ] Every query filters by company_id from session, NEVER from request params
[ ] Cross-entity access requires explicit holding-admin role check
[ ] Callback/webhook endpoints validate HMAC signature or shared secret

INPUT VALIDATION
[ ] File uploads: MIME validated server-side (not just extension)
[ ] File uploads: size limit enforced before writing to disk
[ ] Text inputs: length limits enforced
[ ] SQL: 100% parameterized queries — zero f-string or format() in SQL
[ ] HTML input: bleach sanitization before storage
[ ] Path traversal: file_id from request never used to construct file path directly

FILE SECURITY
[ ] No direct file URLs exposed — all via signed URL endpoint with auth check
[ ] Uploaded files never executed (no .py, .sh, .exe in allowed MIME types)
[ ] Temporary files deleted after processing
[ ] Virus scan status checked before file is made accessible

DATA EXPOSURE
[ ] Error messages contain no stack traces, file paths, or SQL
[ ] API responses exclude fields not relevant to the requesting user
[ ] Confidential documents not returned to users without confidential-viewer role
[ ] Audit log entries never expose other users' PII

WEBHOOK SECURITY
[ ] Google Drive webhook: validate channel token header
[ ] Signature provider callback: validate HMAC
[ ] Rate limited: max 100 webhook calls/minute per source IP
```

**Output format:**
```
[SECURITY REPORT]
Phase: [X] | Task: [description]
Files reviewed: [list]
Issues found: [count]
  CRITICAL: [list — must fix before ANY further work]
  HIGH: [list — must fix before phase closes]
  MEDIUM: [list — fix in current phase if possible, else track]
  LOW: [list — log as tech debt]
VERDICT: ✅ CLEARED / ⚠️ FIX REQUIRED / 🚨 CRITICAL BLOCK
```

---

### 5. CODE-INSPECTOR Agent
**Specialization:** Code quality, patterns, consistency, maintainability, tech debt
**Primary files:** Reviews ALL files written by BACKEND-DEV and FRONTEND
**Authorities:**
- Flag inconsistencies with existing JARVIS codebase patterns
- Require refactoring if code diverges significantly from established patterns
- Approve or reject variable naming, function structure, module organization

**Inspection checklist:**

```
PYTHON / BACKEND
[ ] Uses get_db() connection helper — not raw psycopg2 connect()
[ ] SQL queries in dedicated repository functions, not inline in routes
[ ] Routes only handle request/response — business logic in service layer
[ ] Service functions have docstrings with Args and Returns
[ ] No silent except: pass blocks — all exceptions logged
[ ] Constants at module top level — no magic strings in business logic
[ ] Function max length: 50 lines. If longer, extract sub-functions.
[ ] File max length: 400 lines. If longer, split into sub-modules.
[ ] Import order: stdlib → third-party → internal (alphabetical within each group)
[ ] No circular imports

JAVASCRIPT / REACT
[ ] Functional components only — no class components
[ ] Hooks only (useState, useEffect, useCallback, useMemo) — no HOCs
[ ] No prop drilling beyond 2 levels — use context or lift state
[ ] useEffect has correct dependency arrays — no missing deps
[ ] API calls in custom hooks or service files — not inline in components
[ ] Error boundaries wrap all async data-fetching components
[ ] No hardcoded strings — use constants or i18n keys
[ ] Component max length: 200 lines — split if longer

CROSS-CUTTING
[ ] New modules registered in the correct __init__.py
[ ] New celery tasks registered in celery app config
[ ] New React pages have route defined in router config
[ ] No TODO comments in production code — convert to GitHub issues
[ ] All new env variables documented in .env.example
```

**Output format:**
```
[CODE-INSPECTOR REPORT]
Phase: [X] | Task: [description]
Files reviewed: [count]
Pattern violations: [list with file:line:rule]
Refactoring required: [list]
Tech debt logged: [count issues]
Consistency with existing codebase: [score 1-10 with notes]
VERDICT: ✅ APPROVED / ⚠️ REFACTOR REQUIRED / ❌ REWRITE REQUIRED
```

---

### 6. DBA Agent
**Specialization:** PostgreSQL schema design, query performance, migrations, indexes
**Primary files:** `core/schema/migrations/`, all SQL queries written by BACKEND-DEV
**Authorities:**
- Approve or reject any CREATE TABLE, ALTER TABLE, CREATE INDEX
- Require EXPLAIN ANALYZE on any query touching > 3 tables
- Block any query with sequential scan on tables > 1000 estimated rows
- Define migration file naming and ordering

**Performance standards:**
- Document list query (§2.4 of Intelligence Layer spec): < 50ms on 10,000 documents
- Single document fetch: < 10ms
- RAG vector search (top-5 chunks): < 100ms
- Any API endpoint serving the list view: < 200ms total

**Migration checklist:**
```
[ ] Migration file named: NNN_description.sql (sequential number)
[ ] Migration is idempotent (IF NOT EXISTS / ON CONFLICT DO NOTHING)
[ ] Rollback SQL provided as comment at bottom of migration file
[ ] New columns have sensible DEFAULT values (no NOT NULL without default on existing tables)
[ ] Foreign keys have indexes on the referencing column
[ ] JSONB columns have GIN index if queried with @> or ? operators
[ ] vector columns have ivfflat or hnsw index (not btree)
[ ] All migrations tested on a copy of production schema before applying
```

**Output format:**
```
[DBA REPORT]
Migration files reviewed: [list]
Schema changes: [list of tables/columns added/modified]
Indexes added: [list]
Query analysis:
  [query name]: [EXPLAIN output summary] — [PASS/FAIL] [ms estimate]
Performance verdict: ✅ APPROVED / ⚠️ OPTIMIZE / ❌ REDESIGN
```

---

### 7. AI-SPECIALIST Agent
**Specialization:** RAG implementation, embedding strategy, LLM prompt engineering, vector search tuning
**Primary files:** `dms/services/wml_extractor.py`, `tasks/rag_tasks.py`, `ai_agent/services/rag_service.py` (extension), system_prompts.py
**Authorities:**
- Define chunking strategy and parameters
- Write and test all LLM prompts before they go into production
- Tune vector similarity thresholds (currently 0.70 — may adjust based on testing)
- Approve or reject embedding model choice for DMS chunks
- Define RAG evaluation metrics and run accuracy benchmarks

**Prompt engineering standards:**
```
Every LLM prompt must include:
[ ] System role definition (specific, not generic)
[ ] Output format specification (JSON schema or structured template)
[ ] Failure instruction ("If not found, return null — do not invent")
[ ] Language instruction ("Respond in Romanian if question is in Romanian")
[ ] Confidence instruction ("Include confidence score 0.0-1.0 per field")

Every prompt must be tested against:
[ ] 5 clean digital PDFs (text layer present)
[ ] 3 scanned PDFs with Romanian text
[ ] 2 .docx files with tables and mixed content
[ ] 1 edge case: document in a language other than Romanian/English
[ ] 1 edge case: empty document or document with only images
```

**RAG accuracy benchmark (minimum before Phase E closes):**
- Precision@5: ≥ 0.75 (at least 3 of 5 retrieved chunks are relevant)
- Answer accuracy on structured queries (dates, amounts, parties): ≥ 85%
- Answer accuracy on semantic queries (clause content, party obligations): ≥ 70%
- Hallucination rate (AI answers about clauses not in any retrieved chunk): < 5%

**Output format:**
```
[AI-SPECIALIST REPORT]
Phase: [X] | Task: [description]
Prompts written: [count, locations]
Chunking strategy: [description and parameters]
Embedding model: [name, dimensions, provider]
Benchmark results:
  Precision@5: [score]
  Structured accuracy: [score]
  Semantic accuracy: [score]
  Hallucination rate: [score]
Threshold recommendation: [similarity score]
VERDICT: ✅ READY FOR PRODUCTION / ⚠️ NEEDS TUNING / ❌ REDESIGN REQUIRED
```

---

### 8. VELOCITY-SPECIALIST Agent
**Specialization:** Scope control, dependency blocking, parallel work identification, risk assessment
**Role:** This agent does not write code. It analyzes the implementation plan and answers:
"What is the fastest path to a working, shippable Phase A without compromising Phase B-F?"

**Responsibilities:**
- At session start: review all phases and identify parallelizable work
- Flag tasks that are spec-complete but implementation-blocked (dependency missing)
- Flag scope creep — any work not in the spec that a developer is about to do
- Estimate task duration based on complexity (not days — complexity points: 1=trivial, 3=half-day, 5=full-day, 8=multi-day)
- At each phase boundary: confirm the next phase is unblocked or state the blocker explicitly

**Parallelization rules:**
```
CAN run in parallel (no shared files, no shared DB state):
  - BACKEND-DEV writing service layer while DBA writes migrations
  - FRONTEND building UI components while BACKEND-DEV writes routes
  - AI-SPECIALIST writing prompts while BACKEND-DEV builds the upload pipeline
  - QA writing test scaffolding while BACKEND-DEV implements

CANNOT run in parallel (shared state):
  - DBA migration must apply before BACKEND-DEV writes queries against new table
  - BACKEND-DEV must complete endpoint before FRONTEND consumes it
  - SECURITY must clear a phase before QA marks it APPROVED
  - CODE-INSPECTOR must clear a file before MASTER marks it mergeable
```

**Output format:**
```
[VELOCITY REPORT]
Current phase: [X]
Parallel tracks active: [list]
Blockers: [list with blocking agent and ETA]
Scope creep detected: [description of any out-of-spec work found]
Risk items: [list]
Recommended next 3 tasks in priority order:
  1. [task] — [agent] — [complexity points] — [why first]
  2. [task] — [agent] — [complexity points]
  3. [task] — [agent] — [complexity points]
```

---

### 9. DEVOPS Agent
**Specialization:** Infrastructure, environment config, service dependencies, deployment
**Primary files:** `.env.example`, `docker-compose.yml`, `Procfile`, `requirements.txt`
**Authorities:**
- Approve new Python dependencies before they are added to requirements.txt
- Approve new npm packages before they are added to package.json
- Define environment variable names and document them
- Verify external service connectivity before any agent builds against it

**Pre-flight checklist (run before Phase A begins):**
```
[ ] Redis is running and accessible: redis-cli ping returns PONG
[ ] Celery worker is running: celery -A jarvis inspect active
[ ] LibreOffice headless is installed: soffice --version
[ ] Tesseract is installed with Romanian lang pack: tesseract --list-langs | grep ron
[ ] Google Drive service account JSON file exists in config/
[ ] Drive API is enabled in the Google Cloud project
[ ] R2 / Spaces credentials in .env and connection tested
[ ] pgvector extension installed: SELECT * FROM pg_extension WHERE extname='vector'
[ ] All environment variables in .env.example have non-empty values
```

**Dependency approval criteria:**
```
APPROVE if:
- Package has > 1M monthly downloads OR is the official SDK for the service
- Package has been updated in the last 12 months
- Package has no known critical CVEs in its latest version

REJECT if:
- Functionality already exists in an approved package
- Package is a thin wrapper around something we can call directly
- Package pulls in > 5 transitive dependencies for simple functionality
```

**Output format:**
```
[DEVOPS REPORT]
Pre-flight status: ✅ ALL CLEAR / ❌ [list of failures]
New dependencies reviewed:
  [package]: ✅ APPROVED / ❌ REJECTED — [reason]
Environment variables added: [list]
Infrastructure changes: [description]
Deployment notes: [anything ops needs to know]
```

---

## INTER-AGENT VERIFICATION PROTOCOL

This is the mandatory flow for every phase. No exceptions.

```
PHASE START
    │
    ├─→ VELOCITY-SPECIALIST: Confirm phase is unblocked. Identify parallel tracks.
    │
    ├─→ DEVOPS: Run pre-flight for any new external services in this phase.
    │
    ├─→ DBA: Write and apply migrations. Report to MASTER.
    │        ↓ (MASTER confirms migration applied before BACKEND-DEV starts)
    ├─→ BACKEND-DEV: Implement services + routes. Write unit tests.
    │   FRONTEND: (parallel) Build components + pages. Write component tests.
    │   AI-SPECIALIST: (parallel, if phase involves AI) Write/test prompts.
    │        ↓
    ├─→ QA: Run full test suite. Report coverage. Flag edge cases.
    │        ↓
    ├─→ SECURITY: Review all new files. Run security checklist. Report.
    │        ↓
    ├─→ CODE-INSPECTOR: Review all new files. Check patterns. Report.
    │        ↓
    ├─→ MASTER: Collect all reports. Update STATUS TABLE.
    │   If all verdicts are ✅: mark phase COMPLETE. Notify user.
    │   If any verdict is ⚠️: assign fix to responsible agent. Re-run from that agent.
    │   If any verdict is ❌: HALT. Report to user with full context.
    │
PHASE COMPLETE → Begin next phase only after MASTER confirmation
```

---

## PHASE-SPECIFIC AGENT ASSIGNMENTS

### PHASE A — Signature Wiring

```
READ FIRST: Intelligence Layer Spec §1 (all subsections)

Tasks:
  DBA:         No migrations needed. Confirm document_signatures table exists
               and has correct schema. Confirm index on (document_type, document_id).

  BACKEND-DEV: Create dms/services/dms_signature_service.py
               Create dms/routes/signature_routes.py
               Register blueprint in dms/__init__.py
               Endpoints:
                 POST /api/dms/documents/<id>/request-signature
                 POST /api/dms/signature-callback/<doc_id>/complete
                 POST /api/dms/signature-callback/<doc_id>/next/<signer_index>
                 GET  /api/dms/documents/<id>/signature-status

  FRONTEND:    Add signature_status column to document list table component
               Mount SignatureModal on document detail panel (Signature tab)
               Add 'Request Signatures' button to document action bar (show only to dms_manager role)

  QA:          Test signature request with 1 signer, 2 signers sequential, 2 signers parallel
               Test callback with all signers complete
               Test callback with one signer declined
               Test that document status transitions correctly in all cases

  SECURITY:    Focus on: callback endpoint authentication, file path validation,
               signature_image size limit enforcement

  AI-SPECIALIST: Not active this phase.

Acceptance criteria:
  ✅ A document can be sent for signature from the DMS UI
  ✅ On completion, signed PDF appears as file_role='signed_version' in document_files
  ✅ Document status becomes 'active' after all signatures collected
  ✅ Document list shows correct signature icon for all 6 signature states
```

---

### PHASE B — Party Mapping & Enriched List View

```
READ FIRST: Intelligence Layer Spec §2 (all subsections)

Tasks:
  DBA:         CREATE TABLE document_parties (full schema from spec §2.2)
               CREATE VIEW document_parties_summary
               Add all indexes from spec §2.5
               Add columns to documents table: (no new columns this phase)
               Run EXPLAIN ANALYZE on the full list query (spec §2.4) with test data.
               Target: < 50ms. Report actual result.

  BACKEND-DEV: Create dms/services/party_mapping_service.py
               Functions: sync_supplier_from_invoices(), auto_map_party_by_cui()
               Modify document_ext_links creation to call sync_supplier_from_invoices()
               after any invoice link is created
               Modify parse completion handler to call auto_map_party_by_cui()
               Create GET /api/dms/documents?... — implement the full list SQL from spec §2.4
               Ensure all filter params work: status, supplier_id, expiring_in_days, search, sort

  FRONTEND:    Add all new columns to document list table (refer to spec §2.1 for full column set)
               Make columns toggle-able (user preference stored in localStorage)
               Add filter bar: Status multi-select, Supplier search, Expiry range picker, Search input
               Expiry date column: color-code red/amber/green/gray based on days_to_expiry
               # Invoices column: clickable → opens invoice list filtered by document_id
               # Anexe column: shows count with icon

  QA:          Test party auto-mapping from parse engine (mock parse result with known CUI)
               Test supplier sync when invoice link created
               Test manual party-to-supplier mapping via UI
               Test list query with all filter combinations (at minimum 8 combinations)
               Test sort by: expiry, updated, invoices
               Test with 0 invoices, 1 invoice, 10 invoices on same contract
               Test color coding: document expiring today, in 5 days, in 35 days, expired, no expiry

  SECURITY:    Confirm company_id filter is applied server-side on list query (cannot be bypassed)
               Confirm supplier_id filter cross-references to user's company (no cross-company leakage)
               Confirm confidential documents excluded from results for users without confidential-viewer role

  CODE-INSPECTOR: Review the list SQL for readability and comment completeness
                  Review party_mapping_service.py for function length and docstrings
```

---

### PHASE C — Google Drive Sync

```
READ FIRST: Intelligence Layer Spec §3.1 and §3.2

Tasks:
  DEVOPS:      Verify Google service account JSON exists and has Drive API access
               Verify Drive API v3 is enabled in the Cloud project
               Add env vars: GDRIVE_SERVICE_ACCOUNT_PATH, GDRIVE_COMPANY_ROOT_FOLDER_IDS (JSON map)
               Add to requirements.txt: google-api-python-client, google-auth
               Document folder creation and service account sharing instructions

  DBA:         Add columns to documents table: gdrive_file_id, gdrive_sync_status, gdrive_synced_at
               Add columns to document_files: gdrive_file_id, gdrive_view_link
               Add columns to document_categories: gdrive_sync (boolean, default true)
               Add column to companies: gdrive_root_folder_id, gdrive_webhook_expiry
               Migration: 005_gdrive_columns.sql

  BACKEND-DEV: Create dms/services/gdrive_sync_service.py (full implementation from spec §3.2)
               Create Celery task: tasks/gdrive_tasks.py
                 sync_document_to_drive.delay(document_id) — called after successful upload
               Create webhook receiver: POST /api/gdrive/webhook/<company_id>
               Create drive link endpoint: GET /api/dms/files/<file_id>/drive-link
               Add retry logic: if Drive sync fails, retry 3x with exponential backoff
               Add company setup endpoint: POST /api/admin/companies/<id>/setup-drive

  FRONTEND:    Add Google Drive icon to document list row (gdrive_file_id present = show icon, clickable)
               Add Drive sync status indicator in document detail header
               Add 'Open in Drive' button in file cards when gdrive_view_link is available

  QA:          Test: upload document → Drive sync → verify file appears in correct Drive folder
               Test: upload annex → verify it appears in correct subfolder
               Test: upload proof image → verify it appears in Dovezi subfolder
               Test: Drive webhook fires → JARVIS receives and logs it
               Test: Drive sync failure → document still works, sync retried
               Test: company without Drive configured → graceful fallback (no sync, no error)

  SECURITY:    Verify webhook validates channel token header from Google
               Verify service account credentials never logged or exposed in API responses
               Verify gdrive_view_link is only returned to users with access to that document
               Verify Drive sync does not upload confidential documents if company has disabled it

  DEVOPS:      After implementation: run drive sync on 3 test documents manually
               Confirm folder structure matches spec §3.2
               Set up webhook renewal cron job (webhooks expire after 7 days)
```

---

### PHASE D — WML Extraction & PostgreSQL Storage

```
READ FIRST: Intelligence Layer Spec §3.3 and §3.4

Tasks:
  DEVOPS:      Verify mammoth is installed: python -c "import mammoth; print('ok')"
               Verify lxml is installed: python -c "from lxml import etree; print('ok')"
               Add to requirements.txt if missing: mammoth, lxml

  DBA:         CREATE TABLE document_wml (full schema from spec §3.3)
               CREATE TABLE document_wml_chunks (full schema from spec §3.3)
               Verify pgvector extension: SELECT * FROM pg_extension WHERE extname='vector'
               If not installed: CREATE EXTENSION IF NOT EXISTS vector;
               Create ivfflat index on document_wml_chunks.embedding
               Note: ivfflat index requires at least 100 rows to be effective —
               create index AFTER initial data load, not before.
               Migration: 006_wml_tables.sql

  BACKEND-DEV: Create dms/services/wml_extractor.py (full implementation from spec §3.4)
               Modify upload pipeline: after docx upload and PDF conversion complete,
               enqueue wml_extractor.extract_wml_from_docx.delay(docx_path, document_id, file_id)
               Create endpoint: GET /api/dms/documents/<id>/content
                 Returns: {html_rendition, heading_structure, word_count, chunk_count}
                 Used by frontend preview panel for HTML rendering (faster than PDF.js for small docs)

  QA:          Test WML extraction on: simple contract, complex contract with tables,
               contract with images, very short document (<100 words), very long (>10,000 words)
               Verify heading_structure JSON matches actual document heading hierarchy
               Verify html_rendition renders in browser without broken formatting
               Verify word_count is within 10% of actual word count
               Verify chunk boundaries align with heading boundaries

  AI-SPECIALIST: Review chunking output on 5 real Romanian contracts
                 Verify heading_path breadcrumbs are correct ('Articolul 3 > Clauza 3.1')
                 Verify no chunk exceeds 800 tokens (count via tiktoken or character proxy)
                 Verify no meaningful content is cut mid-sentence at chunk boundaries
                 Report: average chunk size, min chunk size, max chunk size

  CODE-INSPECTOR: Review wml_extractor.py for:
                  - Proper handling of malformed XML (try/except with specific errors)
                  - Memory efficiency (streaming, not loading entire DOCX into RAM)
                  - Correct namespace handling for OOXML (common source of bugs)
```

---

### PHASE E — RAG Integration

```
READ FIRST: Intelligence Layer Spec §4 (all subsections)
READ ALSO:  ai_agent/services/rag_service.py — understand existing search_rag() signature
            ai_agent/services/embedding_service.py — understand batch_generate_embeddings()
            ai_agent/system_prompts.py — understand existing prompt structure

Tasks:
  BACKEND-DEV: Add search_dms_chunks() method to existing RAGService
               Add search_dms_structured() method to existing RAGService
               Extend AIAgentService.send_message() to include DMS search when:
                 - user is on a DMS route (context_scope includes 'dms')
                 - OR query contains document-related keywords detected by ContextManagementService
               Create endpoint: GET /api/dms/chat/context
                 Returns: {category_slug, document_id, company_id} for the current DMS context
                 Used by frontend to pass scope to AI chat

  AI-SPECIALIST: Extend system_prompts.py with DMS_SYSTEM_PROMPT_EXTENSION (from spec §4.4)
                 Build test set: 20 questions against 5 real documents
                   5 questions: specific article/clause content
                   5 questions: party/supplier identification
                   5 questions: structured (invoice count, expiry, totals)
                   5 questions: cross-document (compare two contracts)
                 Run benchmark. Report Precision@5, accuracy, hallucination rate.
                 Tune similarity threshold (default 0.70) if needed.
                 Tune chunk size if retrieval misses relevant content.

  FRONTEND:    Add 'Chat with Documents' button to DMS list view header
               Opens existing AI chat interface with context_scope: {category_slug, company_id}
               Add 'Ask AI about this document' button on document detail panel
               Opens AI chat with context_scope: {document_id}
               Implement source chip component: [Doc Number — Heading Path]
                 Clickable → open document preview at that chunk position
               Implement chunk highlight: amber background on the chunk text in document preview
               Show 'Extracting embeddings...' spinner on document card while chunk job is pending

  QA:          Test: upload contract → wait for chunk job → ask AI about a specific clause
               Test: ask AI about document that has no WML (PDF-only) → graceful response
               Test: ask AI about document from another company → no results returned
               Test: source chip click → correct document opens, correct chunk highlighted
               Test: AI response when no chunks found → correct 'not found' message (no hallucination)

  SECURITY:    Verify search_dms_chunks always filters by company_id from session
               Verify confidential documents are excluded from RAG results for unauthorized users
               Verify AI responses do not leak document content from unauthorized companies
               Verify the chat endpoint is rate-limited (max 20 queries/minute per user)
```

---

### PHASE F — UI Polish, Source Chips, Mobile

```
Tasks:
  FRONTEND:    Mobile viewport for document list (responsive table → card view at < 768px)
               Document detail panel: full-screen on mobile, slide-in on desktop
               Source chip animation (fade in after AI response)
               Chunk highlight smooth scroll behavior
               Column preferences persistence (localStorage is acceptable here — no document content)
               Empty states for all list views (no documents yet, no results, no access)
               Skeleton loading states for list and detail panel

  CODE-INSPECTOR: Final pass on all DMS components and services
                  Remove all TODO comments (convert to GitHub issues)
                  Remove all console.log statements
                  Verify all docstrings are complete

  QA:          Full regression test: run entire test suite (unit + integration)
               E2E test: upload → parse → approve → sign → AI Q&A full flow
               Performance test: load 1000 documents into staging, measure list query time
               Accessibility: run axe-core on all DMS pages

  DEVOPS:      Final environment documentation
               Confirm all new env variables are in .env.example with descriptions
               Confirm all new Celery tasks are in the task routing config
               Confirm Google Drive webhook renewal cron is scheduled
               Write deployment runbook for DMS module
```

---

## REPORTING TEMPLATE — END OF EACH PHASE

At the end of each phase, MASTER compiles this report and presents it to the user:

```
═══════════════════════════════════════════════════════
JARVIS DMS — PHASE [X] COMPLETION REPORT
═══════════════════════════════════════════════════════

PHASE: [name]
STATUS: ✅ COMPLETE / ⚠️ PARTIAL / ❌ BLOCKED

AGENT VERDICTS:
  BACKEND-DEV:       ✅ / ⚠️ / ❌
  FRONTEND:          ✅ / ⚠️ / ❌
  QA:                ✅ / ⚠️ / ❌  [coverage: X%]
  SECURITY:          ✅ / ⚠️ / ❌  [issues: C critical, H high, M medium]
  CODE-INSPECTOR:    ✅ / ⚠️ / ❌
  DBA:               ✅ / ⚠️ / ❌  [list query: Xms]
  AI-SPECIALIST:     ✅ / ⚠️ / ❌  [if applicable]
  DEVOPS:            ✅ / ⚠️ / ❌  [if applicable]
  VELOCITY:          ✅ / ⚠️ / ❌

DELIVERABLES:
  Files created: [count]
  Tests written: [count] | Passing: [count]
  Endpoints added: [list]
  Migrations applied: [list]

OPEN ITEMS (tracked, not blocking):
  - [item 1]
  - [item 2]

NEXT PHASE: [name] — READY TO BEGIN / BLOCKED BY [reason]
═══════════════════════════════════════════════════════
```

---

## ESCALATION TRIGGERS — STOP AND ASK THE USER

Do not proceed. Do not guess. Stop and present the situation when:

1. **A security CRITICAL is found** — always stop, never patch-and-continue
2. **Existing test suite regresses** — a previously passing test now fails
3. **Architecture conflict** — implementation requires changing a spec decision
   (e.g., "the spec says sequential signing but the existing signature service
   only supports parallel — which takes priority?")
4. **External service fails** — Google Drive API returns persistent errors,
   signature provider is down, Redis is unreachable
5. **Performance target missed** — list query exceeds 50ms after DBA optimization
6. **AI accuracy below threshold** — Precision@5 < 0.75 after AI-SPECIALIST tuning
7. **Scope ambiguity** — a feature is implied by the spec but not explicitly defined,
   and the implementation decision would take > 2 hours if wrong

Format for escalation:
```
🚨 ESCALATION REQUIRED — [Category]
Phase: [X] | Agent: [NAME]
Situation: [1-2 sentences describing exactly what happened]
Options:
  A) [option and implication]
  B) [option and implication]
  C) [option and implication]
Recommendation: [which option and why]
Time blocked: [how long work is halted waiting for this decision]
```

---

## CODEBASE RULES — ALL AGENTS MUST FOLLOW

These rules are absolute. Any agent that violates them has their output rejected automatically.

```
PYTHON
  - Flask sync only. No async/await. No FastAPI.
  - Raw psycopg2 via get_db(). No SQLAlchemy. No ORM of any kind.
  - Authentication: session['user_id']. Never JWT, never request params.
  - SQL: 100% parameterized. Zero string formatting in queries.
  - Error logging: use app.logger, never print().

JAVASCRIPT / REACT
  - React 19. Functional components. Hooks only.
  - Tailwind for styling. No CSS-in-JS. No styled-components.
  - No localStorage for any document content, file data, or authentication state.
  - API calls via fetch(). No axios (not in the project).
  - All API errors shown to user as human-readable messages. No raw error objects.

GENERAL
  - No hardcoded credentials, file paths, or company IDs anywhere.
  - All configurable values via environment variables.
  - No feature flags — implement the spec as written.
  - No premature optimization — measure first, then optimize.
  - Every new file must have at least one test. No exceptions.
```

---

## SESSION START COMMAND

Copy and paste this exact text to begin a Claude Code session:

```
Read AGENTS.md completely.

Then read the three DMS specification documents in /docs/dms/ in this order:
1. JARVIS_DMS_Specification.docx
2. JARVIS_DMS_Upload_Parse_Spec.docx
3. JARVIS_DMS_Intelligence_Layer.docx

Then read the existing source files:
- core/signatures/service.py
- core/approval/service.py
- ai_agent/services/rag_service.py
- ai_agent/services/embedding_service.py

After reading everything, activate the MASTER agent role.
Run the DEVOPS pre-flight checklist.
Present the STATUS TABLE with all phases marked as NOT STARTED.
Ask me which phase to begin.
Do not write any code until I confirm the phase.
```
