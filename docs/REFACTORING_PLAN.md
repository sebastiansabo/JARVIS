# JARVIS Architecture Refactoring Plan

## Executive Summary

This document outlines the plan to refactor JARVIS from direct database access in routes to a proper layered architecture with service and repository layers.

**Estimated Total Effort:** 3-4 weeks of focused development
**Risk Level:** Medium (existing functionality must continue working)
**Recommended Approach:** Incremental, module-by-module

---

## Current Architecture Issues

### 1. Layer Violations (Architecture Hook)
Routes directly import and call database functions:
```python
# Current (BAD)
@bp.route('/api/employees')
def get_employees():
    from database import get_db, get_cursor
    cursor.execute("SELECT * FROM employees")
    return jsonify(rows)
```

### 2. SQL Patterns (Database Hook - False Positives)
The hook flags f-strings in SQL, but our pattern is actually safe:
```python
# This is SAFE - ph is a placeholder variable, not user input
cursor.execute(f'SELECT * FROM users WHERE id = {ph}', (user_id,))
```
**Action:** Update hook to recognize `{ph}` pattern as safe.

### 3. N+1 Queries (Performance Hook)
45 instances of potential N+1 queries detected.
**Action:** Review and optimize after architecture refactoring.

---

## Target Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       HTTP Layer                             │
│  routes.py - Only HTTP concerns (request/response)          │
│  - Parse request parameters                                  │
│  - Call service methods                                      │
│  - Format and return responses                               │
│  - Handle HTTP errors                                        │
└─────────────────────────┬───────────────────────────────────┘
                          │ calls
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                     Service Layer                            │
│  services.py - Business logic                                │
│  - Validate business rules                                   │
│  - Orchestrate operations                                    │
│  - Handle transactions                                       │
│  - Transform data                                            │
└─────────────────────────┬───────────────────────────────────┘
                          │ calls
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   Repository Layer                           │
│  repositories.py - Data access                               │
│  - CRUD operations                                           │
│  - Query building                                            │
│  - Result mapping                                            │
└─────────────────────────┬───────────────────────────────────┘
                          │ uses
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   Database Layer                             │
│  database.py - Connection management                         │
│  - Connection pooling                                        │
│  - Transaction management                                    │
│  - Cursor handling                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Module-by-Module Refactoring Plan

### Phase 1: Auth Module (Week 1, Days 1-2)

**Current State:**
- Location: `jarvis/core/auth/routes.py`
- Endpoints: 5 (login, logout, change_password, etc.)
- Database calls: Direct

**Files to Create:**
```
jarvis/core/auth/
├── __init__.py          (exists)
├── routes.py            (refactor)
├── services.py          (NEW)
├── repositories.py      (NEW)
└── models.py            (exists)
```

**Refactoring Steps:**

1. **Create `repositories.py`:**
```python
# jarvis/core/auth/repositories.py
from typing import Optional, Dict, Any
from jarvis.core.database import get_db_connection

class UserRepository:
    def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM users WHERE username = %s",
                (username,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        ...

    def update_password(self, user_id: int, password_hash: str) -> bool:
        ...

    def log_event(self, user_id: int, event_type: str, details: str) -> None:
        ...
```

2. **Create `services.py`:**
```python
# jarvis/core/auth/services.py
from typing import Optional
from .repositories import UserRepository
from .models import User
import bcrypt

class AuthService:
    def __init__(self):
        self.user_repo = UserRepository()

    def authenticate(self, username: str, password: str) -> Optional[User]:
        user_data = self.user_repo.get_by_username(username)
        if not user_data:
            return None

        if not bcrypt.checkpw(password.encode(), user_data['password'].encode()):
            return None

        self.user_repo.log_event(user_data['id'], 'login', 'Successful login')
        return User(user_data)

    def change_password(self, user_id: int, old_password: str, new_password: str) -> bool:
        user_data = self.user_repo.get_by_id(user_id)
        if not user_data:
            return False

        if not bcrypt.checkpw(old_password.encode(), user_data['password'].encode()):
            return False

        new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        return self.user_repo.update_password(user_id, new_hash)
```

3. **Refactor `routes.py`:**
```python
# jarvis/core/auth/routes.py
from flask import Blueprint, request, jsonify, redirect, url_for
from flask_login import login_user, logout_user, login_required, current_user
from .services import AuthService

bp = Blueprint('auth', __name__)
auth_service = AuthService()

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = auth_service.authenticate(username, password)
        if user:
            login_user(user)
            return redirect(url_for('main.index'))

        return render_template('login.html', error='Invalid credentials')

    return render_template('login.html')
```

