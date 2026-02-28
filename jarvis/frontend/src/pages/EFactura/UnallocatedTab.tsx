import { useState, useMemo } from 'react'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { MobileCardList, type MobileCardField } from '@/components/shared/MobileCardList'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Send,
  EyeOff,
  RotateCcw,
  CheckCircle,
  FileStack,
  Pencil,
  Eye,
  FileText,
  Trash2,
  Columns3,
  GripVertical,
  ChevronUp,
  ChevronDown,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { EmptyState } from '@/components/shared/EmptyState'
import { QueryError } from '@/components/QueryError'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { SearchInput } from '@/components/shared/SearchInput'
import { CurrencyDisplay } from '@/components/shared/CurrencyDisplay'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { DatePresetSelect } from '@/components/shared/DatePresetSelect'
import { cn, usePersistedState } from '@/lib/utils'
import { efacturaApi } from '@/api/efactura'
import { organizationApi } from '@/api/organization'
import { TagBadgeList } from '@/components/shared/TagBadge'
import { TagPicker, TagPickerButton } from '@/components/shared/TagPicker'
import { TagFilter } from '@/components/shared/TagFilter'
import { tagsApi } from '@/api/tags'
import { ApprovalWidget } from '@/components/shared/ApprovalWidget'
import type { EFacturaInvoice, EFacturaInvoiceFilters } from '@/types/efactura'

type InvoiceRow = EFacturaInvoice & { _hidden?: boolean }

// ── Column definitions ──────────────────────────────────────
interface ColumnDef {
  key: string
  label: string
  align?: 'left' | 'right'
  render: (inv: InvoiceRow) => React.ReactNode
}

const fmtDate = (d: string | null) => d ? new Date(d).toLocaleDateString('ro-RO') : '—'

const columnDefs: ColumnDef[] = [
  {
    key: 'supplier',
    label: 'Supplier',
    render: (inv) => (
      <>
        <div className="font-medium">
          {inv.partner_name}
          {inv._hidden && (
            <span className="ml-1.5 rounded bg-muted px-1.5 py-0.5 text-[10px] font-normal text-muted-foreground">
              hidden
            </span>
          )}
        </div>
        {inv.partner_cif && <div className="text-xs text-muted-foreground">{inv.partner_cif}</div>}
      </>
    ),
  },
  {
    key: 'invoice_number',
    label: 'Invoice #',
    render: (inv) => (
      <span className="font-mono text-xs">
        {inv.invoice_series ? `${inv.invoice_series}-` : ''}
        {inv.invoice_number}
      </span>
    ),
  },
  {
    key: 'date',
    label: 'Date',
    render: (inv) => <span className="text-muted-foreground">{fmtDate(inv.issue_date)}</span>,
  },
  {
    key: 'due_date',
    label: 'Due Date',
    render: (inv) => <span className="text-muted-foreground">{fmtDate(inv.due_date ?? null)}</span>,
  },
  {
    key: 'direction',
    label: 'Direction',
    render: (inv) => <StatusBadge status={inv.direction} />,
  },
  {
    key: 'amount',
    label: 'Amount',
    align: 'right',
    render: (inv) => <CurrencyDisplay value={inv.total_amount} currency={inv.currency} />,
  },
  {
    key: 'vat',
    label: 'VAT',
    align: 'right',
    render: (inv) => <CurrencyDisplay value={inv.total_vat} currency={inv.currency} />,
  },
  {
    key: 'without_vat',
    label: 'Without VAT',
    align: 'right',
    render: (inv) => <CurrencyDisplay value={inv.total_without_vat} currency={inv.currency} />,
  },
  {
    key: 'company',
    label: 'Company',
    render: (inv) => <span className="text-xs text-muted-foreground">{inv.company_name || inv.cif_owner}</span>,
  },
  {
    key: 'type',
    label: 'Type',
    render: (inv) => <>{inv.type_override || inv.mapped_type_names?.join(', ') || '—'}</>,
  },
  {
    key: 'department',
    label: 'Department',
    render: (inv) => <>{inv.department_override || inv.mapped_department || '—'}</>,
  },
  {
    key: 'subdepartment',
    label: 'Subdepartment',
    render: (inv) => <>{inv.subdepartment_override || inv.mapped_subdepartment || '—'}</>,
  },
  {
    key: 'mapped_supplier',
    label: 'Mapped Supplier',
    render: (inv) => <>{inv.mapped_supplier_name || '—'}</>,
  },
  {
    key: 'mapped_brand',
    label: 'Brand',
    render: (inv) => <>{inv.mapped_brand || '—'}</>,
  },
  {
    key: 'kod_konto',
    label: 'Kod Konto',
    render: (inv) => <span className="font-mono text-xs">{inv.mapped_kod_konto || '—'}</span>,
  },
]

const columnDefMap = new Map(columnDefs.map((c) => [c.key, c]))

const defaultColumns = [
  'supplier', 'invoice_number', 'date', 'direction', 'amount', 'company', 'type',
]

