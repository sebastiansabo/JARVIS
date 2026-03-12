import React, { useState, useMemo, useCallback, memo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  FileText,
  Building2,
  FolderTree,
  FolderArchive,

  Trash2,
  Plus,
  Pencil,
  RotateCcw,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Columns3,
  GripVertical,
  Eye,
  EyeOff,
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
  BarChart3,
  CheckSquare,
  SlidersHorizontal,
  LayoutDashboard,
  Link2,
  Search,
  X,
  Paperclip,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Checkbox } from '@/components/ui/checkbox'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from '@/components/ui/select'
import { PageHeader } from '@/components/shared/PageHeader'
import { useDashboardWidgetToggle } from '@/hooks/useDashboardWidgetToggle'
import { StatCard } from '@/components/shared/StatCard'
import { TableSkeleton } from '@/components/shared/TableSkeleton'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { CurrencyDisplay } from '@/components/shared/CurrencyDisplay'
import { SearchInput } from '@/components/shared/SearchInput'
import { FilterBar, type FilterField } from '@/components/shared/FilterBar'
import { DateField } from '@/components/ui/date-field'
import { EmptyState } from '@/components/shared/EmptyState'
import { Skeleton } from '@/components/ui/skeleton'
import { QueryError } from '@/components/QueryError'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { TagBadgeList } from '@/components/shared/TagBadge'
import { TagPicker, TagPickerButton } from '@/components/shared/TagPicker'
import { TagFilter } from '@/components/shared/TagFilter'
import { invoicesApi } from '@/api/invoices'
import { organizationApi } from '@/api/organization'
import { settingsApi } from '@/api/settings'
import { tagsApi } from '@/api/tags'
import { useAccountingStore, lockedColumns } from '@/stores/accountingStore'
import { useAuthStore } from '@/stores/authStore'
import { cn, usePersistedState, useDebounce } from '@/lib/utils'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import type { Invoice, InvoiceFilters, InvoiceDmsLink, DmsDocSearchResult } from '@/types/invoices'
import { EditInvoiceDialog } from './EditInvoiceDialog'
// import { SummaryTable } from './SummaryTable'
import { AllocationEditor, allocationsToRows, rowsToApiPayload } from './AllocationEditor'
import { ApprovalWidget } from '@/components/shared/ApprovalWidget'
import { BrandFilter } from '@/components/shared/BrandFilter'


// Subtle row tint based on invoice status
const statusRowBg: Record<string, string> = {
  processed: 'bg-green-500/5 border-l-green-500/50',
  new: 'bg-blue-500/5 border-l-blue-500/50',
  incomplete: 'bg-orange-500/5 border-l-orange-500/50',
  eronata: 'bg-red-500/5 border-l-red-500/50',
  nebugetata: 'bg-yellow-500/5 border-l-yellow-500/50',
  bugetata: 'bg-teal-500/5 border-l-teal-500/50',
  approved: 'bg-emerald-500/5 border-l-emerald-500/50',
  paid: 'bg-green-500/5 border-l-green-500/50',
  unpaid: 'bg-red-500/5 border-l-red-500/50',
  pending: 'bg-yellow-500/5 border-l-yellow-500/50',
}

