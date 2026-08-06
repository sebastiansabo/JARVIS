import type { EventParticipant } from '@/types/marketing'

/** An editable participant row in the Manage-participants dialog. */
export interface ParticipantRow {
  id: number | null // existing event_bonus id, or null for a newly added row
  userId: number
  userName: string
  year: number
  month: number
  partStart: string // '' or YYYY-MM-DD
  partEnd: string
  bonusDays: string // string-backed inputs
  hoursFree: string
  bonusNet: number | null
  details: string
  bonusTypeId: string // UI-only: drives amount auto-compute, not persisted
}

/** The payload accepted by createBonus / updateBonus (mirrors AddEventPage). */
export interface BonusPayload {
  employee_id: number
  event_id: number
  year: number
  month: number
  participation_start: string | null
  participation_end: string | null
  bonus_days: number | null
  hours_free: number | null
  bonus_net: number | null
  details: string | null
}

export interface SaveOps {
  creates: BonusPayload[]
  updates: { id: number; data: BonusPayload }[]
  deletes: number[]
}

export function participantToRow(p: EventParticipant): ParticipantRow {
  return {
    id: p.id,
    userId: p.user_id,
    userName: p.user_name,
    year: p.year,
    month: p.month,
    partStart: p.participation_start ?? '',
    partEnd: p.participation_end ?? '',
    bonusDays: p.bonus_days != null ? String(p.bonus_days) : '',
    hoursFree: p.hours_free != null ? String(p.hours_free) : '',
    bonusNet: p.bonus_net != null ? Number(p.bonus_net) : null,
    details: p.details ?? '',
    bonusTypeId: '',
  }
}

const numOrNull = (s: string): number | null => {
  const n = parseFloat(s)
  return Number.isFinite(n) ? n : null
}

const strOrNull = (s: string): string | null => (s.trim() ? s : null)

export function rowToPayload(row: ParticipantRow, eventId: number): BonusPayload {
  return {
    employee_id: row.userId,
    event_id: eventId,
    year: row.year,
    month: row.month,
    participation_start: strOrNull(row.partStart),
    participation_end: strOrNull(row.partEnd),
    bonus_days: numOrNull(row.bonusDays),
    hours_free: numOrNull(row.hoursFree),
    bonus_net: row.bonusNet,
    details: strOrNull(row.details),
  }
}

const samePayload = (a: BonusPayload, b: BonusPayload): boolean =>
  a.participation_start === b.participation_start &&
  a.participation_end === b.participation_end &&
  a.bonus_days === b.bonus_days &&
  a.hours_free === b.hours_free &&
  a.bonus_net === b.bonus_net &&
  a.details === b.details &&
  a.year === b.year &&
  a.month === b.month

export function diffParticipantRows(
  original: EventParticipant[],
  rows: ParticipantRow[],
  eventId: number,
): SaveOps {
  const originalById = new Map(original.map((p) => [p.id, p]))
  const keptIds = new Set(rows.filter((r) => r.id != null).map((r) => r.id as number))

  const creates: BonusPayload[] = []
  const updates: { id: number; data: BonusPayload }[] = []

  for (const row of rows) {
    const payload = rowToPayload(row, eventId)
    if (row.id == null) {
      creates.push(payload)
      continue
    }
    const orig = originalById.get(row.id)
    if (orig && !samePayload(payload, rowToPayload(participantToRow(orig), eventId))) {
      updates.push({ id: row.id, data: payload })
    }
  }

  const deletes = original.filter((p) => !keptIds.has(p.id)).map((p) => p.id)

  return { creates, updates, deletes }
}
