# Git Workflow

## Commit Messages
Format: `type(scope): description`

Types: feat, fix, refactor, test, docs, chore, perf
Scopes: accounting_core, bank_import, invoicing, reconciliation, reporting, archive, ai_agent, vendors, ro_efactura, crypto_rates, shared, infra

Examples:
```
feat(bank_import): add UniCredit PDF statement parser
fix(accounting_core): correct GL balance validation for multi-currency
refactor(vendors): extract fuzzy matching into dedicated service
test(reconciliation): add edge cases for split transaction matching
docs(ai_agent): document RAG pipeline configuration
perf(reporting): add composite index on transaction date + account
```

## Branch Naming
```
feature/module-name-brief-description
fix/module-name-brief-description
refactor/module-name-brief-description
```

## Rules
- One logical change per commit
- Never mix feature code with refactoring in same commit
- Never commit broken tests
- Never commit secrets, .env files, or credentials
- Always run `pytest` before pushing
- Migrations get their own commit: `chore(db): add transactions table migration`
