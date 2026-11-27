// Pure column-grouping/card-mapping/filter logic for the Kanban board,
// extracted out of Kanban.tsx so it can be unit-tested without mounting
// React (Kanban.helpers.test.ts). No side effects, no API imports -- just
// plain-object mapping and small derivations over the already-fetched
// board dict.
import type { GetBoardFilters, KanbanBoardDict, KanbanBoardStatus, KanbanCard, MoveTaskContext } from '@/api/logistics'

// Re-export of the fixed column order per the design spec §4.2 -- must stay
// in sync with BOARD_STATUSES in jarvis/logistics/repositories/task_repository.py.
export const KANBAN_STATUSES: readonly KanbanBoardStatus[] = [
  'De făcut', 'În lucru', 'Blocat', 'Finalizat',
]

export interface KanbanColumn {
  key: KanbanBoardStatus
  label: KanbanBoardStatus
  cards: KanbanCard[]
  count: number
}

/** Decorate the raw `{status: cards[]}` board dict into the 4 fixed-order
 * columns the UI renders, each carrying its own count. Defensive against a
 * missing/extra key (falls back to `[]` for a column the server omitted)
 * so a partial response never crashes the board -- it just renders that
 * column empty. */
export function groupBoardIntoColumns(board: KanbanBoardDict | undefined): KanbanColumn[] {
  return KANBAN_STATUSES.map((status) => {
    const cards = board?.[status] ?? []
    return { key: status, label: status, cards, count: cards.length }
  })
}

/** The columns a card can move to from wherever it currently sits -- every
 * other fixed column, in board order. Populates the per-card "Mută"
 * dropdown (Task 8 wires the actual move; this just lists the choices). */
export function moveTargets(currentStatus: KanbanBoardStatus): KanbanBoardStatus[] {
  return KANBAN_STATUSES.filter((status) => status !== currentStatus)
}

/** "Locație · Poziție" display label for a card -- both parts are
 * nullable (not-yet-positioned vehicle), so this falls back to whichever
 * half is present, or '—' when neither is known. */
export function formatLocationBay(locationName: string | null, positionCode: string | null): string {
  if (locationName && positionCode) return `${locationName} · ${positionCode}`
  if (locationName) return locationName
  if (positionCode) return positionCode
  return '—'
}

/** HH:mm for a `due_at` ISO timestamp, in the viewer's local timezone --
 * '—' for a missing or unparseable value (never throws). */
export function formatDueTime(dueAt: string | null): string {
  if (!dueAt) return '—'
  const parsed = new Date(dueAt)
  if (Number.isNaN(parsed.getTime())) return '—'
  return parsed.toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' })
}

/** Filters-state -> the shape getBoard() sends to the server. `location`
 * is deliberately NOT included here -- see filterBoardByLocation below for
 * why the Locație filter is applied client-side instead. */
export interface KanbanFiltersState {
  q: string
  assignee: string
  /** Display-only client-side filter value (a `location_name` string, not
   * an id) -- '' = "Toate locațiile". */
  location: string
}

export const EMPTY_KANBAN_FILTERS: KanbanFiltersState = { q: '', assignee: '', location: '' }

export function toGetBoardFilters(filters: KanbanFiltersState): GetBoardFilters {
  const result: GetBoardFilters = {}
  if (filters.q) result.q = filters.q
  if (filters.assignee) result.assignee = filters.assignee
  return result
}

function emptyBoard(): Record<KanbanBoardStatus, KanbanCard[]> {
  const board = {} as Record<KanbanBoardStatus, KanbanCard[]>
  for (const status of KANBAN_STATUSES) board[status] = []
  return board
}

/** Client-side Locație filter. A Kanban card only ever carries
 * `location_name` (a display string), not the `location_id` the backend's
 * `get_board` filter actually matches on -- there's no `/locations`
 * endpoint yet to resolve a dropdown id back to a name (same phase-1 gap
 * Parc.tsx's `distinctLocationOptions` works around, see Task 6 notes), so
 * rather than wire a filter the UI can't actually drive, this narrows the
 * already-fetched board by exact `location_name` match instead of
 * round-tripping to the server. */
export function filterBoardByLocation(
  board: KanbanBoardDict | undefined,
  location: string,
): Record<KanbanBoardStatus, KanbanCard[]> {
  if (!location) {
    const result = emptyBoard()
    for (const status of KANBAN_STATUSES) result[status] = board?.[status] ?? []
    return result
  }
  const result = emptyBoard()
  for (const status of KANBAN_STATUSES) {
    result[status] = (board?.[status] ?? []).filter((card) => card.location_name === location)
  }
  return result
}

