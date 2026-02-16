import { useState, useMemo, useImperativeHandle, forwardRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus, Trash2, Lock, Unlock, MessageSquare, ArrowRightLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { organizationApi } from '@/api/organization'
import { cn } from '@/lib/utils'
import type { Allocation } from '@/types/invoices'

/* ──── Types ──── */

export interface ReinvoiceDest {
  id: string
  company: string
  brand: string
  department: string
  subdepartment: string
  percentage: number
  locked: boolean
}

export interface AllocationRow {
  id: string
  brand: string
  department: string
  subdepartment: string
  percent: number
  value: number
  locked: boolean
  comment: string
  reinvoiceDestinations: ReinvoiceDest[]
}

export function newRow(): AllocationRow {
  return {
    id: crypto.randomUUID(),
    brand: '',
    department: '',
    subdepartment: '',
    percent: 100,
    value: 0,
    locked: false,
    comment: '',
    reinvoiceDestinations: [],
  }
}

function newReinvoiceDest(): ReinvoiceDest {
  return {
    id: crypto.randomUUID(),
    company: '',
    brand: '',
    department: '',
    subdepartment: '',
    percentage: 100,
    locked: false,
  }
}

/* ──── Helpers ──── */

export function allocationsToRows(allocations: Allocation[], effectiveValue?: number): AllocationRow[] {
  return allocations.map((a) => ({
    id: crypto.randomUUID(),
    brand: a.brand || '',
    department: a.department,
    subdepartment: a.subdepartment || '',
    percent: a.allocation_percent,
    // DB stores NET value (after reinvoice). Editor needs GROSS.
    value: effectiveValue != null ? effectiveValue * a.allocation_percent / 100 : a.allocation_value,
    locked: a.locked,
    comment: a.comment || '',
    reinvoiceDestinations: (a.reinvoice_destinations || []).map((rd) => ({
      id: crypto.randomUUID(),
      company: rd.company,
      brand: rd.brand || '',
      department: rd.department,
      subdepartment: rd.subdepartment || '',
      percentage: rd.percentage,
      locked: false,
    })),
  }))
}

export function rowsToApiPayload(company: string, rows: AllocationRow[]) {
  return rows.map((r) => ({
    company,
    brand: r.brand || undefined,
    department: r.department,
    subdepartment: r.subdepartment || undefined,
    allocation_percent: r.percent,
    locked: r.locked,
    comment: r.comment || undefined,
    reinvoice_destinations: r.reinvoiceDestinations
      .filter((rd) => rd.company && rd.department)
      .map((rd) => ({
        company: rd.company,
        brand: rd.brand || undefined,
        department: rd.department,
        subdepartment: rd.subdepartment || undefined,
        percentage: rd.percentage,
      })),
  }))
}

/* ──── Editor Ref ──── */

export interface AllocationEditorRef {
  getCompany: () => string
  getRows: () => AllocationRow[]
  isValid: () => boolean
}

/* ──── AllocationEditor Container ──── */

interface AllocationEditorProps {
  initialCompany?: string
  initialRows?: AllocationRow[]
  effectiveValue: number
  currency: string
  onSave?: (company: string, rows: AllocationRow[]) => void | Promise<void>
  onCancel?: () => void
  isSaving?: boolean
  compact?: boolean
}

export const AllocationEditor = forwardRef<AllocationEditorRef, AllocationEditorProps>(function AllocationEditor(
  { initialCompany, initialRows, effectiveValue, currency, onSave, onCancel, isSaving, compact },
  ref,
) {
  const [company, setCompany] = useState(initialCompany || '')
  const [rows, setRows] = useState<AllocationRow[]>(initialRows?.length ? initialRows : [newRow()])

  const { data: companies = [] } = useQuery({
    queryKey: ['companies'],
    queryFn: () => organizationApi.getCompanies(),
  })

  const { data: brands = [] } = useQuery({
    queryKey: ['brands', company],
    queryFn: () => organizationApi.getBrands(company),
    enabled: !!company,
  })

  const { data: departments = [] } = useQuery({
    queryKey: ['departments', company],
    queryFn: () => organizationApi.getDepartments(company),
    enabled: !!company,
  })

  const totalPercent = useMemo(() => rows.reduce((s, r) => s + r.percent, 0), [rows])

  const updateRow = (id: string, updates: Partial<AllocationRow>) => {
    setRows((prev) =>
      prev.map((r) => {
        if (r.id !== id) return r
        const updated = { ...r, ...updates }
        if ('percent' in updates) {
          updated.value = effectiveValue * (updated.percent / 100)
        }
        if ('value' in updates && effectiveValue > 0) {
          updated.percent = (updated.value / effectiveValue) * 100
        }
        return updated
      }),
    )
  }

  const addRow = () => {
    const unlocked = rows.filter((r) => !r.locked)
    const lockedTotal = rows.filter((r) => r.locked).reduce((s, r) => s + r.percent, 0)
    const remaining = 100 - lockedTotal
    const newCount = unlocked.length + 1
    const perRow = remaining / newCount
    setRows((prev) => {
      const updated = prev.map((r) => {
        if (r.locked) return r
        return { ...r, percent: perRow, value: effectiveValue * (perRow / 100) }
      })
      return [...updated, { ...newRow(), percent: perRow, value: effectiveValue * (perRow / 100) }]
    })
  }

  const removeRow = (id: string) => {
    if (rows.length <= 1) return
    setRows((prev) => {
      const remaining = prev.filter((r) => r.id !== id)
      const lockedTotal = remaining.filter((r) => r.locked).reduce((s, r) => s + r.percent, 0)
      const availablePercent = 100 - lockedTotal
      const unlocked = remaining.filter((r) => !r.locked)
      if (unlocked.length === 0) return remaining
      const perRow = availablePercent / unlocked.length
      return remaining.map((r) => {
        if (r.locked) return r
        return { ...r, percent: perRow, value: effectiveValue * (perRow / 100) }
      })
    })
  }

  useImperativeHandle(ref, () => ({
    getCompany: () => company,
    getRows: () => rows,
    isValid: () => {
      if (!company) return false
      if (rows.some((r) => !r.department)) return false
      if (Math.abs(totalPercent - 100) > 1) return false
      return true
    },
  }))

  return (
    <div className={cn('space-y-3', compact && 'space-y-2')}>
      {/* Company selector */}
      <div className="flex items-center gap-3">
        <Label className="text-xs shrink-0">Company</Label>
        <Select
          value={company}
          onValueChange={(v) => {
            setCompany(v)
            setRows([newRow()])
          }}
        >
          <SelectTrigger className={cn('h-8 text-xs', compact ? 'w-48' : 'flex-1')}>
            <SelectValue placeholder="Select company..." />
          </SelectTrigger>
          <SelectContent>
            {(companies as string[]).map((c) => (
              <SelectItem key={c} value={c}>{c}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button size="sm" variant="outline" onClick={addRow} disabled={!company} className="h-8 text-xs">
          <Plus className="mr-1 h-3 w-3" />
          Row
        </Button>
      </div>

      {/* Rows */}
      {company && (
        <div className="space-y-2">
          {/* Header */}
          <div className="grid grid-cols-12 gap-2 text-[11px] font-medium text-muted-foreground px-1">
            {brands.length > 0 && <div className="col-span-2">Brand</div>}
            <div className={brands.length > 0 ? 'col-span-3' : 'col-span-4'}>Department</div>
            <div className="col-span-2">Subdepartment</div>
            <div className="col-span-1 text-right">%</div>
            <div className="col-span-2 text-right">Value ({currency})</div>
            <div className={brands.length > 0 ? 'col-span-2' : 'col-span-3'}></div>
          </div>

          {rows.map((row) => (
            <AllocationRowComponent
              key={row.id}
              row={row}
              company={company}
              allCompanies={companies as string[]}
              brands={brands}
              departments={departments}
              effectiveValue={effectiveValue}
              currency={currency}
              onUpdate={(updates) => updateRow(row.id, updates)}
              onRemove={() => removeRow(row.id)}
              canRemove={rows.length > 1}
            />
          ))}

          {/* Total + actions */}
          <div className="flex items-center justify-between border-t pt-2 px-1">
            <div className="flex items-center gap-3">
              <span className="text-xs font-medium">Total:</span>
              <span
                className={cn(
                  'text-xs font-semibold',
                  Math.abs(totalPercent - 100) <= 1 ? 'text-green-600' : 'text-destructive',
                )}
              >
                {totalPercent.toFixed(2)}%
              </span>
              <span className="text-xs text-muted-foreground">|</span>
              <span className="text-xs font-medium">
                {new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(
                  rows.reduce((s, r) => s + r.value, 0),
                )}{' '}
                {currency}
              </span>
            </div>
            {onSave && (
              <div className="flex items-center gap-2">
                {onCancel && (
                  <Button variant="ghost" size="sm" onClick={onCancel} className="h-7 text-xs">
                    Cancel
                  </Button>
                )}
                <Button
                  size="sm"
                  onClick={() => onSave(company, rows)}
                  disabled={isSaving || !company || rows.some((r) => !r.department) || Math.abs(totalPercent - 100) > 1}
                  className="h-7 text-xs"
                >
                  {isSaving ? 'Saving...' : 'Save Allocations'}
                </Button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
})

/* ──── Allocation Row Component ──── */

export function AllocationRowComponent({
  row,
  company,
  allCompanies,
  brands,
  departments,
  effectiveValue,
  currency,
  onUpdate,
  onRemove,
  canRemove,
}: {
  row: AllocationRow
  company: string
  allCompanies: string[]
  brands: string[]
  departments: string[]
  effectiveValue: number
  currency: string
  onUpdate: (updates: Partial<AllocationRow>) => void
  onRemove: () => void
  canRemove: boolean
}) {
  const [showComment, setShowComment] = useState(!!row.comment)
  const hasReinvoice = row.reinvoiceDestinations.length > 0

  const { data: subdepartments = [] } = useQuery({
    queryKey: ['subdepartments', company, row.department],
    queryFn: () => organizationApi.getSubdepartments(company, row.department),
    enabled: !!row.department,
  })

  const { data: managerData } = useQuery({
    queryKey: ['manager', company, row.department, row.brand],
    queryFn: () =>
      organizationApi.getManager({
        company,
        department: row.department,
        brand: row.brand || undefined,
      }),
    enabled: !!row.department,
  })

  const toggleReinvoice = (checked: boolean) => {
    if (checked) {
      onUpdate({ reinvoiceDestinations: [newReinvoiceDest()] })
    } else {
      onUpdate({ reinvoiceDestinations: [] })
    }
  }

  const updateDest = (destId: string, updates: Partial<ReinvoiceDest>) => {
    const updated = row.reinvoiceDestinations.map((d) =>
      d.id === destId ? { ...d, ...updates } : d,
    )
    onUpdate({ reinvoiceDestinations: updated })
  }

  const addDest = () => {
    const lockedTotal = row.reinvoiceDestinations.filter((d) => d.locked).reduce((s, d) => s + d.percentage, 0)
    const remaining = 100 - lockedTotal
    const unlocked = row.reinvoiceDestinations.filter((d) => !d.locked)
    const newCount = unlocked.length + 1
    const perDest = remaining / newCount
    const redistributed = row.reinvoiceDestinations.map((d) =>
      d.locked ? d : { ...d, percentage: perDest },
    )
    onUpdate({ reinvoiceDestinations: [...redistributed, { ...newReinvoiceDest(), percentage: perDest }] })
  }

  const removeDest = (destId: string) => {
    const remaining = row.reinvoiceDestinations.filter((d) => d.id !== destId)
    if (remaining.length > 0) {
      const lockedTotal = remaining.filter((d) => d.locked).reduce((s, d) => s + d.percentage, 0)
      const availablePercent = 100 - lockedTotal
      const unlocked = remaining.filter((d) => !d.locked)
      if (unlocked.length > 0) {
        const perDest = availablePercent / unlocked.length
        onUpdate({ reinvoiceDestinations: remaining.map((d) => d.locked ? d : { ...d, percentage: perDest }) })
      } else {
        onUpdate({ reinvoiceDestinations: remaining })
      }
    } else {
      onUpdate({ reinvoiceDestinations: [] })
    }
  }

  const hasBrands = brands.length > 0

  // Net values: gross minus reinvoiced portion
  const reinvoiceTotal = row.reinvoiceDestinations.reduce((s, d) => s + d.percentage, 0)
  const netFactor = hasReinvoice ? Math.max(0, 1 - reinvoiceTotal / 100) : 1
  const netValue = row.value * netFactor
  const netPercent = row.percent * netFactor

  return (
    <div className="rounded-lg border p-2 space-y-2">
      <div className="grid grid-cols-12 gap-2 items-center">
        {hasBrands && (
          <div className="col-span-2 min-w-0">
            <Select
              value={row.brand || '__none__'}
              onValueChange={(v) => onUpdate({ brand: v === '__none__' ? '' : v })}
            >
              <SelectTrigger className="h-8 w-full text-xs">
                <SelectValue placeholder="Brand" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">N/A</SelectItem>
                {brands.map((b) => (
                  <SelectItem key={b} value={b}>{b}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        <div className={cn(hasBrands ? 'col-span-3' : 'col-span-4', 'min-w-0')}>
          <Select
            value={row.department || '__none__'}
            onValueChange={(v) =>
              onUpdate({
                department: v === '__none__' ? '' : v,
                subdepartment: '',
              })
            }
          >
            <SelectTrigger className="h-8 w-full text-xs">
              <SelectValue placeholder="Select..." />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">Select...</SelectItem>
              {departments.map((d) => (
                <SelectItem key={d} value={d}>{d}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="col-span-2 min-w-0">
          <Select
            value={row.subdepartment || '__none__'}
            onValueChange={(v) => onUpdate({ subdepartment: v === '__none__' ? '' : v })}
            disabled={subdepartments.length === 0}
          >
            <SelectTrigger className="h-8 w-full text-xs">
              <SelectValue placeholder="N/A" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">N/A</SelectItem>
              {subdepartments.map((sd) => (
                <SelectItem key={sd} value={sd}>{sd}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="col-span-1 min-w-0">
          <Input
            type="number"
            min={0}
            max={100}
            step={0.01}
            className={cn('h-8 text-xs text-right', hasReinvoice && 'opacity-60')}
            value={hasReinvoice ? netPercent.toFixed(2) : row.percent.toFixed(2)}
            disabled={hasReinvoice}
            onChange={(e) => {
              const p = parseFloat(e.target.value) || 0
              onUpdate({ percent: p, value: effectiveValue * (p / 100) })
            }}
          />
        </div>
        <div className="col-span-2">
          <Input
            type="number"
            step={0.01}
            className={cn('h-8 text-xs text-right', hasReinvoice && 'opacity-60')}
            value={hasReinvoice ? netValue.toFixed(2) : row.value.toFixed(2)}
            disabled={hasReinvoice}
            onChange={(e) => {
              const v = parseFloat(e.target.value) || 0
              onUpdate({
                value: v,
                percent: effectiveValue > 0 ? (v / effectiveValue) * 100 : 0,
              })
            }}
          />
        </div>
        <div className={cn('flex items-center gap-1 justify-end', hasBrands ? 'col-span-2' : 'col-span-3')}>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setShowComment(!showComment)} title="Comment">
            <MessageSquare className={cn('h-3.5 w-3.5', row.comment && 'text-primary')} />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onUpdate({ locked: !row.locked })} title={row.locked ? 'Unlock' : 'Lock'}>
            {row.locked ? <Lock className="h-3.5 w-3.5 text-amber-500" /> : <Unlock className="h-3.5 w-3.5" />}
          </Button>
          {canRemove && (
            <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={onRemove}>
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      </div>

      {/* Manager + Reinvoice toggle */}
      <div className="flex items-center gap-4 px-1">
        {managerData?.manager && (
          <span className="text-xs text-muted-foreground">Manager: {managerData.manager}</span>
        )}
        <label className="flex items-center gap-1.5 ml-auto cursor-pointer">
          <Checkbox
            checked={hasReinvoice}
            onCheckedChange={(checked) => toggleReinvoice(!!checked)}
            className="h-3.5 w-3.5"
          />
          <span className="text-xs text-muted-foreground flex items-center gap-1">
            <ArrowRightLeft className="h-3 w-3" />
            Reinvoice
          </span>
        </label>
      </div>

      {/* Reinvoice destinations */}
      {hasReinvoice && (
        <div className="ml-4 border-l-2 border-primary/20 pl-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium text-muted-foreground">Reinvoice to:</span>
            <Button variant="ghost" size="sm" className="h-6 text-[11px] px-2" onClick={addDest}>
              <Plus className="mr-0.5 h-3 w-3" />
              Add
            </Button>
          </div>
          {row.reinvoiceDestinations.map((dest) => (
            <ReinvoiceDestRow
              key={dest.id}
              dest={dest}
              allCompanies={allCompanies}
              sourceCompany={company}
              rowValue={row.value}
              currency={currency}
              onUpdate={(updates) => updateDest(dest.id, updates)}
              onRemove={() => removeDest(dest.id)}
              canRemove={row.reinvoiceDestinations.length > 1}
            />
          ))}
        </div>
      )}

      {showComment && (
        <div className="px-1">
          <Input
            className="h-7 text-xs"
            placeholder="Row comment..."
            value={row.comment}
            onChange={(e) => onUpdate({ comment: e.target.value })}
          />
        </div>
      )}
    </div>
  )
}

/* ──── Reinvoice Destination Row ──── */

function ReinvoiceDestRow({
  dest,
  allCompanies,
  sourceCompany,
  rowValue,
  currency,
  onUpdate,
  onRemove,
  canRemove,
}: {
  dest: ReinvoiceDest
  allCompanies: string[]
  sourceCompany: string
  rowValue: number
  currency: string
  onUpdate: (updates: Partial<ReinvoiceDest>) => void
  onRemove: () => void
  canRemove: boolean
}) {
  // Filter out source company from targets
  const targetCompanies = allCompanies.filter((c) => c !== sourceCompany)

  const { data: targetDepts = [] } = useQuery({
    queryKey: ['departments', dest.company],
    queryFn: () => organizationApi.getDepartments(dest.company),
    enabled: !!dest.company,
  })

  const { data: targetSubdepts = [] } = useQuery({
    queryKey: ['subdepartments', dest.company, dest.department],
    queryFn: () => organizationApi.getSubdepartments(dest.company, dest.department),
    enabled: !!dest.department,
  })

  const { data: targetBrands = [] } = useQuery({
    queryKey: ['brands', dest.company],
    queryFn: () => organizationApi.getBrands(dest.company),
    enabled: !!dest.company,
  })

  return (
    <div className="flex items-center gap-2">
      <Select
        value={dest.company || '__none__'}
        onValueChange={(v) => onUpdate({ company: v === '__none__' ? '' : v, department: '', subdepartment: '', brand: '' })}
      >
        <SelectTrigger className="h-7 text-xs w-32">
          <SelectValue placeholder="Company" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__none__">Company...</SelectItem>
          {targetCompanies.map((c) => (
            <SelectItem key={c} value={c}>{c}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      {targetBrands.length > 0 && (
        <Select
          value={dest.brand || '__none__'}
          onValueChange={(v) => onUpdate({ brand: v === '__none__' ? '' : v })}
        >
          <SelectTrigger className="h-7 text-xs w-28">
            <SelectValue placeholder="Brand" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__">N/A</SelectItem>
            {targetBrands.map((b) => (
              <SelectItem key={b} value={b}>{b}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
      <Select
        value={dest.department || '__none__'}
        onValueChange={(v) => onUpdate({ department: v === '__none__' ? '' : v, subdepartment: '' })}
        disabled={!dest.company}
      >
        <SelectTrigger className="h-7 text-xs flex-1 min-w-[100px]">
          <SelectValue placeholder="Department" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__none__">Department...</SelectItem>
          {targetDepts.map((d) => (
            <SelectItem key={d} value={d}>{d}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      {targetSubdepts.length > 0 && (
        <Select
          value={dest.subdepartment || '__none__'}
          onValueChange={(v) => onUpdate({ subdepartment: v === '__none__' ? '' : v })}
        >
          <SelectTrigger className="h-7 text-xs w-28">
            <SelectValue placeholder="Subdept" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__">N/A</SelectItem>
            {targetSubdepts.map((sd) => (
              <SelectItem key={sd} value={sd}>{sd}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
      <Input
        type="number"
        min={0}
        max={100}
        step={0.01}
        className="h-7 text-xs text-right w-16"
        value={dest.percentage.toFixed(2)}
        onChange={(e) => onUpdate({ percentage: parseFloat(e.target.value) || 0 })}
      />
      <span className="text-[11px] text-muted-foreground shrink-0">%</span>
      <Input
        type="number"
        step={0.01}
        className="h-7 text-xs text-right w-24"
        value={(rowValue * (dest.percentage / 100)).toFixed(2)}
        onChange={(e) => {
          const v = parseFloat(e.target.value) || 0
          onUpdate({ percentage: rowValue > 0 ? (v / rowValue) * 100 : 0 })
        }}
      />
      <span className="text-[11px] text-muted-foreground shrink-0">{currency}</span>
      <Button
        variant="ghost"
        size="icon"
        className="h-6 w-6 shrink-0"
        onClick={() => onUpdate({ locked: !dest.locked })}
        title={dest.locked ? 'Unlock' : 'Lock'}
      >
        {dest.locked ? <Lock className="h-3 w-3 text-amber-500" /> : <Unlock className="h-3 w-3" />}
      </Button>
      {canRemove && (
        <Button variant="ghost" size="icon" className="h-6 w-6 text-destructive shrink-0" onClick={onRemove}>
          <Trash2 className="h-3 w-3" />
        </Button>
      )}
    </div>
  )
}
