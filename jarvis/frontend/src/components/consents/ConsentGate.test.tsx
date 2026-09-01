import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { ConsentDocument } from '@/api/consents'

vi.mock('@/components/shared/SignatureCanvas', () => ({
  default: ({ onSave }: { onSave: (s: string) => void }) => <button onClick={() => onSave('data:sig')}>sign</button>,
}))

const { usePendingConsents, useSignConsent, mutateAsync } = vi.hoisted(() => ({
  usePendingConsents: vi.fn(),
  useSignConsent: vi.fn(),
  mutateAsync: vi.fn(),
}))
vi.mock('@/hooks/useConsents', () => ({ usePendingConsents, useSignConsent }))

import ConsentGate from './ConsentGate'

const DOCS: ConsentDocument[] = [
  { id: 1, doc_key: 'privacy', title: 'Confidențialitate', body: 'Body 1', sort_order: 0, version: 1, requires_signature: true },
  { id: 2, doc_key: 'terms', title: 'Termeni și condiții', body: 'Body 2', sort_order: 1, version: 1, requires_signature: true },
]

beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, 'scrollHeight', { configurable: true, value: 1000 })
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, value: 200 })
})

beforeEach(() => {
  mutateAsync.mockReset()
  useSignConsent.mockReturnValue({ mutateAsync, isPending: false })
})

function signCurrentStep() {
  const body = screen.getByTestId('consent-body')
  body.scrollTop = 1000
  fireEvent.scroll(body)
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByText('sign'))
  fireEvent.click(screen.getByRole('button', { name: /semnează și continuă/i }))
}

describe('ConsentGate', () => {
  it('shows a loading state while pending consents load', () => {
    usePendingConsents.mockReturnValue({ data: undefined, isLoading: true, isError: false, refetch: vi.fn() })
    render(<ConsentGate />)
    expect(screen.getByText(/se încarcă acordurile/i)).toBeInTheDocument()
  })

  it('renders nothing when there is nothing pending', () => {
    usePendingConsents.mockReturnValue({ data: { complete: true, pending: [] }, isLoading: false, isError: false, refetch: vi.fn() })
    const { container } = render(<ConsentGate />)
    expect(container).toBeEmptyDOMElement()
  })

  it('exposes a logout escape', () => {
    usePendingConsents.mockReturnValue({ data: { complete: false, pending: DOCS }, isLoading: false, isError: false, refetch: vi.fn() })
    render(<ConsentGate />)
    expect(screen.getByRole('link', { name: /deconectează-te/i })).toHaveAttribute('href', '/logout')
  })

  it('advances to the next pending document after a non-final sign, then shows a finishing state on the final sign', async () => {
    usePendingConsents.mockReturnValue({ data: { complete: false, pending: DOCS }, isLoading: false, isError: false, refetch: vi.fn() })
    render(<ConsentGate />)

    expect(screen.getByText('Document 1 din 2')).toBeInTheDocument()
    expect(screen.getByText('Confidențialitate')).toBeInTheDocument()

    mutateAsync.mockResolvedValueOnce({ complete: false, pending_count: 1 })
    signCurrentStep()

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ documentId: 1, signatureImage: 'data:sig' }))
    await waitFor(() => expect(screen.getByText('Document 2 din 2')).toBeInTheDocument())
    expect(screen.getByText('Termeni și condiții')).toBeInTheDocument()

    mutateAsync.mockResolvedValueOnce({ complete: true, pending_count: 0 })
    signCurrentStep()

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ documentId: 2, signatureImage: 'data:sig' }))
    // Gate keeps blocking (doesn't unmount itself) until the currentUser
    // refetch it triggered elsewhere causes its host to stop rendering it.
    await waitFor(() => expect(screen.getByText(/se finalizează/i)).toBeInTheDocument())
  })
})
