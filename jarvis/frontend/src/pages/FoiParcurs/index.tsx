import React, { useState, useCallback, useEffect, useRef } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  FileText,
  Plus,
  Route,
  Search,
  UserPlus,
  Check,
  ArrowUpDown,
  Trash2,
  RotateCcw,
  Archive,
  Lock,
  Car,
  Pencil,
  XIcon,
  SlidersHorizontal,
  Settings,
  Save,
  Sparkles,
  MapPin,
  ChevronDown,
  ChevronRight,
  Download,
  FileSpreadsheet,
  PlayCircle,
  Loader2,
} from 'lucide-react'
import { EmptyState } from '@/components/shared/EmptyState'
import { TableSkeleton } from '@/components/shared/TableSkeleton'
import LockVehicleDialog from './LockVehicleDialog'
import ArchiveVehicleDialog from './ArchiveVehicleDialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
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
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from '@/components/ui/dropdown-menu'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import SignatureCanvas from '@/components/shared/SignatureCanvas'
import { DriverLicenseSection } from './CreateClientPanel'
import { SearchInput } from '@/components/shared/SearchInput'
import { useAuthStore } from '@/stores/authStore'
import { foiParcursApi, type StoredRouteSheet, type RouteSheetAlimentare, type RouteSheetEvent, type SessionImportResult } from '@/api/foiParcurs'
import { hrApi } from '@/api/hr'
import {
  fuelUnit,
  usesFuelTank,
  usesBattery,
  type FoiContract,
  type FpVehicle,
} from '@/types/foiParcurs'
import { VehicleOdometerHistory } from './VehicleOdometerHistory'
import { sessionStatus, type SessionStatusKey } from './sessionStatus'
import { naiveDate } from '@/lib/naiveDate'
import { CalendarTab } from './CalendarTab'

/** useState backed by localStorage — survives a page refresh. */
function usePersistentState<T>(key: string, initial: T) {
  const [state, setState] = useState<T>(() => {
    try {
      const s = localStorage.getItem(key)
      return s != null ? (JSON.parse(s) as T) : initial
    } catch {
      return initial
    }
  })
  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(state))
    } catch {
      /* ignore quota/serialization errors */
    }
  }, [key, state])
  return [state, setState] as const
}

// ── Main Page ──
export default function FoiParcurs() {
  const navigate = useNavigate()
  // Persist the tab + company/brand filters so a refresh keeps your context.
  const [activeTab, setActiveTab] = usePersistentState<'contracts' | 'parcurs' | 'stock' | 'calendar' | 'settings'>('fp.activeTab', 'stock')
  const [companyId, setCompanyId] = usePersistentState<number>('fp.companyId', 0)
  const [brand, setBrand] = usePersistentState<string>('fp.brand', '')

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

      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'contracts' | 'parcurs' | 'stock' | 'calendar' | 'settings')}>
        <TabsList>
          <TabsTrigger value="stock">Driving Park</TabsTrigger>
          <TabsTrigger value="parcurs">Sesiuni Driving</TabsTrigger>
          <TabsTrigger value="calendar">Calendar</TabsTrigger>
          <TabsTrigger value="contracts">Foi de Parcurs</TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
        </TabsList>
      </Tabs>

      {activeTab === 'contracts' && <ContractsTab companyId={companyId} />}
      {activeTab === 'parcurs' && <SessionsTab companyId={companyId} brand={brand} />}
      {activeTab === 'stock' && <StockTab companyId={companyId} brand={brand} />}
      {activeTab === 'calendar' && <CalendarTab companyId={companyId} brand={brand} />}
      {activeTab === 'settings' && <SettingsTab />}
    </div>
  )
}

// ── Contracts Tab — Form → Preview → Save Batch ──
function ContractsTab({ companyId }: { companyId: number }) {
  const [importOpen, setImportOpen] = useState(false)
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Foi de Parcurs</h3>
          <p className="text-sm text-muted-foreground">Sesiuni de rulare cumulate lunar, per mașină</p>
        </div>
        <Button variant="outline" onClick={() => setImportOpen(true)}>
          <Download className="mr-1.5 h-4 w-4" /> Importă sesiuni
        </Button>
      </div>
      <RouteSheetsTable companyId={companyId} />
      <SessionImportDialog companyId={companyId} open={importOpen} onOpenChange={setImportOpen} />
    </div>
  )
}

