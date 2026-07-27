import { describe, it, expect } from 'vitest'
import { render, fireEvent, screen } from '@testing-library/react'
import { FormRenderer } from './FormRenderer'
import type { FormField } from '@/types/forms'

// The Bilet de Invoire duration field, rendered through the real FieldComponent
// path (read-only guard + time-wise formatting), not just the pure helper.
const SCHEMA: FormField[] = [
  { id: 'f_bi_start_time', type: 'time', label: 'Ora de început', required: true, order: 1 },
  { id: 'f_bi_end_time', type: 'time', label: 'Ora de sfârșit', required: true, order: 2 },
  {
    id: 'f_bi_hours', type: 'text', label: 'Durată', required: true, order: 3,
    config: {
      duration: { start: 'f_bi_start_time', end: 'f_bi_end_time' },
      hint: 'Se calculează automat din interval.',
    },
  },
]

function renderForm(defaultValues?: Record<string, unknown>) {
  const { container } = render(
    <FormRenderer schema={SCHEMA} onSubmit={() => {}} defaultValues={defaultValues} />,
  )
  const times = Array.from(container.querySelectorAll('input[type="time"]')) as HTMLInputElement[]
  const duration = container.querySelector('input[type="text"]') as HTMLInputElement
  return { start: times[0], end: times[1], duration }
}

describe('FormRenderer duration field', () => {
  it('renders the Durată field read-only', () => {
    const { duration } = renderForm()
    expect(duration).toBeTruthy()
    expect(duration.readOnly).toBe(true)
  })

  it('shows 23:00 → 23:50 as "50 min", not a decimal', () => {
    const { start, end, duration } = renderForm()
    fireEvent.change(start, { target: { value: '23:00' } })
    fireEvent.change(end, { target: { value: '23:50' } })
    expect(duration.value).toBe('50 min')
    expect(duration.value).not.toBe('0.83')
  })

  it('formats an hours-and-minutes interval', () => {
    const { start, end, duration } = renderForm()
    fireEvent.change(start, { target: { value: '09:00' } })
    fireEvent.change(end, { target: { value: '11:30' } })
    expect(duration.value).toBe('2 h 30 min')
  })

  it('clears the duration when the interval is invalid', () => {
    const { start, end, duration } = renderForm()
    fireEvent.change(start, { target: { value: '11:00' } })
    fireEvent.change(end, { target: { value: '09:00' } })
    expect(duration.value).toBe('')
  })

  it('opens with a default 1-hour interval', () => {
    const { start, end, duration } = renderForm({ f_bi_start_time: '09:00' })
    expect(start.value).toBe('09:00')
    expect(end.value).toBe('10:00')
    expect(duration.value).toBe('1 h')
  })

  it('shows an error when the start is later than the end', () => {
    const { start, end, duration } = renderForm()
    fireEvent.change(start, { target: { value: '19:00' } })
    fireEvent.change(end, { target: { value: '12:20' } })
    expect(screen.getByText('Ora de sfârșit trebuie să fie după ora de început.')).toBeInTheDocument()
    expect(duration.value).toBe('')
  })

  it('marks both time fields invalid (red border) for a bad interval', () => {
    const { start, end } = renderForm()
    fireEvent.change(start, { target: { value: '13:58' } })
    fireEvent.change(end, { target: { value: '12:30' } })
    expect(start.getAttribute('aria-invalid')).toBe('true')
    expect(end.getAttribute('aria-invalid')).toBe('true')
  })

  it('drops the red highlight once the interval is valid', () => {
    const { start, end } = renderForm()
    fireEvent.change(start, { target: { value: '13:58' } })
    fireEvent.change(end, { target: { value: '12:30' } })
    expect(start.getAttribute('aria-invalid')).toBe('true')
    fireEvent.change(end, { target: { value: '15:00' } })
    expect(start.getAttribute('aria-invalid')).toBeNull()
    expect(end.getAttribute('aria-invalid')).toBeNull()
  })

  it('drops the error once the interval becomes valid', () => {
    const { start, end } = renderForm()
    fireEvent.change(start, { target: { value: '19:00' } })
    fireEvent.change(end, { target: { value: '12:20' } })
    expect(screen.queryByText('Ora de sfârșit trebuie să fie după ora de început.')).toBeInTheDocument()
    fireEvent.change(end, { target: { value: '20:30' } })
    expect(screen.queryByText('Ora de sfârșit trebuie să fie după ora de început.')).not.toBeInTheDocument()
  })
})
