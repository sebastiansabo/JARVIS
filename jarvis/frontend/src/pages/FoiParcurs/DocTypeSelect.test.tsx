import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import DocTypeSelect from './DocTypeSelect'

const TYPES = [
  { key: 'sales', label: 'Vânzări', is_rental: false },
  { key: 'service', label: 'Mașini de curtoazie', is_rental: true },
  { key: 'comodat', label: 'Comodat', is_rental: false },
]

describe('DocTypeSelect', () => {
  it('shows the currently-selected type label', () => {
    render(<DocTypeSelect value="service" types={TYPES} onChange={vi.fn()} />)
    expect(screen.getByText('Mașini de curtoazie')).toBeInTheDocument()
  })

  it('reflects a different selected key', () => {
    render(<DocTypeSelect value="comodat" types={TYPES} onChange={vi.fn()} />)
    expect(screen.getByText('Comodat')).toBeInTheDocument()
  })
})