// ── Bulk session import — download template, upload filled Excel, show report ──
function SessionImportDialog({ companyId, open, onOpenChange }: {
  companyId: number; open: boolean; onOpenChange: (o: boolean) => void
}) {
  const queryClient = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<SessionImportResult | null>(null)

  useEffect(() => { if (open) { setFile(null); setError(''); setResult(null) } }, [open])

  const doImport = async () => {
    if (!file || !companyId) return
    setBusy(true); setError(''); setResult(null)
    try {
      const r = await foiParcursApi.importSessions(companyId, file)
      setResult(r)
      queryClient.invalidateQueries({ queryKey: ['foi-contracts-all'] })
      queryClient.invalidateQueries({ queryKey: ['fp-vehicles'] })
    } catch (e: any) {
      setError(e?.message || 'Import eșuat')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>Importă sesiuni</DialogTitle></DialogHeader>
        <p className="text-sm text-muted-foreground">
          Descarcă template-ul, completează sesiunile (o linie per cursă), apoi încarcă fișierul.
          VIN-urile inexistente creează mașina; duplicatele sunt ignorate.
        </p>
        <a href={foiParcursApi.getSessionImportTemplateUrl(companyId)} download>
          <Button variant="outline" size="sm" className="h-8" disabled={!companyId}>
            <Download className="mr-1.5 h-4 w-4" /> Descarcă template
          </Button>
        </a>
        <Input type="file" accept=".xlsx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        {error && <div className="text-sm text-red-600">{error}</div>}
        {result && (
          <div className="rounded border p-3 text-sm space-y-1">
            <div className="flex flex-wrap gap-3">
              <Badge className="bg-green-600 text-white">Adăugate: {result.inserted}</Badge>
              <Badge variant="outline">Ignorate (dup): {result.skipped}</Badge>
              <Badge className="bg-blue-600 text-white">Mașini create: {result.cars_created}</Badge>
              {result.errors.length > 0 && <Badge variant="destructive">Erori: {result.errors.length}</Badge>}
            </div>
            {result.errors.length > 0 && (
              <ul className="mt-1 max-h-40 overflow-y-auto text-xs text-red-600">
                {result.errors.map((er, i) => <li key={i}>Linia {er.row}: {er.message}</li>)}
              </ul>
            )}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Închide</Button>
          <Button onClick={doImport} disabled={!file || busy}>
            {busy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Download className="mr-1.5 h-4 w-4" />}
            Importă
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// Order a car's sessions by odometer and insert synthetic "gap" rows wherever
// the odometer jumps between logged sessions (km the car moved without a logged
// drive). Gap rows carry only the distance + the date the gap was spotted (the
// session that revealed it) — no client/traseu — as a legal continuity marker.
export type GapNeighbor = { id: number; client: string; kmStart: number; kmEnd: number }
export type GapRow = {
  id: string; date: string; dateFrom: string; dateTo: string
  kmStart: number; kmEnd: number; distance: number
  // The two logged sessions the gap sits between — targets for "absorb".
  before: GapNeighbor; after: GapNeighbor
}
type DetailRow =
  | { gap: false; session: FoiContract }
  | ({ gap: true } & GapRow)

function withGaps(sessions: FoiContract[]): DetailRow[] {
  const sorted = [...sessions].sort(
    (a, b) => (a.km_start ?? 0) - (b.km_start ?? 0) || (a.km_end ?? 0) - (b.km_end ?? 0),
  )
  const rows: DetailRow[] = []
  let prevEnd: number | null = null
  let prevSession: FoiContract | null = null
  const neighbor = (s: FoiContract): GapNeighbor => ({
    id: s.id, client: s.client_name || s.advisor_name || '—',
    kmStart: s.km_start ?? 0, kmEnd: s.km_end ?? 0,
  })
  for (const c of sorted) {
    const start = c.km_start ?? 0
    if (prevEnd != null && start > prevEnd && prevSession) {
      rows.push({
        gap: true, id: `gap-${c.id}`, date: c.created_at,
        dateFrom: prevSession.created_at ?? c.created_at, dateTo: c.created_at,
        kmStart: prevEnd, kmEnd: start, distance: start - prevEnd,
        before: neighbor(prevSession), after: neighbor(c),
      })
    }
    rows.push({ gap: false, session: c })
    if (prevEnd == null || (c.km_end ?? 0) > prevEnd) { prevEnd = c.km_end ?? 0; prevSession = c }
  }
  return rows
}

// ── Foi de Parcurs — one route sheet per car × month (cumulated driving
//    sessions for that vehicle that month), scoped to the header company.
//    Month is a filter; each row expands to its individual sessions and can
//    generate/store an AI-drafted legal Foaie de Parcurs (PDF) or Excel. ──
function RouteSheetsTable({ companyId }: { companyId: number }) {
  const queryClient = useQueryClient()
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [previewVin, setPreviewVin] = useState<string | null>(null)
  const [redistribute, setRedistribute] = useState<{ vin: string; gap: GapRow; sessions: WinSession[] } | null>(null)
  const now = new Date()
  const [filterYear, setFilterYear] = useState<number>(now.getFullYear())
  const [filterMonth, setFilterMonth] = useState<number>(now.getMonth() + 1) // 0 = all months
  const monthChosen = filterMonth !== 0 // a Foaie de parcurs is monthly — needs a specific month

  const { data, isLoading } = useQuery({
    queryKey: ['foi-contracts-all', 'recent', companyId],
    queryFn: () =>
      foiParcursApi.getContracts({ company_id: companyId || undefined, per_page: 500, sort_by: 'created_at', sort_dir: 'DESC' }),
    staleTime: 30_000,
  })

  // Vehicle catalog → Make/Model for each VIN (contracts only carry the VIN).
  const { data: vehData } = useQuery({
    queryKey: ['fp-vehicles'],
    queryFn: () => foiParcursApi.getVehicles(false),
    staleTime: 60_000,
  })
  const vinMap = React.useMemo(
    () => new Map((vehData?.vehicles ?? []).map((v) => [v.vin, v])),
    [vehData],
  )

  // Which cars already have a stored (generated) sheet for the selected period.
  const { data: storedData } = useQuery({
    queryKey: ['fp-route-sheets', companyId, filterYear, filterMonth],
    queryFn: () => foiParcursApi.listRouteSheets(companyId, filterYear, filterMonth),
    enabled: monthChosen,
    staleTime: 30_000,
  })
  const storedByVin = React.useMemo(() => {
    const m = new Map<string, StoredRouteSheet>()
    ;(storedData?.sheets ?? []).forEach((s) => m.set(s.vin, s))
    return m
  }, [storedData])

  const contracts = data?.contracts ?? []
  const period = (c: (typeof contracts)[number]) => {
    const d = new Date(c.created_at)
    return { year: c.year ?? d.getFullYear(), month: c.month ?? d.getMonth() + 1 }
  }

  const years = React.useMemo(() => {
    const s = new Set<number>([now.getFullYear()])
    for (const c of contracts) s.add(period(c).year)
    return [...s].sort((a, b) => b - a)
  }, [contracts]) // eslint-disable-line react-hooks/exhaustive-deps

  // One row per car (VIN), cumulating the sessions that match the period filter.
  const cars = React.useMemo(() => {
    const map = new Map<string, { vin: string; sessions: typeof contracts }>()
    for (const c of contracts) {
      const p = period(c)
      if (p.year !== filterYear) continue
      if (filterMonth !== 0 && p.month !== filterMonth) continue
      if (!map.has(c.vin)) map.set(c.vin, { vin: c.vin, sessions: [] })
      map.get(c.vin)!.sessions.push(c)
    }
    return [...map.values()].sort((a, b) => a.vin.localeCompare(b.vin))
  }, [contracts, filterYear, filterMonth])

  const toggle = (key: string) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })

  const monthName = (m: number) => new Date(2000, m - 1).toLocaleString('ro-RO', { month: 'long' })

  const toolbar = (
    <div className="flex items-center gap-2">
      <Select value={String(filterMonth)} onValueChange={(v) => setFilterMonth(Number(v))}>
        <SelectTrigger className="h-8 w-[150px]"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value="0">Toate lunile</SelectItem>
          {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
            <SelectItem key={m} value={String(m)} className="capitalize">{monthName(m)}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select value={String(filterYear)} onValueChange={(v) => setFilterYear(Number(v))}>
        <SelectTrigger className="h-8 w-[100px]"><SelectValue /></SelectTrigger>
        <SelectContent>
          {years.map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}
        </SelectContent>
      </Select>
      {!isLoading && <span className="text-xs text-muted-foreground">{cars.length} mașini</span>}
    </div>
  )

  if (isLoading) return <div className="space-y-3">{toolbar}<TableSkeleton rows={6} columns={10} /></div>

  return (
    <div className="space-y-3">
      {toolbar}
      {!cars.length ? (
        <EmptyState
          icon={<FileText className="h-10 w-10" />}
          title="Nicio foaie de parcurs"
          description={contracts.length
            ? 'Nicio sesiune pentru perioada selectată. Schimbă luna/anul sau generează una nouă.'
            : 'Generează prima foaie de parcurs cu butonul de mai sus.'}
        />
      ) : (
        <Card className="overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>Make</TableHead>
                <TableHead>Model</TableHead>
                <TableHead>VIN</TableHead>
                <TableHead>KM start</TableHead>
                <TableHead>KM end</TableHead>
                <TableHead>Total KM</TableHead>
                <TableHead>Sesiuni</TableHead>
                <TableHead>Clienți</TableHead>
                <TableHead className="text-right">Foaie de parcurs</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {cars.map((sheet) => {
                const isOpen = expanded.has(sheet.vin)
                const veh = vinMap.get(sheet.vin)
                const kmStart = Math.min(...sheet.sessions.map((c) => c.km_start ?? 0))
                const kmEnd = Math.max(...sheet.sessions.map((c) => c.km_end ?? 0))
                const totalKm = sheet.sessions.reduce((s, c) => s + (c.distance_km || 0), 0)
                const clientCount = new Set(sheet.sessions.map((c) => c.client_name).filter(Boolean)).size
                const stored = storedByVin.get(sheet.vin)

                return (
                  <React.Fragment key={sheet.vin}>
                    <TableRow className="cursor-pointer hover:bg-muted/50" onClick={() => toggle(sheet.vin)}>
                      <TableCell className="py-2">
                        {isOpen ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                      </TableCell>
                      <TableCell className="text-sm">{veh?.mark || <span className="text-muted-foreground">—</span>}</TableCell>
                      <TableCell className="text-sm font-medium">{veh?.model || <span className="text-muted-foreground">—</span>}</TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">{sheet.vin}</TableCell>
                      <TableCell className="text-sm whitespace-nowrap">{kmStart.toLocaleString('ro-RO')}</TableCell>
                      <TableCell className="text-sm whitespace-nowrap">{kmEnd.toLocaleString('ro-RO')}</TableCell>
                      <TableCell className="text-sm whitespace-nowrap font-medium">{totalKm.toLocaleString('ro-RO')} km</TableCell>
                      <TableCell>{sheet.sessions.length}</TableCell>
                      <TableCell>{clientCount}</TableCell>
                      <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-end gap-2">
                          {stored && (
                            <Badge className="bg-green-600 text-white text-xs"
                              title={`Salvat ${new Date(stored.generated_at).toLocaleString('ro-RO')}`}>
                              Salvat
                            </Badge>
                          )}
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="outline" size="sm" className="h-7 gap-1" disabled={!monthChosen}
                                title={monthChosen ? undefined : 'Selectează o lună'}>
                                <FileText className="h-3.5 w-3.5" />
                                {stored ? 'Vezi' : 'Generează'}
                                <ChevronDown className="h-3 w-3" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onClick={() => setPreviewVin(sheet.vin)}>
                                <FileText className="mr-2 h-4 w-4" /> PDF (previzualizare)
                              </DropdownMenuItem>
                              <DropdownMenuItem asChild>
                                <a href={foiParcursApi.getRouteSheetXlsxUrl(sheet.vin, filterYear, filterMonth)} download>
                                  <FileSpreadsheet className="mr-2 h-4 w-4" /> Excel
                                </a>
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </div>
                      </TableCell>
                    </TableRow>
                    {isOpen && (
                      <TableRow className="bg-muted/20 hover:bg-muted/20">
                        <TableCell colSpan={10} className="p-0">
                          <div className="px-4 py-2">
                            <Table>
                              <TableHeader>
                                <TableRow>
                                  <TableHead>Data</TableHead>
                                  <TableHead>Client</TableHead>
                                  <TableHead>Traseu</TableHead>
                                  <TableHead>Distanță</TableHead>
                                  <TableHead>KM</TableHead>
                                  <TableHead>Status</TableHead>
                                  <TableHead className="text-right">PDF</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {withGaps(sheet.sessions).map((row) => {
                                  if (row.gap) {
                                    return (
                                      <TableRow key={row.id} className="bg-amber-500/10">
                                        <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                                          {new Date(row.date).toLocaleDateString('ro-RO')}
                                        </TableCell>
                                        <TableCell><span className="text-muted-foreground text-xs">—</span></TableCell>
                                        <TableCell className="text-xs italic text-amber-700 dark:text-amber-500">Gap kilometraj (nejustificat)</TableCell>
                                        <TableCell className="text-sm whitespace-nowrap font-medium">{row.distance} km</TableCell>
                                        <TableCell className="text-xs whitespace-nowrap">{row.kmStart} - {row.kmEnd}</TableCell>
                                        <TableCell><Badge variant="outline" className="text-xs">Gap</Badge></TableCell>
                                        <TableCell className="text-right">
                                          <Button variant="outline" size="sm" className="h-7 px-2 text-xs"
                                            onClick={() => setRedistribute({
                                              vin: sheet.vin, gap: row,
                                              sessions: [...sheet.sessions]
                                                .sort((a, b) => (a.km_start ?? 0) - (b.km_start ?? 0) || (a.km_end ?? 0) - (b.km_end ?? 0))
                                                .map((s) => ({
                                                  id: s.id, kmStart: s.km_start ?? 0, kmEnd: s.km_end ?? 0,
                                                  driver: s.client_name || s.advisor_name || '—',
                                                })),
                                            })}>
                                            Redistribuie
                                          </Button>
                                        </TableCell>
                                      </TableRow>
                                    )
                                  }
                                  const c = row.session
                                  const ss = sessionStatus(c)
                                  const hasPdf = c.status !== 'PENDING' && c.status !== 'PLANNED'
                                  return (
                                    <TableRow key={c.id} className={ss.rowClass}>
                                      <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                                        {new Date(c.created_at).toLocaleDateString('ro-RO')}
                                      </TableCell>
                                      <TableCell>
                                        {c.client_name ? (
                                          <span className="font-medium text-sm">{c.client_name}</span>
                                        ) : (
                                          <span className="text-muted-foreground text-xs">—</span>
                                        )}
                                      </TableCell>
                                      <TableCell className="max-w-[220px] truncate text-sm">{c.itinerary || '—'}</TableCell>
                                      <TableCell className="text-sm whitespace-nowrap">{c.distance_km} km</TableCell>
                                      <TableCell className="text-xs whitespace-nowrap">{c.km_start} - {c.km_end}</TableCell>
                                      <TableCell>
                                        <Badge className={`text-xs ${ss.badgeClass}`}>{ss.label}</Badge>
                                      </TableCell>
                                      <TableCell className="text-right">
                                        {hasPdf ? (
                                          <div className="flex justify-end gap-1">
                                            <a href={foiParcursApi.getContractPdfUrl(c.id, 'legal')} target="_blank" rel="noopener" title="Legal PDF">
                                              <Button variant="outline" size="sm" className="h-7 px-2 text-xs">Legal</Button>
                                            </a>
                                            <a href={foiParcursApi.getContractPdfUrl(c.id, 'custom')} target="_blank" rel="noopener" title="Custom PDF">
                                              <Button variant="outline" size="sm" className="h-7 px-2 text-xs">Custom</Button>
                                            </a>
                                          </div>
                                        ) : (
                                          <span className="text-muted-foreground text-xs">—</span>
                                        )}
                                      </TableCell>
                                    </TableRow>
                                  )
                                })}
                              </TableBody>
                            </Table>
                          </div>
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
      <RouteSheetPreviewDialog
        vin={previewVin}
        year={filterYear}
        month={filterMonth}
        stored={previewVin ? storedByVin.get(previewVin) ?? null : null}
        vehicleNorma={previewVin ? vinMap.get(previewVin)?.norma_combustibil ?? null : null}
        vehicleNormaEnergie={previewVin ? vinMap.get(previewVin)?.norma_energie ?? null : null}
        vehicleFuelType={previewVin ? vinMap.get(previewVin)?.fuel_type ?? null : null}
        onClose={() => {
          setPreviewVin(null)
          queryClient.invalidateQueries({ queryKey: ['fp-route-sheets'] })
        }}
      />
      <GapRedistributeDialog
        data={redistribute}
        year={filterYear}
        month={filterMonth}
        onClose={(changed) => {
          setRedistribute(null)
          if (changed) {
            queryClient.invalidateQueries({ queryKey: ['foi-contracts-all'] })
            queryClient.invalidateQueries({ queryKey: ['fp-route-sheets'] })
          }
        }}
      />
    </div>
  )
}

// ── Rezolvă gap: EITHER absorb the km across the bounding sessions + up to 3
//    documented middle entries, OR document up to 3 "client extra" drivers. ──
// A session ordered along the odometer — the window the gap is distributed over.
type WinSession = { id: number; kmStart: number; kmEnd: number; driver: string }
// One session in the Absorb window: `km` is its NEW distance (draggable), `min`
// its original distance (can't shrink below — the gap only ever adds km).
type Seg = { id: number; driver: string; km: number; min: number }
type ExtraClient = {
  client_name: string; advisor_name: string; km: string
  client_signature: string; license_photo: string | null
  license_number: string; license_expiry: string
}
const emptyExtraClient = (km: number, advisor: string): ExtraClient => ({
  client_name: '', advisor_name: advisor, km: km ? String(km) : '',
  client_signature: '', license_photo: null, license_number: '', license_expiry: '',
})

// A single horizontal bar for the whole gap; drag the dividers between segments
// to move km from one neighbour to the next. Segment widths always sum to the
// gap, so it can never over-allocate.
const SEG_COLORS = ['bg-sky-500', 'bg-amber-500', 'bg-violet-500', 'bg-emerald-500', 'bg-rose-500']
function GapSplitBar({ segs, gapDist, onChange }: {
  segs: Seg[]; gapDist: number; onChange: (segs: Seg[]) => void
}) {
  const barRef = useRef<HTMLDivElement>(null)
  const dragIdx = useRef<number | null>(null)

  const bounds: number[] = []          // bounds[i] = cumulative km at end of seg i
  let acc = 0
  for (const s of segs) { acc += s.km; bounds.push(acc) }
  const startOf = (i: number) => (i === 0 ? 0 : bounds[i - 1])
  const pct = (km: number) => `${gapDist ? (km / gapDist) * 100 : 0}%`

  const moveDivider = (clientX: number) => {
    const idx = dragIdx.current
    if (idx == null || !barRef.current) return
    const rect = barRef.current.getBoundingClientRect()
    const kmAtMouse = Math.round(((clientX - rect.left) / rect.width) * gapDist)
    const pairStart = startOf(idx)
    const pairTotal = segs[idx].km + segs[idx + 1].km
    // Neither neighbour may drop below its original distance (`min`).
    const lo = segs[idx].min
    const hi = pairTotal - segs[idx + 1].min
    const leftKm = Math.max(lo, Math.min(hi, kmAtMouse - pairStart))
    onChange(segs.map((s, i) =>
      i === idx ? { ...s, km: leftKm } : i === idx + 1 ? { ...s, km: pairTotal - leftKm } : s))
  }

  return (
    <div
      ref={barRef}
      className="relative h-11 rounded-md overflow-hidden border flex select-none touch-none"
      onPointerMove={(e) => { if (dragIdx.current != null) moveDivider(e.clientX) }}
      onPointerUp={() => { dragIdx.current = null }}
      onPointerLeave={() => { dragIdx.current = null }}
    >
      {segs.map((s, i) => (
        <div key={i} className={`h-full ${SEG_COLORS[i % SEG_COLORS.length]} opacity-85 flex flex-col items-center justify-center text-white overflow-hidden`}
          style={{ width: pct(s.km) }}>
          {s.km > 0 && (
            <>
              <span className="truncate px-1 text-[10px] leading-none font-medium max-w-full">{s.driver || '—'}</span>
              <span className="text-[10px] leading-tight tabular-nums">{s.km}</span>
            </>
          )}
        </div>
      ))}
      {segs.slice(0, -1).map((_, i) => (
        <div key={`d${i}`}
          onPointerDown={(e) => { dragIdx.current = i; (e.currentTarget as Element).setPointerCapture?.(e.pointerId) }}
          className="absolute top-0 h-full w-4 -ml-2 cursor-ew-resize flex items-center justify-center z-10"
          style={{ left: pct(bounds[i]) }}>
          <div className="h-full w-0.5 bg-white/90" />
          <div className="absolute h-5 w-2.5 rounded-sm bg-white border border-slate-300 shadow" />
        </div>
      ))}
    </div>
  )
}

function ExtraClientCard({ idx, c, canRemove, onChange, onRemove }: {
  idx: number; c: ExtraClient; canRemove: boolean
  onChange: (patch: Partial<ExtraClient>) => void; onRemove: () => void
}) {
  return (
    <div className="rounded-md border p-3 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-muted-foreground">Client {idx + 1}</span>
        {canRemove && (
          <Button type="button" variant="ghost" size="icon" className="h-6 w-6" onClick={onRemove}>
            <XIcon className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
      <div className="grid grid-cols-[1fr_90px] gap-2">
        <div className="space-y-1.5">
          <Label className="text-xs">Nume client (șofer) *</Label>
          <Input className="h-8" placeholder="Nume client" value={c.client_name} onChange={(e) => onChange({ client_name: e.target.value })} />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">KM *</Label>
          <Input type="number" min={1} className="h-8" value={c.km} onChange={(e) => onChange({ km: e.target.value })} />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">Consilier</Label>
        <Input className="h-8" placeholder="Nume consilier" value={c.advisor_name} onChange={(e) => onChange({ advisor_name: e.target.value })} />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">Permis de conducere (poză)</Label>
        <DriverLicenseSection
          photo={c.license_photo}
          onPhotoChange={(v) => onChange({ license_photo: v })}
          hasClient={!!c.client_name.trim()}
          onSelectClient={(cl) => onChange({ client_name: cl.display_name || cl.name || c.client_name })}
          onLicenseNumber={(v) => onChange({ license_number: v })}
          onLicenseExpiry={(v) => onChange({ license_expiry: v })}
        />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">Semnătură client *</Label>
        {c.client_signature ? (
          <div className="space-y-2">
            <div className="border rounded-lg p-2 bg-white"><img src={c.client_signature} alt="Semnătură client" className="max-h-[90px] mx-auto" /></div>
            <Button type="button" variant="outline" size="sm" onClick={() => onChange({ client_signature: '' })}>Resemnează</Button>
          </div>
        ) : (
          <SignatureCanvas onSave={(s) => onChange({ client_signature: s })} onClear={() => onChange({ client_signature: '' })} width={460} height={180} />
        )}
      </div>
    </div>
  )
}

function GapRedistributeDialog({ data, year, month, onClose }: {
  data: { vin: string; gap: GapRow; sessions: WinSession[] } | null
  year: number
  month: number
  onClose: (changed: boolean) => void
}) {
  const user = useAuthStore((s) => s.user)
  const gap = data?.gap
  const gapDist = gap?.distance ?? 0
  const sessions = data?.sessions ?? []
  const upperIdx = gap ? sessions.findIndex((s) => s.id === gap.before.id) : -1
  const lowerIdx = gap ? sessions.findIndex((s) => s.id === gap.after.id) : -1
  const [mode, setMode] = useState<'absorb' | 'extra'>('absorb')
  const [win, setWin] = useState<{ start: number; end: number }>({ start: 0, end: 0 })
  const [segs, setSegs] = useState<Seg[]>([])
  const [date, setDate] = useState('')
  const [clients, setClients] = useState<ExtraClient[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const isoDay = (s: string) => (s ? new Date(s).toISOString().slice(0, 10) : '')
  const dFrom = gap ? isoDay(gap.dateFrom) : ''
  const dTo = gap ? isoDay(gap.dateTo) : ''

  // Fresh distribution for a window [start,end]: each session at its original
  // distance, with the whole in-window gap placed on the immediate upper neighbour.
  const buildSegs = (start: number, end: number): Seg[] => {
    const winS = sessions.slice(start, end + 1)
    if (!winS.length) return []
    const span = winS[winS.length - 1].kmEnd - winS[0].kmStart
    const origSum = winS.reduce((t, s) => t + (s.kmEnd - s.kmStart), 0)
    const gapKm = span - origSum
    return winS.map((s) => {
      const orig = s.kmEnd - s.kmStart
      return { id: s.id, driver: s.driver, min: orig, km: orig + (s.id === gap?.before.id ? gapKm : 0) }
    })
  }

  useEffect(() => {
    if (!gap || upperIdx < 0 || lowerIdx < 0) return
    setMode('absorb')
    setWin({ start: upperIdx, end: lowerIdx })
    setSegs(buildSegs(upperIdx, lowerIdx))
    setDate(dTo || dFrom)
    setClients([emptyExtraClient(gap.distance, user?.name ?? '')])
    setError('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.gap?.id])

  const setWindow = (start: number, end: number) => { setWin({ start, end }); setSegs(buildSegs(start, end)) }
  // Add ANY session (need not be adjacent): the window grows to cover it and
  // everything in between, so the re-tile stays contiguous.
  const addSession = (idx: number) => setWindow(Math.min(win.start, idx), Math.max(win.end, idx))
  const removeUp = () => { if (win.start < upperIdx) setWindow(win.start + 1, win.end) }
  const removeDown = () => { if (win.end > lowerIdx) setWindow(win.start, win.end - 1) }
  // Back to the starting point: just the two neighbours, whole gap on the upper one.
  const resetAbsorb = () => setWindow(upperIdx, lowerIdx)

  const setClient = (i: number, patch: Partial<ExtraClient>) =>
    setClients((p) => p.map((c, idx) => (idx === i ? { ...c, ...patch } : c)))
  const addClient = () => setClients((p) => (p.length >= 3 ? p : [...p, emptyExtraClient(0, user?.name ?? '')]))
  const removeClient = (i: number) => setClients((p) => p.filter((_, idx) => idx !== i))

  const num = (s: string) => Number(s || 0)
  const extraSum = clients.reduce((s, c) => s + num(c.km), 0)
  const winSpan = segs.reduce((t, s) => t + s.km, 0) // = window km span; bar fills 100%
  const minSum = segs.reduce((t, s) => t + s.min, 0)
  const windowGapTotal = winSpan - minSum // all unaccounted km inside the window (may span >1 gap)
  const extraGaps = windowGapTotal - gapDist // >0 when the window also covers other gaps
  const outOfWindow = sessions.map((_, i) => i).filter((i) => i < win.start || i > win.end)

  // Re-tiled km range each session covers (row labels), anchored at the window start.
  const ranges: { from: number; to: number }[] = []
  if (segs.length && sessions[win.start]) {
    let cur = sessions[win.start].kmStart
    for (const s of segs) { ranges.push({ from: cur, to: cur + s.km }); cur += s.km }
  }

  const canSaveAbsorb = !!gap && segs.length >= 2
  const canSaveExtra = !!gap && extraSum === gapDist &&
    clients.every((c) => c.client_name.trim() && c.client_signature && num(c.km) > 0)
  const canSave = mode === 'absorb' ? canSaveAbsorb : canSaveExtra

  const saveAbsorb = async () => {
    if (!gap || !data || segs.length < 2) return
    setSaving(true); setError('')
    try {
      await foiParcursApi.retileGap({
        vin: data.vin, year, month,
        allocations: segs.map((s) => ({ id: s.id, distance: s.km })),
      })
      onClose(true)
    } catch (e: any) {
      setError(e?.data?.error || e?.message || 'Redistribuirea a eșuat')
    } finally {
      setSaving(false)
    }
  }

  const saveExtra = async () => {
    if (!gap || !data) return
    for (const c of clients) {
      if (!c.client_name.trim()) return setError('Fiecare client trebuie să aibă un nume.')
      if (num(c.km) <= 0) return setError('Fiecare client trebuie să aibă KM > 0.')
      if (!c.client_signature) return setError('Fiecare client trebuie să semneze.')
    }
    if (extraSum !== gapDist) return setError(`Suma KM (${extraSum}) trebuie să fie ${gapDist} km.`)
    let cursor = gap.kmStart
    const contracts = clients.map((c) => {
      const km = num(c.km)
      const item = {
        date, client_name: c.client_name.trim(),
        km_start: cursor, km_end: cursor + km,
        advisor_name: c.advisor_name.trim() || undefined,
        client_signature: c.client_signature,
        driver_license_photo: c.license_photo || undefined,
        driver_license_number: c.license_number.trim() || undefined,
        driver_license_expiry: c.license_expiry.trim() || undefined,
      }
      cursor += km
      return item
    })
    setSaving(true); setError('')
    try {
      await foiParcursApi.redistributeGap(data.vin, year, month, contracts)
      onClose(true)
    } catch (e: any) {
      setError(e?.data?.error || e?.message || 'Redistribuirea a eșuat')
    } finally {
      setSaving(false)
    }
  }

  const Tally = ({ sum }: { sum: number }) => (
    <div className={`text-xs font-medium ${sum === gapDist ? 'text-emerald-600' : 'text-red-600'}`}>
      Alocat {sum} / {gapDist} km {sum === gapDist ? '✓' : `(${gapDist - sum > 0 ? '−' : '+'}${Math.abs(gapDist - sum)})`}
    </div>
  )

  return (
    <Dialog open={!!data} onOpenChange={(o) => { if (!o) onClose(false) }}>
      <DialogContent className="w-[95vw] max-w-[1080px] sm:max-w-[1080px] max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Rezolvă gap</DialogTitle>
        </DialogHeader>
        {gap && (
          <>
            <p className="text-sm text-muted-foreground">
              {gap.distance} km nejustificați ({gap.kmStart} → {gap.kmEnd}) · între {dFrom} și {dTo}
            </p>
            <Tabs value={mode} onValueChange={(v) => { setMode(v as 'absorb' | 'extra'); setError('') }}>
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="absorb">Absorb în sesiuni</TabsTrigger>
                <TabsTrigger value="extra">Client extra</TabsTrigger>
              </TabsList>

              {/* ── Absorb: distribute the gap across a window of EXISTING sessions (no new lines) ── */}
              <TabsContent value="absorb" className="space-y-3 pt-2">
                <p className="text-xs text-muted-foreground">
                  Distribuie km-ii între sesiunile existente — trage de separatoare. Adaugă orice altă sesiune din lună (nu doar vecinii) cu selectorul de mai jos. Nu se creează linii noi.
                </p>

                <div className="flex items-center justify-between gap-2">
                  <div className="text-xs">
                    <span className="font-medium">Total de distribuit: {windowGapTotal} km</span>
                    {extraGaps > 0 && (
                      <span className="ml-1 text-amber-600">· fereastra acoperă și alte gap-uri (+{extraGaps} km)</span>
                    )}
                  </div>
                  <Button type="button" variant="ghost" size="sm" className="h-7 text-xs" onClick={resetAbsorb}>
                    <RotateCcw className="mr-1 h-3.5 w-3.5" /> Resetează
                  </Button>
                </div>

                <GapSplitBar segs={segs} gapDist={winSpan} onChange={setSegs} />

                <div className="rounded-md border divide-y text-sm">
                  {segs.map((s, i) => {
                    const r = ranges[i]
                    const extra = s.km - s.min
                    const absIdx = win.start + i
                    const isOutermostAdded =
                      (absIdx === win.start && win.start < upperIdx) ||
                      (absIdx === win.end && win.end > lowerIdx)
                    return (
                      <div key={s.id} className="flex items-center gap-2 p-2">
                        <span className={`h-3 w-3 rounded-sm ${SEG_COLORS[i % SEG_COLORS.length]} opacity-85 shrink-0`} />
                        <span className="flex-1 font-medium truncate">{s.driver}</span>
                        <span className="text-[11px] text-muted-foreground tabular-nums whitespace-nowrap">{r?.from} → {r?.to}</span>
                        <Badge variant="outline" className="tabular-nums">{s.km} km</Badge>
                        {extra > 0 && <Badge className="bg-emerald-600 hover:bg-emerald-600 tabular-nums">+{extra}</Badge>}
                        {isOutermostAdded && (
                          <Button type="button" variant="ghost" size="icon" className="h-7 w-7"
                            onClick={absIdx === win.start ? removeUp : removeDown}>
                            <XIcon className="h-3.5 w-3.5" />
                          </Button>
                        )}
                      </div>
                    )
                  })}
                </div>

                {outOfWindow.length > 0 && (
                  <Select value="" onValueChange={(v) => addSession(Number(v))}>
                    <SelectTrigger className="h-8 text-sm w-full">
                      <SelectValue placeholder="+ Adaugă o sesiune din lună (oricare)" />
                    </SelectTrigger>
                    <SelectContent>
                      {outOfWindow.some((i) => i < win.start) && (
                        <SelectGroup>
                          <SelectLabel>Mai sus (înainte de gap)</SelectLabel>
                          {outOfWindow.filter((i) => i < win.start).map((idx) => (
                            <SelectItem key={sessions[idx].id} value={String(idx)}>
                              {sessions[idx].driver} · {sessions[idx].kmStart}–{sessions[idx].kmEnd} km
                            </SelectItem>
                          ))}
                        </SelectGroup>
                      )}
                      {outOfWindow.some((i) => i > win.end) && (
                        <SelectGroup>
                          <SelectLabel>Mai jos (după gap)</SelectLabel>
                          {outOfWindow.filter((i) => i > win.end).map((idx) => (
                            <SelectItem key={sessions[idx].id} value={String(idx)}>
                              {sessions[idx].driver} · {sessions[idx].kmStart}–{sessions[idx].kmEnd} km
                            </SelectItem>
                          ))}
                        </SelectGroup>
                      )}
                    </SelectContent>
                  </Select>
                )}
                <p className="text-[11px] text-muted-foreground">
                  Adăugarea unei sesiuni mai îndepărtate include automat și sesiunile dintre ele (rămâne continuu). Pentru un șofer nou documentat, folosește fila <b>Client extra</b>.
                </p>
              </TabsContent>

              {/* ── Client extra: up to 3 documented drivers tiling the gap ── */}
              <TabsContent value="extra" className="space-y-3 pt-2">
                <div className="flex items-center justify-between gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Data</Label>
                    <Input type="date" min={dFrom} max={dTo} className="h-8 w-[160px]" value={date} onChange={(e) => setDate(e.target.value)} />
                  </div>
                  <Tally sum={extraSum} />
                </div>
                {clients.map((c, i) => (
                  <ExtraClientCard
                    key={i} idx={i} c={c} canRemove={clients.length > 1}
                    onChange={(patch) => setClient(i, patch)} onRemove={() => removeClient(i)}
                  />
                ))}
                {clients.length < 3 && (
                  <Button type="button" variant="outline" size="sm" className="h-7" onClick={addClient}>
                    <Plus className="mr-1 h-3.5 w-3.5" /> Adaugă client
                  </Button>
                )}
                <p className="text-[11px] text-muted-foreground">
                  Clienții acoperă gap-ul în ordine ({gap.kmStart} → {gap.kmEnd}); suma KM trebuie să fie {gap.distance}.
                </p>
              </TabsContent>
            </Tabs>
          </>
        )}
        {error && <div className="text-sm text-red-600">{error}</div>}
        <DialogFooter>
          <Button variant="outline" onClick={() => onClose(false)} disabled={saving}>Anulează</Button>
          <Button onClick={mode === 'absorb' ? saveAbsorb : saveExtra} disabled={saving || !canSave}>
            {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Save className="mr-1.5 h-4 w-4" />}
            Salvează
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Foaie de Parcurs — collect Normă/Alimentări, generate (AI), preview, download ──
type AlimRow = { date: string; bon: string; liters: string; lei: string; unit: 'l' | 'kWh' }
type EventRow = { name: string; start: string; end: string }

function RouteSheetPreviewDialog({ vin, year, month, stored, vehicleNorma, vehicleNormaEnergie, vehicleFuelType, onClose }: {
  vin: string | null; year: number; month: number; stored: StoredRouteSheet | null
  vehicleNorma: number | null; vehicleNormaEnergie: number | null; vehicleFuelType: string | null; onClose: () => void
}) {
  const usesTank = usesFuelTank(vehicleFuelType || undefined)
  const usesBatt = usesBattery(vehicleFuelType || undefined)
  const [url, setUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [norma, setNorma] = useState('')
  const [normaEnergie, setNormaEnergie] = useState('')
  const [alim, setAlim] = useState<AlimRow[]>([])
  const [events, setEvents] = useState<EventRow[]>([])

  // Period bounds for "Din evenimente" (HR calendar events that fall in the month).
  const periodMin = `${year}-${String(month).padStart(2, '0')}-01`
  const periodMax = `${year}-${String(month).padStart(2, '0')}-${String(new Date(year, month, 0).getDate()).padStart(2, '0')}`
  const { data: hrEvents } = useQuery({
    queryKey: ['hr-events-for-routesheet'],
    queryFn: () => hrApi.getEvents(),
    enabled: !!vin,
    staleTime: 60_000,
  })
  const periodEvents = (hrEvents ?? []).filter((e) => e.start_date <= periodMax && e.end_date >= periodMin)

  const load = useCallback(async (regenerate: boolean) => {
    if (!vin) return
    setLoading(true); setError('')
    try {
      const alimentari: RouteSheetAlimentare[] = alim
        .filter((a) => a.date || a.bon || a.liters || a.lei)
        .map((a) => ({ date: a.date, bon: a.bon, liters: Number(a.liters || 0), lei: Number(a.lei || 0), unit: a.unit }))
      const evPayload: RouteSheetEvent[] = events
        .filter((e) => e.name.trim())
        .map((e) => ({ name: e.name.trim(), start: e.start, end: e.end || e.start }))
      const blob = await foiParcursApi.generateRouteSheetPdf(vin, year, month, {
        regenerate, norma: norma ? Number(norma) : null, norma_energie: normaEnergie ? Number(normaEnergie) : null, alimentari, events: evPayload,
      })
      setUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return URL.createObjectURL(blob) })
    } catch (e: any) {
      setError(e?.message || 'Eroare la generarea documentului')
    } finally {
      setLoading(false)
    }
  }, [vin, year, month, norma, normaEnergie, alim, events])

  // On open: prefill the form from the stored sheet, and if one exists show it.
  useEffect(() => {
    if (!vin) return
    // Prefill Normă from the stored sheet, else fall back to the car profile.
    setNorma(
      stored?.norma_combustibil != null ? String(stored.norma_combustibil)
        : vehicleNorma != null ? String(vehicleNorma) : '',
    )
    setNormaEnergie(
      stored?.norma_energie != null ? String(stored.norma_energie)
        : vehicleNormaEnergie != null ? String(vehicleNormaEnergie) : '',
    )
    setAlim(
      Array.isArray(stored?.alimentari)
        ? stored!.alimentari!.map((a) => ({ date: a.date || '', bon: a.bon || '', liters: String(a.liters ?? ''), lei: String(a.lei ?? ''), unit: a.unit === 'kWh' ? 'kWh' : 'l' as 'l' | 'kWh' }))
        : [],
    )
    setEvents(
      Array.isArray(stored?.evenimente)
        ? stored!.evenimente!.map((e) => ({ name: e.name || '', start: e.start || '', end: e.end || e.start || '' }))
        : [],
    )
    setError('')
    setUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return null })
    if (stored) load(false) // show the saved PDF immediately
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vin])

  const setRow = (i: number, k: keyof AlimRow, v: string) =>
    setAlim((p) => p.map((a, idx) => (idx === i ? { ...a, [k]: v } : a)))
  const addRow = (unit: 'l' | 'kWh') => setAlim((p) => [...p, { date: periodMin, bon: '', liters: '', lei: '', unit }])
  const removeRow = (i: number) => setAlim((p) => p.filter((_, idx) => idx !== i))
  // Entries carry their original index so the two sections can edit the shared list.
  const fuelEntries = alim.map((a, i) => ({ a, i })).filter((x) => x.a.unit !== 'kWh')
  const energyEntries = alim.map((a, i) => ({ a, i })).filter((x) => x.a.unit === 'kWh')
  const consumSection = (kind: 'l' | 'kWh', entries: { a: AlimRow; i: number }[], normaVal: string, setNormaVal: (v: string) => void) => {
    const isE = kind === 'kWh'
    return (
      <>
        <div className="space-y-1.5">
          <Label className="text-xs">{isE ? 'Normă energie (kWh/100 km)' : 'Normă consum (l/100 km)'}</Label>
          <Input type="number" step="0.1" value={normaVal} onChange={(e) => setNormaVal(e.target.value)} placeholder={isE ? 'ex. 17.5' : 'ex. 6.5'} />
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label className="text-xs">{isE ? 'Încărcări' : 'Alimentări'}</Label>
            <Button type="button" variant="outline" size="sm" className="h-7" onClick={() => addRow(kind)}>
              <Plus className="mr-1 h-3.5 w-3.5" /> Adaugă
            </Button>
          </div>
          {entries.length === 0 && <p className="text-xs text-muted-foreground">{isE ? 'Nicio încărcare. Adaugă bonurile de energie.' : 'Nicio alimentare. Adaugă bonurile de combustibil.'}</p>}
          {entries.map(({ a, i }) => (
            <div key={i} className="flex items-center gap-1.5">
              <Input type="date" className="h-8 w-[118px] shrink-0 text-xs" value={a.date} onChange={(e) => setRow(i, 'date', e.target.value)} />
              <Input className="h-8 flex-1 min-w-0 text-xs" placeholder="Bon" value={a.bon} onChange={(e) => setRow(i, 'bon', e.target.value)} />
              <Input type="number" step="0.01" className="h-8 w-20 shrink-0 text-xs" placeholder={isE ? 'kWh' : 'Litri'} value={a.liters} onChange={(e) => setRow(i, 'liters', e.target.value)} />
              <Input type="number" step="0.01" className="h-8 w-20 shrink-0 text-xs" placeholder="Lei" value={a.lei} onChange={(e) => setRow(i, 'lei', e.target.value)} />
              <Button type="button" variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={() => removeRow(i)}>
                <XIcon className="h-3.5 w-3.5" />
              </Button>
            </div>
          ))}
        </div>
      </>
    )
  }

  const setEventRow = (i: number, k: keyof EventRow, v: string) =>
    setEvents((p) => p.map((e, idx) => (idx === i ? { ...e, [k]: v } : e)))
  const addEvent = () => setEvents((p) => [...p, { name: '', start: '', end: '' }])
  const removeEvent = (i: number) => setEvents((p) => p.filter((_, idx) => idx !== i))
  const importEvent = (name: string, start: string, end: string) =>
    setEvents((p) => (p.some((e) => e.name === name && e.start === start) ? p : [...p, { name, start, end }]))

  const fileName = `foaie-parcurs-${vin}-${year}-${String(month).padStart(2, '0')}.pdf`

  return (
    <Dialog open={!!vin} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="w-[95vw] max-w-[1120px] sm:max-w-[1120px] max-h-[92vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>Foaie de parcurs — <span className="font-mono text-sm">{vin}</span></DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-[380px_1fr] flex-1 overflow-hidden">
          {/* Left: user-entered fuel inputs */}
          <div className="space-y-3 overflow-y-auto pr-1">
            {usesTank && consumSection('l', fuelEntries, norma, setNorma)}
            {usesBatt && consumSection('kWh', energyEntries, normaEnergie, setNormaEnergie)}

            {/* Evenimente — tie Comodat sessions to promo events (AI). Import from
                the HR calendar (period) or add manually. */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label className="text-xs">Evenimente (promovare)</Label>
                <div className="flex gap-1.5">
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button type="button" variant="outline" size="sm" className="h-7" disabled={!periodEvents.length}
                        title={periodEvents.length ? undefined : 'Niciun eveniment în această lună'}>
                        <Search className="mr-1 h-3.5 w-3.5" /> Din evenimente
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="max-h-[240px] overflow-y-auto">
                      {periodEvents.map((e) => (
                        <DropdownMenuItem key={e.id} onClick={() => importEvent(e.name, e.start_date, e.end_date)}>
                          <span className="truncate">{e.name}</span>
                          <span className="ml-2 text-xs text-muted-foreground">{e.start_date}{e.end_date && e.end_date !== e.start_date ? `–${e.end_date}` : ''}</span>
                        </DropdownMenuItem>
                      ))}
                    </DropdownMenuContent>
                  </DropdownMenu>
                  <Button type="button" variant="outline" size="sm" className="h-7" onClick={addEvent}>
                    <Plus className="mr-1 h-3.5 w-3.5" /> Adaugă
                  </Button>
                </div>
              </div>
              {events.length === 0 && <p className="text-xs text-muted-foreground">Fără evenimente. O cursă se leagă de un eveniment doar dacă data ei e în intervalul evenimentului.</p>}
              {events.map((e, i) => (
                <div key={i} className="space-y-1">
                  <div className="flex items-center gap-1.5">
                    <Input className="h-8 flex-1 min-w-0 text-xs" placeholder="Nume eveniment" value={e.name} onChange={(ev) => setEventRow(i, 'name', ev.target.value)} />
                    <Button type="button" variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={() => removeEvent(i)}>
                      <XIcon className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Input type="date" className="h-8 flex-1 text-xs" title="Început" value={e.start} onChange={(ev) => setEventRow(i, 'start', ev.target.value)} />
                    <span className="text-xs text-muted-foreground">–</span>
                    <Input type="date" className="h-8 flex-1 text-xs" title="Sfârșit" min={e.start || undefined} value={e.end} onChange={(ev) => setEventRow(i, 'end', ev.target.value)} />
                  </div>
                </div>
              ))}
            </div>

            <Button className="w-full" onClick={() => load(true)} disabled={loading}>
              <Sparkles className="mr-1.5 h-4 w-4" /> {url ? 'Regenerează' : 'Generează'}
            </Button>
            {error && <div className="text-sm text-red-600">{error}</div>}
          </div>

          {/* Right: PDF preview */}
          <div className="min-h-[60vh] rounded border bg-muted/20 overflow-hidden">
            {loading ? (
              <div className="flex h-[60vh] items-center justify-center gap-2 text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin" /> Se generează documentul cu AI…
              </div>
            ) : url ? (
              <iframe src={url} title="Foaie de parcurs" className="h-[60vh] w-full" />
            ) : (
              <div className="flex h-[60vh] items-center justify-center text-sm text-muted-foreground px-6 text-center">
                Completează normă/alimentări (opțional) și apasă „Generează”.
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          {url && !loading && (
            <a href={url} download={fileName}>
              <Button><Download className="mr-1.5 h-4 w-4" /> Descarcă PDF</Button>
            </a>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Sesiuni Driving Tab — TD sessions (historical record) ──
// sessionStatus/SessionStatusKey now live in ./sessionStatus.ts (shared with
// CalendarTab — keeping them here would make index.tsx → CalendarTab.tsx →
// index.tsx a circular import).
export { sessionStatus, type SessionStatusKey }

/** Export modal for the Parcurs history: pick a period (quick presets or a
 *  custom from–to) and optionally a single car, then download the session list
 *  as .xlsx or the contract PDFs as a .zip. Downloads go through authenticated
 *  GET links (session cookie), so a plain anchor click suffices. */
function ExportDialog({
  open, onOpenChange, companyId, vehicles, brand, from, to, vin, setFrom, setTo, setVin,
}: {
  open: boolean
  onOpenChange: (o: boolean) => void
  companyId: number
  vehicles: FpVehicle[]
  brand: string
  from: string
  to: string
  vin: string
  setFrom: (v: string) => void
  setTo: (v: string) => void
  setVin: (v: string) => void
}) {
  const pad = (n: number) => String(n).padStart(2, '0')
  const ymd = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  const setThisMonth = () => {
    const d = new Date()
    setFrom(ymd(new Date(d.getFullYear(), d.getMonth(), 1)))
    setTo(ymd(d))
  }
  const setLastMonth = () => {
    const d = new Date()
    setFrom(ymd(new Date(d.getFullYear(), d.getMonth() - 1, 1)))
    setTo(ymd(new Date(d.getFullYear(), d.getMonth(), 0)))
  }

  const carOptions = vehicles.filter(
    (v) => (!companyId || v.company_id === companyId) && (!brand || v.brand === brand),
  )
  const params = {
    company_id: companyId || undefined,
    date_from: from || undefined,
    date_to: to || undefined,
    vin: vin !== 'all' ? vin : undefined,
  }
  const download = (url: string) => {
    const a = document.createElement('a')
    a.href = url
    a.rel = 'noopener'
    document.body.appendChild(a)
    a.click()
    a.remove()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>Export sesiuni</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label className="text-xs">Perioadă</Label>
            <div className="flex gap-2">
              <Button type="button" size="sm" variant="outline" onClick={setThisMonth}>Luna aceasta</Button>
              <Button type="button" size="sm" variant="outline" onClick={setLastMonth}>Luna trecută</Button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label className="text-xs">De la</Label>
                <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Până la</Label>
                <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
              </div>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Mașină</Label>
            <Select value={vin} onValueChange={setVin}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Toate mașinile</SelectItem>
                {carOptions.map((v) => (
                  <SelectItem key={v.id} value={v.vin}>
                    {[v.mark, v.model].filter(Boolean).join(' ')} — {v.registration_number || v.vin}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter className="flex-col sm:flex-row gap-2">
          <Button variant="outline" className="w-full sm:w-auto" onClick={() => download(foiParcursApi.getExportXlsxUrl(params))}>
            <FileSpreadsheet className="mr-1.5 h-4 w-4" /> Export Excel
          </Button>
          <Button className="w-full sm:w-auto" onClick={() => download(foiParcursApi.getExportContractsZipUrl(params))}>
            <FileText className="mr-1.5 h-4 w-4" /> Export contracte (ZIP)
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function SessionsTab({ companyId, brand, onActivate, onReturn }: { companyId: number; brand: string; onActivate?: (id: number) => void; onReturn?: (id: number) => void }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const now = new Date()
  const [allocatingContract, setAllocatingContract] = useState<FoiContract | null>(null)
  const [expandedRow, setExpandedRow] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [filterVin, setFilterVin] = useState<string>('all')
  const [filterStatus, setFilterStatus] = useState<string>('all')
  const [filterMonth, setFilterMonth] = useState<string>('all')
  const [filterYear, setFilterYear] = useState<string>('all')
  const [sortBy, setSortBy] = useState('departure_datetime')
  const [sortDir, setSortDir] = useState('DESC')

  // ── Export modal ──
  const [exportOpen, setExportOpen] = useState(false)
  const [expFrom, setExpFrom] = useState('')
  const [expTo, setExpTo] = useState('')
  const [expVin, setExpVin] = useState('all')

  const isAdmin = ['admin', 'superadmin'].includes((user?.role_name ?? '').toLowerCase())

  const { data, isLoading } = useQuery({
    queryKey: ['foi-contracts-all', companyId],
    queryFn: () =>
      foiParcursApi.getContracts({ company_id: companyId || undefined, per_page: 1000, sort_by: 'created_at', sort_dir: 'DESC' }),
    staleTime: 30_000,
  })

  // Admin-only registration cleanup (delete) + reset a completed TD to 'driving'.
  const deleteContractMutation = useMutation({
    mutationFn: (id: number) => foiParcursApi.deleteContract(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['foi-contracts-all'] }),
  })
  const resetContractMutation = useMutation({
    mutationFn: (id: number) => foiParcursApi.resetContract(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['foi-contracts-all'] })
      queryClient.invalidateQueries({ queryKey: ['odometer-history'] })
    },
  })
  // Discard a PLANNED draft (any TD user — same gate as create). Only PLANNED
  // rows are eligible; the backend 409s otherwise.
  const discardMutation = useMutation({
    mutationFn: (id: number) => foiParcursApi.discardTestDrive(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['foi-contracts-all'] }),
  })

  // Vehicles → vin→brand map, so contracts can be filtered by the selected brand
  const { data: vehiclesData } = useQuery({
    queryKey: ['fp-vehicles'],
    queryFn: () => foiParcursApi.getVehicles(),
    staleTime: 30_000,
  })
  const vehiclesList = vehiclesData?.vehicles ?? []
  const vinBrand = new Map(vehiclesList.map((v) => [v.vin, v.brand]))
  const vinVehicle = new Map(vehiclesList.map((v) => [v.vin, v]))

  const allContracts = data?.contracts ?? []

  // Apply filters
  const filtered = allContracts.filter((c) => {
    if (c.route_type !== 'TD') return false
    if (brand && vinBrand.get(c.vin) !== brand) return false
    if (filterVin !== 'all' && c.vin !== filterVin) return false
    if (filterStatus !== 'all' && sessionStatus(c).key !== filterStatus) return false
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
  const sortVal = (c: FoiContract): string | number => {
    if (sortBy === 'departure_datetime') return c.departure_datetime || c.created_at || ''
    return ((c as any)[sortBy] ?? '') as string | number
  }
  const sorted = [...filtered].sort((a, b) => {
    const aVal = sortVal(a)
    const bVal = sortVal(b)
    const cmp = typeof aVal === 'number' && typeof bVal === 'number'
      ? aVal - bVal
      : String(aVal).localeCompare(String(bVal))
    return sortDir === 'ASC' ? cmp : -cmp
  })

  const toggleSort = (col: string) => {
    if (sortBy === col) setSortDir((d) => (d === 'ASC' ? 'DESC' : 'ASC'))
    else { setSortBy(col); setSortDir('ASC') }
  }

  const countBy = (k: SessionStatusKey) => filtered.filter((c) => sessionStatus(c).key === k).length
  const planificatCount = countBy('planificat')
  const finalizatCount = countBy('finalizat')
  const drivingCount = countBy('driving')
  const intarziatCount = countBy('intarziat')
  const nealocatCount = countBy('nealocat')

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
              <SelectItem value="planificat">Planificat</SelectItem>
              <SelectItem value="finalizat">Finalizat</SelectItem>
              <SelectItem value="driving">În desfășurare</SelectItem>
              <SelectItem value="intarziat">Întârziat</SelectItem>
              <SelectItem value="nealocat">Nealocat</SelectItem>
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
        <div className="space-y-1.5">
          <Label className="text-xs opacity-0 select-none">Export</Label>
          <Button size="sm" variant="outline" className="h-8" onClick={() => setExportOpen(true)}>
            <Download className="mr-1.5 h-4 w-4" />
            Export
          </Button>
        </div>
      </div>

      <ExportDialog
        open={exportOpen}
        onOpenChange={setExportOpen}
        companyId={companyId}
        vehicles={vehiclesData?.vehicles ?? []}
        brand={brand}
        from={expFrom}
        to={expTo}
        vin={expVin}
        setFrom={setExpFrom}
        setTo={setExpTo}
        setVin={setExpVin}
      />

      {/* Summary badges */}
      <div className="flex gap-2 text-sm">
        <Badge variant="outline">{filtered.length} sesiuni</Badge>
        {planificatCount > 0 && <Badge className="bg-indigo-600">{planificatCount} planificate</Badge>}
        {finalizatCount > 0 && <Badge className="bg-green-600">{finalizatCount} finalizate</Badge>}
        {drivingCount > 0 && <Badge className="bg-blue-600">{drivingCount} în desfășurare</Badge>}
        {intarziatCount > 0 && <Badge className="bg-red-600">{intarziatCount} întârziate</Badge>}
        {nealocatCount > 0 && <Badge variant="outline">{nealocatCount} nealocate</Badge>}
      </div>

      {/* Table */}
      {isLoading ? (
        <TableSkeleton rows={8} columns={9} />
      ) : !sorted.length ? (
        <EmptyState
          icon={<FileText className="h-10 w-10" />}
          title="No contracts found"
          description={allContracts.length ? 'Try adjusting your filters.' : 'Generate and save a batch from the Foi de Parcurs tab first.'}
        />
      ) : (
        <Card className="overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <SortableHeader col="departure_datetime" label="Date" current={sortBy} dir={sortDir} toggle={toggleSort} />
                <SortableHeader col="status" label="Status" current={sortBy} dir={sortDir} toggle={toggleSort} />
                <TableHead>Company</TableHead>
                <SortableHeader col="vin" label="Vehicle" current={sortBy} dir={sortDir} toggle={toggleSort} />
                <TableHead>Client</TableHead>
                <TableHead>Consilier</TableHead>
                <TableHead>KM</TableHead>
                <TableHead>Return</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((c) => {
                const isExpanded = expandedRow === c.id
                const ss = sessionStatus(c)
                const u = fuelUnit(c.fuel_tank_capacity_liters > 100 ? 'Electric' : undefined)
                return (
                  <React.Fragment key={c.id}>
                    <TableRow
                      className={`cursor-pointer hover:bg-muted/40 ${ss.rowClass}`}
                      onClick={() => setExpandedRow(isExpanded ? null : c.id)}
                    >
                      <TableCell className="text-xs whitespace-nowrap">
                        {c.departure_datetime
                          ? naiveDate(c.departure_datetime)!.toLocaleDateString('ro-RO', { day: '2-digit', month: 'short', year: 'numeric' })
                          : new Date(c.created_at).toLocaleDateString('ro-RO', { day: '2-digit', month: 'short', year: 'numeric' })}
                      </TableCell>
                      <TableCell>
                        <Badge className={`text-xs ${ss.badgeClass}`}>{ss.label}</Badge>
                      </TableCell>
                      <TableCell className="text-xs">{c.company_name || '—'}</TableCell>
                      <TableCell className="text-xs">
                        {(() => {
                          const v = vinVehicle.get(c.vin)
                          const name = v ? [v.brand || v.mark, v.model].filter(Boolean).join(' ') : ''
                          return (
                            <div className="leading-tight">
                              <div className="font-medium">{name || `${c.vin.slice(0, 12)}...`}</div>
                              {v?.registration_number && <div className="text-muted-foreground font-mono text-[11px]">{v.registration_number}</div>}
                            </div>
                          )
                        })()}
                      </TableCell>
                      <TableCell>
                        {c.client_name ? (
                          <span className="font-medium text-sm">{c.client_name}</span>
                        ) : (
                          <span className="text-muted-foreground text-xs">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-xs">{c.advisor_name || '—'}</TableCell>
                      <TableCell className="text-xs whitespace-nowrap">
                        {(() => {
                          const v = vinVehicle.get(c.vin)
                          const floor = v?.mileage_floor ?? v?.odometer_km ?? null
                          // Planned sessions snapshot km_start at plan time; show the car's
                          // live odometer floor instead so the number reflects reality
                          // (activation applies the same max(entered, floor) refresh).
                          const startKm = c.status === 'PLANNED' && floor != null ? Math.max(c.km_start ?? 0, floor) : c.km_start
                          // Only a finalised session carries a genuine return odometer —
                          // never replicate km_start as the end for planned/driving/overdue
                          // rows (which all still hold the km_start placeholder). Note
                          // return_datetime is the expected arrival, set at plan time, so it
                          // is NOT a "finished" signal.
                          const endKm = ss.key === 'finalizat' && c.km_end != null ? c.km_end : null
                          return (
                            <>
                              {startKm ?? '—'}
                              {endKm != null ? ` - ${endKm}` : ''}
                            </>
                          )
                        })()}
                      </TableCell>
                      <TableCell className="text-xs whitespace-nowrap">
                        {c.return_datetime
                          ? naiveDate(c.return_datetime)!.toLocaleString('ro-RO', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
                          : '—'}
                      </TableCell>
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center gap-1">
                          {c.status === 'PENDING' && (
                            <Button variant="outline" size="sm" onClick={() => setAllocatingContract(c)}>
                              <UserPlus className="mr-1 h-3.5 w-3.5" />
                              Allocate
                            </Button>
                          )}
                          {c.status === 'PLANNED' && (
                            <>
                              <Button variant="outline" size="sm" onClick={() => onActivate ? onActivate(c.id) : navigate(`/app/foi-parcurs/test-drive?activate=${c.id}`)}>
                                <PlayCircle className="mr-1 h-3.5 w-3.5" />
                                Începe sesiunea
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="text-destructive hover:text-destructive"
                                title="Renunță la planificare"
                                onClick={() => {
                                  if (confirm('Renunți la această sesiune planificată? Acțiunea nu poate fi anulată.')) {
                                    discardMutation.mutate(c.id)
                                  }
                                }}
                                disabled={discardMutation.isPending}
                              >
                                <XIcon className="h-4 w-4" />
                              </Button>
                            </>
                          )}
                          {c.status !== 'PENDING' && c.status !== 'PLANNED' && (
                            <a href={foiParcursApi.getContractPdfUrl(c.id, 'legal')} target="_blank" rel="noopener" title="Descarcă PDF">
                              <Button variant="ghost" size="sm">
                                <FileText className="h-4 w-4" />
                              </Button>
                            </a>
                          )}
                          {(ss.key === 'driving' || ss.key === 'intarziat') && (
                            onReturn ? (
                              <button
                                type="button"
                                className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline"
                                onClick={(e) => { e.stopPropagation(); onReturn(c.id) }}
                              >
                                <RotateCcw className="h-3.5 w-3.5" /> Retur
                              </button>
                            ) : (
                              <Link
                                to={`/app/foi-parcurs/test-drive/${c.id}/return`}
                                className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline"
                                onClick={(e) => e.stopPropagation()}
                              >
                                <RotateCcw className="h-3.5 w-3.5" /> Retur
                              </Link>
                            )
                          )}
                          {isAdmin && c.route_type === 'TD' && ss.key !== 'nealocat' && ss.key !== 'planificat' && (
                            <Button
                              variant="ghost"
                              size="sm"
                              title="Reset la 'driving' (re-testare retur)"
                              onClick={() => {
                                if (confirm('Resetezi acest test drive la „driving”? Datele de retur se șterg.')) {
                                  resetContractMutation.mutate(c.id)
                                }
                              }}
                              disabled={resetContractMutation.isPending}
                            >
                              <RotateCcw className="h-4 w-4" />
                            </Button>
                          )}
                          {isAdmin && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-destructive hover:text-destructive"
                              title="Șterge înregistrarea (permanent)"
                              onClick={() => {
                                if (confirm('Ștergi definitiv această înregistrare? Acțiunea nu poate fi anulată.')) {
                                  deleteContractMutation.mutate(c.id)
                                }
                              }}
                              disabled={deleteContractMutation.isPending}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                    {isExpanded && (
                      <TableRow className="bg-muted/30 border-l-4 border-l-primary/30">
                        <TableCell colSpan={9} className="px-6 py-4">
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
                                <span className="text-muted-foreground">VIN</span>
                                <span className="font-mono">{c.vin}</span>
                                <span className="text-muted-foreground">Plecare</span>
                                <span>{c.departure_datetime ? naiveDate(c.departure_datetime)!.toLocaleString('ro-RO') : '—'}</span>
                                <span className="text-muted-foreground">Retur</span>
                                <span>{c.return_datetime ? naiveDate(c.return_datetime)!.toLocaleString('ro-RO') : '—'}</span>
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
                          {/* PDF Downloads — none yet for a PLANNED draft (generated at activation) */}
                          {c.status !== 'PENDING' && c.status !== 'PLANNED' && (
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
  { key: 'mark', label: 'Mark', default: false },
  { key: 'vin', label: 'VIN', default: true },
  { key: 'car_id', label: 'Car ID', default: true },
  { key: 'reg_number', label: 'Reg. No.', default: true },
  { key: 'brand', label: 'Brand', default: false },
  { key: 'color', label: 'Color', default: false },
  { key: 'fuel_type', label: 'Fuel Type', default: true },
  { key: 'capacity', label: 'Capacity', default: true },
  { key: 'odometer', label: 'Odometer', default: true },
  { key: 'company', label: 'Company', default: false },
  { key: 'vignette', label: 'Rovinietă', default: false },
  { key: 'itp', label: 'ITP', default: false },
  { key: 'rca', label: 'RCA', default: false },
] as const

type StockColumnKey = (typeof STOCK_COLUMNS)[number]['key']

/** Formats a validity date + a color class: red if expired, amber within 30 days. */
function fmtValidity(dateStr?: string | null): string {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('ro-RO')
}
function validityCls(dateStr?: string | null): string {
  if (!dateStr) return 'text-muted-foreground'
  const d = new Date(dateStr)
  if (Number.isNaN(d.getTime())) return 'text-muted-foreground'
  const days = Math.floor((d.getTime() - Date.now()) / 86_400_000)
  if (days < 0) return 'text-red-600 font-semibold'
  if (days <= 30) return 'text-amber-600 font-semibold'
  return ''
}

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
  norma_combustibil: string
  norma_energie: string
  category: string
  company_id: string
  vignette_valid_until: string
  itp_valid_until: string
  insurance_valid_until: string
  insurance_doc: string
  talon_doc: string
  civ_doc: string
  registration_doc: string
  offer_doc: string
}

function emptyVehicleForm(companyId?: number): VehicleFormValue {
  return {
    car_id: '', vin: '', registration_number: '', mark: '', model: '', color: '',
    fuel_type: 'Diesel', fuel_tank_capacity_liters: 50, battery_capacity_kwh: 0,
    odometer_km: '', norma_combustibil: '', norma_energie: '', category: '', company_id: companyId ? String(companyId) : '',
    vignette_valid_until: '', itp_valid_until: '', insurance_valid_until: '',
    insurance_doc: '', talon_doc: '', civ_doc: '', registration_doc: '', offer_doc: '',
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
    norma_combustibil: v.norma_combustibil != null ? String(v.norma_combustibil) : '',
    norma_energie: v.norma_energie != null ? String(v.norma_energie) : '',
    category: v.category || '',
    company_id: v.company_id ? String(v.company_id) : '',
    vignette_valid_until: v.vignette_valid_until ? String(v.vignette_valid_until).slice(0, 10) : '',
    itp_valid_until: v.itp_valid_until ? String(v.itp_valid_until).slice(0, 10) : '',
    insurance_valid_until: v.insurance_valid_until ? String(v.insurance_valid_until).slice(0, 10) : '',
    insurance_doc: v.insurance_doc || '',
    talon_doc: v.talon_doc || '',
    civ_doc: v.civ_doc || '',
    registration_doc: v.registration_doc || '',
    offer_doc: v.offer_doc || '',
  }
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(String(r.result))
    r.onerror = reject
    r.readAsDataURL(file)
  })
}

/** Downscale big photos before storing as base64 (PDFs are kept as-is). */
function downscaleImage(dataUrl: string, maxDim = 1600, quality = 0.72): Promise<string> {
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => {
      let { width, height } = img
      if (Math.max(width, height) > maxDim) {
        const scale = maxDim / Math.max(width, height)
        width = Math.round(width * scale)
        height = Math.round(height * scale)
      }
      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      const ctx = canvas.getContext('2d')
      if (!ctx) return resolve(dataUrl)
      ctx.drawImage(img, 0, 0, width, height)
      resolve(canvas.toDataURL('image/jpeg', quality))
    }
    img.onerror = () => resolve(dataUrl)
    img.src = dataUrl
  })
}

async function fileToDoc(file: File): Promise<string> {
  const dataUrl = await fileToDataUrl(file)
  return file.type.startsWith('image/') ? downscaleImage(dataUrl) : dataUrl
}

/** Open a stored document in a new tab. Browsers block top-level navigation to
 *  `data:` URLs (so a plain <a href="data:..."> does nothing), so convert the
 *  base64 data URL to a Blob and open a `blob:` object URL instead. */
function openDoc(value: string) {
  if (!value) return
  if (!value.startsWith('data:')) {
    window.open(value, '_blank', 'noopener,noreferrer')
    return
  }
  try {
    const [meta, b64] = value.split(',', 2)
    const mime = meta.match(/data:([^;]+)/)?.[1] || 'application/octet-stream'
    const bin = atob(b64)
    const bytes = new Uint8Array(bin.length)
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
    const url = URL.createObjectURL(new Blob([bytes], { type: mime }))
    window.open(url, '_blank', 'noopener,noreferrer')
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch {
    window.open(value, '_blank', 'noopener,noreferrer')
  }
}

/** Upload / preview / clear a single base64 document (image or PDF). */
function DocUpload({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const isImg = value.startsWith('data:image')
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      {value ? (
        <div className="flex items-center gap-2">
          {isImg ? (
            <img src={value} alt={label} className="h-14 w-14 rounded border object-cover" />
          ) : (
            <div className="flex h-14 w-14 items-center justify-center rounded border bg-muted text-[10px] font-semibold text-muted-foreground">PDF</div>
          )}
          <button type="button" onClick={() => openDoc(value)} className="text-xs text-primary underline">Vezi</button>
          <button type="button" onClick={() => onChange('')} className="text-xs text-destructive">Șterge</button>
        </div>
      ) : (
        <label className="flex h-14 cursor-pointer items-center justify-center rounded border border-dashed text-xs text-muted-foreground hover:bg-muted/40">
          Încarcă (foto/PDF)
          <input
            type="file"
            accept="image/*,application/pdf"
            className="hidden"
            onChange={async (e) => {
              const f = e.target.files?.[0]
              e.target.value = ''
              if (f) onChange(await fileToDoc(f))
            }}
          />
        </label>
      )}
    </div>
  )
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
    <div className="space-y-4">
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
          <Input type="number" min={0} step="any" value={value.fuel_tank_capacity_liters} onChange={(e) => onChange({ fuel_tank_capacity_liters: Number(e.target.value) })} required />
        </div>
      )}
      {usesBattery(value.fuel_type) && (
        <div className="space-y-1.5">
          <Label className="text-xs">Battery capacity (kWh)</Label>
          <Input type="number" min={0} step="any" value={value.battery_capacity_kwh} onChange={(e) => onChange({ battery_capacity_kwh: Number(e.target.value) })} required />
        </div>
      )}
      <div className="space-y-1.5">
        <Label className="text-xs">Starting odometer (km)</Label>
        <Input type="number" min={0} value={value.odometer_km} onChange={(e) => onChange({ odometer_km: e.target.value })} placeholder="e.g., 12" />
      </div>
      {usesFuelTank(value.fuel_type) && (
        <div className="space-y-1.5">
          <Label className="text-xs">Normă consum (l/100 km)</Label>
          <Input type="number" min={0} step="0.1" value={value.norma_combustibil} onChange={(e) => onChange({ norma_combustibil: e.target.value })} placeholder="ex. 6.5" />
        </div>
      )}
      {usesBattery(value.fuel_type) && (
        <div className="space-y-1.5">
          <Label className="text-xs">Normă energie (kWh/100 km)</Label>
          <Input type="number" min={0} step="0.1" value={value.norma_energie} onChange={(e) => onChange({ norma_energie: e.target.value })} placeholder="ex. 17.5" />
        </div>
      )}
      <div className="space-y-1.5">
        <Label className="text-xs">Categorie</Label>
        <Input value={value.category} onChange={(e) => onChange({ category: e.target.value })} placeholder="ex. AUTOTURISM M1G" />
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

    <div className="space-y-3 border-t pt-4">
      <p className="text-sm font-semibold">Documente & Valabilități</p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div className="space-y-1.5">
          <Label className="text-xs">Rovinietă valabilă până la</Label>
          <Input type="date" value={value.vignette_valid_until} onChange={(e) => onChange({ vignette_valid_until: e.target.value })} />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">ITP valabil până la</Label>
          <Input type="date" value={value.itp_valid_until} onChange={(e) => onChange({ itp_valid_until: e.target.value })} />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">RCA valabil până la</Label>
          <Input type="date" value={value.insurance_valid_until} onChange={(e) => onChange({ insurance_valid_until: e.target.value })} />
        </div>
        <DocUpload label="Asigurare (RCA)" value={value.insurance_doc} onChange={(v) => onChange({ insurance_doc: v })} />
        <DocUpload label="Talon" value={value.talon_doc} onChange={(v) => onChange({ talon_doc: v })} />
        <DocUpload label="Carte de identitate (CIV)" value={value.civ_doc} onChange={(v) => onChange({ civ_doc: v })} />
        <DocUpload label="Documente înmatriculare" value={value.registration_doc} onChange={(v) => onChange({ registration_doc: v })} />
      <DocUpload label="Ofertă (trimisă pe email după test drive)" value={value.offer_doc} onChange={(v) => onChange({ offer_doc: v })} />
      </div>
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
  const [showArchived, setShowArchived] = useState(false)
  const [newVehicle, setNewVehicle] = useState<VehicleFormValue>(() => emptyVehicleForm(companyId))
  const [error, setError] = useState('')

  const { data: vehiclesData, isLoading } = useQuery({
    queryKey: ['fp-vehicles', companyId, showArchived],
    // active_only=false returns archived vehicles too (marked is_active=false).
    queryFn: () => foiParcursApi.getVehicles(!showArchived),
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
        norma_combustibil: newVehicle.norma_combustibil.trim() === '' ? null : Number(newVehicle.norma_combustibil),
        norma_energie: newVehicle.norma_energie.trim() === '' ? null : Number(newVehicle.norma_energie),
        category: newVehicle.category.trim() || null,
        company_id: newVehicle.company_id ? Number(newVehicle.company_id) : undefined,
        vignette_valid_until: newVehicle.vignette_valid_until || undefined,
        itp_valid_until: newVehicle.itp_valid_until || undefined,
        insurance_valid_until: newVehicle.insurance_valid_until || undefined,
        insurance_doc: newVehicle.insurance_doc || undefined,
        talon_doc: newVehicle.talon_doc || undefined,
        civ_doc: newVehicle.civ_doc || undefined,
        registration_doc: newVehicle.registration_doc || undefined,
        offer_doc: newVehicle.offer_doc || undefined,
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

  // Archive a vehicle WITH a reason (Motive arhivare picker in the dialog).
  const [archivingVehicle, setArchivingVehicle] = useState<FpVehicle | null>(null)
  const archiveMutation = useMutation({
    mutationFn: (p: { id: number; category: string; note?: string }) =>
      foiParcursApi.archiveVehicle(p.id, { category: p.category, note: p.note }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fp-vehicles'] })
      setArchivingVehicle(null)
    },
  })

  // Restore an archived vehicle (is_active back to true).
  const restoreMutation = useMutation({
    mutationFn: (id: number) => foiParcursApi.updateVehicle(id, { is_active: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fp-vehicles'] })
    },
  })

  // Lockout — block/unblock a car from the driving park.
  const [lockingVehicle, setLockingVehicle] = useState<FpVehicle | null>(null)
  const lockMutation = useMutation({
    mutationFn: (p: { id: number; category: string; note?: string; until?: string | null }) =>
      foiParcursApi.lockVehicle(p.id, { category: p.category, note: p.note, until: p.until }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['fp-vehicles'] }); setLockingVehicle(null) },
  })
  const unlockMutation = useMutation({
    mutationFn: (id: number) => foiParcursApi.unlockVehicle(id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['fp-vehicles'] }); setLockingVehicle(null) },
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
    // The list row is lean (no document blobs), so seed the form from it, then
    // fetch the full vehicle to populate the docs. Without this fetch, saving
    // would send empty docs and wipe the stored files.
    setEditForm(vehicleToForm(v))
    foiParcursApi.getVehicle(v.id)
      .then((res) => {
        const full = res?.vehicle
        if (!full) return
        setEditForm((prev) =>
          prev.vin === v.vin
            ? {
                ...prev,
                insurance_doc: full.insurance_doc || '',
                talon_doc: full.talon_doc || '',
                civ_doc: full.civ_doc || '',
                registration_doc: full.registration_doc || '',
                offer_doc: full.offer_doc || '',
              }
            : prev,
        )
      })
      .catch(() => {/* keep the lean form; docs just won't preload */})
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
        norma_combustibil: editForm.norma_combustibil.trim() === '' ? null : Number(editForm.norma_combustibil),
        norma_energie: editForm.norma_energie.trim() === '' ? null : Number(editForm.norma_energie),
        category: editForm.category.trim() || null,
        company_id: editForm.company_id ? Number(editForm.company_id) : null,
        vignette_valid_until: editForm.vignette_valid_until || null,
        itp_valid_until: editForm.itp_valid_until || null,
        insurance_valid_until: editForm.insurance_valid_until || null,
        insurance_doc: editForm.insurance_doc || null,
        talon_doc: editForm.talon_doc || null,
        civ_doc: editForm.civ_doc || null,
        registration_doc: editForm.registration_doc || null,
        offer_doc: editForm.offer_doc || null,
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
        <div className="flex items-center gap-2">
          <label className="flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground">
            <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} className="rounded" />
            Arată arhivate
          </label>
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
                {show('vignette') && <TableHead>Rovinietă</TableHead>}
                {show('itp') && <TableHead>ITP</TableHead>}
                {show('rca') && <TableHead>RCA</TableHead>}
                <TableHead className="w-[100px]">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredVehicles.map((v) => (
                <React.Fragment key={v.id}>
                <TableRow
                  className={`cursor-pointer hover:bg-muted/40 ${v.is_active ? '' : 'opacity-60'}`}
                  onClick={() => setExpandedVehicleId((prev) => (prev === v.id ? null : v.id))}
                >
                  {show('model') && (
                    <TableCell>
                      {v.model}
                      {!v.is_active && (
                        <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">Arhivat</span>
                      )}
                      {v.is_active && (v.locked_out || v.blocked_now) && (
                        <span className="ml-2 rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold text-red-700 dark:bg-red-950/40 dark:text-red-300">
                          🔒 Blocat{v.blocked_now && !v.locked_out && v.active_block_end ? ` până ${fmtValidity(v.active_block_end)}` : ''}
                        </span>
                      )}
                      {v.is_active && !v.locked_out && !v.blocked_now && v.next_block_start && (
                        <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
                          🗓 Programat {fmtValidity(v.next_block_start)}
                        </span>
                      )}
                    </TableCell>
                  )}
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
                  {show('vignette') && (
                    <TableCell className={`whitespace-nowrap text-sm ${validityCls(v.vignette_valid_until)}`}>{fmtValidity(v.vignette_valid_until)}</TableCell>
                  )}
                  {show('itp') && (
                    <TableCell className={`whitespace-nowrap text-sm ${validityCls(v.itp_valid_until)}`}>{fmtValidity(v.itp_valid_until)}</TableCell>
                  )}
                  {show('rca') && (
                    <TableCell className={`whitespace-nowrap text-sm ${validityCls(v.insurance_valid_until)}`}>{fmtValidity(v.insurance_valid_until)}</TableCell>
                  )}
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <div className="flex gap-1">
                      {v.is_active ? (
                        <>
                          <Button variant="ghost" size="sm" onClick={() => startEdit(v)}>
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="sm" title="Blocare parc auto (imediată / programată)"
                            onClick={() => setLockingVehicle(v)}>
                            <Lock className={`h-4 w-4 ${(v.locked_out || v.blocked_now) ? 'text-red-600 dark:text-red-400' : ''}`} />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-destructive hover:text-destructive"
                            title="Arhivează vehiculul"
                            onClick={() => setArchivingVehicle(v)}
                            disabled={archiveMutation.isPending}
                          >
                            <Archive className="h-4 w-4" />
                          </Button>
                        </>
                      ) : (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-xs"
                          title="Restaurează vehiculul"
                          onClick={() => restoreMutation.mutate(v.id)}
                          disabled={restoreMutation.isPending}
                        >
                          <RotateCcw className="mr-1 h-4 w-4" />
                          Restaurează
                        </Button>
                      )}
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

      {lockingVehicle && (
        <LockVehicleDialog
          vehicle={lockingVehicle}
          submitting={lockMutation.isPending}
          onClose={() => setLockingVehicle(null)}
          onSubmit={(d) => lockMutation.mutate({ id: lockingVehicle.id, ...d })}
          onUnlock={() => unlockMutation.mutate(lockingVehicle.id)}
          unlocking={unlockMutation.isPending}
        />
      )}

      {archivingVehicle && (
        <ArchiveVehicleDialog
          vehicle={archivingVehicle}
          submitting={archiveMutation.isPending}
          onClose={() => setArchivingVehicle(null)}
          onSubmit={(d) => archiveMutation.mutate({ id: archivingVehicle.id, ...d })}
        />
      )}
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

type CompanyKmConfig = {
  company_id: number
  company_name: string
  td_km_min: number
  td_km_max: number
  comodat_km_min: number
  comodat_km_max: number
  km_gap: number
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

      {/* Section 3: Lockout reasons (Motive blocare) */}
      <LockoutReasonsSettings />

      {/* Section 4: Archive reasons (Motive arhivare) */}
      <ArchiveReasonsSettings />
    </div>
  )
}

// ── Lockout Reasons Settings — configurable "Motive blocare" ──
function LockoutReasonsSettings() {
  const queryClient = useQueryClient()
  const [newLabel, setNewLabel] = useState('')
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['fp-lockout-reasons'] })
    queryClient.invalidateQueries({ queryKey: ['fp-lockout-reasons', 'active'] })
  }

  const { data, isLoading } = useQuery({
    queryKey: ['fp-lockout-reasons', 'all'],
    queryFn: () => foiParcursApi.getLockoutReasons(false),
    staleTime: 30_000,
  })
  const reasons = data?.reasons ?? []

  const createMut = useMutation({
    mutationFn: (label: string) => foiParcursApi.createLockoutReason({ label, sort_order: reasons.length + 1 }),
    onSuccess: () => { setNewLabel(''); invalidate() },
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Lock className="h-5 w-5 text-muted-foreground" />
        <h3 className="text-lg font-semibold">Motive blocare</h3>
      </div>
      <p className="text-sm text-muted-foreground">
        Motivele disponibile când blochezi o mașină în parcul auto. Redenumește, reordonează sau dezactivează-le
        (dezactivarea le ascunde la blocări noi fără a afecta mașinile deja blocate).
      </p>

      <Card className="p-4 space-y-3 max-w-2xl">
        {/* Add new */}
        <div className="flex items-end gap-2">
          <div className="flex-1 space-y-1">
            <Label className="text-xs">Motiv nou</Label>
            <Input
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              placeholder="Ex: Rezervat, Vândut…"
              onKeyDown={(e) => { if (e.key === 'Enter' && newLabel.trim()) createMut.mutate(newLabel.trim()) }}
            />
          </div>
          <Button onClick={() => createMut.mutate(newLabel.trim())} disabled={!newLabel.trim() || createMut.isPending}>
            <Plus className="h-4 w-4 mr-1" /> Adaugă
          </Button>
        </div>

        {/* List */}
        {isLoading ? (
          <p className="text-sm text-muted-foreground py-4">Se încarcă…</p>
        ) : reasons.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4">Niciun motiv configurat.</p>
        ) : (
          <div className="divide-y">
            {reasons.map((r) => (
              <LockoutReasonRow key={r.id} reason={r} onSaved={invalidate} />
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}

function LockoutReasonRow({ reason, onSaved }: { reason: import('@/types/foiParcurs').LockoutReason; onSaved: () => void }) {
  const [label, setLabel] = useState(reason.label)
  const [order, setOrder] = useState(String(reason.sort_order))
  const dirty = label.trim() !== reason.label || Number(order) !== reason.sort_order

  const saveMut = useMutation({
    mutationFn: (patch: { label?: string; sort_order?: number; is_active?: boolean }) =>
      foiParcursApi.updateLockoutReason(reason.id, patch),
    onSuccess: onSaved,
  })

  return (
    <div className={`flex items-center gap-2 py-2${!reason.is_active ? ' opacity-60' : ''}`}>
      <Input value={label} onChange={(e) => setLabel(e.target.value)} className="flex-1 h-8 text-sm" />
      <Input
        type="number"
        value={order}
        onChange={(e) => setOrder(e.target.value)}
        className="h-8 w-16 text-sm"
        title="Ordine"
      />
      {reason.is_active
        ? <Badge variant="outline" className="text-[10px]">Activ</Badge>
        : <Badge variant="secondary" className="text-[10px]">Inactiv</Badge>}
      <Button
        size="sm"
        variant="outline"
        className="h-8"
        disabled={!dirty || !label.trim() || saveMut.isPending}
        onClick={() => saveMut.mutate({ label: label.trim(), sort_order: Number(order) || 0 })}
      >
        Salvează
      </Button>
      <Button
        size="sm"
        variant="ghost"
        className="h-8 text-xs"
        disabled={saveMut.isPending}
        onClick={() => saveMut.mutate({ is_active: !reason.is_active })}
      >
        {reason.is_active ? 'Dezactivează' : 'Activează'}
      </Button>
    </div>
  )
}

// ── Archive Reasons Settings — configurable "Motive arhivare" ──
function ArchiveReasonsSettings() {
  const queryClient = useQueryClient()
  const [newLabel, setNewLabel] = useState('')
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['fp-archive-reasons'] })
    queryClient.invalidateQueries({ queryKey: ['fp-archive-reasons', 'active'] })
  }

  const { data, isLoading } = useQuery({
    queryKey: ['fp-archive-reasons', 'all'],
    queryFn: () => foiParcursApi.getArchiveReasons(false),
    staleTime: 30_000,
  })
  const reasons = data?.reasons ?? []

  const createMut = useMutation({
    mutationFn: (label: string) => foiParcursApi.createArchiveReason({ label, sort_order: reasons.length + 1 }),
    onSuccess: () => { setNewLabel(''); invalidate() },
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Archive className="h-5 w-5 text-muted-foreground" />
        <h3 className="text-lg font-semibold">Motive arhivare</h3>
      </div>
      <p className="text-sm text-muted-foreground">
        Motivele disponibile când arhivezi o mașină din parcul auto. Redenumește, reordonează sau dezactivează-le
        (dezactivarea le ascunde la arhivări noi fără a afecta mașinile deja arhivate).
      </p>

      <Card className="p-4 space-y-3 max-w-2xl">
        {/* Add new */}
        <div className="flex items-end gap-2">
          <div className="flex-1 space-y-1">
            <Label className="text-xs">Motiv nou</Label>
            <Input
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              placeholder="Ex: Vândut, Casat…"
              onKeyDown={(e) => { if (e.key === 'Enter' && newLabel.trim()) createMut.mutate(newLabel.trim()) }}
            />
          </div>
          <Button onClick={() => createMut.mutate(newLabel.trim())} disabled={!newLabel.trim() || createMut.isPending}>
            <Plus className="h-4 w-4 mr-1" /> Adaugă
          </Button>
        </div>

        {/* List */}
        {isLoading ? (
          <p className="text-sm text-muted-foreground py-4">Se încarcă…</p>
        ) : reasons.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4">Niciun motiv configurat.</p>
        ) : (
          <div className="divide-y">
            {reasons.map((r) => (
              <ArchiveReasonRow key={r.id} reason={r} onSaved={invalidate} />
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}

function ArchiveReasonRow({ reason, onSaved }: { reason: import('@/types/foiParcurs').ArchiveReason; onSaved: () => void }) {
  const [label, setLabel] = useState(reason.label)
  const [order, setOrder] = useState(String(reason.sort_order))
  const dirty = label.trim() !== reason.label || Number(order) !== reason.sort_order

  const saveMut = useMutation({
    mutationFn: (patch: { label?: string; sort_order?: number; is_active?: boolean }) =>
      foiParcursApi.updateArchiveReason(reason.id, patch),
    onSuccess: onSaved,
  })

  return (
    <div className={`flex items-center gap-2 py-2${!reason.is_active ? ' opacity-60' : ''}`}>
      <Input value={label} onChange={(e) => setLabel(e.target.value)} className="flex-1 h-8 text-sm" />
      <Input
        type="number"
        value={order}
        onChange={(e) => setOrder(e.target.value)}
        className="h-8 w-16 text-sm"
        title="Ordine"
      />
      {reason.is_active
        ? <Badge variant="outline" className="text-[10px]">Activ</Badge>
        : <Badge variant="secondary" className="text-[10px]">Inactiv</Badge>}
      <Button
        size="sm"
        variant="outline"
        className="h-8"
        disabled={!dirty || !label.trim() || saveMut.isPending}
        onClick={() => saveMut.mutate({ label: label.trim(), sort_order: Number(order) || 0 })}
      >
        Salvează
      </Button>
      <Button
        size="sm"
        variant="ghost"
        className="h-8 text-xs"
        disabled={saveMut.isPending}
        onClick={() => saveMut.mutate({ is_active: !reason.is_active })}
      >
        {reason.is_active ? 'Dezactivează' : 'Activează'}
      </Button>
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