function formatDate(dateStr: string) {
  const d = new Date(dateStr)
  return d.toLocaleDateString('ro-RO', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

export default function Accounting() {
  const queryClient = useQueryClient()
  const isMobile = useIsMobile()
  const { isOnDashboard, toggleDashboardWidget } = useDashboardWidgetToggle('accounting_invoices')
  const [showBin, setShowBin] = useState(false)
  const [search, setSearch] = useState('')
  const [editInvoice, setEditInvoice] = useState<Invoice | null>(null)
  const [expandedRow, setExpandedRow] = useState<number | null>(null)
  const [deleteIds, setDeleteIds] = useState<number[] | null>(null)
  const [permanentDeleteIds, setPermanentDeleteIds] = useState<number[] | null>(null)
  const [sort, setSort] = usePersistedState<SortState | null>('accounting-sort', null)
  const [filterTagIds, setFilterTagIds] = useState<number[]>([])
  const [showStats, setShowStats] = useState(false)
  const [totalCurrency, setTotalCurrency] = useState<'RON' | 'EUR'>('RON')
  const [showFilters, setShowFilters] = useState(false)
  const [selectMode, setSelectMode] = useState(false)
  const [brandFilterKey, setBrandFilterKey] = useState<string | null>(null)
  const [binSelectedIds, setBinSelectedIds] = useState<number[]>([])

  const toggleBinSelected = useCallback((id: number) => {
    setBinSelectedIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])
  }, [])
  const clearBinSelected = useCallback(() => setBinSelectedIds([]), [])

  const user = useAuthStore((s) => s.user)
  const canAdd = user?.can_add_invoices ?? true
  const canEdit = user?.can_edit_invoices ?? true
  const canDelete = user?.can_delete_invoices ?? true

  const filters = useAccountingStore((s) => s.filters)
  const selectedInvoiceIds = useAccountingStore((s) => s.selectedIds)
  const setSelectedInvoiceIds = useAccountingStore((s) => s.setSelectedIds)
  const toggleInvoiceSelected = useAccountingStore((s) => s.toggleSelected)
  const clearSelected = useAccountingStore((s) => s.clearSelected)
  const updateFilter = useAccountingStore((s) => s.updateFilter)
  const visibleColumns = useAccountingStore((s) => s.visibleColumns)
  const setVisibleColumns = useAccountingStore((s) => s.setVisibleColumns)

  // Data queries
  const apiFilters: InvoiceFilters & { include_allocations?: boolean } = {
    ...filters,
    include_allocations: true,
  }

  const { data: invoices = [], isLoading, isError: invoicesError, refetch: refetchInvoices } = useQuery({
    queryKey: ['invoices', filters],
    queryFn: () => invoicesApi.getInvoices(apiFilters),
  })

  const { data: binInvoices = [], isLoading: binLoading, isError: binError, refetch: refetchBin } = useQuery({
    queryKey: ['invoices', 'bin'],
    queryFn: () => invoicesApi.getDeletedInvoices(),
    enabled: showBin,
  })

  // Entity tags for invoices
  const invoiceIds = useMemo(() => invoices.map((i) => i.id), [invoices])
  const { data: entityTagsMap = {} } = useQuery({
    queryKey: ['entity-tags', 'invoice', invoiceIds],
    queryFn: () => tagsApi.getEntityTagsBulk('invoice', invoiceIds),
    enabled: invoiceIds.length > 0,
  })

  // Filter options
  const { data: companies = [] } = useQuery({
    queryKey: ['companies'],
    queryFn: () => organizationApi.getCompanies(),
    staleTime: 5 * 60 * 1000,
  })

  const { data: dropdownOptions = [] } = useQuery({
    queryKey: ['settings', 'dropdowns'],
    queryFn: () => settingsApi.getDropdownOptions(),
    staleTime: 5 * 60 * 1000,
  })

  const statusOptions = useMemo(
    () => dropdownOptions.filter((d) => d.dropdown_type === 'invoice_status').map((d) => ({ value: d.value, label: d.label, color: d.color })),
    [dropdownOptions],
  )

  const paymentOptions = useMemo(
    () =>
      dropdownOptions.filter((d) => d.dropdown_type === 'payment_status').map((d) => ({ value: d.value, label: d.label, color: d.color })),
    [dropdownOptions],
  )

  const companyOptions = useMemo(
    () => (companies as string[]).map((c) => ({ value: c, label: c })),
    [companies],
  )

  const departmentOptions = useMemo(() => {
    const depts = new Set(invoices.flatMap((inv) => inv.allocations?.map((a) => a.department) ?? []))
    return Array.from(depts)
      .sort()
      .map((d) => ({ value: d, label: d }))
  }, [invoices])

  // Mutations
  const deleteMutation = useMutation({
    mutationFn: (ids: number[]) =>
      ids.length === 1 ? invoicesApi.deleteInvoice(ids[0]) : invoicesApi.bulkDelete(ids),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      clearSelected()
      setDeleteIds(null)
      toast.success('Invoice(s) moved to bin')
    },
    onError: () => toast.error('Failed to delete'),
  })

  const restoreMutation = useMutation({
    mutationFn: (ids: number[]) =>
      ids.length === 1 ? invoicesApi.restoreInvoice(ids[0]) : invoicesApi.bulkRestore(ids),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      clearSelected()
      toast.success('Invoice(s) restored')
    },
    onError: () => toast.error('Failed to restore'),
  })

  const permanentDeleteMutation = useMutation({
    mutationFn: (ids: number[]) =>
      ids.length === 1 ? invoicesApi.permanentDeleteInvoice(ids[0]) : invoicesApi.bulkPermanentDelete(ids),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      clearSelected()
      setPermanentDeleteIds(null)
      toast.success('Invoice(s) permanently deleted')
    },
    onError: () => toast.error('Failed to permanently delete'),
  })

  const storeToDmsMutation = useMutation({
    mutationFn: (ids: number[]) => invoicesApi.storeToDms(ids),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      queryClient.invalidateQueries({ queryKey: ['invoice-dms-docs'] })
      clearSelected()
      const msg = [`${result.stored} stored`]
      if (result.skipped > 0) msg.push(`${result.skipped} already stored`)
      if (result.errors > 0) msg.push(`${result.errors} failed`)
      toast.success(`Store to DMS: ${msg.join(', ')}`)
    },
    onError: () => toast.error('Failed to store to DMS'),
  })

  const updateFieldMutation = useMutation({
    mutationFn: ({ id, field, value }: { id: number; field: string; value: string }) =>
      invoicesApi.updateInvoice(id, { [field]: value }),
    onMutate: async ({ id, field, value }) => {
      // Cancel in-flight fetches so they don't overwrite our optimistic update
      await queryClient.cancelQueries({ queryKey: ['invoices'] })
      // Snapshot previous data for rollback
      const prev = queryClient.getQueryData<Invoice[]>(['invoices', filters])
      // Optimistically update cache — instant UI feedback
      if (prev) {
        queryClient.setQueryData<Invoice[]>(['invoices', filters], prev.map((inv) =>
          inv.id === id ? { ...inv, [field]: value } : inv
        ))
      }
      return { prev }
    },
    onError: (_err, _vars, context) => {
      // Rollback on failure
      if (context?.prev) {
        queryClient.setQueryData(['invoices', filters], context.prev)
      }
      toast.error('Failed to update')
    },
    onSettled: () => {
      // Sync with server in background (won't flash — data is already correct)
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
    },
  })

  // Build active columns with inline dropdowns for status/payment
  const activeCols = useMemo(() => {
    const buildDropdown = (
      options: { value: string; label: string; color: string | null }[],
      field: string,
    ) => (inv: Invoice) => {
      const current = inv[field as keyof Invoice] as string
      const currentOpt = options.find((o) => o.value === current)
      return (
        <Select
          value={current}
          onValueChange={(v) => updateFieldMutation.mutate({ id: inv.id, field, value: v })}
        >
          <SelectTrigger className="h-7 w-[130px] text-xs border-none bg-transparent shadow-none px-1.5">
            <span className="flex items-center gap-1.5">
              {currentOpt?.color && (
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: currentOpt.color }} />
              )}
              <span className="truncate">{currentOpt?.label ?? current}</span>
            </span>
          </SelectTrigger>
          <SelectContent>
            {options.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                <span className="flex items-center gap-1.5">
                  {o.color && (
                    <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: o.color }} />
                  )}
                  {o.label}
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )
    }

    const overrides: Record<string, (inv: Invoice) => React.ReactNode> = {
      status: buildDropdown(statusOptions, 'status'),
      payment_status: buildDropdown(paymentOptions, 'payment_status'),
      tags: (inv: Invoice) => {
        const invTags = entityTagsMap[String(inv.id)] ?? []
        return (
          <TagPicker entityType="invoice" entityId={inv.id} currentTags={invTags} onTagsChanged={() => {}}>
            <TagBadgeList tags={invTags} />
          </TagPicker>
        )
      },
    }
    return visibleColumns
      .map((k) => columnDefMap.get(k))
      .filter(Boolean)
      .map((col) => (col && overrides[col.key] ? { ...col, render: overrides[col.key] } : col)) as ColumnDef[]
  }, [visibleColumns, statusOptions, paymentOptions, entityTagsMap])

  // Derived data
  const applySearchAndSort = useCallback((list: typeof invoices) => {
    if (search) {
      const q = search.toLowerCase()
      list = list.filter(
        (inv) =>
          inv.supplier.toLowerCase().includes(q) ||
          inv.invoice_number.toLowerCase().includes(q) ||
          inv.id.toString().includes(q),
      )
    }
    if (filterTagIds.length > 0) {
      list = list.filter((inv) => {
        const tags = entityTagsMap[String(inv.id)] ?? []
        return tags.some((t) => filterTagIds.includes(t.id))
      })
    }
    if (sort) {
      const colDef = columnDefMap.get(sort.key)
      if (colDef?.sortValue) {
        const getter = colDef.sortValue
        const dir = sort.dir === 'asc' ? 1 : -1
        list = [...list].sort((a, b) => {
          const va = getter(a)
          const vb = getter(b)
          if (va < vb) return -dir
          if (va > vb) return dir
          return 0
        })
      }
    }
    return list
  }, [search, sort, filterTagIds, entityTagsMap, columnDefMap])

  const displayedInvoices = useMemo(() => applySearchAndSort(invoices), [invoices, applySearchAndSort])
  const displayedBinInvoices = useMemo(() => applySearchAndSort(binInvoices), [binInvoices, applySearchAndSort])

  const totalRon = useMemo(
    () => displayedInvoices.reduce((sum, i) => {
      if (i.value_ron != null) return sum + Number(i.value_ron)
      return i.currency === 'RON' ? sum + Number(i.net_value ?? 0) : sum
    }, 0),
    [displayedInvoices],
  )

  const totalEur = useMemo(
    () => displayedInvoices.reduce((sum, i) => {
      if (i.value_eur != null) return sum + Number(i.value_eur)
      return i.currency === 'EUR' ? sum + Number(i.net_value ?? 0) : sum
    }, 0),
    [displayedInvoices],
  )

  const allSelected = displayedInvoices.length > 0 && selectedInvoiceIds.length === displayedInvoices.length
  const someSelected = selectedInvoiceIds.length > 0 && !allSelected

  const binAllSelected = displayedBinInvoices.length > 0 && binSelectedIds.length === displayedBinInvoices.length
  const binSomeSelected = binSelectedIds.length > 0 && !binAllSelected
  const handleBinSelectAll = useCallback(() => {
    if (binAllSelected) clearBinSelected()
    else setBinSelectedIds(displayedBinInvoices.map((i) => i.id))
  }, [binAllSelected, displayedBinInvoices, clearBinSelected])

  const filterFields: FilterField[] = useMemo(() => [
    { key: 'company', label: 'Company', type: 'select' as const, options: companyOptions },
    { key: 'department', label: 'Department', type: 'select' as const, options: departmentOptions },
    { key: 'status', label: 'Status', type: 'select' as const, options: statusOptions },
  ], [companyOptions, departmentOptions, statusOptions])

  const filterValues: Record<string, string> = useMemo(() => ({
    company: filters.company ?? '',
    department: filters.department ?? '',
    status: filters.status ?? '',
  }), [filters.company, filters.department, filters.status])

  const handleFilterChange = useCallback((values: Record<string, string>) => {
    Object.entries(values).forEach(([key, value]) => {
      updateFilter(key as keyof InvoiceFilters, value || undefined)
    })
  }, [updateFilter])

  const handleSelectAll = () => {
    if (allSelected) {
      clearSelected()
    } else {
      setSelectedInvoiceIds(displayedInvoices.map((inv) => inv.id))
    }
  }

  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader
        title="Accounting"
        breadcrumbs={[
          { label: 'Accounting', shortLabel: 'Acc.' },
          { label: 'Invoices' },
        ]}
        search={
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder={isMobile ? 'Search...' : 'Search supplier or invoice #...'}
            className={isMobile ? 'w-40' : 'w-48'}
          />
        }
        actions={
          <div className="flex items-center gap-2">
            {!isMobile && (
              <BrandFilter
                mode="company"
                value={brandFilterKey}
                onSelect={(item) => {
                  setBrandFilterKey(item?.key ?? null)
                  updateFilter('company', (item?.companyName ?? '') as InvoiceFilters['company'])
                }}
              />
            )}
            <Button variant="ghost" size="icon" className={showStats ? 'bg-muted' : ''} onClick={() => setShowStats(s => !s)} title="Toggle stats">
              <BarChart3 className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" className={showFilters ? 'bg-muted' : ''} onClick={() => setShowFilters(s => !s)} title="Toggle filters">
              <SlidersHorizontal className="h-4 w-4" />
            </Button>
            {canDelete && (
              <Button variant="ghost" size="icon" className={cn('hidden md:inline-flex relative', showBin ? 'bg-destructive/15 text-destructive' : '')} onClick={() => { setShowBin(s => !s); clearSelected(); setSelectMode(false) }} title="Bin">
                <Trash2 className="h-4 w-4" />
                {binInvoices.length > 0 && <span className="absolute -top-1 -right-1 rounded-full bg-destructive px-1 py-0 text-[9px] text-destructive-foreground">{binInvoices.length}</span>}
              </Button>
            )}
            <Button variant="ghost" size="icon" className="hidden md:inline-flex" onClick={toggleDashboardWidget} title={isOnDashboard() ? 'Hide from Dashboard' : 'Show on Dashboard'}>
              <LayoutDashboard className="h-4 w-4" />
            </Button>
            {canAdd && (
              <Button size="icon" asChild>
                <Link to="/app/accounting/add">
                  <Plus className="h-4 w-4" />
                </Link>
              </Button>
            )}
          </div>
        }
      />

      {/* Stats row */}
      {showStats && <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          title="Invoices"
          value={displayedInvoices.length}
          icon={<FileText className="h-4 w-4" />}
          isLoading={isLoading}
        />
        <StatCard
          title="Companies"
          value={companyOptions.length}
          icon={<Building2 className="h-4 w-4" />}
        />
        <StatCard
          title="Departments"
          value={departmentOptions.length}
          icon={<FolderTree className="h-4 w-4" />}
          isLoading={isLoading}
        />
        <Card className="gap-0 py-0 cursor-pointer select-none" onClick={() => setTotalCurrency(c => c === 'RON' ? 'EUR' : 'RON')}>
          <CardContent className="px-3 py-2">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-muted-foreground">Total {totalCurrency}</p>
              <span className="text-xs font-bold text-muted-foreground">{totalCurrency}</span>
            </div>
            <p className="text-base font-semibold leading-snug">
              {new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(totalCurrency === 'RON' ? totalRon : totalEur)}
            </p>
            <p className="text-[11px] text-muted-foreground">Click to toggle {totalCurrency === 'RON' ? 'EUR' : 'RON'}</p>
          </CardContent>
        </Card>
      </div>}


      {/* Filter bar */}
      {(
        isMobile ? (
          <div className="flex items-center gap-2">
            <FilterBar fields={filterFields} values={filterValues} onChange={handleFilterChange} iconOnly />
            <TagFilter selectedTagIds={filterTagIds} onChange={setFilterTagIds} iconOnly />
            {selectMode ? (
              <Button variant="ghost" size="sm" className="shrink-0" onClick={() => { clearSelected(); setSelectMode(false) }}>Cancel</Button>
            ) : (
              <Button variant="outline" size="icon" className="shrink-0" onClick={() => setSelectMode(true)} title="Select">
                <CheckSquare className="h-4 w-4" />
              </Button>
            )}
          </div>
        ) : showFilters ? (
          <div className="flex flex-wrap items-center gap-2">
            <FilterBar fields={filterFields} values={filterValues} onChange={handleFilterChange} />
            <DateField
              mode="range"
              startDate={filters.start_date ?? ''}
              endDate={filters.end_date ?? ''}
              onRangeChange={(s, e) => { updateFilter('start_date', s || undefined); updateFilter('end_date', e || undefined) }}
            />
            <TagFilter selectedTagIds={filterTagIds} onChange={setFilterTagIds} />
            <div className="ml-auto flex items-center gap-2">
              <ColumnToggle visibleColumns={visibleColumns} onChange={setVisibleColumns} />
            </div>
          </div>
        ) : null
      )}

      {/* Bulk action bar */}
      {selectedInvoiceIds.length > 0 && (
        <div className="flex items-center gap-2 rounded-lg border bg-muted/50 px-4 py-2">
          <span className="text-sm font-medium">{selectedInvoiceIds.length} selected</span>
          <div className="flex-1" />
          <TagPickerButton
            entityType="invoice"
            entityIds={selectedInvoiceIds}
            onTagsChanged={() => queryClient.invalidateQueries({ queryKey: ['entity-tags'] })}
          />
          <Button
            variant="outline" size="sm"
            onClick={() => storeToDmsMutation.mutate(selectedInvoiceIds)}
            disabled={storeToDmsMutation.isPending}
          >
            <FolderArchive className="mr-1 h-3.5 w-3.5" />
            {storeToDmsMutation.isPending ? 'Storing...' : 'Store to DMS'}
          </Button>
          {canDelete && (
            <Button variant="destructive" size="sm" onClick={() => setDeleteIds(selectedInvoiceIds)}>
              <Trash2 className="mr-1 h-3.5 w-3.5" />
              Delete
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={() => { clearSelected(); setSelectMode(false) }}>
            Cancel
          </Button>
        </div>
      )}

      {/* Bin section — shown at top when toggled */}
      {showBin && (
        <>
          <div className="flex items-center gap-3">
            <div className="h-px flex-1 bg-destructive/30" />
            <span className="text-xs font-medium text-destructive flex items-center gap-1.5">
              <Trash2 className="h-3.5 w-3.5" /> Recycle Bin
              {binInvoices.length > 0 && <span className="ml-1 text-muted-foreground">({binInvoices.length})</span>}
            </span>
            <div className="h-px flex-1 bg-destructive/30" />
          </div>
          {binSelectedIds.length > 0 && (
            <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-2">
              <span className="text-sm font-medium">{binSelectedIds.length} selected</span>
              <div className="flex-1" />
              <Button variant="outline" size="sm" onClick={() => { restoreMutation.mutate(binSelectedIds); clearBinSelected() }}>
                <RotateCcw className="mr-1 h-3.5 w-3.5" /> Restore
              </Button>
              <Button variant="destructive" size="sm" onClick={() => { setPermanentDeleteIds(binSelectedIds); clearBinSelected() }}>
                <Trash2 className="mr-1 h-3.5 w-3.5" /> Delete Forever
              </Button>
              <Button variant="ghost" size="sm" onClick={clearBinSelected}>Cancel</Button>
            </div>
          )}
          {binError ? (
            <QueryError message="Failed to load recycle bin" onRetry={refetchBin} />
          ) : (
            <InvoiceTable
              invoices={displayedBinInvoices}
              isLoading={binLoading}
              selectedIds={binSelectedIds}
              allSelected={binAllSelected}
              someSelected={binSomeSelected}
              onSelectAll={handleBinSelectAll}
              onToggleSelect={toggleBinSelected}
              onEdit={setEditInvoice}
              onDelete={() => {}}
              onRestore={(id) => restoreMutation.mutate([id])}
              onPermanentDelete={(id) => setPermanentDeleteIds([id])}
              expandedRow={expandedRow}
              onToggleExpand={(id) => setExpandedRow(expandedRow === id ? null : id)}
              isBin={true}
              activeCols={activeCols}
              sort={sort}
              onSort={setSort}
              isMobile={isMobile}
              selectMode={true}
              canEdit={canEdit}
              canDelete={canDelete}
            />
          )}
          <div className="flex items-center gap-3">
            <div className="h-px flex-1 bg-border" />
            <span className="text-xs text-muted-foreground">Invoices</span>
            <div className="h-px flex-1 bg-border" />
          </div>
        </>
      )}

      {/* Invoices table */}
      {invoicesError ? (
        <QueryError message="Failed to load invoices" onRetry={refetchInvoices} />
      ) : (
        <InvoiceTable
          invoices={displayedInvoices}
          isLoading={isLoading}
          selectedIds={selectedInvoiceIds}
          allSelected={allSelected}
          someSelected={someSelected}
          onSelectAll={handleSelectAll}
          onToggleSelect={toggleInvoiceSelected}
          onEdit={setEditInvoice}
          onDelete={(id) => setDeleteIds([id])}
          onRestore={(id) => restoreMutation.mutate([id])}
          onPermanentDelete={(id) => setPermanentDeleteIds([id])}
          expandedRow={expandedRow}
          onToggleExpand={(id) => setExpandedRow(expandedRow === id ? null : id)}
          isBin={false}
          activeCols={activeCols}
          sort={sort}
          onSort={setSort}
          isMobile={isMobile}
          selectMode={selectMode}
          canEdit={canEdit}
          canDelete={canDelete}
        />
      )}

      {/* Edit dialog */}
      {editInvoice && (
        <EditInvoiceDialog
          invoice={editInvoice}
          open={!!editInvoice}
          onClose={() => setEditInvoice(null)}
          statusOptions={statusOptions}
          paymentOptions={paymentOptions}
        />
      )}

      {/* Delete confirmation */}
      <ConfirmDialog
        open={!!deleteIds}
        onOpenChange={() => setDeleteIds(null)}
        title="Delete Invoice(s)"
        description={`Move ${deleteIds?.length ?? 0} invoice(s) to the recycle bin?`}
        onConfirm={() => deleteIds && deleteMutation.mutate(deleteIds)}
        destructive
      />

      {/* Permanent delete confirmation */}
      <ConfirmDialog
        open={!!permanentDeleteIds}
        onOpenChange={() => setPermanentDeleteIds(null)}
        title="Permanently Delete"
        description={`This will permanently delete ${permanentDeleteIds?.length ?? 0} invoice(s) and remove associated Drive files. This cannot be undone.`}
        onConfirm={() => permanentDeleteIds && permanentDeleteMutation.mutate(permanentDeleteIds)}
        destructive
      />
    </div>
  )
}

