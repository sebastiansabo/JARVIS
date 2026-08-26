# Category-based Rental Tariffs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Foi de Parcurs courtesy-car ("Mașini de curtoazie") rentals a category × duration-interval price matrix, replacing the per-car flat `svc_tariff_eur_day/month`.

**Architecture:** Three new per-company tables (`fp_rental_intervals`, `fp_rental_categories`, `fp_rental_category_prices`) + `fp_vehicles.rental_category_id`. A car carries a category; the rental price = the category's €/day for the interval matching the rental's day-count. Interval-selection + total are pure functions (`rental_pricing.py`); a repository does the DB; the result maps onto the *existing* `svc_*` snapshot so the contract PDF and every `{svc_*}` token are unchanged. Legacy per-car pricing stays as a fallback for un-categorized cars.

**Tech Stack:** Python 3 / Flask (repository pattern: routes → services → repositories → `BaseRepository`); PostgreSQL (idempotent DDL in `migrations/domains/schema_incremental.py`); React 19 + TS + Tailwind + shadcn/ui + @tanstack/react-query; pytest (psycopg2 pool mocked globally in `jarvis/conftest.py`); vitest.

**Spec:** `docs/superpowers/specs/2026-08-26-foi-parcurs-rental-category-tariffs-design.md`

## Global Constraints

- All tariffs are **EUR, ex-VAT** (per the Sharetoo PDF). Amounts stored `NUMERIC(10,2)`.
- The Sharetoo seed loads **for company_id 11 only** (Autoworld PREMIUM); every seed insert is `ON CONFLICT DO NOTHING` so re-runs and other companies are untouched.
- **Back-compat:** a car with no `rental_category_id` keeps the legacy per-car pricing path. Existing `svc_tariff_eur_*` columns are retained; category pricing does not delete or rewrite them.
- Migration is **additive + idempotent**: `CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS` (DO-block guarded), `ON CONFLICT DO NOTHING`, SAVEPOINT-scoped seeds (same discipline as `_seed_document_types`).
- **Repository pattern:** no SQL in routes; routes call repositories. Repos extend `BaseRepository` (`query_one`/`query_all`/`execute`).
- **Tests:** psycopg2 is mocked in `jarvis/conftest.py`, so repo tests stub the repo's `query_one`/`query_all`/`execute` (see `jarvis/tests/foi_parcurs/test_general_conditions.py` for the exact pattern); route tests register `foi_parcurs_bp` on a bare Flask app with `LOGIN_DISABLED=True` and `monkeypatch` the module's repo singletons / `_is_admin`.
- Datetimes are naive wall-clock by convention; reuse `rental_pricing.rental_days`.
- UI copy is Romanian.
- Admin-only writes: reuse the `role_name in ('admin','superadmin')` gate from `routes/document_types.py`.

---

### Task 1: Pricing math — `select_interval` + `compute_category_pricing`

Pure functions. No DB. This is the foundation the repo and the pricing wiring build on.

**Files:**
- Modify: `jarvis/foi_parcurs/services/rental_pricing.py` (append two functions)
- Test: `jarvis/tests/foi_parcurs/test_rental_pricing.py` (new)

**Interfaces:**
- Consumes: nothing (pure).
- Produces:
  - `select_interval(intervals: list[dict], days: int) -> dict | None` — `intervals` are dicts with at least `min_days` (int) and `max_days` (int | None; None = open-ended). Returns the matching interval dict, or None.
  - `compute_category_pricing(days: int, eur_per_day, franchise_eur, extra_km_eur, km_included_day) -> dict` — returns the `svc_*` snapshot keys `svc_rate_basis='day'`, `svc_tariff_eur`, `svc_units`, `svc_total_eur`, `svc_km_included_day`, `svc_extra_km_eur`, `svc_fransiza_eur` (NOT `svc_garantie_eur` — the deposit stays from policy in Task 7).

- [ ] **Step 1: Write the failing tests**

Create `jarvis/tests/foi_parcurs/test_rental_pricing.py`:

```python
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from foi_parcurs.services.rental_pricing import select_interval, compute_category_pricing

INTERVALS = [
    {'id': 1, 'min_days': 1, 'max_days': 8},
    {'id': 2, 'min_days': 9, 'max_days': 30},
    {'id': 3, 'min_days': 31, 'max_days': 90},
    {'id': 4, 'min_days': 91, 'max_days': 180},
    {'id': 5, 'min_days': 181, 'max_days': None},
]


def test_select_interval_lower_boundary():
    assert select_interval(INTERVALS, 1)['id'] == 1
    assert select_interval(INTERVALS, 8)['id'] == 1


def test_select_interval_crosses_boundary():
    assert select_interval(INTERVALS, 9)['id'] == 2
    assert select_interval(INTERVALS, 30)['id'] == 2
    assert select_interval(INTERVALS, 31)['id'] == 3
    assert select_interval(INTERVALS, 180)['id'] == 4


def test_select_interval_open_ended_top_band():
    assert select_interval(INTERVALS, 181)['id'] == 5
    assert select_interval(INTERVALS, 5000)['id'] == 5


def test_select_interval_no_match_returns_none():
    assert select_interval(INTERVALS, 0) is None
    assert select_interval([], 5) is None


def test_select_interval_unsorted_input():
    shuffled = list(reversed(INTERVALS))
    assert select_interval(shuffled, 15)['id'] == 2


def test_compute_category_pricing_multiplies_and_rounds():
    snap = compute_category_pricing(10, 33, 250, 0.25, 300)
    assert snap['svc_rate_basis'] == 'day'
    assert snap['svc_tariff_eur'] == 33
    assert snap['svc_units'] == 10
    assert snap['svc_total_eur'] == 330.0
    assert snap['svc_km_included_day'] == 300
    assert snap['svc_extra_km_eur'] == 0.25
    assert snap['svc_fransiza_eur'] == 250
    assert 'svc_garantie_eur' not in snap


def test_compute_category_pricing_none_rate_is_zero():
    snap = compute_category_pricing(5, None, None, None, None)
    assert snap['svc_tariff_eur'] == 0
    assert snap['svc_total_eur'] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jarvis && python -m pytest tests/foi_parcurs/test_rental_pricing.py -v`
Expected: FAIL with `ImportError: cannot import name 'select_interval'`.

- [ ] **Step 3: Implement the two functions**

Append to `jarvis/foi_parcurs/services/rental_pricing.py`:

```python
def select_interval(intervals, days: int):
    """Pick the duration interval whose [min_days, max_days] contains `days`.

    intervals: dicts with 'min_days' (int) and 'max_days' (int or None; None =
    open-ended top band). Returns the matching dict, or None when no interval
    covers `days`. Sorted by min_days so an unordered input still resolves
    deterministically."""
    for iv in sorted(intervals or [], key=lambda x: x['min_days']):
        hi = iv.get('max_days')
        if days >= iv['min_days'] and (hi is None or days <= hi):
            return iv
    return None


def compute_category_pricing(days: int, eur_per_day, franchise_eur,
                             extra_km_eur, km_included_day) -> dict:
    """Build the rent-a-car svc_* snapshot from a resolved category price.

    Pure: `eur_per_day`/franchise/extra-km come from the car's category, the
    interval is already resolved (its rate is `eur_per_day`), and the km-included
    default comes from company policy. The deposit (svc_garantie_eur) is NOT set
    here — it is layered on from policy by the caller, mirroring
    compute_service_pricing's split."""
    rate = eur_per_day or 0
    return {
        'svc_rate_basis': 'day',
        'svc_tariff_eur': rate,
        'svc_units': days,
        'svc_total_eur': round(rate * days, 2),
        'svc_km_included_day': km_included_day,
        'svc_extra_km_eur': extra_km_eur,
        'svc_fransiza_eur': franchise_eur,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jarvis && python -m pytest tests/foi_parcurs/test_rental_pricing.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add jarvis/foi_parcurs/services/rental_pricing.py jarvis/tests/foi_parcurs/test_rental_pricing.py
git commit -m "feat(foi-parcurs): pure interval-select + category pricing math"
```

---

### Task 2: Sharetoo seed-data module

The Sharetoo scheme as a pure Python constant (so the numbers are unit-testable and the migration just imports + inserts). Transmission is folded into `models_note` (not a pricing axis).

**Files:**
- Create: `jarvis/foi_parcurs/services/rental_tariff_seed.py`
- Test: `jarvis/tests/foi_parcurs/test_rental_tariff_seed.py` (new)

**Interfaces:**
- Produces:
  - `SHARETOO_INTERVALS: list[tuple]` — `(label, min_days, max_days, sort_order)`.
  - `SHARETOO_CATEGORIES: list[tuple]` — `(name, models_note, franchise_eur, extra_km_eur, prices)` where `prices` is a 5-tuple of `eur_per_day` aligned to `SHARETOO_INTERVALS` order.
  - `SHARETOO_COMPANY_ID = 11`.

- [ ] **Step 1: Write the failing tests**

Create `jarvis/tests/foi_parcurs/test_rental_tariff_seed.py`:

