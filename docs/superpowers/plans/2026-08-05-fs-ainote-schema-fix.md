# AI Visit-Note Schema Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `ai_service.structure_visit_note` emit the canonical `FSStructuredNote` schema that the review UI and the notifiers already consume, hardened by a server-side normalizer, and surface `sentiment` in the UI.

**Architecture:** Rewrite the AI prompt's target JSON to the canonical schema; add a pure `_normalize_structured_note` coercion step applied to the parsed LLM output before it is returned/stored; add `sentiment` to the frontend contract + a review badge. No DB, route, or finalize-behavior changes.

**Tech Stack:** Python (Flask service, pytest), React 19 + TypeScript + Tailwind (Vitest).

## Global Constraints
- Work in the worktree `/Users/sebastiansabo/Documents/Git/JARVIS-fs-tenant` on branch `fs-ainote-schema-fix` (off `dev` 22d210dd8); ff-merge to `dev` at finish.
- **Canonical schema** — the AI output, the normalizer output, and `FSStructuredNote` all share exactly these keys:
  `visit_summary` (str), `sentiment` (`'positive'|'neutral'|'negative'|null`), `contact_person` (str|null), `vehicles_discussed` (`[{action, current_vehicle, interested_in, budget_eur}]`), `commitments_made` (`str[]`), `next_steps` (`[{action, owner, deadline}]`), `opportunity_value_eur` (num|null), `decision_timeline` (str|null), `follow_up_date` (str|null), `objections` (`str[]`), `risk_flags` (`str[]`).
- Backend tests never call the real LLM — patch `ai_service.ask` and `ai_service._AI_AVAILABLE`. `tests/conftest.py` sets a dummy `DATABASE_URL`, so importing the module works with no DB.
- Backend test run (from worktree root): `python3 -m pytest tests/test_field_sales_ai_note.py -v`. Backend syntax check: `python3 -c "import ast; ast.parse(open('jarvis/field_sales/services/ai_service.py').read())"`.
- Frontend commands run from `jarvis/frontend`: `npx tsc --noEmit`, `npx vitest run <path>`. Do NOT `npm run build` in task commits; commit **source only** (never `jarvis/static/react/*` or `tsconfig.tsbuildinfo`).
- The post-commit hook prints a repo-wide validation report — ignore its pre-existing (unrelated) Python-side failures.
- Romanian UI copy; iOS-standard sizing; match existing NoteCaptureModal styling.

---

### Task 1: Backend — `_normalize_structured_note` coercion

**Files:**
- Modify: `jarvis/field_sales/services/ai_service.py` (add the function + two tiny helpers, above `structure_visit_note`)
- Test: `tests/test_field_sales_ai_note.py` (new)