**Validation:**
- Run `python hooks/architecture_hook.py jarvis/core/auth`
- Should pass with no violations

---

### Phase 2: HR Events Module (Week 1, Days 3-5)

**Current State:**
- Location: `jarvis/hr/events/routes.py`
- Endpoints: ~30 (employees, events, bonuses, structure)
- Database calls: 28 direct imports

**Files to Create:**
```
jarvis/hr/events/
├── __init__.py          (exists)
├── routes.py            (refactor)
├── services/            (NEW directory)
│   ├── __init__.py
│   ├── employee_service.py
│   ├── event_service.py
│   └── bonus_service.py
├── repositories/        (NEW directory)
│   ├── __init__.py
│   ├── employee_repo.py
│   ├── event_repo.py
│   └── bonus_repo.py
└── database.py          (exists - move to repositories)
```

**Key Refactoring Tasks:**

1. **Group endpoints by domain:**
   - Employee endpoints → `EmployeeService` + `EmployeeRepository`
   - Event endpoints → `EventService` + `EventRepository`
   - Bonus endpoints → `BonusService` + `BonusRepository`
   - Structure endpoints → `StructureService` + `StructureRepository`

2. **Example Employee Service:**
```python
# jarvis/hr/events/services/employee_service.py
from typing import List, Optional, Dict, Any
from ..repositories.employee_repo import EmployeeRepository

class EmployeeService:
    def __init__(self):
        self.repo = EmployeeRepository()

    def get_all(self, filters: Dict[str, Any] = None) -> List[Dict]:
        return self.repo.find_all(filters)

    def get_by_id(self, employee_id: int) -> Optional[Dict]:
        return self.repo.find_by_id(employee_id)

    def create(self, data: Dict[str, Any]) -> Dict:
        # Validate business rules
        if not data.get('name'):
            raise ValueError("Employee name is required")

        # Check for duplicates
        existing = self.repo.find_by_name(data['name'])
        if existing:
            raise ValueError("Employee already exists")

        return self.repo.create(data)

    def update(self, employee_id: int, data: Dict[str, Any]) -> Dict:
        existing = self.repo.find_by_id(employee_id)
        if not existing:
            raise ValueError("Employee not found")

        return self.repo.update(employee_id, data)

    def delete(self, employee_id: int) -> bool:
        # Check for dependencies (bonuses, etc.)
        if self.repo.has_bonuses(employee_id):
            raise ValueError("Cannot delete employee with existing bonuses")

        return self.repo.delete(employee_id)
```

3. **Refactor routes to use services:**
```python
# jarvis/hr/events/routes.py
from flask import Blueprint, request, jsonify
from .services.employee_service import EmployeeService

bp = Blueprint('hr_events', __name__, url_prefix='/hr/events')
employee_service = EmployeeService()

@bp.route('/api/employees', methods=['GET'])
def get_employees():
    filters = {
        'company': request.args.get('company'),
        'brand': request.args.get('brand'),
        'is_active': request.args.get('is_active', 'true') == 'true'
    }
    employees = employee_service.get_all(filters)
    return jsonify(employees)

@bp.route('/api/employees', methods=['POST'])
def create_employee():
    try:
        employee = employee_service.create(request.json)
        return jsonify(employee), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
```

---

### Phase 3: Statements Module (Week 2, Days 1-3)

**Current State:**
- Location: `jarvis/accounting/statements/routes.py`
- Endpoints: ~20 (upload, transactions, mappings, invoices)
- Has existing `database.py` with functions

**Files to Create:**
```
jarvis/accounting/statements/
├── __init__.py          (exists)
├── routes.py            (refactor)
├── services/            (NEW)
│   ├── __init__.py
│   ├── statement_service.py
│   ├── transaction_service.py
│   └── mapping_service.py
├── repositories/        (NEW)
│   ├── __init__.py
│   ├── transaction_repo.py
│   └── mapping_repo.py
├── database.py          (exists - migrate to repos)
└── parser.py            (exists)
```

**Key Tasks:**
1. Convert `database.py` functions to `TransactionRepository` class
2. Create `StatementService` for upload/parsing logic
3. Create `MappingService` for vendor mapping logic
4. Refactor routes to use services

---

### Phase 4: e-Factura Connector (Week 2, Days 4-5)

**Current State:**
- Location: `jarvis/core/connectors/efactura/routes.py`
- Has good separation already (client, parser, repo)
- Some direct database access in routes

