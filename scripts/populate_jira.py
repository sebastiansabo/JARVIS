#!/usr/bin/env python3
"""Populate JARVIS Jira board with full project history."""

import json
import os
import subprocess
import sys
import time

DOMAIN = "autoworldro.atlassian.net"
EMAIL = "sebastian.sabo@autoworld.ro"
TOKEN = os.environ['JIRA_API_TOKEN']
PROJECT = "JAR"

def jira(method, endpoint, data=None):
    cmd = ["curl", "-s", "-X", method,
           f"https://{DOMAIN}/rest/api/3{endpoint}",
           "-u", f"{EMAIL}:{TOKEN}",
           "-H", "Content-Type: application/json"]
    if data:
        cmd.extend(["-d", json.dumps(data)])
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except:
        print(f"  ERROR: {r.stdout[:200]}")
        return {}

def create_issue(issue_type_id, summary, description, parent_key=None, labels=None, start_date=None, due_date=None):
    fields = {
        "project": {"key": PROJECT},
        "issuetype": {"id": str(issue_type_id)},
        "summary": summary,
        "description": {
            "type": "doc", "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": block}]} for block in description.split("\n\n") if block.strip()]
        },
        "labels": labels or ["claude-code"],
    }
    if parent_key:
        fields["parent"] = {"key": parent_key}
    if start_date:
        fields["customfield_10015"] = start_date
    if due_date:
        fields["duedate"] = due_date
    result = jira("POST", "/issue", {"fields": fields})
    key = result.get("key")
    if key:
        print(f"  Created {key}: {summary}")
    else:
        print(f"  FAILED: {summary} -> {result}")
    return key

def transition_to_done(issue_key):
    # Get available transitions
    t = jira("GET", f"/issue/{issue_key}/transitions")
    for tr in t.get("transitions", []):
        if tr["name"] == "Done" or tr["to"]["name"] == "Done":
            jira("POST", f"/issue/{issue_key}/transitions", {"transition": {"id": tr["id"]}})
            return True
    return False

WORKSTREAM = 10285   # Epic
ACTIVITATE = 10286   # Story/Task
SUBTASK = 10287      # Subtask

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WORKSTREAMS (Epics)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

workstreams = {
    "INFRA": {
        "summary": "Platform & Infrastructure",
        "desc": "Flask/PostgreSQL platform, DigitalOcean deployment, Docker, CI/CD, connection pooling, performance optimization.\n\n470 commits total. Dec 8, 2025 - Feb 16, 2026. 560 tests passing.",
        "start": "2025-12-08", "due": "2026-02-16"
    },
    "ACCT": {
        "summary": "Accounting & Invoice Management",
        "desc": "Core invoicing system with allocations, reinvoice destinations, VAT subtraction, bulk processing, status management, and dashboard analytics.\n\nThe primary business module of JARVIS — tracks all invoices across AUTOWORLD companies with department-level cost allocation.",
        "start": "2025-12-08", "due": "2026-02-16"
    },
    "EFACT": {
        "summary": "e-Factura ANAF Integration",
        "desc": "Integration with Romanian ANAF e-Factura system. OAuth2 authentication, invoice sync, supplier mapping, automatic classification, and send-to-accounting workflow.\n\nEnables automatic import of electronic invoices from the Romanian tax authority.",
        "start": "2026-01-28", "due": "2026-02-13"
    },
    "BANK": {
        "summary": "Bank Statement Processing",
        "desc": "Bank statement parsing, transaction matching with invoices, vendor mapping with regex patterns, reconciliation workflows, and bulk operations.\n\nAutomates matching of bank transactions to accounting invoices.",
        "start": "2026-01-22", "due": "2026-02-13"
    },
    "HR": {
        "summary": "HR Events & Bonuses Module",
        "desc": "HR module with employee events tracking, bonus management with monthly locks, organizational structure, and scope-based permissions.\n\nManages employee events (hiring, departures, bonuses) across all AUTOWORLD companies.",
        "start": "2026-01-29", "due": "2026-02-06"
    },
    "AI": {
        "summary": "AI Agent & Analytics Engine",
        "desc": "Multi-provider LLM chat (Claude, OpenAI, Groq, Gemini) with RAG over 7 data sources, SSE streaming, analytics engine with SQL aggregations, and admin settings UI.\n\nInternal AI assistant that can answer questions about invoices, transactions, employees, and business analytics.",
        "start": "2026-01-29", "due": "2026-02-13"
    },
    "REACT": {
        "summary": "React Frontend Migration",
        "desc": "Full migration from Jinja2/Bootstrap to React 19 + TypeScript + Tailwind 4 + shadcn/ui. 9 phases, ~115 TSX files, 2226 Vite modules.\n\nMigrated all 9 pages: Dashboard, Settings, Profile, Accounting, Add Invoice, HR Events, Bank Statements, e-Factura, AI Agent.",
        "start": "2026-02-08", "due": "2026-02-13"
    },
    "AUTH": {
        "summary": "User Management & Permissions",
        "desc": "Role-based access control, granular permissions (permissions_v2), user profiles, password recovery, organizational fields, and module-level access filtering.\n\n18 permission categories across 6 modules with Admin/Manager/User role hierarchy.",
        "start": "2026-01-29", "due": "2026-02-05"
    },
    "TAGS": {
        "summary": "Tagging & Auto-Classification System",
        "desc": "Platform-wide tagging with tag groups, auto-tag rules (11 condition operators, AND/OR logic), entity tagging across 6 entity types, and filter integration.\n\nEnables automatic categorization of invoices, transactions, and other entities based on configurable rules.",
        "start": "2026-02-04", "due": "2026-02-16"
    },
    "NOTIF": {
        "summary": "Email Notification System",
        "desc": "Email notifications for invoice allocation, status changes, and e-Factura imports. Department CC emails, manager auto-population, configurable per-user opt-in.\n\nAutomatically notifies responsible persons when invoices are allocated or status changes.",
        "start": "2026-02-03", "due": "2026-02-06"
    },
}

