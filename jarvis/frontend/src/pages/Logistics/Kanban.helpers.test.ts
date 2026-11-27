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
  type KanbanFiltersState,
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
