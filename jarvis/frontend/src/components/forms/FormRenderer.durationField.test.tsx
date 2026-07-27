import { describe, it, expect } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
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

function renderForm() {
  const { container } = render(<FormRenderer schema={SCHEMA} onSubmit={() => {}} />)
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
})
