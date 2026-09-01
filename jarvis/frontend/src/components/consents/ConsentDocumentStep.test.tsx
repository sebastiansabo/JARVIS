import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { ConsentDocument } from '@/api/consents'

// SignatureCanvas is a canvas widget (signature_pad) — stub it to a button
// that emits a signature, same pattern as TestDriveReturn.test.tsx.
vi.mock('@/components/shared/SignatureCanvas', () => ({
  default: ({ onSave }: { onSave: (s: string) => void }) => <button onClick={() => onSave('data:sig')}>sign</button>,
}))

import { ConsentDocumentStep } from './ConsentDocumentStep'

const DOC: ConsentDocument = {
  id: 1,
  doc_key: 'privacy',
  title: 'Politica de confidențialitate',
  body: 'Body text',
  sort_order: 0,
  version: 1,
  requires_signature: true,
}

// jsdom has no layout engine — scrollHeight/clientHeight are always 0.
// Fake a body tall enough that it starts "not scrolled to the end".
beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, 'scrollHeight', { configurable: true, value: 1000 })
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, value: 200 })
})

function scrollToEnd() {
  const body = screen.getByTestId('consent-body')
  body.scrollTop = 1000
  fireEvent.scroll(body)
}

describe('ConsentDocumentStep', () => {
  it('shows the progress label', () => {
    render(<ConsentDocumentStep doc={DOC} index={1} total={3} onSign={vi.fn()} submitting={false} />)
    expect(screen.getByText('Document 2 din 3')).toBeInTheDocument()
  })

  it('keeps the agree checkbox disabled until the body is scrolled to the end', () => {
    render(<ConsentDocumentStep doc={DOC} index={0} total={1} onSign={vi.fn()} submitting={false} />)
    expect(screen.getByRole('checkbox')).toBeDisabled()

    scrollToEnd()
    expect(screen.getByRole('checkbox')).toBeEnabled()
  })

  it('keeps submit disabled until agreed AND signed, then calls onSign with the signature', () => {
    const onSign = vi.fn()
    render(<ConsentDocumentStep doc={DOC} index={0} total={1} onSign={onSign} submitting={false} />)
    const submit = screen.getByRole('button', { name: /semnează și continuă/i })
    expect(submit).toBeDisabled()

    scrollToEnd()
    fireEvent.click(screen.getByRole('checkbox'))
    expect(submit).toBeDisabled() // agreed but not yet signed

    fireEvent.click(screen.getByText('sign'))
    expect(submit).toBeEnabled()

    fireEvent.click(submit)
    expect(onSign).toHaveBeenCalledWith('data:sig')
  })

  it('disables submit while submitting', () => {
    render(<ConsentDocumentStep doc={DOC} index={0} total={1} onSign={vi.fn()} submitting />)
    scrollToEnd()
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByText('sign'))
    expect(screen.getByRole('button', { name: /se salvează/i })).toBeDisabled()
  })
})