**Interfaces:**
- Produces: `_normalize_structured_note(raw: dict) -> dict` — returns the canonical shape; passes an `{'error': …}` dict through untouched; never raises. Also module-level `_SENTIMENTS = {'positive','neutral','negative'}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_field_sales_ai_note.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from field_sales.services import ai_service
from field_sales.services.ai_service import _normalize_structured_note

CANONICAL_KEYS = {
    'visit_summary', 'sentiment', 'contact_person', 'vehicles_discussed',
    'commitments_made', 'next_steps', 'opportunity_value_eur',
    'decision_timeline', 'follow_up_date', 'objections', 'risk_flags',
}


def test_normalizer_coerces_offshape_to_canonical():
    raw = {
        'visit_summary': 'Rezumat',
        'sentiment': 'wat',                       # invalid -> None
        'next_steps': 'do a thing',               # string -> []
        'commitments_made': None,                 # None -> []
        'vehicles_discussed': [{'action': 'buy', 'budget_eur': '20000'}],
        'opportunity_value_eur': 'nope',          # non-numeric -> None
        'stray_key': 'dropped',
    }
    out = _normalize_structured_note(raw)
    assert set(out) == CANONICAL_KEYS
    assert out['sentiment'] is None
    assert out['next_steps'] == []
    assert out['commitments_made'] == []
    assert out['vehicles_discussed'][0]['budget_eur'] == 20000
    assert out['vehicles_discussed'][0]['current_vehicle'] is None
    assert out['opportunity_value_eur'] is None
    assert 'stray_key' not in out


def test_normalizer_passes_error_marker_through():
    err = {'error': 'parse_failed', 'raw': 'x'}
    assert _normalize_structured_note(err) == err


def test_normalizer_preserves_valid_canonical():
    raw = {
        'visit_summary': 'S', 'sentiment': 'positive', 'contact_person': 'Ana',
        'vehicles_discussed': [{'action': 'replace', 'current_vehicle': 'A4', 'interested_in': 'A6', 'budget_eur': 45000}],
        'commitments_made': ['send offer'],
        'next_steps': [{'action': 'call', 'owner': 'kam', 'deadline': '2026-08-10'}],
        'opportunity_value_eur': 45000, 'decision_timeline': 'Q3',
        'follow_up_date': '2026-08-10', 'objections': ['price'], 'risk_flags': ['competitor'],
    }
    assert _normalize_structured_note(raw) == raw


def test_normalizer_non_dict_returns_error():
    out = _normalize_structured_note('garbage')
    assert out.get('error') == 'parse_failed'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_field_sales_ai_note.py -v`
Expected: FAIL — `ImportError: cannot import name '_normalize_structured_note'`.

- [ ] **Step 3: Implement the normalizer**

In `jarvis/field_sales/services/ai_service.py`, immediately below the `_MODEL = 'claude-sonnet-4-6'` line, add:

```python
_SENTIMENTS = {'positive', 'neutral', 'negative'}


def _coerce_number(v):
    """Return v as a number, or None. Bools and non-numeric values -> None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _as_list(v):
    return v if isinstance(v, list) else []


def _normalize_structured_note(raw):
    """Coerce a parsed AI note into the canonical FSStructuredNote shape.

    Whitelists known keys, forces list/scalar types, clamps `sentiment` to the
    enum, and never raises — a malformed element degrades to a safe default.
    An {'error': ...} marker (or a non-dict) is returned as an error dict so the
    caller's `structured.get('error')` skip-save check still holds.
    """
    if not isinstance(raw, dict):
        return {'error': 'parse_failed', 'raw': str(raw)}
    if raw.get('error'):
        return raw

    sentiment = raw.get('sentiment')
    if sentiment not in _SENTIMENTS:
        sentiment = None

    vehicles = []
    for v in _as_list(raw.get('vehicles_discussed')):
        if isinstance(v, dict):
            vehicles.append({
                'action': v.get('action'),
                'current_vehicle': v.get('current_vehicle'),
                'interested_in': v.get('interested_in'),
                'budget_eur': _coerce_number(v.get('budget_eur')),
            })

    next_steps = []
    for s in _as_list(raw.get('next_steps')):
        if isinstance(s, dict):
            next_steps.append({
                'action': s.get('action'),
                'owner': s.get('owner'),
                'deadline': s.get('deadline'),
            })

    return {
        'visit_summary': raw.get('visit_summary') or '',
        'sentiment': sentiment,
        'contact_person': raw.get('contact_person'),
        'vehicles_discussed': vehicles,
        'commitments_made': [str(c) for c in _as_list(raw.get('commitments_made'))],
        'next_steps': next_steps,
        'opportunity_value_eur': _coerce_number(raw.get('opportunity_value_eur')),
        'decision_timeline': raw.get('decision_timeline'),
        'follow_up_date': raw.get('follow_up_date'),
        'objections': [str(o) for o in _as_list(raw.get('objections'))],
        'risk_flags': [str(r) for r in _as_list(raw.get('risk_flags'))],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_field_sales_ai_note.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add jarvis/field_sales/services/ai_service.py tests/test_field_sales_ai_note.py
git commit -m "feat(field-sales): add canonical structured-note normalizer"
```

---

