# Testing Standards

## Coverage Thresholds
- `accounting_core`: 80% minimum (strict — money logic)
- `bank_import`: 80% minimum (strict — parsing accuracy)
- `reconciliation`: 75% minimum
- All other modules: 70% minimum
- New features: must include tests in the same PR

## Test Organization
```
module/
└── tests/
    ├── conftest.py              # Shared fixtures for this module
    ├── factories.py             # Test data factories
    ├── test_service.py          # Service layer tests
    ├── test_repository.py       # Data access tests
    ├── test_models.py           # Model validation tests
    ├── test_integration.py      # End-to-end within module
    └── test_edge_cases.py       # Boundary values, errors
```

## Test Naming
```python
# Pattern: test_{action}_{scenario}_{expected_result}
def test_create_transaction_with_valid_data_succeeds(): ...
def test_create_transaction_with_duplicate_raises_conflict(): ...
def test_import_statement_with_empty_pdf_raises_parse_error(): ...
def test_reconcile_with_exact_match_auto_confirms(): ...
```

## Fixtures
```python
@pytest.fixture
async def db_session():
    """Provides a clean database session that rolls back after test."""
    async with async_session() as session:
        async with session.begin():
            yield session
            await session.rollback()

@pytest.fixture
def sample_transaction_data():
    return TransactionCreate(
        amount=Decimal("1234.56"),
        currency="EUR",
        date=date(2025, 1, 15),
        reference="TXN-001",
        description="Payment from ACME Corp",
    )
```

## Rules
- Never use `float` for monetary assertions — always `Decimal`
- Never hit real external APIs — mock ANAF, Shopify, LLM providers
- Never share state between tests — each test is independent
- Always test error paths, not just happy paths
- Always verify audit trails are created for financial operations
- Always verify idempotency for import/sync operations
