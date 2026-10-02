import { describe, it, expect } from 'vitest'
import { withGaps, sheetKmSpan } from './gaps'
import type { FoiContract } from '@/types/foiParcurs'

const s = (o: Partial<FoiContract>): FoiContract => o as FoiContract

// The MG S9 October sheet from the bug report: three not-yet-driven PLANNED
// bookings (0-0) plus real drives whose lowest odometer is 1642. The planned
// bookings must not anchor the odometer chain — otherwise the jump from their
// 0 reading up to 1642 renders as a phantom "Gap kilometraj (nejustificat)".
const plannedSheet = (): FoiContract[] => [
  s({ id: 101, status: 'PLANNED', km_start: 0, km_end: 0, client_name: 'Adrian Boros', created_at: '2026-10-02' }),
  s({ id: 102, status: 'PLANNED', km_start: 0, km_end: 0, client_name: 'Valentin Pantea', created_at: '2026-10-02' }),
  s({ id: 103, status: 'PLANNED', km_start: 0, km_end: 0, client_name: 'Adrian Noja', created_at: '2026-10-03' }),
  s({ id: 1, status: 'COMPLETED', is_internal: true, km_start: 1642, km_end: 1670, advisor_name: 'Margineanu Irina', created_at: '2026-10-01' }),
  s({ id: 2, status: 'COMPLETED', km_start: 1678, km_end: 1680, client_name: 'Teusdea Cristian', created_at: '2026-09-25' }),
  s({ id: 3, status: 'COMPLETED', km_start: 1680, km_end: 1689, client_name: 'Grecu Cosmin', created_at: '2026-10-01' }),
  s({ id: 4, status: 'COMPLETED', km_start: 1759, km_end: 1770, client_name: 'Karoly Molnar', created_at: '2026-10-02' }),
]

describe('withGaps — PLANNED sessions do not manufacture gaps', () => {
  it('emits no phantom gap from the 0 baseline up to the first real drive', () => {
    const rows = withGaps(plannedSheet(), 1642, 1770)
    const gaps = rows.filter((r) => r.gap)
    expect(gaps.some((g) => g.gap && g.kmStart === 0)).toBe(false)
    expect(gaps.some((g) => g.gap && g.distance === 1642)).toBe(false)
  })

  it('still reports the real gaps between completed drives', () => {
    const rows = withGaps(plannedSheet(), 1642, 1770)
    const spans = rows.filter((r) => r.gap).map((g) => (g.gap ? `${g.kmStart}-${g.kmEnd}` : ''))
    expect(spans).toContain('1670-1678') // Margineanu → Teusdea
    expect(spans).toContain('1689-1759') // Grecu → Karoly
  })

  it('still lists the planned bookings as rows', () => {
    const rows = withGaps(plannedSheet(), 1642, 1770)
    const sessionIds = rows.filter((r) => !r.gap).map((r) => (r.gap ? 0 : r.session.id))
    expect(sessionIds).toEqual(expect.arrayContaining([101, 102, 103]))
  })
})

describe('sheetKmSpan — PLANNED bookings never pull the baseline to 0', () => {
  it('spans only the real drives, ignoring 0-0 planned rows', () => {
    expect(sheetKmSpan(plannedSheet())).toEqual({ kmMin: 1642, kmMax: 1770 })
  })

  it('returns an empty span when the sheet has only planned bookings', () => {
    const span = sheetKmSpan([
      s({ id: 101, status: 'PLANNED', km_start: 0, km_end: 0 }),
      s({ id: 102, status: 'PLANNED', km_start: 0, km_end: 0 }),
    ])
    expect(Number.isFinite(span.kmMin)).toBe(false)
    expect(Number.isFinite(span.kmMax)).toBe(false)
  })

  it('counts a real drive that genuinely starts at 0', () => {
    expect(sheetKmSpan([
      s({ id: 1, status: 'COMPLETED', km_start: 0, km_end: 60 }),
      s({ id: 2, status: 'COMPLETED', km_start: 60, km_end: 120 }),
    ])).toEqual({ kmMin: 0, kmMax: 120 })
  })
})

describe('withGaps — behaviour unchanged without PLANNED rows', () => {
  it('keeps a genuine leading boundary gap (hidden internal drive below first trip)', () => {
    // Toggle "Sesiuni interne" off hides an internal drive that moved the car
    // from 1600→1642; kmMin (1600) still reflects it, so the leftover shows as a
    // leading gap attributed to the first visible client trip.
    const rows = withGaps([
      s({ id: 10, status: 'COMPLETED', km_start: 1642, km_end: 1670, client_name: 'A', created_at: '2026-10-01' }),
    ], 1600, 1670)
    const gaps = rows.filter((r) => r.gap)
    expect(gaps.length).toBe(1)
    expect(gaps[0].gap && gaps[0].kmStart).toBe(1600)
    expect(gaps[0].gap && gaps[0].kmEnd).toBe(1642)
  })
})
