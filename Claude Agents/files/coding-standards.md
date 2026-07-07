# Coding Standards

## Python
- Formatter: Black (line-length 100)
- Linter: Ruff (all rules enabled except conflicting with Black)
- Type checker: mypy --strict
- Python 3.12+ features allowed (type parameter syntax, etc.)

## Naming
- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private: `_single_underscore` prefix
- Database tables: `snake_case` (plural: `transactions`, `invoices`)
- Database columns: `snake_case`
- API endpoints: `kebab-case` in URLs, `snake_case` in JSON bodies
- Environment variables: `UPPER_SNAKE_CASE` with `JARVIS_` prefix

## Imports
```python
# Standard library
import os
from datetime import datetime
from decimal import Decimal
from uuid import UUID

# Third party
from fastapi import APIRouter, Depends
from sqlalchemy import select
from pydantic import BaseModel

# Local
from jarvis.shared.models import AuditMixin
from jarvis.accounting_core.services import GLService
```

## Type Hints
- Required on all function signatures (params + return)
- Use `X | None` not `Optional[X]`
- Use `list[X]` not `List[X]`
- Use `dict[K, V]` not `Dict[K, V]`
- Pydantic models for complex structures

## Docstrings
```python
async def import_statement(
    file: UploadFile,
    bank_account_id: UUID,
    match_vendors: bool = True,
) -> ImportResult:
    """Import a bank statement PDF and create transactions.

    Parses the PDF, extracts transactions, deduplicates against existing
    records, optionally matches vendors, and returns the import result.

    Raises:
        StatementParseError: If PDF cannot be parsed.
        DuplicateTransactionError: If all transactions already exist.
    """
```

## Function Size
- Max 50 lines per function. If longer, decompose.
- Max 5 parameters. If more, use a Pydantic model or dataclass.
- Max 3 levels of nesting. If deeper, extract helper functions.

## Financial Specifics
- ALL monetary values: `Decimal` (never `float`)
- ALL monetary calculations: explicit rounding with `ROUND_HALF_UP`
- ALL monetary comparisons: use `Decimal` equality, not approximate
- ALL monetary formatting: use locale-aware formatters for display
