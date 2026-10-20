import { describe, it, expect } from 'vitest'
import { vinHistoryWarning, fmtEur, fmtDate } from './buybackVinHistory'
import type { VinHistoryEntry } from '@/types/buyback'

const base: VinHistoryEntry = {
  id: 1,
  record_code: 'BB-1',
  company_id: 10,
  company_name: 'Autoworld International',
  advisor_name: 'Arthur',
  status: 'FINAL_OFFER',
  created_at: '2026-10-14T09:00:00Z',
  client_asking_price_eur: 10000,
  market_price_eur: 9000,
  purchase_price_eur: null,
  last_offer_eur: 8500,
  last_offer_type: 'final',
  last_offer_vat: 'no_vat',
  last_offer_at: '2026-10-14T10:00:00Z',
}

describe('vinHistoryWarning', () => {
  it('returns null for empty history', () => {
    expect(vinHistoryWarning([])).toBeNull()
  })

  it('summarizes the most recent evaluation: company, date, last offer', () => {
    const msg = vinHistoryWarning([base])!
    expect(msg).toContain('Evaluat anterior')
    expect(msg).toContain('Autoworld International')
    expect(msg).toContain((8500).toLocaleString('ro-RO'))
  })

  it('notes how many earlier evaluations exist beyond the latest', () => {
    const msg = vinHistoryWarning([base, { ...base, id: 2 }, { ...base, id: 3 }])!
    expect(msg).toContain('+2')
  })

  it('says "fără ofertă" when the prior record had no offer', () => {
    const msg = vinHistoryWarning([{ ...base, last_offer_eur: null }])!
    expect(msg).toContain('fără ofertă')
  })
})

describe('fmt helpers', () => {
  it('fmtEur formats a number with ro-RO grouping + euro sign, dash for null', () => {
    expect(fmtEur(8500)).toBe(`${(8500).toLocaleString('ro-RO')} €`)
    expect(fmtEur(null)).toBe('—')
  })
  it('fmtDate formats an ISO date, dash for empty/invalid', () => {
    expect(fmtDate('')).toBe('—')
    expect(fmtDate('not-a-date')).toBe('—')
    expect(fmtDate('2026-10-14T09:00:00Z')).toMatch(/2026/)
  })
})