/* ──── Column Definitions ──── */

type SortDir = 'asc' | 'desc'
interface SortState { key: string; dir: SortDir }

interface ColumnDef {
  key: string
  label: string
  headerClass?: string
  sortable?: boolean
  sortValue?: (inv: Invoice) => string | number
  render: (inv: Invoice) => React.ReactNode
}

const columnDefs: ColumnDef[] = [
  {
    key: 'status',
    label: 'Status',
    sortable: true,
    sortValue: (inv) => inv.status,
    render: (inv) => <StatusBadge status={inv.status} />,
  },
  {
    key: 'payment_status',
    label: 'Payment',
    sortable: true,
    sortValue: (inv) => inv.payment_status,
    render: (inv) => <StatusBadge status={inv.payment_status} />,
  },
  {
    key: 'invoice_date',
    label: 'Date',
    sortable: true,
    sortValue: (inv) => inv.invoice_date,
    render: (inv) => <span className="whitespace-nowrap text-sm">{formatDate(inv.invoice_date)}</span>,
  },
  {
    key: 'supplier',
    label: 'Supplier',
    sortable: true,
    sortValue: (inv) => inv.supplier.toLowerCase(),
    render: (inv) => <span className="block max-w-[200px] truncate text-sm">{inv.supplier}</span>,
  },
  {
    key: 'invoice_number',
    label: 'Invoice #',
    sortable: true,
    sortValue: (inv) => inv.invoice_number.toLowerCase(),
    render: (inv) => <span className="text-sm font-medium">{inv.invoice_number}</span>,
  },
  {
    key: 'net_value',
    label: 'Net Value',
    headerClass: 'text-right',
    sortable: true,
    sortValue: (inv) => Number(inv.net_value ?? 0),
    render: (inv) => (
      <div className="text-right">
        {inv.net_value != null ? (
          <CurrencyDisplay value={inv.net_value} currency={inv.currency} />
        ) : (
          <span className="text-muted-foreground text-xs">-</span>
        )}
      </div>
    ),
  },
  {
    key: 'invoice_value',
    label: 'Total',
    headerClass: 'text-right',
    sortable: true,
    sortValue: (inv) => Number(inv.invoice_value),
    render: (inv) => (
      <div className="text-right">
        <CurrencyDisplay value={inv.invoice_value} currency={inv.currency} />
      </div>
    ),
  },
  {
    key: 'drive_link',
    label: 'Drive Link',
    render: (inv) =>
      inv.drive_link ? (
        <a href={inv.drive_link} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline text-xs truncate block max-w-[120px]">
          Link
        </a>
      ) : (
        <span className="text-muted-foreground text-xs">-</span>
      ),
  },
  {
    key: 'company',
    label: 'Company',
    sortable: true,
    sortValue: (inv) => (inv.allocations?.[0]?.company ?? '').toLowerCase(),
    render: (inv) => <span className="text-sm">{inv.allocations?.[0]?.company ?? '-'}</span>,
  },
  {
    key: 'department',
    label: 'Department',
    sortable: true,
    sortValue: (inv) => (inv.allocations?.[0]?.department ?? '').toLowerCase(),
    render: (inv) => <span className="text-sm">{inv.allocations?.[0]?.department ?? '-'}</span>,
  },
  {
    key: 'tags',
    label: 'Tags',
    render: () => null,
  },
]

