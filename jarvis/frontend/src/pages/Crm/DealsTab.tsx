import { useState, useMemo, Fragment } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ChevronLeft, ChevronRight, ChevronDown, ChevronUp, ChevronsUpDown, Search, Download, Pencil, Trash2, Car, TrendingUp, Palette, FilterX, SlidersHorizontal } from 'lucide-react'
import { crmApi, type CrmDeal } from '@/api/crm'
import { ColumnToggle, useColumnState, type ColumnDef } from '@/components/shared/ColumnToggle'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { EditDealDialog } from './EditDealDialog'
import { usePersistedState } from '@/lib/utils'
import { useAuthStore } from '@/stores/authStore'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { MobileCardList, type MobileCardField } from '@/components/shared/MobileCardList'
import { DatePicker } from '@/components/ui/date-picker'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { toast } from 'sonner'

const columnDefs: ColumnDef<CrmDeal>[] = [
  { key: 'source', label: 'Type', className: 'w-[70px]', render: (d) => <Badge variant={d.source === 'nw' ? 'default' : 'secondary'}>{d.source.toUpperCase()}</Badge> },
  { key: 'dossier_number', label: 'Dossier', className: 'font-mono text-xs', render: (d) => d.dossier_number || '-' },
  { key: 'brand', label: 'Brand', render: (d) => d.brand || '-' },
  { key: 'model_name', label: 'Model', className: 'max-w-[200px] truncate', render: (d) => d.model_name || '-' },
  { key: 'buyer_name', label: 'Client', className: 'max-w-[180px] truncate', render: (d) => d.buyer_name || d.client_display_name || '-' },
  { key: 'dossier_status', label: 'Status', render: (d) => d.dossier_status ? <Badge variant="outline">{d.dossier_status}</Badge> : '-' },
  { key: 'sale_price_net', label: 'Price', className: 'text-right font-mono text-xs', render: (d) => {
    const v = d.sale_price_net || d.gw_gross_value
    return v ? Number(v).toLocaleString('ro-RO', { minimumFractionDigits: 0 }) : '-'
  }},
  { key: 'contract_date', label: 'Date', className: 'text-xs', render: (d) => d.contract_date ? new Date(d.contract_date).toLocaleDateString() : '-' },
  { key: 'dealer_name', label: 'Dealer', className: 'text-xs max-w-[140px] truncate', render: (d) => d.dealer_name || '-' },
  { key: 'branch', label: 'Branch', className: 'text-xs', render: (d) => d.branch || '-' },
  { key: 'order_number', label: 'Order #', className: 'font-mono text-xs', render: (d) => d.order_number || '-' },
  { key: 'vin', label: 'VIN', className: 'font-mono text-xs max-w-[160px] truncate', render: (d) => d.vin || '-' },
  { key: 'engine_code', label: 'Engine', className: 'text-xs', render: (d) => d.engine_code || '-' },
  { key: 'fuel_type', label: 'Fuel', className: 'text-xs', render: (d) => d.fuel_type || '-' },
  { key: 'color', label: 'Color', className: 'text-xs', render: (d) => d.color || '-' },
  { key: 'model_year', label: 'Year', className: 'text-xs', render: (d) => d.model_year ?? '-' },
  { key: 'order_status', label: 'Order Status', className: 'text-xs', render: (d) => d.order_status || '-' },
  { key: 'contract_status', label: 'Contract Status', className: 'text-xs', render: (d) => d.contract_status || '-' },
  { key: 'sales_person', label: 'Sales Person', className: 'text-xs max-w-[120px] truncate', render: (d) => d.sales_person || '-' },
  { key: 'owner_name', label: 'Owner', className: 'text-xs max-w-[140px] truncate', render: (d) => d.owner_name || '-' },
  { key: 'list_price', label: 'List Price', className: 'text-right font-mono text-xs', render: (d) => d.list_price ? Number(d.list_price).toLocaleString('ro-RO') : '-' },
  { key: 'purchase_price_net', label: 'Purchase Price', className: 'text-right font-mono text-xs', render: (d) => d.purchase_price_net ? Number(d.purchase_price_net).toLocaleString('ro-RO') : '-' },
  { key: 'gross_profit', label: 'Gross Profit', className: 'text-right font-mono text-xs', render: (d) => d.gross_profit ? Number(d.gross_profit).toLocaleString('ro-RO') : '-' },
  { key: 'discount_value', label: 'Discount', className: 'text-right font-mono text-xs', render: (d) => d.discount_value ? Number(d.discount_value).toLocaleString('ro-RO') : '-' },
  { key: 'vehicle_type', label: 'Vehicle Type', className: 'text-xs', render: (d) => d.vehicle_type || '-' },
  { key: 'registration_number', label: 'Reg. Number', className: 'font-mono text-xs', render: (d) => d.registration_number || '-' },
  { key: 'delivery_date', label: 'Delivery', className: 'text-xs', render: (d) => d.delivery_date ? new Date(d.delivery_date).toLocaleDateString() : '-' },
]

