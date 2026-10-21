import { describe, it, expect } from 'vitest'
import { DOCUMENT_TYPES, DOCUMENT_TYPE_LABELS } from './carpark'

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
