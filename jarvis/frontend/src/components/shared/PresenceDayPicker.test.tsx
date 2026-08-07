import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { PresenceDayPicker } from './PresenceDayPicker'

// Event range 2099-01-30 .. 2099-02-03 (inclusive) = 5 days across two months.
const START = '2099-01-30'
const END = '2099-02-03'

describe('PresenceDayPicker', () => {
  it('renders one toggle per day in the inclusive event range', () => {
    render(<PresenceDayPicker startDate={START} endDate={END} value={[]} onChange={() => {}} />)
    expect(screen.getAllByRole('button')).toHaveLength(5)
  })

  it('groups the days by calendar month', () => {
    render(<PresenceDayPicker startDate={START} endDate={END} value={[]} onChange={() => {}} />)
    expect(screen.getAllByTestId('presence-month')).toHaveLength(2)
  })

  it('adds a day (kept sorted) when an unselected day is clicked', () => {
    const onChange = vi.fn()
    render(<PresenceDayPicker startDate={START} endDate={END} value={['2099-01-31']} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: /2099-02-02/ }))
    expect(onChange).toHaveBeenCalledWith(['2099-01-31', '2099-02-02'])
  })

  it('removes a day when an already-selected day is clicked', () => {
    const onChange = vi.fn()
    render(<PresenceDayPicker startDate={START} endDate={END} value={['2099-01-31', '2099-02-02']} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: /2099-01-31/ }))
    expect(onChange).toHaveBeenCalledWith(['2099-02-02'])
  })

  it('marks selected days with aria-pressed', () => {
    render(<PresenceDayPicker startDate={START} endDate={END} value={['2099-01-31']} onChange={() => {}} />)
    expect(screen.getByRole('button', { name: /2099-01-31/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /2099-02-01/ })).toHaveAttribute('aria-pressed', 'false')
  })

  it('day toggles are type=button so they never submit a surrounding form', () => {
    render(<PresenceDayPicker startDate={START} endDate={END} value={[]} onChange={() => {}} />)
    for (const b of screen.getAllByRole('button')) expect(b).toHaveAttribute('type', 'button')
  })

  it('readOnly mode renders non-interactive days and marks attended ones', () => {
    render(<PresenceDayPicker startDate={START} endDate={END} value={['2099-02-02']} onChange={() => {}} readOnly />)
    // no buttons in read-only mode
    expect(screen.queryAllByRole('button')).toHaveLength(0)
    // every event day is still shown, attended flagged via data-selected
    const days = screen.getAllByTestId('presence-day')
    expect(days).toHaveLength(5)
    const attended = screen.getByLabelText('2099-02-02')
    expect(attended).toHaveAttribute('data-selected', 'true')
    expect(screen.getByLabelText('2099-01-30')).toHaveAttribute('data-selected', 'false')
  })
})