const defaultVisible = ['source', 'dossier_number', 'brand', 'model_name', 'buyer_name', 'dossier_status', 'sale_price_net', 'contract_date']
const lockedColumns = new Set(['source'])
const columnDefMap = new Map(columnDefs.map((c) => [c.key, c]))

// All detail fields for the expanded row
const detailFields: { key: keyof CrmDeal; label: string }[] = [
  { key: 'source', label: 'Type' },
  { key: 'dossier_number', label: 'Dossier' },
  { key: 'order_number', label: 'Order #' },
  { key: 'brand', label: 'Brand' },
  { key: 'model_name', label: 'Model' },
  { key: 'model_code', label: 'Model Code' },
  { key: 'model_year', label: 'Year' },
  { key: 'vin', label: 'VIN' },
  { key: 'engine_code', label: 'Engine' },
  { key: 'fuel_type', label: 'Fuel' },
  { key: 'color', label: 'Color' },
  { key: 'vehicle_type', label: 'Vehicle Type' },
  { key: 'buyer_name', label: 'Buyer' },
  { key: 'owner_name', label: 'Owner' },
  { key: 'sales_person', label: 'Sales Person' },
  { key: 'dealer_name', label: 'Dealer' },
  { key: 'branch', label: 'Branch' },
  { key: 'dossier_status', label: 'Dossier Status' },
  { key: 'order_status', label: 'Order Status' },
  { key: 'contract_status', label: 'Contract Status' },
  { key: 'contract_date', label: 'Contract Date' },
  { key: 'delivery_date', label: 'Delivery Date' },
  { key: 'registration_number', label: 'Reg. Number' },
  { key: 'list_price', label: 'List Price' },
  { key: 'purchase_price_net', label: 'Purchase Price' },
  { key: 'sale_price_net', label: 'Sale Price' },
  { key: 'gross_profit', label: 'Gross Profit' },
  { key: 'discount_value', label: 'Discount' },
  { key: 'gw_gross_value', label: 'GW Gross Value' },
]

function formatVal(v: unknown): string {
  if (v == null || v === '') return '-'
  if (typeof v === 'number') {
    // Don't add thousands separators to years (4-digit integers)
    if (Number.isInteger(v) && v >= 1900 && v <= 2100) return String(v)
    return v.toLocaleString('ro-RO')
  }
  if (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}/.test(v)) return new Date(v).toLocaleDateString()
  return String(v)
}