```python
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from foi_parcurs.services.rental_tariff_seed import (
    SHARETOO_INTERVALS, SHARETOO_CATEGORIES, SHARETOO_COMPANY_ID,
)


def test_five_intervals_open_ended_top():
    assert len(SHARETOO_INTERVALS) == 5
    assert SHARETOO_INTERVALS[0][1] == 1 and SHARETOO_INTERVALS[0][2] == 8
    assert SHARETOO_INTERVALS[-1][1] == 181 and SHARETOO_INTERVALS[-1][2] is None


def test_eighteen_categories_each_with_five_prices():
    assert len(SHARETOO_CATEGORIES) == 18
    for name, note, fr, ekm, prices in SHARETOO_CATEGORIES:
        assert len(prices) == 5, name
        assert all(p > 0 for p in prices), name
        assert fr > 0 and ekm > 0, name


def test_spot_check_known_cells():
    by_name = {c[0]: c for c in SHARETOO_CATEGORIES}
    # SUV+ : 33/31/28/24/23, franchise 250, extra-km 0.25
    assert by_name['SUV+'][2] == 250
    assert by_name['SUV+'][3] == 0.25
    assert by_name['SUV+'][4] == (33, 31, 28, 24, 23)
    # LUXURY : 105/99/94/86/80, franchise 500, extra-km 0.50
    assert by_name['LUXURY'][4] == (105, 99, 94, 86, 80)
    assert by_name['LUXURY'][2] == 500
    # PREMIUM + : 45/42/32/30/29
    assert by_name['PREMIUM +'][4] == (45, 42, 32, 30, 29)


def test_company_is_autoworld_premium():
    assert SHARETOO_COMPANY_ID == 11
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jarvis && python -m pytest tests/foi_parcurs/test_rental_tariff_seed.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'foi_parcurs.services.rental_tariff_seed'`.

- [ ] **Step 3: Create the seed-data module**

Create `jarvis/foi_parcurs/services/rental_tariff_seed.py`:

```python
"""SHARETOO RENT corporate tariff scheme (Octombrie 2025), transcribed from
`Tarife Coporate - Sharetoo Rent Octombrie 2025.pdf`. Pure data — imported by
the schema-incremental seed to populate the rental-tariff tables for Autoworld
PREMIUM (company_id 11). All amounts EUR ex-VAT. Transmission is folded into
`models_note` (it is not a pricing dimension). Daily rates only; the PDF's
monthly-estimate columns are intentionally omitted (deferred)."""

SHARETOO_COMPANY_ID = 11

# (label, min_days, max_days, sort_order); max_days None = open-ended top band.
SHARETOO_INTERVALS = [
    ('1-8 zile',     1,    8, 0),
    ('9-30 zile',    9,   30, 1),
    ('31-90 zile',  31,   90, 2),
    ('91-180 zile', 91,  180, 3),
    ('181+ zile',  181, None, 4),
]

# (name, models_note, franchise_eur, extra_km_eur, prices) — prices align to
# SHARETOO_INTERVALS order (1-8 / 9-30 / 31-90 / 91-180 / 181+), EUR per day.
SHARETOO_CATEGORIES = [
    ('ECONOMY',          'Skoda Fabia, VW Polo (manuală)',                                        200, 0.25, (20, 18, 16, 15, 14)),
    ('ECONOMY +',        'Skoda Fabia, VW Polo (automată)',                                       200, 0.25, (21, 19, 18, 17, 16)),
    ('INTERMEDIATE',     'VW T-Cross, Skoda Kamiq (manuală)',                                     200, 0.25, (22, 20, 19, 18, 17)),
    ('INTERMEDIATE +',   'Skoda Scala, VW T-Cross, Skoda Kamiq, Seat Arona, VW Taigo (automată)', 200, 0.25, (24, 21, 20, 19, 18)),
    ('COMPACT',          'VW Golf, Skoda Octavia, Seat & Cupra Leon (manuală)',                   200, 0.25, (25, 23, 21, 20, 19)),
    ('COMPACT +',        'VW Golf, Skoda Octavia, Seat & Cupra Leon, Audi A3 (automată)',         200, 0.25, (30, 26, 23, 22, 21)),
    ('SUV',              'Skoda Karoq, VW T-Roc (manuală)',                                       200, 0.25, (31, 29, 26, 24, 22)),
    ('SUV+',             'Skoda Karoq, VW T-Roc, Cupra Formentor (automată)',                     250, 0.25, (33, 31, 28, 24, 23)),
    ('ELECTRIC COMPACT', 'VW ID3',                                                                250, 0.25, (36, 32, 30, 28, 27)),
    ('PREMIUM',          'Skoda Superb, VW Passat, VW Arteon',                                    250, 0.35, (36, 32, 29, 27, 26)),
    ('PREMIUM SUV',      'VW Tiguan, Audi Q3, Skoda Kodiaq, Seat Tarraco, Cupra Terramar',        250, 0.35, (40, 35, 30, 28, 27)),
    ('ELECTRIC SUV',     'VW ID4',                                                                300, 0.35, (44, 40, 38, 35, 34)),
    ('PREMIUM +',        'Audi A4 / Audi A5',                                                     250, 0.35, (45, 42, 32, 30, 29)),
    ('PREMIUM SUV +',    'Audi Q5',                                                               300, 0.50, (55, 49, 40, 38, 37)),
    ('EXECUTIVE',        'Audi A6',                                                               300, 0.50, (61, 57, 50, 47, 45)),
    ('EXECUTIVE +',      'VW Touareg, Audi Q7, Porsche Macan',                                    400, 0.50, (84, 81, 70, 66, 62)),
    ('LUXURY',           'Audi Q8',                                                               500, 0.50, (105, 99, 94, 86, 80)),
    ('PICKUP',           'VW Amarok',                                                             300, 0.35, (51, 48, 44, 42, 40)),
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jarvis && python -m pytest tests/foi_parcurs/test_rental_tariff_seed.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add jarvis/foi_parcurs/services/rental_tariff_seed.py jarvis/tests/foi_parcurs/test_rental_tariff_seed.py
git commit -m "feat(foi-parcurs): Sharetoo rental tariff seed data (18 categories)"
```

---

### Task 3: `RentalCategoryRepository`

DB access for intervals, categories (+ their price grid), and the `price_for` lookup used by pricing.

**Files:**
- Create: `jarvis/foi_parcurs/repositories/rental_category_repository.py`
- Test: `jarvis/tests/foi_parcurs/test_rental_category_repository.py` (new)

**Interfaces:**
- Consumes: `rental_pricing.select_interval` (Task 1); `BaseRepository`.
- Produces `RentalCategoryRepository` with:
  - `list_intervals(company_id) -> list[dict]`
  - `upsert_interval(company_id, interval_id, label, min_days, max_days, sort_order) -> dict` (returns `{id}`)
  - `delete_interval(company_id, interval_id)` — refuses if any price rows reference it (`ValueError`)
  - `list_categories(company_id, active_only=False) -> list[dict]` — each row gets a `prices` dict `{interval_id: eur_per_day}`
  - `add_category(company_id, name) -> dict` (returns `{id}`; blank/duplicate name → `ValueError`)
  - `upsert_category(company_id, category_id, name, models_note, franchise_eur, extra_km_eur, sort_order, is_active) -> dict`
  - `delete_category(company_id, category_id)` — refuses if any `fp_vehicles.rental_category_id` references it (`ValueError`)
  - `set_price(company_id, category_id, interval_id, eur_per_day)`
  - `price_for(company_id, category_id, days) -> dict | None` — `{eur_per_day, interval_id, interval_label, franchise_eur, extra_km_eur}`

- [ ] **Step 1: Write the failing tests**

Create `jarvis/tests/foi_parcurs/test_rental_category_repository.py`:

```python
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from unittest.mock import MagicMock
import pytest
from foi_parcurs.repositories.rental_category_repository import RentalCategoryRepository


def _repo():
    return RentalCategoryRepository()


def test_list_categories_attaches_price_map():
    repo = _repo()
    repo.query_all = MagicMock(side_effect=[
        [{'id': 7, 'name': 'SUV+', 'franchise_eur': 250, 'extra_km_eur': 0.25,
          'models_note': 'x', 'sort_order': 0, 'is_active': True}],   # categories
        [{'category_id': 7, 'interval_id': 2, 'eur_per_day': 31},
         {'category_id': 7, 'interval_id': 1, 'eur_per_day': 33}],    # prices
    ])
    cats = repo.list_categories(11)
    assert cats[0]['prices'] == {2: 31, 1: 33}


def test_price_for_uses_selected_interval():
    repo = _repo()
    repo.query_one = MagicMock(side_effect=[
        {'id': 7, 'franchise_eur': 250, 'extra_km_eur': 0.25},   # category
        {'eur_per_day': 28},                                     # price row
    ])
    repo.query_all = MagicMock(return_value=[
        {'id': 1, 'min_days': 1, 'max_days': 8},
        {'id': 3, 'min_days': 31, 'max_days': 90},
    ])
    out = repo.price_for(11, 7, 45)   # 45 days -> interval id 3
    assert out['eur_per_day'] == 28
    assert out['interval_id'] == 3
    assert out['franchise_eur'] == 250
    assert out['extra_km_eur'] == 0.25


def test_price_for_missing_category_returns_none():
    repo = _repo()
    repo.query_one = MagicMock(return_value=None)
    assert repo.price_for(11, 999, 5) is None


def test_price_for_no_matching_interval_returns_none():
    repo = _repo()
    repo.query_one = MagicMock(return_value={'id': 7, 'franchise_eur': 250, 'extra_km_eur': 0.25})
    repo.query_all = MagicMock(return_value=[{'id': 1, 'min_days': 10, 'max_days': 20}])
    assert repo.price_for(11, 7, 5) is None


def test_delete_category_refuses_when_cars_reference_it():
    repo = _repo()
    repo.query_one = MagicMock(return_value={'n': 3})
    with pytest.raises(ValueError):
        repo.delete_category(11, 7)


def test_add_category_rejects_blank_name():
    repo = _repo()
    with pytest.raises(ValueError):
        repo.add_category(11, '   ')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jarvis && python -m pytest tests/foi_parcurs/test_rental_category_repository.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the repository**

Create `jarvis/foi_parcurs/repositories/rental_category_repository.py`:

```python
"""Data access for the courtesy-car rental tariff scheme (per company):
duration intervals, categories, and the category × interval €/day price grid.
A car's `rental_category_id` + the rental day-count resolve to a €/day via
`price_for`. Interval selection is the pure `rental_pricing.select_interval`."""
from core.base_repository import BaseRepository
from ..services.rental_pricing import select_interval