const columnDefMap = new Map(columnDefs.map((c) => [c.key, c]))

/* ──── Column Toggle + Reorder ──── */

function ColumnToggle({
  visibleColumns,
  onChange,
}: {
  visibleColumns: string[]
  onChange: (cols: string[]) => void
}) {
  const hiddenColumns = columnDefs.filter((c) => !visibleColumns.includes(c.key) && !lockedColumns.has(c.key))

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
    if (lockedColumns.has(key)) return
    if (visibleColumns.includes(key)) {
      onChange(visibleColumns.filter((c) => c !== key))
    } else {
      onChange([...visibleColumns, key])
    }
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="icon" className="h-9 w-9 shrink-0" title="Toggle columns" aria-label="Toggle columns">
          <Columns3 className="h-4 w-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-56 p-3">
        <p className="mb-2 text-xs font-medium text-muted-foreground">Columns &amp; Order</p>
        <div className="space-y-0.5">
          {visibleColumns.map((key, idx) => {
            const col = columnDefMap.get(key)
            if (!col) return null
            const isLocked = lockedColumns.has(key)
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
                {isLocked ? (
                  <span className="p-0.5 text-muted-foreground/40" title="Always visible">
                    <EyeOff className="h-3 w-3" />
                  </span>
                ) : (
                  <button onClick={() => toggle(key)} className="rounded p-0.5 text-muted-foreground hover:text-foreground">
                    <EyeOff className="h-3 w-3" />
                  </button>
                )}
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
      </PopoverContent>
    </Popover>
  )
}

/* ──── Invoice Table ──── */

function InvoiceTable({
  invoices,
  isLoading,
  selectedIds,
  allSelected,
  someSelected,
  onSelectAll,
  onToggleSelect,
  onEdit,
  onDelete,
  onRestore,
  onPermanentDelete,
  expandedRow,
  onToggleExpand,
  isBin,
  activeCols,
  sort,
  onSort,
  isMobile,
  selectMode,
  canEdit,
  canDelete,
}: {
  invoices: Invoice[]
  isLoading: boolean
  selectedIds: number[]
  allSelected: boolean
  someSelected: boolean
  onSelectAll: () => void
  onToggleSelect: (id: number) => void
  onEdit: (inv: Invoice) => void
  onDelete: (id: number) => void
  onRestore: (id: number) => void
  onPermanentDelete: (id: number) => void
  expandedRow: number | null
  onToggleExpand: (id: number) => void
  isBin: boolean
  activeCols: ColumnDef[]
  sort: SortState | null
  onSort: (s: SortState | null) => void
  isMobile?: boolean
  selectMode?: boolean
  canEdit?: boolean
  canDelete?: boolean
}) {
  const colCount = 2 + activeCols.length + 1 // checkbox + ID + visible cols + actions

  // Payment status → dot color (Apple-style minimal indicator)
  const paymentDotColor = useCallback((status: string | undefined | null) => {
    if (!status) return 'bg-gray-300'
    switch (status.toLowerCase()) {
      case 'paid': return 'bg-green-500'
      case 'partial': return 'bg-orange-500'
      case 'unpaid': case 'not_paid': return 'bg-red-500'
      default: return 'bg-yellow-500'
    }
  }, [])

  if (isLoading) {
    return isMobile ? (
      <div className="space-y-1.5">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="rounded-xl border bg-card px-3.5 py-3 space-y-2">
            <div className="flex items-center justify-between">
              <Skeleton className="h-5 w-2/5" />
              <Skeleton className="h-5 w-24" />
            </div>
            <div className="flex items-center justify-between ml-[30px]">
              <Skeleton className="h-4 w-3/5" />
              <Skeleton className="h-4 w-14" />
            </div>
          </div>
        ))}
      </div>
    ) : (
      <Card>
        <CardContent className="p-0">
          <TableSkeleton rows={8} columns={6} showCheckbox />
        </CardContent>
      </Card>
    )
  }

  if (invoices.length === 0) {
    return (
      <EmptyState
        title={isBin ? 'Recycle bin is empty' : 'No invoices found'}
        description={isBin ? 'Deleted invoices will appear here.' : 'Try adjusting your filters or add a new invoice.'}
      />
    )
  }

  if (isMobile) {
    const selectedSet = new Set(selectedIds)
    return (
      <div className="space-y-1.5">
        {invoices.map((inv) => {
          const isSelected = selectedSet.has(inv.id)
          const company = inv.allocations?.[0]?.company
          return (
            <div
              key={inv.id}
              className={cn(
                'rounded-xl border bg-card px-3.5 py-3 active:bg-accent/50 transition-colors',
                isSelected && 'border-primary/50 bg-primary/5',
              )}
              onClick={() => onEdit(inv)}
            >
              {/* Row 1: Checkbox + Supplier + Amount */}
              <div className="flex items-center gap-2.5">
                {selectMode && (
                  <div className="-m-2 p-2" onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      checked={isSelected}
                      onCheckedChange={() => onToggleSelect(inv.id)}
                    />
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <span className="text-[15px] font-semibold leading-tight truncate block">
                    {inv.supplier}
                  </span>
                </div>
                <span className="shrink-0 text-[15px] font-semibold tabular-nums">
                  <CurrencyDisplay value={inv.invoice_value} currency={inv.currency} />
                </span>
              </div>

              {/* Row 2: Invoice meta + Status badge */}
              <div className={cn('flex items-center justify-between mt-1', selectMode && 'ml-[30px]')}>
                <span className="text-[13px] text-muted-foreground truncate">
                  #{inv.invoice_number} · {formatDate(inv.invoice_date)}
                  {company ? ` · ${company}` : ''}
                </span>
                <div className="flex items-center gap-1.5 shrink-0 ml-2">
                  <span className={cn('h-2 w-2 rounded-full shrink-0', paymentDotColor(inv.payment_status))} />
                  <StatusBadge status={inv.status} className="text-[11px] px-1.5 py-0" />
                </div>
              </div>

              {/* Actions — only in bin mode (normal mode: tap = edit) */}
              {isBin && (
                <div className={cn('flex items-center justify-end gap-1 mt-2 border-t pt-2', selectMode && 'ml-[30px]')} onClick={(e) => e.stopPropagation()}>
                  <Button variant="ghost" size="icon" className="h-9 w-9" onClick={() => onRestore(inv.id)}>
                    <RotateCcw className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-9 w-9 text-destructive" onClick={() => onPermanentDelete(inv.id)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              )}
            </div>
          )
        })}
        <p className="text-xs text-muted-foreground pt-1">
          {invoices.length} invoice{invoices.length !== 1 ? 's' : ''}
        </p>
      </div>
    )
  }

  return (
    <Card>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">
                  <Checkbox
                    checked={allSelected ? true : someSelected ? 'indeterminate' : false}
                    onCheckedChange={onSelectAll}
                  />
                </TableHead>
                <TableHead className="w-14">ID</TableHead>
                {activeCols.map((col) => {
                  const isSorted = sort?.key === col.key
                  const handleSort = col.sortable ? () => {
                    if (!isSorted) onSort({ key: col.key, dir: 'asc' })
                    else if (sort.dir === 'asc') onSort({ key: col.key, dir: 'desc' })
                    else onSort(null)
                  } : undefined
                  return (
                    <TableHead
                      key={col.key}
                      className={cn(col.headerClass, col.sortable && 'cursor-pointer select-none')}
                      onClick={handleSort}
                    >
                      <span className="inline-flex items-center gap-1">
                        {col.label}
                        {col.sortable && (
                          isSorted
                            ? sort.dir === 'asc'
                              ? <ArrowUp className="h-3 w-3" />
                              : <ArrowDown className="h-3 w-3" />
                            : <ArrowUpDown className="h-3 w-3 opacity-30" />
                        )}
                      </span>
                    </TableHead>
                  )
                })}
                <TableHead className="w-20">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {invoices.map((inv) => (
                  <InvoiceRow
                    key={inv.id}
                    invoice={inv}
                    isSelected={selectedIds.includes(inv.id)}
                    isExpanded={expandedRow === inv.id}
                    onToggleSelect={onToggleSelect}
                    onToggleExpand={onToggleExpand}
                    onEdit={onEdit}
                    onDelete={onDelete}
                    onRestore={onRestore}
                    onPermanentDelete={onPermanentDelete}
                    isBin={isBin}
                    activeCols={activeCols}
                    colCount={colCount}
                    canEdit={canEdit}
                    canDelete={canDelete}
                  />
              ))}
            </TableBody>
          </Table>
        </div>
        <div className="border-t px-4 py-2 text-xs text-muted-foreground">
          {invoices.length} invoice{invoices.length !== 1 ? 's' : ''}
        </div>
      </CardContent>
    </Card>
  )
}

/* ──── Invoice Row + Allocation Expansion ──── */

const InvoiceRow = memo(function InvoiceRow({
  invoice: inv,
  isSelected,
  isExpanded,
  onToggleSelect,
  onToggleExpand,
  onEdit,
  onDelete,
  onRestore,
  onPermanentDelete,
  isBin,
  activeCols,
  colCount,
  canEdit = true,
  canDelete = true,
}: {
  invoice: Invoice
  isSelected: boolean
  isExpanded: boolean
  onToggleSelect: (id: number) => void
  onToggleExpand: (id: number) => void
  onEdit: (inv: Invoice) => void
  onDelete: (id: number) => void
  onRestore: (id: number) => void
  onPermanentDelete: (id: number) => void
  isBin: boolean
  activeCols: ColumnDef[]
  colCount: number
  canEdit?: boolean
  canDelete?: boolean
}) {
  const queryClient = useQueryClient()
  const hasAllocations = inv.allocations && inv.allocations.length > 0
  const [editingAllocations, setEditingAllocations] = useState(false)

  const storeToDmsMut = useMutation({
    mutationFn: () => invoicesApi.storeToDms([inv.id]),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['invoice-dms-docs', inv.id] })
      if (result.stored > 0) toast.success('Invoice stored to DMS')
      else if (result.skipped > 0) toast.info('Invoice already stored in DMS')
      else toast.error('Failed to store to DMS')
    },
    onError: () => toast.error('Failed to store to DMS'),
  })

  const saveMutation = useMutation({
    mutationFn: (payload: { company: string; rows: import('./AllocationEditor').AllocationRow[] }) =>
      invoicesApi.updateAllocations(inv.id, {
        allocations: rowsToApiPayload(payload.company, payload.rows),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      setEditingAllocations(false)
      toast.success('Allocations updated')
    },
    onError: () => toast.error('Failed to update allocations'),
  })

  const effectiveValue = inv.net_value ?? inv.invoice_value

  return (
    <>
      <TableRow className={cn('cursor-pointer hover:bg-muted/40', isSelected && 'bg-muted/50')} onClick={(e) => {
        const target = e.target as HTMLElement
        if (target.closest('[data-slot="select-trigger"], [data-slot="select-content"], [role="combobox"], [role="option"], [role="listbox"], button, input, [data-radix-collection-item]')) return
        onToggleExpand(inv.id)
      }} aria-expanded={isExpanded}>
        <TableCell onClick={(e) => e.stopPropagation()}>
          <Checkbox checked={isSelected} onCheckedChange={() => onToggleSelect(inv.id)} />
        </TableCell>
        <TableCell>
          <span className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
            {hasAllocations &&
              (isExpanded ? <ChevronDown className="h-3 w-3" aria-hidden="true" /> : <ChevronRight className="h-3 w-3" aria-hidden="true" />)}
            {inv.id}
          </span>
        </TableCell>
        {activeCols.map((col) => (
          <TableCell key={col.key}>
            {col.render(inv)}
          </TableCell>
        ))}
        <TableCell onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center gap-1">
            {isBin ? (
              <>
                <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onRestore(inv.id)} title="Restore">
                  <RotateCcw className="h-3.5 w-3.5" />
                </Button>
                <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => onPermanentDelete(inv.id)} title="Delete permanently">
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </>
            ) : (
              <>
                {canEdit && (
                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onEdit(inv)} title="Edit">
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                )}
                {canEdit && (
                  <Button
                    variant="ghost" size="icon" className="h-7 w-7"
                    onClick={() => storeToDmsMut.mutate()}
                    disabled={storeToDmsMut.isPending}
                    title="Store to DMS"
                  >
                    <FolderArchive className="h-3.5 w-3.5" />
                  </Button>
                )}
                {canDelete && (
                  <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => onDelete(inv.id)} title="Delete">
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                )}
              </>
            )}
          </div>
        </TableCell>
      </TableRow>
      {isExpanded && (hasAllocations || editingAllocations) && (
        <TableRow>
          <TableCell colSpan={colCount} className="p-0">
            <div className={cn('px-8 py-3 border-l-2 shadow-[inset_0_1px_0_0_hsl(var(--border)),inset_0_-1px_0_0_hsl(var(--border))]', statusRowBg[inv.status?.toLowerCase()] || 'bg-muted/50 border-l-primary/50')}>
              {editingAllocations ? (
                <AllocationEditor
                  initialCompany={inv.allocations?.[0]?.company}
                  initialRows={inv.allocations ? allocationsToRows(inv.allocations, effectiveValue) : undefined}
                  effectiveValue={effectiveValue}
                  currency={inv.currency}
                  onSave={(company, rows) => saveMutation.mutate({ company, rows })}
                  onCancel={() => setEditingAllocations(false)}
                  isSaving={saveMutation.isPending}
                  compact
                />
              ) : (
                <>
                  {(() => {
                    const allRows = inv.allocations!.flatMap(a => [a, ...(a.reinvoice_destinations ?? [])])
                    const hasBrand = allRows.some(r => !!(r as Record<string, unknown>).brand)
                    const hasSubdept = allRows.some(r => !!(r as Record<string, unknown>).subdepartment)
                    const hasComment = inv.allocations!.some(a => !!a.comment)
                    return (
                  <table className="text-xs w-full">
                    <thead>
                      <tr className="text-[10px] text-muted-foreground/70 uppercase tracking-wider">
                        <th className="py-1 pr-4 text-left font-medium">Company</th>
                        {hasBrand && <th className="py-1 pr-4 text-left font-medium">Brand</th>}
                        <th className="py-1 pr-4 text-left font-medium">Department</th>
                        {hasSubdept && <th className="py-1 pr-4 text-left font-medium">Sub-dept</th>}
                        <th className="py-1 pr-4 text-right font-medium">Amount</th>
                        <th className="py-1 pr-4 text-right font-medium w-14">%</th>
                        {hasComment && <th className="py-1 text-left font-medium">Comment</th>}
                        <th className="w-7" />
                      </tr>
                    </thead>
                    <tbody>
                      {inv.allocations!.map((alloc, idx) => {
                        const hasReinvoice = alloc.reinvoice_destinations?.length > 0
                        const totalTableRows = inv.allocations!.reduce(
                          (sum, a) => sum + 1 + (a.reinvoice_destinations?.length ?? 0), 0
                        )
                        return (
                        <React.Fragment key={alloc.id}>
                          <tr className={cn('border-t border-border/50', hasReinvoice && 'text-muted-foreground/50')}>
                            <td className="py-1 pr-4">{alloc.company}</td>
                            {hasBrand && <td className="py-1 pr-4">{alloc.brand || '-'}</td>}
                            <td className="py-1 pr-4">{alloc.department}</td>
                            {hasSubdept && <td className="py-1 pr-4">{alloc.subdepartment || '-'}</td>}
                            <td className={cn('py-1 pr-4 text-right tabular-nums', hasReinvoice && 'opacity-40')}>
                              <CurrencyDisplay value={alloc.allocation_value} currency={inv.currency} />
                            </td>
                            <td className="py-1 pr-4 text-right tabular-nums">{alloc.allocation_percent}%</td>
                            {hasComment && (
                            <td className="py-1 text-muted-foreground max-w-[150px] truncate">
                              {alloc.comment ? (
                                <TooltipProvider delayDuration={200}>
                                  <Tooltip>
                                    <TooltipTrigger asChild>
                                      <span className="cursor-default">{alloc.comment}</span>
                                    </TooltipTrigger>
                                    <TooltipContent side="top" className="max-w-[400px] whitespace-pre-wrap">
                                      {alloc.comment}
                                    </TooltipContent>
                                  </Tooltip>
                                </TooltipProvider>
                              ) : ''}
                            </td>
                            )}
                            {idx === 0 && !isBin && (
                              <td rowSpan={totalTableRows} className="py-1 pl-1 align-middle w-7">
                                <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setEditingAllocations(true)}>
                                  <Pencil className="h-3 w-3" />
                                </Button>
                              </td>
                            )}
                          </tr>
                          {hasReinvoice && alloc.reinvoice_destinations.map((rd) => (
                            <tr key={rd.id} className="text-[11px]">
                              <td className="py-0.5 pl-6 pr-4 text-foreground">{rd.company}</td>
                              {hasBrand && <td className="py-0.5 pr-4 text-foreground">{rd.brand || '-'}</td>}
                              <td className="py-0.5 pr-4 text-foreground">{rd.department}</td>
                              {hasSubdept && <td className="py-0.5 pr-4 text-foreground">{rd.subdepartment || '-'}</td>}
                              <td className="py-0.5 pr-4 text-right text-foreground tabular-nums">
                                <CurrencyDisplay value={rd.value} currency={inv.currency} />
                              </td>
                              <td className="py-0.5 pr-4 text-right text-foreground tabular-nums">{rd.percentage}%</td>
                              {hasComment && <td className="py-0.5 text-muted-foreground italic">reinvoiced</td>}
                            </tr>
                          ))}
                        </React.Fragment>
                      )})}
                    </tbody>
                  </table>
                    )
                  })()}
                  <div className="mt-2 flex justify-end">
                    <ApprovalWidget entityType="invoice" entityId={inv.id} compact />
                  </div>

                  {/* ── Linked DMS Documents ── */}
                  <InvoiceLinkedDocs invoiceId={inv.id} isBin={isBin} canEdit={canEdit} />
                </>
              )}
            </div>
          </TableCell>
        </TableRow>
      )}
    </>
  )
})

