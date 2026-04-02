import { useState, useMemo, useCallback } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Plus,
  SlidersHorizontal,
  Car,
  ArrowUpDown,
  Eye,
  ImageIcon,
} from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { SearchInput } from '@/components/shared/SearchInput'
import { FilterBar, type FilterField } from '@/components/shared/FilterBar'
import { EmptyState } from '@/components/shared/EmptyState'
import { TableSkeleton } from '@/components/shared/TableSkeleton'
import { CurrencyDisplay } from '@/components/shared/CurrencyDisplay'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
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
import { useAuthStore } from '@/stores/authStore'
import { useCarParkStore } from '@/stores/carParkStore'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { carparkApi } from '@/api/carpark'
import {
  STATUS_LABELS,
  CATEGORY_LABELS,
  CATALOG_TABS,
  type VehicleCatalogItem,
  type VehicleStatus,
  type VehicleCategory,
} from '@/types/carpark'

// ── Status colors ──────────────────────────────────────────
const STATUS_COLORS: Record<string, string> = {
  ACQUIRED: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  INSPECTION: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
  RECONDITIONING: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
  READY_FOR_SALE: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200',
  LISTED: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
  RESERVED: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
  SOLD: 'bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-200',
  DELIVERED: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200',
  PRICE_REDUCED: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
  AUCTION_CANDIDATE: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200',
  IN_TRANSIT: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200',
  AT_BODYSHOP: 'bg-rose-100 text-rose-800 dark:bg-rose-900 dark:text-rose-200',
  INSURANCE_CLAIM: 'bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-200',
  RETURNED: 'bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200',
  SCRAPPED: 'bg-zinc-100 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200',
  TRANSFERRED: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900 dark:text-cyan-200',
}

function VehicleStatusBadge({ status }: { status: VehicleStatus }) {
  return (
    <Badge
      variant="secondary"
      className={`font-normal text-[11px] ${STATUS_COLORS[status] ?? ''}`}
    >
      {STATUS_LABELS[status] ?? status}
    </Badge>
  )
}

function CategoryBadge({ category }: { category: VehicleCategory }) {
  return (
    <Badge variant="outline" className="font-normal text-[11px]">
      {CATEGORY_LABELS[category] ?? category}
    </Badge>
  )
}

// ── Format helpers ─────────────────────────────────────────
function formatKm(km: number): string {
  return new Intl.NumberFormat('ro-RO').format(km) + ' km'
}