/** Distinct, sorted assignee names present across every column -- used to
 * populate the Responsabil filter dropdown from whatever's already loaded
 * (mirrors Parc.helpers.ts's distinctLocationOptions). Cards with no
 * assignee yet are excluded, since there's nothing to filter on. */
export function distinctAssignees(board: KanbanBoardDict | undefined): string[] {
  const set = new Set<string>()
  for (const status of KANBAN_STATUSES) {
    for (const card of board?.[status] ?? []) {
      if (card.assignee) set.add(card.assignee)
    }
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b))
}

/** Distinct, sorted location names present across every column -- used to
 * populate the Locație filter dropdown (see filterBoardByLocation's
 * docstring for why this is name-based, not id-based). */
export function distinctLocationNames(board: KanbanBoardDict | undefined): string[] {
  const set = new Set<string>()
  for (const status of KANBAN_STATUSES) {
    for (const card of board?.[status] ?? []) {
      if (card.location_name) set.add(card.location_name)
    }
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b))
}

// ── Move engine (Task 8) ─────────────────────────────────────────────────

/** The `Blocat` gate's own validation, mirrored client-side so the "Blochează"
 * button in the dialog disables itself instead of round-tripping to the
 * server just to learn both fields are required (backend's `move_task` in
 * jarvis/logistics/services/moves.py enforces the same rule — this is a UX
 * head start, not a replacement for it). Whitespace-only input doesn't
 * count as filled in. */
export function isBlockFormValid(responsible: string, nextAction: string): boolean {
  return responsible.trim().length > 0 && nextAction.trim().length > 0
}

/** Build the `ctx` body `moveTask()` sends for a given transition. Only
 * `to_status === 'Blocat'` carries a `block` payload (trimmed); every other
 * transition sends an empty ctx -- the backend only looks at `block` when
 * moving to Blocat, but there's no reason to send stale/irrelevant form
 * values along for the ride. */
export function buildMoveContext(
  toStatus: KanbanBoardStatus,
  block: { responsible: string; nextAction: string },
): MoveTaskContext {
  if (toStatus !== 'Blocat') return {}
  return {
    block: {
      responsible: block.responsible.trim(),
      next_action: block.nextAction.trim(),
    },
  }
}

// ── Reception gate (Task 9: Recepție -> Finalizat, "Confirmă recepția") ──

/** Raw <input> values for the ConfirmReceptionDialog -- every field is a
 * string (what a controlled <input> hands back), including the two that are
 * numeric IDs/counts on the wire (`location_id`/`position_id`/`keys`); see
 * buildReceptionContext for the string -> number conversion. */
export interface ReceptionFormState {
  vin: string
  location_id: string
  position_id: string
  keys: string
  condition: string
}

export const EMPTY_RECEPTION_FORM: ReceptionFormState = {
  vin: '', location_id: '', position_id: '', keys: '', condition: '',
}

/** A non-negative whole number, as typed into a plain text/number <input>
 * (optional surrounding whitespace only -- no decimals, no sign). */
function isWholeNumberString(value: string): boolean {
  return /^\d+$/.test(value.trim())
}

/** The reception gate's own validation, mirrored client-side so the
 * "Confirmă recepția" button disables itself instead of round-tripping to
 * the server just to learn a field is missing (backend's `move_task` in
 * jarvis/logistics/services/moves.py enforces the same rule via
 * `_require_reception_fields` -- this is a UX head start, not a replacement
 * for it). `location_id`/`position_id` must be a positive id (0 is never a
 * real row); `keys` may be 0 (a car handed over with no keys is still a
 * valid, complete reception). */
export function isReceptionFormValid(form: ReceptionFormState): boolean {
  return (
    form.vin.trim().length > 0 &&
    isWholeNumberString(form.location_id) && Number(form.location_id.trim()) > 0 &&
    isWholeNumberString(form.position_id) && Number(form.position_id.trim()) > 0 &&
    isWholeNumberString(form.keys) &&
    form.condition.trim().length > 0
  )
}

/** Build the `ctx.reception` body `moveTask()` sends for the "Confirmă
 * recepția" move (vin/condition trimmed; location_id/position_id/keys
 * coerced to numbers) -- call only once `isReceptionFormValid` is true. */
export function buildReceptionContext(form: ReceptionFormState): MoveTaskContext {
  return {
    reception: {
      vin: form.vin.trim(),
      location_id: Number(form.location_id.trim()),
      position_id: Number(form.position_id.trim()),
      keys: Number(form.keys.trim()),
      condition: form.condition.trim(),
    },
  }
}