print("━━━ Creating Workstreams ━━━")
ws_keys = {}
for code, ws in workstreams.items():
    key = create_issue(WORKSTREAM, ws["summary"], ws["desc"],
                       start_date=ws["start"], due_date=ws["due"])
    ws_keys[code] = key
    time.sleep(0.3)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ACTIVITATE (Stories) under each Workstream
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

stories = [
    # ── INFRASTRUCTURE ──
    ("INFRA", "PostgreSQL migration & connection pooling",
     "Migrated from SQLite to PostgreSQL. Implemented psycopg2 connection pooling (8 connections/worker, 3 workers). Pool exhaustion fixes, ping caching, health checks.\n\nFiles: database.py (268 lines), migrations/init_schema.py (1,934 lines DDL/seeds)\nCommits: ~25 | Period: Dec 2025 - Feb 2026",
     "2025-12-08", "2026-02-13"),

    ("INFRA", "DigitalOcean App Platform deployment",
     "Multi-stage Docker build for React frontend compilation. Gunicorn with 3 workers x 3 threads. Environment variable management, health check endpoint, static asset caching.\n\nFiles: Dockerfile, app.yaml, gunicorn.conf.py\nCommits: ~15 | Period: Dec 2025 - Feb 2026",
     "2025-12-08", "2026-02-08"),

    ("INFRA", "Backend architecture refactoring (20 phases)",
     "Refactored monolithic app.py (3,400 lines) and database.py (7,800 lines) into modular architecture. 18 blueprints, ~30 repository classes, services layer. Deleted services.py after full migration.\n\nResult: app.py 502 lines, database.py 268 lines. 560/560 tests passing.\nCommits: ~40 | Period: Jan-Feb 2026",
     "2026-01-12", "2026-02-08"),

    ("INFRA", "Performance optimization",
     "init_db() schema check optimization (was running 1,934-line migration every worker startup). ETag conditional hashing, static asset cache headers, connection pool tuning, worker recycling.\n\nDB: 24 MB, 99.95% cache hit ratio. Response: 90-160ms warm.\nCommits: ~8 | Period: Feb 13, 2026",
     "2026-02-13", "2026-02-16"),

    ("INFRA", "Test suite (560 tests)",
     "Comprehensive pytest test suite covering all 70+ API endpoints, repository classes, and service layer. All returning 200.\n\nFiles: tests/ directory\nCommits: ~20 across all phases",
     "2026-01-12", "2026-02-16"),

    # ── ACCOUNTING ──
    ("ACCT", "Invoice CRUD with allocation splitting",
     "Core invoice management with multi-department cost allocation. VAT subtraction toggle, bidirectional %/value sync, allocation locking, tolerance handling (1%).\n\nFiles: repos/invoice_repository.py, routes/invoice_routes.py, frontend/src/pages/Accounting/\nCommits: ~30 | Period: Dec 2025 - Feb 2026",
     "2025-12-08", "2026-02-09"),

    ("ACCT", "Reinvoice destinations system",
     "Multi-destination reinvoice with NET value deduction, lock per destination, comments, brand validation. Bidirectional %/value sync for reinvoice amounts.\n\nFiles: invoice allocation forms, edit modal, expanded rows\nCommits: ~15 | Period: Feb 3-8, 2026",
     "2026-02-03", "2026-02-08"),

    ("ACCT", "Accounting dashboard with filters & analytics",
     "6-tab dashboard (By Company, Department, Brand, Supplier, Summary, All). Column reorder/visibility with localStorage persistence. Inline status/payment dropdowns with color dots. Click-to-expand rows with inline allocation editing.\n\nFiles: frontend/src/pages/Accounting/ (5 files)\nCommits: ~25 | Period: Dec 2025 - Feb 2026",
     "2025-12-09", "2026-02-13"),

    ("ACCT", "Bulk invoice processor with AI parsing",
     "Drag-drop file upload, AI-powered invoice parsing (template matching + AI fallback), duplicate detection, session caching. Template selector for known invoice formats.\n\nFiles: AddInvoice page, bulk processor\nCommits: ~15 | Period: Jan 2026",
     "2026-01-12", "2026-01-30"),

    ("ACCT", "Google Drive integration",
     "Automatic file upload to Drive on allocation confirm. Year/Month/Supplier folder structure. OAuth2 token management, TinyPNG image compression, retry logic for cold starts.\n\nFiles: drive upload service\nCommits: ~10 | Period: Dec 2025",
     "2025-12-09", "2025-12-18"),

    # ── E-FACTURA ──
    ("EFACT", "ANAF OAuth2 connector & invoice sync",
     "OAuth2 JWT token support for ANAF API. Company connection management, automatic token refresh, sync with configurable period/company. Progress bar with real percentage tracking.\n\nFiles: repos/efactura_repository.py, routes/efactura_routes.py\nCommits: ~20 | Period: Jan 28-30, 2026",
     "2026-01-28", "2026-01-30"),

    ("EFACT", "Supplier mapping & type classification",
     "Supplier-to-type mapping with multi-type support, brand field, department/subdepartment dropdowns from company structure. Import suppliers from invoices dialog. Hide-in-filter toggle.\n\nFiles: efactura mappings, supplier types\nCommits: ~25 | Period: Jan 28 - Feb 13, 2026",
     "2026-01-28", "2026-02-13"),

    ("EFACT", "Send-to-accounting workflow",
     "Send e-Factura invoices to accounting module with validation (requires Type + Department). Duplicate detection with AI fallback. Automatic responsible assignment. Batch operations.\n\nFiles: efactura routes, invoice repository\nCommits: ~15 | Period: Jan 29 - Feb 10, 2026",
     "2026-01-29", "2026-02-10"),

    ("EFACT", "e-Factura UI refactoring (React)",
     "Refactored from 6 to 2 tabs (Unallocated, Mappings). Connections moved to Settings/Connectors. Per-card fetch dialog. 16-column management with show/hide/reorder. Edit Overrides dialog matching Jinja2 modal.\n\nFiles: frontend/src/pages/EFactura/ (2 files + Settings connectors)\nCommits: ~20 | Period: Feb 9-13, 2026",
     "2026-02-09", "2026-02-13"),

    ("EFACT", "APScheduler auto-cleanup",
     "Automatic cleanup of old unallocated e-Factura invoices every 6h (>15 days). Manual cleanup per connector. Daily RAG reindex at midnight.\n\nFiles: tasks/cleanup.py, app.py scheduler setup\nCommits: ~5 | Period: Feb 9, 2026",
     "2026-02-09", "2026-02-09"),

    # ── BANK STATEMENTS ──
    ("BANK", "Bank statement parsing & import",
     "Parse bank statement files (PDF/CSV), extract transactions. File upload with drag-drop. Transaction list with filters and bulk operations.\n\nFiles: repos/bank_statement_repository.py, routes/bank_statement_routes.py\nCommits: ~10 | Period: Jan 22-26, 2026",
     "2026-01-22", "2026-01-26"),

    ("BANK", "Transaction-invoice matching & reconciliation",
     "Match bank transactions to accounting invoices. Vendor mapping with regex pattern testing. Merge transactions. Link to existing invoices. Reconciliation status tracking.\n\nFiles: bank statement repos/routes, frontend/src/pages/Statements/\nCommits: ~15 | Period: Jan 26 - Feb 13, 2026",
     "2026-01-26", "2026-02-13"),

    # ── HR ──
    ("HR", "HR events & bonus management",
     "Employee event tracking (hiring, departure, transfers). Bonus CRUD with 3 sub-views (list, by event, summary). Monthly lock system with configurable deadline. Brand column in bonuses.\n\nFiles: repos/hr_repository.py, routes/hr_routes.py, frontend/src/pages/HREvents/\nCommits: ~20 | Period: Jan 29 - Feb 6, 2026",
     "2026-01-29", "2026-02-06"),

    ("HR", "Organizational structure management",
     "Company structure with department/subdepartment hierarchy. Department structure mapping (responsible, CC email, manager auto-population). Brands junction table.\n\nFiles: company structure repos/routes, Settings page\nCommits: ~15 | Period: Jan 29 - Feb 5, 2026",
     "2026-01-29", "2026-02-05"),

    ("HR", "User table consolidation",
     "Consolidated responsables and hr.employees into single users table. Fixed FK references, profile queries, HR Events loading. Organizational fields in Edit User modal.\n\nFiles: migrations, user repository, profile routes\nCommits: ~10 | Period: Feb 2-5, 2026",
     "2026-02-02", "2026-02-05"),

    # ── AI AGENT ──
    ("AI", "Multi-provider LLM integration",
     "4 LLM providers: Claude (Anthropic), OpenAI, Groq, Gemini. Provider abstraction with BaseProvider class. Model management (enable/disable, set default, API key per provider).\n\nFiles: services/ai_agent/ (providers, config)\nCommits: ~10 | Period: Jan 29-30, 2026",
     "2026-01-29", "2026-01-30"),

    ("AI", "RAG system with 7 data sources",
     "Retrieval-Augmented Generation indexing: invoices, companies, departments, employees, bank transactions, e-Factura, HR events. Generic _index_document() helper, batch reindexing.\n\nFiles: services/ai_agent/rag_service.py\nCommits: ~10 | Period: Feb 8-9, 2026",
     "2026-02-08", "2026-02-09"),

    ("AI", "SSE streaming for real-time chat",
     "Server-Sent Events streaming for all 4 providers. generate_stream() + chat_stream() generators. React ReadableStream parser with token-by-token rendering.\n\nFiles: ai_agent service + routes, frontend ChatWindow.tsx\nCommits: ~8 | Period: Feb 8, 2026",
     "2026-02-08", "2026-02-08"),

    ("AI", "Analytics engine with SQL aggregations",
     "Invoice summary (4 GROUP BY dimensions), monthly trends, top suppliers, transaction summary, e-Factura summary. Query parser with keyword intent detection, regex date extraction (EN/RO), entity matching.\n\nFiles: services/analytics_service.py, services/query_parser.py\nCommits: ~8 | Period: Feb 9, 2026",
     "2026-02-09", "2026-02-09"),

    ("AI", "AI settings admin page",
     "Settings > AI Agent tab with 3 cards: LLM Models, RAG Configuration, Data Sources & Indexing. Runtime settings with 60s DB cache. 7 AI permissions.\n\nFiles: frontend/src/pages/Settings/AiTab.tsx, ai settings routes\nCommits: ~5 | Period: Feb 8, 2026",
     "2026-02-08", "2026-02-08"),

    # ── REACT FRONTEND ──
    ("REACT", "Shared infrastructure & component library",
     "10 shared components, 13 API modules, 12 type files, 5 Zustand stores. Vite + React 19 + TypeScript + Tailwind 4 + shadcn/ui + React Query.\n\nFiles: frontend/src/components/, api/, types/, stores/\nPhase 1 of 9",
     "2026-02-08", "2026-02-08"),

    ("REACT", "Dashboard, Settings, Profile pages",
     "Dashboard: stats row, recent invoices, company summary, quick actions. Settings: 12 files (index + 11 tabs), lazy-loaded sub-routes. Profile: user card, 4 stat cards, 3 tabs.\n\nPhases 2-4 of 9 | ~30 files",
     "2026-02-08", "2026-02-08"),

    ("REACT", "Accounting dashboard (React)",
     "5 files: index + AllocationEditor + EditInvoiceDialog + SummaryTable + AddInvoice. 6 tabs, filters, bulk ops, inline allocation editing, click-to-expand rows, column reorder/visibility.\n\nPhases 5-6 of 9 | ~10 files",
     "2026-02-08", "2026-02-09"),

    ("REACT", "HR Events, Bank Statements, e-Factura pages",
     "HR: 5 files, 3 tabs, bonus CRUD, event CRUD, structure management. Statements: 4 files, 3 tabs, reconciliation, file upload, vendor mappings. e-Factura: 2 tabs, column management.\n\nPhases 7-9 of 9 | ~15 files",
     "2026-02-09", "2026-02-13"),

    ("REACT", "Jinja2 template removal & route migration",
     "Removed 32 Jinja2 templates. Redirected all old routes to React /app/* paths. Fixed asset serving paths. Collapsible sidebar with hamburger toggle.\n\nFiles: templates/ (removed), app.py route redirects\nCommits: ~10 | Period: Feb 9, 2026",
     "2026-02-09", "2026-02-09"),

    # ── USER MANAGEMENT ──
    ("AUTH", "Role-based access control (RBAC)",
     "permissions_v2 system with 18 permission categories across 6 modules. Admin/Manager/User role hierarchy. Module menu filtering by permissions. Min-role for status dropdowns.\n\nFiles: auth routes, permissions middleware\nCommits: ~15 | Period: Jan 29 - Feb 4, 2026",
     "2026-01-29", "2026-02-04"),

    ("AUTH", "Profile page & password recovery",
     "User profile with invoice/HR/activity tabs. Self-service password recovery via email. Organizational fields in user modal. responsible_user_id FK for faster profile queries.\n\nFiles: profile routes, auth routes, frontend Profile page\nCommits: ~12 | Period: Feb 2-5, 2026",
     "2026-02-02", "2026-02-05"),

    # ── TAGGING ──
    ("TAGS", "Tag system backend & database",
     "4 tables: tag_groups, tags, entity_tags, auto_tag_rules. TagRepository + AutoTagRepository. 16 API endpoints. 6 entity types supported.\n\nFiles: repos/tag_repository.py, routes/tag_routes.py, migrations\nCommits: ~10 | Period: Feb 4-13, 2026",
     "2026-02-04", "2026-02-13"),

    ("TAGS", "Tag UI components & page integration",
     "TagBadge, TagPicker, TagFilter components. Tags displayed + filterable on Accounting, Statements, e-Factura, HR Events pages.\n\nFiles: frontend/src/components/tags/\nCommits: ~8 | Period: Feb 13, 2026",
     "2026-02-13", "2026-02-13"),

    ("TAGS", "Auto-tag rules with condition builder",
     "11 condition operators, AND/OR match mode, 'Run Now' execution, entity creation hooks. Settings UI for managing auto-tag rules.\n\nFiles: services/auto_tag_service.py, frontend Settings/TagsTab\nCommits: ~10 | Period: Feb 13-16, 2026",
     "2026-02-13", "2026-02-16"),

    # ── NOTIFICATIONS ──
    ("NOTIF", "Email notification service",
     "Notifications for invoice allocation, status changes, e-Factura imports. Department CC emails, manager auto-population from department_structure. Per-user opt-in toggle.\n\nFiles: services/notification_service.py, notification routes\nCommits: ~15 | Period: Feb 3-6, 2026",
     "2026-02-03", "2026-02-06"),

    ("NOTIF", "Status-based notifications",
     "Automatic email when invoice status changes. Notification for multi-department invoices. Responsible lookup from department_structure with company filtering.\n\nFiles: notification service, allocation routes\nCommits: ~8 | Period: Feb 5-6, 2026",
     "2026-02-05", "2026-02-06"),
]