### Task 2: Backend — rewrite prompt to canonical schema + wire normalizer

**Files:**
- Modify: `jarvis/field_sales/services/ai_service.py` (the `system_prompt` block + the success `return` in `structure_visit_note`)
- Test: `tests/test_field_sales_ai_note.py` (append)

**Interfaces:**
- Consumes: `_normalize_structured_note` (Task 1).
- Produces: `structure_visit_note(raw_note, client_context=None)` now returns the normalized canonical dict on success (error dicts unchanged on failure paths).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_field_sales_ai_note.py`)

```python
import json


def _patch_ask(monkeypatch, response):
    captured = {}

    def fake_ask(user_message, system=None, model=None, max_tokens=None):
        captured['system'] = system
        captured['user'] = user_message
        return response

    monkeypatch.setattr(ai_service, '_AI_AVAILABLE', True)
    monkeypatch.setattr(ai_service, 'ask', fake_ask)
    return captured


def test_prompt_declares_every_canonical_key(monkeypatch):
    captured = _patch_ask(monkeypatch, json.dumps({'visit_summary': 'ok'}))
    ai_service.structure_visit_note('some note')
    for key in CANONICAL_KEYS:
        assert key in captured['system'], f'prompt missing {key}'
    # dropped legacy fields must not reappear in the schema block
    assert 'deal_probability' not in captured['system']
    assert 'vehicles_of_interest' not in captured['system']


def test_structure_visit_note_normalizes_fenced_ai_output(monkeypatch):
    payload = {'visit_summary': 'S', 'sentiment': 'positive', 'next_steps': 'bad', 'stray': 1}
    _patch_ask(monkeypatch, '```json\n' + json.dumps(payload) + '\n```')
    out = ai_service.structure_visit_note('note')
    assert set(out) == CANONICAL_KEYS       # stray dropped, keys filled
    assert out['visit_summary'] == 'S'
    assert out['sentiment'] == 'positive'
    assert out['next_steps'] == []          # string coerced away
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_field_sales_ai_note.py -k "prompt_declares or normalizes_fenced" -v`
Expected: FAIL — the prompt still contains `summary`/`vehicles_of_interest` (missing canonical keys) and the return is un-normalized (`stray` present).

- [ ] **Step 3: Rewrite the prompt schema block**

In `structure_visit_note`, replace the JSON schema + Rules inside `system_prompt` so it reads (keep the intro line and the `user_message` block unchanged):

```python
    system_prompt = """You are a CRM assistant for a car dealership group. Your job is to structure raw visit notes from Key Account Managers (KAMs) into a clean JSON format.

Extract and categorize information from the raw note into EXACTLY this JSON structure (use these field names verbatim):
{
  "visit_summary": "1-2 sentence summary of the visit",
  "sentiment": "positive|neutral|negative",
  "contact_person": "name of the person met, or null",
  "vehicles_discussed": [
    {"action": "buy|replace|service|inquire", "current_vehicle": "or null", "interested_in": "or null", "budget_eur": 0}
  ],
  "commitments_made": ["promises the KAM or client made"],
  "next_steps": [
    {"action": "description", "owner": "kam|client|other", "deadline": "YYYY-MM-DD or null"}
  ],
  "opportunity_value_eur": 0,
  "decision_timeline": "when the client expects to decide, or null",
  "follow_up_date": "YYYY-MM-DD if mentioned, else null",
  "objections": ["concerns or blockers the client raised"],
  "risk_flags": ["churn/competitor/dissatisfaction signals"]
}

Rules:
- Always return valid JSON and nothing else.
- Use these exact field names; do NOT invent extra fields.
- If a field has no data: null for scalars, [] for arrays.
- sentiment must be one of positive, neutral, negative.
- budget_eur and opportunity_value_eur are plain numbers (EUR), or null.
- Detect language automatically but always output field names in English.
- Preserve important details and numbers mentioned."""
```

- [ ] **Step 4: Wire the normalizer into the success return**

In `structure_visit_note`, change the success return from:

```python
        structured = json.loads(json_text)
        return structured
