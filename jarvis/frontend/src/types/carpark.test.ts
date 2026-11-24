import { describe, it, test, expect } from 'vitest'
import { type CostType, COST_TYPE_LABELS, DOCUMENT_TYPES, DOCUMENT_TYPE_LABELS } from './carpark'

describe('CostType and COST_TYPE_LABELS', () => {
  test('achizitie label is "Achiziție"', () => {
    expect(COST_TYPE_LABELS.achizitie).toBe('Achiziție')
  })

  test('achizitie is assignable to CostType', () => {
    // This test verifies type-level exhaustiveness: if 'achizitie' is not in CostType,
    // TypeScript will fail to compile this file.
    const costType: CostType = 'achizitie'
    expect(costType).toBe('achizitie')
  })
})

// Pins the FE/BE coordination for the new "Documente vânzare" warranty
// certificate doc type: backend documents.py's VALID_DOCUMENT_TYPES now
// includes 'garantie' (Task 6), so the frontend's document-type list and
// its Romanian label must stay in sync.
describe('DocumentType — garantie', () => {
  it('includes garantie in DOCUMENT_TYPES', () => {
    expect(DOCUMENT_TYPES).toContain('garantie')
  })

  it('labels garantie as "Certificat garanție"', () => {
    expect(DOCUMENT_TYPE_LABELS.garantie).toBe('Certificat garanție')
  })
})
