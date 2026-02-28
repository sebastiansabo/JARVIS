import React, { useState, useMemo, useCallback, memo } from 'react'
import { Link } from 'react-router-dom'
import { useTabParam } from '@/hooks/useTabParam'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  FileText,
  Building2,
  FolderTree,
  Tag,
  Truck,
  Trash2,
  Plus,
  Pencil,
  RotateCcw,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Columns3,
  GripVertical,
  LayoutDashboard,
  Eye,
  EyeOff,
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Checkbox } from '@/components/ui/checkbox'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from '@/components/ui/select'
import { PageHeader } from '@/components/shared/PageHeader'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useDashboardWidgetToggle } from '@/hooks/useDashboardWidgetToggle'
import { StatCard } from '@/components/shared/StatCard'
import { TableSkeleton } from '@/components/shared/TableSkeleton'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { CurrencyDisplay } from '@/components/shared/CurrencyDisplay'
import { SearchInput } from '@/components/shared/SearchInput'
import { FilterBar, type FilterField } from '@/components/shared/FilterBar'
import { DatePresetSelect } from '@/components/shared/DatePresetSelect'
import { EmptyState } from '@/components/shared/EmptyState'
import { MobileCardList, type MobileCardField } from '@/components/shared/MobileCardList'
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
import { cn, usePersistedState } from '@/lib/utils'
import { toast } from 'sonner'
import type { Invoice, InvoiceFilters } from '@/types/invoices'
import { EditInvoiceDialog } from './EditInvoiceDialog'
import { SummaryTable } from './SummaryTable'
import { AllocationEditor, allocationsToRows, rowsToApiPayload } from './AllocationEditor'
import { ApprovalWidget } from '@/components/shared/ApprovalWidget'

type TabKey = 'invoices' | 'company' | 'department' | 'brand' | 'supplier' | 'bin'

const tabs: { key: TabKey; label: string; icon: React.ElementType }[] = [
  { key: 'invoices', label: 'Invoices', icon: FileText },
  { key: 'company', label: 'By Company', icon: Building2 },
  { key: 'department', label: 'By Department', icon: FolderTree },
  { key: 'brand', label: 'By Brand', icon: Tag },
  { key: 'supplier', label: 'By Supplier', icon: Truck },
  { key: 'bin', label: 'Bin', icon: Trash2 },
]