print("\n━━━ Creating Stories (Activitate) ━━━")
story_keys = []
for ws_code, summary, desc, start, due in stories:
    parent = ws_keys.get(ws_code)
    if not parent:
        print(f"  SKIP (no parent): {summary}")
        continue
    key = create_issue(ACTIVITATE, summary, desc, parent_key=parent,
                       start_date=start, due_date=due)
    story_keys.append((ws_code, key, summary))
    time.sleep(0.3)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TRANSITION ALL TO DONE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n━━━ Transitioning Stories to Done ━━━")
for ws_code, key, summary in story_keys:
    if key:
        transition_to_done(key)
        print(f"  Done: {key}")
        time.sleep(0.2)

print("\n━━━ Transitioning Workstreams to Done ━━━")
for code, key in ws_keys.items():
    if key:
        transition_to_done(key)
        print(f"  Done: {key}")
        time.sleep(0.2)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SUMMARY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("     JIRA POPULATION COMPLETE")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print(f"\nWorkstreams created: {len([k for k in ws_keys.values() if k])}")
print(f"Stories created: {len([k for _, k, _ in story_keys if k])}")
print("\nWorkstreams:")
for code, key in ws_keys.items():
    print(f"  {key}: {workstreams[code]['summary']}")
print(f"\nBoard: https://autoworldro.atlassian.net/jira/core/projects/JAR/board")
