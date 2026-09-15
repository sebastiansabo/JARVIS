import { render, screen } from '@testing-library/react'
import { ListingFreshness } from './ListingFreshness'

it('shows the up-to-date label', () => {
  render(<ListingFreshness freshness="up_to_date" lastSync="2026-09-15T10:00:00Z" expiresAt={null} />)
  expect(screen.getByText('La zi')).toBeInTheDocument()
})
it('shows the stale label', () => {
  render(<ListingFreshness freshness="stale" lastSync={null} expiresAt={null} />)
  expect(screen.getByText('Necesită actualizare')).toBeInTheDocument()
})
it('shows expired', () => {
  render(<ListingFreshness freshness="expired" lastSync={null} expiresAt="2026-09-01T00:00:00Z" />)
  expect(screen.getByText('Expirat')).toBeInTheDocument()
})
