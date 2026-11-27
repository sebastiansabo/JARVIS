import { describe, it, expect } from 'vitest'
import {
  KANBAN_STATUSES,
  EMPTY_KANBAN_FILTERS,
  groupBoardIntoColumns,
  moveTargets,
  formatLocationBay,
  formatDueTime,
  toGetBoardFilters,
  filterBoardByLocation,
  distinctAssignees,
  distinctLocationNames,
  isBlockFormValid,
  buildMoveContext,
  isReceptionFormValid,
  buildReceptionContext,
  EMPTY_RECEPTION_FORM,
  isMeasuredFormValid,
  buildMeasuredContext,
  EMPTY_MEASURED_FORM,
  type KanbanFiltersState,
  type ReceptionFormState,
  type MeasuredFormState,
} from './Kanban.helpers'
import type { KanbanBoardDict, KanbanCard } from '@/api/logistics'

const card = (overrides: Partial<KanbanCard>): KanbanCard => ({
  id: 1,
  title: 'Recepție programată',
  type: 'Recepție',
  vehicle_model: 'Audi A4',
  order_ref: 'AW-1001',
  location_name: 'Rampă Nord',
  position_code: 'A-01',
  assignee: 'Logistică',
  due_at: '2026-11-27T10:30:00Z',
  ...overrides,
})

describe('groupBoardIntoColumns', () => {
  it('returns all 4 fixed-order columns with counts, even when the board omits a key', () => {
    const board: KanbanBoardDict = {
      'De făcut': [card({ id: 1 })],
      'În lucru': [card({ id: 2 }), card({ id: 3 })],
      // 'Blocat' intentionally omitted -- must still render as an empty column.
      Finalizat: [],
    }
    const columns = groupBoardIntoColumns(board)

    expect(columns.map((c) => c.key)).toEqual(KANBAN_STATUSES)
    expect(columns.map((c) => c.count)).toEqual([1, 2, 0, 0])
    expect(columns.find((c) => c.key === 'Blocat')?.cards).toEqual([])
  })

  it('handles an undefined board (not-yet-loaded) as all-empty columns', () => {
    const columns = groupBoardIntoColumns(undefined)
    expect(columns.every((c) => c.count === 0)).toBe(true)
    expect(columns.map((c) => c.key)).toEqual(KANBAN_STATUSES)
  })
})

describe('moveTargets', () => {
  it('lists every column except the current one, in board order', () => {
    expect(moveTargets('De făcut')).toEqual(['În lucru', 'Blocat', 'Finalizat'])
    expect(moveTargets('Blocat')).toEqual(['De făcut', 'În lucru', 'Finalizat'])
  })
})

describe('formatLocationBay', () => {
  it('joins location + bay with a middle dot when both are known', () => {
    expect(formatLocationBay('Rampă Nord', 'A-01')).toBe('Rampă Nord · A-01')
  })

  it('falls back to whichever half is present', () => {
    expect(formatLocationBay('Rampă Nord', null)).toBe('Rampă Nord')
    expect(formatLocationBay(null, 'A-01')).toBe('A-01')
  })

  it('falls back to an em-dash when neither is known', () => {
    expect(formatLocationBay(null, null)).toBe('—')
  })
})

describe('formatDueTime', () => {
  it('formats a valid ISO timestamp as HH:mm', () => {
    // Just assert it's a non-dash, colon-bearing time string -- exact
    // wall-clock text depends on the test runner's timezone.
    const formatted = formatDueTime('2026-11-27T10:30:00Z')
    expect(formatted).not.toBe('—')
    expect(formatted).toMatch(/\d{1,2}:\d{2}/)
  })

  it('falls back to an em-dash for null/unparseable input', () => {
    expect(formatDueTime(null)).toBe('—')
    expect(formatDueTime('not-a-date')).toBe('—')
  })
})