/* ──── Linked DMS Documents section inside expanded row ──── */

const DMS_STATUS_COLORS: Record<string, string> = {
  draft: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  active: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  archived: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
}

function InvoiceLinkedDocs({ invoiceId, isBin, canEdit }: { invoiceId: number; isBin: boolean; canEdit: boolean }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [linkDialogOpen, setLinkDialogOpen] = useState(false)

  const { data: dmsData } = useQuery({
    queryKey: ['invoice-dms-docs', invoiceId],
    queryFn: () => invoicesApi.getInvoiceDmsDocuments(invoiceId),
  })
  const linkedDocs: InvoiceDmsLink[] = dmsData?.documents ?? []

  const unlinkMut = useMutation({
    mutationFn: (docId: number) => invoicesApi.unlinkDmsDocument(invoiceId, docId),
    onSuccess: () => {
      toast.success('Document unlinked')
      queryClient.invalidateQueries({ queryKey: ['invoice-dms-docs', invoiceId] })
    },
    onError: () => toast.error('Failed to unlink document'),
  })

  return (
    <div className="mt-3 pt-3 border-t border-border/50">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium flex items-center gap-1.5 text-muted-foreground">
          <Link2 className="h-3.5 w-3.5" />
          Linked Documents{linkedDocs.length > 0 && ` (${linkedDocs.length})`}
        </span>
        {!isBin && canEdit && (
          <Button variant="ghost" size="sm" className="h-6 text-[11px] px-2" onClick={() => setLinkDialogOpen(true)}>
            <Link2 className="h-3 w-3 mr-1" />Link
          </Button>
        )}
      </div>

      {linkedDocs.length > 0 && (
        <div className="space-y-1">
          {linkedDocs.map((doc) => (
            <div key={doc.id} className="flex items-center gap-2 text-xs rounded-md border px-2.5 py-1.5 hover:bg-muted/50 group">
              <FileText className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
              <span
                className="font-medium truncate cursor-pointer hover:underline text-blue-600 dark:text-blue-400"
                onClick={() => navigate(`/app/dms/documents/${doc.document_id}`)}
              >
                {doc.title}
              </span>
              {doc.category_name && (
                <Badge variant="outline" className="text-[10px] px-1 py-0 shrink-0" style={{ borderColor: doc.category_color || undefined, color: doc.category_color || undefined }}>
                  {doc.category_name}
                </Badge>
              )}
              <Badge className={cn('text-[10px] px-1 py-0 shrink-0', DMS_STATUS_COLORS[doc.status])}>{doc.status}</Badge>
              {doc.file_count > 0 && (
                <span className="inline-flex items-center gap-0.5 text-muted-foreground shrink-0">
                  <Paperclip className="h-3 w-3" />{doc.file_count}
                </span>
              )}
              <span className="flex-1" />
              {!isBin && canEdit && (
                <Button
                  variant="ghost" size="icon" className="h-5 w-5 opacity-0 group-hover:opacity-100"
                  onClick={() => unlinkMut.mutate(doc.document_id)}
                >
                  <X className="h-3 w-3 text-destructive" />
                </Button>
              )}
            </div>
          ))}
        </div>
      )}

      <InvoiceLinkDocumentDialog
        open={linkDialogOpen}
        onOpenChange={setLinkDialogOpen}
        invoiceId={invoiceId}
        linkedDocIds={linkedDocs.map((d) => d.document_id)}
      />
    </div>
  )
}

