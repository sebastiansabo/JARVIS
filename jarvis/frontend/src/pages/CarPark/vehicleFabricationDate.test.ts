import { describe, test, expect } from 'vitest'
import { deriveFabParts, fabToManufactureDate } from './vehicleFabricationDate'

describe('deriveFabParts', () => {
  test('reads month + year from a stored manufacture_date', () => {
    expect(deriveFabParts('2020-06-01', 2020)).toEqual({ month: '06', year: '2020' })
  })

  test('falls back to year_of_manufacture when manufacture_date is null', () => {
    // Regression: imported/VIN-decoded cars have no manufacture_date but do have
    // year_of_manufacture — the year selector must still show the year.
    expect(deriveFabParts(null, 2018)).toEqual({ month: '', year: '2018' })
  })

  test('falls back to year_of_manufacture when manufacture_date is empty', () => {
    expect(deriveFabParts('', 2018)).toEqual({ month: '', year: '2018' })
  })

  test('year is blank only when both sources are absent', () => {
    expect(deriveFabParts(null, null)).toEqual({ month: '', year: '' })
  })

  test('manufacture_date year wins over year_of_manufacture', () => {
    expect(deriveFabParts('2019-03-01', 2020)).toEqual({ month: '03', year: '2019' })
  })
})

describe('fabToManufactureDate', () => {
  test('composes YYYY-MM-01 and mirrors the year', () => {
    expect(fabToManufactureDate('06', '2020')).toEqual({
      manufacture_date: '2020-06-01',
      year_of_manufacture: 2020,
    })
  })

  test('defaults the month to January when none is chosen', () => {
    expect(fabToManufactureDate('', '2020')).toEqual({
      manufacture_date: '2020-01-01',
      year_of_manufacture: 2020,
    })
  })

  test('does not fabricate a year (caller resolves fallback)', () => {
    // A real year passed in is preserved verbatim — no silent reset to "now".
    expect(fabToManufactureDate('05', '2015').year_of_manufacture).toBe(2015)
  })
})
