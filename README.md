# J.A.R.V.I.S. - Enterprise Platform

A modular enterprise platform for accounting, HR, and business operations management.

## Sections

| Section | Apps | Description |
|---------|------|-------------|
| **Accounting** | Invoices, Templates, Bugetare, Statements, e-Factura | Invoice allocation, bank statement parsing, ANAF e-invoicing |
| **HR** | Events | Employee event & bonus management |
| **Marketing** | Projects, Budgets, KPIs, OKR | Marketing project management with approval workflows |
| **AI** | AI Agent | Multi-provider chatbot with RAG, 10 tools, SSE streaming |
| **Approvals** | Flows, Requests, Delegations | Configurable approval engine with multi-step workflows |
| **Core** | Auth, Roles, Organization, Settings, Profile, Tags, Notifications | User management, permissions, platform configuration |

## Tech Stack

- **Backend**: Flask + Gunicorn (20 blueprints, 50 repository classes, 19 services)
- **Database**: PostgreSQL (pgvector for RAG)
- **Frontend**: React 19 + TypeScript + Vite + Tailwind 4 + shadcn/ui (~140 TSX files at `/app/*`)
- **AI**: Multi-provider (Claude, OpenAI, Groq, Gemini) with RAG, 10 tools, SSE streaming
- **Storage**: Google Drive integration
- **Deployment**: DigitalOcean App Platform (Docker, auto-deploy from staging)

## Quick Start

See [SETUP.md](SETUP.md) for full local development setup.

```bash
pip install -r requirements.txt
cd jarvis/frontend && npm ci && cd ../..

PORT=5001 DATABASE_URL="postgresql://user@localhost/defaultdb" \
FLASK_SECRET_KEY="dev-key" python3 jarvis/app.py
```

## Project Structure

```
jarvis/
├── app.py                 # Flask app (20 blueprints, scheduler)
├── database.py            # DB pool + helpers + init_db()
├── migrations/            # Schema & seed data (auto-runs on first boot)
├── core/                  # Core platform
│   ├── auth/              # Authentication, users, employees
│   ├── roles/             # Roles & permissions_v2
│   ├── organization/      # Companies, brands, departments
│   ├── settings/          # App settings, themes, dropdowns
│   ├── tags/              # Tags, auto-tag rules, AI suggest
│   ├── approvals/         # Approval engine (flows, steps, decisions)
│   ├── notifications/     # In-app + email notifications
│   ├── profile/           # User profile
│   ├── connectors/        # External connectors (e-Factura/ANAF)
│   ├── drive/             # Google Drive integration
│   ├── presets/           # User filter presets
│   ├── services/          # Shared services
│   ├── utils/             # API helpers, logging
│   └── base_repository.py # BaseRepository (inherited by 48 repos)
├── accounting/            # Accounting section
│   ├── invoices/          # Invoice CRUD, allocations, service layer
│   ├── templates/         # Invoice parsing templates
│   ├── bugetare/          # Bulk processor & invoice parser
│   └── statements/        # Bank statement parsing
├── hr/events/             # HR events & bonus management
├── ai_agent/              # AI (4 LLM providers, RAG, 10 tools, streaming)
├── marketing/             # Marketing projects, budgets, KPIs, OKR
└── frontend/              # React 19 + TypeScript + Vite + Tailwind 4
```

## Documentation

- **[SETUP.md](SETUP.md)** — Local development setup & architecture overview
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — Code conventions & workflow
- **[docs/CHANGELOG.md](docs/CHANGELOG.md)** — Version history and release notes

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string (required) |
| `ANTHROPIC_API_KEY` | Claude API key for invoice parsing |
| `GOOGLE_CREDENTIALS_JSON` | Google Drive API credentials |
| `EFACTURA_MOCK_MODE` | Set `true` for dev without ANAF certificate |

## Deployment

Configured for DigitalOcean App Platform via `.do/app.yaml`. Auto-deploys on push to `main` branch.

## Branch Workflow

| Branch | Purpose |
|--------|---------|
| `staging` | Development & testing |
| `main` | Production |

## License

Proprietary - All rights reserved.
