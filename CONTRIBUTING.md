# Contributing to JARVIS

## Branch Workflow

| Branch | Purpose |
|--------|---------|
| `staging` | Development & testing — all work goes here |
| `main` | Production — **never push directly** |

DigitalOcean auto-deploys from `staging` on every push.

## Getting Started

See [SETUP.md](SETUP.md) for local environment setup.

## Code Conventions

### Backend (Python/Flask)

- **Repository pattern**: All data access through repository classes inheriting `BaseRepository`
- **Service layer**: Business logic in service classes, routes stay thin (parse → call service → return)
- **Parameterized queries**: Always use `%s` placeholders, never f-strings in SQL
- **Error handling**: Use `safe_error_response(e)` for unexpected errors, `error_response(msg, code)` for known errors
- **Imports**: Repos import from `database` (not `core.database`)
- **Connection management**: `get_db()` / `release_db(conn)` in `try/finally` blocks (BaseRepository handles this automatically)

### Frontend (React/TypeScript)

- **Stack**: React 19 + TypeScript + Tailwind 4 + shadcn/ui
- **State**: Zustand stores (use `dataTableFactory` for table state)
- **Data fetching**: React Query (`useQuery` / `useMutation`)
- **API clients**: One file per module in `frontend/src/api/`
- **Components**: shadcn/ui primitives in `components/ui/`, shared components in `components/shared/`

### Naming

- Python: `snake_case` for functions, variables, files
- TypeScript: `camelCase` for variables/functions, `PascalCase` for components/types
- API routes: `/api/module-name/action` (kebab-case)
- DB tables: `snake_case`, prefixed by module (`mkt_projects`, `approval_flows`)

## Adding a New Module

1. **DB tables**: Add DDL to `migrations/init_schema.py` (in the appropriate domain section)
2. **Repository**: Create in `module/repositories/`, inherit `BaseRepository`
3. **Routes**: Create blueprint in `module/routes.py`, register in `app.py`
4. **Frontend**: Add types in `types/`, API client in `api/`, page in `pages/`
5. **Permissions**: Add to `permissions_v2` seed data if access control needed
6. **Tests**: Add to `tests/` — match the module structure

## Testing

```bash
pytest tests/ -x       # all tests, stop on first failure
pytest tests/ -x -q    # quiet output
```

All tests must pass before pushing. Currently: **642 tests**.

## Commit Messages

Format: `type(scope): description`

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`

Examples:
```
feat(marketing): Add OKR system with KPI linking
fix(auth): Prevent IDOR on user profile endpoint
refactor(accounting): Extract InvoiceService from routes
```

## Pull Requests

- Branch from `staging`, PR back to `staging`
- Include what changed and why
- All tests must pass
- TypeScript must compile clean (`npm run build` in `jarvis/frontend/`)

## Project Documentation

| File | Content |
|------|---------|
| [SETUP.md](SETUP.md) | Local development setup |
| [README.md](README.md) | Project overview |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Release notes |
