import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import SessionTypeChooser from './SessionTypeChooser'

describe('SessionTypeChooser', () => {
  it('renders nothing when closed', () => {
    render(<SessionTypeChooser open={false} onOpenChange={vi.fn()} onPick={vi.fn()} />)
    expect(screen.queryByText(/sesiune cu client/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/sesiune internă/i)).not.toBeInTheDocument()
  })

  it('shows both options when open', async () => {
    render(<SessionTypeChooser open onOpenChange={vi.fn()} onPick={vi.fn()} />)
    expect(await screen.findByText(/sesiune cu client/i)).toBeInTheDocument()
    expect(screen.getByText(/sesiune internă/i)).toBeInTheDocument()
  })

  it('calls onPick("client") when the Client option is chosen', async () => {
    const onPick = vi.fn()
    render(<SessionTypeChooser open onOpenChange={vi.fn()} onPick={onPick} />)
    fireEvent.click(await screen.findByRole('button', { name: /sesiune cu client/i }))
    expect(onPick).toHaveBeenCalledWith('client')
  })

  it('calls onPick("internal") when the Intern option is chosen', async () => {
    const onPick = vi.fn()
    render(<SessionTypeChooser open onOpenChange={vi.fn()} onPick={onPick} />)
    fireEvent.click(await screen.findByRole('button', { name: /sesiune internă/i }))
    expect(onPick).toHaveBeenCalledWith('internal')
  })

  it('hides the Client card when showClient={false} (courtesy panel)', async () => {
    render(<SessionTypeChooser open showClient={false} showRental onOpenChange={vi.fn()} onPick={vi.fn()} />)
    // Rent-a-car + Internal remain; the client test-drive card is gone.
    expect(await screen.findByRole('button', { name: /rent-a-car/i })).toBeInTheDocument()
    expect(screen.getByText(/sesiune internă/i)).toBeInTheDocument()
    expect(screen.queryByText(/sesiune cu client/i)).not.toBeInTheDocument()
  })
})
