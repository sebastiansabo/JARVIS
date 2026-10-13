import { afterEach, describe, expect, it } from 'vitest'
import { draftKey, isDraftDirty, loadDraft, saveDraft, clearDraft } from './buybackDraft'

const empty = { brand: '', model: '', vin: '', seller_name: '', images: [], advisor_id: 0, advisor_name: '' }

afterEach(() => localStorage.clear())

describe('buybackDraft', () => {
  it('keys drafts per user', () => {
    expect(draftKey(7)).toBe('buyback.draft.v1.7')
    expect(draftKey(7)).not.toBe(draftKey(8))
    expect(draftKey(null)).toBe('buyback.draft.v1.anon')
  })

  it('round-trips a draft but strips images + advisor', () => {
    saveDraft(7, { ...empty, brand: 'BMW', images: ['data:huge'], advisor_id: 99, advisor_name: 'X' })
    const d = loadDraft<Record<string, unknown>>(7)
    expect(d?.brand).toBe('BMW')
    expect('images' in (d ?? {})).toBe(false)
    expect('advisor_id' in (d ?? {})).toBe(false)
    expect('advisor_name' in (d ?? {})).toBe(false)
  })

  it('isolates drafts between users', () => {
    saveDraft(7, { ...empty, brand: 'BMW' })
    expect(loadDraft(8)).toBeNull()
  })

  it('isDraftDirty ignores the auto-filled advisor and images', () => {
    // Only advisor/images differ from empty → not dirty.
    expect(isDraftDirty({ ...empty, advisor_id: 5, advisor_name: 'Me', images: ['x'] }, empty)).toBe(false)
    // A real content field differs → dirty.
    expect(isDraftDirty({ ...empty, vin: 'WVWZZZ' }, empty)).toBe(true)
  })

  it('clearDraft removes the stored draft', () => {
    saveDraft(7, { ...empty, brand: 'BMW' })
    clearDraft(7)
    expect(loadDraft(7)).toBeNull()
  })

  it('loadDraft tolerates corrupt JSON', () => {
    localStorage.setItem(draftKey(7), '{not json')
    expect(loadDraft(7)).toBeNull()
  })
})