describe('toGetBoardFilters', () => {
  it('maps only q and assignee -- location is deliberately excluded (client-side only)', () => {
    const filters: KanbanFiltersState = { q: 'AW-1', assignee: 'Ana Pop', location: 'Rampă Nord' }
    expect(toGetBoardFilters(filters)).toEqual({ q: 'AW-1', assignee: 'Ana Pop' })
  })

  it('sends nothing for the empty filters state', () => {
    expect(toGetBoardFilters(EMPTY_KANBAN_FILTERS)).toEqual({})
  })
})

describe('filterBoardByLocation', () => {
  const board: KanbanBoardDict = {
    'De făcut': [card({ id: 1, location_name: 'Rampă Nord' }), card({ id: 2, location_name: 'Atelier' })],
    'În lucru': [card({ id: 3, location_name: 'Rampă Nord' })],
    Blocat: [],
    Finalizat: [],
  }

  it('passes every card through unfiltered when no location is selected', () => {
    const result = filterBoardByLocation(board, '')
    expect(result['De făcut']).toHaveLength(2)
    expect(result['În lucru']).toHaveLength(1)
  })

  it('narrows every column to exact location_name matches', () => {
    const result = filterBoardByLocation(board, 'Rampă Nord')
    expect(result['De făcut'].map((c) => c.id)).toEqual([1])
    expect(result['În lucru'].map((c) => c.id)).toEqual([3])
    expect(result['Blocat']).toEqual([])
  })

  it('tolerates an undefined board', () => {
    expect(filterBoardByLocation(undefined, 'Rampă Nord')).toEqual({
      'De făcut': [], 'În lucru': [], Blocat: [], Finalizat: [],
    })
  })
})

describe('distinctAssignees', () => {
  it('dedupes and sorts assignees across all columns, excluding unset ones', () => {
    const board: KanbanBoardDict = {
      'De făcut': [card({ assignee: 'Ion Ionescu' }), card({ assignee: null })],
      'În lucru': [card({ assignee: 'Ana Pop' }), card({ assignee: 'Ana Pop' })],
      Blocat: [],
      Finalizat: [],
    }
    expect(distinctAssignees(board)).toEqual(['Ana Pop', 'Ion Ionescu'])
  })
})

describe('distinctLocationNames', () => {
  it('dedupes and sorts location names across all columns, excluding unset ones', () => {
    const board: KanbanBoardDict = {
      'De făcut': [card({ location_name: 'Rampă Sud' }), card({ location_name: null })],
      'În lucru': [card({ location_name: 'Atelier' })],
      Blocat: [],
      Finalizat: [],
    }
    expect(distinctLocationNames(board)).toEqual(['Atelier', 'Rampă Sud'])
  })
})

describe('isBlockFormValid', () => {
  it('requires both fields non-empty after trimming', () => {
    expect(isBlockFormValid('Ion Pop', 'Comandă piesă')).toBe(true)
    expect(isBlockFormValid('', 'Comandă piesă')).toBe(false)
    expect(isBlockFormValid('Ion Pop', '')).toBe(false)
    expect(isBlockFormValid('   ', '   ')).toBe(false)
    expect(isBlockFormValid('', '')).toBe(false)
  })
})

describe('buildMoveContext', () => {
  it('builds a trimmed block payload only when moving to Blocat', () => {
    expect(buildMoveContext('Blocat', { responsible: '  Ion Pop  ', nextAction: ' Comandă piesă ' })).toEqual({
      block: { responsible: 'Ion Pop', next_action: 'Comandă piesă' },
    })
  })

  it('sends an empty ctx for every other transition, ignoring the block form', () => {
    expect(buildMoveContext('În lucru', { responsible: 'Ion Pop', nextAction: 'Comandă piesă' })).toEqual({})
    expect(buildMoveContext('De făcut', { responsible: '', nextAction: '' })).toEqual({})
    expect(buildMoveContext('Finalizat', { responsible: '', nextAction: '' })).toEqual({})
  })
})

const receptionForm = (overrides: Partial<ReceptionFormState> = {}): ReceptionFormState => ({
  vin: 'WVWZZZ1KZAW000001',
  location_id: '3',
  position_id: '12',
  keys: '2',
  condition: 'Bună',
  ...overrides,
})

