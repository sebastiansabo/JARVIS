import { describe, it, expect, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import AcorduriPage from './AcorduriPage'

// PageHeader → useIsMobile() calls window.matchMedia, which jsdom doesn't
// implement. Stub it so the desktop layout renders (matches: false).
beforeAll(() => {
  window.matchMedia =
    window.matchMedia ||
    ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList)
})

describe('AcorduriPage', () => {
  it('renders a link for each of the three consent documents with the correct href', () => {
    render(
      <MemoryRouter>
        <AcorduriPage />
      </MemoryRouter>,
    )

    const dataUsage = screen.getByRole('link', { name: /Acord privind utilizarea datelor de contact/ })
    const gdpr = screen.getByRole('link', { name: /Notă de informare și acord GDPR/ })
    const nda = screen.getByRole('link', { name: /Acord de confidențialitate \(NDA\)/ })

    expect(dataUsage).toHaveAttribute('href', '/app/acord/data_usage')
    expect(gdpr).toHaveAttribute('href', '/app/acord/gdpr')
    expect(nda).toHaveAttribute('href', '/app/acord/nda')
  })
})
