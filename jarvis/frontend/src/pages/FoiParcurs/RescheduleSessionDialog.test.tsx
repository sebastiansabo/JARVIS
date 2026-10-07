import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import RescheduleSessionDialog from './RescheduleSessionDialog'
import type { FoiContract } from '@/types/foiParcurs'

const session = {
  id: 5, client_name: 'Ion Pop',
  departure_datetime: '2999-01-01T10:00', return_datetime: '2999-01-01T11:00',
} as FoiContract

function setup(overrides: Partial<React.ComponentProps<typeof RescheduleSessionDialog>> = {}) {
  const onSubmit = vi.fn()
  const onClose = vi.fn()
  render(<RescheduleSessionDialog session={session} onClose={onClose} onSubmit={onSubmit} submitting={false} {...overrides} />)
  return { onSubmit, onClose }
}

describe('RescheduleSessionDialog', () => {
  it('defaults the departure field to the current departure', () => {
    setup()
    expect(screen.getByLabelText('Nouă plecare')).toHaveValue('2999-01-01T10:00')
  })

  it('submits the chosen departure + return', () => {
    const { onSubmit } = setup()
    fireEvent.click(screen.getByRole('button', { name: /replanifică/i }))
    expect(onSubmit).toHaveBeenCalledWith({ departure_datetime: '2999-01-01T10:00', return_datetime: '2999-01-01T11:00' })
  })

  it('disables save when departure is cleared', () => {
    const { onSubmit } = setup()
    fireEvent.change(screen.getByLabelText('Nouă plecare'), { target: { value: '' } })
    const save = screen.getByRole('button', { name: /replanifică/i })
    expect(save).toBeDisabled()
    fireEvent.click(save)
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('disables save when return is before departure', () => {
    setup()
    fireEvent.change(screen.getByLabelText('Nou retur'), { target: { value: '2999-01-01T09:00' } })
    expect(screen.getByRole('button', { name: /replanifică/i })).toBeDisabled()
  })

  it('rejects a departure in the past', () => {
    setup()
    fireEvent.change(screen.getByLabelText('Nouă plecare'), { target: { value: '2000-01-01T10:00' } })
    expect(screen.getByRole('button', { name: /replanifică/i })).toBeDisabled()
  })

  it('omits return_datetime when the return field is empty', () => {
    const { onSubmit } = setup()
    fireEvent.change(screen.getByLabelText('Nou retur'), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: /replanifică/i }))
    expect(onSubmit).toHaveBeenCalledWith({ departure_datetime: '2999-01-01T10:00' })
  })
})