const STORAGE_KEY = 'efactura-unallocated-columns'

function loadColumns(): string[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      const parsed = JSON.parse(stored) as string[]
      const valid = parsed.filter((k) => columnDefMap.has(k))
      if (valid.length > 0) return valid
    }
  } catch { /* ignore */ }
  return defaultColumns
}

function saveColumns(cols: string[]) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(cols)) } catch { /* ignore */ }
}

// ── Column Toggle Popover ───────────────────────────────────
function ColumnToggle({
  visibleColumns,
  onChange,
}: {
  visibleColumns: string[]
  onChange: (cols: string[]) => void
}) {
  const hiddenColumns = columnDefs.filter((c) => !visibleColumns.includes(c.key))

  const moveUp = (idx: number) => {
    if (idx <= 0) return
    const next = [...visibleColumns]
    ;[next[idx - 1], next[idx]] = [next[idx], next[idx - 1]]
    onChange(next)
  }

  const moveDown = (idx: number) => {
    if (idx >= visibleColumns.length - 1) return
    const next = [...visibleColumns]
    ;[next[idx], next[idx + 1]] = [next[idx + 1], next[idx]]
    onChange(next)
  }

  const toggle = (key: string) => {
    if (visibleColumns.includes(key)) {
      onChange(visibleColumns.filter((c) => c !== key))
    } else {
      onChange([...visibleColumns, key])
    }
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="icon" className="h-9 w-9 shrink-0" title="Configure columns">
          <Columns3 className="h-4 w-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-56 p-3">
        <p className="mb-2 text-xs font-medium text-muted-foreground">Columns &amp; Order</p>

        <div className="space-y-0.5">
          {visibleColumns.map((key, idx) => {
            const col = columnDefMap.get(key)
            if (!col) return null
            return (
              <div key={key} className="flex items-center gap-1 rounded px-1 py-0.5 hover:bg-accent/50">
                <GripVertical className="h-3 w-3 text-muted-foreground/50 shrink-0" />
                <span className="flex-1 text-sm">{col.label}</span>
                <button
                  onClick={() => moveUp(idx)}
                  disabled={idx === 0}
                  className="rounded p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-25"
                >
                  <ChevronUp className="h-3 w-3" />
                </button>
                <button
                  onClick={() => moveDown(idx)}
                  disabled={idx === visibleColumns.length - 1}
                  className="rounded p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-25"
                >
                  <ChevronDown className="h-3 w-3" />
                </button>
                <button onClick={() => toggle(key)} className="rounded p-0.5 text-muted-foreground hover:text-foreground">
                  <EyeOff className="h-3 w-3" />
                </button>
              </div>
            )
          })}
        </div>

        {hiddenColumns.length > 0 && (
          <>
            <div className="my-2 border-t" />
            <p className="mb-1 text-xs font-medium text-muted-foreground">Hidden</p>
            <div className="space-y-0.5">
              {hiddenColumns.map((col) => (
                <div key={col.key} className="flex items-center gap-1 rounded px-1 py-0.5 hover:bg-accent/50">
                  <span className="flex-1 text-sm text-muted-foreground">{col.label}</span>
                  <button onClick={() => toggle(col.key)} className="rounded p-0.5 text-muted-foreground hover:text-foreground">
                    <Eye className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          </>
        )}

        {visibleColumns.length !== defaultColumns.length ||
          visibleColumns.some((k, i) => k !== defaultColumns[i]) ? (
          <>
            <div className="my-2 border-t" />
            <button
              onClick={() => onChange(defaultColumns)}
              className="w-full rounded px-2 py-1 text-xs text-muted-foreground hover:bg-accent/50 hover:text-foreground"
            >
              Reset to default
            </button>
          </>
        ) : null}
      </PopoverContent>
    </Popover>
  )
}

// ── Main Component ──────────────────────────────────────────
export default function UnallocatedTab({ showHidden }: { showHidden: boolean }) {
  const qc = useQueryClient()
  const isMobile = useIsMobile()
  const [savedLimit, setSavedLimit] = usePersistedState('efactura-page-size', 50)
  const [filters, setFilters] = useState<EFacturaInvoiceFilters>({ page: 1, limit: savedLimit })
  const [search, setSearch] = useState('')
  const [filterTagIds, setFilterTagIds] = useState<number[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [confirmAction, setConfirmAction] = useState<{ action: string; ids: number[] } | null>(null)
  const [viewInvoice, setViewInvoice] = useState<InvoiceRow | null>(null)
  const [editInvoice, setEditInvoice] = useState<InvoiceRow | null>(null)
  const [overrides, setOverrides] = useState({
    type_override: '',
    department_override: '',
    subdepartment_override: '',
    department_override_2: '',
    subdepartment_override_2: '',
  })
  const [splitDept, setSplitDept] = useState(false)
  const [visibleColumns, setVisibleColumnsRaw] = useState<string[]>(loadColumns)

  const setVisibleColumns = (cols: string[]) => {
    setVisibleColumnsRaw(cols)
    saveColumns(cols)
  }

  const activeCols = useMemo(
    () => visibleColumns.map((k) => columnDefMap.get(k)).filter(Boolean) as ColumnDef[],
    [visibleColumns],
  )
  // +3 for checkbox + tags + actions columns
  const totalColSpan = activeCols.length + 3

  const updateFilter = (key: string, value: string | number | boolean | undefined) => {
    setFilters((f) => ({ ...f, [key]: value || undefined, page: 1 }))
    setSelectedIds(new Set())
  }

  // ── Queries ──────────────────────────────────────────────
  const { data: unallocData, isLoading: unallocLoading, isError: unallocError, refetch: refetchUnalloc } = useQuery({
    queryKey: ['efactura-unallocated', { ...filters, search }],
    queryFn: () => efacturaApi.getUnallocated({ ...filters, search: search || undefined }),
  })

  const { data: hiddenData, isLoading: hiddenLoading } = useQuery({
    queryKey: ['efactura-hidden', { ...filters, search }],
    queryFn: () => efacturaApi.getHidden({ ...filters, search: search || undefined }),
    enabled: showHidden,
  })

  // Department dropdowns for Edit Overrides dialog
  const companies = unallocData?.companies ?? []
  const editCompanyName = editInvoice
    ? companies.find((c) => c.id === editInvoice.company_id)?.name
    : undefined

  const { data: departments = [] } = useQuery({
    queryKey: ['departments', editCompanyName],
    queryFn: () => organizationApi.getDepartments(editCompanyName!),
    enabled: !!editCompanyName,
  })

  const { data: subdepartments1 = [] } = useQuery({
    queryKey: ['subdepartments', editCompanyName, overrides.department_override],
    queryFn: () => organizationApi.getSubdepartments(editCompanyName!, overrides.department_override),
    enabled: !!editCompanyName && !!overrides.department_override,
  })

  const { data: subdepartments2 = [] } = useQuery({
    queryKey: ['subdepartments', editCompanyName, overrides.department_override_2],
    queryFn: () => organizationApi.getSubdepartments(editCompanyName!, overrides.department_override_2),
    enabled: !!editCompanyName && !!overrides.department_override_2,
  })

  const { data: supplierTypes = [] } = useQuery({
    queryKey: ['supplier-types'],
    queryFn: () => efacturaApi.getSupplierTypes(true),
    enabled: !!editInvoice,
  })

  // ── Mutations ─────────────────────────────────────────────
  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ['efactura-unallocated'] })
    qc.invalidateQueries({ queryKey: ['efactura-hidden'] })
    qc.invalidateQueries({ queryKey: ['efactura-unallocated-count'] })
    qc.invalidateQueries({ queryKey: ['efactura-hidden-count'] })
    setSelectedIds(new Set())
    setConfirmAction(null)
  }

  const sendToModuleMut = useMutation({
    mutationFn: (ids: number[]) => efacturaApi.sendToModule(ids),
    onSuccess: invalidateAll,
  })

  const bulkHideMut = useMutation({
    mutationFn: (ids: number[]) => efacturaApi.bulkHide(ids),
    onSuccess: invalidateAll,
  })

  const bulkRestoreHiddenMut = useMutation({
    mutationFn: (ids: number[]) => efacturaApi.bulkRestoreHidden(ids),
    onSuccess: invalidateAll,
  })

  const deleteMut = useMutation({
    mutationFn: async (ids: number[]) => {
      if (ids.length === 1) await efacturaApi.deleteInvoice(ids[0])
      else await efacturaApi.bulkDelete(ids)
    },
    onSuccess: invalidateAll,
  })

  const updateOverridesMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, string | null> }) =>
      efacturaApi.updateOverrides(id, data),
    onSuccess: () => {
      invalidateAll()
      setEditInvoice(null)
    },
  })

  // ── Derived state ────────────────────────────────────────
  const unallocInvoices = unallocData?.invoices ?? []
  const hiddenInvoices = showHidden ? (hiddenData?.invoices ?? []) : []
  const invoices: InvoiceRow[] = [
    ...unallocInvoices.map((i) => ({ ...i, _hidden: false })),
    ...hiddenInvoices.map((i) => ({ ...i, _hidden: true })),
  ]
  const isLoading = unallocLoading || (showHidden && hiddenLoading)
  const pagination = unallocData?.pagination

  // Entity tags for e-factura invoices
  const efacturaIds = useMemo(() => invoices.map((i) => i.id), [invoices])
  const { data: efacturaTagsMap = {} } = useQuery({
    queryKey: ['entity-tags', 'efactura_invoice', efacturaIds],
    queryFn: () => tagsApi.getEntityTagsBulk('efactura_invoice', efacturaIds),
    enabled: efacturaIds.length > 0,
  })

  // Apply tag filter client-side
  const displayedInvoices = useMemo(() => {
    if (filterTagIds.length === 0) return invoices
    return invoices.filter((inv) => {
      const tags = efacturaTagsMap[String(inv.id)] ?? []
      return tags.some((t) => filterTagIds.includes(t.id))
    })
  }, [invoices, filterTagIds, efacturaTagsMap])

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    if (selectedIds.size === displayedInvoices.length) setSelectedIds(new Set())
    else setSelectedIds(new Set(displayedInvoices.map((i) => i.id)))
  }

  const selectedInvoices = displayedInvoices.filter((i) => selectedIds.has(i.id))
  const hasUnallocSelected = selectedInvoices.some((i) => !i._hidden)
  const hasHiddenSelected = selectedInvoices.some((i) => i._hidden)

  /** Invoice can be sent to accounting only if it has Type + Department (from override or mapping) */
  const canSend = (inv: InvoiceRow) =>
    !!(inv.type_override || inv.mapped_type_names?.length) &&
    !!(inv.department_override || inv.mapped_department)

  const efacturaMobileFields: MobileCardField<InvoiceRow>[] = useMemo(() => [
    {
      key: 'supplier',
      label: 'Supplier',
      isPrimary: true,
      render: (inv) => (
        <span>
          {inv.partner_name}
          {inv._hidden && <span className="ml-1 text-[10px] text-muted-foreground">(hidden)</span>}
        </span>
      ),
    },
    {
      key: 'invoice_number',
      label: 'Invoice #',
      isSecondary: true,
      render: (inv) => (
        <span className="font-mono text-xs">
          {inv.invoice_series ? `${inv.invoice_series}-` : ''}
          {inv.invoice_number}
        </span>
      ),
    },
    {
      key: 'date',
      label: 'Date',
      isSecondary: true,
      render: (inv) => fmtDate(inv.issue_date),
    },
    {
      key: 'amount',
      label: 'Amount',
      render: (inv) => <CurrencyDisplay value={inv.total_amount} currency={inv.currency} />,
    },
    {
      key: 'direction',
      label: 'Direction',
      render: (inv) => <StatusBadge status={inv.direction} />,
    },
    {
      key: 'company',
      label: 'Company',
      expandOnly: true,
      render: (inv) => <span className="text-xs">{inv.company_name || inv.cif_owner || '—'}</span>,
    },
    {
      key: 'type',
      label: 'Type',
      expandOnly: true,
      render: (inv) => <span className="text-xs">{inv.type_override || inv.mapped_type_names?.join(', ') || '—'}</span>,
    },
    {
      key: 'department',
      label: 'Department',
      expandOnly: true,
      render: (inv) => <span className="text-xs">{inv.department_override || inv.mapped_department || '—'}</span>,
    },
  ], [])

  const executeAction = () => {
    if (!confirmAction) return
    const { action, ids } = confirmAction
    switch (action) {
      case 'send': sendToModuleMut.mutate(ids); break
      case 'hide': bulkHideMut.mutate(ids); break
      case 'restore-hidden': bulkRestoreHiddenMut.mutate(ids); break
      case 'delete': deleteMut.mutate(ids); break
    }
  }

  const openEdit = (inv: InvoiceRow) => {
    setOverrides({
      type_override: inv.type_override ?? '',
      department_override: inv.department_override ?? '',
      subdepartment_override: inv.subdepartment_override ?? '',
      department_override_2: inv.department_override_2 ?? '',
      subdepartment_override_2: inv.subdepartment_override_2 ?? '',
    })
    setSplitDept(!!(inv.department_override_2 || inv.subdepartment_override_2))
    setEditInvoice(inv)
  }

  const saveOverrides = () => {
    if (!editInvoice) return
    const data: Record<string, string | null> = {}
    for (const [k, v] of Object.entries(overrides)) {
      data[k] = v || null
    }
    // Clear second department pair if split is off
    if (!splitDept) {
      data.department_override_2 = null
      data.subdepartment_override_2 = null
    }
    updateOverridesMut.mutate({ id: editInvoice.id, data })
  }

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-col gap-3 md:flex-row md:flex-wrap md:items-end">
        {companies.length > 0 && (
          <div className="space-y-1">
            <Label className="text-xs">Company</Label>
            <Select
              value={filters.company_id?.toString() ?? 'all'}
              onValueChange={(v) => updateFilter('company_id', v === 'all' ? undefined : Number(v))}
            >
              <SelectTrigger className="w-[200px]">
                <SelectValue placeholder="All companies" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All companies</SelectItem>
                {companies.map((c) => (
                  <SelectItem key={c.id} value={c.id.toString()}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        <div className="space-y-1">
          <Label className="text-xs">Direction</Label>
          <Select
            value={filters.direction ?? 'all'}
            onValueChange={(v) => updateFilter('direction', v === 'all' ? undefined : v)}
          >
            <SelectTrigger className="w-[130px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="received">Received</SelectItem>
              <SelectItem value="sent">Sent</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <Label className="text-xs">Period</Label>
          <DatePresetSelect
            startDate={filters.start_date ?? ''}
            endDate={filters.end_date ?? ''}
            onChange={(s, e) => {
              setFilters((f) => ({ ...f, start_date: s || undefined, end_date: e || undefined, page: 1 }))
              setSelectedIds(new Set())
            }}
          />
        </div>

        <div className="space-y-1">
          <Label className="text-xs">From</Label>
          <Input
            type="date"
            className="w-[150px]"
            value={filters.start_date ?? ''}
            onChange={(e) => updateFilter('start_date', e.target.value)}
          />
        </div>

        <div className="space-y-1">
          <Label className="text-xs">To</Label>
          <Input
            type="date"
            className="w-[150px]"
            value={filters.end_date ?? ''}
            onChange={(e) => updateFilter('end_date', e.target.value)}
          />
        </div>

        <SearchInput
          value={search}
          onChange={setSearch}
          placeholder="Search supplier, invoice#..."
          className="w-[200px]"
        />

        <TagFilter selectedTagIds={filterTagIds} onChange={setFilterTagIds} />

        {!isMobile && (
          <div className="ml-auto">
            <ColumnToggle visibleColumns={visibleColumns} onChange={setVisibleColumns} />
          </div>
        )}
      </div>

      {/* Bulk actions */}
      {selectedIds.size > 0 && (
        <div className={cn(
          'flex flex-wrap items-center gap-2 rounded border bg-muted/30 px-3 py-2',
          isMobile && 'fixed inset-x-0 bottom-14 z-40 mx-2 rounded-lg border bg-background shadow-lg',
        )}>
          <span className="text-sm font-medium">{selectedIds.size} selected</span>

          {hasUnallocSelected && (() => {
            const sendable = selectedInvoices.filter((i) => !i._hidden && canSend(i))
            const unsendable = selectedInvoices.filter((i) => !i._hidden && !canSend(i))
            return (
            <>
              <Button size="sm" disabled={sendable.length === 0} onClick={() => setConfirmAction({
                action: 'send',
                ids: sendable.map((i) => i.id),
              })}>
                <Send className="mr-1 h-3 w-3" /> Send to Module{sendable.length > 0 ? ` (${sendable.length})` : ''}
              </Button>
              {unsendable.length > 0 && (
                <span className="text-xs text-amber-600 dark:text-amber-400">
                  {unsendable.length} missing Type/Dept
                </span>
              )}
              <Button size="sm" variant="outline" onClick={() => setConfirmAction({
                action: 'hide',
                ids: selectedInvoices.filter((i) => !i._hidden).map((i) => i.id),
              })}>
                <EyeOff className="mr-1 h-3 w-3" /> Hide
              </Button>
              <Button size="sm" variant="outline" className="text-destructive" onClick={() => setConfirmAction({
                action: 'delete',
                ids: selectedInvoices.filter((i) => !i._hidden).map((i) => i.id),
              })}>
                <Trash2 className="mr-1 h-3 w-3" /> Delete
              </Button>
            </>
            )
          })()}
          {hasHiddenSelected && (
            <Button size="sm" variant="outline" onClick={() => setConfirmAction({
              action: 'restore-hidden',
              ids: selectedInvoices.filter((i) => i._hidden).map((i) => i.id),
            })}>
              <RotateCcw className="mr-1 h-3 w-3" /> Restore
            </Button>
          )}

          <TagPickerButton
            entityType="efactura_invoice"
            entityIds={Array.from(selectedIds)}
            onTagsChanged={() => qc.invalidateQueries({ queryKey: ['entity-tags'] })}
          />
          <Button size="sm" variant="ghost" onClick={() => setSelectedIds(new Set())}>Clear</Button>
        </div>
      )}

      {/* Success banner */}
      {sendToModuleMut.isSuccess && sendToModuleMut.data && (
        <div className="flex items-center gap-2 rounded border border-green-200 bg-green-50 p-3 text-sm text-green-700 dark:border-green-800 dark:bg-green-900/20 dark:text-green-400">
          <CheckCircle className="h-4 w-4" />
          Sent {sendToModuleMut.data.sent} invoice(s) to module.
          {(sendToModuleMut.data.duplicates ?? 0) > 0 && ` ${sendToModuleMut.data.duplicates} duplicate(s) skipped.`}
        </div>
      )}

      {/* Invoice table / Card list */}
      {unallocError ? (
        <QueryError message="Failed to load e-Factura data" onRetry={() => refetchUnalloc()} />
      ) : isLoading ? (
        isMobile ? (
          <MobileCardList data={[]} fields={efacturaMobileFields} getRowId={(inv) => inv.id} isLoading />
        ) : (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => <div key={i} className="h-12 animate-pulse rounded bg-muted/50" />)}
          </div>
        )
      ) : invoices.length === 0 ? (
        <EmptyState
          icon={<FileStack className="h-10 w-10" />}
          title={showHidden ? 'No unallocated or hidden invoices' : 'No unallocated invoices'}
          description={!showHidden ? 'All imported invoices have been allocated' : undefined}
        />
      ) : isMobile ? (
        <MobileCardList
          data={displayedInvoices}
          fields={efacturaMobileFields}
          getRowId={(inv) => inv.id}
          selectable
          selectedIds={selectedIds}
          onToggleSelect={toggleSelect}
          actions={(inv) => (
            <>
              {inv._hidden ? (
                <Button variant="ghost" size="icon" className="h-8 w-8" title="Restore"
                  onClick={() => setConfirmAction({ action: 'restore-hidden', ids: [inv.id] })}>
                  <RotateCcw className="h-4 w-4" />
                </Button>
              ) : (
                <>
                  <Button variant="ghost" size="icon" className="h-8 w-8 text-green-600" title="Send"
                    disabled={!canSend(inv)} onClick={() => setConfirmAction({ action: 'send', ids: [inv.id] })}>
                    <Send className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-8 w-8 text-amber-600" title="Edit"
                    onClick={() => openEdit(inv)}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-8 w-8 text-blue-600" title="View"
                    onClick={() => setViewInvoice(inv)}>
                    <Eye className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-8 w-8" title="Hide"
                    onClick={() => setConfirmAction({ action: 'hide', ids: [inv.id] })}>
                    <EyeOff className="h-4 w-4" />
                  </Button>
                </>
              )}
            </>
          )}
        />
      ) : (
        <div className="rounded border overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="p-2 text-left w-8">
                  <Checkbox
                    checked={invoices.length > 0 && selectedIds.size === invoices.length}
                    onCheckedChange={toggleAll}
                  />
                </th>
                {activeCols.map((col) => (
                  <th key={col.key} className={`p-2 ${col.align === 'right' ? 'text-right' : 'text-left'}`}>
                    {col.label}
                  </th>
                ))}
                <th className="p-2 text-left">Tags</th>
                <th className="p-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {/* Hidden separator */}
              {showHidden && unallocInvoices.length > 0 && hiddenInvoices.length > 0 && (
                <tr>
                  <td colSpan={totalColSpan} className="bg-muted/30 px-3 py-1.5 text-xs font-medium text-muted-foreground">
                    <EyeOff className="mr-1 inline h-3 w-3" />
                    Hidden invoices ({hiddenInvoices.length})
                  </td>
                </tr>
              )}
              {displayedInvoices.map((inv) => (
                <tr
                  key={inv.id}
                  className={`border-b hover:bg-muted/30 ${inv._hidden ? 'opacity-60' : ''}`}
                >
                  <td className="p-2">
                    <Checkbox
                      checked={selectedIds.has(inv.id)}
                      onCheckedChange={() => toggleSelect(inv.id)}
                    />
                  </td>
                  {activeCols.map((col) => (
                    <td key={col.key} className={`p-2 ${col.align === 'right' ? 'text-right' : ''}`}>
                      {col.render(inv)}
                    </td>
                  ))}
                  <td className="p-2">
                    <TagPicker entityType="efactura_invoice" entityId={inv.id} currentTags={efacturaTagsMap[String(inv.id)] ?? []} onTagsChanged={() => {}}>
                      <TagBadgeList tags={efacturaTagsMap[String(inv.id)] ?? []} />
                    </TagPicker>
                  </td>
                  <td className="p-2">
                    <div className="flex justify-end gap-0.5">
                      {inv._hidden ? (
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-7 w-7"
                          title="Restore"
                          onClick={() => setConfirmAction({ action: 'restore-hidden', ids: [inv.id] })}
                        >
                          <RotateCcw className="h-3.5 w-3.5" />
                        </Button>
                      ) : (
                        <>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-7 w-7 text-green-600 dark:text-green-400"
                            title={canSend(inv) ? 'Send to Module' : 'Set Type and Department before sending'}
                            disabled={!canSend(inv)}
                            onClick={() => setConfirmAction({ action: 'send', ids: [inv.id] })}
                          >
                            <Send className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-7 w-7 text-amber-600 dark:text-amber-400"
                            title="Edit Type/Dept"
                            onClick={() => openEdit(inv)}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-7 w-7 text-blue-600 dark:text-blue-400"
                            title="View Details"
                            onClick={() => setViewInvoice(inv)}
                          >
                            <Eye className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-7 w-7 text-red-600 dark:text-red-400"
                            title="Export PDF"
                            onClick={() => window.open(efacturaApi.getInvoicePdfUrl(inv.id), '_blank')}
                          >
                            <FileText className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-7 w-7"
                            title="Hide"
                            onClick={() => setConfirmAction({ action: 'hide', ids: [inv.id] })}
                          >
                            <EyeOff className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-7 w-7 text-destructive"
                            title="Delete"
                            onClick={() => setConfirmAction({ action: 'delete', ids: [inv.id] })}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {pagination && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">
            Page {pagination.page} of {pagination.total_pages} ({pagination.total} invoices)
          </span>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-muted-foreground">Rows</span>
              <Select
                value={String(filters.limit ?? 50)}
                onValueChange={(v) => { const n = Number(v); setSavedLimit(n); setFilters((f) => ({ ...f, limit: n, page: 1 })) }}
              >
                <SelectTrigger className="h-8 w-[70px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {[25, 50, 100, 200].map((n) => (
                    <SelectItem key={n} value={String(n)}>{n}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={!pagination.has_prev}
                onClick={() => setFilters((f) => ({ ...f, page: (f.page ?? 1) - 1 }))}
              >
                Previous
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={!pagination.has_next}
                onClick={() => setFilters((f) => ({ ...f, page: (f.page ?? 1) + 1 }))}
              >
                Next
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Confirm dialog */}
      <ConfirmDialog
        open={!!confirmAction}
        onOpenChange={() => setConfirmAction(null)}
        title={
          confirmAction?.action === 'send' ? 'Send to Invoice Module'
          : confirmAction?.action === 'hide' ? 'Hide Invoices'
          : confirmAction?.action === 'delete' ? 'Delete Invoices'
          : 'Restore from Hidden'
        }
        description={
          confirmAction?.action === 'delete'
            ? `This will move ${confirmAction.ids.length} invoice(s) to the bin.`
            : `This will affect ${confirmAction?.ids.length ?? 0} invoice(s).`
        }
        onConfirm={executeAction}
        destructive={confirmAction?.action === 'delete'}
      />

      {/* View Details Dialog */}
      <Dialog open={!!viewInvoice} onOpenChange={() => setViewInvoice(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Invoice Details</DialogTitle>
          </DialogHeader>
          {viewInvoice && (
            <div className="grid grid-cols-1 gap-x-4 gap-y-2 text-sm sm:grid-cols-2">
              <div className="text-muted-foreground">Supplier</div>
              <div className="font-medium">{viewInvoice.partner_name}</div>

              <div className="text-muted-foreground">Supplier CIF</div>
              <div>{viewInvoice.partner_cif || '—'}</div>

              <div className="text-muted-foreground">Invoice #</div>
              <div className="font-mono">
                {viewInvoice.invoice_series ? `${viewInvoice.invoice_series}-` : ''}
                {viewInvoice.invoice_number}
              </div>

              <div className="text-muted-foreground">Issue Date</div>
              <div>{fmtDate(viewInvoice.issue_date)}</div>

              <div className="text-muted-foreground">Due Date</div>
              <div>{fmtDate(viewInvoice.due_date ?? null)}</div>

              <div className="text-muted-foreground">Direction</div>
              <div><StatusBadge status={viewInvoice.direction} /></div>

              <div className="col-span-2 mt-2 border-t pt-2" />

              <div className="text-muted-foreground">Total Amount</div>
              <div className="font-medium"><CurrencyDisplay value={viewInvoice.total_amount} currency={viewInvoice.currency} /></div>

              <div className="text-muted-foreground">VAT</div>
              <div><CurrencyDisplay value={viewInvoice.total_vat} currency={viewInvoice.currency} /></div>

              <div className="text-muted-foreground">Without VAT</div>
              <div><CurrencyDisplay value={viewInvoice.total_without_vat} currency={viewInvoice.currency} /></div>

              <div className="col-span-2 mt-2 border-t pt-2" />

              <div className="text-muted-foreground">Company (CIF)</div>
              <div>{viewInvoice.cif_owner}</div>

              <div className="text-muted-foreground">Type Override</div>
              <div>{viewInvoice.type_override || '—'}</div>

              <div className="text-muted-foreground">Mapped Type(s)</div>
              <div>{viewInvoice.mapped_type_names?.join(', ') || '—'}</div>

              <div className="text-muted-foreground">Mapped Supplier</div>
              <div>{viewInvoice.mapped_supplier_name || '—'}</div>

              <div className="text-muted-foreground">Mapped Brand</div>
              <div>{viewInvoice.mapped_brand || '—'}</div>

              <div className="text-muted-foreground">Mapped Dept</div>
              <div>{viewInvoice.mapped_department || '—'}</div>

              <div className="text-muted-foreground">Mapped Subdept</div>
              <div>{viewInvoice.mapped_subdepartment || '—'}</div>

              <div className="text-muted-foreground">Kod Konto</div>
              <div>{viewInvoice.mapped_kod_konto || '—'}</div>

              <div className="col-span-2 mt-2 border-t pt-2" />
              <div className="col-span-2">
                <ApprovalWidget entityType="efactura_invoice" entityId={viewInvoice.id} />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => viewInvoice && window.open(efacturaApi.getInvoicePdfUrl(viewInvoice.id), '_blank')}
            >
              <FileText className="mr-1.5 h-3.5 w-3.5" /> Export PDF
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Overrides Dialog */}
      <Dialog open={!!editInvoice} onOpenChange={() => setEditInvoice(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Edit Invoice Overrides</DialogTitle>
          </DialogHeader>
          {editInvoice && (
            <div className="space-y-4">
              {/* Invoice info header */}
              <div className="rounded-md border bg-muted/50 px-3 py-2 text-sm">
                <div className="font-medium">
                  {editInvoice.invoice_series ? `${editInvoice.invoice_series}-` : ''}
                  {editInvoice.invoice_number}
                  <span className="ml-2 font-normal text-muted-foreground">
                    {editInvoice.partner_name}
                  </span>
                </div>
                <div className="mt-0.5 text-xs text-muted-foreground">
                  {fmtDate(editInvoice.issue_date)} &middot;{' '}
                  <CurrencyDisplay value={editInvoice.total_amount} currency={editInvoice.currency} />
                </div>
              </div>

              {/* Type Override */}
              <div className="space-y-1">
                <Label className="text-xs">Type Override</Label>
                {supplierTypes.length > 0 ? (
                  <Select
                    value={overrides.type_override || '__default__'}
                    onValueChange={(v) => setOverrides((o) => ({ ...o, type_override: v === '__default__' ? '' : v }))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__default__">-- Use Mapping Default --</SelectItem>
                      {supplierTypes.map((t) => (
                        <SelectItem key={t.id} value={t.name}>{t.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Input
                    value={overrides.type_override}
                    onChange={(e) => setOverrides((o) => ({ ...o, type_override: e.target.value }))}
                    placeholder="e.g. Service, Parts, Marketing..."
                  />
                )}
                <p className="text-[11px] text-muted-foreground">Leave empty to use the supplier mapping default</p>
              </div>

              {/* Department 1 */}
              <div className="space-y-1">
                <Label className="text-xs">Department Override</Label>
                {departments.length > 0 ? (
                  <Select
                    value={overrides.department_override || '__default__'}
                    onValueChange={(v) => setOverrides((o) => ({
                      ...o,
                      department_override: v === '__default__' ? '' : v,
                      subdepartment_override: '',
                    }))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__default__">-- Use Mapping Default --</SelectItem>
                      {departments.map((d) => (
                        <SelectItem key={d} value={d}>{d}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Input
                    value={overrides.department_override}
                    onChange={(e) => setOverrides((o) => ({ ...o, department_override: e.target.value }))}
                    placeholder="Department"
                  />
                )}
                <p className="text-[11px] text-muted-foreground">Leave empty to use the supplier mapping default</p>
              </div>

              <div className="space-y-1">
                <Label className="text-xs">Subdepartment Override</Label>
                <Select
                  value={overrides.subdepartment_override || '__default__'}
                  onValueChange={(v) => setOverrides((o) => ({
                    ...o,
                    subdepartment_override: v === '__default__' ? '' : v,
                  }))}
                  disabled={!overrides.department_override || subdepartments1.length === 0}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__default__">-- Use Mapping Default --</SelectItem>
                    {subdepartments1.map((s) => (
                      <SelectItem key={s} value={s}>{s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Split between two departments */}
              <div className="flex items-center gap-2">
                <Checkbox
                  id="split-dept"
                  checked={splitDept}
                  onCheckedChange={(checked) => {
                    const on = !!checked
                    setSplitDept(on)
                    if (!on) {
                      setOverrides((o) => ({
                        ...o,
                        department_override_2: '',
                        subdepartment_override_2: '',
                      }))
                    }
                  }}
                />
                <div>
                  <Label htmlFor="split-dept" className="text-xs font-normal cursor-pointer">
                    Split between two departments
                  </Label>
                  <p className="text-[11px] text-muted-foreground">
                    When enabled, the invoice will be sent to Accounting without auto-allocation
                  </p>
                </div>
              </div>

              {/* Department 2 (conditional) */}
              {splitDept && (
                <>
                  <div className="space-y-1">
                    <Label className="text-xs">Department 2</Label>
                    {departments.length > 0 ? (
                      <Select
                        value={overrides.department_override_2 || '__default__'}
                        onValueChange={(v) => setOverrides((o) => ({
                          ...o,
                          department_override_2: v === '__default__' ? '' : v,
                          subdepartment_override_2: '',
                        }))}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__default__">-- Select --</SelectItem>
                          {departments.map((d) => (
                            <SelectItem key={d} value={d}>{d}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    ) : (
                      <Input
                        value={overrides.department_override_2}
                        onChange={(e) => setOverrides((o) => ({ ...o, department_override_2: e.target.value }))}
                        placeholder="Department 2"
                      />
                    )}
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Subdepartment 2</Label>
                    <Select
                      value={overrides.subdepartment_override_2 || '__default__'}
                      onValueChange={(v) => setOverrides((o) => ({
                        ...o,
                        subdepartment_override_2: v === '__default__' ? '' : v,
                      }))}
                      disabled={!overrides.department_override_2 || subdepartments2.length === 0}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__default__">-- Select --</SelectItem>
                        {subdepartments2.map((s) => (
                          <SelectItem key={s} value={s}>{s}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditInvoice(null)}>Cancel</Button>
            <Button onClick={saveOverrides} disabled={updateOverridesMut.isPending}>
              {updateOverridesMut.isPending ? 'Saving...' : 'Save Overrides'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
