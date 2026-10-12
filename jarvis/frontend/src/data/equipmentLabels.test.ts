import { describe, test, expect } from 'vitest'
import { humanizeSlug, equipmentLabel } from './autovitData'

describe('humanizeSlug', () => {
  test('humanizes raw underscore equipment keys', () => {
    expect(humanizeSlug('antilock_brake_system')).toBe('Antilock Brake System')
    expect(humanizeSlug('windscreenwiper_other')).toBe('Windscreenwiper Other')
  })

  test('keeps automotive acronyms uppercase', () => {
    expect(humanizeSlug('abs')).toBe('ABS')
    expect(humanizeSlug('awd')).toBe('AWD')
    expect(humanizeSlug('usb_in')).toBe('USB In')
  })

  test('strips Autovit version/generation prefixes and cleans up slugs', () => {
    expect(humanizeSlug('ver-t5-awd-inscription', { stripVersionPrefix: true })).toBe('T5 AWD Inscription')
    expect(humanizeSlug('gen-ii-2017', { stripVersionPrefix: true })).toBe('II 2017')
  })

  test('does not strip the prefix unless asked', () => {
    expect(humanizeSlug('ver-t5-awd-inscription')).toBe('Ver T5 AWD Inscription')
  })

  test('preserves already mixed-case tokens', () => {
    expect(humanizeSlug('sDrive18d')).toBe('sDrive18d')
  })

  test('leaves clean manual input intact', () => {
    expect(humanizeSlug('T5 AWD Inscription')).toBe('T5 AWD Inscription')
  })

  test('handles empty / nullish input', () => {
    expect(humanizeSlug('')).toBe('')
    expect(humanizeSlug(null)).toBe('')
    expect(humanizeSlug(undefined)).toBe('')
  })
})

describe('equipmentLabel', () => {
  test('resolves curated RO labels for raw underscore keys', () => {
    expect(equipmentLabel('apple_carplay')).toBe('Apple CarPlay')
    expect(equipmentLabel('navigation_system')).toBe('Sistem de navigație')
  })

  test('resolves hyphen taxonomy slugs (equipment_options)', () => {
    expect(equipmentLabel('heated-seats-front')).toBe('Scaune încălzite față')
  })

  test('normalizes underscores to hit the hyphen taxonomy', () => {
    // not in the curated raw map, but matches 'heated-seats-front' once normalized
    expect(equipmentLabel('heated_seats_front')).toBe('Scaune încălzite față')
  })

  test('falls back to humanized text for unknown keys', () => {
    expect(equipmentLabel('some_unmapped_feature')).toBe('Some Unmapped Feature')
  })

  test('handles empty input', () => {
    expect(equipmentLabel('')).toBe('')
  })
})
