import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import DocTypeToggle from './DocTypeToggle'

describe('DocTypeToggle', () => {
  it('renders both Romanian labels and fires onChange', () => {
    const onChange = vi.fn()
    render(<DocTypeToggle value="sales" onChange={onChange} />)
    fireEvent.click(screen.getByLabelText('Mașini de curtoazie'))
    expect(onChange).toHaveBeenCalledWith('service')
  })
})
