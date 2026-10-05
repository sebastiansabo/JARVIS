import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ProjectTable } from './index'
import type { MktProject } from '@/types/marketing'

function makeProject(over: Partial<MktProject> = {}): MktProject {
  return {
    id: 1,
    name: 'Spring Campaign',
    slug: 'spring',
    description: null,
    company_id: 1,
    company_ids: [1],
    company_name: 'Autoworld',
    brand_id: null,
    brand_ids: [],
    brand_name: 'Volvo',
    department_structure_id: null,
    department_ids: [],
    project_type: 'always_on',
    channel_mix: [],
    status: 'active',
    start_date: '2026-09-01',
    end_date: '2026-12-31',
    total_budget: 1000,
    currency: 'RON',
    owner_id: 2,
    owner_name: 'Raluca',
    owner_email: null,
    created_by: 1,
    created_by_name: null,
    objective: null,
    target_audience: null,
    brief: {},
    approval_mode: 'any',
    external_ref: null,
    metadata: {},
    created_at: '2026-09-01',
    updated_at: null,
    deleted_at: null,
    total_spent: 500,
    ...over,
  } as MktProject
}

const noop = () => {}

function headerTexts(): string[] {
  return screen
    .getAllByRole('columnheader')
    .map((h) => h.textContent?.trim() ?? '')
    .filter(Boolean)
}

describe('ProjectTable column visibility', () => {
  it('renders only the requested visible columns', () => {
    render(
      <ProjectTable
        projects={[makeProject()]}
        onSelect={noop}
        visibleColumns={['name', 'status']}
      />,
    )
    const headers = headerTexts()
    expect(headers).toContain('Project')
    expect(headers).toContain('Status')
    expect(headers).not.toContain('Company')
    expect(headers).not.toContain('Owner')
    expect(headers).not.toContain('Budget')
  })

  it('respects the order of visibleColumns', () => {
    render(
      <ProjectTable
        projects={[makeProject()]}
        onSelect={noop}
        visibleColumns={['status', 'name']}
      />,
    )
    const headers = headerTexts()
    expect(headers.indexOf('Status')).toBeLessThan(headers.indexOf('Project'))
  })

  it('can show optional columns that are not in the default set (Brand, End)', () => {
    render(
      <ProjectTable
        projects={[makeProject()]}
        onSelect={noop}
        visibleColumns={['name', 'brand_name', 'end_date']}
      />,
    )
    const headers = headerTexts()
    expect(headers).toContain('Brand')
    expect(headers).toContain('End')
    expect(screen.getByText('Volvo')).toBeInTheDocument()
  })
})

describe('ProjectTable sorting', () => {
  it('clicking the Start header calls onSort with its sort key', () => {
    const onSort = vi.fn()
    render(
      <ProjectTable
        projects={[makeProject()]}
        onSelect={noop}
        visibleColumns={['name', 'start_date']}
        sort="start_date"
        order="asc"
        onSort={onSort}
      />,
    )
    fireEvent.click(screen.getByRole('columnheader', { name: /Start/ }))
    expect(onSort).toHaveBeenCalledWith('start_date')
  })

  it('does not make non-sortable columns clickable', () => {
    const onSort = vi.fn()
    render(
      <ProjectTable
        projects={[makeProject()]}
        onSelect={noop}
        visibleColumns={['company_name', 'owner_name']}
        onSort={onSort}
      />,
    )
    fireEvent.click(screen.getByRole('columnheader', { name: /Company/ }))
    fireEvent.click(screen.getByRole('columnheader', { name: /Owner/ }))
    expect(onSort).not.toHaveBeenCalled()
  })

  it('makes the chosen sortable columns clickable (name, budget, spent, end)', () => {
    const onSort = vi.fn()
    render(
      <ProjectTable
        projects={[makeProject()]}
        onSelect={noop}
        visibleColumns={['name', 'total_budget', 'total_spent', 'end_date']}
        onSort={onSort}
      />,
    )
    for (const [name, key] of [
      [/Project/, 'name'],
      [/Budget/, 'total_budget'],
      [/Spent/, 'total_spent'],
      [/End/, 'end_date'],
    ] as const) {
      onSort.mockClear()
      fireEvent.click(screen.getByRole('columnheader', { name }))
      expect(onSort).toHaveBeenCalledWith(key)
    }
  })
})
