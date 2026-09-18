import { describe, test, expect } from 'vitest'
import {
  validateListPriceOnCreate,
  seedCurrentPriceOnCreate,
  activeSellingPrice,
} from './vehicleFormPricing'

describe('activeSellingPrice', () => {
  test('prefers the promo price when set', () => {
    expect(activeSellingPrice({ list_price: 45000, promotional_price: 42000 })).toBe(42000)
  })

  test('falls back to the list price when there is no promo', () => {
    expect(activeSellingPrice({ list_price: 45000, promotional_price: null })).toBe(45000)
  })

  test('ignores a zero or negative promo and uses the list price', () => {
    expect(activeSellingPrice({ list_price: 45000, promotional_price: 0 })).toBe(45000)
  })

  test('returns null when neither price is set', () => {
    expect(activeSellingPrice({ list_price: null, promotional_price: null })).toBeNull()
  })
})

describe('validateListPriceOnCreate', () => {
  test('blocks create when list price is missing', () => {
    expect(validateListPriceOnCreate({ list_price: null }, false)).toBe(
      'Prețul de listă este obligatoriu',
    )
  })

  test('blocks create when list price is zero', () => {
    expect(validateListPriceOnCreate({ list_price: 0 }, false)).toBe(
      'Prețul de listă este obligatoriu',
    )
  })

  test('blocks create when list price is negative', () => {
    expect(validateListPriceOnCreate({ list_price: -100 }, false)).toBe(
      'Prețul de listă este obligatoriu',
    )
  })

  test('allows create when list price is a positive number', () => {
    expect(validateListPriceOnCreate({ list_price: 45000 }, false)).toBeNull()
  })

  test('does not block editing an existing car without a list price', () => {
    expect(validateListPriceOnCreate({ list_price: null }, true)).toBeNull()
  })
})

describe('seedCurrentPriceOnCreate', () => {
  test('seeds current_price from list_price on create when current is unset', () => {
    const out = seedCurrentPriceOnCreate({ list_price: 45000, current_price: null }, false)
    expect(out.current_price).toBe(45000)
  })

  test('seeds current_price from the promo price when a promo is set on create', () => {
    const out = seedCurrentPriceOnCreate(
      { list_price: 45000, promotional_price: 42000, current_price: null },
      false,
    )
    expect(out.current_price).toBe(42000)
  })

  test('does not overwrite an already-set current_price on create', () => {
    const out = seedCurrentPriceOnCreate({ list_price: 45000, current_price: 40000 }, false)
    expect(out.current_price).toBe(40000)
  })

  test('does not seed current_price on edit', () => {
    const out = seedCurrentPriceOnCreate({ list_price: 45000, current_price: null }, true)
    expect(out.current_price).toBeNull()
  })
})