class RentalCategoryRepository(BaseRepository):

    # ── intervals ───────────────────────────────────────────────────────────
    def list_intervals(self, company_id) -> list:
        if not company_id:
            return []
        return self.query_all(
            '''SELECT id, label, min_days, max_days, sort_order
               FROM fp_rental_intervals
               WHERE company_id = %s
               ORDER BY sort_order, min_days''',
            (company_id,),
        ) or []

    def upsert_interval(self, company_id, interval_id, label, min_days,
                        max_days, sort_order):
        if not company_id:
            raise ValueError('company_id required')
        if min_days is None:
            raise ValueError('min_days required')
        if interval_id:
            return self.execute(
                '''UPDATE fp_rental_intervals
                   SET label=%s, min_days=%s, max_days=%s, sort_order=%s
                   WHERE id=%s AND company_id=%s RETURNING id''',
                (label, min_days, max_days, sort_order or 0, interval_id, company_id),
                returning=True,
            )
        return self.execute(
            '''INSERT INTO fp_rental_intervals
                   (company_id, label, min_days, max_days, sort_order)
               VALUES (%s, %s, %s, %s, %s) RETURNING id''',
            (company_id, label, min_days, max_days, sort_order or 0),
            returning=True,
        )

    def delete_interval(self, company_id, interval_id):
        used = self.query_one(
            'SELECT COUNT(*) AS n FROM fp_rental_category_prices '
            'WHERE company_id=%s AND interval_id=%s',
            (company_id, interval_id),
        ) or {}
        if int(used.get('n') or 0):
            raise ValueError('Intervalul are prețuri asociate — șterge întâi prețurile.')
        return self.execute(
            'DELETE FROM fp_rental_intervals WHERE company_id=%s AND id=%s',
            (company_id, interval_id),
        )

    # ── categories (+ price grid) ───────────────────────────────────────────
    def list_categories(self, company_id, active_only=False) -> list:
        if not company_id:
            return []
        where = 'WHERE company_id = %s'
        params = [company_id]
        if active_only:
            where += ' AND is_active = TRUE'
        cats = self.query_all(
            f'''SELECT id, name, models_note, franchise_eur, extra_km_eur,
                       sort_order, is_active
                FROM fp_rental_categories {where}
                ORDER BY sort_order, name''',
            tuple(params),
        ) or []
        prices = self.query_all(
            'SELECT category_id, interval_id, eur_per_day '
            'FROM fp_rental_category_prices WHERE company_id = %s',
            (company_id,),
        ) or []
        by_cat = {}
        for p in prices:
            by_cat.setdefault(p['category_id'], {})[p['interval_id']] = p['eur_per_day']
        for c in cats:
            c['prices'] = by_cat.get(c['id'], {})
        return cats

    def add_category(self, company_id, name):
        if not company_id:
            raise ValueError('company_id required')
        name = (name or '').strip()
        if not name:
            raise ValueError('Denumirea categoriei este obligatorie')
        next_order = self.query_one(
            'SELECT COALESCE(MAX(sort_order), -1) + 1 AS n '
            'FROM fp_rental_categories WHERE company_id=%s',
            (company_id,),
        ) or {}
        return self.execute(
            '''INSERT INTO fp_rental_categories
                   (company_id, name, sort_order, is_active)
               VALUES (%s, %s, %s, TRUE)
               ON CONFLICT (company_id, name) DO NOTHING
               RETURNING id''',
            (company_id, name, int(next_order.get('n') or 0)),
            returning=True,
        )

    def upsert_category(self, company_id, category_id, name, models_note,
                        franchise_eur, extra_km_eur, sort_order, is_active):
        name = (name or '').strip()
        if not name:
            raise ValueError('Denumirea categoriei este obligatorie')
        return self.execute(
            '''UPDATE fp_rental_categories
               SET name=%s, models_note=%s, franchise_eur=%s, extra_km_eur=%s,
                   sort_order=%s, is_active=%s
               WHERE id=%s AND company_id=%s RETURNING id''',
            (name, models_note, franchise_eur, extra_km_eur, sort_order or 0,
             bool(is_active), category_id, company_id),
            returning=True,
        )

    def delete_category(self, company_id, category_id):
        used = self.query_one(
            'SELECT COUNT(*) AS n FROM fp_vehicles '
            'WHERE company_id=%s AND rental_category_id=%s',
            (company_id, category_id),
        ) or {}
        if int(used.get('n') or 0):
            raise ValueError(
                f"Categoria este folosită de {used['n']} mașini — "
                'dezactiveaz-o în loc să o ștergi.')
        # prices FK-orphan cleanup then the category
        self.execute(
            'DELETE FROM fp_rental_category_prices WHERE company_id=%s AND category_id=%s',
            (company_id, category_id),
        )
        return self.execute(
            'DELETE FROM fp_rental_categories WHERE company_id=%s AND id=%s',
            (company_id, category_id),
        )

    def set_price(self, company_id, category_id, interval_id, eur_per_day):
        return self.execute(
            '''INSERT INTO fp_rental_category_prices
                   (company_id, category_id, interval_id, eur_per_day)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (company_id, category_id, interval_id)
               DO UPDATE SET eur_per_day = EXCLUDED.eur_per_day''',
            (company_id, category_id, interval_id, eur_per_day),
        )

    # ── pricing lookup ──────────────────────────────────────────────────────
    def price_for(self, company_id, category_id, days):
        """Resolve a car's category + rental day-count to a €/day + policy.
        Returns None when the category is unknown or no interval covers `days`."""
        cat = self.query_one(
            'SELECT id, franchise_eur, extra_km_eur FROM fp_rental_categories '
            'WHERE company_id=%s AND id=%s',
            (company_id, category_id),
        )
        if not cat:
            return None
        iv = select_interval(self.list_intervals(company_id), days)
        if not iv:
            return None
        price = self.query_one(
            'SELECT eur_per_day FROM fp_rental_category_prices '
            'WHERE company_id=%s AND category_id=%s AND interval_id=%s',
            (company_id, category_id, iv['id']),
        ) or {}
        return {
            'eur_per_day': price.get('eur_per_day'),
            'interval_id': iv['id'],
            'interval_label': iv['label'],
            'franchise_eur': cat['franchise_eur'],
            'extra_km_eur': cat['extra_km_eur'],
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jarvis && python -m pytest tests/foi_parcurs/test_rental_category_repository.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add jarvis/foi_parcurs/repositories/rental_category_repository.py jarvis/tests/foi_parcurs/test_rental_category_repository.py
git commit -m "feat(foi-parcurs): RentalCategoryRepository (intervals/categories/prices/price_for)"
```

---

### Task 4: Migration — 3 tables + `rental_category_id` + Sharetoo seed

Additive, idempotent DDL + a SAVEPOINT-scoped co11-only seed that imports Task 2's data. Mirrors the existing `_seed_document_types` discipline exactly.

**Files:**
- Modify: `jarvis/migrations/domains/schema_incremental.py`
  - add `_seed_rental_tariffs(conn, cursor)` after `_seed_document_types` (after line 194)
  - add the 3 `CREATE TABLE IF NOT EXISTS` + `rental_category_id` column + indexes + the `_seed_rental_tariffs(conn, cursor)` call inside the "Foi de Parcurs — Service courtesy-car rental pricing" block, immediately after the closing `''')` of the `svc_*` DO-block at line 2603.
- Verify: localhost DB apply + count queries (raw SQL DDL is not unit-tested; the seed *data* is tested in Task 2).

**Interfaces:**
- Consumes: `rental_tariff_seed.SHARETOO_INTERVALS/SHARETOO_CATEGORIES/SHARETOO_COMPANY_ID` (loaded by file path via importlib, like `_seed_service_contract_configs`, to avoid the `import foi_parcurs...` circular import from `database.init_db()`).
- Produces: tables `fp_rental_intervals`, `fp_rental_categories`, `fp_rental_category_prices`; column `fp_vehicles.rental_category_id`.

- [ ] **Step 1: Add the seed function**

Insert after line 194 (after `_seed_document_types`) in `schema_incremental.py`:

```python
def _seed_rental_tariffs(conn, cursor):
    """Seed the SHARETOO rental tariff scheme for Autoworld PREMIUM (company 11).

    Idempotent (ON CONFLICT DO NOTHING everywhere) and company-scoped, so
    re-runs and every other company are untouched; admins edit afterwards. Seed
    data is loaded by file path (importlib) to avoid the foi_parcurs package
    circular import when called from database.init_db(). Same SAVEPOINT
    discipline as _seed_document_types — only the seed rolls back on failure."""
    try:
        seed_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'foi_parcurs',
            'services', 'rental_tariff_seed.py'
        )
        spec = importlib.util.spec_from_file_location('_rental_tariff_seed', seed_path)
        seed = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(seed)
        co = seed.SHARETOO_COMPANY_ID

        use_savepoint = not getattr(conn, 'autocommit', False)
        if use_savepoint:
            cursor.execute('SAVEPOINT rental_tariff_seed')
        try:
            for label, mn, mx, so in seed.SHARETOO_INTERVALS:
                cursor.execute(
                    '''INSERT INTO fp_rental_intervals
                           (company_id, label, min_days, max_days, sort_order)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (company_id, min_days) DO NOTHING''',
                    (co, label, mn, mx, so))
            cursor.execute(
                'SELECT id, min_days FROM fp_rental_intervals WHERE company_id=%s', (co,))
            iv_by_min = {r['min_days']: r['id'] for r in cursor.fetchall()}
            mins_in_order = [mn for (_, mn, _, _) in seed.SHARETOO_INTERVALS]

            for idx, (name, note, fr, ekm, prices) in enumerate(seed.SHARETOO_CATEGORIES):
                cursor.execute(
                    '''INSERT INTO fp_rental_categories
                           (company_id, name, models_note, franchise_eur,
                            extra_km_eur, sort_order, is_active)
                       VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                       ON CONFLICT (company_id, name) DO NOTHING''',
                    (co, name, note, fr, ekm, idx))
                cursor.execute(
                    'SELECT id FROM fp_rental_categories WHERE company_id=%s AND name=%s',
                    (co, name))
                cat_id = cursor.fetchone()['id']
                for mn, price in zip(mins_in_order, prices):
                    cursor.execute(
                        '''INSERT INTO fp_rental_category_prices
                               (company_id, category_id, interval_id, eur_per_day)
                           VALUES (%s, %s, %s, %s)
                           ON CONFLICT (company_id, category_id, interval_id) DO NOTHING''',
                        (co, cat_id, iv_by_min[mn], price))
            if use_savepoint:
                cursor.execute('RELEASE SAVEPOINT rental_tariff_seed')
        except Exception:
            if use_savepoint:
                cursor.execute('ROLLBACK TO SAVEPOINT rental_tariff_seed')
            raise
    except Exception:
        logger.exception('Failed to seed rental tariffs — continuing schema init')
```

- [ ] **Step 2: Add the DDL + column + seed call**

Insert immediately after line 2603 (the `''')` closing the `svc_*` DO-block, before the "Test Drive RETURN fields" comment) in `schema_incremental.py`:

```python
    # ── Foi de Parcurs — category-based rental tariffs ──
    # Per-company duration intervals + categories + the category×interval €/day
    # grid. A car's rental_category_id + the rental day-count resolve to a €/day.
    # Additive/idempotent; legacy per-car svc_tariff_* stays as a fallback.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fp_rental_intervals (
            id          BIGSERIAL PRIMARY KEY,
            company_id  BIGINT NOT NULL,
            label       VARCHAR(64) NOT NULL,
            min_days    INTEGER NOT NULL,
            max_days    INTEGER,
            sort_order  INTEGER NOT NULL DEFAULT 0,
            created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (company_id, min_days)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fp_rental_categories (
            id            BIGSERIAL PRIMARY KEY,
            company_id    BIGINT NOT NULL,
            name          VARCHAR(128) NOT NULL,
            models_note   TEXT,
            franchise_eur NUMERIC(10,2),
            extra_km_eur  NUMERIC(10,2),
            sort_order    INTEGER NOT NULL DEFAULT 0,
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (company_id, name)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fp_rental_category_prices (
            id          BIGSERIAL PRIMARY KEY,
            company_id  BIGINT NOT NULL,
            category_id BIGINT NOT NULL,
            interval_id BIGINT NOT NULL,
            eur_per_day NUMERIC(10,2),
            UNIQUE (company_id, category_id, interval_id)
        )
    ''')
    cursor.execute('''
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='fp_vehicles' AND column_name='rental_category_id') THEN
                ALTER TABLE fp_vehicles ADD COLUMN rental_category_id BIGINT;
            END IF;
        END $$;
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_rental_prices_lookup ON fp_rental_category_prices(company_id, category_id, interval_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fp_vehicles_rental_category ON fp_vehicles(rental_category_id)')
    _seed_rental_tariffs(conn, cursor)
```

- [ ] **Step 3: Verify py_compile + apply against localhost DB**

```bash
cd jarvis && python -m py_compile migrations/domains/schema_incremental.py && \
DATABASE_URL="postgresql://localhost/defaultdb" python -c "
from database import get_db, get_cursor, release_db
from migrations.domains.schema_incremental import create_schema_incremental
conn = get_db(); cur = get_cursor(conn)
create_schema_incremental(conn, cur); conn.commit(); release_db(conn)
print('applied')
"
```
Expected: prints `applied` with no traceback.

- [ ] **Step 4: Verify counts + idempotency (run the apply a SECOND time, then count)**

Re-run the Step 3 apply command once more (must still print `applied`), then:

```bash
cd jarvis && DATABASE_URL="postgresql://localhost/defaultdb" python -c "
from database import get_db, get_cursor, release_db
conn = get_db(); cur = get_cursor(conn)
for q in [
  \"SELECT COUNT(*) n FROM fp_rental_intervals WHERE company_id=11\",
  \"SELECT COUNT(*) n FROM fp_rental_categories WHERE company_id=11\",
  \"SELECT COUNT(*) n FROM fp_rental_category_prices WHERE company_id=11\",
]:
  cur.execute(q); print(q, '->', cur.fetchone()['n'])
release_db(conn)
"
```
Expected (stable across both runs — idempotent): intervals `5`, categories `18`, prices `90`.

- [ ] **Step 5: Commit** (migration gets its own commit)

```bash
git add jarvis/migrations/domains/schema_incremental.py
git commit -m "feat(db): rental tariff tables + fp_vehicles.rental_category_id + co11 seed"
```

---

### Task 5: Vehicle repository — carry `rental_category_id`

Thread the new column through create/update/list so the car form can set it and the pricing path (Task 7) reads it.

**Files:**
- Modify: `jarvis/foi_parcurs/repositories/vehicle_repository.py`
  - `_LIST_SELECT` (line 48-59): add `v.rental_category_id,`
  - `create()` (line 189): add `rental_category_id` to the column list + `data.get('rental_category_id')` to the values
  - `update()` allowlist (line ~231): add `'rental_category_id'`
- Test: `jarvis/tests/foi_parcurs/test_vehicle_rental_category.py` (new)

**Interfaces:**
- `get_by_vin`/`get_by_id` already `SELECT *`, so they carry `rental_category_id` for free once the column exists — no change there.

- [ ] **Step 1: Write the failing test**

Create `jarvis/tests/foi_parcurs/test_vehicle_rental_category.py`:

```python
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from unittest.mock import MagicMock
from foi_parcurs.repositories.vehicle_repository import FPVehicleRepository


def test_update_allows_rental_category_id():
    repo = FPVehicleRepository()
    repo.execute = MagicMock(return_value={'id': 3})
    repo.update(3, {'rental_category_id': 7})
    sql, params = repo.execute.call_args[0][0], repo.execute.call_args[0][1]
    assert 'rental_category_id' in sql
    assert 7 in params


def test_create_includes_rental_category_id_column():
    repo = FPVehicleRepository()
    repo.execute = MagicMock(return_value={'id': 1})
    repo.create({'vin': 'V1', 'mark': 'VW', 'model': 'T-Roc',
                 'fuel_type': 'petrol', 'rental_category_id': 7})
    sql = repo.execute.call_args[0][0]
    assert 'rental_category_id' in sql
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd jarvis && python -m pytest tests/foi_parcurs/test_vehicle_rental_category.py -v`
Expected: FAIL (`rental_category_id` not in SQL).

- [ ] **Step 3: Wire the column through (3 exact edits)**

**Edit 1 — `_LIST_SELECT` (line 59).** Change:
```python
        'v.svc_tariff_eur_day, v.svc_tariff_eur_month, '
```
to:
```python
        'v.svc_tariff_eur_day, v.svc_tariff_eur_month, v.rental_category_id, '
```

**Edit 2 — `create()` (lines 198-202).** Change the tail of the column list + VALUES so the last column line and the VALUES read:
```python
                svc_tariff_eur_day, svc_tariff_eur_month, svc_km_included_day,
                svc_extra_km_eur, svc_deposit_eur, svc_franchise_eur, rental_category_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s, %s) RETURNING *''',
```
and change the tail of the values tuple (line 220) from:
```python
             data.get('svc_deposit_eur'), data.get('svc_franchise_eur')),
```
to:
```python
             data.get('svc_deposit_eur'), data.get('svc_franchise_eur'),
             data.get('rental_category_id')),
```
(Net: one column added, one `%s` added to the last VALUES group, one value added — 31 columns / 31 placeholders / 31 values.)

**Edit 3 — `update()` allowlist (line 235).** Change:
```python
                    'svc_extra_km_eur', 'svc_deposit_eur', 'svc_franchise_eur'):
```
to:
```python
                    'svc_extra_km_eur', 'svc_deposit_eur', 'svc_franchise_eur',
                    'rental_category_id'):
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd jarvis && python -m pytest tests/foi_parcurs/test_vehicle_rental_category.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add jarvis/foi_parcurs/repositories/vehicle_repository.py jarvis/tests/foi_parcurs/test_vehicle_rental_category.py
git commit -m "feat(foi-parcurs): thread rental_category_id through vehicle repo"
```

---

### Task 6: Routes — `/api/foi-parcurs/rental-tariffs/*`

Admin-gated CRUD, mirroring `routes/document_types.py`.

**Files:**
- Create: `jarvis/foi_parcurs/routes/rental_tariffs.py`
- Modify: `jarvis/foi_parcurs/routes/__init__.py` — add `from . import rental_tariffs  # noqa: F401`
- Test: `jarvis/tests/foi_parcurs/test_rental_tariffs_routes.py` (new)

**Interfaces:**
- Consumes: `RentalCategoryRepository` (Task 3).
- Produces endpoints:
  - `GET /api/foi-parcurs/rental-tariffs/intervals?company_id` → `{success, intervals}`
  - `PUT /api/foi-parcurs/rental-tariffs/intervals` (body `{company_id, id?, label, min_days, max_days, sort_order}`) → `{success, id}`
  - `DELETE /api/foi-parcurs/rental-tariffs/intervals` (body `{company_id, id}`)
  - `GET /api/foi-parcurs/rental-tariffs/categories?company_id[&active=1]` → `{success, categories}` (each with `prices` map)
  - `POST /api/foi-parcurs/rental-tariffs/categories` (body `{company_id, name}`) → `{success, id}`
  - `PUT /api/foi-parcurs/rental-tariffs/categories` (body full row) → `{success}`
  - `DELETE /api/foi-parcurs/rental-tariffs/categories` (body `{company_id, id}`)
  - `PUT /api/foi-parcurs/rental-tariffs/prices` (body `{company_id, category_id, interval_id, eur_per_day}`)

- [ ] **Step 1: Write the failing tests**

Create `jarvis/tests/foi_parcurs/test_rental_tariffs_routes.py`:

```python
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask
from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.rental_tariffs as mod


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    return app.test_client()


def test_get_categories_returns_list(client, monkeypatch):
    monkeypatch.setattr(mod._repo, 'list_categories',
                        lambda cid, active_only=False: [{'id': 7, 'name': 'SUV+', 'prices': {1: 33}}])
    r = client.get('/api/foi-parcurs/rental-tariffs/categories?company_id=11')
    assert r.status_code == 200
    assert r.get_json()['categories'][0]['name'] == 'SUV+'


def test_set_price_requires_admin(client, monkeypatch):
    monkeypatch.setattr(mod, '_is_admin', lambda: False)
    r = client.put('/api/foi-parcurs/rental-tariffs/prices',
                   json={'company_id': 11, 'category_id': 7, 'interval_id': 1, 'eur_per_day': 33})
    assert r.status_code == 403


def test_set_price_admin_ok(client, monkeypatch):
    monkeypatch.setattr(mod, '_is_admin', lambda: True)
    called = {}
    monkeypatch.setattr(mod._repo, 'set_price',
                        lambda *a: called.setdefault('args', a))
    r = client.put('/api/foi-parcurs/rental-tariffs/prices',
                   json={'company_id': 11, 'category_id': 7, 'interval_id': 1, 'eur_per_day': 33})
    assert r.status_code == 200 and r.get_json()['success'] is True
    assert called['args'] == (11, 7, 1, 33)


def test_delete_category_in_use_returns_400(client, monkeypatch):
    monkeypatch.setattr(mod, '_is_admin', lambda: True)
    def _boom(cid, catid):
        raise ValueError('folosită de 3 mașini')
    monkeypatch.setattr(mod._repo, 'delete_category', _boom)
    r = client.delete('/api/foi-parcurs/rental-tariffs/categories',
                      json={'company_id': 11, 'id': 7})
    assert r.status_code == 400
    assert 'mașini' in r.get_json()['error']
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd jarvis && python -m pytest tests/foi_parcurs/test_rental_tariffs_routes.py -v`
Expected: FAIL with `ModuleNotFoundError: foi_parcurs.routes.rental_tariffs`.

- [ ] **Step 3: Implement routes + register**

Create `jarvis/foi_parcurs/routes/rental_tariffs.py`:

```python
"""Routes for the courtesy-car rental tariff scheme: duration intervals,
categories, and the category×interval €/day price grid. GET feeds the Settings
"Tarife închiriere" editor + the car-form category dropdown; writes are admin
only. Mirrors routes/document_types.py."""
from ._shared import foi_parcurs_bp, jsonify, request, login_required, current_user, logger
from ..repositories.rental_category_repository import RentalCategoryRepository

_repo = RentalCategoryRepository()


def _is_admin():
    return getattr(current_user, 'role_name', '').lower() in ('admin', 'superadmin')


def _admin_guard():
    if not _is_admin():
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    return None


# ── intervals ───────────────────────────────────────────────────────────────
@foi_parcurs_bp.route('/api/foi-parcurs/rental-tariffs/intervals', methods=['GET'])
@login_required
def api_list_rental_intervals():
    company_id = request.args.get('company_id', type=int)
    return jsonify({'success': True, 'intervals': _repo.list_intervals(company_id)})


@foi_parcurs_bp.route('/api/foi-parcurs/rental-tariffs/intervals', methods=['PUT'])
@login_required
def api_put_rental_interval():
    guard = _admin_guard()
    if guard:
        return guard
    d = request.get_json(silent=True) or {}
    try:
        row = _repo.upsert_interval(
            d.get('company_id'), d.get('id'), (d.get('label') or '').strip(),
            d.get('min_days'), d.get('max_days'), d.get('sort_order'))
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    return jsonify({'success': True, 'id': (row or {}).get('id')})


@foi_parcurs_bp.route('/api/foi-parcurs/rental-tariffs/intervals', methods=['DELETE'])
@login_required
def api_delete_rental_interval():
    guard = _admin_guard()
    if guard:
        return guard
    d = request.get_json(silent=True) or {}
    try:
        _repo.delete_interval(d.get('company_id'), d.get('id'))
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    return jsonify({'success': True})


# ── categories ────────────────────────────────────────────────────────────────
@foi_parcurs_bp.route('/api/foi-parcurs/rental-tariffs/categories', methods=['GET'])
@login_required
def api_list_rental_categories():
    company_id = request.args.get('company_id', type=int)
    active_only = request.args.get('active') in ('1', 'true', 'True')
    return jsonify({'success': True,
                    'categories': _repo.list_categories(company_id, active_only=active_only)})


@foi_parcurs_bp.route('/api/foi-parcurs/rental-tariffs/categories', methods=['POST'])
@login_required
def api_add_rental_category():
    guard = _admin_guard()
    if guard:
        return guard
    d = request.get_json(silent=True) or {}
    try:
        row = _repo.add_category(d.get('company_id'), d.get('name'))
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    return jsonify({'success': True, 'id': (row or {}).get('id')})


@foi_parcurs_bp.route('/api/foi-parcurs/rental-tariffs/categories', methods=['PUT'])
@login_required
def api_put_rental_category():
    guard = _admin_guard()
    if guard:
        return guard
    d = request.get_json(silent=True) or {}
    try:
        _repo.upsert_category(
            d.get('company_id'), d.get('id'), d.get('name'), d.get('models_note'),
            d.get('franchise_eur'), d.get('extra_km_eur'),
            d.get('sort_order'), d.get('is_active', True))
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    return jsonify({'success': True})


@foi_parcurs_bp.route('/api/foi-parcurs/rental-tariffs/categories', methods=['DELETE'])
@login_required
def api_delete_rental_category():
    guard = _admin_guard()
    if guard:
        return guard
    d = request.get_json(silent=True) or {}
    try:
        _repo.delete_category(d.get('company_id'), d.get('id'))
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    return jsonify({'success': True})


# ── price cell ────────────────────────────────────────────────────────────────
@foi_parcurs_bp.route('/api/foi-parcurs/rental-tariffs/prices', methods=['PUT'])
@login_required
def api_set_rental_price():
    guard = _admin_guard()
    if guard:
        return guard
    d = request.get_json(silent=True) or {}
    _repo.set_price(d.get('company_id'), d.get('category_id'),
                    d.get('interval_id'), d.get('eur_per_day'))
    logger.info('rental price set company=%s cat=%s iv=%s by %s',
                d.get('company_id'), d.get('category_id'), d.get('interval_id'),
                getattr(current_user, 'email', '?'))
    return jsonify({'success': True})
```

Then add to `jarvis/foi_parcurs/routes/__init__.py` (after the `document_types` import):

```python
from . import rental_tariffs   # noqa: F401
```

- [ ] **Step 4: Run to verify they pass**

Run: `cd jarvis && python -m pytest tests/foi_parcurs/test_rental_tariffs_routes.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add jarvis/foi_parcurs/routes/rental_tariffs.py jarvis/foi_parcurs/routes/__init__.py jarvis/tests/foi_parcurs/test_rental_tariffs_routes.py
git commit -m "feat(foi-parcurs): rental-tariffs CRUD routes (admin-gated)"
```

---

### Task 7: Wire category pricing into the session snapshot

Make `_resolve_service_pricing` prefer category pricing when the car has a `rental_category_id`, else fall back to the legacy per-car path. The two call sites (submit @339, activate @567) are unchanged — they already pass `_veh` (which now carries `rental_category_id`).

**Files:**
- Modify: `jarvis/foi_parcurs/routes/test_drive.py`
  - add `from ..repositories.rental_category_repository import RentalCategoryRepository` + `_rc_repo = RentalCategoryRepository()` near `_dt_repo` (line 27)
  - rework `_resolve_service_pricing` (lines 85-115) to try category pricing first
- Test: `jarvis/tests/foi_parcurs/test_rental_category_pricing.py` (new)

**Interfaces:**
- Consumes: `RentalCategoryRepository.price_for` (Task 3), `rental_pricing.rental_days` + `compute_category_pricing` (Task 1).

- [ ] **Step 1: Write the failing test**

Create `jarvis/tests/foi_parcurs/test_rental_category_pricing.py`:

```python
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from unittest.mock import MagicMock
import foi_parcurs.routes.test_drive as td


def test_category_pricing_wins_when_car_has_category(monkeypatch):
    monkeypatch.setattr(td._fp_repo, 'query_one',
                        lambda *a, **k: {'svc_km_included_day': 300, 'svc_extra_km_eur': None,
                                         'svc_deposit_eur': 400, 'svc_franchise_eur': None})
    monkeypatch.setattr(td._rc_repo, 'price_for',
                        lambda cid, cat, days: {'eur_per_day': 33, 'interval_id': 1,
                                                'interval_label': '1-8 zile',
                                                'franchise_eur': 250, 'extra_km_eur': 0.25})
    veh = {'rental_category_id': 7, 'svc_tariff_eur_day': 999}   # legacy value ignored
    out = td._resolve_service_pricing(
        veh, 11, '2026-02-01T09:00:00', '2026-02-05T09:00:00', {})
    assert out['svc_tariff_eur'] == 33          # from category, not 999
    assert out['svc_units'] == 4
    assert out['svc_total_eur'] == 132.0
    assert out['svc_fransiza_eur'] == 250       # category franchise
    assert out['svc_garantie_eur'] == 400       # deposit from policy


def test_falls_back_to_legacy_when_no_category(monkeypatch):
    monkeypatch.setattr(td._fp_repo, 'query_one',
                        lambda *a, **k: {'svc_km_included_day': 300})
    monkeypatch.setattr(td._rc_repo, 'price_for',
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError('should not call')))
    veh = {'svc_tariff_eur_day': 40}   # no rental_category_id
    out = td._resolve_service_pricing(
        veh, 11, '2026-02-01T09:00:00', '2026-02-03T09:00:00', {})
    assert out['svc_tariff_eur'] == 40          # legacy per-car path
    assert out['svc_rate_basis'] == 'day'
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd jarvis && python -m pytest tests/foi_parcurs/test_rental_category_pricing.py -v`
Expected: FAIL (`_rc_repo` attribute doesn't exist / category branch not present).

- [ ] **Step 3: Add the repo singleton + rework `_resolve_service_pricing`**

In `test_drive.py`, near line 27 (after `_dt_repo = DocumentTypeRepository()`):

```python
from ..repositories.rental_category_repository import RentalCategoryRepository
from ..services.rental_pricing import rental_days, compute_category_pricing
_rc_repo = RentalCategoryRepository()
```

Replace the body of `_resolve_service_pricing` (keep the docstring; change the compute block) so the `computed = {}` … `except` section becomes:

```python
    computed = {}
    try:
        policy = {}
        if company_id:
            policy = _fp_repo.query_one(
                'SELECT svc_km_included_day, svc_extra_km_eur, svc_deposit_eur, svc_franchise_eur '
                'FROM fp_company_config WHERE company_id = %s',
                (int(company_id),),
            ) or {}
        cat_id = (vehicle or {}).get('rental_category_id')
        if cat_id and company_id and departure and return_dt:
            # Category-based pricing: resolve €/day for the interval matching the
            # rental day-count. Deposit stays from company policy (no per-category
            # deposit in the tariff scheme).
            days = rental_days(departure, return_dt)
            price = _rc_repo.price_for(int(company_id), int(cat_id), days)
            if price and price.get('eur_per_day') is not None:
                computed = compute_category_pricing(
                    days, price['eur_per_day'], price['franchise_eur'],
                    price['extra_km_eur'], policy.get('svc_km_included_day'))
                computed['svc_garantie_eur'] = policy.get('svc_deposit_eur')
        if not computed and departure and return_dt:
            # Legacy per-car fallback (no category, or category has no price).
            computed = compute_service_pricing(vehicle or {}, policy, departure, return_dt) or {}
    except Exception:
        logger.warning('Service pricing compute failed; using payload overrides only', exc_info=True)
    resolved = dict(computed)
    for key in _SVC_SNAPSHOT_KEYS:
        override = payload.get(key)
        if override is not None:
            resolved[key] = override
    return resolved
```

(The payload-override loop and `_SVC_SNAPSHOT_KEYS` are unchanged; `compute_service_pricing` stays imported at line 13.)

- [ ] **Step 4: Run to verify it passes + no regressions**

Run: `cd jarvis && python -m pytest tests/foi_parcurs/test_rental_category_pricing.py -v && python -m pytest tests/foi_parcurs/test_test_drive_submit.py -q`
Expected: the new tests PASS; the pre-existing `test_test_drive_submit.py` failures are unchanged (they are a known-red login_manager harness issue, not introduced here — confirm the count/identity matches base).

- [ ] **Step 5: Commit**

```bash
git add jarvis/foi_parcurs/routes/test_drive.py jarvis/tests/foi_parcurs/test_rental_category_pricing.py
git commit -m "feat(foi-parcurs): category pricing in session snapshot (legacy fallback)"
```

---

### Task 8: Frontend — types + API client

**Files:**
- Modify: `jarvis/frontend/src/types/foiParcurs.ts` — add `rental_category_id?: number | null` to `FpVehicle` (after the `svc_*` fields, ~line 54)
- Modify: `jarvis/frontend/src/api/foiParcurs.ts` — add the rental-tariff endpoints to the `foiParcursApi` object (near the `getDocumentTypes` block, ~line 325)
- Test: none (thin typed wrappers; covered by the component tests in Tasks 9-10 and the `npm run build` typecheck)

**Interfaces:**
- Produces on `foiParcursApi`:
  - `getRentalIntervals(companyId) → { success; intervals: RentalInterval[] }`
  - `putRentalInterval(payload) → { success; id }`
  - `deleteRentalInterval(payload) → { success }`
  - `getRentalCategories(companyId, active?) → { success; categories: RentalCategory[] }`
  - `addRentalCategory(payload) → { success; id }`
  - `putRentalCategory(payload) → { success }`
  - `deleteRentalCategory(payload) → { success }`
  - `setRentalPrice(payload) → { success }`

- [ ] **Step 1: Add the `FpVehicle` field**

In `jarvis/frontend/src/types/foiParcurs.ts`, add after `svc_franchise_eur?: number | null` (line 54):

```ts
  rental_category_id?: number | null
```

- [ ] **Step 2: Add the API endpoints**

In `jarvis/frontend/src/api/foiParcurs.ts`, insert after the `deleteDocumentType` entry (~line 335):

```ts
  // ── Rental tariffs (courtesy-car category pricing) ──
  getRentalIntervals: (companyId: number) =>
    api.get<{ success: boolean; intervals: Array<{ id: number; label: string; min_days: number; max_days: number | null; sort_order: number }> }>(
      `${BASE}/rental-tariffs/intervals`, { company_id: String(companyId) }),
  putRentalInterval: (payload: { company_id: number; id?: number; label: string; min_days: number; max_days: number | null; sort_order?: number }) =>
    api.put<{ success: boolean; id: number }>(`${BASE}/rental-tariffs/intervals`, payload),
  deleteRentalInterval: (payload: { company_id: number; id: number }) =>
    api.delete<{ success: boolean }>(`${BASE}/rental-tariffs/intervals`, payload),
  getRentalCategories: (companyId: number, active = false) =>
    api.get<{ success: boolean; categories: Array<{ id: number; name: string; models_note: string | null; franchise_eur: number | null; extra_km_eur: number | null; sort_order: number; is_active: boolean; prices: Record<number, number> }> }>(
      `${BASE}/rental-tariffs/categories`, { company_id: String(companyId), ...(active ? { active: '1' } : {}) }),
  addRentalCategory: (payload: { company_id: number; name: string }) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/rental-tariffs/categories`, payload),
  putRentalCategory: (payload: { company_id: number; id: number; name: string; models_note: string | null; franchise_eur: number | null; extra_km_eur: number | null; sort_order?: number; is_active: boolean }) =>
    api.put<{ success: boolean }>(`${BASE}/rental-tariffs/categories`, payload),
  deleteRentalCategory: (payload: { company_id: number; id: number }) =>
    api.delete<{ success: boolean }>(`${BASE}/rental-tariffs/categories`, payload),
  setRentalPrice: (payload: { company_id: number; category_id: number; interval_id: number; eur_per_day: number | null }) =>
    api.put<{ success: boolean }>(`${BASE}/rental-tariffs/prices`, payload),
```

- [ ] **Step 3: Typecheck**

Run: `cd jarvis/frontend && npm run build`
Expected: 0 TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add jarvis/frontend/src/types/foiParcurs.ts jarvis/frontend/src/api/foiParcurs.ts
git commit -m "feat(frontend): rental-tariff API client + FpVehicle.rental_category_id"
```

---

### Task 9: Frontend — car-form Category dropdown

Replace the per-car tariff *source* with a category selector (the per-car `svc_*` inputs stay as an inherit-fallback for un-categorized cars, so nothing regresses).

**Files:**
- Modify: `jarvis/frontend/src/pages/FoiParcurs/index.tsx`
  - `VehicleFormValue` (2319-2352): add `rental_category_id: string`
  - `emptyVehicleForm` (2354-2365): add `rental_category_id: ''`
  - `vehicleToForm` (2367-2399): add `rental_category_id: v.rental_category_id != null ? String(v.rental_category_id) : ''`
  - `VehicleFormFields` (2503+): inside the `isRentalType` block (2671-2704), add a Category `<Select>` above the per-car price grid, fed by `getRentalCategories(_companyId, true)`
  - create-mutation payload (2838-2868) and `saveEdit` payload (2990-2998): add `rental_category_id: value.rental_category_id.trim() === '' ? null : Number(value.rental_category_id)`
- Test: none beyond `npm run build` (the existing `ContractConfigSection.test.tsx` pattern covers Settings; the car-form change is a typed dropdown)

**Interfaces:**
- Consumes: `foiParcursApi.getRentalCategories` (Task 8).

- [ ] **Step 1: Add the form field + mappers**

- `VehicleFormValue`: after `svc_franchise_eur: string` add `rental_category_id: string`.
- `emptyVehicleForm`: add `rental_category_id: ''` to the returned object.
- `vehicleToForm`: add `rental_category_id: v.rental_category_id != null ? String(v.rental_category_id) : ''`.

- [ ] **Step 2: Add the category query + `<Select>` in `VehicleFormFields`**

After the `docTypes`/`isRentalType` derivation (index.tsx:2525-2536), add:

```tsx
  const { data: rentalCatsData } = useQuery({
    queryKey: ['fp-rental-categories', _companyId],
    queryFn: () => foiParcursApi.getRentalCategories(_companyId, true),
    enabled: _companyId > 0 && isRentalType,
    staleTime: 30_000,
  })
  const rentalCategories = rentalCatsData?.categories ?? []
```

Inside the `{isRentalType && ( … )}` block, as the FIRST child of the inner `<div className="space-y-3 border-t pt-4">` (before the "Preț & politică" `<p>`), insert:

```tsx
      <div className="space-y-1.5">
        <Label className="text-xs">Categorie tarifară</Label>
        <Select
          value={value.rental_category_id || 'none'}
          onValueChange={(v) => onChange({ rental_category_id: v === 'none' ? '' : v })}
        >
          <SelectTrigger><SelectValue placeholder="Fără categorie" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="none">Fără categorie (tarif per mașină)</SelectItem>
            {rentalCategories.map((c) => (
              <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          Prețul se ia din categoria selectată (Settings → Tarife închiriere). Câmpurile de mai jos se folosesc doar când nu e selectată o categorie.
        </p>
      </div>
```

(`Select`, `SelectTrigger`, `SelectValue`, `SelectContent`, `SelectItem` are already imported in index.tsx — they back the existing "Parc / Tip document" selector. `useQuery` and `foiParcursApi` are already imported.)

- [ ] **Step 3: Add to both save payloads**

In the create-mutation payload builder (~2838-2868) and the `saveEdit` payload (~2990-2998), add:

```ts
      rental_category_id: newVehicle.rental_category_id.trim() === '' ? null : Number(newVehicle.rental_category_id),
```
(and the `editForm.` equivalent in `saveEdit`).

- [ ] **Step 4: Typecheck**

Run: `cd jarvis/frontend && npm run build`
Expected: 0 TypeScript errors.

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/pages/FoiParcurs/index.tsx
git commit -m "feat(frontend): car-form rental category selector"
```

---

### Task 10: Frontend — Settings "Tarife închiriere" editor

A new `isService`-gated Settings section: an Intervale editor + a Categorii price-grid, mirroring `ContractConfigSection`'s query/mutation pattern.

**Files:**
- Create: `jarvis/frontend/src/pages/FoiParcurs/RentalTariffsSection.tsx`
- Modify: `jarvis/frontend/src/pages/FoiParcurs/index.tsx` — mount it in `SettingsTab` right after `ContractConfigSection` (index.tsx:3770): `{isService && <RentalTariffsSection companyId={companyId} />}` (add the import at the top)
- Test: `jarvis/frontend/src/pages/FoiParcurs/RentalTariffsSection.test.tsx` (new) — render + assert the grid shows a seeded category and interval header

**Interfaces:**
- Consumes: the Task 8 API endpoints.
- Produces: `export default function RentalTariffsSection({ companyId }: { companyId?: number | null })`.

- [ ] **Step 1: Write the failing test**

Create `jarvis/frontend/src/pages/FoiParcurs/RentalTariffsSection.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import RentalTariffsSection from './RentalTariffsSection'
import { foiParcursApi } from '@/api/foiParcurs'

vi.mock('@/api/foiParcurs', () => ({
  foiParcursApi: {
    getRentalIntervals: vi.fn(),
    getRentalCategories: vi.fn(),
    putRentalInterval: vi.fn(),
    deleteRentalInterval: vi.fn(),
    addRentalCategory: vi.fn(),
    putRentalCategory: vi.fn(),
    deleteRentalCategory: vi.fn(),
    setRentalPrice: vi.fn(),
  },
}))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('RentalTariffsSection', () => {
  beforeEach(() => {
    ;(foiParcursApi.getRentalIntervals as any).mockResolvedValue({
      success: true, intervals: [{ id: 1, label: '1-8 zile', min_days: 1, max_days: 8, sort_order: 0 }],
    })
    ;(foiParcursApi.getRentalCategories as any).mockResolvedValue({
      success: true, categories: [{ id: 7, name: 'SUV+', models_note: 'x', franchise_eur: 250, extra_km_eur: 0.25, sort_order: 0, is_active: true, prices: { 1: 33 } }],
    })
  })

  it('renders the category row and interval header', async () => {
    wrap(<RentalTariffsSection companyId={11} />)
    await waitFor(() => expect(screen.getByText('SUV+')).toBeInTheDocument())
    expect(screen.getByText('1-8 zile')).toBeInTheDocument()
    expect(screen.getByDisplayValue('33')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd jarvis/frontend && npx vitest run src/pages/FoiParcurs/RentalTariffsSection.test.tsx`
Expected: FAIL (module `./RentalTariffsSection` not found).

- [ ] **Step 3: Implement the component**

Create `jarvis/frontend/src/pages/FoiParcurs/RentalTariffsSection.tsx`:

```tsx
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Trash2, Plus } from 'lucide-react'
import { foiParcursApi } from '@/api/foiParcurs'

export default function RentalTariffsSection({ companyId }: { companyId?: number | null }) {
  const qc = useQueryClient()
  const cid = companyId ?? 0
  const [newIvLabel, setNewIvLabel] = useState('')
  const [newIvMin, setNewIvMin] = useState('')
  const [newIvMax, setNewIvMax] = useState('')
  const [newCatName, setNewCatName] = useState('')

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['fp-rental-intervals'] })
    qc.invalidateQueries({ queryKey: ['fp-rental-categories'] })
  }

  const { data: ivData } = useQuery({
    queryKey: ['fp-rental-intervals', cid],
    queryFn: () => foiParcursApi.getRentalIntervals(cid),
    enabled: cid > 0,
    staleTime: 30_000,
  })
  const { data: catData } = useQuery({
    queryKey: ['fp-rental-categories', cid, 'all'],
    queryFn: () => foiParcursApi.getRentalCategories(cid),
    enabled: cid > 0,
    staleTime: 30_000,
  })
  const intervals = ivData?.intervals ?? []
  const categories = catData?.categories ?? []

  const onErr = (e: unknown) =>
    toast.error((e as { data?: { error?: string } })?.data?.error ?? 'Eroare')

  const saveIv = useMutation({
    mutationFn: (p: { id?: number; label: string; min_days: number; max_days: number | null; sort_order?: number }) =>
      foiParcursApi.putRentalInterval({ company_id: cid, ...p }),
    onSuccess: () => { setNewIvLabel(''); setNewIvMin(''); setNewIvMax(''); invalidate() },
    onError: onErr,
  })
  const delIv = useMutation({
    mutationFn: (id: number) => foiParcursApi.deleteRentalInterval({ company_id: cid, id }),
    onSuccess: invalidate, onError: onErr,
  })
  const addCat = useMutation({
    mutationFn: (name: string) => foiParcursApi.addRentalCategory({ company_id: cid, name }),
    onSuccess: () => { setNewCatName(''); invalidate() }, onError: onErr,
  })
  const saveCat = useMutation({
    mutationFn: (p: { id: number; name: string; models_note: string | null; franchise_eur: number | null; extra_km_eur: number | null; sort_order?: number; is_active: boolean }) =>
      foiParcursApi.putRentalCategory({ company_id: cid, ...p }),
    onSuccess: invalidate, onError: onErr,
  })
  const delCat = useMutation({
    mutationFn: (id: number) => foiParcursApi.deleteRentalCategory({ company_id: cid, id }),
    onSuccess: invalidate, onError: onErr,
  })
  const setPrice = useMutation({
    mutationFn: (p: { category_id: number; interval_id: number; eur_per_day: number | null }) =>
      foiParcursApi.setRentalPrice({ company_id: cid, ...p }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['fp-rental-categories'] }),
    onError: onErr,
  })

  if (!cid) return null

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold">Tarife închiriere (Mașini de curtoazie)</h3>
        <p className="text-sm text-muted-foreground">
          Intervale de durată + categorii cu preț €/zi. Fiecare mașină primește o categorie (în fișa mașinii).
        </p>
      </div>

      {/* Intervale */}
      <Card className="p-4 space-y-3">
        <p className="text-sm font-semibold">Intervale de durată (zile)</p>
        <div className="space-y-2">
          {intervals.map((iv) => (
            <div key={iv.id} className="flex items-center gap-2">
              <Input className="w-40" defaultValue={iv.label}
                     onBlur={(e) => saveIv.mutate({ id: iv.id, label: e.target.value, min_days: iv.min_days, max_days: iv.max_days, sort_order: iv.sort_order })} />
              <Input type="number" className="w-24" defaultValue={iv.min_days}
                     onBlur={(e) => saveIv.mutate({ id: iv.id, label: iv.label, min_days: Number(e.target.value), max_days: iv.max_days, sort_order: iv.sort_order })} />
              <span className="text-muted-foreground">–</span>
              <Input type="number" className="w-24" defaultValue={iv.max_days ?? ''} placeholder="∞"
                     onBlur={(e) => saveIv.mutate({ id: iv.id, label: iv.label, min_days: iv.min_days, max_days: e.target.value === '' ? null : Number(e.target.value), sort_order: iv.sort_order })} />
              <Button variant="ghost" size="icon" onClick={() => delIv.mutate(iv.id)}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-2 border-t pt-3">
          <Input className="w-40" placeholder="ex: 1-8 zile" value={newIvLabel} onChange={(e) => setNewIvLabel(e.target.value)} />
          <Input type="number" className="w-24" placeholder="min" value={newIvMin} onChange={(e) => setNewIvMin(e.target.value)} />
          <span className="text-muted-foreground">–</span>
          <Input type="number" className="w-24" placeholder="max (∞)" value={newIvMax} onChange={(e) => setNewIvMax(e.target.value)} />
          <Button variant="outline" size="sm"
                  disabled={!newIvLabel.trim() || newIvMin === ''}
                  onClick={() => saveIv.mutate({ label: newIvLabel.trim(), min_days: Number(newIvMin), max_days: newIvMax === '' ? null : Number(newIvMax) })}>
            <Plus className="h-4 w-4 mr-1" /> Adaugă interval
          </Button>
        </div>
      </Card>

      {/* Categorii price grid */}
      <Card className="p-4 space-y-3 overflow-x-auto">
        <p className="text-sm font-semibold">Categorii &amp; prețuri (€/zi)</p>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b">
              <th className="p-2">Categorie</th>
              {intervals.map((iv) => <th key={iv.id} className="p-2 text-center">{iv.label}</th>)}
              <th className="p-2 text-center">Franșiză €</th>
              <th className="p-2 text-center">Extra km €</th>
              <th className="p-2"></th>
            </tr>
          </thead>
          <tbody>
            {categories.map((c) => (
              <tr key={c.id} className="border-b">
                <td className="p-2">
                  <Input className="w-40" defaultValue={c.name}
                         onBlur={(e) => saveCat.mutate({ id: c.id, name: e.target.value, models_note: c.models_note, franchise_eur: c.franchise_eur, extra_km_eur: c.extra_km_eur, sort_order: c.sort_order, is_active: c.is_active })} />
                </td>
                {intervals.map((iv) => (
                  <td key={iv.id} className="p-2">
                    <Input type="number" step="0.01" className="w-20 text-center"
                           defaultValue={c.prices[iv.id] ?? ''}
                           onBlur={(e) => setPrice.mutate({ category_id: c.id, interval_id: iv.id, eur_per_day: e.target.value === '' ? null : Number(e.target.value) })} />
                  </td>
                ))}
                <td className="p-2">
                  <Input type="number" step="0.01" className="w-20 text-center" defaultValue={c.franchise_eur ?? ''}
                         onBlur={(e) => saveCat.mutate({ id: c.id, name: c.name, models_note: c.models_note, franchise_eur: e.target.value === '' ? null : Number(e.target.value), extra_km_eur: c.extra_km_eur, sort_order: c.sort_order, is_active: c.is_active })} />
                </td>
                <td className="p-2">
                  <Input type="number" step="0.01" className="w-20 text-center" defaultValue={c.extra_km_eur ?? ''}
                         onBlur={(e) => saveCat.mutate({ id: c.id, name: c.name, models_note: c.models_note, franchise_eur: c.franchise_eur, extra_km_eur: e.target.value === '' ? null : Number(e.target.value), sort_order: c.sort_order, is_active: c.is_active })} />
                </td>
                <td className="p-2">
                  <Button variant="ghost" size="icon" onClick={() => delCat.mutate(c.id)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="flex items-center gap-2 border-t pt-3">
          <Input className="w-56" placeholder="Categorie nouă (ex: SUV+)" value={newCatName} onChange={(e) => setNewCatName(e.target.value)} />
          <Button variant="outline" size="sm" disabled={!newCatName.trim()} onClick={() => addCat.mutate(newCatName.trim())}>
            <Plus className="h-4 w-4 mr-1" /> Adaugă categorie
          </Button>
        </div>
      </Card>
    </div>
  )
}
```

- [ ] **Step 4: Mount it in `SettingsTab` + import**

- Add near the other page imports in index.tsx: `import RentalTariffsSection from './RentalTariffsSection'`.
- In `SettingsTab`'s return, immediately after `{isService && <ContractConfigSection companyId={companyId} />}` (index.tsx:3770), add:

```tsx
      {isService && <RentalTariffsSection companyId={companyId} />}
```

- [ ] **Step 5: Run the component test + full build/typecheck**

Run: `cd jarvis/frontend && npx vitest run src/pages/FoiParcurs/RentalTariffsSection.test.tsx && npm run build`
Expected: the vitest test PASSES; `npm run build` reports 0 TypeScript errors.

- [ ] **Step 6: Commit**

```bash
git add jarvis/frontend/src/pages/FoiParcurs/RentalTariffsSection.tsx jarvis/frontend/src/pages/FoiParcurs/RentalTariffsSection.test.tsx jarvis/frontend/src/pages/FoiParcurs/index.tsx
git commit -m "feat(frontend): Settings Tarife închiriere editor (intervals + price grid)"
```

---

### Task 11: Full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Backend suite**

Run: `cd jarvis && python -m pytest tests/foi_parcurs/ -q`
Expected: all new tests green; the only failures are the pre-existing known-red ones (`test_test_drive_submit.py` ×5 and `test_correct_*` ×13 — the `login_manager` harness issue documented on `origin/staging`). Confirm identity vs base if unsure.

- [ ] **Step 2: Frontend suite + build**

Run: `cd jarvis/frontend && npx vitest run && npm run build`
Expected: all vitest suites pass (incl. the new `RentalTariffsSection.test.tsx`); `npm run build` = 0 TypeScript errors.

- [ ] **Step 3: py_compile the app entrypoint**

Run: `cd jarvis && python -m py_compile app.py foi_parcurs/routes/rental_tariffs.py foi_parcurs/repositories/rental_category_repository.py migrations/domains/schema_incremental.py`
Expected: no output (success).

- [ ] **Step 4: Manual smoke on localhost (web)** — after the plan is implemented, run the app against localhost DB, open Driving Hub → Settings on Autoworld PREMIUM (co11) with the Mașini de curtoazie context, and confirm the "Tarife închiriere" grid shows the 18 seeded categories × 5 intervals; edit a cell; open a courtesy car's Edit form and confirm the Categorie dropdown lists them. (Login is interactive — this step is user-driven, not headless.)

---

## Rollout (post-implementation, user-gated)

Not tasks — the deploy sequence, gated on the user's confirmations per the JARVIS git workflow:
1. localhost verified (Task 11 + manual smoke).
2. staging: FF-push the branch to `staging` (safe-push guard: nothing BUILDING + origin unchanged + worktree == HEAD). Migration runs on the staging DB (idempotent; co11 seeded).
3. prod: **requires 2 confirmations.** Because `main` is cherry-pick-maintained and diverged from staging, promote via the established squash-merge in an isolated temp worktree (as with the document-types launch), not a FF-of-staging. Migration runs on the prod DB on deploy (additive/idempotent; co11 seeded).
4. Post-deploy (manual, safe): assign each of the 3 prod courtesy cars a category in the car form (the seed intentionally does NOT auto-assign, to avoid mis-mapping). Un-assigned cars keep the legacy per-car pricing until then.

## Deferred (not in this plan — from the spec)

- Monthly-subscription pricing mode + the PDF's estimated-monthly display columns.
- Transmission as a stored/pricing dimension (folded into `models_note` for now).
- Per-car price override alongside a category.