```

to:

```python
        structured = json.loads(json_text)
        return _normalize_structured_note(structured)
```

(Leave the `except json.JSONDecodeError` / `except Exception` error-dict returns unchanged.)

- [ ] **Step 5: Run the full backend test file**

Run: `python3 -m pytest tests/test_field_sales_ai_note.py -v`
Expected: all tests pass (Task 1's 4 + these 2).

- [ ] **Step 6: Syntax check + commit**

```bash
python3 -c "import ast; ast.parse(open('jarvis/field_sales/services/ai_service.py').read())" && echo OK
git add jarvis/field_sales/services/ai_service.py tests/test_field_sales_ai_note.py
git commit -m "fix(field-sales): align AI note prompt to canonical FSStructuredNote schema"
```

---

### Task 3: Frontend — `sentiment` in the contract + review badge

**Files:**
- Modify: `jarvis/frontend/src/api/fieldSales.ts` (`FSStructuredNote`)
- Modify: `jarvis/frontend/src/pages/FieldSales/NoteCaptureModal.tsx` (summary card)
- Test: `jarvis/frontend/src/pages/FieldSales/NoteCaptureModal.test.tsx` (append)

**Interfaces:**
- Consumes: the canonical schema (backend Task 2). No cross-file code interface.

- [ ] **Step 1: Write the failing tests** (append inside the top-level `describe` in `NoteCaptureModal.test.tsx`)

```tsx
  it('renders a sentiment badge when sentiment is present', async () => {
    addNote.mockResolvedValue({
      success: true,
      note: { id: 1, raw_note: 'x', created_at: '' },
      structured_note: { visit_summary: 'Rezumat', sentiment: 'positive' } as unknown,
    })
    wrap(<NoteCaptureModal visitId={9} clientId={760} onDone={vi.fn()} onCancel={() => {}} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'discutie buna' } })
    fireEvent.click(screen.getByRole('button', { name: /proceseaz/i }))
    expect(await screen.findByText('Rezumat')).toBeInTheDocument()
    expect(screen.getByText(/Pozitiv/i)).toBeInTheDocument()
  })

  it('renders no sentiment badge when sentiment is null', async () => {
    addNote.mockResolvedValue({
      success: true,
      note: { id: 1, raw_note: 'x', created_at: '' },
      structured_note: { visit_summary: 'Rezumat', sentiment: null } as unknown,
    })
    wrap(<NoteCaptureModal visitId={9} clientId={760} onDone={vi.fn()} onCancel={() => {}} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'ceva' } })
    fireEvent.click(screen.getByRole('button', { name: /proceseaz/i }))
    expect(await screen.findByText('Rezumat')).toBeInTheDocument()
    expect(screen.queryByText(/Pozitiv|Neutru|Negativ/i)).not.toBeInTheDocument()
  })
```

- [ ] **Step 2: Run to verify they fail**

Run (from `jarvis/frontend`): `npx vitest run src/pages/FieldSales/NoteCaptureModal.test.tsx`
Expected: the first new test FAILS (no "Pozitiv" badge rendered).

- [ ] **Step 3: Add `sentiment` to the contract**

In `jarvis/frontend/src/api/fieldSales.ts`, in `interface FSStructuredNote`, add after `visit_summary`:

```ts
  sentiment: 'positive' | 'neutral' | 'negative' | null
