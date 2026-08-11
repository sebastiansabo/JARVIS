import { useCallback, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowUpDown,
  Car,
  BookmarkCheck,
  TrendingUp,
  PackageCheck,
  Clock,
  AlertTriangle,
  DollarSign,
  Paperclip,
  FileSpreadsheet,
} from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { SearchInput } from '@/components/shared/SearchInput'
import { FilterBar, type FilterField } from '@/components/shared/FilterBar'
import { StatCard } from '@/components/shared/StatCard'
import { EmptyState } from '@/components/shared/EmptyState'
import { TableSkeleton } from '@/components/shared/TableSkeleton'
import { CurrencyDisplay } from '@/components/shared/CurrencyDisplay'
import { ColumnToggle, useColumnState, type ColumnDef } from '@/components/shared/ColumnToggle'
import { ResponsiveDataView } from '@/components/shared/ResponsiveDataView'
import type { MobileCardField } from '@/components/shared/MobileCardList'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { DateField } from '@/components/ui/date-field'
import { DispoRowActions } from './DispoRowActions'
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from '@/components/ui/pagination'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useAuthStore } from '@/stores/authStore'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { cn } from '@/lib/utils'
import { carparkDispoApi } from '@/api/carparkDispo'
import { carparkApi } from '@/api/carpark'
import { usersApi } from '@/api/users'
import { settingsApi } from '@/api/settings'
import { ClientSearchSelect } from '@/components/shared/ClientSearchSelect'
import {
  DISPO_STAGES,
  type DispoRow,
  type DispoFilters,
  type VehicleStatus,
} from '@/types/carpark'
import { DispoStatusBadge } from './DispoStatusBadge'
import { EditableCell, type EditableCellOption } from './EditableCell'
import { StatusEditCell } from './StatusEditCell'
import { useDispoInlineSave } from './dispoInlineEdit'

function Muted() {
  return <span className="text-muted-foreground">—</span>
}

// Sale-type literals in current use (types/carpark.ts's SaleType comment) — a
// static list keeps the filter selectable even before any row using a given
// type has loaded on the current page.
const SALE_TYPE_OPTIONS = ['PLR', 'CASH', 'CREDIT PLR', 'BT LEASING', 'BRD', 'BCR', 'AW NEXT']

const STOCK_REMOVED_OPTIONS = [
  { value: 'false', label: 'Activ (nescos)' },
  { value: 'true', label: 'Scos din evidență' },
]

// Backend sort whitelist (DispoRepository._SORTABLE_COLUMNS) — column keys
// below are named to match these 1:1 so a click can pass the key straight
// through as `sort_by`.
const SORTABLE_KEYS = new Set([
  'acquisition_date', 'sale_date', 'listing_date', 'delivery_date',
  'days_in_stock', 'gross_margin', 'current_price', 'sale_price',
  'acquisition_price', 'brand', 'model', 'status', 'vin', 'created_at',
])

// Stages that are no longer "in the pipeline" for aging purposes — a sold,
// delivered, or exited vehicle stops accumulating stock-aging risk.
const SOLD_OR_EXITED_STATUSES = new Set<VehicleStatus>(
  DISPO_STAGES.filter((s) => s.key === 'vandut' || s.key === 'livrat' || s.key === 'iesit').flatMap(
    (s) => s.statuses,
  ),
)

function agingClass(days: number, status: VehicleStatus): string {
  if (SOLD_OR_EXITED_STATUSES.has(status)) return ''
  if (days > 90) return 'text-red-800 dark:text-red-300 font-semibold'
  if (days > 60) return 'text-red-600 dark:text-red-400 font-medium'
  if (days >= 30) return 'text-amber-600 dark:text-amber-500'
  return 'text-green-600 dark:text-green-500'
}

function fmtDate(d: string | null | undefined): string {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ro-RO')
}

// KPI-strip aggregates are shown in € (matches the sibling CarPark Dashboard
// page's own convention for aggregate figures — DispoKpis carries no
// per-value currency, unlike DispoRow's individual money columns which fall
// back to CurrencyDisplay's RON default).
function fmtKpiCurrency(val: number | null | undefined): string {
  if (val == null) return '—'
  return `${new Intl.NumberFormat('ro-RO', { maximumFractionDigits: 0 }).format(val)} €`
}

