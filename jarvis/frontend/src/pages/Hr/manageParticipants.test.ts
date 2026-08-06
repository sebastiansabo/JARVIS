import { describe, it, expect } from 'vitest'
import type { EventParticipant } from '@/types/marketing'
import {
  participantToRow,
  rowToPayload,
  diffParticipantRows,
  type ParticipantRow,
} from './manageParticipants'

const EVENT_ID = 42

function participant(overrides: Partial<EventParticipant> = {}): EventParticipant {
  return {
    id: 100,
    user_id: 7,
    user_name: 'Doja Paul-Sebastian',
    year: 2026,
    month: 8,
    participation_start: '2026-08-02',
    participation_end: '2026-08-02',
    bonus_days: 1,
    hours_free: 6,
    bonus_net: 150,
    details: null,
    allocation_month: null,
    bonus_type_name: null,
    ...overrides,
  }
}

describe('participantToRow', () => {
  it('maps a participant to an editable row, nulls -> empty strings, numbers -> string inputs', () => {
    const row = participantToRow(participant())
    expect(row).toMatchObject({
      id: 100,
      userId: 7,
      userName: 'Doja Paul-Sebastian',
      year: 2026,
      month: 8,
      partStart: '2026-08-02',
      partEnd: '2026-08-02',
      bonusDays: '1',
      hoursFree: '6',
      bonusNet: 150,
      details: '',
    })
  })

  it('coerces null period/days/hours to empty inputs', () => {
    const row = participantToRow(
      participant({ participation_start: null, participation_end: null, bonus_days: null, hours_free: null }),
    )
    expect(row.partStart).toBe('')
    expect(row.partEnd).toBe('')
    expect(row.bonusDays).toBe('')
    expect(row.hoursFree).toBe('')
  })
})

describe('rowToPayload', () => {
  it('builds the backend payload, empty strings -> null, numeric strings -> numbers', () => {
    const row = participantToRow(participant())
    expect(rowToPayload(row, EVENT_ID)).toEqual({
      employee_id: 7,
      event_id: 42,
      year: 2026,
      month: 8,
      participation_start: '2026-08-02',
      participation_end: '2026-08-02',
      bonus_days: 1,
      hours_free: 6,
      bonus_net: 150,
      details: null,
    })
  })

  it('empty period/days/hours become null in the payload', () => {
    const row: ParticipantRow = {
      id: null, userId: 9, userName: 'New Person', year: 2026, month: 8,
      partStart: '', partEnd: '', bonusDays: '', hoursFree: '', bonusNet: null,
      details: '', bonusTypeId: '',
    }
    expect(rowToPayload(row, EVENT_ID)).toMatchObject({
      participation_start: null,
      participation_end: null,
      bonus_days: null,
      hours_free: null,
      details: null,
    })
  })
})

describe('diffParticipantRows', () => {
  it('returns nothing to do when rows are unchanged', () => {
    const original = [participant()]
    const rows = original.map(participantToRow)
    const ops = diffParticipantRows(original, rows, EVENT_ID)
    expect(ops).toEqual({ creates: [], updates: [], deletes: [] })
  })

  it('flags a create for a new row (no id)', () => {
    const original = [participant()]
    const rows = [
      ...original.map(participantToRow),
      { id: null, userId: 9, userName: 'New Person', year: 2026, month: 8,
        partStart: '2026-08-03', partEnd: '2026-08-03', bonusDays: '2', hoursFree: '9',
        bonusNet: 300, details: '', bonusTypeId: '' } as ParticipantRow,
    ]
    const ops = diffParticipantRows(original, rows, EVENT_ID)
    expect(ops.updates).toEqual([])
    expect(ops.deletes).toEqual([])
    expect(ops.creates).toHaveLength(1)
    expect(ops.creates[0]).toMatchObject({ employee_id: 9, event_id: 42, bonus_days: 2, bonus_net: 300 })
  })

  it('flags an update when a persisted field changed', () => {
    const original = [participant()]
    const rows = original.map(participantToRow)
    rows[0].bonusDays = '2'
    rows[0].bonusNet = 300
    const ops = diffParticipantRows(original, rows, EVENT_ID)
    expect(ops.creates).toEqual([])
    expect(ops.deletes).toEqual([])
    expect(ops.updates).toHaveLength(1)
    expect(ops.updates[0].id).toBe(100)
    expect(ops.updates[0].data).toMatchObject({ bonus_days: 2, bonus_net: 300 })
  })

  it('does NOT flag an update when only the UI-only bonusTypeId changed but the payload is identical', () => {
    const original = [participant()]
    const rows = original.map(participantToRow)
    rows[0].bonusTypeId = '5' // pre-selected type, no amount/day change
    const ops = diffParticipantRows(original, rows, EVENT_ID)
    expect(ops.updates).toEqual([])
  })

  it('flags a delete when an existing participant is removed from rows', () => {
    const original = [participant({ id: 100 }), participant({ id: 200, user_id: 8, user_name: 'Gone' })]
    const rows = [participantToRow(original[0])] // dropped id=200
    const ops = diffParticipantRows(original, rows, EVENT_ID)
    expect(ops.creates).toEqual([])
    expect(ops.updates).toEqual([])
    expect(ops.deletes).toEqual([200])
  })

  it('handles a simultaneous create, update, and delete', () => {
    const original = [participant({ id: 100 }), participant({ id: 200, user_id: 8, user_name: 'Gone' })]
    const rows = [participantToRow(original[0]), {
      id: null, userId: 9, userName: 'New', year: 2026, month: 8,
      partStart: '', partEnd: '', bonusDays: '1', hoursFree: '6', bonusNet: 150, details: '', bonusTypeId: '',
    } as ParticipantRow]
    rows[0].hoursFree = '3'
    const ops = diffParticipantRows(original, rows, EVENT_ID)
    expect(ops.creates.map((c) => c.employee_id)).toEqual([9])
    expect(ops.updates.map((u) => u.id)).toEqual([100])
    expect(ops.deletes).toEqual([200])
  })
})
