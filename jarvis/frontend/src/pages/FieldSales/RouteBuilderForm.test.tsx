import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const createMyRoute = vi.fn()
vi.mock('@/api/fieldSales', () => ({ fieldSalesApi: { createMyRoute: (...a: unknown[]) => createMyRoute(...a) } }))
// Needed because RouteBuilderForm imports VISIT_TYPE_LABELS from the panel module.
vi.mock('@/pages/Hub/HubFieldSalesPanel', () => ({ VISIT_TYPE_LABELS: { general: 'General', prospecting: 'Prospectare' } }))
// Stub the picker: render two buttons that each add a fixed client via onPick.
vi.mock('./FSClientPicker', () => ({
  default: ({ onPick }: { onPick: (c: { id: number; display_name: string }) => void }) => (
    <div>
      <button onClick={() => onPick({ id: 1, display_name: 'Client A' })}>pick-A</button>
      <button onClick={() => onPick({ id: 2, display_name: 'Client B' })}>pick-B</button>
    </div>
  ),
}))
import RouteBuilderForm from './RouteBuilderForm'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('RouteBuilderForm', () => {
  // Braces (not an implicit-return arrow) matter here: `mockReset()` returns
  // the mock itself for chaining, and Vitest 3.x treats a function value
  // returned from a hook as an auto-registered post-test cleanup callback. An
  // implicit-return version re-invokes the mock (with zero args) after the
  // test completes, which — while a rejection is still the configured
  // implementation (the error-surfacing test below) — produces an unhandled
  // rejection that fails that test spuriously.
  beforeEach(() => { createMyRoute.mockReset() })

  it('submit is disabled with no stops', () => {
    wrap(<RouteBuilderForm companyId={7} onDone={() => {}} onCancel={() => {}} />)
    expect(screen.getByRole('button', { name: /creeaz[aă] ruta/i })).toBeDisabled()
  })

  it('adds two stops, removes one, and submits a kam_id-free payload', async () => {
    createMyRoute.mockResolvedValue({ success: true, route: { id: 10, visits: [] } })
    const onDone = vi.fn()
    wrap(<RouteBuilderForm companyId={7} onDone={onDone} onCancel={() => {}} />)
    fireEvent.click(screen.getByText('Adauga oprire'))
    fireEvent.click(screen.getByText('pick-A'))
    fireEvent.click(screen.getByText('Adauga oprire'))
    fireEvent.click(screen.getByText('pick-B'))
    // remove the first stop (Client A)
    fireEvent.click(screen.getAllByLabelText(/sterge oprire/i)[0])
    fireEvent.click(screen.getByRole('button', { name: /creeaz[aă] ruta/i }))
    await waitFor(() => expect(onDone).toHaveBeenCalled())
    const payload = createMyRoute.mock.calls[0][0] as Record<string, unknown>
    expect(payload).not.toHaveProperty('kam_id')
    expect(payload.stops).toEqual([{ client_id: 2, visit_type: 'general' }])
  })

  it('surfaces the backend error inline on failure', async () => {
    createMyRoute.mockRejectedValue({ data: { error: 'Stop 1: client dintr-o companie neautorizată' } })
    wrap(<RouteBuilderForm companyId={7} onDone={() => {}} onCancel={() => {}} />)
    fireEvent.click(screen.getByText('Adauga oprire'))
    fireEvent.click(screen.getByText('pick-A'))
    fireEvent.click(screen.getByRole('button', { name: /creeaz[aă] ruta/i }))
    expect(await screen.findByText(/companie neautorizat/i)).toBeInTheDocument()
  })
})