function formatDate(dateStr: string) {
  const d = new Date(dateStr)
  return d.toLocaleDateString('ro-RO', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

export default function Accounting() {
  const queryClient = useQueryClient()
  const isMobile = useIsMobile()
  const { isOnDashboard, toggleDashboardWidget } = useDashboardWidgetToggle('accounting_invoices')
  const [activeTab, setActiveTab] = useTabParam<TabKey>('invoices')
  const [search, setSearch] = useState('')
  const [editInvoice, setEditInvoice] = useState<Invoice | null>(null)
  const [expandedRow, setExpandedRow] = useState<number | null>(null)
  const [deleteIds, setDeleteIds] = useState<number[] | null>(null)
  const [permanentDeleteIds, setPermanentDeleteIds] = useState<number[] | null>(null)
  const [sort, setSort] = usePersistedState<SortState | null>('accounting-sort', null)
  const [filterTagIds, setFilterTagIds] = useState<number[]>([])

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
    enabled: activeTab === 'invoices',
  })

  const { data: binInvoices = [], isLoading: binLoading, isError: binError, refetch: refetchBin } = useQuery({
    queryKey: ['invoices', 'bin'],
    queryFn: () => invoicesApi.getDeletedInvoices(),
    enabled: activeTab === 'bin',
  })

  const { data: companySummary = [] } = useQuery({
    queryKey: ['invoices', 'summary', 'company', filters],
    queryFn: () => invoicesApi.getCompanySummary(filters),
    enabled: activeTab === 'invoices' || activeTab === 'company',
  })

  const { data: departmentSummary = [] } = useQuery({
    queryKey: ['invoices', 'summary', 'department', filters],
    queryFn: () => invoicesApi.getDepartmentSummary(filters),
    enabled: activeTab === 'department',
  })

  const { data: brandSummary = [] } = useQuery({
    queryKey: ['invoices', 'summary', 'brand', filters],
    queryFn: () => invoicesApi.getBrandSummary(filters),
    enabled: activeTab === 'brand',
  })

  const { data: supplierSummary = [] } = useQuery({
    queryKey: ['invoices', 'summary', 'supplier', filters],
    queryFn: () => invoicesApi.getSupplierSummary(filters),
    enabled: activeTab === 'supplier',
  })

  // Entity tags for invoices
  const invoiceIds = useMemo(() => invoices.map((i) => i.id), [invoices])
  const { data: entityTagsMap = {} } = useQuery({
    queryKey: ['entity-tags', 'invoice', invoiceIds],
    queryFn: () => tagsApi.getEntityTagsBulk('invoice', invoiceIds),
    enabled: invoiceIds.length > 0 && activeTab === 'invoices',
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

  const updateFieldMutation = useMutation({
    mutationFn: ({ id, field, value }: { id: number; field: string; value: string }) =>
      invoicesApi.updateInvoice(id, { [field]: value }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['invoices'] }),
    onError: () => toast.error('Failed to update'),
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
  const displayedInvoices = useMemo(() => {
    let list = activeTab === 'bin' ? binInvoices : invoices
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
  }, [invoices, binInvoices, activeTab, search, sort, filterTagIds, entityTagsMap])

  const totalRon = useMemo(
    () => companySummary.reduce((sum, c) => sum + Number(c.total_value_ron ?? 0), 0),
    [companySummary],
  )

  const totalEur = useMemo(
    () => companySummary.reduce((sum, c) => sum + Number(c.total_value_eur ?? 0), 0),
    [companySummary],
  )

  const allSelected = displayedInvoices.length > 0 && selectedInvoiceIds.length === displayedInvoices.length
  const someSelected = selectedInvoiceIds.length > 0 && !allSelected

  const filterFields: FilterField[] = useMemo(() => [
    { key: 'company', label: 'Company', type: 'select' as const, options: companyOptions },
    { key: 'department', label: 'Department', type: 'select' as const, options: departmentOptions },
    { key: 'status', label: 'Status', type: 'select' as const, options: statusOptions },
    { key: 'start_date', label: 'Start Date', type: 'date' as const },
    { key: 'end_date', label: 'End Date', type: 'date' as const },
  ], [companyOptions, departmentOptions, statusOptions])

  const filterValues: Record<string, string> = useMemo(() => ({
    company: filters.company ?? '',
    department: filters.department ?? '',
    status: filters.status ?? '',
    start_date: filters.start_date ?? '',
    end_date: filters.end_date ?? '',
  }), [filters.company, filters.department, filters.status, filters.start_date, filters.end_date])

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
          { label: 'Accounting' },
          { label: tabs.find(t => t.key === activeTab)?.label ?? 'Invoices' },
        ]}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" className="md:size-auto md:px-3" onClick={toggleDashboardWidget}>
              <LayoutDashboard className="h-3.5 w-3.5 md:mr-1.5" />
              <span className="hidden md:inline">{isOnDashboard() ? 'Hide from Dashboard' : 'Show on Dashboard'}</span>
            </Button>
            <Button size="icon" className="md:size-auto md:px-4" asChild>
              <Link to="/app/accounting/add">
                <Plus className="h-4 w-4 md:mr-1.5" />
                <span className="hidden md:inline">New Invoice</span>
              </Link>
            </Button>
          </div>
        }
      />

      {/* Stats row */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatCard
          title="Invoices"
          value={invoices.length}
          icon={<FileText className="h-4 w-4" />}
          isLoading={isLoading}
        />
        <StatCard
          title="Companies"
          value={companySummary.length}
          icon={<Building2 className="h-4 w-4" />}
        />
        <StatCard
          title="Departments"
          value={departmentOptions.length}
          icon={<FolderTree className="h-4 w-4" />}
          isLoading={isLoading}
        />
        <StatCard
          title="Total RON"
          value={new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(totalRon)}
          icon={<span className="text-xs font-bold">RON</span>}
        />
        <StatCard
          title="Total EUR"
          value={new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(totalEur)}
          icon={<span className="text-xs font-bold">EUR</span>}
        />
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={(v) => { setActiveTab(v as TabKey); clearSelected(); setSearch('') }}>
        <div className="-mx-4 overflow-x-auto px-4 md:mx-0 md:overflow-visible md:px-0">
        <TabsList className="w-max md:w-auto">
          {tabs.map((tab) => {
            const Icon = tab.icon
            return (
              <TabsTrigger key={tab.key} value={tab.key}>
                <Icon className="h-3.5 w-3.5" />
                {tab.label}
                {tab.key === 'bin' && binInvoices.length > 0 && (
                  <span className="ml-1 rounded-full bg-destructive px-1.5 py-0.5 text-[10px] text-destructive-foreground">
                    {binInvoices.length}
                  </span>
                )}
              </TabsTrigger>
            )
          })}
        </TabsList>
        </div>
      </Tabs>

      {/* Filter + Search bar */}
      {(activeTab === 'invoices' || activeTab === 'bin') && (
        <div className="flex flex-col gap-2 md:flex-row md:flex-wrap md:items-center">
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder="Search supplier or invoice #..."
            className="w-full md:w-48"
          />
          <div className="flex flex-wrap items-center gap-2">
            <FilterBar fields={filterFields} values={filterValues} onChange={handleFilterChange} />
            <DatePresetSelect
              startDate={filters.start_date ?? ''}
              endDate={filters.end_date ?? ''}
              onChange={(s, e) => handleFilterChange({ ...filterValues, start_date: s, end_date: e })}
            />
            <TagFilter selectedTagIds={filterTagIds} onChange={setFilterTagIds} />
          </div>
          {!isMobile && (
            <div className="ml-auto flex items-center gap-2">
              <ColumnToggle visibleColumns={visibleColumns} onChange={setVisibleColumns} />
            </div>
          )}
        </div>
      )}

      {/* Bulk action bar */}
      {selectedInvoiceIds.length > 0 && (
        <div className="flex items-center gap-2 rounded-lg border bg-muted/50 px-4 py-2">
          <span className="text-sm font-medium">{selectedInvoiceIds.length} selected</span>
          <div className="flex-1" />
          {activeTab === 'invoices' && (
            <>
              <TagPickerButton
                entityType="invoice"
                entityIds={selectedInvoiceIds}
                onTagsChanged={() => queryClient.invalidateQueries({ queryKey: ['entity-tags'] })}
              />
              <Button variant="destructive" size="sm" onClick={() => setDeleteIds(selectedInvoiceIds)}>
                <Trash2 className="mr-1 h-3.5 w-3.5" />
                Delete
              </Button>
            </>
          )}
          {activeTab === 'bin' && (
            <>
              <Button variant="outline" size="sm" onClick={() => restoreMutation.mutate(selectedInvoiceIds)}>
                <RotateCcw className="mr-1 h-3.5 w-3.5" />
                Restore
              </Button>
              <Button variant="destructive" size="sm" onClick={() => setPermanentDeleteIds(selectedInvoiceIds)}>
                <Trash2 className="mr-1 h-3.5 w-3.5" />
                Permanent Delete
              </Button>
            </>
          )}
          <Button variant="ghost" size="sm" onClick={clearSelected}>
            Cancel
          </Button>
        </div>
      )}

      {/* Tab content */}
      {(activeTab === 'invoices' && invoicesError) || (activeTab === 'bin' && binError) ? (
        <QueryError
          message={activeTab === 'bin' ? 'Failed to load recycle bin' : 'Failed to load invoices'}
          onRetry={() => (activeTab === 'bin' ? refetchBin() : refetchInvoices())}
        />
      ) : activeTab === 'invoices' || activeTab === 'bin' ? (
        <InvoiceTable
          invoices={displayedInvoices}
          isLoading={activeTab === 'bin' ? binLoading : isLoading}
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
          isBin={activeTab === 'bin'}
          activeCols={activeCols}
          sort={sort}
          onSort={setSort}
          isMobile={isMobile}
        />
      ) : activeTab === 'company' ? (
        <SummaryTable data={companySummary} nameKey="company" label="Company" />
      ) : activeTab === 'department' ? (
        <SummaryTable data={departmentSummary} nameKey="department" label="Department" />
      ) : activeTab === 'brand' ? (
        <SummaryTable data={brandSummary} nameKey="brand" label="Brand" />
      ) : activeTab === 'supplier' ? (
        <SummaryTable data={supplierSummary} nameKey="supplier" label="Supplier" />
      ) : null}

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
}) {
  const colCount = 2 + activeCols.length + 1 // checkbox + ID + visible cols + actions

  // Mobile card fields for invoice cards
  const mobileFields: MobileCardField<Invoice>[] = useMemo(() => [
    {
      key: 'supplier', label: 'Supplier', isPrimary: true,
      render: (inv) => <span className="font-medium">{inv.supplier}</span>,
    },
    {
      key: 'meta', label: 'Invoice', isSecondary: true,
      render: (inv) => (
        <span className="flex items-center gap-2">
          <span>#{inv.invoice_number}</span>
          <span>{formatDate(inv.invoice_date)}</span>
        </span>
      ),
    },
    {
      key: 'value', label: 'Total',
      render: (inv) => <CurrencyDisplay value={inv.invoice_value} currency={inv.currency} />,
    },
    {
      key: 'status', label: 'Status',
      render: (inv) => <StatusBadge status={inv.status} />,
    },
    {
      key: 'payment', label: 'Payment',
      render: (inv) => <StatusBadge status={inv.payment_status} />,
    },
    {
      key: 'company', label: 'Company', expandOnly: true,
      render: (inv) => <span className="text-xs">{inv.allocations?.[0]?.company ?? '—'}</span>,
    },
    {
      key: 'department', label: 'Department', expandOnly: true,
      render: (inv) => <span className="text-xs">{inv.allocations?.[0]?.department ?? '—'}</span>,
    },
  ], [])

  if (isLoading) {
    return isMobile ? (
      <MobileCardList data={[]} fields={mobileFields} getRowId={() => 0} isLoading />
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
    return (
      <>
        <MobileCardList
          data={invoices}
          fields={mobileFields}
          getRowId={(inv) => inv.id}
          onRowClick={(inv) => onEdit(inv)}
          selectable
          selectedIds={selectedIds}
          onToggleSelect={onToggleSelect}
          actions={(inv) => (
            <div className="flex items-center gap-1">
              {isBin ? (
                <>
                  <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => onRestore(inv.id)}>
                    <RotateCcw className="h-3.5 w-3.5" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={() => onPermanentDelete(inv.id)}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </>
              ) : (
                <>
                  <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => onEdit(inv)}>
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={() => onDelete(inv.id)}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </>
              )}
            </div>
          )}
        />
        <div className="text-xs text-muted-foreground">
          {invoices.length} invoice{invoices.length !== 1 ? 's' : ''}
        </div>
      </>
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
}) {
  const queryClient = useQueryClient()
  const hasAllocations = inv.allocations && inv.allocations.length > 0
  const [editingAllocations, setEditingAllocations] = useState(false)

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
      <TableRow className={cn('cursor-pointer hover:bg-muted/40', isSelected && 'bg-muted/50')} onClick={() => onToggleExpand(inv.id)} aria-expanded={isExpanded}>
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
          <TableCell
            key={col.key}
            onClick={col.key === 'status' || col.key === 'payment_status' || col.key === 'tags' ? (e) => e.stopPropagation() : undefined}
          >
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
                <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onEdit(inv)} title="Edit">
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
                <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => onDelete(inv.id)} title="Delete">
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </>
            )}
          </div>
        </TableCell>
      </TableRow>
      {isExpanded && (hasAllocations || editingAllocations) && (
        <TableRow className="bg-muted/30">
          <TableCell colSpan={colCount} className="p-0">
            <div className="px-8 py-3">
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
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-xs font-medium text-muted-foreground">Allocations</span>
                    {!isBin && (
                      <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setEditingAllocations(true)}>
                        <Pencil className="mr-1 h-3 w-3" />
                        Edit
                      </Button>
                    )}
                  </div>
                  <table className="w-full text-xs border-separate border-spacing-x-3 border-spacing-y-0">
                    <thead>
                      <tr className="text-muted-foreground">
                        <th className="pb-1 text-left font-medium">Company</th>
                        <th className="pb-1 text-left font-medium">Brand</th>
                        <th className="pb-1 text-left font-medium">Department</th>
                        <th className="pb-1 text-left font-medium">Subdepartment</th>
                        <th className="pb-1 text-right font-medium">%</th>
                        <th className="pb-1 text-right font-medium">Value</th>
                        <th className="pb-1 text-left font-medium">Responsible</th>
                        <th className="pb-1 text-left font-medium">Comment</th>
                      </tr>
                    </thead>
                    <tbody>
                      {inv.allocations!.map((alloc) => {
                        const hasReinvoice = alloc.reinvoice_destinations?.length > 0
                        return (
                        <React.Fragment key={alloc.id}>
                          <tr className={cn('border-t border-border/50', hasReinvoice && 'text-muted-foreground/50')}>
                            <td className="py-1">{alloc.company}</td>
                            <td className="py-1">{alloc.brand || '-'}</td>
                            <td className="py-1">{alloc.department}</td>
                            <td className="py-1">{alloc.subdepartment || '-'}</td>
                            <td className="py-1 text-right">{alloc.allocation_percent}%</td>
                            <td className={cn('py-1 text-right', hasReinvoice && 'opacity-40')}>
                              <CurrencyDisplay value={alloc.allocation_value} currency={inv.currency} />
                            </td>
                            <td className="py-1">{alloc.responsible || '-'}</td>
                            <td className="py-1 text-muted-foreground max-w-[150px] truncate">{alloc.comment || ''}</td>
                          </tr>
                          {hasReinvoice && alloc.reinvoice_destinations.map((rd) => (
                            <tr key={rd.id} className="text-[11px]">
                              <td className="py-0.5 pl-6 text-foreground">{rd.company}</td>
                              <td className="py-0.5 text-foreground">{rd.brand || '-'}</td>
                              <td className="py-0.5 text-foreground">{rd.department}</td>
                              <td className="py-0.5 text-foreground">{rd.subdepartment || '-'}</td>
                              <td className="py-0.5 text-right text-foreground">{rd.percentage}%</td>
                              <td className="py-0.5 text-right text-foreground">
                                <CurrencyDisplay value={rd.value} currency={inv.currency} />
                              </td>
                              <td colSpan={2} className="py-0.5 text-muted-foreground italic">reinvoiced</td>
                            </tr>
                          ))}
                        </React.Fragment>
                      )})}
                    </tbody>
                  </table>
                  <div className="mt-3 border-t pt-3">
                    <ApprovalWidget entityType="invoice" entityId={inv.id} compact />
                  </div>
                </>
              )}
            </div>
          </TableCell>
        </TableRow>
      )}
    </>
  )
})