**Files to Update:**
```
jarvis/core/connectors/efactura/
├── __init__.py
├── routes.py            (refactor)
├── services.py          (NEW - orchestration)
├── anaf_client.py       (exists)
├── xml_parser.py        (exists)
└── repositories/
    └── invoice_repo.py  (exists)
```

**Tasks:**
1. Create `EfacturaService` to orchestrate operations
2. Move business logic from routes to service
3. Routes only handle HTTP concerns

---

### Phase 5: Core/Main App (Week 3)

**Current State:**
- Location: `jarvis/app.py`
- Endpoints: ~50 (invoices, allocations, templates, etc.)
- Largest file, most complex

**Approach:**
Split into domain-specific modules:
```
jarvis/accounting/bugetare/
├── __init__.py
├── routes.py
├── services/
│   ├── invoice_service.py
│   ├── allocation_service.py
│   └── template_service.py
└── repositories/
    ├── invoice_repo.py
    ├── allocation_repo.py
    └── template_repo.py
```

---

## Hook Adjustments

### 1. Update Database Hook (Immediate)

Add pattern recognition for safe placeholder usage:

```python
# hooks/database_hook.py
# Add to SQL_INJECTION_PATTERNS whitelist
SAFE_PATTERNS = [
    r"execute\s*\(\s*f['\"][^'\"]*\{ph\}",  # Placeholder pattern
    r"execute\s*\(\s*f['\"][^'\"]*\{get_placeholder\(\)\}",
]
```

### 2. Update Architecture Hook

Add module-level exceptions during transition:

```python
# hooks/architecture_hook.py
TRANSITION_EXCEPTIONS = [
    "jarvis/app.py",  # Legacy - will be refactored in Phase 5
]
```

---

## Testing Strategy

### For Each Module Refactored:

1. **Before refactoring:**
   - Document existing behavior
   - Ensure existing tests pass
   - Note any integration points

2. **During refactoring:**
   - Write unit tests for new services
   - Write unit tests for repositories
   - Use mocks to isolate layers

3. **After refactoring:**
   - Run integration tests
   - Manual testing of endpoints
   - Run hooks validation

### Test File Structure:
```
tests/
├── unit/
│   ├── auth/
│   │   ├── test_auth_service.py
│   │   └── test_user_repository.py
│   ├── hr/
│   │   ├── test_employee_service.py
│   │   └── test_employee_repository.py
│   └── ...
└── integration/
    ├── test_auth_endpoints.py
    ├── test_hr_endpoints.py
    └── ...
```

---

## Rollback Plan

Each phase is independent. If issues arise:

1. **Revert commits** for that phase only
2. **Keep old code** in `_legacy.py` files during transition
3. **Feature flags** for gradual rollout (optional)

---

## Success Criteria

### Per Module:
- [ ] No architecture hook violations
- [ ] No database hook violations (excluding known patterns)
- [ ] All existing tests pass
- [ ] New unit tests achieve 80%+ coverage
- [ ] Manual testing confirms functionality

### Overall:
- [ ] All 7 hooks pass
- [ ] No regressions in functionality
- [ ] Clear separation of concerns
- [ ] Improved testability

---

## Timeline Summary

| Phase | Module | Duration | Dependencies |
|-------|--------|----------|--------------|
| 1 | Auth | 2 days | None |
| 2 | HR Events | 3 days | Phase 1 (patterns established) |
| 3 | Statements | 3 days | Phase 1-2 |
| 4 | e-Factura | 2 days | Phase 1-3 |
| 5 | Core/Main | 5 days | Phase 1-4 |
| - | Testing & Polish | 3-5 days | Phase 1-5 |

**Total: 18-20 working days (3-4 weeks)**

---

## Immediate Actions (Before Full Refactor)

1. **Update hooks to reduce false positives:**
   - Add `{ph}` pattern to safe list
   - Add transition exceptions for legacy files

2. **Create service layer template:**
   - Standard patterns for all modules
   - Shared base classes if needed

3. **Document existing endpoints:**
   - API documentation for each module
   - Expected request/response formats

---

## Questions to Resolve

1. **Dependency Injection:** Use simple instantiation or DI framework?
   - Recommendation: Simple instantiation (Flask-style)

2. **Transaction Management:** Service layer or repository layer?
   - Recommendation: Service layer (business transaction boundaries)

3. **Error Handling:** Custom exceptions or standard Python?
   - Recommendation: Custom exceptions per domain

4. **Logging:** Where to add structured logging?
   - Recommendation: Service layer (business events)

---

*Document created: 2026-01-27*
*Last updated: 2026-01-27*
*Author: Claude Code Assistant*
