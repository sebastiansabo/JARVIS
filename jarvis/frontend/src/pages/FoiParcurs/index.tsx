import React, { useState, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  FileText,
  Plus,
  Eye,
  ChevronLeft,
  Fuel,
  Route,
  Search,
  UserPlus,
  Check,
  ArrowUpDown,
  Trash2,
  Car,
  Pencil,
  XIcon,
  SlidersHorizontal,
  Settings,
  Save,
  Sparkles,
  MapPin,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import { EmptyState } from '@/components/shared/EmptyState'
import { TableSkeleton } from '@/components/shared/TableSkeleton'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DateField } from '@/components/ui/date-field'
import { SearchInput } from '@/components/shared/SearchInput'
import { useAuthStore } from '@/stores/authStore'
import { foiParcursApi } from '@/api/foiParcurs'
import { hrApi } from '@/api/hr'
import {
  FUEL_LEVEL_OPTIONS,
  fuelUnit,
  usesFuelTank,
  usesBattery,
  type FuelGaugeLevel,
  type BatchConfig,
  type PreviewResponse,
  type FoiContract,
  type FpVehicle,
} from '@/types/foiParcurs'
import { VehicleOdometerHistory } from './VehicleOdometerHistory'

// ── Main Page ──
export default function FoiParcurs() {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<'contracts' | 'parcurs' | 'stock' | 'settings'>('stock')
  const [companyId, setCompanyId] = useState<number>(0)
  const [brand, setBrand] = useState<string>('')

  const { data: companiesData } = useQuery({
    queryKey: ['fp-companies'],
    queryFn: () => foiParcursApi.getCompanies(),
    staleTime: 60_000,
  })

  // Auto-select first company
  const companies = companiesData?.companies ?? []
  if (companyId === 0 && companies.length > 0) {
    setCompanyId(companies[0].id)
  }

  // Brands for the selected company (from the company_brands catalog)
  const { data: brandsData } = useQuery({
    queryKey: ['fp-brands', companyId],
    queryFn: () => foiParcursApi.getBrands(companyId),
    enabled: companyId > 0,
    staleTime: 60_000,
  })
  const brands = brandsData?.brands ?? []

  // Auto-select first brand when the company (and thus its brand list) changes
  useEffect(() => {
    const list = brandsData?.brands ?? []
    if (list.length === 0) {
      if (brand !== '') setBrand('')
    } else if (!list.includes(brand)) {
      setBrand(list[0])
    }
  }, [brandsData, brand])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">Driving Hub</h1>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => navigate('/app/foi-parcurs/test-drive')}>
            <FileText className="mr-1.5 h-4 w-4" />
            New Test Drive
          </Button>
          <Select value={String(companyId)} onValueChange={(v) => setCompanyId(Number(v))}>
            <SelectTrigger className="w-56">
              <SelectValue placeholder="Selectează compania" />
            </SelectTrigger>
            <SelectContent>
              {companies.map((c) => (
                <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {brands.length > 0 && (
            <Select value={brand} onValueChange={setBrand}>
              <SelectTrigger className="w-44">
                <SelectValue placeholder="Selectează brandul" />
              </SelectTrigger>
              <SelectContent>
                {brands.map((b) => (
                  <SelectItem key={b} value={b}>{b}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'contracts' | 'parcurs' | 'stock' | 'settings')}>
        <TabsList>
          <TabsTrigger value="stock">Driving Park</TabsTrigger>
          <TabsTrigger value="contracts">Contracts</TabsTrigger>
          <TabsTrigger value="parcurs">Parcurs</TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
        </TabsList>
      </Tabs>

      {activeTab === 'contracts' && <ContractsTab companyId={companyId} brand={brand} />}
      {activeTab === 'parcurs' && <ParcursTab companyId={companyId} brand={brand} />}
      {activeTab === 'stock' && <StockTab companyId={companyId} brand={brand} />}
      {activeTab === 'settings' && <SettingsTab />}
    </div>
  )
}

// ── Contracts Tab — Form → Preview → Save Batch ──
type ContractStep = 'form' | 'preview' | 'saved'

function ContractsTab({ companyId, brand }: { companyId: number; brand: string }) {
  const queryClient = useQueryClient()
  const [step, setStep] = useState<ContractStep>('form')
  const [batchConfig, setBatchConfig] = useState<BatchConfig | null>(null)
  const [preview, setPreview] = useState<PreviewResponse | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')

  const handlePreviewReady = useCallback(
    (config: BatchConfig, prev: PreviewResponse) => {
      setBatchConfig(config)
      setPreview(prev)
      setStep('preview')
    },
    []
  )

  const handleSaveBatch = async () => {
    if (!batchConfig || !preview) return
    setSaving(true)
    setSaveError('')
    try {
      await foiParcursApi.saveBatch(batchConfig, preview)
      setStep('saved')
      queryClient.invalidateQueries({ queryKey: ['foi-contracts'] })
      queryClient.invalidateQueries({ queryKey: ['foi-contracts-all'] })
    } catch (err: any) {
      setSaveError(err?.data?.error || err?.message || 'Failed to save batch')
    } finally {
      setSaving(false)
    }
  }

  const handleReset = useCallback(() => {
    setStep('form')
    setBatchConfig(null)
    setPreview(null)
    setSaveError('')
  }, [])

  return (
    <div className="space-y-6">
      {step !== 'form' && (
        <div className="flex justify-end">
          <Button variant="outline" size="sm" onClick={handleReset}>
            <Plus className="mr-1.5 h-4 w-4" />
            New Batch
          </Button>
        </div>
      )}

      {/* Step 1: Batch Config Form */}
      {step === 'form' && <BatchConfigForm companyId={companyId} brand={brand} onPreview={handlePreviewReady} />}

      {/* Step 2: Preview — Save or Regenerate */}
      {step === 'preview' && preview && batchConfig && (
        <PreviewPanel
          preview={preview}
          config={batchConfig}
          onSave={handleSaveBatch}
          saving={saving}
          saveError={saveError}
          onBack={() => setStep('form')}
        />
      )}

      {/* Step 3: Saved confirmation */}
      {step === 'saved' && (
        <Card className="p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="rounded-full bg-green-100 p-2 dark:bg-green-900">
              <Check className="h-5 w-5 text-green-600 dark:text-green-400" />
            </div>
            <div>
              <h3 className="font-semibold">
                Batch saved — {preview?.assignments.clients.length} contracts generated
              </h3>
              <p className="text-sm text-muted-foreground">
                VIN: {batchConfig?.vin} | {preview?.assignments.num_test_drives} TD
                + {preview?.assignments.num_comadats} Comodat
              </p>
              <p className="text-sm text-muted-foreground mt-1">
                Go to the <span className="font-medium">Parcurs</span> tab to allocate clients.
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            <Button onClick={handleReset}>
              <Plus className="mr-1.5 h-4 w-4" />
              New Batch
            </Button>
          </div>
        </Card>
      )}

      {/* Recent Contracts — grouped by VIN */}
      <RecentContractsGrouped />
    </div>
  )
}

// ── Recent Contracts grouped by VIN ──
function RecentContractsGrouped() {
  const [expandedVins, setExpandedVins] = useState<Set<string>>(new Set())

  const { data, isLoading } = useQuery({
    queryKey: ['foi-contracts-all'],
    queryFn: () =>
      foiParcursApi.getContracts({ per_page: 500, sort_by: 'created_at', sort_dir: 'DESC' }),
    staleTime: 30_000,
  })

  const contracts = data?.contracts ?? []

  const toggleVin = (vin: string) => {
    setExpandedVins((prev) => {
      const next = new Set(prev)
      if (next.has(vin)) next.delete(vin)
      else next.add(vin)
      return next
    })
  }

  // Group by VIN
  const byVin: Record<string, typeof contracts> = {}
  for (const c of contracts) {
    if (!byVin[c.vin]) byVin[c.vin] = []
    byVin[c.vin].push(c)
  }
  const vins = Object.keys(byVin).sort()

  return (
    <div className="space-y-3">
      <h3 className="text-lg font-semibold">Recent Contracts</h3>
      {isLoading ? (
        <TableSkeleton rows={5} columns={6} />
      ) : !contracts.length ? (
        <EmptyState
          icon={<FileText className="h-10 w-10" />}
          title="No contracts yet"
          description="Create your first batch using the form above."
        />
      ) : (
        vins.map((vin) => {
          const vinContracts = byVin[vin]
          const vinOpen = expandedVins.has(vin)
          const pendingCount = vinContracts.filter((c) => c.status === 'PENDING').length
          const companyName = vinContracts[0]?.company_name

          return (
            <Card key={vin} className="overflow-hidden">
              <button
                className="w-full flex items-center justify-between px-5 py-3 hover:bg-muted/50 transition-colors"
                onClick={() => toggleVin(vin)}
              >
                <div className="flex items-center gap-2">
                  <Car className="h-4 w-4 text-muted-foreground" />
                  <span className="font-mono text-sm font-medium">{vin}</span>
                  {companyName && (
                    <span className="text-xs text-muted-foreground">({companyName})</span>
                  )}
                  <Badge variant="outline">{vinContracts.length} contracts</Badge>
                  {pendingCount > 0 && (
                    <Badge variant="destructive" className="text-xs">{pendingCount} pending</Badge>
                  )}
                </div>
                {vinOpen ? (
                  <ChevronUp className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                )}
              </button>
              {vinOpen && (
                <div className="border-t px-5 pb-3">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>#</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>Distance</TableHead>
                        <TableHead>KM</TableHead>
                        <TableHead>Client</TableHead>
                        <TableHead>Itinerary</TableHead>
                        <TableHead>Advisor</TableHead>
                        <TableHead>Date</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {vinContracts.map((c) => (
                        <TableRow key={c.id} className={c.status === 'PENDING' ? 'bg-orange-500/5' : ''}>
                          <TableCell className="text-xs">{c.slot_number || '—'}</TableCell>
                          <TableCell>
                            <Badge variant={c.status === 'FILLED' ? 'default' : 'destructive'} className="text-xs">
                              {c.status}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Badge variant={c.route_type === 'TD' ? 'default' : 'secondary'}>{c.route_type}</Badge>
                          </TableCell>
                          <TableCell>{c.distance_km} km</TableCell>
                          <TableCell className="text-xs">{c.km_start} - {c.km_end}</TableCell>
                          <TableCell>
                            {c.client_name ? (
                              <span className="font-medium">{c.client_name}</span>
                            ) : (
                              <span className="text-muted-foreground text-xs">—</span>
                            )}
                          </TableCell>
                          <TableCell className="max-w-[150px] truncate text-xs">{c.itinerary || '—'}</TableCell>
                          <TableCell className="text-sm">{c.advisor_name || '—'}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {new Date(c.created_at).toLocaleDateString('ro-RO')}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </Card>
          )
        })
      )}
    </div>
  )
}

// ── Parcurs Tab — all contracts grouped by Company → VIN ──
const STATUS_ROW_BG: Record<string, string> = {
  pending: 'bg-orange-500/5 border-l-4 border-l-orange-500/50',
  filled: 'bg-green-500/5 border-l-4 border-l-green-500/50',
}

function ParcursTab({ companyId, brand }: { companyId: number; brand: string }) {
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const now = new Date()
  const [allocatingContract, setAllocatingContract] = useState<FoiContract | null>(null)
  const [expandedRow, setExpandedRow] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [filterVin, setFilterVin] = useState<string>('all')
  const [filterStatus, setFilterStatus] = useState<string>('all')
  const [filterMonth, setFilterMonth] = useState<string>(String(now.getMonth() + 1))
  const [filterYear, setFilterYear] = useState<string>(String(now.getFullYear()))
  const [sortBy, setSortBy] = useState('slot_number')
  const [sortDir, setSortDir] = useState('ASC')

  const { data, isLoading } = useQuery({
    queryKey: ['foi-contracts-all', companyId],
    queryFn: () =>
      foiParcursApi.getContracts({ company_id: companyId || undefined, per_page: 1000, sort_by: 'created_at', sort_dir: 'DESC' }),
    staleTime: 30_000,
  })

  // Vehicles → vin→brand map, so contracts can be filtered by the selected brand
  const { data: vehiclesData } = useQuery({
    queryKey: ['fp-vehicles'],
    queryFn: () => foiParcursApi.getVehicles(),
    staleTime: 30_000,
  })
  const vinBrand = new Map((vehiclesData?.vehicles ?? []).map((v) => [v.vin, v.brand]))

  const allContracts = data?.contracts ?? []

  // Apply filters
  const filtered = allContracts.filter((c) => {
    if (brand && vinBrand.get(c.vin) !== brand) return false
    if (filterVin !== 'all' && c.vin !== filterVin) return false
    if (filterStatus !== 'all' && c.status !== filterStatus) return false
    if (filterMonth !== 'all' && c.month != null && String(c.month) !== filterMonth) return false
    if (filterYear !== 'all' && c.year != null && String(c.year) !== filterYear) return false
    if (search) {
      const q = search.toLowerCase()
      const haystack = `${c.vin} ${c.client_name || ''} ${c.company_name || ''} ${c.itinerary || ''} ${c.advisor_name || ''}`.toLowerCase()
      if (!haystack.includes(q)) return false
    }
    return true
  })

  // Sort
  const sorted = [...filtered].sort((a, b) => {
    const aVal = (a as any)[sortBy] ?? ''
    const bVal = (b as any)[sortBy] ?? ''
    const cmp = typeof aVal === 'number' ? aVal - bVal : String(aVal).localeCompare(String(bVal))
    return sortDir === 'ASC' ? cmp : -cmp
  })

  const toggleSort = (col: string) => {
    if (sortBy === col) setSortDir((d) => (d === 'ASC' ? 'DESC' : 'ASC'))
    else { setSortBy(col); setSortDir('ASC') }
  }

  const pendingCount = filtered.filter((c) => c.status === 'PENDING').length
  const filledCount = filtered.filter((c) => c.status === 'FILLED').length

  // Unique VINs for filter
  const uniqueVins = [...new Set(allContracts.map((c) => c.vin))].sort()

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[200px] max-w-sm">
          <SearchInput value={search} onChange={setSearch} placeholder="Search VIN, client, itinerary..." />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Vehicle</Label>
          <Select value={filterVin} onValueChange={setFilterVin}>
            <SelectTrigger className="h-8 min-w-[140px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Vehicles</SelectItem>
              {uniqueVins.map((vin) => (
                <SelectItem key={vin} value={vin}>{vin.slice(0, 12)}...</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Status</Label>
          <Select value={filterStatus} onValueChange={setFilterStatus}>
            <SelectTrigger className="h-8 min-w-[120px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="PENDING">Pending</SelectItem>
              <SelectItem value="FILLED">Filled</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Month</Label>
          <Select value={filterMonth} onValueChange={setFilterMonth}>
            <SelectTrigger className="h-8 min-w-[110px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              {Array.from({ length: 12 }, (_, i) => (
                <SelectItem key={i + 1} value={String(i + 1)}>
                  {new Date(2024, i).toLocaleString('ro-RO', { month: 'long' })}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Year</Label>
          <Select value={filterYear} onValueChange={setFilterYear}>
            <SelectTrigger className="h-8 w-20 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              {Array.from({ length: 5 }, (_, i) => {
                const y = now.getFullYear() - 2 + i
                return <SelectItem key={y} value={String(y)}>{y}</SelectItem>
              })}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Summary badges */}
      <div className="flex gap-2 text-sm">
        <Badge variant="outline">{filtered.length} contracts</Badge>
        {pendingCount > 0 && <Badge variant="destructive">{pendingCount} pending</Badge>}
        {filledCount > 0 && <Badge className="bg-green-600">{filledCount} filled</Badge>}
      </div>

      {/* Table */}
      {isLoading ? (
        <TableSkeleton rows={8} columns={10} />
      ) : !sorted.length ? (
        <EmptyState
          icon={<FileText className="h-10 w-10" />}
          title="No contracts found"
          description={allContracts.length ? 'Try adjusting your filters.' : 'Generate and save a batch from the Contracts tab first.'}
        />
      ) : (
        <Card className="overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <SortableHeader col="slot_number" label="#" current={sortBy} dir={sortDir} toggle={toggleSort} />
                <SortableHeader col="status" label="Status" current={sortBy} dir={sortDir} toggle={toggleSort} />
                <TableHead>Company</TableHead>
                <SortableHeader col="vin" label="VIN" current={sortBy} dir={sortDir} toggle={toggleSort} />
                <SortableHeader col="route_type" label="Type" current={sortBy} dir={sortDir} toggle={toggleSort} />
                <SortableHeader col="distance_km" label="Distance" current={sortBy} dir={sortDir} toggle={toggleSort} />
                <TableHead>KM</TableHead>
                <TableHead>Client</TableHead>
                <TableHead>Itinerary</TableHead>
                <TableHead>Advisor</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((c) => {
                const isExpanded = expandedRow === c.id
                const u = fuelUnit(c.fuel_tank_capacity_liters > 100 ? 'Electric' : undefined)
                return (
                  <React.Fragment key={c.id}>
                    <TableRow
                      className={`cursor-pointer hover:bg-muted/40 ${STATUS_ROW_BG[c.status?.toLowerCase()] || ''}`}
                      onClick={() => setExpandedRow(isExpanded ? null : c.id)}
                    >
                      <TableCell className="text-xs">{c.slot_number || '—'}</TableCell>
                      <TableCell>
                        <Badge
                          variant={c.status === 'FILLED' ? 'default' : 'destructive'}
                          className="text-xs"
                        >
                          {c.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs">{c.company_name || '—'}</TableCell>
                      <TableCell className="font-mono text-xs">{c.vin.slice(0, 12)}...</TableCell>
                      <TableCell>
                        <Badge variant={c.route_type === 'TD' ? 'default' : 'secondary'}>
                          {c.route_type}
                        </Badge>
                      </TableCell>
                      <TableCell>{c.distance_km} km</TableCell>
                      <TableCell className="text-xs">{c.km_start} - {c.km_end}</TableCell>
                      <TableCell>
                        {c.client_name ? (
                          <span className="font-medium text-sm">{c.client_name}</span>
                        ) : (
                          <span className="text-muted-foreground text-xs">—</span>
                        )}
                      </TableCell>
                      <TableCell className="max-w-[150px] truncate text-xs">{c.itinerary || '—'}</TableCell>
                      <TableCell className="text-xs">{c.advisor_name || '—'}</TableCell>
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        {c.status === 'PENDING' ? (
                          <Button variant="outline" size="sm" onClick={() => setAllocatingContract(c)}>
                            <UserPlus className="mr-1 h-3.5 w-3.5" />
                            Allocate
                          </Button>
                        ) : (
                          <span className="text-xs text-green-600 flex items-center gap-1">
                            <Check className="h-3.5 w-3.5 shrink-0" />
                            {c.client_name || 'Filled'}
                          </span>
                        )}
                      </TableCell>
                    </TableRow>
                    {isExpanded && (
                      <TableRow className="bg-muted/30 border-l-4 border-l-primary/30">
                        <TableCell colSpan={11} className="px-6 py-4">
                          <div className="grid grid-cols-3 gap-6">
                            {/* Fuel */}
                            <div className="space-y-1.5">
                              <h4 className="text-xs font-semibold uppercase text-muted-foreground tracking-wide">Fuel</h4>
                              <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
                                <span className="text-muted-foreground text-xs">Tank</span>
                                <span className="text-xs">{c.fuel_tank_capacity_liters}{u}</span>
                                <span className="text-muted-foreground text-xs">Gauge</span>
                                <span className="text-xs">{c.fuel_gauge_start_level} → {c.fuel_gauge_end_level}</span>
                                <span className="text-muted-foreground text-xs">Start</span>
                                <span className="text-xs">{c.fuel_start_liters}{u}</span>
                                <span className="text-muted-foreground text-xs">End</span>
                                <span className="text-xs">{c.fuel_end_liters}{u}</span>
                                <span className="text-muted-foreground text-xs">Consumed</span>
                                <span className="text-xs font-medium">{c.fuel_consumed_liters}{u}</span>
                              </div>
                            </div>

                            {/* Client */}
                            <div className="space-y-1.5">
                              <h4 className="text-xs font-semibold uppercase text-muted-foreground tracking-wide">Client</h4>
                              {c.client_name ? (
                                <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
                                  <span className="text-muted-foreground">Name</span>
                                  <span className="font-medium">{c.client_name}</span>
                                  {c.client_phone && (
                                    <>
                                      <span className="text-muted-foreground">Phone</span>
                                      <span>{c.client_phone}</span>
                                    </>
                                  )}
                                  <span className="text-muted-foreground">Advisor</span>
                                  <span>{c.advisor_name || '—'}</span>
                                </div>
                              ) : (
                                <p className="text-xs text-muted-foreground">Not allocated yet</p>
                              )}
                            </div>

                            {/* Route */}
                            <div className="space-y-1.5">
                              <h4 className="text-xs font-semibold uppercase text-muted-foreground tracking-wide">Route</h4>
                              <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
                                <span className="text-muted-foreground">Itinerary</span>
                                <span>{c.itinerary || '—'}</span>
                                <span className="text-muted-foreground">Contract</span>
                                <span className="font-mono">{c.contract_id}</span>
                                <span className="text-muted-foreground">Batch</span>
                                <span className="font-mono">{c.batch_id || '—'}</span>
                                <span className="text-muted-foreground">Period</span>
                                <span>{c.month && c.year ? `${String(c.month).padStart(2, '0')}/${c.year}` : '—'}</span>
                                <span className="text-muted-foreground">Created</span>
                                <span>{new Date(c.created_at).toLocaleString('ro-RO')}</span>
                              </div>
                            </div>
                          </div>
                          {/* PDF Downloads */}
                          {c.status === 'FILLED' && (
                            <div className="flex gap-2 mt-3 pt-3 border-t">
                              <a href={foiParcursApi.getContractPdfUrl(c.id, 'legal')} target="_blank" rel="noopener">
                                <Button variant="outline" size="sm">
                                  <FileText className="mr-1.5 h-3.5 w-3.5" />
                                  Legal PDF
                                </Button>
                              </a>
                              <a href={foiParcursApi.getContractPdfUrl(c.id, 'custom')} target="_blank" rel="noopener">
                                <Button variant="outline" size="sm">
                                  <FileText className="mr-1.5 h-3.5 w-3.5" />
                                  Custom PDF
                                </Button>
                              </a>
                            </div>
                          )}
                        </TableCell>
                      </TableRow>
                    )}
                  </React.Fragment>
                )
              })}
            </TableBody>
          </Table>
        </Card>
      )}

      {/* Allocation Dialog */}
      {allocatingContract && (
        <AllocateClientDialog
          contractId={allocatingContract.id}
          defaultAdvisor={allocatingContract.advisor_name || user?.name || ''}
          defaultItinerary={allocatingContract.itinerary || ''}
          companyId={allocatingContract.company_id}
          routeType={allocatingContract.route_type as 'TD' | 'Comodat'}
          distanceKm={allocatingContract.distance_km}
          onClose={() => setAllocatingContract(null)}
          onAllocated={() => {
            setAllocatingContract(null)
            queryClient.invalidateQueries({ queryKey: ['foi-contracts-all'] })
          }}
        />
      )}
    </div>
  )
}

// ── Allocate Client Dialog ──
function AllocateClientDialog({
  contractId,
  defaultAdvisor,
  defaultItinerary,
  companyId,
  routeType,
  distanceKm,
  onClose,
  onAllocated,
}: {
  contractId: number
  defaultAdvisor: string
  defaultItinerary: string
  companyId: number
  routeType: 'TD' | 'Comodat'
  distanceKm: number
  onClose: () => void
  onAllocated: () => void
}) {
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedClient, setSelectedClient] = useState<{ id: number; name: string } | null>(null)
  const [itinerary, setItinerary] = useState(defaultItinerary)
  const [advisorName, setAdvisorName] = useState(defaultAdvisor)
  const [error, setError] = useState('')

  const { data: searchResults } = useQuery({
    queryKey: ['fp-clients-search', searchQuery],
    queryFn: () => foiParcursApi.searchClients(searchQuery, 10),
    enabled: searchQuery.length >= 2,
    staleTime: 10_000,
  })

  const allocateMutation = useMutation({
    mutationFn: () =>
      foiParcursApi.allocateClient(contractId, {
        client_id: selectedClient!.id,
        itinerary,
        advisor_name: advisorName,
      }),
    onSuccess: () => onAllocated(),
    onError: (err: any) => {
      setError(err?.data?.error || err?.message || 'Failed to allocate')
    },
  })

  const handleSubmit = () => {
    setError('')
    if (!selectedClient) return setError('Select a client')
    if (!advisorName.trim()) return setError('Advisor name is required')
    allocateMutation.mutate()
  }

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Allocate Client</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {/* Client search */}
          <div className="space-y-1.5">
            <Label className="text-xs">Client</Label>
            {selectedClient ? (
              <div className="flex items-center gap-2 mt-1">
                <Badge variant="outline" className="py-1.5 px-3">{selectedClient.name}</Badge>
                <Button variant="ghost" size="sm" onClick={() => setSelectedClient(null)}>Change</Button>
              </div>
            ) : (
              <div className="relative mt-1">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  className="pl-9"
                  placeholder="Search by name, phone..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
                {searchQuery.length >= 2 && searchResults?.clients && (
                  <div className="absolute z-10 mt-1 w-full rounded-md border bg-popover shadow-md max-h-48 overflow-y-auto">
                    {searchResults.clients.length === 0 ? (
                      <div className="p-3 text-sm text-muted-foreground">No clients found</div>
                    ) : (
                      searchResults.clients.map((c) => (
                        <button
                          key={c.id}
                          className="w-full px-3 py-2 text-left text-sm hover:bg-accent flex justify-between"
                          onClick={() => {
                            setSelectedClient({ id: c.id, name: c.name })
                            setSearchQuery('')
                          }}
                        >
                          <span className="font-medium">{c.name}</span>
                          <span className="text-muted-foreground">{c.phone}</span>
                        </button>
                      ))
                    )}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Itinerary with auto-fill */}
          <ItineraryField
            value={itinerary}
            companyId={companyId}
            routeType={routeType}
            distanceKm={distanceKm}
            onChange={(v) => setItinerary(v.slice(0, 500))}
          />

          {/* Advisor */}
          <div className="space-y-1.5">
            <Label className="text-xs">Advisor Name</Label>
            <Input value={advisorName} onChange={(e) => setAdvisorName(e.target.value)} className="mt-1" />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={allocateMutation.isPending}>
            {allocateMutation.isPending ? 'Allocating...' : 'Allocate Client'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Stock Tab (Vehicle CRUD) ──
const STOCK_COLUMNS = [
  { key: 'model', label: 'Model', default: true },
  { key: 'mark', label: 'Mark', default: true },
  { key: 'vin', label: 'VIN', default: true },
  { key: 'car_id', label: 'Car ID', default: true },
  { key: 'reg_number', label: 'Reg. No.', default: true },
  { key: 'brand', label: 'Brand', default: true },
  { key: 'color', label: 'Color', default: true },
  { key: 'fuel_type', label: 'Fuel Type', default: true },
  { key: 'capacity', label: 'Capacity', default: true },
  { key: 'odometer', label: 'Odometer', default: true },
  { key: 'company', label: 'Company', default: true },
] as const

type StockColumnKey = (typeof STOCK_COLUMNS)[number]['key']

// Unified value shape for the vehicle Add/Edit form (shared by the inline Add
// card and the Edit modal so the two never drift apart).
interface VehicleFormValue {
  car_id: string
  vin: string
  registration_number: string
  mark: string
  model: string
  color: string
  fuel_type: string
  fuel_tank_capacity_liters: number
  battery_capacity_kwh: number
  odometer_km: string
  company_id: string
}

function emptyVehicleForm(companyId?: number): VehicleFormValue {
  return {
    car_id: '', vin: '', registration_number: '', mark: '', model: '', color: '',
    fuel_type: 'Diesel', fuel_tank_capacity_liters: 50, battery_capacity_kwh: 0,
    odometer_km: '', company_id: companyId ? String(companyId) : '',
  }
}

function vehicleToForm(v: FpVehicle): VehicleFormValue {
  return {
    car_id: v.car_id || '',
    vin: v.vin,
    registration_number: v.registration_number || '',
    mark: v.mark,
    model: v.model,
    color: v.color || '',
    fuel_type: v.fuel_type || 'Diesel',
    fuel_tank_capacity_liters: v.fuel_tank_capacity_liters ?? 0,
    battery_capacity_kwh: v.battery_capacity_kwh ?? 0,
    odometer_km: v.odometer_km != null ? String(v.odometer_km) : '',
    company_id: v.company_id ? String(v.company_id) : '',
  }
}

/** The full vehicle field grid, in the canonical column order. Shared by the
 *  Add card and the Edit modal. Brand is read-only (set from the header on Add,
 *  kept as-is on Edit). */
function VehicleFormFields({
  value,
  onChange,
  brandLabel,
  companies,
}: {
  value: VehicleFormValue
  onChange: (patch: Partial<VehicleFormValue>) => void
  brandLabel: string
  companies: { id: number; company: string }[]
}) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <div className="space-y-1.5">
        <Label className="text-xs">Model</Label>
        <Input value={value.model} onChange={(e) => onChange({ model: e.target.value })} placeholder="e.g., EX90" required />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">Mark</Label>
        <Input value={value.mark} onChange={(e) => onChange({ mark: e.target.value })} placeholder="e.g., VOLVO" required />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">VIN</Label>
        <Input value={value.vin} onChange={(e) => onChange({ vin: e.target.value.toUpperCase() })} placeholder="e.g., YV1TFEVB1SG004808" required />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">Car ID</Label>
        <Input value={value.car_id} onChange={(e) => onChange({ car_id: e.target.value })} placeholder="internal ID" />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">Reg. No.</Label>
        <Input value={value.registration_number} onChange={(e) => onChange({ registration_number: e.target.value.toUpperCase() })} placeholder="e.g., CJ-01-ABC" />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">Brand</Label>
        <Input value={brandLabel} readOnly disabled />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">Color</Label>
        <Input value={value.color} onChange={(e) => onChange({ color: e.target.value })} placeholder="e.g., Soul Red" />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">Fuel Type</Label>
        <Select value={value.fuel_type} onValueChange={(v) => onChange({ fuel_type: v })}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="Benzina">Benzina</SelectItem>
            <SelectItem value="Diesel">Diesel</SelectItem>
            <SelectItem value="Electric">Electric</SelectItem>
            <SelectItem value="Hybrid">Hybrid</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {usesFuelTank(value.fuel_type) && (
        <div className="space-y-1.5">
          <Label className="text-xs">Fuel capacity (L)</Label>
          <Input type="number" min={1} value={value.fuel_tank_capacity_liters} onChange={(e) => onChange({ fuel_tank_capacity_liters: Number(e.target.value) })} required />
        </div>
      )}
      {usesBattery(value.fuel_type) && (
        <div className="space-y-1.5">
          <Label className="text-xs">Battery capacity (kWh)</Label>
          <Input type="number" min={1} value={value.battery_capacity_kwh} onChange={(e) => onChange({ battery_capacity_kwh: Number(e.target.value) })} required />
        </div>
      )}
      <div className="space-y-1.5">
        <Label className="text-xs">Starting odometer (km)</Label>
        <Input type="number" min={0} value={value.odometer_km} onChange={(e) => onChange({ odometer_km: e.target.value })} placeholder="e.g., 12" />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">Company</Label>
        <Select value={value.company_id} onValueChange={(v) => onChange({ company_id: v })}>
          <SelectTrigger><SelectValue placeholder="Select company..." /></SelectTrigger>
          <SelectContent>
            {companies.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
    </div>
  )
}

function StockTab({ companyId, brand }: { companyId: number; brand: string }) {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [expandedVehicleId, setExpandedVehicleId] = useState<number | string | null>(null)
  const [editVehicle, setEditVehicle] = useState<FpVehicle | null>(null)
  const [editForm, setEditForm] = useState<VehicleFormValue>(emptyVehicleForm())
  const [editError, setEditError] = useState('')
  const [visibleCols, setVisibleCols] = useState<Set<StockColumnKey>>(
    new Set(STOCK_COLUMNS.filter((c) => c.default).map((c) => c.key))
  )
  const [showColMenu, setShowColMenu] = useState(false)
  const [newVehicle, setNewVehicle] = useState<VehicleFormValue>(() => emptyVehicleForm(companyId))
  const [error, setError] = useState('')

  const { data: vehiclesData, isLoading } = useQuery({
    queryKey: ['fp-vehicles', companyId],
    queryFn: () => foiParcursApi.getVehicles(),
    staleTime: 30_000,
  })

  // Filter vehicles by selected company and brand
  const filteredVehicles = vehiclesData?.vehicles?.filter(
    (v) => (!companyId || v.company_id === companyId) && (!brand || v.brand === brand)
  ) ?? []

  const { data: companiesData } = useQuery({
    queryKey: ['fp-companies'],
    queryFn: () => foiParcursApi.getCompanies(),
    staleTime: 60_000,
  })

  const createMutation = useMutation({
    mutationFn: () =>
      foiParcursApi.createVehicle({
        vin: newVehicle.vin.toUpperCase().trim(),
        registration_number: newVehicle.registration_number.trim() || undefined,
        car_id: newVehicle.car_id.trim() || undefined,
        mark: newVehicle.mark.trim(),
        brand: brand || undefined,
        model: newVehicle.model.trim(),
        color: newVehicle.color.trim() || undefined,
        fuel_type: newVehicle.fuel_type,
        fuel_tank_capacity_liters: usesFuelTank(newVehicle.fuel_type) ? newVehicle.fuel_tank_capacity_liters : null,
        battery_capacity_kwh: usesBattery(newVehicle.fuel_type) ? newVehicle.battery_capacity_kwh : null,
        odometer_km: newVehicle.odometer_km.trim() === '' ? null : Number(newVehicle.odometer_km),
        company_id: newVehicle.company_id ? Number(newVehicle.company_id) : undefined,
      }),
    onSuccess: () => {
      setError('')
      setShowAdd(false)
      setNewVehicle(emptyVehicleForm(companyId))
      queryClient.invalidateQueries({ queryKey: ['fp-vehicles'] })
    },
    onError: (err: any) => {
      setError(err?.data?.error || err?.message || 'Failed to create vehicle')
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) =>
      foiParcursApi.updateVehicle(id, data),
    onSuccess: () => {
      setEditVehicle(null)
      setEditError('')
      queryClient.invalidateQueries({ queryKey: ['fp-vehicles'] })
    },
    onError: (err: any) => {
      setEditError(err?.data?.error || err?.message || 'Failed to update vehicle')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => foiParcursApi.deleteVehicle(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fp-vehicles'] })
    },
  })

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (!newVehicle.vin.trim()) return setError('VIN is required')
    if (!newVehicle.mark.trim()) return setError('Mark is required')
    if (!newVehicle.model.trim()) return setError('Model is required')
    if (usesFuelTank(newVehicle.fuel_type) && newVehicle.fuel_tank_capacity_liters <= 0) return setError('Fuel capacity (L) must be positive')
    if (usesBattery(newVehicle.fuel_type) && newVehicle.battery_capacity_kwh <= 0) return setError('Battery capacity (kWh) must be positive')
    createMutation.mutate()
  }

  const startEdit = (v: FpVehicle) => {
    setEditError('')
    setEditVehicle(v)
    setEditForm(vehicleToForm(v))
  }

  const saveEdit = () => {
    if (!editVehicle) return
    setEditError('')
    if (!editForm.vin.trim()) return setEditError('VIN is required')
    if (!editForm.mark.trim()) return setEditError('Mark is required')
    if (!editForm.model.trim()) return setEditError('Model is required')
    const ft = editForm.fuel_type
    if (usesFuelTank(ft) && editForm.fuel_tank_capacity_liters <= 0) return setEditError('Fuel capacity (L) must be positive')
    if (usesBattery(ft) && editForm.battery_capacity_kwh <= 0) return setEditError('Battery capacity (kWh) must be positive')
    updateMutation.mutate({
      id: editVehicle.id,
      data: {
        vin: editForm.vin.toUpperCase().trim(),
        registration_number: editForm.registration_number.trim() || null,
        car_id: editForm.car_id.trim() || null,
        mark: editForm.mark.trim(),
        model: editForm.model.trim(),
        color: editForm.color.trim() || null,
        fuel_type: ft,
        fuel_tank_capacity_liters: usesFuelTank(ft) ? Number(editForm.fuel_tank_capacity_liters) : null,
        battery_capacity_kwh: usesBattery(ft) ? Number(editForm.battery_capacity_kwh) : null,
        odometer_km: editForm.odometer_km.trim() === '' ? null : Number(editForm.odometer_km),
        company_id: editForm.company_id ? Number(editForm.company_id) : null,
      },
    })
  }

  const toggleCol = (key: StockColumnKey) => {
    setVisibleCols((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const show = (key: StockColumnKey) => visibleCols.has(key)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <Car className="h-5 w-5 text-muted-foreground" />
          Driving Park
        </h3>
        <div className="flex gap-2">
          <div className="relative">
            <Button size="sm" variant="outline" onClick={() => setShowColMenu(!showColMenu)}>
              <SlidersHorizontal className="mr-1.5 h-4 w-4" />
              Columns
            </Button>
            {showColMenu && (
              <div className="absolute right-0 z-10 mt-1 w-44 rounded-md border bg-popover p-2 shadow-md">
                {STOCK_COLUMNS.map((c) => (
                  <label key={c.key} className="flex items-center gap-2 py-1 text-sm cursor-pointer">
                    <input
                      type="checkbox"
                      checked={visibleCols.has(c.key)}
                      onChange={() => toggleCol(c.key)}
                      className="rounded"
                    />
                    {c.label}
                  </label>
                ))}
              </div>
            )}
          </div>
          <Button size="sm" onClick={() => setShowAdd(!showAdd)}>
            <Plus className="mr-1.5 h-4 w-4" />
            Add Vehicle
          </Button>
        </div>
      </div>

      {/* Inline Add Form */}
      {showAdd && (
        <Card className="p-4">
          <form onSubmit={handleCreate} className="space-y-4">
            <VehicleFormFields
              value={newVehicle}
              onChange={(patch) => setNewVehicle((p) => ({ ...p, ...patch }))}
              brandLabel={brand || '—'}
              companies={companiesData?.companies ?? []}
            />
            {error && <p className="text-sm text-destructive">{error}</p>}
            <div className="flex gap-2">
              <Button type="submit" size="sm" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Adding...' : 'Add Vehicle'}
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => { setShowAdd(false); setError('') }}>
                Cancel
              </Button>
            </div>
          </form>
        </Card>
      )}

      {/* Vehicles Table */}
      {isLoading ? (
        <TableSkeleton rows={4} columns={7} />
      ) : !filteredVehicles.length ? (
        <EmptyState
          icon={<Car className="h-10 w-10" />}
          title="No vehicles in stock"
          description="Add your first vehicle using the button above."
        />
      ) : (
        <Card className="overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                {show('model') && <TableHead>Model</TableHead>}
                {show('mark') && <TableHead>Mark</TableHead>}
                {show('vin') && <TableHead>VIN</TableHead>}
                {show('car_id') && <TableHead>Car ID</TableHead>}
                {show('reg_number') && <TableHead>Reg. No.</TableHead>}
                {show('brand') && <TableHead>Brand</TableHead>}
                {show('color') && <TableHead>Color</TableHead>}
                {show('fuel_type') && <TableHead>Fuel Type</TableHead>}
                {show('capacity') && <TableHead>Capacity</TableHead>}
                {show('odometer') && <TableHead>Odometer</TableHead>}
                {show('company') && <TableHead>Company</TableHead>}
                <TableHead className="w-[100px]">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredVehicles.map((v) => (
                <React.Fragment key={v.id}>
                <TableRow
                  className="cursor-pointer hover:bg-muted/40"
                  onClick={() => setExpandedVehicleId((prev) => (prev === v.id ? null : v.id))}
                >
                  {show('model') && <TableCell>{v.model}</TableCell>}
                  {show('mark') && <TableCell>{v.mark}</TableCell>}
                  {show('vin') && <TableCell className="font-mono text-xs">{v.vin}</TableCell>}
                  {show('car_id') && <TableCell className="text-sm">{v.car_id || '—'}</TableCell>}
                  {show('reg_number') && <TableCell className="text-sm">{v.registration_number || '—'}</TableCell>}
                  {show('brand') && <TableCell className="text-sm">{v.brand || '—'}</TableCell>}
                  {show('color') && <TableCell className="text-sm">{v.color || '—'}</TableCell>}
                  {show('fuel_type') && (
                    <TableCell><Badge variant="outline">{v.fuel_type}</Badge></TableCell>
                  )}
                  {show('capacity') && (
                    <TableCell className="text-sm whitespace-nowrap">
                      {[
                        usesFuelTank(v.fuel_type) && v.fuel_tank_capacity_liters ? `${v.fuel_tank_capacity_liters} L` : null,
                        usesBattery(v.fuel_type) && v.battery_capacity_kwh ? `${v.battery_capacity_kwh} kWh` : null,
                      ].filter(Boolean).join(' + ') || '—'}
                    </TableCell>
                  )}
                  {show('odometer') && (
                    <TableCell className="text-sm whitespace-nowrap">{v.odometer_km != null ? `${v.odometer_km.toLocaleString('ro-RO')} km` : '—'}</TableCell>
                  )}
                  {show('company') && (
                    <TableCell className="text-sm text-muted-foreground">{v.company_name || '—'}</TableCell>
                  )}
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="sm" onClick={() => startEdit(v)}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={() => deleteMutation.mutate(v.id)}
                        disabled={deleteMutation.isPending}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
                {expandedVehicleId === v.id && v.vin && (
                  <TableRow className="bg-muted/30 border-l-4 border-l-primary/30 hover:bg-muted/30">
                    <TableCell colSpan={12} className="p-0">
                      <VehicleOdometerHistory vin={v.vin} />
                    </TableCell>
                  </TableRow>
                )}
                </React.Fragment>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      {/* Edit Vehicle Modal */}
      <Dialog open={!!editVehicle} onOpenChange={(open) => { if (!open) { setEditVehicle(null); setEditError('') } }}>
        <DialogContent className="max-w-[min(95vw,1400px)] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Edit Vehicle</DialogTitle>
          </DialogHeader>
          <VehicleFormFields
            value={editForm}
            onChange={(patch) => setEditForm((p) => ({ ...p, ...patch }))}
            brandLabel={editVehicle?.brand || '—'}
            companies={companiesData?.companies ?? []}
          />
          {editError && <p className="text-sm text-destructive">{editError}</p>}
          <DialogFooter>
            <Button variant="outline" onClick={() => { setEditVehicle(null); setEditError('') }}>Cancel</Button>
            <Button onClick={saveEdit} disabled={updateMutation.isPending}>
              {updateMutation.isPending ? 'Saving...' : 'Save'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ── Sortable Header ──
function SortableHeader({
  col,
  label,
  current,
  dir,
  toggle,
}: {
  col: string
  label: string
  current: string
  dir: string
  toggle: (col: string) => void
}) {
  return (
    <TableHead
      className="cursor-pointer select-none"
      onClick={() => toggle(col)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        <ArrowUpDown
          className={`h-3 w-3 ${current === col ? 'text-foreground' : 'text-muted-foreground/50'}`}
        />
        {current === col && (
          <span className="text-[10px]">{dir === 'ASC' ? '\u2191' : '\u2193'}</span>
        )}
      </span>
    </TableHead>
  )
}

// ── Batch Config Form ──
function BatchConfigForm({
  companyId: defaultCompanyId,
  brand,
  onPreview,
}: {
  companyId: number
  brand: string
  onPreview: (config: BatchConfig, preview: PreviewResponse) => void
}) {
  const now = new Date()
  const [form, setForm] = useState({
    year: String(now.getFullYear()),
    month: String(now.getMonth() + 1),
    company_id: defaultCompanyId ? String(defaultCompanyId) : '',
    vin: '',
    odometer_start: '',
    odometer_end: '',
    num_clients: '5',
    num_td: '3',
    fuel_tank_capacity_liters: '75',
    fuel_gauge_start_level: '1' as FuelGaugeLevel,
    fuel_gauge_end_level: '1/2' as FuelGaugeLevel,
    total_consumption_period_liters: '15',
  })
  const [trips, setTrips] = useState<{ date_from: string; date_to: string; location: string; estimated_km: string }[]>([])
  const [fuelings, setFuelings] = useState<{ doc_number: string; liters: string; date: string }[]>([])
  const [error, setError] = useState('')

  const set = (k: string, v: string) => setForm((p) => ({ ...p, [k]: v }))

  const numClients = Number(form.num_clients || 0)
  const numTd = Number(form.num_td || 0)
  const numComodat = Math.max(0, numClients - numTd)
  const totalKm =
    Number(form.odometer_end || 0) - Number(form.odometer_start || 0)

  // Vehicle list for VIN dropdown
  const { data: vehiclesData } = useQuery({
    queryKey: ['fp-vehicles'],
    queryFn: () => foiParcursApi.getVehicles(),
    staleTime: 30_000,
  })

  const { data: companiesData } = useQuery({
    queryKey: ['fp-companies'],
    queryFn: () => foiParcursApi.getCompanies(),
    staleTime: 60_000,
  })

  const filteredVehicles = vehiclesData?.vehicles?.filter(
    (v) => (!form.company_id || v.company_id === Number(form.company_id)) &&
           (!brand || v.brand === brand)
  )
  const selectedVehicle = vehiclesData?.vehicles?.find((v) => v.vin === form.vin)

  // When company changes, clear VIN if the selected vehicle doesn't belong to the new company
  const handleCompanyChange = (companyId: string) => {
    set('company_id', companyId)
    if (form.vin && companyId) {
      const vehicle = vehiclesData?.vehicles?.find((v) => v.vin === form.vin)
      if (vehicle && vehicle.company_id !== Number(companyId)) {
        set('vin', '')
      }
    }
  }

  // When num_clients changes, clamp num_td
  const handleNumClientsChange = (val: string) => {
    const nc = Math.max(1, Number(val || 0))
    set('num_clients', String(nc))
    if (numTd > nc) {
      set('num_td', String(nc))
    }
  }

  const handleNumTdChange = (val: string) => {
    const td = Math.max(0, Math.min(Number(val || 0), numClients))
    set('num_td', String(td))
  }

  const handleVinChange = (vin: string) => {
    set('vin', vin)
    const vehicle = vehiclesData?.vehicles?.find((v) => v.vin === vin)
    if (vehicle) {
      set('fuel_tank_capacity_liters', String(vehicle.fuel_tank_capacity_liters))
    }
  }

  const u = fuelUnit(selectedVehicle?.fuel_type)
  const fuelingsTotal = fuelings.reduce((sum, f) => sum + Number(f.liters || 0), 0)

  // Period boundaries
  const periodYear = Number(form.year)
  const periodMonth = Number(form.month)
  const periodMin = `${periodYear}-${String(periodMonth).padStart(2, '0')}-01`
  const periodLastDay = new Date(periodYear, periodMonth, 0).getDate()
  const periodMax = `${periodYear}-${String(periodMonth).padStart(2, '0')}-${String(periodLastDay).padStart(2, '0')}`
  const periodLabel = new Date(periodYear, periodMonth - 1).toLocaleString('ro-RO', { month: 'long', year: 'numeric' })

  const previewMutation = useMutation({
    mutationFn: (config: BatchConfig) => foiParcursApi.preview(config),
    onSuccess: (data, config) => {
      setError('')
      onPreview(config, data)
    },
    onError: (err: any) => {
      setError(err?.data?.error || err?.message || 'Preview failed')
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    const config: BatchConfig = {
      year: periodYear,
      month: periodMonth,
      company_id: Number(form.company_id),
      vin: form.vin.trim(),
      fuel_type: selectedVehicle?.fuel_type || 'Diesel',
      odometer_start: Number(form.odometer_start),
      odometer_end: Number(form.odometer_end),
      num_clients: numClients,
      num_td: numTd,
      num_comodat: numComodat,
      fuel_tank_capacity_liters: Number(form.fuel_tank_capacity_liters),
      fuel_gauge_start_level: form.fuel_gauge_start_level,
      fuel_gauge_end_level: form.fuel_gauge_end_level,
      total_consumption_period_liters: fuelings.length > 0
        ? fuelingsTotal
        : Number(form.total_consumption_period_liters),
      fuelings: fuelings.length > 0
        ? fuelings.map((f) => ({ date: f.date, doc_number: f.doc_number, liters: Number(f.liters || 0) }))
        : undefined,
      trips: trips.length > 0
        ? trips.map((t) => ({ date_from: t.date_from, date_to: t.date_to, location: t.location, estimated_km: Number(t.estimated_km || 0) }))
        : undefined,
    }

    if (!config.vin) return setError('VIN is required')
    if (!config.company_id) return setError('Company is required')
    if (config.total_consumption_period_liters <= 0)
      return setError('Total consumption is required')
    if (config.odometer_end <= config.odometer_start)
      return setError('Odometer end must be greater than start')
    if (config.num_clients < 1)
      return setError('At least 1 client is required')
    if (config.num_td < 0 || config.num_td > config.num_clients)
      return setError('TD Routes must be between 0 and number of clients')

    previewMutation.mutate(config)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Route className="h-5 w-5 text-muted-foreground" />
          <h3 className="font-semibold text-lg">Generate Contracts Batch</h3>
        </div>
        <div className="flex items-center gap-2">
          <Select value={form.month} onValueChange={(v) => { set('month', v); setTrips([]); setFuelings([]) }}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Array.from({ length: 12 }, (_, i) => (
                <SelectItem key={i + 1} value={String(i + 1)}>
                  {new Date(2024, i).toLocaleString('ro-RO', { month: 'long' })}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={form.year} onValueChange={(v) => { set('year', v); setTrips([]); setFuelings([]) }}>
            <SelectTrigger className="w-24">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Array.from({ length: 5 }, (_, i) => {
                const y = now.getFullYear() - 2 + i
                return <SelectItem key={y} value={String(y)}>{y}</SelectItem>
              })}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Left column: Vehicle & Odometer */}
        <Card className="p-5 space-y-4">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Car className="h-4 w-4 text-muted-foreground" />
            Vehicle & Odometer
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Company</Label>
              <Select value={form.company_id} onValueChange={handleCompanyChange}>
                <SelectTrigger>
                  <SelectValue placeholder="Select company..." />
                </SelectTrigger>
                <SelectContent>
                  {companiesData?.companies?.map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">VIN</Label>
              <Select value={form.vin} onValueChange={handleVinChange}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a vehicle" />
                </SelectTrigger>
                <SelectContent>
                  {filteredVehicles?.map((v) => (
                    <SelectItem key={v.vin} value={v.vin}>
                      {v.vin} - {v.mark} {v.model}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {selectedVehicle && (
                <span className="text-xs text-muted-foreground">
                  {selectedVehicle.mark} {selectedVehicle.model} ({selectedVehicle.fuel_tank_capacity_liters}{fuelUnit(selectedVehicle.fuel_type)} tank)
                </span>
              )}
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Odometer Start (km)</Label>
              <Input
                type="number"
                value={form.odometer_start}
                onChange={(e) => set('odometer_start', e.target.value)}
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Odometer End (km)</Label>
              <Input
                type="number"
                value={form.odometer_end}
                onChange={(e) => set('odometer_end', e.target.value)}
                required
              />
              {totalKm > 0 && (
                <span className="text-xs text-muted-foreground">
                  Total: {totalKm} km
                </span>
              )}
            </div>
          </div>

          {/* Trips / Events — context for AI route generation */}
          <div className="space-y-3 border-t pt-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Trips & Events</span>
              <div className="flex gap-2">
                <FetchEventsButton periodMin={periodMin} periodMax={periodMax} periodLabel={periodLabel} onImport={(events) =>
                  setTrips((p) => [
                    ...p,
                    ...events.map((e) => ({
                      date_from: e.start_date,
                      date_to: e.end_date,
                      location: e.name,
                      estimated_km: '',
                    })),
                  ])
                } />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setTrips((p) => [...p, { date_from: '', date_to: '', location: '', estimated_km: '' }])}
                >
                  <Plus className="mr-1.5 h-3.5 w-3.5" />
                  Add Trip
                </Button>
              </div>
            </div>
            {trips.length === 0 && (
              <p className="text-xs text-muted-foreground">
                Add locations or events where the car was used. AI uses these to generate realistic itineraries.
              </p>
            )}
            {trips.map((t, i) => (
              <div key={i} className="space-y-2">
                <div className="grid grid-cols-[1fr_1fr_2fr_80px_32px] items-end gap-2">
                  <div>
                    {i === 0 && <Label className="text-xs">Departure</Label>}
                    <DateField
                      value={t.date_from}
                      onChange={(v) =>
                        setTrips((p) =>
                          p.map((x, j) => (j === i ? { ...x, date_from: v } : x))
                        )
                      }
                      placeholder="From"
                      min={periodMin}
                      max={periodMax}
                    />
                  </div>
                  <div>
                    {i === 0 && <Label className="text-xs">Return</Label>}
                    <DateField
                      value={t.date_to}
                      onChange={(v) =>
                        setTrips((p) =>
                          p.map((x, j) => (j === i ? { ...x, date_to: v } : x))
                        )
                      }
                      placeholder="To"
                      min={periodMin}
                      max={periodMax}
                    />
                  </div>
                  <div>
                    {i === 0 && <Label className="text-xs">Location / Event</Label>}
                    <Input
                      value={t.location}
                      onChange={(e) =>
                        setTrips((p) =>
                          p.map((x, j) => (j === i ? { ...x, location: e.target.value } : x))
                        )
                      }
                      placeholder="e.g., Turda, Client visit Bistrita"
                    />
                  </div>
                  <div>
                    {i === 0 && <Label className="text-xs">Est. KM</Label>}
                    <Input
                      type="number"
                      value={t.estimated_km}
                      onChange={(e) =>
                        setTrips((p) =>
                          p.map((x, j) => (j === i ? { ...x, estimated_km: e.target.value } : x))
                        )
                      }
                      placeholder="0"
                    />
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive self-end"
                    onClick={() => setTrips((p) => p.filter((_, j) => j !== i))}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
            {trips.length > 0 && (
              <div className="text-xs text-muted-foreground text-right">
                Est. total: {trips.reduce((s, t) => s + Number(t.estimated_km || 0), 0)} km
                {totalKm > 0 && (
                  <span> / {totalKm} km odometer</span>
                )}
              </div>
            )}
          </div>
        </Card>

        {/* Right column: Route Distribution + Fuel stacked */}
        <div className="space-y-4">
          <Card className="p-5 space-y-4">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Route className="h-4 w-4 text-muted-foreground" />
              Route Distribution
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs">Clients</Label>
                <Input
                  type="number"
                  min={1}
                  value={form.num_clients}
                  onChange={(e) => handleNumClientsChange(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">TD Routes</Label>
                <Input
                  type="number"
                  min={0}
                  max={numClients}
                  value={form.num_td}
                  onChange={(e) => handleNumTdChange(e.target.value)}
                  required
                />
                <span className="text-xs text-muted-foreground">
                  0 - {numClients}
                </span>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Comodat</Label>
                <Input type="number" value={numComodat} disabled />
                <span className="text-xs text-muted-foreground">
                  {numClients} - {numTd} = {numComodat}
                </span>
              </div>
            </div>
          </Card>

          <Card className="p-5 space-y-4">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Fuel className="h-4 w-4 text-muted-foreground" />
              Fuel
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs">Capacity ({u})</Label>
                <Input
                  type="number"
                  value={form.fuel_tank_capacity_liters}
                  disabled
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Total Consumption ({u})</Label>
                <Input
                  type="number"
                  value={fuelingsTotal || form.total_consumption_period_liters}
                  disabled={fuelings.length > 0}
                  onChange={(e) =>
                    set('total_consumption_period_liters', e.target.value)
                  }
                />
                {fuelings.length > 0 && (
                  <span className="text-xs text-muted-foreground">
                    Auto-calculated from {fuelings.length} fueling(s)
                  </span>
                )}
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Start Level</Label>
                <Select
                  value={form.fuel_gauge_start_level}
                  onValueChange={(v) => set('fuel_gauge_start_level', v)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {FUEL_LEVEL_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">End Level</Label>
                <Select
                  value={form.fuel_gauge_end_level}
                  onValueChange={(v) => set('fuel_gauge_end_level', v)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {FUEL_LEVEL_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Fueling Records */}
            <div className="space-y-3 border-t pt-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">Fuelings</span>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setFuelings((p) => [...p, { doc_number: '', liters: '', date: '' }])}
                >
                  <Plus className="mr-1.5 h-3.5 w-3.5" />
                  Add Fueling
                </Button>
              </div>
              {fuelings.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  No fuelings added. Enter total consumption manually or add fueling records.
                </p>
              )}
              {fuelings.map((f, i) => (
                <div key={i} className="flex items-end gap-2">
                  <div className="w-36">
                    {i === 0 && <Label className="text-xs">Date</Label>}
                    <DateField
                      value={f.date}
                      onChange={(v) =>
                        setFuelings((p) =>
                          p.map((x, j) => (j === i ? { ...x, date: v } : x))
                        )
                      }
                      placeholder="Date"
                      min={periodMin}
                      max={periodMax}
                    />
                  </div>
                  <div className="flex-1">
                    {i === 0 && <Label className="text-xs">Document No.</Label>}
                    <Input
                      value={f.doc_number}
                      onChange={(e) =>
                        setFuelings((p) =>
                          p.map((x, j) => (j === i ? { ...x, doc_number: e.target.value } : x))
                        )
                      }
                      placeholder="e.g., F-2024-001"
                    />
                  </div>
                  <div className="w-28">
                    {i === 0 && <Label className="text-xs">{u}</Label>}
                    <Input
                      type="number"
                      step="0.1"
                      value={f.liters}
                      onChange={(e) =>
                        setFuelings((p) =>
                          p.map((x, j) => (j === i ? { ...x, liters: e.target.value } : x))
                        )
                      }
                      placeholder="0"
                    />
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() => setFuelings((p) => p.filter((_, j) => j !== i))}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
              {fuelings.length > 0 && (
                <div className="text-sm font-medium text-right">
                  Total: {fuelingsTotal} {u}
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>

      {error && (
        <p className="text-sm text-destructive">{error}</p>
      )}

      <Button type="submit" disabled={previewMutation.isPending} className="w-full sm:w-auto">
        <Eye className="mr-1.5 h-4 w-4" />
        {previewMutation.isPending ? 'Calculating...' : 'Preview Contracts'}
      </Button>
    </form>
  )
}

// ── Preview Panel ──
function PreviewPanel({
  preview,
  config,
  onSave,
  saving,
  saveError,
  onBack,
}: {
  preview: PreviewResponse
  config: BatchConfig
  onSave: () => void
  saving: boolean
  saveError: string
  onBack: () => void
}) {
  const { assignments, fuel_distribution } = preview
  const u = fuelUnit(config.fuel_type)

  return (
    <Card className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Eye className="h-5 w-5 text-muted-foreground" />
          <h3 className="font-semibold text-lg">Preview</h3>
        </div>
        <div className="flex gap-2 text-sm">
          <Badge variant="default">{assignments.num_test_drives} TD</Badge>
          <Badge variant="secondary">{assignments.num_comadats} Comodat</Badge>
          <Badge variant="outline">{assignments.total_distance_km} km total</Badge>
        </div>
      </div>

      {/* Fuel Summary */}
      <div className="rounded-lg bg-muted/50 p-4 flex flex-wrap gap-6 text-sm">
        <div>
          <Fuel className="inline h-4 w-4 mr-1 text-muted-foreground" />
          <span className="text-muted-foreground">Tank:</span>{' '}
          {config.fuel_tank_capacity_liters}{u}
        </div>
        <div>
          <span className="text-muted-foreground">Start:</span>{' '}
          {config.fuel_gauge_start_level} ({fuel_distribution.start_liters}{u})
        </div>
        <div>
          <span className="text-muted-foreground">End:</span>{' '}
          {config.fuel_gauge_end_level} ({fuel_distribution.end_liters}{u})
        </div>
        <div>
          <span className="text-muted-foreground">Consumption:</span>{' '}
          {config.total_consumption_period_liters}{u} /{' '}
          {fuel_distribution.available_consumption}{u} available
        </div>
      </div>

      {/* Route Assignment Table */}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>#</TableHead>
            <TableHead>Route Type</TableHead>
            <TableHead>Distance</TableHead>
            <TableHead>KM Start</TableHead>
            <TableHead>KM End</TableHead>
            <TableHead>Fuel Start</TableHead>
            <TableHead>Fuel End</TableHead>
            <TableHead>Consumed</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {assignments.clients.map((c, i) => (
            <TableRow key={c.slot}>
              <TableCell>{c.slot}</TableCell>
              <TableCell>
                <Badge variant={c.route_type === 'TD' ? 'default' : 'secondary'}>
                  {c.route_type}
                </Badge>
              </TableCell>
              <TableCell>{c.distance_km} km</TableCell>
              <TableCell>{c.km_start}</TableCell>
              <TableCell>{c.km_end}</TableCell>
              <TableCell>
                {fuel_distribution.per_client[i].fuel_start_liters}{u}
              </TableCell>
              <TableCell>
                {fuel_distribution.per_client[i].fuel_end_liters}{u}
              </TableCell>
              <TableCell>
                {fuel_distribution.per_client[i].fuel_consumed_liters}{u}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <div className="flex gap-2">
        <Button variant="outline" onClick={onBack}>
          <ChevronLeft className="mr-1 h-4 w-4" />
          Regenerate
        </Button>
        <Button onClick={onSave} disabled={saving}>
          <Save className="mr-1.5 h-4 w-4" />
          {saving ? 'Saving...' : 'Save Batch'}
        </Button>
      </div>
      {saveError && (
        <p className="text-sm text-destructive">{saveError}</p>
      )}
    </Card>
  )
}


// ── Settings Tab — per-company KM limits for TD and Comodat ──
type CompanyKmConfig = {
  company_id: number
  company_name: string
  td_km_min: number
  td_km_max: number
  comodat_km_min: number
  comodat_km_max: number
  km_gap: number
}

// ── Fetch Events Button ──
function FetchEventsButton({
  onImport,
  periodMin,
  periodMax,
  periodLabel,
}: {
  onImport: (events: { name: string; start_date: string; end_date: string }[]) => void
  periodMin: string
  periodMax: string
  periodLabel: string
}) {
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())

  const { data, isLoading } = useQuery({
    queryKey: ['hr-events-for-trips'],
    queryFn: () => hrApi.getEvents(),
    enabled: open,
    staleTime: 60_000,
  })

  const events = data ?? []

  const isInPeriod = (e: { start_date: string; end_date: string }) => {
    return e.start_date <= periodMax && e.end_date >= periodMin
  }

  const toggle = (id: number) => {
    const event = events.find((e) => e.id === id)
    if (event && !isInPeriod(event)) return
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleImport = () => {
    const picked = events.filter((e) => selected.has(e.id))
    onImport(picked.map((e) => ({ name: e.name, start_date: e.start_date, end_date: e.end_date })))
    setSelected(new Set())
    setOpen(false)
  }

  return (
    <>
      <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)}>
        <Search className="mr-1.5 h-3.5 w-3.5" />
        From Events
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg max-h-[70vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Import from Events</DialogTitle>
          </DialogHeader>
          <p className="text-xs text-muted-foreground -mt-2">
            Period: <span className="font-medium capitalize">{periodLabel}</span>
          </p>
          <div className="flex-1 overflow-y-auto space-y-1">
            {isLoading ? (
              <TableSkeleton rows={4} columns={3} />
            ) : !events.length ? (
              <p className="text-sm text-muted-foreground py-4 text-center">No events found.</p>
            ) : (
              events.map((e) => {
                const inPeriod = isInPeriod(e)
                return (
                  <label
                    key={e.id}
                    className={`flex items-center gap-3 rounded-md border px-3 py-2 ${
                      inPeriod
                        ? 'cursor-pointer hover:bg-accent/50'
                        : 'opacity-50 cursor-not-allowed'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={selected.has(e.id)}
                      onChange={() => toggle(e.id)}
                      disabled={!inPeriod}
                      className="rounded"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">{e.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {e.start_date} → {e.end_date}
                        {e.company && <span className="ml-2">({e.company})</span>}
                      </div>
                      {!inPeriod && (
                        <div className="text-xs text-destructive mt-0.5">
                          Outside selected period
                        </div>
                      )}
                    </div>
                  </label>
                )
              })
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={handleImport} disabled={selected.size === 0}>
              Import {selected.size} Event{selected.size !== 1 ? 's' : ''}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

// ── Itinerary Field with AI Auto-Fill ──
function ItineraryField({
  value,
  companyId,
  routeType,
  distanceKm,
  onChange,
}: {
  value: string
  companyId: number
  routeType: 'TD' | 'Comodat'
  distanceKm: number
  onChange: (val: string) => void
}) {
  const [generating, setGenerating] = useState(false)

  // Comodat manual routes as fallback
  const { data: routesData } = useQuery({
    queryKey: ['fp-routes', companyId, 'Comodat'],
    queryFn: () => foiParcursApi.getRoutes(companyId, 'Comodat'),
    enabled: !!companyId && routeType === 'Comodat',
    staleTime: 30_000,
  })

  const comodatRoutes = routesData?.routes ?? []

  const autoFill = async () => {
    // For Comodat: try manual list first, fall back to AI
    if (routeType === 'Comodat' && comodatRoutes.length > 0) {
      const random = comodatRoutes[Math.floor(Math.random() * comodatRoutes.length)]
      onChange(random.itinerary)
      return
    }

    // AI generation for both TD and Comodat (when no manual routes)
    setGenerating(true)
    try {
      const result = await foiParcursApi.generateItinerary(companyId, routeType, distanceKm)
      onChange(result.itinerary)
    } catch {
      // silent — user can type manually
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <Label>Itinerary</Label>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 text-xs gap-1"
          onClick={autoFill}
          disabled={generating}
        >
          <Sparkles className="h-3.5 w-3.5" />
          {generating ? 'Generating...' : `Auto-fill (${routeType})`}
        </Button>
      </div>
      <Textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={`Click Auto-fill to generate a ${routeType} route or type manually...`}
        maxLength={500}
        rows={2}
        className="mt-1"
      />
      <span className="text-xs text-muted-foreground">
        {value.length}/500
      </span>
    </div>
  )
}

function SettingsTab() {
  const queryClient = useQueryClient()
  const [editId, setEditId] = useState<number | null>(null)
  const [editData, setEditData] = useState<{ td_km_min: number; td_km_max: number; comodat_km_min: number; comodat_km_max: number; km_gap: number }>({ td_km_min: 5, td_km_max: 50, comodat_km_min: 10, comodat_km_max: 200, km_gap: 20 })
  const [saveSuccess, setSaveSuccess] = useState<number | null>(null)

  const { data: companiesData } = useQuery({
    queryKey: ['fp-companies'],
    queryFn: () => foiParcursApi.getCompanies(),
    staleTime: 60_000,
  })

  const { data: configsData, isLoading } = useQuery({
    queryKey: ['fp-km-configs'],
    queryFn: () => foiParcursApi.getKmConfigs(),
    staleTime: 30_000,
  })

  const updateMutation = useMutation({
    mutationFn: ({ company_id, data }: { company_id: number; data: { td_km_min: number; td_km_max: number; comodat_km_min: number; comodat_km_max: number; km_gap: number } }) =>
      foiParcursApi.updateKmConfig(company_id, data),
    onSuccess: (_, variables) => {
      setEditId(null)
      setEditData({ td_km_min: 5, td_km_max: 50, comodat_km_min: 10, comodat_km_max: 200, km_gap: 20 })
      setSaveSuccess(variables.company_id)
      setTimeout(() => setSaveSuccess(null), 2000)
      queryClient.invalidateQueries({ queryKey: ['fp-km-configs'] })
    },
  })

  // Merge companies with their configs (show all companies, defaults if no config yet)
  const rows: CompanyKmConfig[] = (companiesData?.companies ?? []).map((c) => {
    const cfg = configsData?.configs?.find((k) => k.company_id === c.id)
    return {
      company_id: c.id,
      company_name: c.company,
      td_km_min: cfg?.td_km_min ?? 5,
      td_km_max: cfg?.td_km_max ?? 50,
      comodat_km_min: cfg?.comodat_km_min ?? 10,
      comodat_km_max: cfg?.comodat_km_max ?? 200,
      km_gap: cfg?.km_gap ?? 20,
    }
  })

  const startEdit = (row: CompanyKmConfig) => {
    setEditId(row.company_id)
    setEditData({
      td_km_min: row.td_km_min,
      td_km_max: row.td_km_max,
      comodat_km_min: row.comodat_km_min,
      comodat_km_max: row.comodat_km_max,
      km_gap: row.km_gap,
    })
  }

  const saveEdit = () => {
    if (!editId) return
    updateMutation.mutate({
      company_id: editId,
      data: {
        td_km_min: editData.td_km_min,
        td_km_max: editData.td_km_max,
        comodat_km_min: editData.comodat_km_min,
        comodat_km_max: editData.comodat_km_max,
        km_gap: editData.km_gap,
      },
    })
  }

  return (
    <div className="space-y-8">
      {/* Section 1: KM Limits */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Settings className="h-5 w-5 text-muted-foreground" />
          <h3 className="text-lg font-semibold">Route KM Limits per Company</h3>
        </div>
        <p className="text-sm text-muted-foreground">
          Min/max KM range for TD and Comodat routes when distributing KM across a batch.
        </p>

        {isLoading ? (
          <TableSkeleton rows={4} columns={6} />
        ) : !rows.length ? (
          <EmptyState
            icon={<Settings className="h-10 w-10" />}
            title="No companies found"
            description="Add companies to configure route KM limits."
          />
        ) : (
          <Card className="overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Company</TableHead>
                  <TableHead className="text-center" colSpan={2}>
                    <Badge variant="default" className="font-normal">TD</Badge>{' '}
                    KM Range
                  </TableHead>
                  <TableHead className="text-center" colSpan={2}>
                    <Badge variant="secondary" className="font-normal">Comodat</Badge>{' '}
                    KM Range
                  </TableHead>
                  <TableHead className="text-center">Gap ±</TableHead>
                  <TableHead className="w-[100px]">Actions</TableHead>
                </TableRow>
                <TableRow className="border-b-0">
                  <TableHead />
                  <TableHead className="text-center text-xs text-muted-foreground">Min</TableHead>
                  <TableHead className="text-center text-xs text-muted-foreground">Max</TableHead>
                  <TableHead className="text-center text-xs text-muted-foreground">Min</TableHead>
                  <TableHead className="text-center text-xs text-muted-foreground">Max</TableHead>
                  <TableHead className="text-center text-xs text-muted-foreground">km</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) =>
                  editId === row.company_id ? (
                    <TableRow key={row.company_id} className="bg-muted/30">
                      <TableCell className="font-medium">{row.company_name}</TableCell>
                      <TableCell>
                        <Input
                          className="h-8 w-20 text-center mx-auto"
                          type="number"
                          min={1}
                          value={editData.td_km_min}
                          onChange={(e) => setEditData((p) => ({ ...p, td_km_min: Number(e.target.value) }))}
                        />
                      </TableCell>
                      <TableCell>
                        <Input
                          className="h-8 w-20 text-center mx-auto"
                          type="number"
                          min={1}
                          value={editData.td_km_max}
                          onChange={(e) => setEditData((p) => ({ ...p, td_km_max: Number(e.target.value) }))}
                        />
                      </TableCell>
                      <TableCell>
                        <Input
                          className="h-8 w-20 text-center mx-auto"
                          type="number"
                          min={1}
                          value={editData.comodat_km_min}
                          onChange={(e) => setEditData((p) => ({ ...p, comodat_km_min: Number(e.target.value) }))}
                        />
                      </TableCell>
                      <TableCell>
                        <Input
                          className="h-8 w-20 text-center mx-auto"
                          type="number"
                          min={1}
                          value={editData.comodat_km_max}
                          onChange={(e) => setEditData((p) => ({ ...p, comodat_km_max: Number(e.target.value) }))}
                        />
                      </TableCell>
                      <TableCell>
                        <Input
                          className="h-8 w-16 text-center mx-auto"
                          type="number"
                          min={0}
                          value={editData.km_gap}
                          onChange={(e) => setEditData((p) => ({ ...p, km_gap: Number(e.target.value) }))}
                        />
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button variant="ghost" size="sm" onClick={saveEdit} disabled={updateMutation.isPending}>
                            <Save className="h-4 w-4 text-green-600" />
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => setEditId(null)}>
                            <XIcon className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ) : (
                    <TableRow key={row.company_id}>
                      <TableCell className="font-medium">{row.company_name}</TableCell>
                      <TableCell className="text-center">{row.td_km_min} km</TableCell>
                      <TableCell className="text-center">{row.td_km_max} km</TableCell>
                      <TableCell className="text-center">{row.comodat_km_min} km</TableCell>
                      <TableCell className="text-center">{row.comodat_km_max} km</TableCell>
                      <TableCell className="text-center">±{row.km_gap} km</TableCell>
                      <TableCell>
                        <div className="flex gap-1 items-center">
                          <Button variant="ghost" size="sm" onClick={() => startEdit(row)}>
                            <Pencil className="h-4 w-4" />
                          </Button>
                          {saveSuccess === row.company_id && (
                            <Check className="h-4 w-4 text-green-500" />
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                )}
              </TableBody>
            </Table>
          </Card>
        )}
      </div>

      {/* Section 2: Itinerary Routes per Company */}
      <RoutesSettings companies={companiesData?.companies ?? []} />
    </div>
  )
}

// ── Routes Settings — per-company itinerary list ──
function RoutesSettings({ companies }: { companies: { id: number; company: string }[] }) {
  const queryClient = useQueryClient()
  const [selectedCompany, setSelectedCompany] = useState<string>('')
  const [newComodatRoute, setNewComodatRoute] = useState('')
  const [newComodatKm, setNewComodatKm] = useState('')

  // Company config (base location, td radius, comodat avg km)
  const [configForm, setConfigForm] = useState({ base_location: '', td_radius_km: 50, comodat_avg_km: 150 })
  const [configSaved, setConfigSaved] = useState(false)

  const companyId = selectedCompany ? Number(selectedCompany) : null

  const { data: configData } = useQuery({
    queryKey: ['fp-company-config', companyId],
    queryFn: () => foiParcursApi.getCompanyConfig(companyId!),
    enabled: !!companyId,
    staleTime: 30_000,
  })

  // Update form when config data arrives
  const loadedConfig = configData?.config
  useEffect(() => {
    if (loadedConfig) {
      setConfigForm({
        base_location: loadedConfig.base_location || '',
        td_radius_km: loadedConfig.td_radius_km || 50,
        comodat_avg_km: loadedConfig.comodat_avg_km || 150,
      })
    }
  }, [loadedConfig])

  const { data: routesData, isLoading } = useQuery({
    queryKey: ['fp-routes', companyId],
    queryFn: () => foiParcursApi.getRoutes(companyId!, 'Comodat'),
    enabled: !!companyId,
    staleTime: 30_000,
  })

  const comodatRoutes = routesData?.routes ?? []

  const configMutation = useMutation({
    mutationFn: () => foiParcursApi.updateCompanyConfig(companyId!, configForm),
    onSuccess: () => {
      setConfigSaved(true)
      setTimeout(() => setConfigSaved(false), 2000)
      queryClient.invalidateQueries({ queryKey: ['fp-company-config', companyId] })
    },
  })

  const addComodatMutation = useMutation({
    mutationFn: () =>
      foiParcursApi.addRoute(companyId!, {
        route_type: 'Comodat',
        itinerary: newComodatRoute.trim(),
        estimated_km: newComodatKm ? Number(newComodatKm) : undefined,
      }),
    onSuccess: () => {
      setNewComodatRoute('')
      setNewComodatKm('')
      queryClient.invalidateQueries({ queryKey: ['fp-routes', companyId] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (routeId: number) => foiParcursApi.deleteRoute(routeId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fp-routes', companyId] })
    },
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <MapPin className="h-5 w-5 text-muted-foreground" />
        <h3 className="text-lg font-semibold">Itinerary Routes per Company</h3>
      </div>
      <p className="text-sm text-muted-foreground">
        Set the company base location for AI-generated TD routes (streets and landmarks within radius).
        Manually configure Comodat routes for longer inter-city trips.
      </p>

      <div className="max-w-sm">
        <Label>Company</Label>
        <Select value={selectedCompany} onValueChange={setSelectedCompany}>
          <SelectTrigger>
            <SelectValue placeholder="Select a company..." />
          </SelectTrigger>
          <SelectContent>
            {companies.map((c) => (
              <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {companyId && (
        <div className="space-y-4">
          {/* Company Location Config */}
          <Card className="p-5 space-y-4">
            <div className="flex items-center gap-2 text-sm font-medium">
              <MapPin className="h-4 w-4 text-muted-foreground" />
              Company Location & Radius
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label className="text-xs">Base Location</Label>
                <Input
                  value={configForm.base_location}
                  onChange={(e) => setConfigForm((p) => ({ ...p, base_location: e.target.value }))}
                  placeholder="e.g., Cluj-Napoca"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">TD Radius (km)</Label>
                <Input
                  type="number"
                  min={1}
                  value={configForm.td_radius_km}
                  onChange={(e) => setConfigForm((p) => ({ ...p, td_radius_km: Number(e.target.value) }))}
                />
                <span className="text-xs text-muted-foreground">
                  AI generates TD routes within this radius
                </span>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Comodat Avg KM</Label>
                <Input
                  type="number"
                  min={1}
                  value={configForm.comodat_avg_km}
                  onChange={(e) => setConfigForm((p) => ({ ...p, comodat_avg_km: Number(e.target.value) }))}
                />
                <span className="text-xs text-muted-foreground">
                  Average distance for Comodat routes
                </span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                onClick={() => configMutation.mutate()}
                disabled={configMutation.isPending}
              >
                <Save className="mr-1.5 h-4 w-4" />
                {configMutation.isPending ? 'Saving...' : 'Save'}
              </Button>
              {configSaved && (
                <span className="text-sm text-green-600 flex items-center gap-1">
                  <Check className="h-4 w-4" /> Saved
                </span>
              )}
            </div>

            {/* TD info box */}
            <div className="rounded-lg bg-muted/50 p-3 text-sm text-muted-foreground flex items-start gap-2">
              <Sparkles className="h-4 w-4 mt-0.5 shrink-0" />
              <div>
                <span className="font-medium text-foreground">TD routes are AI-generated.</span>{' '}
                When filling a TD contract, the auto-fill uses the base location and radius to generate
                realistic itineraries using real streets and landmarks around{' '}
                {configForm.base_location || 'the city'}.
              </div>
            </div>
          </Card>

          {/* Comodat Routes (manual) */}
          <Card className="p-5 space-y-4">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Badge variant="secondary">Comodat</Badge>
              Comodat Routes
              {configForm.comodat_avg_km > 0 && (
                <span className="text-xs text-muted-foreground font-normal">
                  avg ~{configForm.comodat_avg_km}km
                </span>
              )}
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault()
                if (newComodatRoute.trim()) addComodatMutation.mutate()
              }}
              className="flex gap-2"
            >
              <Input
                value={newComodatRoute}
                onChange={(e) => setNewComodatRoute(e.target.value)}
                placeholder={configForm.base_location
                  ? `e.g., ${configForm.base_location} - Oradea - ${configForm.base_location}`
                  : 'e.g., Cluj-Napoca - Oradea - Cluj-Napoca'}
                className="flex-1"
              />
              <Input
                type="number"
                min={1}
                value={newComodatKm}
                onChange={(e) => setNewComodatKm(e.target.value)}
                placeholder="Est. KM"
                className="w-28"
              />
              <Button type="submit" size="sm" disabled={!newComodatRoute.trim() || addComodatMutation.isPending}>
                <Plus className="mr-1.5 h-4 w-4" />
                Add
              </Button>
            </form>

            {isLoading ? (
              <TableSkeleton rows={2} columns={2} />
            ) : !comodatRoutes.length ? (
              <p className="text-sm text-muted-foreground py-2 text-center">
                No Comodat routes yet.
              </p>
            ) : (
              <div className="space-y-2">
                {comodatRoutes.map((r) => (
                  <div key={r.id} className="flex items-center justify-between rounded-md border px-3 py-2">
                    <div className="flex items-center gap-2 text-sm">
                      <Route className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                      {r.itinerary}
                      {r.estimated_km && (
                        <Badge variant="outline" className="text-xs ml-1">
                          ~{r.estimated_km} km
                        </Badge>
                      )}
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive shrink-0"
                      onClick={() => deleteMutation.mutate(r.id)}
                      disabled={deleteMutation.isPending}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  )
}
