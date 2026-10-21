import type { ReactNode } from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { carparkSaleDocsApi } from '@/api/carparkSaleDocs'
import { LeasingCompanySelect } from './LeasingCompanySelect'
import type { LeasingCompany } from '@/types/carpark'

vi.mock('@/api/carparkSaleDocs', () => ({
  carparkSaleDocsApi: {
    listLeasingCompanies: vi.fn(() =>
      Promise.resolve({
        leasing_companies: [
          { id: 1, name: 'BT Leasing IFN' },
          { id: 2, name: 'BCR Leasing' },
        ] as LeasingCompany[],
      }),
    ),
    createLeasingCompany: vi.fn(),
  },
}))

// The real shadcn Select is Radix-backed: while closed it renders its items
// into a detached DocumentFragment (a portal), so option labels never hit the
// queryable DOM, and jsdom lacks the layout APIs Radix probes on open. Rather
// than drive that flaky open-the-portal path, stub the Select primitives as
// plain DOM so the mapped company names render inline and can be asserted
// directly. The inline-add form (plain Input/Button) is untouched by this mock.
vi.mock('@/components/ui/select', () => {
  const Passthrough = ({ children }: { children?: ReactNode }) => <div>{children}</div>
  return {
    Select: Passthrough,
    SelectTrigger: Passthrough,
    SelectContent: Passthrough,
    SelectValue: ({ placeholder }: { placeholder?: string }) => <span>{placeholder}</span>,
    SelectItem: ({ children }: { children?: ReactNode }) => <div role="option">{children}</div>,
  }
})

function renderSelect(onSelect = vi.fn(), value: number | null = null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const utils = render(
    <QueryClientProvider client={qc}>
      <LeasingCompanySelect value={value} onSelect={onSelect} />
    </QueryClientProvider>,
  )
  return { ...utils, onSelect }
}

const addButton = () => screen.getByRole('button', { name: /adaugă firmă de leasing/i })

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(carparkSaleDocsApi.listLeasingCompanies).mockResolvedValue({
    leasing_companies: [
      { id: 1, name: 'BT Leasing IFN' },
      { id: 2, name: 'BCR Leasing' },
    ] as LeasingCompany[],
  })
})

describe('LeasingCompanySelect', () => {
  it('renders options for the fetched leasing companies', async () => {
    renderSelect()
    // The query unwraps `.leasing_companies` and maps each into an option;
    // both names must land in the DOM (no dropdown-open needed).
    expect(await screen.findByText('BT Leasing IFN')).toBeInTheDocument()
    expect(await screen.findByText('BCR Leasing')).toBeInTheDocument()
  })

  it('"Adaugă firmă de leasing" submits create and selects the returned company', async () => {
    const created: LeasingCompany = { id: 3, name: 'Raiffeisen Leasing' }
    vi.mocked(carparkSaleDocsApi.createLeasingCompany).mockResolvedValue({ leasing_company: created })

    const { onSelect } = renderSelect()
    await screen.findByText('BT Leasing IFN') // let the initial query settle

    fireEvent.click(addButton())

    const nameInput = screen.getByLabelText(/^nume/i)
    fireEvent.change(nameInput, { target: { value: 'Raiffeisen Leasing' } })

    fireEvent.click(screen.getByRole('button', { name: /salvează/i }))

    await waitFor(() =>
      expect(carparkSaleDocsApi.createLeasingCompany).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'Raiffeisen Leasing' }),
      ),
    )
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith(created))

    // Inline form closes after a successful create.
    expect(screen.queryByLabelText(/^nume/i)).not.toBeInTheDocument()

    // Let the invalidated query's refetch settle before the test exits, so the
    // resulting re-render doesn't leak an act() warning into the next test.
    await waitFor(() => expect(carparkSaleDocsApi.listLeasingCompanies).toHaveBeenCalledTimes(2))
  })

  it('surfaces the error and does not auto-select when create fails', async () => {
    vi.mocked(carparkSaleDocsApi.createLeasingCompany).mockRejectedValue(new Error('CUI deja folosit'))

    const { onSelect } = renderSelect()
    await screen.findByText('BT Leasing IFN')

    fireEvent.click(addButton())
    fireEvent.change(screen.getByLabelText(/^nume/i), { target: { value: 'Test SRL' } })
    fireEvent.click(screen.getByRole('button', { name: /salvează/i }))

    // The mutation's onError surfaces the message in the inline form…
    expect(await screen.findByText('CUI deja folosit')).toBeInTheDocument()
    // …the company is NOT auto-selected, and the form stays open to retry.
    expect(onSelect).not.toHaveBeenCalled()
    expect(screen.getByLabelText(/^nume/i)).toBeInTheDocument()
  })

  it('disables "Salvează" until a name is typed', async () => {
    renderSelect()
    await screen.findByText('BT Leasing IFN')
    fireEvent.click(addButton())
    expect(screen.getByRole('button', { name: /salvează/i })).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/^nume/i), { target: { value: 'X' } })
    expect(screen.getByRole('button', { name: /salvează/i })).not.toBeDisabled()
  })
})