```

- [ ] **Step 4: Render the badge**

In `NoteCaptureModal.tsx`, above the component (module scope) add:

```tsx
const SENTIMENT_BADGE: Record<string, { label: string; cls: string }> = {
  positive: { label: 'Pozitiv', cls: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300' },
  neutral: { label: 'Neutru', cls: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300' },
  negative: { label: 'Negativ', cls: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300' },
}
```

Then in the summary card, replace the `<h4>Sumar vizita</h4>` header line (currently a lone `<h4>`) with a flex row carrying the optional badge:

```tsx
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Sumar vizita</h4>
                {structured.sentiment && SENTIMENT_BADGE[structured.sentiment] && (
                  <span className={cn('shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide', SENTIMENT_BADGE[structured.sentiment].cls)}>
                    {SENTIMENT_BADGE[structured.sentiment].label}
                  </span>
                )}
              </div>
```

(The removed `<h4 … mb-1.5>` loses its own `mb-1.5`; the wrapper row now carries it.) If `cn` is not already imported in this file, add `import { cn } from '@/lib/utils'`.

- [ ] **Step 5: Run tests + typecheck**

Run (from `jarvis/frontend`):
`npx vitest run src/pages/FieldSales/NoteCaptureModal.test.tsx` → all pass (existing + 2 new).
`npx tsc --noEmit` → clean.

- [ ] **Step 6: Commit**

```bash
git add jarvis/frontend/src/api/fieldSales.ts jarvis/frontend/src/pages/FieldSales/NoteCaptureModal.tsx jarvis/frontend/src/pages/FieldSales/NoteCaptureModal.test.tsx
git commit -m "feat(field-sales): surface visit-note sentiment badge in review"
```

---

### Task 4: Full verification + ff-merge to dev

**Files:** none (verification + integration only).

- [ ] **Step 1: Backend tests + syntax**

Run (worktree root): `python3 -m pytest tests/test_field_sales_ai_note.py -v` → all pass.
Run: `python3 -c "import ast; ast.parse(open('jarvis/field_sales/services/ai_service.py').read())" && echo OK`.

- [ ] **Step 2: Frontend gates**

Run (from `jarvis/frontend`): `npx tsc --noEmit` → clean; `npx vitest run` → full suite green, pristine.

- [ ] **Step 3: Build check, then revert artifacts**

Run (from `jarvis/frontend`): `npm run build` → succeeds.
Then (worktree root): `git checkout -- jarvis/static/react jarvis/frontend/tsconfig.tsbuildinfo && git clean -fdq jarvis/static/react` → tree clean (only `node_modules` untracked).

- [ ] **Step 4: Final scoped review**

Request a review of the range `dev..HEAD` (the 3 implementation commits) via superpowers:requesting-code-review. Address any Critical/Important findings before merging.

- [ ] **Step 5: Rebase onto dev + ff-merge** (dev is checked out & may be dirty in the main folder `/Users/sebastiansabo/Documents/Git/JARVIS`)

```bash
# from the worktree; dev may have advanced — rebase to keep ff-able
git rebase dev
# re-run gates after rebase: npx tsc --noEmit && npx vitest run  (from jarvis/frontend)
# then fast-forward dev in the main worktree (guarded):
git merge-base --is-ancestor dev fs-ainote-schema-fix && \
  git -C /Users/sebastiansabo/Documents/Git/JARVIS merge --ff-only fs-ainote-schema-fix
```
Confirm the main folder's uncommitted work is preserved (`git -C … status --short`). If `git rebase dev` conflicts (it shouldn't — files are disjoint from dev's calendar/testdrive work), STOP and surface.

- [ ] **Step 6: Update memory**

Update `project_fs_tenant_isolation.md` (mark Slice 1 shipped to dev) and the `MEMORY.md` pointer.

## Self-Review
- **Spec coverage:** prompt rewrite (Task 2) ✓; normalizer (Task 1) ✓; sentiment kept + rendered (Task 3) ✓; drift-guard + normalizer + parse tests (Tasks 1–2) ✓; frontend badge test (Task 3) ✓; tenant-awareness (no change, documented) ✓; verify + merge (Task 4) ✓.
- **Placeholders:** none — every step has exact code/commands.
- **Type consistency:** `_normalize_structured_note`, `_coerce_number`, `_as_list`, `_SENTIMENTS`, `CANONICAL_KEYS`, `SENTIMENT_BADGE`, and the `FSStructuredNote.sentiment` union are used consistently across tasks. The canonical key set matches the spec and `FSStructuredNote` (plus `sentiment`).
