import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

const { getTestDrive, submitTestDriveReturn } = vi.hoisted(() => ({
  getTestDrive: vi.fn(),
  submitTestDriveReturn: vi.fn().mockResolvedValue({ success: true, contract: { id: 5, status: 'COMPLETED' } }),
}))
vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: { getTestDrive, submitTestDriveReturn } }))
// SignatureCanvas is a lazy canvas widget — stub it to a button that emits a signature.
vi.mock('@/components/shared/SignatureCanvas', () => ({
  default: ({ onSave }: { onSave: (s: string) => void }) => (
    <button onClick={() => onSave('data:sig')}>sign</button>
  ),
}))

import TestDriveReturn from './TestDriveReturn'

// TestDriveReturn always calls useNavigate()/useParams() (dual route/embedded
// mode), which requires a Router ancestor even in embedded mode — the app
// shell already provides one in production, so the test supplies a MemoryRouter.
function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('TestDriveReturn (embedded)', () => {
  beforeEach(() => { getTestDrive.mockReset(); submitTestDriveReturn.mockClear() })

  it('blocks an already-completed drive', async () => {
    getTestDrive.mockResolvedValue({ contract: { id: 5, status: 'COMPLETED', km_start: 100 } })
    wrap(<TestDriveReturn id={5} embedded onDone={vi.fn()} />)
    expect(await screen.findByText(/deja finalizat/i)).toBeInTheDocument()
  })

  it('submits a valid return and calls onDone', async () => {
    getTestDrive.mockResolvedValue({ contract: { id: 5, status: 'FILLED', km_start: 100, departure_damage: [] } })
    const onDone = vi.fn()
    wrap(<TestDriveReturn id={5} embedded onDone={onDone} />)
    // fill km, fuel, both signatures
    fireEvent.change(await screen.findByLabelText(/km retur/i), { target: { value: '150' } })
    fireEvent.click(screen.getByRole('button', { name: 'Plin' }))
    const signBtns = screen.getAllByRole('button', { name: 'sign' })
    fireEvent.click(signBtns[0]); fireEvent.click(signBtns[1])
    fireEvent.click(screen.getByRole('button', { name: /finalizează/i }))
    await waitFor(() => expect(submitTestDriveReturn).toHaveBeenCalledWith(5, expect.objectContaining({ km_end: 150, fuel_gauge_end_level: 'Plin' })))
    await waitFor(() => expect(onDone).toHaveBeenCalled())
  })
})