describe('isReceptionFormValid', () => {
  it('is valid when every field is filled, including keys=0', () => {
    expect(isReceptionFormValid(receptionForm())).toBe(true)
    expect(isReceptionFormValid(receptionForm({ keys: '0' }))).toBe(true)
  })

  it('is invalid when the empty starting form is untouched', () => {
    expect(isReceptionFormValid(EMPTY_RECEPTION_FORM)).toBe(false)
  })

  it.each(['vin', 'condition'] as const)('is invalid when %s is blank/whitespace-only', (field) => {
    expect(isReceptionFormValid(receptionForm({ [field]: '' }))).toBe(false)
    expect(isReceptionFormValid(receptionForm({ [field]: '   ' }))).toBe(false)
  })

  it.each(['location_id', 'position_id'] as const)('is invalid when %s is 0, negative, or non-numeric', (field) => {
    expect(isReceptionFormValid(receptionForm({ [field]: '0' }))).toBe(false)
    expect(isReceptionFormValid(receptionForm({ [field]: '-1' }))).toBe(false)
    expect(isReceptionFormValid(receptionForm({ [field]: 'abc' }))).toBe(false)
    expect(isReceptionFormValid(receptionForm({ [field]: '' }))).toBe(false)
  })

  it('is invalid when keys is non-numeric or negative', () => {
    expect(isReceptionFormValid(receptionForm({ keys: 'abc' }))).toBe(false)
    expect(isReceptionFormValid(receptionForm({ keys: '-1' }))).toBe(false)
    expect(isReceptionFormValid(receptionForm({ keys: '' }))).toBe(false)
  })
})

describe('buildReceptionContext', () => {
  it('trims strings and coerces the numeric fields', () => {
    expect(buildReceptionContext(receptionForm({
      vin: '  WVWZZZ1KZAW000001  ',
      location_id: '3',
      position_id: '12',
      keys: '0',
      condition: '  Bună  ',
    }))).toEqual({
      reception: {
        vin: 'WVWZZZ1KZAW000001',
        location_id: 3,
        position_id: 12,
        keys: 0,
        condition: 'Bună',
      },
    })
  })
})

const measuredForm = (overrides: Partial<MeasuredFormState> = {}): MeasuredFormState => ({
  value: '12.4',
  unit: 'V',
  ...overrides,
})

describe('isMeasuredFormValid', () => {
  it('is valid when value is a real number and unit is non-empty', () => {
    expect(isMeasuredFormValid(measuredForm())).toBe(true)
    expect(isMeasuredFormValid(measuredForm({ value: '0' }))).toBe(true)
    expect(isMeasuredFormValid(measuredForm({ value: '-5' }))).toBe(true)
    expect(isMeasuredFormValid(measuredForm({ unit: '%' }))).toBe(true)
  })

  it('is invalid when the empty starting form is untouched', () => {
    expect(isMeasuredFormValid(EMPTY_MEASURED_FORM)).toBe(false)
  })

  it('is invalid when value is non-numeric, blank, or whitespace-only', () => {
    expect(isMeasuredFormValid(measuredForm({ value: 'abc' }))).toBe(false)
    expect(isMeasuredFormValid(measuredForm({ value: '' }))).toBe(false)
    expect(isMeasuredFormValid(measuredForm({ value: '   ' }))).toBe(false)
  })

  it('is invalid when unit is blank or whitespace-only', () => {
    expect(isMeasuredFormValid(measuredForm({ unit: '' }))).toBe(false)
    expect(isMeasuredFormValid(measuredForm({ unit: '   ' }))).toBe(false)
  })
})

describe('buildMeasuredContext', () => {
  it('coerces value to a number and trims the unit', () => {
    expect(buildMeasuredContext(measuredForm({ value: '  12.4  ', unit: '  V  ' }))).toEqual({
      measured: { value: 12.4, unit: 'V' },
    })
  })
})
