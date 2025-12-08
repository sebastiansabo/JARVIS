# Bugetare - Invoice Budget Allocation System

## Project Overview
Flask-based web application for managing invoice allocations across companies, brands, and departments. Features AI-powered invoice parsing using Claude API.

## Tech Stack
- **Backend**: Flask + Gunicorn
- **Database**: PostgreSQL (production) / SQLite (local development)
- **AI**: Anthropic Claude API for invoice parsing
- **Storage**: Google Drive integration for invoice uploads
- **Deployment**: DigitalOcean App Platform via Docker

## Project Structure
```
app/
├── app.py           # Main Flask application and routes
├── database.py      # Database operations (PostgreSQL/SQLite dual support)
├── models.py        # Data models and structure loading
├── services.py      # Business logic for allocations
├── invoice_parser.py # AI-powered invoice parsing with Claude
├── drive_service.py # Google Drive integration
├── config.py        # Configuration settings
└── templates/       # Jinja2 HTML templates
```

## Key Commands

### Local Development
```bash
source venv/bin/activate
cd app && python app.py
```

### Database
- PostgreSQL connection via `DATABASE_URL` environment variable
- Falls back to SQLite (`invoices.db`) when `DATABASE_URL` not set
- Tables auto-initialize on first run with seed data

### Docker Build
```bash
docker build -t bugetare .
docker run -p 8080:8080 -e DATABASE_URL="..." -e ANTHROPIC_API_KEY="..." bugetare
```

## Environment Variables
- `DATABASE_URL` - PostgreSQL connection string (required for production)
- `ANTHROPIC_API_KEY` - Claude API key for invoice parsing
- `GOOGLE_CREDENTIALS_JSON` - Google Drive API credentials

## Database Schema
- `invoices` - Invoice header records
- `allocations` - Department allocation splits
- `invoice_templates` - AI parsing templates per supplier
- `department_structure` - Company/department hierarchy
- `companies` - Company VAT registry for matching

## Deployment
Configured via `.do/app.yaml` for DigitalOcean App Platform with auto-deploy on push to main branch.

## MCP Server Setup
To enable DigitalOcean integration in Claude Code, add the MCP server:
```bash
claude mcp add digitalocean -- npx -y @digitalocean/mcp --api-token YOUR_DO_API_TOKEN
```
Restart Claude Code after adding to use DO management tools.