// `editable` wires each flag badge through EditableCell(type='flag') so a
// click toggles + saves that single boolean; the missingPvLivrare paperclip
// stays a computed, non-interactive indicator either way. Mobile card usage
// (mobileFields below) omits `editable`, keeping it read-only there.
function FlagsCell({ row, editable = false }: { row: DispoRow; editable?: boolean }) {
  const missingPvLivrare =
    (row.status === 'SOLD' || row.status === 'DELIVERED') && !row.doc_types.includes('pv_livrare')

  if (!editable) {
    if (!row.is_impus && !row.missing_civ && !row.stock_removed && !missingPvLivrare) return <Muted />
    return (
      <div className="flex flex-wrap items-center gap-1">
        {row.is_impus && (
          <Badge variant="destructive" className="text-[10px] font-normal">
            IMPUS
          </Badge>
        )}
        {row.missing_civ && (
          <Badge variant="outline" className="text-[10px] font-normal border-amber-500 text-amber-600 dark:text-amber-400">
            LIPSĂ CIV
          </Badge>
        )}
        {row.stock_removed && (
          <Badge variant="secondary" className="text-[10px] font-normal">
            SCOS
          </Badge>
        )}
        {missingPvLivrare && (
          <span title="Lipsă PV livrare" className="inline-flex text-red-600 dark:text-red-400">
            <Paperclip className="h-3.5 w-3.5" />
          </span>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-wrap items-center gap-1" onClick={(e) => e.stopPropagation()}>
      <EditableCell
        row={row}
        field="is_impus"
        type="flag"
        value={row.is_impus}
        editable
        display={(v) => (
          <Badge
            variant={v ? 'destructive' : 'outline'}
            className={cn('text-[10px] font-normal', !v && 'border-dashed text-muted-foreground/50')}
          >
            IMPUS
          </Badge>
        )}
      />
      <EditableCell
        row={row}
        field="missing_civ"
        type="flag"
        value={row.missing_civ}
        editable
        display={(v) => (
          <Badge
            variant="outline"
            className={cn(
              'text-[10px] font-normal',
              v ? 'border-amber-500 text-amber-600 dark:text-amber-400' : 'border-dashed text-muted-foreground/50',
            )}
          >
            LIPSĂ CIV
          </Badge>
        )}
      />
      <EditableCell
        row={row}
        field="stock_removed"
        type="flag"
        value={row.stock_removed}
        editable
        display={(v) => (
          <Badge
            variant={v ? 'secondary' : 'outline'}
            className={cn('text-[10px] font-normal', !v && 'border-dashed text-muted-foreground/50')}
          >
            SCOS
          </Badge>
        )}
      />
      {missingPvLivrare && (
        <span title="Lipsă PV livrare" className="inline-flex text-red-600 dark:text-red-400">
          <Paperclip className="h-3.5 w-3.5" />
        </span>
      )}
    </div>
  )
}

// Client cell: async CRM search over buyer_name + buyer_client_id together.
// Bypasses EditableCell's generic single-field flow (its runSave always
// patches exactly one `field`) and drives useDispoInlineSave directly —
// its patch/revert/request triple is field-count-agnostic, so a two-key
// Partial<DispoRow> patch works exactly like EditableCell's one-key ones.
function ClientCell({ row, editable }: { row: DispoRow; editable: boolean }) {
  const [editing, setEditing] = useState(false)
  const save = useDispoInlineSave(row.id)

  const displayName = row.buyer_name ?? row.reservation_client_name ?? null

  if (!editable) return <>{displayName ?? <Muted />}</>

  if (!editing) {
    return (
      <span
        onClick={(e) => {
          e.stopPropagation()
          setEditing(true)
        }}
        className="block cursor-text rounded-sm px-0.5 -mx-0.5 hover:bg-accent/60"
      >
        {displayName ?? <Muted />}
      </span>
    )
  }

  return (
    <div onClick={(e) => e.stopPropagation()} className="min-w-[12rem]">
      <ClientSearchSelect
        value={{ id: row.buyer_client_id, name: row.buyer_name }}
        companyId={row.company_id ?? undefined}
        open
        onOpenChange={(o) => {
          if (!o) setEditing(false)
        }}
        onSelect={(client) => {
          setEditing(false)
          if (client.id === row.buyer_client_id && client.name === (row.buyer_name ?? '')) return
          const patch: Partial<DispoRow> = { buyer_client_id: client.id, buyer_name: client.name }
          const revert: Partial<DispoRow> = { buyer_client_id: row.buyer_client_id, buyer_name: row.buyer_name }
          void save({
            patch,
            revert,
            request: () => carparkApi.updateVehicle(row.id, { buyer_client_id: client.id, buyer_name: client.name }),
            errorFallback: 'Eroare la salvare',
          })
        }}
      />
    </div>
  )
}

// ── Dispo workspace page ──────────────────────────────────────
export default function CarParkDispo() {
  const navigate = useNavigate()
  const isMobile = useIsMobile()
  const user = useAuthStore((s) => s.user)
  const canViewFinance = !!user?.can_view_carpark_finance
  const canEdit = !!user?.can_edit_carpark

  const [searchParams, setSearchParams] = useSearchParams()
  const activeStage = searchParams.get('stage') || ''

  const [filterValues, setFilterValues] = useState<Record<string, string>>({
    brand: '',
    location_id: '',
    salesperson_user_id: '',
    source: '',
    sale_type: '',
    stock_removed: '',
  })
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)
  const [sortBy, setSortBy] = useState('acquisition_date')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  const setActiveStage = useCallback(
    (stage: string) => {
      const params: Record<string, string> = {}
      if (stage) params.stage = stage
      setSearchParams(params, { replace: true })
      setPage(1)
    },
    [setSearchParams],
  )

  const handleFilterChange = useCallback((values: Record<string, string>) => {
    setFilterValues(values)
    setPage(1)
  }, [])

  const handleSearch = useCallback((value: string) => {
    setSearch(value)
    setPage(1)
  }, [])

  const handleDateChange = useCallback((start: string, end: string) => {
    setDateFrom(start)
    setDateTo(end)
    setPage(1)
  }, [])

  const handleSort = useCallback(
    (key: string) => {
      if (sortBy === key) {
        setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
      } else {
        setSortBy(key)
        setSortDir('asc')
      }
    },
    [sortBy],
  )

  const handleRowClick = useCallback((row: DispoRow) => navigate(`/app/carpark/${row.id}`), [navigate])

  // ── Filters passed to the API ───────────────────────────
  const activeFilters: DispoFilters = useMemo(() => {
    const f: DispoFilters = {}
    if (activeStage) f.stage = activeStage
    if (filterValues.brand) f.brand = filterValues.brand
    if (filterValues.location_id) f.location_id = filterValues.location_id
    if (filterValues.salesperson_user_id) f.salesperson_user_id = filterValues.salesperson_user_id
    if (filterValues.source) f.source = filterValues.source
    if (filterValues.sale_type) f.sale_type = filterValues.sale_type
    if (filterValues.stock_removed) f.stock_removed = filterValues.stock_removed === 'true'
    if (dateFrom) f.date_from = dateFrom
    if (dateTo) f.date_to = dateTo
    if (search) f.search = search
    return f
  }, [activeStage, filterValues, dateFrom, dateTo, search])

  // ── Data fetching ────────────────────────────────────────
  const { data: summaryData, isLoading: summaryLoading } = useQuery({
    queryKey: ['carpark', 'dispo', 'summary', activeFilters, page, perPage, sortBy, sortDir],
    queryFn: () => carparkDispoApi.getSummary(activeFilters, page, perPage, sortBy, sortDir),
  })

  const { data: kpisData, isLoading: kpisLoading } = useQuery({
    queryKey: ['carpark', 'dispo', 'kpis'],
    queryFn: () => carparkDispoApi.getKpis(),
    staleTime: 30_000,
  })

  const { data: filterOptions } = useQuery({
    queryKey: ['carpark', 'filter-options'],
    queryFn: () => carparkApi.getFilterOptions(),
    staleTime: 60_000,
  })

  const { data: locationsData } = useQuery({
    queryKey: ['carpark', 'locations'],
    queryFn: () => carparkApi.getLocations(),
    staleTime: 60_000,
  })

  const { data: usersData } = useQuery({
    queryKey: ['users-list'],
    queryFn: () => usersApi.getUsers(),
    staleTime: 5 * 60_000,
  })

  // Canonical dropdown_options lists (settings/dropdowns — seeded per
  // dropdown_type in schema_carpark.py) back the source/sale_type inline
  // edit selects, unlike the filter bar's page-scoped sourceOptions below.
  const { data: sourceDropdown } = useQuery({
    queryKey: ['dropdown-options', 'carpark_source'],
    queryFn: () => settingsApi.getDropdownOptions('carpark_source'),
    staleTime: 5 * 60_000,
    enabled: canEdit,
  })

  const { data: saleTypeDropdown } = useQuery({
    queryKey: ['dropdown-options', 'carpark_sale_type'],
    queryFn: () => settingsApi.getDropdownOptions('carpark_sale_type'),
    staleTime: 5 * 60_000,
    enabled: canEdit,
  })

  const sourceEditOptions: EditableCellOption[] = useMemo(
    () => (sourceDropdown ?? []).filter((o) => o.is_active).map((o) => ({ value: o.value, label: o.label })),
    [sourceDropdown],
  )

  const saleTypeEditOptions: EditableCellOption[] = useMemo(
    () => (saleTypeDropdown ?? []).filter((o) => o.is_active).map((o) => ({ value: o.value, label: o.label })),
    [saleTypeDropdown],
  )

  const userNameMap = useMemo(() => {
    const m = new Map<number, string>()
    for (const u of usersData ?? []) m.set(u.id, u.name)
    return m
  }, [usersData])

  const userEditOptions: EditableCellOption[] = useMemo(
    () =>
      (usersData ?? [])
        .map((u) => ({ value: String(u.id), label: u.name }))
        .sort((a, b) => a.label.localeCompare(b.label)),
    [usersData],
  )

  const rows = summaryData?.rows ?? []
  const total = summaryData?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / perPage))
  const stageCounts = summaryData?.stage_counts

  // ── Filter field definitions ────────────────────────────
  // Source options are derived from the currently loaded page ("select from
  // summary" per the brief) rather than a dedicated options endpoint — a
  // deliberate simplification; picking a rare source may temporarily narrow
  // the list to itself.
  const sourceOptions = useMemo(() => {
    const set = new Set<string>()
    for (const r of rows) if (r.source) set.add(r.source)
    return Array.from(set)
      .sort()
      .map((s) => ({ value: s, label: s }))
  }, [rows])

  const filterFields: FilterField[] = useMemo(
    () => [
      {
        key: 'brand',
        label: 'Marcă',
        type: 'select' as const,
        options: (filterOptions?.brands ?? []).map((b) => ({ value: b, label: b })),
      },
      {
        key: 'location_id',
        label: 'Locație',
        type: 'select' as const,
        options: (locationsData?.locations ?? []).map((l) => ({ value: String(l.id), label: l.name })),
      },
      {
        key: 'salesperson_user_id',
        label: 'Vânzător',
        type: 'select' as const,
        options: (usersData ?? [])
          .map((u) => ({ value: String(u.id), label: u.name }))
          .sort((a, b) => a.label.localeCompare(b.label)),
      },
      { key: 'source', label: 'Furnizor', type: 'select' as const, options: sourceOptions },
      {
        key: 'sale_type',
        label: 'Tip vânzare',
        type: 'select' as const,
        options: SALE_TYPE_OPTIONS.map((s) => ({ value: s, label: s })),
      },
      {
        key: 'stock_removed',
        label: 'Scos din evidență',
        type: 'select' as const,
        options: STOCK_REMOVED_OPTIONS,
      },
    ],
    [filterOptions, locationsData, usersData, sourceOptions],
  )

  // ── Column definitions (centralizator order) ────────────
  // Editable columns route through EditableCell/StatusEditCell (click →
  // input → Enter/blur saves, Escape cancels; see EditableCell.tsx). Each
  // `display` callback reproduces that column's exact prior read-only
  // markup, so a non-editing/non-`canEdit` viewer sees byte-for-byte the
  // same cell as before this feature. days_in_stock/total_costs/
  // gross_margin/margin_pct/vin stay plain renders — all computed, never
  // editable.
  const columnDefs: ColumnDef<DispoRow>[] = useMemo(() => {
    const cols: ColumnDef<DispoRow>[] = [
      {
        key: 'brand',
        label: 'Marca',
        className: 'font-medium whitespace-nowrap',
        render: (r) => (
          <EditableCell row={r} field="brand" type="text" value={r.brand} editable={canEdit} display={(v) => (v as string) || r.brand} />
        ),
      },
      {
        key: 'model',
        label: 'Model',
        className: 'whitespace-nowrap',
        render: (r) => (
          <EditableCell
            row={r}
            field="model"
            type="text"
            value={r.model}
            editable={canEdit}
            display={(v) => (
              <>
                {(v as string) || r.model}
                {r.variant && <span className="ml-1 text-xs text-muted-foreground">{r.variant}</span>}
              </>
            )}
          />
        ),
      },
      {
        key: 'vin',
        label: 'VIN',
        className: 'font-mono text-xs whitespace-nowrap',
        render: (r) => <span title={r.vin}>{r.vin.slice(-6)}</span>,
      },
      { key: 'status', label: 'Status', render: (r) => <StatusEditCell row={r} editable={canEdit} /> },
      {
        key: 'source',
        label: 'Furnizor',
        className: 'text-sm',
        render: (r) => (
          <EditableCell
            row={r}
            field="source"
            type="select"
            value={r.source}
            editable={canEdit}
            options={sourceEditOptions}
            display={(v) => (v ? String(v) : <Muted />)}
          />
        ),
      },
      {
        key: 'location',
        label: 'Locație',
        className: 'text-sm',
        render: (r) => (
          <EditableCell
            row={r}
            field="location_text"
            type="text"
            value={r.location_text}
            editable={canEdit}
            display={(v) => (v ? String(v) : <Muted />)}
          />
        ),
      },
      {
        key: 'acquisition_date',
        label: 'Data achiziție',
        className: 'whitespace-nowrap text-sm tabular-nums',
        render: (r) => (
          <EditableCell
            row={r}
            field="acquisition_date"
            type="date"
            value={r.acquisition_date}
            editable={canEdit}
            display={(v) => fmtDate(v as string | null)}
          />
        ),
      },
      {
        key: 'supplier_payment_date',
        label: 'Data plată',
        className: 'whitespace-nowrap text-sm tabular-nums',
        render: (r) => (
          <EditableCell
            row={r}
            field="supplier_payment_date"
            type="date"
            value={r.supplier_payment_date}
            editable={canEdit}
            display={(v) => fmtDate(v as string | null)}
          />
        ),
      },
      {
        key: 'listing_date',
        label: 'Data promovare',
        className: 'whitespace-nowrap text-sm tabular-nums',
        render: (r) => (
          <EditableCell
            row={r}
            field="listing_date"
            type="date"
            value={r.listing_date}
            editable={canEdit}
            display={(v) => fmtDate(v as string | null)}
          />
        ),
      },
      {
        key: 'days_in_stock',
        label: 'Zile în stoc',
        className: 'text-right tabular-nums',
        render: (r) => <span className={agingClass(r.days_in_stock, r.status)}>{r.days_in_stock}</span>,
      },
      ...(canViewFinance
        ? ([
            {
              key: 'acquisition_price',
              label: 'Preț achiziție',
              className: 'text-right tabular-nums',
              render: (r) => (
                <EditableCell
                  row={r}
                  field="acquisition_price"
                  type="money"
                  value={r.acquisition_price ?? null}
                  editable={canEdit}
                  display={(v) => (v != null ? <CurrencyDisplay value={v as number} /> : <Muted />)}
                />
              ),
            },
            {
              key: 'total_costs',
              label: 'Total costuri',
              className: 'text-right tabular-nums',
              render: (r) => (r.total_costs != null ? <CurrencyDisplay value={r.total_costs} /> : <Muted />),
            },
          ] as ColumnDef<DispoRow>[])
        : []),
      {
        key: 'sale_price',
        label: 'Preț vânzare',
        className: 'text-right tabular-nums',
        render: (r) => (
          <EditableCell
            row={r}
            field="sale_price"
            type="money"
            value={r.sale_price}
            editable={canEdit}
            display={(v) => (v != null ? <CurrencyDisplay value={v as number} /> : <Muted />)}
          />
        ),
      },
      ...(canViewFinance
        ? ([
            {
              key: 'gross_margin',
              label: 'Marjă brută',
              className: 'text-right tabular-nums',
              render: (r) => (r.gross_margin != null ? <CurrencyDisplay value={r.gross_margin} /> : <Muted />),
            },
            {
              key: 'margin_pct',
              label: 'Marjă %',
              className: 'text-right tabular-nums',
              render: (r) =>
                r.margin_pct != null ? (
                  <span className={r.margin_pct < 0 ? 'text-red-600 dark:text-red-400 font-medium' : ''}>
                    {r.margin_pct.toFixed(1)}%
                  </span>
                ) : (
                  <Muted />
                ),
            },
          ] as ColumnDef<DispoRow>[])
        : []),
      {
        key: 'sale_type',
        label: 'Tip vânzare',
        className: 'text-sm whitespace-nowrap',
        render: (r) => (
          <EditableCell
            row={r}
            field="sale_type"
            type="select"
            value={r.sale_type}
            editable={canEdit}
            options={saleTypeEditOptions}
            display={(v) => (v ? String(v) : <Muted />)}
          />
        ),
      },
      {
        key: 'client',
        label: 'Client',
        className: 'text-sm',
        render: (r) => <ClientCell row={r} editable={canEdit} />,
      },
      {
        key: 'salesperson',
        label: 'Vânzător',
        className: 'text-sm whitespace-nowrap',
        render: (r) => (
          <EditableCell
            row={r}
            field="salesperson_user_id"
            type="user"
            value={r.salesperson_user_id}
            editable={canEdit}
            options={userEditOptions}
            display={(v) => (v != null ? (userNameMap.get(v as number) ?? `#${v}`) : <Muted />)}
          />
        ),
      },
      {
        key: 'acquisition_manager',
        label: 'Achizitor',
        className: 'text-sm whitespace-nowrap',
        render: (r) => (
          <EditableCell
            row={r}
            field="acquisition_manager_id"
            type="user"
            value={r.acquisition_manager_id}
            editable={canEdit}
            options={userEditOptions}
            display={(v) => (v != null ? (userNameMap.get(v as number) ?? `#${v}`) : <Muted />)}
          />
        ),
      },
      {
        key: 'gw_file_number',
        label: 'Dosar GW',
        className: 'text-sm whitespace-nowrap',
        render: (r) => (
          <EditableCell
            row={r}
            field="gw_file_number"
            type="text"
            value={r.gw_file_number}
            editable={canEdit}
            display={(v) => (v as string) || <Muted />}
          />
        ),
      },
      {
        key: 'sale_date',
        label: 'Data vânzării',
        className: 'whitespace-nowrap text-sm tabular-nums',
        render: (r) => (
          <EditableCell
            row={r}
            field="sale_date"
            type="date"
            value={r.sale_date}
            editable={canEdit}
            display={(v) => fmtDate(v as string | null)}
          />
        ),
      },
      {
        key: 'delivery_date',
        label: 'Data livrării',
        className: 'whitespace-nowrap text-sm tabular-nums',
        render: (r) => (
          <EditableCell
            row={r}
            field="delivery_date"
            type="date"
            value={r.delivery_date}
            editable={canEdit}
            display={(v) => fmtDate(v as string | null)}
          />
        ),
      },
      { key: 'flags', label: 'Flags', render: (r) => <FlagsCell row={r} editable={canEdit} /> },
    ]
    return cols
  }, [canViewFinance, canEdit, userNameMap, sourceEditOptions, saleTypeEditOptions, userEditOptions])

  const defaultVisible = useMemo(() => columnDefs.map((c) => c.key), [columnDefs])

  const { visibleColumns, setVisibleColumns, defaultColumns } = useColumnState(
    'carpark-dispo-columns',
    defaultVisible,
    columnDefs.map((c) => c.key),
  )

  // ── Mobile card fields ───────────────────────────────────
  const mobileFields: MobileCardField<DispoRow>[] = useMemo(
    () => [
      { key: 'vehicle', label: 'Vehicul', isPrimary: true, render: (r) => `${r.brand} ${r.model}` },
      {
        key: 'price',
        label: 'Preț',
        isPrimary: true,
        alignRight: true,
        render: (r) =>
          r.sale_price != null ? (
            <CurrencyDisplay value={r.sale_price} />
          ) : r.current_price != null ? (
            <CurrencyDisplay value={r.current_price} />
          ) : (
            <Muted />
          ),
      },
      { key: 'vin', label: 'VIN', isSecondary: true, render: (r) => <span className="font-mono">{r.vin.slice(-6)}</span> },
      { key: 'status', label: 'Status', isSecondary: true, render: (r) => <DispoStatusBadge status={r.status} /> },
      {
        key: 'days',
        label: 'Zile în stoc',
        render: (r) => <span className={agingClass(r.days_in_stock, r.status)}>{r.days_in_stock}</span>,
      },
      { key: 'location', label: 'Locație', render: (r) => r.location_text ?? '—' },
      { key: 'source', label: 'Furnizor', expandOnly: true, render: (r) => r.source ?? '—' },
      { key: 'client', label: 'Client', expandOnly: true, render: (r) => r.buyer_name ?? r.reservation_client_name ?? '—' },
      { key: 'acq_date', label: 'Data achiziție', expandOnly: true, render: (r) => fmtDate(r.acquisition_date) },
      { key: 'flags', label: 'Flags', expandOnly: true, render: (r) => <FlagsCell row={r} /> },
    ],
    [],
  )

  // ── Tab counts ───────────────────────────────────────────
  const totals = summaryData?.totals ?? null

  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader
        title="Dispo"
        breadcrumbs={[{ label: 'CarPark', href: '/app/carpark' }, { label: 'Dispo' }]}
        description="Pipeline de dispoziție — de la achiziție la livrare."
        search={
          <SearchInput
            value={search}
            onChange={handleSearch}
            placeholder="VIN, model, client..."
            className={isMobile ? undefined : 'w-56'}
            collapsible={isMobile}
          />
        }
        actions={
          <Button variant="outline" size="sm" asChild>
            <a href={carparkDispoApi.exportUrl(activeFilters)} download>
              <FileSpreadsheet className="mr-1.5 h-4 w-4" />
              {isMobile ? 'Export' : 'Export Excel'}
            </a>
          </Button>
        }
      />

      {/* Zone 1 — KPI strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-7">
        <StatCard title="Mașini în stoc" value={kpisData?.cars_in_stock ?? 0} icon={<Car className="h-4 w-4" />} isLoading={kpisLoading} />
        <StatCard title="Rezervate" value={kpisData?.reserved ?? 0} icon={<BookmarkCheck className="h-4 w-4" />} isLoading={kpisLoading} />
        <StatCard
          title="Vândute luna asta"
          value={kpisData?.sold_this_month ?? 0}
          icon={<TrendingUp className="h-4 w-4" />}
          isLoading={kpisLoading}
        />
        <StatCard
          title="Livrate luna asta"
          value={kpisData?.delivered_this_month ?? 0}
          icon={<PackageCheck className="h-4 w-4" />}
          isLoading={kpisLoading}
        />
        <StatCard
          title="Zile medii în stoc"
          value={kpisData?.avg_days_in_stock ?? 0}
          icon={<Clock className="h-4 w-4" />}
          isLoading={kpisLoading}
        />
        <StatCard
          title="Peste 60 zile"
          value={kpisData?.aged_over_60 ?? 0}
          icon={<AlertTriangle className="h-4 w-4" />}
          isLoading={kpisLoading}
          className={(kpisData?.aged_over_60 ?? 0) > 0 ? '[&_p.text-base]:text-red-600 dark:[&_p.text-base]:text-red-400' : undefined}
        />
        {canViewFinance && (
          <StatCard
            title="Marjă brută MTD"
            value={fmtKpiCurrency(kpisData?.gross_margin_mtd)}
            icon={<DollarSign className="h-4 w-4" />}
            isLoading={kpisLoading}
          />
        )}
      </div>

      {/* Zone 2 — pipeline tabs */}
      <div className="flex gap-1 overflow-x-auto pb-1 scrollbar-none">
        {DISPO_STAGES.map((stage) => {
          const isActive = activeStage === stage.key
          const count = stageCounts ? (stage.key ? stageCounts[stage.key] : stageCounts.all) : undefined
          return (
            <button
              key={stage.key || 'all'}
              onClick={() => setActiveStage(stage.key)}
              className={cn(
                'shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors',
                isActive ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground hover:bg-muted/80',
              )}
            >
              {stage.label}
              {count != null && (
                <span className={cn('ml-1.5 text-xs', isActive ? 'text-primary-foreground/70' : 'text-muted-foreground/60')}>
                  {count}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* Filters toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <FilterBar fields={filterFields} values={filterValues} onChange={handleFilterChange} />
        <DateField mode="range" startDate={dateFrom} endDate={dateTo} onRangeChange={handleDateChange} showPresets />
        <div className="ml-auto">
          <ColumnToggle
            visibleColumns={visibleColumns}
            defaultColumns={defaultColumns}
            columnDefs={columnDefs as ColumnDef<never>[]}
            onChange={setVisibleColumns}
          />
        </div>
      </div>

      {/* Zone 3 — dense table */}
      {summaryLoading ? (
        <TableSkeleton rows={10} columns={8} />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={<Car className="h-12 w-12" />}
          title="Niciun vehicul găsit"
          description="Încearcă să ajustezi filtrele sau căutarea."
        />
      ) : (
        <ResponsiveDataView
          data={rows}
          mobileFields={mobileFields}
          getRowId={(r) => r.id}
          onRowClick={handleRowClick}
          actions={(row) => <DispoRowActions row={row} />}
          desktopTable={
            <Card>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        {visibleColumns.map((key) => {
                          const col = columnDefs.find((c) => c.key === key)
                          if (!col) return null
                          const sortable = SORTABLE_KEYS.has(key)
                          return (
                            <TableHead
                              key={key}
                              className={cn(col.className, sortable && 'cursor-pointer select-none')}
                              onClick={sortable ? () => handleSort(key) : undefined}
                            >
                              {sortable ? (
                                <span className="flex items-center gap-1 whitespace-nowrap">
                                  {col.label}
                                  <ArrowUpDown
                                    className={cn('h-3 w-3', sortBy === key ? 'text-foreground' : 'text-muted-foreground/40')}
                                  />
                                </span>
                              ) : (
                                <span className="whitespace-nowrap">{col.label}</span>
                              )}
                            </TableHead>
                          )
                        })}
                        {/* Row actions — always visible, not a ColumnToggle column */}
                        <TableHead className="w-9" />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {rows.map((row) => (
                        <TableRow key={row.id} className="cursor-pointer hover:bg-muted/40" onClick={() => handleRowClick(row)}>
                          {visibleColumns.map((key) => {
                            const col = columnDefs.find((c) => c.key === key)
                            if (!col) return null
                            return (
                              <TableCell key={key} className={col.className}>
                                {col.render(row)}
                              </TableCell>
                            )
                          })}
                          <TableCell className="text-right">
                            <DispoRowActions row={row} />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                    {totals && (
                      <TableFooter>
                        <TableRow>
                          {visibleColumns.map((key, idx) => {
                            if (key === 'acquisition_price') {
                              return (
                                <TableCell key={key} className="text-right font-semibold tabular-nums">
                                  <CurrencyDisplay value={totals.acquisition_price} />
                                </TableCell>
                              )
                            }
                            if (key === 'total_costs') {
                              return (
                                <TableCell key={key} className="text-right font-semibold tabular-nums">
                                  <CurrencyDisplay value={totals.total_costs} />
                                </TableCell>
                              )
                            }
                            if (key === 'sale_price') {
                              return (
                                <TableCell key={key} className="text-right font-semibold tabular-nums">
                                  <CurrencyDisplay value={totals.sale_price} />
                                </TableCell>
                              )
                            }
                            if (key === 'gross_margin') {
                              return (
                                <TableCell key={key} className="text-right font-semibold tabular-nums">
                                  <CurrencyDisplay value={totals.gross_margin} />
                                </TableCell>
                              )
                            }
                            if (idx === 0) {
                              return (
                                <TableCell key={key} className="font-semibold text-muted-foreground whitespace-nowrap">
                                  Total ({total})
                                </TableCell>
                              )
                            }
                            return <TableCell key={key} />
                          })}
                          <TableCell />
                        </TableRow>
                      </TableFooter>
                    )}
                  </Table>
                </div>
              </CardContent>
            </Card>
          }
        />
      )}

      {/* Pagination */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>{total} vehicule</span>
          <Select
            value={String(perPage)}
            onValueChange={(v) => {
              setPerPage(Number(v))
              setPage(1)
            }}
          >
            <SelectTrigger className="h-8 w-[90px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="25">25 / pag.</SelectItem>
              <SelectItem value="50">50 / pag.</SelectItem>
              <SelectItem value="100">100 / pag.</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {totalPages > 1 && (
          <Pagination className="mx-0 w-auto">
            <PaginationContent>
              <PaginationItem>
                <PaginationPrevious
                  onClick={() => page > 1 && setPage(page - 1)}
                  className={page <= 1 ? 'pointer-events-none opacity-50' : 'cursor-pointer'}
                />
              </PaginationItem>
              {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                let pageNum: number
                if (totalPages <= 5) {
                  pageNum = i + 1
                } else if (page <= 3) {
                  pageNum = i + 1
                } else if (page >= totalPages - 2) {
                  pageNum = totalPages - 4 + i
                } else {
                  pageNum = page - 2 + i
                }
                return (
                  <PaginationItem key={pageNum}>
                    <PaginationLink isActive={pageNum === page} onClick={() => setPage(pageNum)} className="cursor-pointer">
                      {pageNum}
                    </PaginationLink>
                  </PaginationItem>
                )
              })}
              <PaginationItem>
                <PaginationNext
                  onClick={() => page < totalPages && setPage(page + 1)}
                  className={page >= totalPages ? 'pointer-events-none opacity-50' : 'cursor-pointer'}
                />
              </PaginationItem>
            </PaginationContent>
          </Pagination>
        )}
      </div>
    </div>
  )
}