export default function DealsTab({ showStats = false }: { showStats?: boolean }) {
  const user = useAuthStore((s) => s.user)
  const queryClient = useQueryClient()
  const isMobile = useIsMobile()

  const [search, setSearch] = useState('')
  const [source, setSource] = useState<string>('all')
  const [brand, setBrand] = useState('')
  const [status, setStatus] = useState('')
  const [dealer, setDealer] = useState('')
  const [salesPerson, setSalesPerson] = useState('')
  const [buyer, setBuyer] = useState('')
  const [vinSearch, setVinSearch] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [page, setPage] = useState(0)
  const [limit, setLimit] = usePersistedState('crm-deals-page-size', 30)
  const [sortBy, setSortBy] = useState('')
  const [sortOrder, setSortOrder] = useState<'ASC' | 'DESC' | ''>('')

  const toggleSort = (key: string) => {
    if (sortBy === key) {
      if (sortOrder === 'ASC') { setSortOrder('DESC') }
      else if (sortOrder === 'DESC') { setSortBy(''); setSortOrder('') }
      else { setSortOrder('ASC') }
    } else {
      setSortBy(key)
      setSortOrder('ASC')
    }
    setPage(0)
  }

  const hasFilters = !!(search || source !== 'all' || brand || status || dealer || salesPerson || buyer || vinSearch || dateFrom || dateTo || sortBy)
  const clearFilters = () => {
    setSearch(''); setSource('all'); setBrand(''); setStatus('')
    setDealer(''); setSalesPerson(''); setBuyer(''); setVinSearch('')
    setDateFrom(''); setDateTo(''); setSortBy(''); setSortOrder(''); setPage(0)
  }

  const [filtersOpen, setFiltersOpen] = useState(false)
  const [expandedRow, setExpandedRow] = useState<number | null>(null)
  const [editDeal, setEditDeal] = useState<CrmDeal | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { visibleColumns, setVisibleColumns, defaultColumns } = useColumnState(
    'crm-deals-columns',
    defaultVisible,
    columnDefs.map((c) => c.key),
  )

  const params: Record<string, string> = { limit: String(limit), offset: String(page * limit) }
  if (source !== 'all') params.source = source
  if (search) params.model = search
  if (brand) params.brand = brand
  if (status) params.status = status
  if (dealer) params.dealer = dealer
  if (salesPerson) params.sales_person = salesPerson
  if (buyer) params.buyer = buyer
  if (vinSearch) params.vin = vinSearch
  if (dateFrom) params.date_from = dateFrom
  if (dateTo) params.date_to = dateTo
  if (sortBy) params.sort_by = sortBy
  if (sortOrder) params.sort_order = sortOrder

  const { data, isLoading } = useQuery({
    queryKey: ['crm-deals', params],
    queryFn: () => crmApi.getDeals(params),
  })
  const { data: brandsData } = useQuery({ queryKey: ['crm-brands'], queryFn: crmApi.getBrands })
  const { data: statusesData } = useQuery({ queryKey: ['crm-deal-statuses'], queryFn: crmApi.getDealStatuses })
  const { data: dealersData } = useQuery({ queryKey: ['crm-dealers'], queryFn: crmApi.getDealers })
  const { data: salesPersonsData } = useQuery({ queryKey: ['crm-sales-persons'], queryFn: crmApi.getSalesPersons })
  const { data: stats } = useQuery({ queryKey: ['crm-stats'], queryFn: crmApi.getStats })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => crmApi.deleteDeal(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['crm-deals'] })
      toast.success('Deal deleted')
      setDeleteId(null)
      setExpandedRow(null)
    },
    onError: () => toast.error('Failed to delete deal'),
  })

  const deals = data?.deals || []
  const total = data?.total || 0
  const canEdit = user?.can_edit_crm
  const canDelete = user?.can_delete_crm
  const canExport = user?.can_export_crm

  const mobileFields: MobileCardField<CrmDeal>[] = useMemo(() => [
    { key: 'buyer_name', label: 'Client', isPrimary: true, render: (d) => d.buyer_name || d.client_display_name || 'Unknown' },
    { key: 'sale_price_net', label: 'Price', isPrimary: true, alignRight: true, render: (d) => {
      const v = d.sale_price_net || d.gw_gross_value
      return v ? <span className="tabular-nums">{Number(v).toLocaleString('ro-RO', { minimumFractionDigits: 0 })}</span> : '-'
    }},
    { key: 'model', label: 'Vehicle', isSecondary: true, render: (d) => [d.brand, d.model_name].filter(Boolean).join(' ') || '-' },
    { key: 'dossier_status', label: 'Status', isSecondary: true, render: (d) => d.dossier_status ? <Badge variant="outline" className="text-[11px] px-1.5 py-0">{d.dossier_status}</Badge> : null },
    { key: 'source', label: 'Type', render: (d) => <Badge variant={d.source === 'nw' ? 'default' : 'secondary'} className="text-[11px]">{d.source.toUpperCase()}</Badge> },
    { key: 'contract_date', label: 'Date', render: (d) => d.contract_date ? new Date(d.contract_date).toLocaleDateString() : '-' },
    { key: 'dossier_number', label: 'Dossier', expandOnly: true, render: (d) => d.dossier_number || '-' },
    { key: 'sales_person', label: 'Sales Person', expandOnly: true, render: (d) => d.sales_person || '-' },
    { key: 'dealer_name', label: 'Dealer', expandOnly: true, render: (d) => d.dealer_name || '-' },
    { key: 'branch', label: 'Branch', expandOnly: true, render: (d) => d.branch || '-' },
    { key: 'vin', label: 'VIN', expandOnly: true, render: (d) => <span className="font-mono text-xs">{d.vin || '-'}</span> },
    { key: 'order_number', label: 'Order #', expandOnly: true, render: (d) => d.order_number || '-' },
    { key: 'color', label: 'Color', expandOnly: true, render: (d) => d.color || '-' },
    { key: 'fuel_type', label: 'Fuel', expandOnly: true, render: (d) => d.fuel_type || '-' },
    { key: 'model_year', label: 'Year', expandOnly: true, render: (d) => d.model_year ?? '-' },
    { key: 'delivery_date', label: 'Delivery', expandOnly: true, render: (d) => d.delivery_date ? new Date(d.delivery_date).toLocaleDateString() : '-' },
    { key: 'owner_name', label: 'Owner', expandOnly: true, render: (d) => d.owner_name || '-' },
  ], [])

  // Build export params (same filters, no pagination)
  const exportParams: Record<string, string> = {}
  if (source !== 'all') exportParams.source = source
  if (search) exportParams.model = search
  if (brand) exportParams.brand = brand
  if (status) exportParams.status = status
  if (dealer) exportParams.dealer = dealer
  if (salesPerson) exportParams.sales_person = salesPerson
  if (buyer) exportParams.buyer = buyer
  if (vinSearch) exportParams.vin = vinSearch
  if (dateFrom) exportParams.date_from = dateFrom
  if (dateTo) exportParams.date_to = dateTo
  if (sortBy) exportParams.sort_by = sortBy
  if (sortOrder) exportParams.sort_order = sortOrder

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Car Sales (NW + GW)</CardTitle>
          <div className="flex items-center gap-2">
            {canExport && (
              <Button variant="outline" size="sm" className="hidden md:inline-flex" asChild>
                <a href={crmApi.exportDealsUrl(exportParams)} download><Download className="h-4 w-4 mr-1" />Export CSV</a>
              </Button>
            )}
            <ColumnToggle
              visibleColumns={visibleColumns}
              defaultColumns={defaultColumns}
              columnDefs={columnDefs as ColumnDef<never>[]}
              lockedColumns={lockedColumns}
              onChange={setVisibleColumns}
            />
          </div>
        </div>

        {/* Info cards */}
        {stats && (
          <div className={`grid grid-cols-2 md:grid-cols-4 gap-3 mt-2 ${showStats ? '' : 'hidden md:grid'}`}>
            <div className="rounded-lg border bg-card p-3 flex items-center gap-2.5">
              <div className="rounded-md bg-primary/10 p-1.5"><Car className="h-4 w-4 text-primary" /></div>
              <div>
                <p className="text-xl font-bold leading-none">{stats.deals.total.toLocaleString()}</p>
                <p className="text-xs text-muted-foreground mt-0.5">Total Sales</p>
              </div>
            </div>
            <div className="rounded-lg border bg-card p-3 flex items-center gap-2.5">
              <div className="rounded-md bg-green-500/10 p-1.5"><TrendingUp className="h-4 w-4 text-green-500" /></div>
              <div>
                <p className="text-xl font-bold leading-none">{stats.deals.new_cars.toLocaleString()}</p>
                <p className="text-xs text-muted-foreground mt-0.5">New Cars (NW)</p>
              </div>
            </div>
            <div className="rounded-lg border bg-card p-3 flex items-center gap-2.5">
              <div className="rounded-md bg-orange-500/10 p-1.5"><Car className="h-4 w-4 text-orange-500" /></div>
              <div>
                <p className="text-xl font-bold leading-none">{stats.deals.used_cars.toLocaleString()}</p>
                <p className="text-xs text-muted-foreground mt-0.5">Used Cars (GW)</p>
              </div>
            </div>
            <div className="rounded-lg border bg-card p-3 flex items-center gap-2.5">
              <div className="rounded-md bg-violet-500/10 p-1.5"><Palette className="h-4 w-4 text-violet-500" /></div>
              <div>
                <p className="text-xl font-bold leading-none">{stats.deals.brands}</p>
                <p className="text-xs text-muted-foreground mt-0.5">Brands</p>
              </div>
            </div>
          </div>
        )}

        {/* Filters */}
        {(() => {
          const activeFilterCount = [source !== 'all', brand, status, dealer, salesPerson, buyer, vinSearch, dateFrom, dateTo].filter(Boolean).length

          const filterControls = (
            <>
              <Select value={source} onValueChange={v => { setSource(v); setPage(0) }}>
                <SelectTrigger className={isMobile ? 'w-full' : 'w-[110px] h-9'}><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="nw">NW</SelectItem>
                  <SelectItem value="gw">GW</SelectItem>
                </SelectContent>
              </Select>
              <Select value={brand || '_all'} onValueChange={v => { setBrand(v === '_all' ? '' : v); setPage(0) }}>
                <SelectTrigger className={isMobile ? 'w-full' : 'w-[130px] h-9'}><SelectValue placeholder="Brand" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_all">All Brands</SelectItem>
                  {brandsData?.brands.map(b => <SelectItem key={b} value={b}>{b}</SelectItem>)}
                </SelectContent>
              </Select>
              <Select value={status || '_all'} onValueChange={v => { setStatus(v === '_all' ? '' : v); setPage(0) }}>
                <SelectTrigger className={isMobile ? 'w-full' : 'w-[130px] h-9'}><SelectValue placeholder="Status" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_all">All Statuses</SelectItem>
                  {statusesData?.statuses.map(s => <SelectItem key={s.dossier_status} value={s.dossier_status}>{s.dossier_status} ({s.count})</SelectItem>)}
                </SelectContent>
              </Select>
              <Select value={dealer || '_all'} onValueChange={v => { setDealer(v === '_all' ? '' : v); setPage(0) }}>
                <SelectTrigger className={isMobile ? 'w-full' : 'w-[130px] h-9'}><SelectValue placeholder="Dealer" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_all">All Dealers</SelectItem>
                  {dealersData?.dealers.map(d => <SelectItem key={d} value={d}>{d}</SelectItem>)}
                </SelectContent>
              </Select>
              <Select value={salesPerson || '_all'} onValueChange={v => { setSalesPerson(v === '_all' ? '' : v); setPage(0) }}>
                <SelectTrigger className={isMobile ? 'w-full' : 'w-[130px] h-9'}><SelectValue placeholder="Sales Person" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_all">All Sales</SelectItem>
                  {salesPersonsData?.sales_persons.map(sp => <SelectItem key={sp} value={sp}>{sp}</SelectItem>)}
                </SelectContent>
              </Select>
              <Input placeholder="Buyer..." value={buyer} onChange={e => { setBuyer(e.target.value); setPage(0) }} className={isMobile ? 'w-full' : 'w-[120px] h-9'} />
              <Input placeholder="VIN..." value={vinSearch} onChange={e => { setVinSearch(e.target.value); setPage(0) }} className={isMobile ? 'w-full font-mono' : 'w-[120px] h-9 font-mono'} />
              <DatePicker value={dateFrom} onChange={v => { setDateFrom(v); setPage(0) }} placeholder="From date" className={isMobile ? 'w-full' : 'w-[155px]'} />
              <DatePicker value={dateTo} onChange={v => { setDateTo(v); setPage(0) }} placeholder="To date" className={isMobile ? 'w-full' : 'w-[155px]'} />
            </>
          )

          if (isMobile) {
            return (
              <div className="mt-3 space-y-2">
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input placeholder="Model..." value={search} onChange={e => { setSearch(e.target.value); setPage(0) }} className="pl-8" />
                  </div>
                  <Button variant="outline" size="icon" className="shrink-0" onClick={() => setFiltersOpen(true)}>
                    <SlidersHorizontal className="h-4 w-4" />
                    {activeFilterCount > 0 && (
                      <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[10px] font-semibold text-primary-foreground">
                        {activeFilterCount}
                      </span>
                    )}
                  </Button>
                </div>
                <Sheet open={filtersOpen} onOpenChange={setFiltersOpen}>
                  <SheetContent side="bottom" className="max-h-[80vh] overflow-y-auto px-4">
                    <SheetHeader><SheetTitle>Filters</SheetTitle></SheetHeader>
                    <div className="grid grid-cols-2 gap-2 py-4">
                      {filterControls}
                      <div className="col-span-2 flex gap-2 pt-2">
                        {hasFilters && (
                          <Button variant="outline" onClick={() => { clearFilters(); setFiltersOpen(false) }} className="flex-1">
                            Clear All
                          </Button>
                        )}
                        <Button onClick={() => setFiltersOpen(false)} className="flex-1">
                          Apply
                        </Button>
                      </div>
                    </div>
                  </SheetContent>
                </Sheet>
              </div>
            )
          }

          return (
            <div className="flex flex-wrap gap-1.5 mt-3">
              <div className="relative flex-1 min-w-[160px]">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input placeholder="Model..." value={search} onChange={e => { setSearch(e.target.value); setPage(0) }} className="pl-8 h-9" />
              </div>
              {filterControls}
              {hasFilters && (
                <Button variant="ghost" size="sm" className="h-9 px-2 text-muted-foreground hover:text-foreground" onClick={clearFilters}>
                  <FilterX className="h-4 w-4 mr-1" />Clear
                </Button>
              )}
            </div>
          )
        })()}
      </CardHeader>
      <CardContent>
        {isMobile ? (
          <MobileCardList
            data={deals}
            fields={mobileFields}
            getRowId={(d) => d.id}
            emptyMessage="No deals found."
            isLoading={isLoading}
            actions={(d) => (
              <>
                {canEdit && (
                  <Button size="sm" variant="outline" onClick={() => setEditDeal(d)}>
                    <Pencil className="h-3.5 w-3.5 mr-1" />Edit
                  </Button>
                )}
                {canDelete && (
                  <Button size="sm" variant="outline" className="text-destructive" onClick={() => setDeleteId(d.id)}>
                    <Trash2 className="h-3.5 w-3.5 mr-1" />Delete
                  </Button>
                )}
              </>
            )}
          />
        ) : (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                {visibleColumns.map((key) => {
                  const col = columnDefMap.get(key)
                  if (!col) return null
                  return (
                    <TableHead
                      key={key}
                      className="cursor-pointer select-none hover:bg-muted/50"
                      onClick={() => toggleSort(key)}
                    >
                      <div className="flex items-center gap-1">
                        {col.label}
                        {sortBy === key ? (
                          sortOrder === 'ASC' ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />
                        ) : (
                          <ChevronsUpDown className="h-3.5 w-3.5 text-muted-foreground/40" />
                        )}
                      </div>
                    </TableHead>
                  )
                })}
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow><TableCell colSpan={visibleColumns.length + 1} className="text-center py-8 text-muted-foreground">Loading...</TableCell></TableRow>
              ) : deals.length === 0 ? (
                <TableRow><TableCell colSpan={visibleColumns.length + 1} className="text-center py-8 text-muted-foreground">No deals found</TableCell></TableRow>
              ) : deals.map(d => (
                <Fragment key={d.id}>
                  <TableRow className="cursor-pointer hover:bg-muted/50" onClick={() => setExpandedRow(expandedRow === d.id ? null : d.id)}>
                    <TableCell className="w-8 px-2">
                      <ChevronDown className={`h-4 w-4 transition-transform ${expandedRow === d.id ? '' : '-rotate-90'}`} />
                    </TableCell>
                    {visibleColumns.map((key) => {
                      const col = columnDefMap.get(key)
                      return col ? <TableCell key={key} className={col.className}>{(col as ColumnDef<CrmDeal>).render(d)}</TableCell> : null
                    })}
                  </TableRow>
                  {expandedRow === d.id && (
                    <TableRow key={`${d.id}-expand`} className="bg-muted/30">
                      <TableCell colSpan={visibleColumns.length + 1} className="p-4">
                        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-x-6 gap-y-2 text-sm">
                          {detailFields.map(f => (
                            <div key={f.key}>
                              <span className="text-muted-foreground text-xs">{f.label}:</span>{' '}
                              <span className="font-medium">{formatVal(d[f.key])}</span>
                            </div>
                          ))}
                        </div>
                        {(canEdit || canDelete) && (
                          <div className="flex gap-2 mt-3 pt-3 border-t">
                            {canEdit && (
                              <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); setEditDeal(d) }}>
                                <Pencil className="h-3.5 w-3.5 mr-1" />Edit
                              </Button>
                            )}
                            {canDelete && (
                              <Button size="sm" variant="outline" className="text-destructive" onClick={(e) => { e.stopPropagation(); setDeleteId(d.id) }}>
                                <Trash2 className="h-3.5 w-3.5 mr-1" />Delete
                              </Button>
                            )}
                          </div>
                        )}
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              ))}
            </TableBody>
          </Table>
        </div>
        )}

        {/* Pagination + page size */}
        <div className="flex items-center justify-between mt-4">
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">{total.toLocaleString()} total</span>
            <Select value={String(limit)} onValueChange={v => { setLimit(Number(v)); setPage(0) }}>
              <SelectTrigger className="w-[80px] h-8 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="30">30</SelectItem>
                <SelectItem value="50">50</SelectItem>
                <SelectItem value="100">100</SelectItem>
              </SelectContent>
            </Select>
            <span className="text-xs text-muted-foreground">per page</span>
          </div>
          {total > limit && (
            <div className="flex gap-1">
              <Button size="sm" variant="outline" disabled={page === 0} onClick={() => setPage(p => p - 1)}><ChevronLeft className="h-4 w-4" /></Button>
              <span className="flex items-center px-2 text-sm">{page + 1}/{Math.ceil(total / limit)}</span>
              <Button size="sm" variant="outline" disabled={(page + 1) * limit >= total} onClick={() => setPage(p => p + 1)}><ChevronRight className="h-4 w-4" /></Button>
            </div>
          )}
        </div>
      </CardContent>

      {/* Edit dialog */}
      <EditDealDialog deal={editDeal} open={!!editDeal} onOpenChange={(open) => { if (!open) setEditDeal(null) }} />

      {/* Delete confirm */}
      <ConfirmDialog
        open={deleteId !== null}
        onOpenChange={(open) => { if (!open) setDeleteId(null) }}
        title="Delete Deal"
        description="This will permanently delete this deal record. This action cannot be undone."
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={() => deleteId && deleteMutation.mutate(deleteId)}
      />
    </Card>
  )
}
