import { describe, test, expect } from 'vitest'
import { findMissingRequiredFields } from './vehicleFormValidation'

const complete = {
  vin: 'WAUZZZ4M1PD000777',
  brand: 'Audi',
  model: 'RS Q8',
  category: 'SH',
  list_price: 45000,
}

describe('findMissingRequiredFields', () => {
  test('a complete create form has nothing missing', () => {
    expect(findMissingRequiredFields(complete, false)).toEqual([])
  })

  test('flags every empty required field on create', () => {
    const labels = findMissingRequiredFields({}, false).map((m) => m.label)
    expect(labels).toEqual(
      expect.arrayContaining(['VIN (minim 5 caractere)', 'Marcă', 'Model', 'Tip stoc (categorie)', 'Preț listă']),
    )
  })

  test('requires Tip stoc (categorie) when category is blank', () => {
    const labels = findMissingRequiredFields({ ...complete, category: '' }, false).map((m) => m.label)
    expect(labels).toContain('Tip stoc (categorie)')
  })

  test('still requires Tip stoc (categorie) on edit', () => {
    const labels = findMissingRequiredFields({ ...complete, category: null }, true).map((m) => m.label)
    expect(labels).toContain('Tip stoc (categorie)')
  })

  test('does not require Preț listă on edit', () => {
    const labels = findMissingRequiredFields({ ...complete, list_price: null }, true).map((m) => m.label)
    expect(labels).not.toContain('Preț listă')
  })

  test('flags a too-short VIN', () => {
    const labels = findMissingRequiredFields({ ...complete, vin: 'AB' }, false).map((m) => m.label)
    expect(labels).toContain('VIN (minim 5 caractere)')
  })

  test('points each missing field at the tab that contains it', () => {
    const miss = findMissingRequiredFields({ ...complete, category: '', list_price: null }, false)
    expect(miss.find((m) => m.label.startsWith('Tip stoc'))?.tab).toBe('vehicul')
    expect(miss.find((m) => m.label === 'Preț listă')?.tab).toBe('comercial')
  })
})
