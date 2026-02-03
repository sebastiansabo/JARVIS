# Agent Modes

## UI Agent

Focus: Frontend improvements, UX optimization, template modifications.

### Scope
- HTML templates in `jarvis/templates/`
- JavaScript (inline in templates)
- Bootstrap 5 styling
- User interactions and feedback

### Guidelines
- Test in browser before committing
- Maintain Bootstrap 5 patterns
- Keep JavaScript inline (no build step)
- Ensure mobile responsiveness

---

## Developer Agent

Focus: Backend development, API endpoints, database operations.

### Scope
- Flask routes in `jarvis/app.py` and section-specific routes
- Database operations in `jarvis/database.py`
- Business logic in `jarvis/services.py`, `jarvis/models.py`
- Invoice parsing in `jarvis/accounting/bugetare/invoice_parser.py`
- Bulk processing in `jarvis/accounting/bugetare/bulk_processor.py`
- e-Factura connector in `jarvis/core/connectors/efactura/`

### Guidelines
- Use connection pooling via `get_db()` / `release_db()`
- Store dates as ISO `YYYY-MM-DD`
- Return JSON with `success` boolean for mutations
- Invalidate caches after CRUD operations

---

## Test Agent

Focus: Code analysis, testing, validation.

### Scope
- Function usage analysis
- Dead code detection
- Documentation accuracy
- API endpoint testing

### Guidelines
- Verify changes against documentation
- Check for unused imports/functions
- Validate database migrations
- Test API responses
