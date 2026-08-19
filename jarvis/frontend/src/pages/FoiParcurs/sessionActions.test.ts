import { describe, it, expect } from 'vitest'
import { sessionActionLabel } from './sessionActions'

describe('sessionActionLabel', () => {
  it('maps known action codes to Romanian labels', () => {
    expect(sessionActionLabel('return')).toBe('Retur înregistrat')
    expect(sessionActionLabel('activate')).toBe('Activat')
    expect(sessionActionLabel('correct')).toBe('Corectat')
    expect(sessionActionLabel('extend')).toBe('Retur prelungit')
    expect(sessionActionLabel('create')).toBe('Creat')
  })

  it('falls back to the raw code for unknown/future actions', () => {
    expect(sessionActionLabel('teleport')).toBe('teleport')
  })
})
