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
      expect.arrayContaining(['VIN (17 caractere, ISO 3779)', 'Marcă', 'Model', 'Tip stoc (categorie)', 'Preț listă']),
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

  test('flags a 16-char VIN on create (backend requires exactly 17 → would 500)', () => {
    const labels = findMissingRequiredFields({ ...complete, vin: 'WAUZZZ4M1PD00077' }, false).map((m) => m.label)
    expect(labels).toContain('VIN (17 caractere, ISO 3779)')
  })

  test('flags a VIN containing I/O/Q on create (not ISO-3779)', () => {
    const labels = findMissingRequiredFields({ ...complete, vin: 'WAUZZZ4M1PD0007IO' }, false).map((m) => m.label)
    expect(labels).toContain('VIN (17 caractere, ISO 3779)')
  })

  test('accepts a valid lower-case 17-char VIN on create', () => {
    const labels = findMissingRequiredFields({ ...complete, vin: 'wauzzz4m1pd000777' }, false).map((m) => m.label)
    expect(labels).not.toContain('VIN (17 caractere, ISO 3779)')
  })

  test('does not block editing an existing car whose VIN is not 17 chars', () => {
    // The backend validates VIN format only on create, and legacy/imported cars
    // may have imperfect VINs — editing them must not be blocked.
    const labels = findMissingRequiredFields({ ...complete, vin: 'LEGACY123' }, true).map((m) => m.label)
    expect(labels).not.toContain('VIN (17 caractere, ISO 3779)')
  })

  test('points each missing field at the tab that contains it', () => {
    const miss = findMissingRequiredFields({ ...complete, category: '', list_price: null }, false)
    expect(miss.find((m) => m.label.startsWith('Tip stoc'))?.tab).toBe('vehicul')
    expect(miss.find((m) => m.label === 'Preț listă')?.tab).toBe('comercial')
  })
})

import {
  isCustodyCategory,
  normalizeCategory,
  clearAcquisitionFields,
} from './vehicleFormValidation'

describe('isCustodyCategory', () => {
  test('true for custody-type stock (held, not purchased)', () => {
    expect(isCustodyCategory('CUS')).toBe(true)
    expect(isCustodyCategory('CON')).toBe(true)
  })
  test('false for purchased/other stock and blanks', () => {
    expect(isCustodyCategory('SH')).toBe(false)
    expect(isCustodyCategory('TI')).toBe(false)
    expect(isCustodyCategory('')).toBe(false)
    expect(isCustodyCategory(undefined)).toBe(false)
  })
})

describe('normalizeCategory', () => {
  test('passes through valid codes (case-insensitive)', () => {
    expect(normalizeCategory('CUS')).toBe('CUS')
    expect(normalizeCategory('sh')).toBe('SH')
  })
  test('maps Romanian labels (and diacritics) to codes', () => {
    expect(normalizeCategory('Custodie')).toBe('CUS')
    expect(normalizeCategory('Consemnație')).toBe('CON')
    expect(normalizeCategory('Consemnatie')).toBe('CON')
    expect(normalizeCategory('Second Hand')).toBe('SH')
    expect(normalizeCategory('Nou')).toBe('NEW')
    expect(normalizeCategory('Trade-In')).toBe('TI')
  })
  test('blank stays blank; unknown value is kept (never silently dropped)', () => {
    expect(normalizeCategory('')).toBe('')
    expect(normalizeCategory(null)).toBe('')
    expect(normalizeCategory('Buyback')).toBe('Buyback')
  })
})

describe('clearAcquisitionFields', () => {
  test('nulls supplier + cost-basis fields, leaves the rest', () => {
    const out = clearAcquisitionFields({
      supplier_name: 'ACME', supplier_cif: 'RO1', acquisition_price: 10000,
      purchase_price_net: 8000, acquisition_vat: 1600, acquisition_exchange_rate: 5,
      brand: 'Audi', list_price: 25000,
    })
    expect(out.supplier_name).toBeNull()
    expect(out.acquisition_price).toBeNull()
    expect(out.purchase_price_net).toBeNull()
    expect(out.acquisition_vat).toBeNull()
    expect(out.brand).toBe('Audi')      // untouched
    expect(out.list_price).toBe(25000)  // untouched
  })
})
