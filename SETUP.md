# JARVIS — Local Development Setup

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.11+ | Docker uses 3.11-slim |
| Node.js | 22+ | Docker uses node:22-slim |
| PostgreSQL | 14+ | With `pgvector` extension for RAG |
| poppler-utils | — | PDF processing (`brew install poppler` on macOS) |

## 1. Clone & Install

```bash
git clone https://github.com/sebastiansabo/JARVIS.git
cd JARVIS

# Python dependencies
pip install -r requirements.txt

# Frontend dependencies
cd jarvis/frontend
npm ci
cd ../..
```

## 2. Database Setup

Create a PostgreSQL database. The schema auto-initializes on first app start via `migrations/init_schema.py` — no manual migration needed.

```bash
createdb defaultdb  # or use an existing database
```

Enable pgvector (required for AI RAG):
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

## 3. Environment Variables

### Required

| Variable | Example | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://user@localhost/defaultdb` | PostgreSQL connection string |
| `FLASK_SECRET_KEY` | `your-secret-key-here` | Session signing key |

### Optional (feature-specific)

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Claude API — invoice parsing + AI chat |
| `OPENAI_API_KEY` | OpenAI provider for AI chat |
| `GROQ_API_KEY` | Groq provider for AI chat |
| `GOOGLE_API_KEY` | Gemini provider for AI chat |
| `GOOGLE_CREDENTIALS_JSON` | Google Drive integration |
| `GOOGLE_OAUTH_TOKEN` | Google Drive OAuth token |
| `ANAF_OAUTH_CLIENT_ID` | e-Factura ANAF integration |
| `ANAF_OAUTH_CLIENT_SECRET` | e-Factura ANAF secret |
| `ANAF_OAUTH_REDIRECT_URI` | e-Factura OAuth callback URL |
| `EFACTURA_MOCK_MODE` | Set `true` to skip ANAF cert in dev |
| `FLASK_DEBUG` | Set `true` for debug mode (default: `false`) |
| `LOG_LEVEL` | Logging level (default: `INFO`) |
| `PORT` | Flask port (default: `5000`, use `5001` locally) |

## 4. Run Locally

### Backend (Flask)

```bash
PORT=5001 \
DATABASE_URL="postgresql://youruser@localhost/defaultdb" \
FLASK_SECRET_KEY="dev-secret-key" \
python3 jarvis/app.py
```

Flask starts on `http://localhost:5001`. The schema auto-creates on first boot.

### Frontend (Vite dev server)

```bash
cd jarvis/frontend
npm run dev
```

Vite starts on `http://localhost:5173` with HMR, proxying API calls to Flask.

### Access the app

- Development (with HMR): `http://localhost:5173/app/dashboard`
- Flask-served (production build): `http://localhost:5001/app/dashboard`

## 5. Running Tests

```bash
pytest tests/ -x          # stop on first failure
pytest tests/ -x -q       # quiet output
pytest tests/ -k "test_invoice"  # run specific tests
```

Currently: **642 tests passing**.

## 6. Production Build

The frontend builds to `jarvis/static/react/` which Flask serves at `/app/*`:

```bash
cd jarvis/frontend
npm run build
```

## 7. Docker (matches production)

```bash
docker build -t jarvis .
docker run -p 8080:8080 \
  -e DATABASE_URL="postgresql://..." \
  -e FLASK_SECRET_KEY="..." \
  jarvis
```

Multi-stage build: Node 22 builds frontend, Python 3.11 runs backend.
Gunicorn: 3 workers x 3 threads, 120s timeout, worker recycling at ~1000 requests.

## 8. Deployment

DigitalOcean App Platform — auto-deploys from `staging` branch on push.

Config: `.do/app.yaml` | Region: Frankfurt | Instance: 1vCPU/1GB

```
staging branch  →  DO auto-build  →  Docker image  →  Production
```

**Never push directly to `main`** — all work goes through `staging`.

## 9. Project Structure

```
jarvis/
├── app.py                    # Flask app entry (20 blueprints, scheduler)
├── database.py               # DB pool, helpers, init_db()
├── models.py                 # Org structure model
├── migrations/init_schema.py # DDL + seed data (auto-runs on first boot)
├── tasks/cleanup.py          # APScheduler background jobs (6 tasks)
├── core/
│   ├── auth/                 # Login, users, employees, password reset
│   ├── roles/                # Roles & permissions_v2
│   ├── organization/         # Companies, brands, departments
│   ├── settings/             # App settings, themes, dropdowns
│   ├── tags/                 # Tags, auto-tag rules, AI suggest
│   ├── presets/              # User filter presets
│   ├── notifications/        # In-app + email notifications
│   ├── profile/              # User profile management
│   ├── approvals/            # Approval engine (flows, steps, decisions)
│   ├── connectors/efactura/  # ANAF e-Factura integration
│   ├── drive/                # Google Drive file storage
│   ├── services/             # Shared services
│   ├── utils/                # api_helpers, logging_config
│   └── base_repository.py    # BaseRepository (inherited by 48 repos)
├── accounting/
│   ├── invoices/             # Invoice CRUD, allocations, services
│   ├── templates/            # Invoice parsing templates
│   ├── bugetare/             # Bulk invoice processor
│   └── statements/           # Bank statement parsing
├── hr/events/                # HR events & bonus management
├── ai_agent/                 # Multi-provider AI (4 LLMs, RAG, 10 tools)
├── marketing/                # Marketing projects, budgets, KPIs, OKR
└── frontend/                 # React 19 + TypeScript + Vite + Tailwind 4
    └── src/
        ├── api/              # API client modules (~11 files)
        ├── components/       # Shared UI (shadcn/ui based)
        ├── pages/            # Route pages (Dashboard, Accounting, etc.)
        ├── stores/           # Zustand state stores
        ├── types/            # TypeScript interfaces
        └── lib/              # Utilities
```

## 10. Key Architecture Decisions

- **BaseRepository pattern**: All 48 repos inherit CRUD, connection management, error handling
- **Service layer**: Business logic in `InvoiceService`, `ProjectService` (routes are thin)
- **No ORM**: Raw SQL with parameterized queries via psycopg2
- **Schema auto-init**: `init_db()` creates tables + seeds on first run, skips if schema exists
- **DB pool**: 8 connections per Gunicorn worker, 5s ping cache
- **React SPA**: Served from Flask at `/app/*`, Vite dev server proxies to Flask