// ── Catalog page ───────────────────────────────────────────
export default function CarPark() {
  const isMobile = useIsMobile()
  const user = useAuthStore((s) => s.user)
  const canEdit = user?.can_edit_carpark ?? false

  const [searchParams, setSearchParams] = useSearchParams()
  const [showFilters, setShowFilters] = useState(false)

  // Store
  const filters = useCarParkStore((s) => s.filters)
  const updateFilter = useCarParkStore((s) => s.updateFilter)
  const clearFilters = useCarParkStore((s) => s.clearFilters)
  const page = useCarParkStore((s) => s.page)
  const perPage = useCarParkStore((s) => s.perPage)
  const setPage = useCarParkStore((s) => s.setPage)
  const sort = useCarParkStore((s) => s.sort)
  const order = useCarParkStore((s) => s.order)
  const setSort = useCarParkStore((s) => s.setSort)

  // Active status tab from URL
  const activeTab = searchParams.get('status') || ''

  const setActiveTab = useCallback(
    (status: string) => {
      const params: Record<string, string> = {}
      if (status) params.status = status
      setSearchParams(params, { replace: true })
      updateFilter('status', status || undefined)
      setPage(1)
    },
    [setSearchParams, updateFilter, setPage],
  )

  // Build full filter set including tab status
  const activeFilters = useMemo(() => {
    const f = { ...filters }
    if (activeTab) f.status = activeTab
    return f
  }, [filters, activeTab])

  // ── Data fetching ──────────────────────────────────────
  const { data: catalogData, isLoading } = useQuery({
    queryKey: ['carpark', 'catalog', activeFilters, page, perPage, sort, order],
    queryFn: () => carparkApi.getCatalog(activeFilters, page, perPage, sort, order),
  })

  const { data: statusCountsData } = useQuery({
    queryKey: ['carpark', 'status-counts'],
    queryFn: () => carparkApi.getStatusCounts(),
    staleTime: 30_000,
  })

  const { data: filterOptions } = useQuery({
    queryKey: ['carpark', 'filter-options'],
    queryFn: () => carparkApi.getFilterOptions(),
    staleTime: 60_000,
  })

  const items = catalogData?.items ?? []
  const total = catalogData?.total ?? 0
  const totalPages = Math.ceil(total / perPage)

  // Status counts map
  const countMap = useMemo(() => {
    const m = new Map<string, number>()
    let allCount = 0
    for (const sc of statusCountsData?.counts ?? []) {
      m.set(sc.status, sc.count)
      allCount += sc.count
    }
    m.set('', allCount)
    return m
  }, [statusCountsData])

  // ── Filter fields ──────────────────────────────────────
  const filterFields: FilterField[] = useMemo(() => {
    const brands = (filterOptions?.brands ?? []).map((b) => ({ value: b, label: b }))
    const fuels = (filterOptions?.fuel_types ?? []).map((f) => ({ value: f, label: f }))
    const bodies = (filterOptions?.body_types ?? []).map((b) => ({ value: b, label: b }))
    return [
      { key: 'brand', label: 'Brand', type: 'select' as const, options: brands },
      { key: 'fuel_type', label: 'Fuel', type: 'select' as const, options: fuels },
      { key: 'body_type', label: 'Body', type: 'select' as const, options: bodies },
      { key: 'year_min', label: 'Year From', type: 'text' as const, placeholder: 'e.g. 2020' },
      { key: 'year_max', label: 'Year To', type: 'text' as const, placeholder: 'e.g. 2025' },
      { key: 'price_min', label: 'Price Min', type: 'text' as const, placeholder: 'e.g. 10000' },
      { key: 'price_max', label: 'Price Max', type: 'text' as const, placeholder: 'e.g. 50000' },
    ]
  }, [filterOptions])

  const filterValues: Record<string, string> = useMemo(
    () => ({
      brand: filters.brand ?? '',
      fuel_type: filters.fuel_type ?? '',
      body_type: filters.body_type ?? '',
      year_min: filters.year_min ?? '',
      year_max: filters.year_max ?? '',
      price_min: filters.price_min ?? '',
      price_max: filters.price_max ?? '',
    }),
    [filters],
  )

  const handleFilterChange = useCallback(
    (values: Record<string, string>) => {
      Object.entries(values).forEach(([key, value]) => {
        updateFilter(key as keyof typeof filters, value || undefined)
      })
      setPage(1)
    },
    [updateFilter, setPage],
  )

  // ── Search ─────────────────────────────────────────────
  const [search, setSearch] = useState(filters.search ?? '')
  const handleSearch = useCallback(
    (value: string) => {
      setSearch(value)
      updateFilter('search', value || undefined)
      setPage(1)
    },
    [updateFilter, setPage],
  )

  // ── Sort handler ───────────────────────────────────────
  const handleSort = useCallback(
    (column: string) => {
      if (sort === column) {
        setSort(column, order === 'asc' ? 'desc' : 'asc')
      } else {
        setSort(column, 'asc')
      }
    },
    [sort, order, setSort],
  )

  function SortableHeader({ column, label }: { column: string; label: string }) {
    const isActive = sort === column
    return (
      <TableHead
        className="cursor-pointer select-none whitespace-nowrap"
        onClick={() => handleSort(column)}
      >
        <div className="flex items-center gap-1">
          {label}
          <ArrowUpDown
            className={`h-3 w-3 ${isActive ? 'text-foreground' : 'text-muted-foreground/40'}`}
          />
        </div>
      </TableHead>
    )
  }

  // ── Render ─────────────────────────────────────────────
  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader
        title="CarPark"
        breadcrumbs={[{ label: 'CarPark' }]}
        search={
          <SearchInput
            value={search}
            onChange={handleSearch}
            placeholder="VIN, brand, model..."
            className="w-48 md:w-64"
          />
        }
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              onClick={() => setShowFilters(!showFilters)}
              className="relative"
            >
              <SlidersHorizontal className="h-4 w-4" />
              {Object.values(filterValues).filter(Boolean).length > 0 && (
                <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[9px] font-bold text-primary-foreground">
                  {Object.values(filterValues).filter(Boolean).length}
                </span>
              )}
            </Button>
            {canEdit && (
              <Button size="sm" asChild>
                <Link to="/app/carpark/new">
                  <Plus className="mr-1 h-4 w-4" />
                  {!isMobile && 'Add Vehicle'}
                </Link>
              </Button>
            )}
          </div>
        }
      />

      {/* Status tabs */}
      <div className="flex gap-1 overflow-x-auto pb-1 scrollbar-none">
        {CATALOG_TABS.map((tab) => {
          const isActive = activeTab === tab.key
          const count = countMap.get(tab.key)
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`
                shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors
                ${
                  isActive
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-muted-foreground hover:bg-muted/80'
                }
              `}
            >
              {tab.label}
              {count != null && (
                <span
                  className={`ml-1.5 text-xs ${
                    isActive ? 'text-primary-foreground/70' : 'text-muted-foreground/60'
                  }`}
                >
                  {count}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* Filters */}
      {showFilters && (
        <FilterBar
          fields={filterFields}
          values={filterValues}
          onChange={handleFilterChange}
        />
      )}

      {/* Results count */}
      {!isLoading && (
        <div className="text-sm text-muted-foreground">
          {total} {total === 1 ? 'vehicle' : 'vehicles'}
        </div>
      )}

      {/* Content */}
      {isLoading ? (
        <TableSkeleton rows={10} columns={8} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Car className="h-12 w-12" />}
          title="No vehicles found"
          description="Try adjusting your filters or search query."
          action={
            Object.values(filterValues).some(Boolean) ? (
              <Button variant="outline" onClick={clearFilters}>
                Clear all filters
              </Button>
            ) : undefined
          }
        />
      ) : isMobile ? (
        <MobileCardList items={items} />
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-16" />
                <SortableHeader column="brand" label="Vehicle" />
                <TableHead>Category</TableHead>
                <TableHead>Status</TableHead>
                <SortableHeader column="year_of_manufacture" label="Year" />
                <SortableHeader column="mileage_km" label="Mileage" />
                <TableHead>Fuel</TableHead>
                <SortableHeader column="current_price" label="Price" />
                <SortableHeader column="stationary_days" label="Days" />
                <TableHead>Location</TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((v) => (
                <VehicleRow key={v.id} vehicle={v} />
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <Pagination>
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
                  <PaginationLink
                    isActive={pageNum === page}
                    onClick={() => setPage(pageNum)}
                    className="cursor-pointer"
                  >
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
  )
}

// ── Table row ────────────────────────────────────────────────
function VehicleRow({ vehicle: v }: { vehicle: VehicleCatalogItem }) {
  return (
    <TableRow className="group">
      {/* Thumbnail */}
      <TableCell className="p-2">
        {v.primary_photo_url ? (
          <img
            src={v.primary_photo_url}
            alt={`${v.brand} ${v.model}`}
            className="h-10 w-14 rounded object-cover"
            loading="lazy"
          />
        ) : (
          <div className="flex h-10 w-14 items-center justify-center rounded bg-muted">
            <ImageIcon className="h-4 w-4 text-muted-foreground" />
          </div>
        )}
      </TableCell>

      {/* Brand + Model */}
      <TableCell>
        <Link
          to={`/app/carpark/${v.id}`}
          className="font-medium hover:underline"
        >
          {v.brand} {v.model}
        </Link>
        {v.variant && (
          <div className="text-xs text-muted-foreground truncate max-w-[200px]">
            {v.variant}
          </div>
        )}
        {v.nr_stoc && (
          <div className="text-[11px] text-muted-foreground/60">#{v.nr_stoc}</div>
        )}
      </TableCell>

      {/* Category */}
      <TableCell>
        <CategoryBadge category={v.category} />
      </TableCell>

      {/* Status */}
      <TableCell>
        <VehicleStatusBadge status={v.status} />
      </TableCell>

      {/* Year */}
      <TableCell className="tabular-nums">
        {v.year_of_manufacture ?? '-'}
      </TableCell>

      {/* Mileage */}
      <TableCell className="tabular-nums text-sm">
        {v.mileage_km > 0 ? formatKm(v.mileage_km) : '-'}
      </TableCell>

      {/* Fuel */}
      <TableCell className="text-sm">{v.fuel_type ?? '-'}</TableCell>

      {/* Price */}
      <TableCell className="text-right">
        {v.current_price != null ? (
          <CurrencyDisplay value={v.current_price} currency={v.price_currency} />
        ) : (
          <span className="text-muted-foreground">-</span>
        )}
      </TableCell>

      {/* Days */}
      <TableCell className="tabular-nums">
        <span
          className={
            v.stationary_days > 90
              ? 'text-red-600 dark:text-red-400 font-medium'
              : v.stationary_days > 60
                ? 'text-orange-600 dark:text-orange-400'
                : ''
          }
        >
          {v.stationary_days}
        </span>
      </TableCell>

      {/* Location */}
      <TableCell className="text-sm text-muted-foreground truncate max-w-[120px]">
        {v.location_text ?? '-'}
      </TableCell>

      {/* Actions */}
      <TableCell>
        <Button variant="ghost" size="icon" asChild className="opacity-0 group-hover:opacity-100">
          <Link to={`/app/carpark/${v.id}`}>
            <Eye className="h-4 w-4" />
          </Link>
        </Button>
      </TableCell>
    </TableRow>
  )
}

// ── Mobile card list ─────────────────────────────────────────
function MobileCardList({ items }: { items: VehicleCatalogItem[] }) {
  return (
    <div className="space-y-2">
      {items.map((v) => (
        <Link key={v.id} to={`/app/carpark/${v.id}`}>
          <Card className="p-3">
            <div className="flex gap-3">
              {/* Thumbnail */}
              {v.primary_photo_url ? (
                <img
                  src={v.primary_photo_url}
                  alt={`${v.brand} ${v.model}`}
                  className="h-16 w-20 shrink-0 rounded object-cover"
                  loading="lazy"
                />
              ) : (
                <div className="flex h-16 w-20 shrink-0 items-center justify-center rounded bg-muted">
                  <ImageIcon className="h-5 w-5 text-muted-foreground" />
                </div>
              )}

              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-2">
                  <div className="font-medium truncate">
                    {v.brand} {v.model}
                  </div>
                  <VehicleStatusBadge status={v.status} />
                </div>
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                  {v.year_of_manufacture && <span>{v.year_of_manufacture}</span>}
                  {v.mileage_km > 0 && <span>{formatKm(v.mileage_km)}</span>}
                  {v.fuel_type && <span>{v.fuel_type}</span>}
                </div>
                <div className="mt-1 flex items-center justify-between">
                  {v.current_price != null ? (
                    <CurrencyDisplay
                      value={v.current_price}
                      currency={v.price_currency}
                      className="text-sm font-semibold"
                    />
                  ) : (
                    <span className="text-sm text-muted-foreground">-</span>
                  )}
                  <span className="text-xs text-muted-foreground">
                    {v.stationary_days}d
                  </span>
                </div>
              </div>
            </div>
          </Card>
        </Link>
      ))}
    </div>
  )
}
