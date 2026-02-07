# J.A.R.V.I.S. - Enterprise Platform

A modular enterprise platform for accounting, HR, and business operations management.

## Sections

| Section | Apps | Description |
|---------|------|-------------|
| **Accounting** | Bugetare, Statements, e-Factura | Invoice allocation, bank statement parsing, ANAF e-invoicing |
| **HR** | Events | Employee event bonus management |
| **Core** | Auth, Settings, Profile | User management, platform configuration |

## Tech Stack

- **Backend**: Flask + Gunicorn
- **Database**: PostgreSQL
- **AI**: Anthropic Claude API (invoice parsing)
- **Storage**: Google Drive integration
- **Deployment**: DigitalOcean App Platform (Docker)

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL='postgresql://user@localhost:5432/defaultdb'
export ANTHROPIC_API_KEY='your-key'

# Run locally
python jarvis/app.py
```

## Project Structure

```
jarvis/
├── app.py                 # Main Flask application
├── database.py            # Database operations
├── core/                  # Core platform (auth, settings, connectors)
│   └── connectors/
│       └── efactura/      # ANAF e-Factura integration
├── accounting/            # Accounting section
│   ├── bugetare/          # Invoice budget allocation
│   └── statements/        # Bank statement parsing
└── hr/                    # HR section
    └── events/            # Event bonus management
```

## Documentation

- **[docs/CLAUDE.md](docs/CLAUDE.md)** - Detailed project documentation and development guide
- **[docs/CHANGELOG.md](docs/CHANGELOG.md)** - Version history and release notes

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
