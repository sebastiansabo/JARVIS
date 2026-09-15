import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ListingScheduleSelect } from './ListingScheduleSelect'

it('renders the cadence trigger', () => {
  const qc = new QueryClient()
  render(
    <QueryClientProvider client={qc}>
      <ListingScheduleSelect vehicleId={1} platform="shopify" />
    </QueryClientProvider>,
  )
  expect(screen.getByText(/Actualizare automată/)).toBeInTheDocument()
})
