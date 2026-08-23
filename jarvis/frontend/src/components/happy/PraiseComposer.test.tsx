import { describe, it, expect } from 'vitest'
import { canSubmitKudos, MIN_NOTE_LENGTH } from './PraiseComposer'

const shortNote = 'a'.repeat(MIN_NOTE_LENGTH - 1) // 39 chars
const longNote = 'a'.repeat(MIN_NOTE_LENGTH) // 40 chars

describe('canSubmitKudos', () => {
  it('is disabled when the note is under 40 characters', () => {
    expect(canSubmitKudos({ recipientId: 5, valueTagId: 2, note: shortNote })).toBe(false)
  })

  it('is enabled once recipient, value tag and a >=40-char note are all present', () => {
    expect(canSubmitKudos({ recipientId: 5, valueTagId: 2, note: longNote })).toBe(true)
  })

  it('requires a recipient', () => {
    expect(canSubmitKudos({ recipientId: null, valueTagId: 2, note: longNote })).toBe(false)
  })

  it('requires a value tag', () => {
    expect(canSubmitKudos({ recipientId: 5, valueTagId: null, note: longNote })).toBe(false)
  })

  it('ignores surrounding whitespace when counting the note', () => {
    expect(canSubmitKudos({ recipientId: 5, valueTagId: 2, note: `   ${shortNote}   ` })).toBe(false)
  })

  it('is disabled while a submit is in flight', () => {
    expect(canSubmitKudos({ recipientId: 5, valueTagId: 2, note: longNote, submitting: true })).toBe(false)
  })
})