/* ──── Link Document Dialog — search and pick DMS documents ──── */

function InvoiceLinkDocumentDialog({
  open,
  onOpenChange,
  invoiceId,
  linkedDocIds,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  invoiceId: number
  linkedDocIds: number[]
}) {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounce(search, 300)

  const { data } = useQuery({
    queryKey: ['invoice-dms-search', debouncedSearch],
    queryFn: () => invoicesApi.searchDmsDocuments(debouncedSearch || undefined),
    enabled: open,
  })
  const results: DmsDocSearchResult[] = data?.documents ?? []

  const linkMut = useMutation({
    mutationFn: (documentId: number) => invoicesApi.linkDmsDocument(invoiceId, documentId),
    onSuccess: () => {
      toast.success('Document linked')
      queryClient.invalidateQueries({ queryKey: ['invoice-dms-docs', invoiceId] })
      queryClient.invalidateQueries({ queryKey: ['invoice-dms-search'] })
    },
    onError: () => toast.error('Failed to link document'),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" aria-describedby={undefined}>
        <DialogHeader><DialogTitle>Link DMS Document</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search documents by title or number..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
              autoFocus
            />
          </div>

          <div className="max-h-[300px] overflow-y-auto space-y-1">
            {results.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">No documents found</p>
            ) : results.map((doc) => {
              const isLinked = linkedDocIds.includes(doc.id)
              return (
                <div
                  key={doc.id}
                  className={cn(
                    'flex items-center gap-3 rounded-md border p-2.5',
                    isLinked ? 'opacity-50' : 'hover:bg-muted/50 cursor-pointer',
                  )}
                  onClick={() => !isLinked && linkMut.mutate(doc.id)}
                >
                  <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium truncate">{doc.title}</div>
                    <div className="text-xs text-muted-foreground flex items-center gap-2">
                      {doc.doc_number && <span>{doc.doc_number}</span>}
                      {doc.category_name && (
                        <Badge variant="outline" className="text-[10px] px-1 py-0" style={{ borderColor: doc.category_color || undefined, color: doc.category_color || undefined }}>
                          {doc.category_name}
                        </Badge>
                      )}
                      <Badge className={cn('text-[10px] px-1 py-0', DMS_STATUS_COLORS[doc.status])}>{doc.status}</Badge>
                      {doc.file_count > 0 && (
                        <span className="inline-flex items-center gap-0.5"><Paperclip className="h-3 w-3" />{doc.file_count}</span>
                      )}
                    </div>
                  </div>
                  {isLinked ? (
                    <span className="text-xs text-muted-foreground">Linked</span>
                  ) : (
                    <Button variant="ghost" size="sm" className="h-7 shrink-0" disabled={linkMut.isPending}>
                      <Link2 className="h-3.5 w-3.5 mr-1" />Link
                    </Button>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
