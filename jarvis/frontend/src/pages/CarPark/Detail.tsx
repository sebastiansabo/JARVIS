import { useState, useMemo, useRef, useEffect, Fragment } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Pencil,
  Trash2,
  Camera,
  Clock,
  FileText,
  ChevronLeft,
  ChevronDown,
  ChevronRight,
  Car,
  Check,
  LayoutGrid,
  Maximize2,
  X,
  Plus,
  DollarSign,
  TrendingUp,
  TrendingDown,
  Globe,
  ExternalLink,
  Eye,
  MessageSquare,
  Power,
  PowerOff,
  Link2,
  Search,
  Unlink,
  Upload,
  Send,
  RefreshCw,
  ShoppingBag,
  AlertTriangle,
  Loader2,
  GripVertical,
  Sparkles,
} from 'lucide-react'
import {
  DndContext,
  PointerSensor,
  TouchSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  closestCenter,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  rectSortingStrategy,
  arrayMove,
  useSortable,
  sortableKeyboardCoordinates,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { mediaUrl } from '@/lib/media'
import { PageHeader } from '@/components/shared/PageHeader'
import { CurrencyDisplay } from '@/components/shared/CurrencyDisplay'
import { reductionPct, formatReductionPct } from './priceReduction'
import { useDragScroll } from './useDragScroll'
import { PricingSheet, PriceZone, computePricingModel, type PricingModel, type PricingSheetSnapshot, type SheetInputs } from './PricingSheet'
import { econ, type EngineParams } from './pricingEngine'
import { acquisitionProfitInputs } from './profitInputs'
import { AutofoxSyncModal } from './AutofoxSyncModal'
import { activeSellingPrice } from './vehicleFormPricing'
import { EmptyState } from '@/components/shared/EmptyState'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { useAuthStore } from '@/stores/authStore'
import { useCarParkStore } from '@/stores/carParkStore'
import { carparkApi } from '@/api/carpark'
import { carparkDispoApi } from '@/api/carparkDispo'
import { carbackgroundApi } from '@/api/carbackground'
import { autovitApi } from '@/api/autovit'
import type { AutovitAccount } from '@/api/autovit'
import { toast } from 'sonner'
import { DocumenteTab } from './Detail/DocumenteTab'
import { CronologieTab } from './Detail/CronologieTab'
import { VanzareTab, buildDispoRow } from './Detail/VanzareTab'
import { ReserveDialog } from './Dispo/ReserveDialog'
import { SellDialog } from './Dispo/SellDialog'
import { ShopifyPublishControl } from './Detail/ShopifyPublishControl'
import { ListingScheduleSelect } from './Detail/ListingScheduleSelect'
import { safeStatusTransitions } from './Dispo/statusTransitions'
import {
  STATUS_LABELS,
  CATEGORY_LABELS,
  COST_TYPE_LABELS,
  REVENUE_TYPE_LABELS,
  PROMO_TYPE_LABELS,
  LISTING_STATUS_LABELS,
  type Vehicle,
  type VehiclePhoto,
  type VehicleCostLine,
  type VehicleCost,
  type VehicleRevenue,
  type VehicleStatus,
  type VehicleListing,
  type ListingStatus,
  type CostType,
  type RevenueType,
  type Profitability,
  type PricingHistoryEntry,
  type Promotion,
  type PublishingPlatform,
  type VehicleLink,
  type LinkedEntityType,
  ENTITY_TYPE_LABELS,
} from '@/types/carpark'
import {
  VEHICLE_SOURCES, equipmentLabel, humanizeSlug,
  AUTOVIT_FUEL_TYPES, AUTOVIT_GEARBOX_TYPES, AUTOVIT_BODY_TYPES, AUTOVIT_COLORS,
  AUTOVIT_DRIVE_TYPES, AUTOVIT_EURO_STANDARDS, AUTOVIT_INTERIOR_MATERIALS,
  AUTOVIT_INTERIOR_COLORS, AUTOVIT_COLOR_FINISHES,
} from '@/data/autovitData'

// Map a stored enum slug (fuel/gearbox/body/color) to its Romanian label for
// display, so the profile reads "Diesel / Off-road (SUV) / Automata / Negru"
// instead of the raw slug. Falls back to humanizeSlug for anything unmapped.
const specLabel = (
  list: readonly { value: string; label: string }[],
  value?: string | null,
): string => (value ? (list.find((o) => o.value === value)?.label ?? humanizeSlug(value)) : '')

// ── Status colors (shared with catalog) ────────────────────
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

// ── Helpers ────────────────────────────────────────────────
function formatDate(d: string | null): string {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('ro-RO')
}

// Server timestamps (e.g. last_sync) come back as naive UTC isoformat (no zone);
// a plain `new Date` would read them as local and skew the time. Parse as UTC and
// render in Romania time.
function formatRoDateTime(d: string | null): string {
  if (!d) return '-'
  const iso = /[Zz]|[+-]\d\d:?\d\d$/.test(d) ? d : d + 'Z'
  return new Date(iso).toLocaleString('ro-RO', {
    timeZone: 'Europe/Bucharest', dateStyle: 'short', timeStyle: 'short',
  })
}

function formatKm(km: number): string {
  return new Intl.NumberFormat('ro-RO').format(km) + ' km'
}

function fmtMoney(v: number): string {
  return new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v)
}

// One parsed acquisition cost line (stored as a JSON string in
// carpark_vehicles.cost_lines — see VehicleForm's CostLine).
type CostLineJson = {
  type?: string
  description?: string
  date?: string
  lei?: number | null
  kurs?: number | null
  eur?: number | null
}

// Parse the vehicle.cost_lines TEXT column (a JSON string) → [] on any error.
function parseCostLines(raw: string | null | undefined): CostLineJson[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as CostLineJson[]) : []
  } catch {
    return []
  }
}

// ── Fișă de preț (versioned pricing sheets) ────────────────────────────────
// The vehicle.pricing_sheets TEXT column holds a JSON array of snapshots, in
// chronological order (last = most recent). Latest PUBLISHED sheet is the live
// price; a published sheet is editable only within 24h of publishing.
const SHEET_LOCK_MS = 24 * 3600 * 1000

function parseSheets(raw: string | null | undefined): PricingSheetSnapshot[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as PricingSheetSnapshot[]) : []
  } catch {
    return []
  }
}

// A published sheet locks 24h after its publish time; drafts never lock.
function sheetEditable(s: PricingSheetSnapshot): boolean {
  if (s.status !== 'published' || !s.published_at) return true
  const t = new Date(s.published_at).getTime()
  return Number.isNaN(t) || Date.now() - t < SHEET_LOCK_MS
}

// Map an acquisition-source slug to its Romanian label (VEHICLE_SOURCES),
// falling back to the raw value; null → null so <Field> shows a dash.
function sourceLabel(source: string | null): string | null {
  if (!source) return null
  return VEHICLE_SOURCES.find((s) => s.value === source)?.label ?? source
}

// ── Detail Field ───────────────────────────────────────────
function Field({ label, value, className }: { label: string; value: React.ReactNode; className?: string }) {
  // Hide fields with no data — the profile shows only what the car actually has.
  if (value == null || value === '' || value === '-') return null
  return (
    <div className={`min-w-0 ${className ?? ''}`}>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm font-medium break-words">{value}</dd>
    </div>
  )
}

// ── Inline per-card editing ─────────────────────────────────
// EditableCard wraps a detail card: it shows the read-only view (children) plus
// a pencil for editors; clicking it swaps to a field grid with Save/Cancel that
// PATCHes only this card's fields via updateVehicle (partial payload supported).
type EditFieldType = 'text' | 'number' | 'date' | 'bool' | 'textarea' | 'select'
interface EditFieldDef {
  key: keyof Vehicle
  label: string
  type: EditFieldType
  options?: { value: string; label: string }[]
  step?: string
}

function FieldEditor({
  def,
  value,
  onChange,
}: {
  def: EditFieldDef
  value: unknown
  onChange: (v: unknown) => void
}) {
  if (def.type === 'bool') {
    return (
      <label className="flex items-center gap-2 py-1 text-sm">
        <input
          type="checkbox"
          checked={!!value}
          onChange={(e) => onChange(e.target.checked)}
          className="h-4 w-4 rounded border-input accent-primary"
        />
        <span>{def.label}</span>
      </label>
    )
  }
  const strValue = value == null ? '' : String(value)
  return (
    <div className={def.type === 'textarea' ? 'sm:col-span-2 lg:col-span-4' : 'min-w-0'}>
      <Label className="text-xs text-muted-foreground">{def.label}</Label>
      {def.type === 'select' ? (
        <select
          value={strValue}
          onChange={(e) => onChange(e.target.value)}
          className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
        >
          <option value="">—</option>
          {def.options?.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      ) : def.type === 'textarea' ? (
        <Textarea
          value={strValue}
          onChange={(e) => onChange(e.target.value)}
          rows={5}
          className="mt-1"
        />
      ) : (
        <Input
          type={def.type === 'number' ? 'number' : def.type === 'date' ? 'date' : 'text'}
          step={def.type === 'number' ? (def.step ?? 'any') : undefined}
          value={strValue}
          onChange={(e) => onChange(e.target.value)}
          className="mt-1"
        />
      )}
    </div>
  )
}

function EditableCard({
  title,
  canEdit,
  vehicleId,
  vehicle,
  fields,
  children,
  className,
  editGridClassName,
}: {
  title: string
  canEdit: boolean
  vehicleId: number
  vehicle: Vehicle
  fields: EditFieldDef[]
  children: React.ReactNode
  className?: string
  editGridClassName?: string
}) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Record<string, unknown>>({})

  const mutation = useMutation({
    mutationFn: (data: Partial<Vehicle>) => carparkApi.updateVehicle(vehicleId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'vehicle', vehicleId] })
      toast.success('Modificări salvate')
      setEditing(false)
    },
    onError: () => toast.error('Salvarea a eșuat'),
  })

  const startEdit = () => {
    const d: Record<string, unknown> = {}
    for (const f of fields) {
      const cur = (vehicle as unknown as Record<string, unknown>)[f.key as string]
      d[f.key as string] = f.type === 'bool' ? !!cur : cur ?? ''
    }
    setDraft(d)
    setEditing(true)
  }

  const submit = () => {
    const payload: Record<string, unknown> = {}
    for (const f of fields) {
      const raw = draft[f.key as string]
      if (f.type === 'number') payload[f.key as string] = raw === '' || raw == null ? null : Number(raw)
      else if (f.type === 'bool') payload[f.key as string] = !!raw
      else payload[f.key as string] = raw === '' ? null : raw
    }
    mutation.mutate(payload as Partial<Vehicle>)
  }

  return (
    <Card className={`p-4 ${className ?? ''}`}>
      <div className="mb-3 flex items-start justify-between gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        {canEdit && !editing && (
          <button
            type="button"
            onClick={startEdit}
            className="-mt-0.5 rounded-md p-1 text-muted-foreground transition hover:bg-muted hover:text-foreground"
            aria-label={`Editează ${title}`}
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
        )}
        {editing && (
          <div className="flex shrink-0 items-center gap-1.5">
            <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(false)} disabled={mutation.isPending}>
              Anulează
            </Button>
            <Button type="button" size="sm" onClick={submit} disabled={mutation.isPending}>
              {mutation.isPending ? 'Se salvează…' : 'Salvează'}
            </Button>
          </div>
        )}
      </div>
      {editing ? (
        <div className={editGridClassName ?? 'grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2 lg:grid-cols-4'}>
          {fields.map((f) => (
            <FieldEditor
              key={f.key as string}
              def={f}
              value={draft[f.key as string]}
              onChange={(val) => setDraft((p) => {
                const next = { ...p, [f.key as string]: val }
                // Putere HP ↔ kW: filling one computes the other (1 kW ≈ 1.35962 HP).
                if (f.key === 'engine_power_hp') {
                  const hp = Number(val)
                  next.engine_power_kw = val === '' || Number.isNaN(hp) ? '' : Math.round(hp * 0.7355)
                } else if (f.key === 'engine_power_kw') {
                  const kw = Number(val)
                  next.engine_power_hp = val === '' || Number.isNaN(kw) ? '' : Math.round(kw * 1.35962)
                }
                return next
              })}
            />
          ))}
        </div>
      ) : (
        children
      )}
    </Card>
  )
}

// ── Main Detail Page ───────────────────────────────────────
export default function CarParkDetail() {
  const { vehicleId } = useParams<{ vehicleId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const canEdit = user?.can_edit_carpark ?? false
  const canDelete = user?.can_delete_carpark ?? false
  const canViewFinance = user?.can_view_carpark_finance ?? false

  const id = Number(vehicleId)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['carpark', 'vehicle', id],
    queryFn: () => carparkApi.getVehicle(id),
    enabled: !!id,
  })

  const { data: historyData } = useQuery({
    queryKey: ['carpark', 'status-history', id],
    queryFn: () => carparkApi.getStatusHistory(id),
    enabled: !!id,
  })

  const { data: modsData } = useQuery({
    queryKey: ['carpark', 'modifications', id],
    queryFn: () => carparkApi.getModifications(id),
    enabled: !!id,
  })

  // Finance-gated queries: /cost-lines, /revenues, /profitability and
  // /pricing-history are all @carpark_finance_required on the backend, so
  // firing them for a non-finance user only yields 403s + retry noise. Gate
  // on canViewFinance to match the server permission.
  const { data: costLinesData } = useQuery({
    queryKey: ['carpark', 'cost-lines', id],
    queryFn: () => carparkApi.getCostLines(id),
    enabled: !!id && canViewFinance,
  })

  const { data: revenuesData } = useQuery({
    queryKey: ['carpark', 'revenues', id],
    queryFn: () => carparkApi.getRevenues(id),
    enabled: !!id && canViewFinance,
  })

  const { data: profitData } = useQuery({
    queryKey: ['carpark', 'profitability', id],
    queryFn: () => carparkApi.getProfitability(id),
    enabled: !!id && canViewFinance,
  })

  const { data: pricingHistoryData } = useQuery({
    queryKey: ['carpark', 'pricing-history', id],
    queryFn: () => carparkApi.getPricingHistory(id),
    enabled: !!id && canViewFinance,
  })

  const { data: vehiclePromosData } = useQuery({
    queryKey: ['carpark', 'vehicle-promotions', id],
    queryFn: () => carparkApi.getVehiclePromotions(id),
    enabled: !!id,
  })

  const { data: listingsData } = useQuery({
    queryKey: ['carpark', 'listings', id],
    queryFn: () => carparkApi.getVehicleListings(id),
    enabled: !!id,
  })

  const { data: platformsData } = useQuery({
    queryKey: ['carpark', 'platforms'],
    queryFn: () => carparkApi.getPlatforms(true),
    enabled: !!id,
  })

  const { data: linksData } = useQuery({
    queryKey: ['carpark', 'vehicle-links', id],
    queryFn: () => carparkApi.getVehicleLinks(id),
    enabled: !!id,
  })

  const vehicle = data?.vehicle
  // Active reservation (who + client) for the persistent "Rezervat" banner.
  const { data: reservationData } = useQuery({
    queryKey: ['carpark', 'reservations', id],
    queryFn: () => carparkDispoApi.getReservations(id),
    enabled: !!id && vehicle?.status === 'RESERVED',
  })
  const activeReservation = reservationData?.reservations?.find((r) => r.status === 'active') ?? null
  const vehicleLinks = linksData?.links ?? []
  const history = historyData?.history ?? []
  const modifications = modsData?.modifications ?? []
  const costLines = costLinesData?.cost_lines ?? []
  const revenues = revenuesData?.revenues ?? []
  const pricingHistory = pricingHistoryData?.history ?? []
  const vehiclePromos = vehiclePromosData?.promotions ?? []
  const listings = listingsData?.listings ?? []
  const platforms = platformsData?.platforms ?? []

  // Status change dialog
  const [statusDialogOpen, setStatusDialogOpen] = useState(false)
  const [activeTab, setActiveTab] = useState('details')
  const [dispoDialog, setDispoDialog] = useState<'reserve' | 'sell' | null>(null)
  const [newStatus, setNewStatus] = useState<string>('')
  const [statusNotes, setStatusNotes] = useState('')

  // Delete dialog
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)

  // Photo lightbox
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)

  const statusMutation = useMutation({
    mutationFn: ({ status, notes }: { status: string; notes?: string }) =>
      carparkApi.changeStatus(id, status, notes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'vehicle', id] })
      queryClient.invalidateQueries({ queryKey: ['carpark', 'status-history', id] })
      queryClient.invalidateQueries({ queryKey: ['carpark', 'status-counts'] })
      toast.success('Status actualizat')
      setStatusDialogOpen(false)
      setNewStatus('')
      setStatusNotes('')
    },
    onError: () => toast.error('Actualizarea statusului a eșuat'),
  })

  const deleteMutation = useMutation({
    mutationFn: () => carparkApi.deleteVehicle(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark'] })
      toast.success('Vehicul șters')
      navigate('/app/carpark')
    },
    onError: () => toast.error('Ștergerea vehiculului a eșuat'),
  })

  // Available next statuses — the same safe, legal transitions the Dispo
  // inline editor and Kanban board offer (canonical STATUS_TRANSITIONS minus
  // the guarded RESERVED/SOLD/DELIVERED targets, which require the guarded
  // Reserve/Sell/Deliver dialogs on the Vânzare tab instead of a plain
  // status change).
  const nextStatuses = useMemo(() => {
    if (!vehicle) return []
    return safeStatusTransitions(vehicle.status)
  }, [vehicle])

  if (isLoading) return <DetailSkeleton />
  if (isError || !vehicle) {
    return (
      <EmptyState
        icon={<Car className="h-12 w-12" />}
        title="Vehicul negăsit"
        action={
          <Button variant="outline" asChild>
            <Link to="/app/carpark">Înapoi la catalog</Link>
          </Button>
        }
      />
    )
  }

  const photos = vehicle.photos ?? []

  return (
    <div className="space-y-6">
      {/* Header — status + key-info badges inline with the title */}
      <PageHeader
        title={`${vehicle.brand} ${vehicle.model}`}
        titleSuffix={
          <div className="flex flex-wrap items-center gap-2 font-normal">
            {canEdit && nextStatuses.length > 0 ? (
              <button
                type="button"
                onClick={() => setStatusDialogOpen(true)}
                title="Schimbă statusul"
                className="group rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <Badge
                  variant="secondary"
                  className={`text-sm cursor-pointer transition group-hover:ring-2 group-hover:ring-ring/40 ${STATUS_COLORS[vehicle.status] ?? ''}`}
                >
                  {STATUS_LABELS[vehicle.status] ?? vehicle.status}
                  <Pencil className="h-3 w-3 opacity-60" />
                </Badge>
              </button>
            ) : (
              <Badge variant="secondary" className={`text-sm ${STATUS_COLORS[vehicle.status] ?? ''}`}>
                {STATUS_LABELS[vehicle.status] ?? vehicle.status}
              </Badge>
            )}
            <Badge variant="outline">{CATEGORY_LABELS[vehicle.category] ?? vehicle.category}</Badge>
            {vehicle.is_consignment && (
              <Badge variant="outline" className="border-amber-500 text-amber-600 dark:text-amber-400">
                Custodie
              </Badge>
            )}
            {vehicle.nr_stoc && (
              <span className="text-sm text-muted-foreground">#{vehicle.nr_stoc}</span>
            )}
            <span className="text-sm text-muted-foreground">VIN: {vehicle.vin}</span>
          </div>
        }
        breadcrumbs={[
          { label: 'CarPark', href: '/app/carpark' },
          { label: `${vehicle.brand} ${vehicle.model}` },
        ]}
        actions={
          <div className="flex items-center gap-2">
            {/* Rezervă / Vinde open the Vânzare tab, where the guarded
                reserve/sell Dispo actions (reservation close, PV de livrare) live. */}
            {canEdit && !['SOLD', 'DELIVERED'].includes(vehicle.status) && (
              <>
                <Button variant="outline" size="sm" onClick={() => setDispoDialog('reserve')}>
                  Rezervă
                </Button>
                <Button variant="outline" size="sm" onClick={() => setDispoDialog('sell')}>
                  Vinde
                </Button>
              </>
            )}
            {canEdit && (
              <Button size="sm" asChild>
                <Link to={`/app/carpark/${id}/edit`}>
                  <Pencil className="mr-1 h-3.5 w-3.5" />
                  Editează
                </Link>
              </Button>
            )}
            {canDelete && (
              <Button
                variant="destructive"
                size="sm"
                onClick={() => setDeleteDialogOpen(true)}
              >
                <Trash2 className="mr-1 h-3.5 w-3.5" />
                Șterge
              </Button>
            )}
          </div>
        }
      />

      {/* Reserved banner — persistent across all tabs while the car is reserved:
          who reserved it and for which client. */}
      {vehicle.status === 'RESERVED' && activeReservation && (
        <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 rounded-md border border-purple-300 bg-purple-50 px-4 py-2 text-sm dark:border-purple-800 dark:bg-purple-950/50">
          <span className="font-semibold text-purple-800 dark:text-purple-200">Rezervat</span>
          {activeReservation.created_by_name && (
            <span>de <span className="font-medium">{activeReservation.created_by_name}</span></span>
          )}
          {activeReservation.client_name && (
            <span>pentru <span className="font-medium">{activeReservation.client_name}</span>
              {activeReservation.client_company ? ` (${activeReservation.client_company})` : ''}</span>
          )}
          {activeReservation.reservation_end && (
            <span className="text-muted-foreground">· până la {formatDate(activeReservation.reservation_end)}</span>
          )}
        </div>
      )}

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="details">Detalii</TabsTrigger>
          <TabsTrigger value="vanzare">Vânzare</TabsTrigger>
          <TabsTrigger value="pricing">Pricing</TabsTrigger>
          {canViewFinance && (
            <TabsTrigger value="costs">Costuri ({parseCostLines(vehicle.cost_lines).length})</TabsTrigger>
          )}
          {canViewFinance && (
            <TabsTrigger value="revenues">Venituri ({revenues.length})</TabsTrigger>
          )}
          <TabsTrigger value="listings">Anunțuri ({listings.length})</TabsTrigger>
          <TabsTrigger value="links">Linkuri ({vehicleLinks.length})</TabsTrigger>
          <TabsTrigger value="documente">Documente</TabsTrigger>
          <TabsTrigger value="cronologie">Cronologie</TabsTrigger>
          <TabsTrigger value="history">Istoric</TabsTrigger>
          <TabsTrigger value="modifications">Modificări</TabsTrigger>
        </TabsList>

        <TabsContent value="details" className="mt-4">
          <DetailsTab vehicle={vehicle} photos={photos} onPhotoClick={setLightboxIndex} canEdit={canEdit} canViewFinance={canViewFinance} profitData={profitData} />
        </TabsContent>

        <TabsContent value="vanzare" className="mt-4">
          <VanzareTab
            vehicle={vehicle}
            onChanged={() => queryClient.invalidateQueries({ queryKey: ['carpark', 'vehicle', id] })}
          />
        </TabsContent>

        <TabsContent value="pricing" className="mt-4">
          <PricingTab
            vehicle={vehicle}
            pricingHistory={pricingHistory}
            promotions={vehiclePromos}
            canEdit={canEdit}
          />
        </TabsContent>

        {canViewFinance && (
          <TabsContent value="costs" className="mt-4 space-y-4">
            <AcqCostLines vehicle={vehicle} canEdit={canEdit} />
            {costLines.length > 0 && (
              <CostsTab vehicleId={id} costLines={costLines} canEdit={canEdit} currency={vehicle.price_currency || 'EUR'} />
            )}
          </TabsContent>
        )}

        {canViewFinance && (
          <TabsContent value="revenues" className="mt-4">
            <RevenuesTab vehicleId={id} revenues={revenues} canEdit={canEdit} currency={vehicle.price_currency || 'RON'} />
          </TabsContent>
        )}

        <TabsContent value="listings" className="mt-4">
          <ListingsTab vehicleId={id} listings={listings} platforms={platforms} canEdit={canEdit} />
        </TabsContent>

        <TabsContent value="links" className="mt-4">
          <LinksTab vehicleId={id} links={vehicleLinks} canEdit={canEdit} />
        </TabsContent>

        <TabsContent value="documente" className="mt-4">
          <DocumenteTab vehicleId={id} status={vehicle.status} />
        </TabsContent>

        <TabsContent value="cronologie" className="mt-4">
          <CronologieTab vehicleId={id} />
        </TabsContent>

        <TabsContent value="history" className="mt-4">
          <HistoryTab history={history} />
        </TabsContent>

        <TabsContent value="modifications" className="mt-4">
          <ModificationsTab modifications={modifications} />
        </TabsContent>
      </Tabs>

      {/* Rezervă / Vinde — reuse the guarded Dispo reserve/sell modals. */}
      {dispoDialog === 'reserve' && (
        <ReserveDialog
          row={buildDispoRow(vehicle, activeReservation)}
          onClose={() => setDispoDialog(null)}
          onSuccess={() => {
            setDispoDialog(null)
            queryClient.invalidateQueries({ queryKey: ['carpark', 'vehicle', id] })
            queryClient.invalidateQueries({ queryKey: ['carpark', 'reservations', id] })
          }}
        />
      )}
      {dispoDialog === 'sell' && (
        <SellDialog
          row={buildDispoRow(vehicle, activeReservation)}
          onClose={() => setDispoDialog(null)}
          onSuccess={() => {
            setDispoDialog(null)
            queryClient.invalidateQueries({ queryKey: ['carpark', 'vehicle', id] })
          }}
        />
      )}

      {/* Status Change Dialog */}
      <Dialog open={statusDialogOpen} onOpenChange={setStatusDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Schimbă statusul vehiculului</DialogTitle>
            <DialogDescription>
              Status curent: {STATUS_LABELS[vehicle.status]}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <Select value={newStatus} onValueChange={setNewStatus}>
              <SelectTrigger>
                <SelectValue placeholder="Selectează status nou" />
              </SelectTrigger>
              <SelectContent>
                {nextStatuses.map((s) => (
                  <SelectItem key={s} value={s}>
                    {STATUS_LABELS[s] ?? s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Pentru Rezervare, Vânzare sau Livrare folosește acțiunile din tab-ul «Vânzare».
            </p>
            <Textarea
              placeholder="Note (opțional)"
              value={statusNotes}
              onChange={(e) => setStatusNotes(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setStatusDialogOpen(false)}>
              Anulează
            </Button>
            <Button
              disabled={!newStatus || statusMutation.isPending}
              onClick={() => statusMutation.mutate({ status: newStatus, notes: statusNotes || undefined })}
            >
              {statusMutation.isPending ? 'Se actualizează...' : 'Actualizează status'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Șterge vehiculul</DialogTitle>
            <DialogDescription>
              Sigur dorești să ștergi {vehicle.brand} {vehicle.model} (VIN: {vehicle.vin})?
              Această acțiune nu poate fi anulată.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              Anulează
            </Button>
            <Button
              variant="destructive"
              disabled={deleteMutation.isPending}
              onClick={() => deleteMutation.mutate()}
            >
              {deleteMutation.isPending ? 'Se șterge...' : 'Șterge'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Photo Lightbox */}
      {lightboxIndex !== null && photos.length > 0 && (
        <PhotoLightbox
          photos={photos}
          index={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
          onNavigate={setLightboxIndex}
        />
      )}
    </div>
  )
}


// ── Photo Gallery ──────────────────────────────────────────
// Hero + horizontal thumbnail filmstrip. The whole gallery block is capped at
// 600px wide (GALLERY_MAX_WIDTH); "show all" grid overlay + fullscreen lightbox on click.
const GALLERY_MAX_WIDTH = 600 // px — the whole gallery block never exceeds this width

// In the product gallery a PUBLISHED studio variant replaces its original
// (the same "effective publish URL" rule the Shopify push uses), so the in-app
// gallery matches the live listing. Unpublished variants are NOT shown here —
// they stay previewable only in the "Toate pozele" grid.
export function publishedGallerySrc(photo: VehiclePhoto, preferThumb: boolean): string {
  if (photo.enhanced_published && photo.enhanced_url) {
    return mediaUrl((preferThumb ? photo.enhanced_thumbnail_url : null) || photo.enhanced_url)
  }
  return mediaUrl((preferThumb ? photo.thumbnail_url : null) || photo.url)
}

function PhotoGallery({
  photos,
  onPhotoClick,
  vehicleId,
  canEdit,
}: {
  photos: VehiclePhoto[]
  onPhotoClick: (index: number) => void
  vehicleId: number
  canEdit: boolean
}) {
  const [active, setActive] = useState(0)
  const [gridOpen, setGridOpen] = useState(false)
  const strip = useDragScroll()
  const idx = photos.length ? Math.min(active, photos.length - 1) : 0

  useEffect(() => {
    const el = strip.ref.current?.querySelector<HTMLElement>(`[data-i="${idx}"]`)
    el?.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' })
  }, [idx])

  if (photos.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-dashed bg-muted/30">
        <div className="text-center">
          <Camera className="mx-auto h-8 w-8 text-muted-foreground" />
          <p className="mt-2 text-sm text-muted-foreground">Fără poze</p>
        </div>
      </div>
    )
  }

  const go = (i: number) => setActive((i + photos.length) % photos.length)

  return (
    <div className="w-full space-y-2" style={{ maxWidth: GALLERY_MAX_WIDTH }}>
      {/* Hero — the main viewing zone */}
      <div
        className="group relative aspect-[3/2] w-full cursor-zoom-in overflow-hidden rounded-xl bg-muted"
        onClick={() => onPhotoClick(idx)}
      >
        <img
          src={publishedGallerySrc(photos[idx], false)}
          alt={`Photo ${idx + 1}`}
          className="h-full w-full object-cover"
        />
        <div className="absolute left-3 top-3 rounded-full bg-black/60 px-2.5 py-1 text-xs font-medium tabular-nums text-white backdrop-blur">
          {idx + 1} / {photos.length}
        </div>
        <div className="absolute right-3 top-3 flex gap-2">
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setGridOpen(true) }}
            className="flex items-center gap-1.5 rounded-full bg-black/60 px-3 py-1.5 text-xs font-medium text-white backdrop-blur transition hover:bg-black/80"
          >
            <LayoutGrid className="h-3.5 w-3.5" /> Toate pozele
          </button>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onPhotoClick(idx) }}
            className="flex items-center gap-1.5 rounded-full bg-black/60 px-3 py-1.5 text-xs font-medium text-white backdrop-blur transition hover:bg-black/80"
          >
            <Maximize2 className="h-3.5 w-3.5" /> Ecran complet
          </button>
        </div>
        {photos.length > 1 && (
          <>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); go(idx - 1) }}
              className="absolute left-3 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-black/50 text-white opacity-0 backdrop-blur transition hover:bg-black/80 group-hover:opacity-100"
              aria-label="Poza anterioară"
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); go(idx + 1) }}
              className="absolute right-3 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-black/50 text-white opacity-0 backdrop-blur transition hover:bg-black/80 group-hover:opacity-100"
              aria-label="Poza următoare"
            >
              <ChevronRight className="h-5 w-5" />
            </button>
          </>
        )}
      </div>

      {/* Filmstrip */}
      {photos.length > 1 && (
        <div
          ref={strip.ref}
          {...strip.dragProps}
          className="flex cursor-grab select-none gap-2 overflow-x-auto overscroll-x-contain pb-1 active:cursor-grabbing"
          style={{ scrollbarWidth: 'thin' }}
        >
          {photos.map((p, i) => (
            <button
              type="button"
              key={p.id}
              data-i={i}
              onClick={() => { if (strip.didDrag()) return; go(i) }}
              className={`h-16 w-[96px] flex-none overflow-hidden rounded-md border-2 transition ${
                i === idx ? 'border-primary opacity-100' : 'border-transparent opacity-60 hover:opacity-100'
              }`}
            >
              <img
                src={publishedGallerySrc(p, true)}
                alt={`Thumbnail ${i + 1}`}
                draggable={false}
                className="h-full w-full object-cover"
              />
            </button>
          ))}
        </div>
      )}

      {gridOpen && (
        <PhotoGridOverlay
          photos={photos}
          vehicleId={vehicleId}
          canEdit={canEdit}
          onClose={() => setGridOpen(false)}
        />
      )}
    </div>
  )
}

// Which src to show for a tile: the studio variant by default once one
// exists, falling back to the original — `showOriginal` lets the user peek
// at the before/after.
function tileImageSrc(photo: VehiclePhoto, showOriginal: boolean): string {
  if (!showOriginal && photo.enhanced_url) {
    return mediaUrl(photo.enhanced_thumbnail_url || photo.enhanced_url)
  }
  return mediaUrl(photo.thumbnail_url || photo.url)
}

// ── Enhanced-photo controls (footer under a tile) ───────────
// Renders nothing unless the photo has a carbackground.ai studio variant.
// Mirrors the AutoFox-style compact action row: an original↔studio preview
// switch plus a publish toggle (editors only).
function EnhancedControls({
  photo,
  canEdit,
  showOriginal,
  onTogglePreview,
  onTogglePublish,
  publishPending,
}: {
  photo: VehiclePhoto
  canEdit: boolean
  showOriginal: boolean
  onTogglePreview: () => void
  onTogglePublish: (v: boolean) => void
  publishPending: boolean
}) {
  if (!photo.enhanced_url) return null
  return (
    <div className="flex items-center justify-between gap-1 border-t bg-muted/60 px-1.5 py-1">
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); onTogglePreview() }}
        className="flex items-center gap-1 rounded px-1 py-0.5 text-[11px] font-medium text-muted-foreground transition hover:bg-muted hover:text-foreground"
      >
        <Eye className="h-3 w-3" /> {showOriginal ? 'Original' : 'Studio'}
      </button>
      {canEdit && (
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground" onClick={(e) => e.stopPropagation()}>
          <span className="hidden sm:inline">Publică</span>
          <Switch
            size="sm"
            checked={!!photo.enhanced_published}
            disabled={publishPending}
            onCheckedChange={onTogglePublish}
            aria-label="Publică varianta studio"
          />
        </div>
      )}
    </div>
  )
}

// ── Sortable Photo Tile ─────────────────────────────────────
// One draggable tile in the "Toate pozele" grid. Tap the image to open the
// lightbox; drag the grip handle (top-right) to reorder. A separate handle
// keeps tap-to-open clean and lets the grid scroll on touch devices.
function SortablePhotoTile({
  photo,
  index,
  onSelect,
  canEdit,
  showOriginal,
  onTogglePreview,
  onTogglePublish,
  publishPending,
}: {
  photo: VehiclePhoto
  index: number
  onSelect: (index: number) => void
  canEdit: boolean
  showOriginal: boolean
  onTogglePreview: () => void
  onTogglePublish: (v: boolean) => void
  publishPending: boolean
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: photo.id,
  })
  const style = { transform: CSS.Transform.toString(transform), transition }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`group relative overflow-hidden rounded-lg border bg-muted ${
        isDragging ? 'z-10 opacity-80 shadow-xl ring-2 ring-primary' : ''
      }`}
    >
      <div className="relative aspect-[3/2]">
        <button
          type="button"
          onClick={() => onSelect(index)}
          className="block h-full w-full"
          aria-label={`Deschide poza ${index + 1}`}
        >
          <img
            src={tileImageSrc(photo, showOriginal)}
            alt={`Photo ${index + 1}`}
            draggable={false}
            className="h-full w-full object-cover transition group-hover:scale-105"
          />
        </button>
        {/* Position badge — makes the first → last order visible (1 = cover) */}
        <div className="pointer-events-none absolute left-1.5 top-1.5 rounded-full bg-black/60 px-1.5 py-0.5 text-[11px] font-semibold tabular-nums text-white backdrop-blur">
          {index + 1}
        </div>
        {/* Drag handle */}
        <button
          type="button"
          {...attributes}
          {...listeners}
          aria-label="Trage pentru a reordona"
          className="absolute right-1.5 top-1.5 flex touch-none cursor-grab items-center justify-center rounded-md bg-black/60 p-1.5 text-white opacity-0 backdrop-blur transition hover:bg-black/80 focus:opacity-100 group-hover:opacity-100 active:cursor-grabbing"
        >
          <GripVertical className="h-4 w-4" />
        </button>
        {photo.enhanced_url && (
          <span className="pointer-events-none absolute bottom-1.5 left-1.5 flex items-center gap-1 rounded-full bg-violet-600/90 px-1.5 py-0.5 text-[10px] font-semibold text-white backdrop-blur">
            <Sparkles className="h-3 w-3" /> Enhanced
          </span>
        )}
      </div>
      <EnhancedControls
        photo={photo}
        canEdit={canEdit}
        showOriginal={showOriginal}
        onTogglePreview={onTogglePreview}
        onTogglePublish={onTogglePublish}
        publishPending={publishPending}
      />
    </div>
  )
}

// ── Photo Grid Overlay ("Toate pozele") ────────────────────
// Fullscreen photo grid. For editors it becomes drag-and-drop sortable: drop
// auto-saves the new order via the existing reorder endpoint (optimistic).
// Exported so Detail's photo-studio-enhance flow (select → "Generează
// studio" → publish toggle → preview) can be exercised in isolation by tests.
export function PhotoGridOverlay({
  photos,
  vehicleId,
  canEdit,
  onClose,
}: {
  photos: VehiclePhoto[]
  vehicleId: number
  canEdit: boolean
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [confirming, setConfirming] = useState(false)
  // Which enhanced photos are currently showing their ORIGINAL (pre-studio)
  // image instead of the default studio variant.
  const [showOriginal, setShowOriginal] = useState<Set<number>>(new Set())
  // Clicking a photo opens a simple single-photo preview (not the full lightbox).
  const [preview, setPreview] = useState<number | null>(null)
  const previewRef = useRef<number | null>(null)
  useEffect(() => { previewRef.current = preview }, [preview])
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 180, tolerance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  // Preferred studio backgrounds for the "Generează studio" picker (editors
  // only). The picker lists the curated preferred set; the starred default is
  // pre-selected. null = untouched → fall back to that default.
  const { data: cbgConfig } = useQuery({
    queryKey: ['carbackground', 'config'],
    queryFn: carbackgroundApi.getConfig,
    enabled: canEdit,
  })
  const { data: cbgBackgrounds } = useQuery({
    queryKey: ['carbackground', 'backgrounds'],
    queryFn: carbackgroundApi.listBackgrounds,
    enabled: canEdit,
  })
  const preferredIds = cbgConfig?.connector?.preferred_background_ids ?? []
  const bgNames = new Map((cbgBackgrounds?.backgrounds ?? []).map((b) => [b.id, b.name]))
  const preferredOptions = preferredIds.map((id) => ({ id, name: bgNames.get(id) ?? id }))
  const defaultBgId = cbgConfig?.connector?.background_id || preferredIds[0] || ''
  const [bgChoice, setBgChoice] = useState<string | null>(null)
  const chosenBg = bgChoice ?? defaultBgId

  // Background studio-enhance job status for THIS vehicle. Resolves once on
  // mount (so the progress indicator resumes after a reload / navigating back)
  // and polls every 3s while a job is running, then stops.
  const { data: enhanceJob } = useQuery({
    queryKey: ['carbackground', 'enhance-status', vehicleId],
    queryFn: () => carbackgroundApi.enhanceStatus(vehicleId),
    enabled: canEdit,
    refetchInterval: (q) => (q.state.data?.running ? 3000 : false),
  })
  const jobRunning = enhanceJob?.running ?? false

  // While a job runs, pull the vehicle query forward on each progress tick so
  // finished photos — and their publish toggle — appear without a manual
  // refresh. On the running→idle edge, emit the completion toast.
  const prevJobRunning = useRef(false)
  useEffect(() => {
    if (!enhanceJob) return
    if (enhanceJob.running || prevJobRunning.current) {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'vehicle', vehicleId] })
    }
    if (prevJobRunning.current && !enhanceJob.running) {
      const errs = enhanceJob.errors?.length ?? 0
      if (enhanceJob.created === 0 && errs) toast.error(`Generare studio eșuată (${errs} erori)`)
      else toast.success(`${enhanceJob.created} poze studio generate${errs ? ` (${errs} erori)` : ''}`)
    }
    prevJobRunning.current = enhanceJob.running
  }, [enhanceJob?.running, enhanceJob?.done, enhanceJob, queryClient, vehicleId])

  const reorderMutation = useMutation({
    mutationFn: (orderedIds: number[]) => carparkApi.reorderPhotos(vehicleId, orderedIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'vehicle', vehicleId] })
    },
    onError: () => {
      // Roll back to server truth and tell the user it didn't stick.
      queryClient.invalidateQueries({ queryKey: ['carpark', 'vehicle', vehicleId] })
      toast.error('Reordonarea pozelor a eșuat')
    },
  })

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIndex = photos.findIndex((p) => p.id === active.id)
    const newIndex = photos.findIndex((p) => p.id === over.id)
    if (oldIndex < 0 || newIndex < 0) return
    const newPhotos = arrayMove(photos, oldIndex, newIndex)
    // Optimistic: reorder the cached vehicle so the grid updates instantly.
    queryClient.setQueryData<{ vehicle: Vehicle }>(['carpark', 'vehicle', vehicleId], (old) =>
      old?.vehicle ? { ...old, vehicle: { ...old.vehicle, photos: newPhotos } } : old,
    )
    reorderMutation.mutate(newPhotos.map((p) => p.id))
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // While the single-photo preview is open, keys drive it (not the grid).
      if (previewRef.current !== null) {
        if (e.key === 'Escape') setPreview(null)
        else if (e.key === 'ArrowRight') setPreview((i) => (i === null ? null : (i + 1) % photos.length))
        else if (e.key === 'ArrowLeft') setPreview((i) => (i === null ? null : (i - 1 + photos.length) % photos.length))
        return
      }
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose, photos.length])

  const deleteMut = useMutation({
    mutationFn: () => carparkApi.bulkDeletePhotos(vehicleId, Array.from(selected)),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'vehicle', vehicleId] })
      toast.success(`${res.deleted} poze șterse (recuperabile 24h)`)
      setSelected(new Set())
      setSelectMode(false)
      setConfirming(false)
    },
    onError: () => toast.error('Ștergerea pozelor a eșuat'),
  })

  // "Generează studio" — queues the selected photos for BACKGROUND enhancement
  // and returns at once (202). A daemon worker processes them server-side; the
  // enhance-status poll above drives the live progress count and refreshes the
  // gallery as each photo lands, so the user never waits here and the publish
  // toggle appears without a manual reload. The job survives leaving the page.
  const enhanceMut = useMutation({
    mutationFn: () => carbackgroundApi.enhance(vehicleId, Array.from(selected), chosenBg || undefined),
    onSuccess: (res) => {
      toast.success(`Generare pornită în fundal (${res.queued} poze)`)
      setSelected(new Set())
      setSelectMode(false)
      // Kick the status poll immediately so progress shows without the 3s wait.
      queryClient.invalidateQueries({ queryKey: ['carbackground', 'enhance-status', vehicleId] })
    },
    onError: () => toast.error('Pornirea generării a eșuat'),
  })

  // Publish/unpublish the studio variant for a single photo.
  const pubMut = useMutation({
    mutationFn: ({ id, published }: { id: number; published: boolean }) =>
      carbackgroundApi.setPublished(id, published),
    onError: () => toast.error('Actualizarea publicării a eșuat'),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['carpark', 'vehicle', vehicleId] }),
  })

  const togglePreview = (photoId: number) => setShowOriginal((prev) => {
    const n = new Set(prev)
    if (n.has(photoId)) n.delete(photoId)
    else n.add(photoId)
    return n
  })

  const allSelected = photos.length > 0 && selected.size === photos.length
  const toggle = (photoId: number) => setSelected((prev) => {
    const n = new Set(prev)
    if (n.has(photoId)) n.delete(photoId)
    else n.add(photoId)
    return n
  })
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(photos.map((p) => p.id)))
  const exitSelect = () => { setSelectMode(false); setSelected(new Set()); setConfirming(false) }

  // Drag-to-reorder is available to editors only when not selecting for deletion.
  const sortable = canEdit && !selectMode && photos.length > 1

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-background">
      <div className="sticky top-0 z-10 flex items-center justify-between gap-2 border-b bg-background/85 px-6 py-4 backdrop-blur">
        <div className="flex min-w-0 items-baseline gap-3">
          <h2 className="text-base font-semibold">
            Toate pozele · {photos.length}
            {selectMode && (
              <span className="ml-2 text-sm font-normal text-muted-foreground">{selected.size} selectate</span>
            )}
          </h2>
          {sortable && (
            <span className="hidden truncate text-xs text-muted-foreground sm:inline">
              Trage de <GripVertical className="mx-0.5 inline h-3 w-3 align-text-bottom" /> pentru a reordona · prima poză = coperta
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {jobRunning && (
            <span className="flex items-center gap-1.5 rounded-full bg-violet-600/10 px-2.5 py-1 text-xs font-medium text-violet-700 dark:text-violet-300">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {`Generare studio: ${enhanceJob?.done ?? 0}/${enhanceJob?.total ?? 0}`}
            </span>
          )}
          {canEdit && selectMode && (
            <>
              <Button size="sm" variant="ghost" onClick={toggleAll} disabled={deleteMut.isPending || photos.length === 0}>
                {allSelected ? 'Deselectează tot' : 'Selectează tot'}
              </Button>
              {selected.size > 0 && (
                <>
                  {preferredOptions.length > 0 && (
                    <select
                      aria-label="Fundal studio"
                      value={chosenBg}
                      onChange={(e) => setBgChoice(e.target.value)}
                      disabled={enhanceMut.isPending}
                      className="h-8 rounded-md border bg-background px-2 text-sm"
                    >
                      {preferredOptions.map((o) => (
                        <option key={o.id} value={o.id}>{o.name}</option>
                      ))}
                    </select>
                  )}
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => enhanceMut.mutate()}
                    disabled={enhanceMut.isPending || jobRunning}
                    title={jobRunning ? 'O generare este deja în curs' : undefined}
                  >
                    {enhanceMut.isPending || jobRunning ? (
                      <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Sparkles className="mr-1 h-3.5 w-3.5" />
                    )}
                    Generează studio ({selected.size})
                  </Button>
                </>
              )}
              {confirming ? (
                <Button size="sm" variant="destructive" onClick={() => deleteMut.mutate()}
                        disabled={deleteMut.isPending || selected.size === 0}>
                  <Trash2 className="mr-1 h-3.5 w-3.5" /> Confirmă ștergerea ({selected.size})
                </Button>
              ) : (
                <Button size="sm" variant="destructive" onClick={() => setConfirming(true)} disabled={selected.size === 0}>
                  <Trash2 className="mr-1 h-3.5 w-3.5" /> Șterge ({selected.size})
                </Button>
              )}
              <Button size="sm" variant="outline" onClick={exitSelect} disabled={deleteMut.isPending}>Anulează</Button>
            </>
          )}
          {canEdit && !selectMode && (
            <Button size="sm" variant="outline" onClick={() => setSelectMode(true)}>Selectează</Button>
          )}
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground transition hover:bg-muted hover:text-foreground"
            aria-label="Închide"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      </div>
      {confirming && (
        <div className="border-b bg-destructive/10 px-6 py-2 text-sm text-destructive">
          {selected.size} poze vor fi ascunse acum și șterse definitiv după 24h.
        </div>
      )}
      {sortable ? (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={photos.map((p) => p.id)} strategy={rectSortingStrategy}>
            <div className="mx-auto grid max-w-5xl grid-cols-2 gap-2 p-6 sm:grid-cols-3">
              {photos.map((p, i) => (
                <SortablePhotoTile
                  key={p.id}
                  photo={p}
                  index={i}
                  onSelect={setPreview}
                  canEdit={canEdit}
                  showOriginal={showOriginal.has(p.id)}
                  onTogglePreview={() => togglePreview(p.id)}
                  onTogglePublish={(v) => pubMut.mutate({ id: p.id, published: v })}
                  publishPending={pubMut.isPending && pubMut.variables?.id === p.id}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      ) : (
        <div className="mx-auto grid max-w-5xl grid-cols-2 gap-2 p-6 sm:grid-cols-3">
          {photos.map((p, i) => {
            const sel = selected.has(p.id)
            const showOrig = showOriginal.has(p.id)
            return (
              <div
                key={p.id}
                className={`group relative overflow-hidden rounded-lg border-2 bg-muted ${sel ? 'border-primary' : 'border-transparent'}`}
              >
                <button
                  type="button"
                  onClick={() => (selectMode ? toggle(p.id) : setPreview(i))}
                  className="relative block aspect-[3/2] w-full"
                  aria-label={selectMode ? `Selectează poza ${p.id}` : `Deschide poza ${i + 1}`}
                >
                  <img
                    src={tileImageSrc(p, showOrig)}
                    alt={`Photo ${i + 1}`}
                    className="h-full w-full object-cover transition group-hover:scale-105"
                  />
                  {selectMode && (
                    <span className={`absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-full border-2 ${sel ? 'border-primary bg-primary text-primary-foreground' : 'border-white/80 bg-black/30'}`}>
                      {sel && <Check className="h-4 w-4" />}
                    </span>
                  )}
                  {!selectMode && p.enhanced_url && (
                    <span className="pointer-events-none absolute bottom-1.5 left-1.5 flex items-center gap-1 rounded-full bg-violet-600/90 px-1.5 py-0.5 text-[10px] font-semibold text-white backdrop-blur">
                      <Sparkles className="h-3 w-3" /> Enhanced
                    </span>
                  )}
                </button>
                {!selectMode && (
                  <EnhancedControls
                    photo={p}
                    canEdit={canEdit}
                    showOriginal={showOrig}
                    onTogglePreview={() => togglePreview(p.id)}
                    onTogglePublish={(v) => pubMut.mutate({ id: p.id, published: v })}
                    publishPending={pubMut.isPending && pubMut.variables?.id === p.id}
                  />
                )}
              </div>
            )
          })}
        </div>
      )}
      {/* Single-photo preview — simple viewer with prev/next, NOT the full lightbox. */}
      {preview !== null && photos[preview] && (
        <div className="fixed inset-0 z-[60] flex flex-col bg-black/95" onClick={() => setPreview(null)}>
          <div className="flex items-center justify-between px-5 py-3" onClick={(e) => e.stopPropagation()}>
            <span className="text-sm tabular-nums text-white/70">{preview + 1} / {photos.length}</span>
            <button
              type="button"
              onClick={() => setPreview(null)}
              className="rounded-md bg-white/10 p-2 text-white transition hover:bg-white/20"
              aria-label="Închide"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
          <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden p-4" onClick={(e) => e.stopPropagation()}>
            {photos.length > 1 && (
              <button
                type="button"
                onClick={() => setPreview((i) => (i === null ? null : (i - 1 + photos.length) % photos.length))}
                className="absolute left-4 z-10 flex h-11 w-11 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/25"
                aria-label="Poza anterioară"
              >
                <ChevronLeft className="h-6 w-6" />
              </button>
            )}
            <img
              src={mediaUrl(photos[preview].url)}
              alt={`Photo ${preview + 1}`}
              className="max-h-full max-w-full object-contain"
            />
            {photos.length > 1 && (
              <button
                type="button"
                onClick={() => setPreview((i) => (i === null ? null : (i + 1) % photos.length))}
                className="absolute right-4 z-10 flex h-11 w-11 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/25"
                aria-label="Poza următoare"
              >
                <ChevronRight className="h-6 w-6" />
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Photo Lightbox ─────────────────────────────────────────
// Fullscreen viewer: keyboard (← → Esc), swipe, click-to-zoom, thumbnail strip.
function PhotoLightbox({
  photos,
  index,
  onClose,
  onNavigate,
}: {
  photos: VehiclePhoto[]
  index: number
  onClose: () => void
  onNavigate: (index: number) => void
}) {
  const [zoomed, setZoomed] = useState(false)
  const [origin, setOrigin] = useState('50% 50%')
  const touchX = useRef<number | null>(null)
  const lbStrip = useDragScroll()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') onNavigate((index + 1) % photos.length)
      else if (e.key === 'ArrowLeft') onNavigate((index - 1 + photos.length) % photos.length)
      else if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [index, photos.length, onNavigate, onClose])

  useEffect(() => { setZoomed(false) }, [index])

  useEffect(() => {
    const el = lbStrip.ref.current?.querySelector<HTMLElement>(`[data-i="${index}"]`)
    el?.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' })
  }, [index])

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black/95" onClick={onClose}>
      {/* Top bar */}
      <div className="flex items-center justify-between px-5 py-3" onClick={(e) => e.stopPropagation()}>
        <span className="text-sm tabular-nums text-white/70">
          {index + 1} / {photos.length}
        </span>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md bg-white/10 p-2 text-white transition hover:bg-white/20"
          aria-label="Închide"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* Stage */}
      <div
        className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        onTouchStart={(e) => { touchX.current = e.touches[0].clientX }}
        onTouchEnd={(e) => {
          if (touchX.current === null) return
          const dx = e.changedTouches[0].clientX - touchX.current
          if (!zoomed && Math.abs(dx) > 40) {
            if (dx < 0) onNavigate((index + 1) % photos.length)
            else onNavigate((index - 1 + photos.length) % photos.length)
          }
          touchX.current = null
        }}
      >
        {photos.length > 1 && (
          <button
            type="button"
            onClick={() => onNavigate((index - 1 + photos.length) % photos.length)}
            className="absolute left-4 z-10 flex h-11 w-11 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/25"
            aria-label="Poza anterioară"
          >
            <ChevronLeft className="h-6 w-6" />
          </button>
        )}
        <img
          src={publishedGallerySrc(photos[index], false)}
          alt={`Photo ${index + 1}`}
          onClick={(e) => {
            e.stopPropagation()
            if (zoomed) { setZoomed(false); return }
            const r = e.currentTarget.getBoundingClientRect()
            setOrigin(`${((e.clientX - r.left) / r.width) * 100}% ${((e.clientY - r.top) / r.height) * 100}%`)
            setZoomed(true)
          }}
          className={
            zoomed
              ? 'max-h-none max-w-none cursor-zoom-out'
              : 'max-h-full max-w-[94vw] cursor-zoom-in object-contain'
          }
          style={zoomed ? { transform: 'scale(2.2)', transformOrigin: origin } : undefined}
        />
        {photos.length > 1 && (
          <button
            type="button"
            onClick={() => onNavigate((index + 1) % photos.length)}
            className="absolute right-4 z-10 flex h-11 w-11 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/25"
            aria-label="Poza următoare"
          >
            <ChevronRight className="h-6 w-6" />
          </button>
        )}
      </div>

      {/* Thumbnail strip */}
      {photos.length > 1 && (
        <div
          ref={lbStrip.ref}
          {...lbStrip.dragProps}
          className="flex cursor-grab select-none gap-1.5 overflow-x-auto overscroll-x-contain px-4 py-3 active:cursor-grabbing"
          onClick={(e) => e.stopPropagation()}
          style={{ scrollbarWidth: 'thin' }}
        >
          {photos.map((p, i) => (
            <button
              type="button"
              key={p.id}
              data-i={i}
              onClick={() => { if (lbStrip.didDrag()) return; onNavigate(i) }}
              className={`h-14 w-[84px] flex-none overflow-hidden rounded border-2 transition ${
                i === index ? 'border-white opacity-100' : 'border-transparent opacity-50 hover:opacity-100'
              }`}
            >
              <img src={publishedGallerySrc(p, true)} alt="" draggable={false} className="h-full w-full object-cover" />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Details Tab ────────────────────────────────────────────
function DetailsTab({ vehicle: v, photos, onPhotoClick, canEdit, canViewFinance, profitData }: { vehicle: Vehicle; photos: VehiclePhoto[]; onPhotoClick: (index: number) => void; canEdit: boolean; canViewFinance: boolean; profitData?: Profitability | null }) {
  // New pricing model: "Preț" = list_price; "Preț promoțional" = promotional_price.
  // The displayed price is the promo when set, else the list price.
  const pricePct = reductionPct(v.list_price, v.promotional_price)
  const displayPrice = v.promotional_price ?? v.list_price
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [autofoxOpen, setAutofoxOpen] = useState(false)

  // Parsed acquisition cost lines (vehicle.cost_lines JSON) + total EUR.
  const acqCostLines = parseCostLines(v.cost_lines)
  const acqCostTotal = acqCostLines.reduce((s, l) => s + (Number(l.eur) || 0), 0)

  const uploadMutation = useMutation({
    mutationFn: (files: File[]) => carparkApi.uploadPhotos(v.id, files),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'vehicle', v.id] })
      toast.success('Poze încărcate')
    },
    onError: () => toast.error('Încărcarea pozelor a eșuat'),
  })

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    e.target.value = ''
    if (files.length > 0) uploadMutation.mutate(files)
  }

  return (
    <div className="space-y-6">
      {/* Photo Gallery + Identification + Quick Info */}
      <div className="grid gap-6 items-stretch xl:grid-cols-[600px_minmax(0,1fr)_400px]">
        <div className="space-y-2">
          <PhotoGallery photos={photos} onPhotoClick={onPhotoClick} vehicleId={v.id} canEdit={canEdit} />
          {canEdit && (
            <div className="flex justify-end gap-2">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                multiple
                className="hidden"
                onChange={handleFileChange}
              />
              {v.vin && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setAutofoxOpen(true)}
                >
                  <Camera className="mr-1 h-3.5 w-3.5" />
                  Sincronizează din AutoFox
                </Button>
              )}
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={uploadMutation.isPending}
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload className="mr-1 h-3.5 w-3.5" />
                {uploadMutation.isPending ? 'Se încarcă...' : 'Încarcă poze'}
              </Button>
            </div>
          )}
          {canEdit && v.vin && (
            <AutofoxSyncModal
              open={autofoxOpen}
              onOpenChange={setAutofoxOpen}
              vin={v.vin}
              vehicleId={v.id}
            />
          )}
        </div>

        {/* Identification */}
        <Card className="p-4 h-full">
          <h3 className="text-sm font-semibold mb-3">Identificare</h3>
          <dl className="grid grid-cols-2 gap-3">
            <Field label="Marcă" value={v.brand} />
            <Field label="Model" value={v.model} />
            <Field label="Versiune" value={humanizeSlug(v.variant, { stripVersionPrefix: true })} />
            <Field label="Stare" value={v.state} />
            <Field label="Generație" value={humanizeSlug(v.generation, { stripVersionPrefix: true })} />
            <Field label="Nivel echipare" value={humanizeSlug(v.equipment_level)} />
            <Field label="Tip stoc" value={CATEGORY_LABELS[v.category] ?? v.category} />
            <Field label="VIN" value={v.vin} />
            <Field label="Nr. stoc" value={v.nr_stoc} />
            <Field label="Prima înmatriculare" value={formatDate(v.first_registration_date)} />
            <Field label="Data fabricației" value={formatDate(v.manufacture_date)} />
            <Field label="Înmatriculare" value={v.registration_number} />
            <Field label="Cod șasiu" value={v.chassis_code} />
            <Field label="Cod emisii" value={v.emission_code} />
            {v.internal_notes && (
              <div className="col-span-2">
                <Field label="Note interne" value={v.internal_notes} />
              </div>
            )}
          </dl>
        </Card>

        <Card className="p-4 space-y-4 h-full">
          {displayPrice != null && (
            <div>
              <div className="text-xs text-muted-foreground">Preț</div>
              <CurrencyDisplay
                value={displayPrice}
                currency={v.price_currency}
                className="text-2xl font-bold"
              />
              {v.promotional_price != null && v.list_price != null && v.list_price !== v.promotional_price && (
                <div className="flex items-baseline gap-1.5">
                  <span className="text-sm text-muted-foreground line-through">
                    {new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2 }).format(v.list_price)} {v.price_currency}
                  </span>
                  {pricePct != null && (
                    <span className="text-xs font-medium text-red-600 dark:text-red-400">
                      {formatReductionPct(pricePct)}
                    </span>
                  )}
                </div>
              )}
            </div>
          )}
          <Separator />
          <dl className="grid grid-cols-2 gap-3">
            <Field label="An" value={v.year_of_manufacture} />
            <Field label="Rulaj" value={v.mileage_km > 0 ? formatKm(v.mileage_km) : '-'} />
            <Field label="Combustibil" value={specLabel(AUTOVIT_FUEL_TYPES, v.fuel_type)} />
            <Field label="Cutie de viteze" value={specLabel(AUTOVIT_GEARBOX_TYPES, v.transmission)} />
            <Field label="Caroserie" value={specLabel(AUTOVIT_BODY_TYPES, v.body_type)} />
            <Field label="Putere" value={v.engine_power_hp ? `${v.engine_power_hp} HP` : null} />
            <Field label="Culoare" value={specLabel(AUTOVIT_COLORS, v.color_exterior)} />
            <Field label="Portiere" value={v.doors} />
          </dl>
          <Separator />
          <dl className="grid grid-cols-2 gap-3">
            <Field label="Achiziție" value={formatDate(v.acquisition_date)} />
            <Field label="Zile în stoc" value={
              <span className={v.stationary_days > 90 ? 'text-red-600 font-medium' : ''}>
                {v.stationary_days}
              </span>
            } />
            <Field label="Locație" value={v.location_text ?? v.location_name} />
            <Field label="Parcare" value={v.parking_spot} />
          </dl>
        </Card>
      </div>

      {/* Price/cost summary tiles — under the Picture / Identificare / Preț cards. */}
      {profitData && <ProfitabilitySummary data={profitData} vehicle={v} />}

      {/* Technical + Cargo — single full-width card */}
      <EditableCard
        title="Specificații tehnice"
        canEdit={canEdit}
        vehicleId={v.id}
        vehicle={v}
        fields={[
          { key: 'engine_displacement_cc', label: 'Motor (cc)', type: 'number' },
          { key: 'engine_power_hp', label: 'Putere (HP)', type: 'number' },
          { key: 'engine_power_kw', label: 'Putere (kW)', type: 'number' },
          { key: 'engine_torque_nm', label: 'Cuplu (Nm)', type: 'number' },
          { key: 'drive_type', label: 'Tracțiune', type: 'select', options: [...AUTOVIT_DRIVE_TYPES] },
          { key: 'co2_emissions', label: 'CO2 (g/km)', type: 'number' },
          { key: 'euro_standard', label: 'Normă poluare', type: 'select', options: [...AUTOVIT_EURO_STANDARDS] },
          { key: 'fuel_consumption', label: 'Consum', type: 'text' },
          { key: 'seats', label: 'Locuri', type: 'number' },
          { key: 'fuel_tank_capacity_liters', label: 'Capacitate rezervor (L)', type: 'number' },
          { key: 'battery_capacity_kwh', label: 'Capacitate baterie (kWh)', type: 'number' },
          { key: 'electric_range_km', label: 'Autonomie electrică (km)', type: 'number' },
          { key: 'consum_urban', label: 'Consum urban', type: 'number' },
          { key: 'consum_extraurban', label: 'Consum extraurban', type: 'number' },
          { key: 'consum_mixt', label: 'Consum mixt', type: 'number' },
          { key: 'norma_combustibil', label: 'Normă consum', type: 'text' },
          { key: 'norma_energie', label: 'Normă energie', type: 'text' },
          { key: 'interior_material', label: 'Tapițerie', type: 'select', options: [...AUTOVIT_INTERIOR_MATERIALS] },
          { key: 'color_interior', label: 'Culoare interior', type: 'select', options: [...AUTOVIT_INTERIOR_COLORS] },
          { key: 'color_finish', label: 'Tip culoare', type: 'select', options: [...AUTOVIT_COLOR_FINISHES] },
          ...(v.body_type === 'van'
            ? ([
                { key: 'max_weight_kg', label: 'Masă maximă (kg)', type: 'number' },
                { key: 'payload_kg', label: 'Sarcină utilă (kg)', type: 'number' },
                { key: 'cargo_volume_m3', label: 'Volum util (m³)', type: 'number' },
                { key: 'cargo_length_mm', label: 'Lungime cală (mm)', type: 'number' },
                { key: 'cargo_width_mm', label: 'Lățime cală (mm)', type: 'number' },
                { key: 'cargo_height_mm', label: 'Înălțime cală (mm)', type: 'number' },
                { key: 'euro_pallets', label: 'Europaleți', type: 'number' },
              ] as EditFieldDef[])
            : []),
        ]}
      >
        <dl className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          <Field label="Motor" value={v.engine_displacement_cc ? `${v.engine_displacement_cc} cc` : null} />
          <Field label="Putere" value={v.engine_power_hp ? `${v.engine_power_hp} HP${v.engine_power_kw ? ` (${v.engine_power_kw} kW)` : ''}` : null} />
          <Field label="Cuplu" value={v.engine_torque_nm ? `${v.engine_torque_nm} Nm` : null} />
          <Field label="Tracțiune" value={specLabel(AUTOVIT_DRIVE_TYPES, v.drive_type)} />
          <Field label="CO2" value={v.co2_emissions ? `${v.co2_emissions} g/km` : null} />
          <Field label="Normă poluare" value={specLabel(AUTOVIT_EURO_STANDARDS, v.euro_standard)} />
          <Field label="Consum" value={v.fuel_consumption} />
          <Field label="Locuri" value={v.seats} />
          <Field label="Capacitate rezervor" value={v.fuel_tank_capacity_liters != null ? `${v.fuel_tank_capacity_liters} L` : null} />
          <Field label="Capacitate baterie" value={v.battery_capacity_kwh != null ? `${v.battery_capacity_kwh} kWh` : null} />
          <Field label="Autonomie electrică" value={v.electric_range_km != null ? `${v.electric_range_km} km` : null} />
          <Field label="Consum urban" value={v.consum_urban != null ? `${v.consum_urban} l/100km` : null} />
          <Field label="Consum extraurban" value={v.consum_extraurban != null ? `${v.consum_extraurban} l/100km` : null} />
          <Field label="Consum mixt" value={v.consum_mixt != null ? `${v.consum_mixt} l/100km` : null} />
          <Field label="Normă consum" value={v.norma_combustibil} />
          <Field label="Normă energie" value={v.norma_energie} />
          <Field label="Tapițerie" value={specLabel(AUTOVIT_INTERIOR_MATERIALS, v.interior_material)} />
          <Field label="Culoare interior" value={specLabel(AUTOVIT_INTERIOR_COLORS, v.color_interior)} />
          <Field label="Tip culoare" value={specLabel(AUTOVIT_COLOR_FINISHES, v.color_finish)} />
          {v.body_type === 'van' && (
            <>
              <Field label="Masă maximă" value={v.max_weight_kg != null ? `${v.max_weight_kg} kg` : null} />
              <Field label="Sarcină utilă" value={v.payload_kg != null ? `${v.payload_kg} kg` : null} />
              <Field label="Volum util" value={v.cargo_volume_m3 != null ? `${v.cargo_volume_m3} m³` : null} />
              <Field label="Lungime cală" value={v.cargo_length_mm != null ? `${v.cargo_length_mm} mm` : null} />
              <Field label="Lățime cală" value={v.cargo_width_mm != null ? `${v.cargo_width_mm} mm` : null} />
              <Field label="Înălțime cală" value={v.cargo_height_mm != null ? `${v.cargo_height_mm} mm` : null} />
              <Field label="Europaleți" value={v.euro_pallets} />
            </>
          )}
        </dl>
      </EditableCard>

      {/* Detail cards */}
      <div className="grid gap-6 md:grid-cols-2">
      {/* Condition */}
      <EditableCard
        title="Stare & Garanție"
        canEdit={canEdit}
        vehicleId={v.id}
        vehicle={v}
        fields={[
          { key: 'is_first_owner', label: 'Primul proprietar', type: 'bool' },
          { key: 'has_accident_history', label: 'Istoric accidente', type: 'bool' },
          { key: 'has_service_book', label: 'Carte service', type: 'bool' },
          { key: 'has_tuning', label: 'Tuning', type: 'bool' },
          { key: 'has_manufacturer_warranty', label: 'Garanție producător', type: 'bool' },
          { key: 'manufacturer_warranty_date', label: 'Garanție producător până la', type: 'date' },
          { key: 'has_dealer_warranty', label: 'Garanție dealer', type: 'bool' },
          { key: 'dealer_warranty_months', label: 'Garanție dealer (luni)', type: 'number' },
          { key: 'is_right_hand_drive', label: 'Volan pe dreapta', type: 'bool' },
          { key: 'has_particle_filter', label: 'Filtru de particule', type: 'bool' },
          { key: 'is_vintage', label: 'Vehicul de epocă', type: 'bool' },
          { key: 'is_damaged', label: 'Avariat', type: 'bool' },
          { key: 'certified_mileage', label: 'Rulaj certificat', type: 'bool' },
          { key: 'is_registered', label: 'Înmatriculat', type: 'bool' },
          { key: 'previous_owners', label: 'Nr. proprietari', type: 'number' },
          { key: 'country_of_origin', label: 'Țara de origine', type: 'text' },
        ]}
      >
        <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          <Field label="Primul proprietar" value={v.is_first_owner ? 'Da' : null} />
          <Field label="Istoric accidente" value={v.has_accident_history ? 'Da' : null} />
          <Field label="Carte service" value={v.has_service_book ? 'Da' : null} />
          <Field label="Tuning" value={v.has_tuning ? 'Da' : null} />
          <Field label="Garanție producător" value={v.has_manufacturer_warranty ? `Da${v.manufacturer_warranty_date ? ` (până la ${formatDate(v.manufacturer_warranty_date)})` : ''}` : null} />
          <Field label="Garanție dealer" value={v.has_dealer_warranty ? `${v.dealer_warranty_months ?? ''} luni` : null} />
          <Field label="Volan pe dreapta" value={v.is_right_hand_drive ? 'Da' : null} />
          <Field label="Filtru de particule" value={v.has_particle_filter ? 'Da' : null} />
          <Field label="Vehicul de epocă" value={v.is_vintage ? 'Da' : null} />
          <Field label="Avariat" value={v.is_damaged ? 'Da' : null} />
          <Field label="Rulaj certificat" value={v.certified_mileage ? 'Da' : null} />
          <Field label="Înmatriculat" value={v.is_registered ? 'Da' : null} />
          <Field label="Nr. proprietari" value={v.previous_owners} />
          <Field label="Țara de origine" value={v.country_of_origin} />
        </dl>
      </EditableCard>

      {/* Source & Acquisition */}
      <EditableCard
        title="Sursă & Achiziție"
        canEdit={canEdit}
        vehicleId={v.id}
        vehicle={v}
        fields={[
          { key: 'supplier_name', label: 'Furnizor', type: 'text' },
          { key: 'supplier_cif', label: 'CIF furnizor', type: 'text' },
          { key: 'purchase_contract_number', label: 'Nr. contract', type: 'text' },
          { key: 'purchase_contract_date', label: 'Dată contract', type: 'date' },
          { key: 'owner_name', label: 'Proprietar', type: 'text' },
          { key: 'acquisition_document_number', label: 'Nr. factură intrare', type: 'text' },
          // acquisition_price (GROSS EUR) is intentionally NOT inline-editable: editing
          // gross in isolation would desync purchase_price_net (NET EUR), breaking the
          // canonical gross/net invariant the PricingSheet + profit strip rely on. It
          // stays editable only via the full vehicle editor, which keeps gross/net/currency
          // in sync via toCanonical. The read-only Field below still shows the value.
          { key: 'acquisition_exchange_rate', label: 'Curs BNR', type: 'number' },
        ]}
      >
        <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          <Field label="Sursă" value={sourceLabel(v.source)} />
          <Field label="Furnizor" value={v.supplier_name} />
          <Field label="CIF furnizor" value={v.supplier_cif} />
          <Field label="Nr. contract" value={v.purchase_contract_number} />
          <Field label="Dată contract" value={formatDate(v.purchase_contract_date)} />
          <Field label="Proprietar" value={v.owner_name} />
          <Field label="Nr. factură intrare" value={v.acquisition_document_number} />
          <Field label="Preț achiziție (EUR)" value={v.acquisition_price != null ? `${fmtMoney(v.acquisition_price)} EUR` : null} />
          <Field label="Curs BNR" value={v.acquisition_exchange_rate} />
        </dl>
      </EditableCard>

      {/* Custody/consignment agreement — present only when the vehicle was
          handed off from a failed (LOST) buyback record into CarPark custody
          (is_consignment=true, source='CUSTODIE'); see carpark_vehicle_consignment.
          Additionally gated on canViewFinance (defense-in-depth): the card shows
          owner payout / commission / floor, which the backend already strips for
          non-finance users. */}
      {v.consignment && canViewFinance && (
        <Card className="p-4 space-y-3">
          <h3 className="text-sm font-semibold">Acord custodie</h3>
          <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            <Field
              label="Preț proprietar"
              value={v.consignment.owner_price != null ? `${fmtMoney(v.consignment.owner_price)} ${v.consignment.currency}` : null}
            />
            <Field
              label="Comision"
              value={
                v.consignment.commission_type === 'percent'
                  ? `${v.consignment.commission_value}%`
                  : `${fmtMoney(v.consignment.commission_value)} ${v.consignment.currency}`
              }
            />
            <Field
              label="Preț minim"
              value={v.consignment.min_sale_price != null ? `${fmtMoney(v.consignment.min_sale_price)} ${v.consignment.currency}` : null}
            />
            <Field label="Nr. contract" value={v.consignment.contract_number} />
            <Field label="Data acord" value={formatDate(v.consignment.agreement_date)} />
            <Field label="Data expirare" value={formatDate(v.consignment.expiry_date)} />
          </dl>
        </Card>
      )}

      {/* Acquisition cost lines (vehicle.cost_lines JSON) */}
      {acqCostLines.length > 0 && (
        <Card className="p-4 md:col-span-2">
          <h3 className="text-sm font-semibold mb-3">Costuri achiziție</h3>
          <div className="space-y-1.5">
            {acqCostLines.map((l, i) => (
              <div key={i} className="flex items-start justify-between gap-3 border-b pb-1.5 text-sm last:border-0 last:pb-0">
                <span className="text-muted-foreground">
                  {l.type || '-'}{l.description ? ` — ${l.description}` : ''}
                </span>
                <span className="shrink-0 text-right tabular-nums">
                  <span className="font-medium">{fmtMoney(Number(l.eur) || 0)} EUR</span>
                  {(l.lei != null || l.kurs != null || l.date) && (
                    <span className="ml-2 text-xs text-muted-foreground">
                      {[
                        l.lei != null ? `${fmtMoney(Number(l.lei))} LEI` : null,
                        l.kurs != null ? `@ ${l.kurs}` : null,
                        l.date ? formatDate(l.date) : null,
                      ].filter(Boolean).join(', ')}
                    </span>
                  )}
                </span>
              </div>
            ))}
            <div className="flex items-center justify-between pt-1.5 text-sm font-semibold">
              <span>Total</span>
              <span className="tabular-nums">{fmtMoney(acqCostTotal)} EUR</span>
            </div>
          </div>
        </Card>
      )}

      {/* Equipment */}
      {(() => {
        // Two equipment sources, shown as one deduplicated set of labelled chips:
        //  • equipment_options (TEXT[]) — the hyphen slugs picked in the form.
        //  • equipment (JSONB) — the importer writes a flat {slug: true} map of
        //    raw Autovit API flags; show only the TRUE (present) ones. A legacy
        //    grouped {category: [labels]} shape is still rendered under headings.
        const optionSlugs = Array.isArray(v.equipment_options) ? v.equipment_options : []
        const flagKeys: string[] = []
        const grouped: Array<[string, string[]]> = []
        if (v.equipment && typeof v.equipment === 'object') {
          for (const [k, val] of Object.entries(v.equipment)) {
            if (Array.isArray(val)) grouped.push([k, val.filter(Boolean).map(String)])
            else if (val) flagKeys.push(k)
          }
        }
        const seen = new Set<string>()
        const chips: string[] = []
        for (const key of [...optionSlugs, ...flagKeys]) {
          const label = equipmentLabel(String(key))
          const norm = label.toLowerCase()
          if (label && !seen.has(norm)) { seen.add(norm); chips.push(label) }
        }
        if (chips.length === 0 && grouped.length === 0) return null
        return (
          <Card className="p-4 md:col-span-2">
            <h3 className="text-sm font-semibold mb-3">Dotări</h3>
            {chips.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {chips.map((label) => (
                  <Badge key={label} variant="secondary" className="text-[11px]">{label}</Badge>
                ))}
              </div>
            )}
            {grouped.length > 0 && (
              <div className="mt-4 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {grouped.map(([category, items]) => (
                  <div key={category}>
                    <h4 className="text-xs font-medium text-muted-foreground mb-1">{humanizeSlug(category)}</h4>
                    <ul className="space-y-0.5">
                      {items.map((item, i) => (
                        <li key={i} className="text-sm">{item}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </Card>
        )
      })()}

      {/* Announcement / listing */}
      {(canEdit || v.listing_title || v.listing_description) && (
        <EditableCard
          title="Anunț"
          canEdit={canEdit}
          vehicleId={v.id}
          vehicle={v}
          className="md:col-span-2"
          editGridClassName="grid grid-cols-1 gap-3"
          fields={[
            { key: 'listing_title', label: 'Titlu anunț', type: 'text' },
            { key: 'listing_description', label: 'Descriere anunț', type: 'textarea' },
          ]}
        >
          {v.listing_title && (
            <div className="mb-3">
              <div className="text-xs text-muted-foreground mb-1">Titlu anunț</div>
              <p className="text-sm whitespace-pre-wrap">{v.listing_title}</p>
            </div>
          )}
          {v.listing_description && (
            <div>
              <div className="text-xs text-muted-foreground mb-1">Descriere anunț</div>
              <p className="text-sm whitespace-pre-wrap">{v.listing_description}</p>
            </div>
          )}
          {!v.listing_title && !v.listing_description && (
            <p className="text-sm text-muted-foreground">Fără anunț — apasă creionul pentru a adăuga.</p>
          )}
        </EditableCard>
      )}

      {/* Notes */}
      {(canEdit || v.notes || v.internal_notes) && (
        <EditableCard
          title="Note"
          canEdit={canEdit}
          vehicleId={v.id}
          vehicle={v}
          className="md:col-span-2"
          editGridClassName="grid grid-cols-1 gap-3"
          fields={[
            { key: 'notes', label: 'Note publice', type: 'textarea' },
            { key: 'internal_notes', label: 'Note interne', type: 'textarea' },
          ]}
        >
          {v.notes && (
            <div className="mb-3">
              <div className="text-xs text-muted-foreground mb-1">Note publice</div>
              <p className="text-sm whitespace-pre-wrap">{v.notes}</p>
            </div>
          )}
          {v.internal_notes && (
            <div>
              <div className="text-xs text-muted-foreground mb-1">Note interne</div>
              <p className="text-sm whitespace-pre-wrap">{v.internal_notes}</p>
            </div>
          )}
          {!v.notes && !v.internal_notes && (
            <p className="text-sm text-muted-foreground">Fără note — apasă creionul pentru a adăuga.</p>
          )}
        </EditableCard>
      )}
      </div>
    </div>
  )
}

// ── Pricing Tab ────────────────────────────────────────────
function PricingTab({
  vehicle: v,
  pricingHistory,
  promotions,
  canEdit,
}: {
  vehicle: Vehicle
  pricingHistory: PricingHistoryEntry[]
  promotions: Promotion[]
  canEdit: boolean
}) {
  const queryClient = useQueryClient()

  const sheets = useMemo(() => parseSheets(v.pricing_sheets), [v.pricing_sheets])
  const latest = sheets.length ? sheets[sheets.length - 1] : null
  const latestPublished = useMemo(
    () => [...sheets].reverse().find((s) => s.status === 'published') ?? null,
    [sheets],
  )
  const costLinesForSheet = useMemo(
    () => parseCostLines(v.cost_lines).map((l) => ({ eur: typeof l.eur === 'number' ? l.eur : null })),
    [v.cost_lines],
  )

  // Adding a fișă: "Deschide fișă nouă" starts a blank editable draft shown as a
  // synthetic top row in the history table; `newSeq` re-seeds the editor.
  const [newDraft, setNewDraft] = useState(false)
  const [newSeq, setNewSeq] = useState(0)

  // The editor edits the newest fișă in place when it's still editable (draft or
  // published <24h); otherwise you open a new one. Seeds come from that context.
  const active = newDraft ? null : latest
  const seedList = active?.list_price ?? (latestPublished?.list_price ?? v.list_price ?? null)
  const seedPromo = active?.promotional_price ?? (latestPublished?.promotional_price ?? v.promotional_price ?? null)
  const initialInputs: Partial<SheetInputs> | undefined = active
    ? { target: active.target, finRate: active.finRate, targetDays: active.targetDays, warrantyPct: active.warrantyPct, anchor: active.anchor, comps: active.comps, anchorDate: active.anchorDate }
    : undefined
  const seedKey = active ? `sheet-${active.id}` : `new-${newSeq}`

  // Zona de preț stays on top, fed by the LAST fișă (published if any, else the
  // most recent). If no fișă exists yet, fall back to the vehicle's own price +
  // default params so the ladder never disappears (needs an acquisition basis).
  const liveSheet = latestPublished ?? latest
  const liveModel = useMemo(() => {
    const form = {
      ...(v as unknown as Record<string, unknown>),
      list_price: liveSheet ? liveSheet.list_price : v.list_price,
      promotional_price: liveSheet ? liveSheet.promotional_price : v.promotional_price,
      price_currency: liveSheet ? liveSheet.price_currency : v.price_currency,
    }
    const inputs = liveSheet
      ? { target: liveSheet.target, finRate: liveSheet.finRate, targetDays: liveSheet.targetDays, warrantyPct: liveSheet.warrantyPct, anchor: liveSheet.anchor, comps: liveSheet.comps, anchorDate: liveSheet.anchorDate }
      : { target: 600, finRate: 0.05, targetDays: 45, warrantyPct: 1.5, anchor: 0, comps: null, anchorDate: '' }
    const model = computePricingModel(form, costLinesForSheet, inputs)
    return model.hasBasis ? model : null
  }, [liveSheet, v, costLinesForSheet])

  // Per-row expand/collapse in the fișe history table. The synthetic "new fișă"
  // row uses the sentinel id below.
  const NEW_ROW = '__new__'
  const [expandedSheets, setExpandedSheets] = useState<Set<string>>(new Set())
  const toggleSheet = (id: string) => setExpandedSheets((prev) => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })
  const openNewSheet = () => {
    setNewDraft(true)
    setNewSeq((n) => n + 1)
    setExpandedSheets((prev) => new Set(prev).add(NEW_ROW))
  }
  const cancelNewSheet = () => {
    setNewDraft(false)
    setExpandedSheets((prev) => { const n = new Set(prev); n.delete(NEW_ROW); return n })
  }

  const saveSheets = useMutation({
    mutationFn: (payload: Partial<Vehicle>) => carparkApi.updateVehicle(v.id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'vehicle', v.id] })
      setNewDraft(false)
      setExpandedSheets((prev) => { const n = new Set(prev); n.delete(NEW_ROW); return n })
    },
    onError: () => toast.error('Salvarea fișei a eșuat'),
  })

  // Upsert the working sheet: reuse the active sheet if it is still editable,
  // otherwise append a new one. Publishing also writes the vehicle live price.
  const upsertSheet = (inputs: SheetInputs, derived: { breakeven: number; critic: number }, status: 'draft' | 'published') => {
    const nowIso = new Date().toISOString()
    const reuse = active && sheetEditable(active) ? active : null
    const snap: PricingSheetSnapshot = {
      id: reuse?.id ?? `sheet-${Date.now()}-${Math.round(Math.random() * 1e6)}`,
      status,
      created_at: reuse?.created_at ?? nowIso,
      published_at: status === 'published' ? (reuse?.status === 'published' ? reuse.published_at : nowIso) : null,
      ...inputs,
      breakeven: derived.breakeven,
      critic: derived.critic,
    }
    const next = reuse ? sheets.map((s) => (s.id === reuse.id ? snap : s)) : [...sheets, snap]
    const payload: Partial<Vehicle> = { pricing_sheets: JSON.stringify(next) }
    if (status === 'published') {
      payload.list_price = inputs.list_price
      payload.promotional_price = inputs.promotional_price
      if (inputs.price_currency) payload.price_currency = inputs.price_currency
      // Keep the active price (used by the catalog column + price filter/sort) in
      // sync with the published price, else it would show the stale create value.
      payload.current_price = activeSellingPrice(inputs)
    }
    return payload
  }
  const handleDraft = (inputs: SheetInputs, d: { breakeven: number; critic: number }) =>
    saveSheets.mutate(upsertSheet(inputs, d, 'draft'), { onSuccess: () => toast.success('Ciornă salvată — prețul mașinii nu s-a schimbat') })
  const handlePublish = (inputs: SheetInputs, d: { breakeven: number; critic: number }) =>
    saveSheets.mutate(upsertSheet(inputs, d, 'published'), { onSuccess: () => toast.success('Preț publicat') })

  const currency = latestPublished?.price_currency ?? v.price_currency
  const editorProps = {
    vehicle: v, costLines: costLinesForSheet, editable: canEdit, locked: false,
    initial: initialInputs, seedList, seedPromo, saving: saveSheets.isPending,
    onSaveDraft: handleDraft, onPublish: handlePublish,
  }

  return (
    <div className="space-y-6">
      {/* Zona de preț — fed by the LAST fișă (not the live editor). */}
      {liveModel && <PriceZone model={liveModel} />}

      {/* Fișe de preț — create/edit inline; the table is the single surface. */}
      {(sheets.length > 0 || canEdit) && (
        <Card className="overflow-hidden p-0">
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
              <span className="font-semibold">Fișe de preț ({sheets.length})</span>
              <span className="text-muted-foreground">· Preț publicat:</span>
              {latestPublished && latestPublished.list_price != null ? (
                <b className="tabular-nums"><CurrencyDisplay value={latestPublished.list_price} currency={latestPublished.price_currency} /></b>
              ) : (
                <b className="text-amber-600 dark:text-amber-400">fără preț publicat</b>
              )}
            </div>
            {canEdit && (newDraft ? (
              <Button type="button" variant="ghost" size="sm" onClick={cancelNewSheet}>Renunță</Button>
            ) : (
              <Button type="button" variant="outline" size="sm" onClick={openNewSheet}>
                <Plus className="mr-1 h-3.5 w-3.5" /> Fișă nouă
              </Button>
            ))}
          </div>
          <div className="overflow-x-auto border-t">
            <table className="w-full text-sm">
              <thead className="text-xs text-muted-foreground">
                <tr className="border-b">
                  <th className="w-8 px-3 py-2"></th>
                  <th className="px-3 py-2 text-left font-medium">Dată</th>
                  <th className="px-3 py-2 text-left font-medium">Status</th>
                  <th className="px-3 py-2 text-right font-medium">Listă</th>
                  <th className="px-3 py-2 text-right font-medium">Promo</th>
                  <th className="px-3 py-2 text-right font-medium">Breakeven</th>
                  <th className="px-3 py-2 text-right font-medium">Critic</th>
                </tr>
              </thead>
              <tbody>
                {/* New fișă — synthetic editable row */}
                {newDraft && canEdit && (
                  <Fragment key={NEW_ROW}>
                    <tr className="cursor-pointer border-b bg-blue-50/40 dark:bg-blue-950/20" onClick={() => toggleSheet(NEW_ROW)}>
                      <td className="px-3 py-2 text-muted-foreground">{expandedSheets.has(NEW_ROW) ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</td>
                      <td className="px-3 py-2 tabular-nums">azi</td>
                      <td className="px-3 py-2"><Badge variant="outline" className="text-[10px] uppercase">fișă nouă</Badge></td>
                      <td className="px-3 py-2 text-right tabular-nums">{seedList != null ? <CurrencyDisplay value={seedList} currency={currency} /> : '—'}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{seedPromo != null ? <CurrencyDisplay value={seedPromo} currency={currency} /> : '—'}</td>
                      <td className="px-3 py-2 text-right text-muted-foreground">—</td>
                      <td className="px-3 py-2 text-right text-muted-foreground">—</td>
                    </tr>
                    {expandedSheets.has(NEW_ROW) && (
                      <tr className="border-b bg-muted/30">
                        <td></td>
                        <td colSpan={6} className="px-3 py-3"><SheetEditor key={seedKey} {...editorProps} /></td>
                      </tr>
                    )}
                  </Fragment>
                )}
                {sheets.length === 0 && !newDraft && (
                  <tr><td colSpan={7} className="px-3 py-6 text-center text-muted-foreground">Nicio fișă de preț. Apasă „Fișă nouă" pentru a crea prima.</td></tr>
                )}
                {[...sheets].reverse().map((s) => {
                  const ed = sheetEditable(s)
                  const editRow = !newDraft && latest?.id === s.id && ed // the one in-place-editable fișă
                  const isOpen = expandedSheets.has(s.id)
                  // Recompute breakeven/critic from the engine so the table, the
                  // expanded summary and the Zona all show the same numbers
                  // (stored values are only a fallback).
                  const rowModel = sheetModel(s, v, costLinesForSheet)
                  const eur0 = (x: number) => `${Math.round(x).toLocaleString('ro-RO')} €`
                  return (
                    <Fragment key={s.id}>
                      <tr className="cursor-pointer border-b last:border-0 hover:bg-muted/50" onClick={() => toggleSheet(s.id)}>
                        <td className="px-3 py-2 text-muted-foreground">
                          {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                        </td>
                        <td className="px-3 py-2 tabular-nums">{formatDate(s.published_at ?? s.created_at)}</td>
                        <td className="px-3 py-2">
                          <Badge variant="outline" className="text-[10px] uppercase">
                            {s.status === 'draft' ? 'ciornă' : ed ? 'publicat · editabil' : 'publicat · blocat'}
                          </Badge>
                          {editRow && <span className="ml-1.5 text-[10px] text-blue-600 dark:text-blue-400">editează</span>}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">{s.list_price != null ? <CurrencyDisplay value={s.list_price} currency={s.price_currency} /> : '—'}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{s.promotional_price != null ? <CurrencyDisplay value={s.promotional_price} currency={s.price_currency} /> : '—'}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{rowModel.hasBasis ? eur0(rowModel.be) : '—'}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{rowModel.hasBasis ? eur0(rowModel.critic) : '—'}</td>
                      </tr>
                      {isOpen && (
                        <tr className="border-b bg-muted/30 last:border-0">
                          <td></td>
                          <td colSpan={6} className="px-3 py-3">
                            {editRow ? <SheetEditor key={seedKey} {...editorProps} /> : <SheetSummary sheet={s} model={rowModel} />}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Config flags + promotions — collapsed. Prices live in the header/fișă,
          costs on the Costuri tab, sale info on the Vânzare tab. */}
      <details className="rounded-lg border">
        <summary className="cursor-pointer px-4 py-3 text-sm font-semibold">Detalii preț & configurare</summary>
        <div className="space-y-4 border-t p-4">
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Field label="TVA inclus" value={v.price_includes_vat ? 'Da' : 'Nu'} />
            <Field label="Negociabil" value={v.is_negotiable ? 'Da' : 'Nu'} />
            <Field label="Regim marjă" value={v.margin_scheme ? 'Da' : 'Nu'} />
            <Field label="Finanțare" value={v.eligible_for_financing ? 'Da' : 'Nu'} />
          </dl>
          {promotions.length > 0 && (
            <div>
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Promoții active</h4>
              <div className="space-y-2">
                {promotions.map((promo) => (
                  <div key={promo.id} className="flex items-center justify-between rounded border p-2">
                    <div>
                      <span className="text-sm font-medium">{promo.name}</span>
                      <Badge variant="outline" className="ml-2 text-[10px]">
                        {PROMO_TYPE_LABELS[promo.promo_type]}
                      </Badge>
                      {promo.discount_value != null && promo.promo_type === 'discount' && (
                        <span className="ml-2 text-sm text-muted-foreground">
                          {promo.discount_type === 'percent' ? `${promo.discount_value}%` : `${promo.discount_value} ${v.price_currency}`}
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {formatDate(promo.start_date)} — {formatDate(promo.end_date)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </details>

      {/* Pricing History */}
      {pricingHistory.length > 0 && (
        <Card className="p-4">
          <h3 className="text-sm font-semibold mb-3">Istoric prețuri</h3>
          <div className="space-y-2">
            {pricingHistory.map((entry) => (
              <div key={entry.id} className="flex items-center justify-between text-sm border-b last:border-0 pb-2 last:pb-0">
                <div className="flex items-center gap-2">
                  {entry.old_price != null && (
                    <span className="text-muted-foreground line-through">
                      <CurrencyDisplay value={entry.old_price} currency={v.price_currency} />
                    </span>
                  )}
                  {entry.old_price != null && <span className="text-muted-foreground">&rarr;</span>}
                  {entry.new_price != null && (
                    <span className="font-medium">
                      <CurrencyDisplay value={entry.new_price} currency={v.price_currency} />
                    </span>
                  )}
                  {entry.change_reason && (
                    <Badge variant="outline" className="text-[10px]">{entry.change_reason}</Badge>
                  )}
                  {entry.rule_name && (
                    <Badge variant="secondary" className="text-[10px]">{entry.rule_name}</Badge>
                  )}
                </div>
                <span className="text-xs text-muted-foreground">{formatDate(entry.created_at)}</span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}

// Build the engine model for one saved fișă snapshot (list/promo + inputs)
// against the current vehicle acquisition. Pure — safe to call in render.
function sheetModel(s: PricingSheetSnapshot, v: Vehicle, costLines: { eur: number | null }[]): PricingModel {
  const form = { ...(v as unknown as Record<string, unknown>), list_price: s.list_price, promotional_price: s.promotional_price, price_currency: s.price_currency }
  return computePricingModel(form, costLines, {
    target: s.target, finRate: s.finRate, targetDays: s.targetDays,
    warrantyPct: s.warrantyPct, anchor: s.anchor, comps: s.comps, anchorDate: s.anchorDate,
  })
}

// Expanded fișă summary — compact. A stat strip (recomputed economics) on top,
// then a dense parameter grid. Breakeven/critic come from `model` (recomputed),
// so they match the table cells and the Zona.
function SheetSummary({ sheet: s, model }: {
  sheet: PricingSheetSnapshot
  model: PricingModel
}) {
  const eur = (x: number) => `${Math.round(x).toLocaleString('ro-RO')} €`
  const eL = model.listEur > 0 ? econ(model.listEur, model.params) : null
  const profitCls = eL ? (eL.profitNet >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400') : ''

  const stats: [string, string, string?][] = [
    ['Profit net', eL ? eur(eL.profitNet) : '—', profitCls],
    ['Marjă netă', eL ? `${(eL.marginNet * 100).toFixed(1)}%` : '—', profitCls],
    ['Cost total', eur(model.landedCostEur)],
    ['Breakeven', eur(model.be)],
    ['Critic', eur(model.critic)],
    ['Regim', model.regime === 'MARGIN' ? 'Marjă' : 'TVA'],
  ]
  const params: [string, string][] = [
    ['Creată', formatDate(s.created_at)],
    ['Publicată', s.published_at ? formatDate(s.published_at) : '—'],
    ['Profit țintă', eur(s.target)],
    ['Zile țintă', `${s.targetDays}`],
    ['Finanțare/zi', `${s.finRate}%`],
    ['Garanție', `${s.warrantyPct}%`],
    ['Preț piață', s.anchor > 0 ? eur(s.anchor) : '—'],
    ['Nr. anunțuri', s.comps != null ? `${s.comps}` : '—'],
    ['Data piață', s.anchorDate ? formatDate(s.anchorDate) : '—'],
  ]

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-3 gap-px overflow-hidden rounded-md border bg-border sm:grid-cols-6">
        {stats.map(([t, val, cls]) => (
          <div key={t} className="bg-card px-2.5 py-1.5">
            <div className="text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">{t}</div>
            <div className={`text-xs font-semibold tabular-nums ${cls ?? ''}`}>{val}</div>
          </div>
        ))}
      </div>
      <dl className="grid grid-cols-2 gap-x-4 text-[11px] sm:grid-cols-3 lg:grid-cols-5">
        {params.map(([k, val]) => (
          <div key={k} className="flex justify-between gap-2 border-b border-dashed border-border/60 py-0.5">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="font-medium tabular-nums">{val}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

// Holds the working list/promo prices for one fișă; remounted (re-seeded) by
// its `key` in PricingTab whenever the active sheet changes.
function SheetEditor({
  vehicle: v,
  costLines,
  editable,
  locked,
  initial,
  seedList,
  seedPromo,
  saving,
  onSaveDraft,
  onPublish,
}: {
  vehicle: Vehicle
  costLines: { eur: number | null }[]
  editable: boolean
  locked: boolean
  initial?: Partial<SheetInputs>
  seedList: number | null
  seedPromo: number | null
  saving: boolean
  onSaveDraft: (inputs: SheetInputs, derived: { breakeven: number; critic: number }) => void
  onPublish: (inputs: SheetInputs, derived: { breakeven: number; critic: number }) => void
}) {
  const [prices, setPrices] = useState<{ list_price: number | null; promotional_price: number | null }>({
    list_price: seedList,
    promotional_price: seedPromo,
  })
  const formForSheet = { ...(v as unknown as Record<string, unknown>), ...prices }
  return (
    <PricingSheet
      form={formForSheet}
      costLines={costLines}
      editable={editable}
      locked={locked}
      initial={initial}
      onPriceChange={(f, val) => setPrices((p) => ({ ...p, [f]: val }))}
      onSaveDraft={onSaveDraft}
      onPublish={onPublish}
      saving={saving}
    />
  )
}

// ── Autovit direct publish (account picker → dry-run preview → confirm) ────
function advertField(params: Record<string, unknown>, key: string): string {
  const v = params[key]
  return v === undefined || v === null || v === '' ? '—' : String(v)
}

function AutovitPublishAction({ vehicleId, canEdit }: { vehicleId: number; canEdit: boolean }) {
  const [open, setOpen] = useState(false)
  const [accountId, setAccountId] = useState('')
  const [step, setStep] = useState<'select' | 'preview' | 'missing' | 'success'>('select')
  const [advert, setAdvert] = useState<Record<string, unknown> | null>(null)
  const [missing, setMissing] = useState<string[]>([])
  const [externalUrl, setExternalUrl] = useState<string | null>(null)
  const [publishOutcome, setPublishOutcome] = useState<{ updated: boolean; status?: string } | null>(null)

  const queryClient = useQueryClient()
  const { data: accounts = [], isLoading: accountsLoading } = useQuery({
    queryKey: ['autovit', 'accounts'],
    queryFn: autovitApi.getAccounts,
    enabled: open,
  })
  const connectedAccounts = accounts.filter((a) => a.status === 'connected')

  // Current Autovit publish state (across accounts) — surfaces the status/last
  // error that used to be visible only in the DB.
  const { data: autovitListings = [] } = useQuery({
    queryKey: ['autovit', 'vehicle-status', vehicleId],
    queryFn: () => autovitApi.getVehicleStatus(vehicleId),
  })
  const autovitListing = autovitListings[0] ?? null

  const reset = () => {
    setStep('select')
    setAccountId('')
    setAdvert(null)
    setMissing([])
    setExternalUrl(null)
    setPublishOutcome(null)
  }

  const previewMutation = useMutation({
    mutationFn: () => autovitApi.publish(Number(accountId), vehicleId, { dryRun: true }),
    onSuccess: (res) => {
      setAdvert((res.advert as Record<string, unknown>) ?? null)
      setStep('preview')
    },
    onError: (err: unknown) => {
      const apiErr = err as { data?: { error?: string; missing?: string[] } }
      if (apiErr?.data?.missing?.length) {
        setMissing(apiErr.data.missing)
        setStep('missing')
      } else {
        toast.error(apiErr?.data?.error || 'Previzualizarea a eșuat')
      }
    },
  })

  const publishMutation = useMutation({
    mutationFn: () => autovitApi.publish(Number(accountId), vehicleId, { draft: true }),
    onSuccess: (res) => {
      if (res.success) {
        setExternalUrl(res.external_url || null)
        setPublishOutcome({ updated: !!res.updated_existing, status: res.status })
        setStep('success')
        queryClient.invalidateQueries({ queryKey: ['autovit', 'vehicle-status', vehicleId] })
        toast.success(res.updated_existing
          ? 'Anunț actualizat pe Autovit'
          : res.status === 'active' ? 'Anunț publicat (activ) pe Autovit'
          : 'Anunț publicat ca draft pe Autovit')
        // Surface "already published → updated" + any dropped-param warnings.
        if (res.warnings && res.warnings.length > 0) {
          toast.info(res.warnings.join(' · '))
        }
      } else {
        toast.error(res.error || 'Publicarea a eșuat')
      }
    },
    onError: (err: unknown) => {
      const apiErr = err as { data?: { error?: string } }
      toast.error(apiErr?.data?.error || 'Publicarea a eșuat')
    },
  })

  const verifyStatusMutation = useMutation({
    mutationFn: () => autovitApi.verifyStatus(vehicleId),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['autovit', 'vehicle-status', vehicleId] })
      toast.success(res.refreshed > 0 ? 'Status Autovit actualizat' : 'Niciun anunț de verificat')
    },
    onError: () => toast.error('Verificarea statusului a eșuat'),
  })

  const refreshStatus = () =>
    queryClient.invalidateQueries({ queryKey: ['autovit', 'vehicle-status', vehicleId] })
  const autovitErr = (e: unknown, fallback: string) =>
    toast.error((e as { data?: { error?: string } })?.data?.error || fallback)

  // Deactivate = disable on Autovit (reversible — re-publishing reactivates).
  const deactivateMutation = useMutation({
    mutationFn: () => autovitApi.unpublish(Number(autovitListing?.account_id), vehicleId),
    onSuccess: (res) => {
      if (res.success) { refreshStatus(); toast.success('Anunț dezactivat pe Autovit') }
      else toast.error(res.error || 'Dezactivarea a eșuat')
    },
    onError: (e) => autovitErr(e, 'Dezactivarea a eșuat'),
  })

  // Delete = permanent removal on Autovit (re-publishing creates a new advert).
  const deleteMutation = useMutation({
    mutationFn: () => autovitApi.deleteAdvert(Number(autovitListing?.account_id), vehicleId),
    onSuccess: (res) => {
      if (res.success) { refreshStatus(); toast.success('Anunț șters de pe Autovit') }
      else toast.error(res.error || 'Ștergerea a eșuat')
    },
    onError: (e) => autovitErr(e, 'Ștergerea a eșuat'),
  })

  const params = (advert?.params as Record<string, unknown>) || {}
  const price = params.price as { '1'?: number; currency?: string } | undefined

  const autovitStatusUi: Record<string, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
    active: { label: 'Publicat', variant: 'default' },
    unpaid: { label: 'Draft (neplătit)', variant: 'secondary' },
    inactive: { label: 'Inactiv', variant: 'outline' },
    moderation: { label: 'În moderare', variant: 'secondary' },
    expired: { label: 'Expirat', variant: 'outline' },
    disabled: { label: 'Dezactivat', variant: 'outline' },
    removed_by_user: { label: 'Retras de pe Autovit', variant: 'outline' },
    removed_by_moderator: { label: 'Eliminat de Autovit', variant: 'destructive' },
    error: { label: 'Eroare', variant: 'destructive' },
  }
  // An advert the user/moderator removed on Autovit no longer exists there, so
  // "publishing" re-creates it (the backend recreates on a removed/404 advert).
  const autovitLive = !!autovitListing?.external_advert_id &&
    !String(autovitListing?.status ?? '').startsWith('removed')
  const autovitUi = autovitListing
    ? autovitStatusUi[autovitListing.status] ?? { label: autovitListing.status, variant: 'outline' as const }
    : null

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline" className="min-w-[11rem]" onClick={() => setOpen(true)}>
          <Send className="mr-1.5 h-3.5 w-3.5" />
          {autovitLive ? 'Actualizează pe Autovit' : 'Publică pe Autovit'}
        </Button>
        {autovitListing && autovitUi && (
          <Badge
            variant={autovitUi.variant}
            className="text-[10px] font-normal"
            title={autovitListing.last_error || autovitListing.external_url || undefined}
          >
            Autovit: {autovitUi.label}
          </Badge>
        )}
        {autovitListing?.external_advert_id && (
          <Button
            size="sm"
            variant="ghost"
            className="h-7 px-2 text-xs"
            onClick={() => verifyStatusMutation.mutate()}
            disabled={verifyStatusMutation.isPending}
            title="Reîmprospătează statusul din Autovit"
          >
            <RefreshCw className={`mr-1 h-3.5 w-3.5 ${verifyStatusMutation.isPending ? 'animate-spin' : ''}`} />
            Verifică status
          </Button>
        )}
        {canEdit && autovitLive && (
          <>
            <Button
              size="sm" variant="ghost" className="h-7 w-7 p-0"
              onClick={() => deactivateMutation.mutate()}
              disabled={deactivateMutation.isPending}
              title="Dezactivează anunțul pe Autovit (reversibil)"
            >
              {deactivateMutation.isPending
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <PowerOff className="h-3.5 w-3.5" />}
            </Button>
            <Button
              size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive hover:text-destructive"
              onClick={() => {
                if (window.confirm('Ștergi definitiv anunțul de pe Autovit? Acțiunea este ireversibilă — republicarea va crea un anunț nou.'))
                  deleteMutation.mutate()
              }}
              disabled={deleteMutation.isPending}
              title="Șterge definitiv anunțul de pe Autovit"
            >
              {deleteMutation.isPending
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <Trash2 className="h-3.5 w-3.5" />}
            </Button>
          </>
        )}
        {autovitListing?.last_sync && (
          <span className="text-[10px] text-muted-foreground" title="Ultima verificare a statusului Autovit">
            verificat {formatRoDateTime(autovitListing.last_sync)}
          </span>
        )}
        {autovitListing?.external_url && (
          <a
            href={autovitListing.external_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            title="Deschide anunțul publicat pe Autovit"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Vezi anunțul
          </a>
        )}
      </div>
      <Dialog
        open={open}
        onOpenChange={(v) => {
          setOpen(v)
          if (!v) reset()
        }}
      >
        <DialogContent className="sm:max-w-lg" aria-describedby={undefined}>
          <DialogHeader>
            <DialogTitle>Publică pe Autovit</DialogTitle>
            {step === 'select' && (
              <DialogDescription>Alege contul Autovit conectat pentru publicare.</DialogDescription>
            )}
          </DialogHeader>

          {step === 'select' && (
            <div className="space-y-4 py-2">
              {accountsLoading ? (
                <Skeleton className="h-9 w-full" />
              ) : connectedAccounts.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Niciun cont Autovit conectat. Configurează unul din Setări → Connectori.
                </p>
              ) : (
                <Select value={accountId} onValueChange={setAccountId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Selectează contul Autovit" />
                  </SelectTrigger>
                  <SelectContent>
                    {connectedAccounts.map((a: AutovitAccount) => (
                      <SelectItem key={a.id} value={String(a.id)}>
                        {a.email}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
          )}

          {step === 'missing' && (
            <div className="space-y-3 py-2">
              <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <div>
                  <p className="font-medium">Câmpuri obligatorii lipsă</p>
                  <ul className="mt-1 list-disc pl-4 text-xs">
                    {missing.map((m) => (
                      <li key={m}>{m}</li>
                    ))}
                  </ul>
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                Completează aceste câmpuri pe fișa vehiculului, apoi încearcă din nou.
              </p>
            </div>
          )}

          {step === 'preview' && advert && (
            <div className="space-y-3 py-2">
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <Field label="Titlu" value={String(advert.title || '—')} className="col-span-2" />
                <Field
                  label="Preț"
                  value={price?.['1'] ? `${Number(price['1']).toLocaleString('ro-RO')} ${price.currency || ''}` : '—'}
                />
                <Field label="Marcă / Model" value={`${advertField(params, 'make')} ${advertField(params, 'model')}`} />
                <Field label="An" value={advertField(params, 'year')} />
                <Field label="Km" value={advertField(params, 'mileage')} />
                <Field label="Combustibil" value={advertField(params, 'fuel_type')} />
              </dl>
              {advert.description ? (
                <div className="max-h-24 overflow-y-auto rounded-md border p-2 text-xs text-muted-foreground">
                  {String(advert.description)}
                </div>
              ) : null}
              <p className="text-xs text-muted-foreground">
                Anunțul va fi publicat ca <strong>draft</strong> (dezactivat) — îl poți activa manual de pe Autovit.ro.
              </p>
            </div>
          )}

          {step === 'success' && (
            <div className="space-y-3 py-2">
              <p className="text-sm">
                {publishOutcome?.updated
                  ? 'Anunțul existent a fost actualizat pe Autovit.'
                  : publishOutcome?.status === 'active'
                    ? 'Anunțul a fost publicat (activ) pe Autovit.'
                    : 'Anunțul a fost publicat ca draft (neplătit) pe Autovit.'}
              </p>
              {externalUrl && (
                <a
                  href={externalUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-sm text-primary underline"
                >
                  <ExternalLink className="h-3.5 w-3.5" /> Deschide anunțul
                </a>
              )}
            </div>
          )}

          <DialogFooter>
            {step === 'select' && (
              <>
                <Button variant="outline" onClick={() => setOpen(false)}>
                  Anulează
                </Button>
                <Button disabled={!accountId || previewMutation.isPending} onClick={() => previewMutation.mutate()}>
                  {previewMutation.isPending ? (
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  ) : null}
                  Previzualizează
                </Button>
              </>
            )}
            {step === 'missing' && (
              <>
                <Button variant="outline" onClick={() => setStep('select')}>
                  Înapoi
                </Button>
                <Button variant="outline" onClick={() => setOpen(false)}>
                  Închide
                </Button>
              </>
            )}
            {step === 'preview' && (
              <>
                <Button variant="outline" onClick={() => setStep('select')}>
                  Înapoi
                </Button>
                <Button disabled={publishMutation.isPending} onClick={() => publishMutation.mutate()}>
                  {publishMutation.isPending ? (
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  ) : null}
                  Publică (draft)
                </Button>
              </>
            )}
            {step === 'success' && <Button onClick={() => setOpen(false)}>Închide</Button>}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

// ── Listings Tab ──────────────────────────────────────────
function ListingsTab({
  vehicleId,
  listings,
  platforms,
  canEdit,
}: {
  vehicleId: number
  listings: VehicleListing[]
  platforms: PublishingPlatform[]
  canEdit: boolean
}) {
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const selectedCompanyId = useCarParkStore((s) => s.selectedCompanyId)
  // Tenant switcher: acting company (defaults to the current user's own company)
  const effectiveCompanyId = selectedCompanyId ?? user?.company_id ?? null

  const publishMutation = useMutation({
    mutationFn: (platformId: number) => carparkApi.publishVehicle(vehicleId, platformId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'listings', vehicleId] })
      toast.success('Publicat cu succes')
    },
    onError: () => toast.error('Eroare la publicare'),
  })

  const publishAllMutation = useMutation({
    mutationFn: () => carparkApi.publishVehicleAll(vehicleId, undefined, effectiveCompanyId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'listings', vehicleId] })
      toast.success('Publicat pe toate platformele')
    },
    onError: () => toast.error('Eroare la publicare'),
  })

  const activateMutation = useMutation({
    mutationFn: (listingId: number) => carparkApi.activateListing(listingId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'listings', vehicleId] })
      toast.success('Listing activat')
    },
    onError: () => toast.error('Eroare la activare'),
  })

  const deactivateMutation = useMutation({
    mutationFn: (listingId: number) => carparkApi.deactivateListing(listingId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'listings', vehicleId] })
      toast.success('Listing dezactivat')
    },
    onError: () => toast.error('Eroare la dezactivare'),
  })

  const deactivateAllMutation = useMutation({
    mutationFn: () => carparkApi.deactivateAllListings(vehicleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'listings', vehicleId] })
      toast.success('Toate listing-urile dezactivate')
    },
    onError: () => toast.error('Eroare la dezactivare'),
  })

  // Platforms not yet listed
  const listedPlatformIds = new Set(listings.map((l) => l.platform_id))
  const unlistedPlatforms = platforms.filter((p) => !listedPlatformIds.has(p.id))

  // Autovit and Shopify each have their own connector panel above, so we drop their
  // generic rows here — otherwise the vehicle shows up twice per channel. The Shopify
  // store IS autoworld.ro, so the legacy "Website Autoworld" channel points at the
  // same destination and is covered by the Shopify panel too.
  const isDedicatedConnector = (name?: string | null, type?: string | null) => {
    const n = (name ?? '').toLowerCase()
    return (
      type === 'autovit' ||
      n.includes('autovit') ||
      n.includes('shopify') ||
      n.includes('autoworld')
    )
  }
  const otherListings = listings.filter((l) => !isDedicatedConnector(l.platform_name, l.platform_type))
  const otherUnlisted = unlistedPlatforms.filter((p) => !isDedicatedConnector(p.name, p.platform_type))
  const hasOtherChannels = otherListings.length > 0 || otherUnlisted.length > 0

  const statusColors: Record<string, string> = {
    active: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
    draft: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300',
    inactive: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
    expired: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
    error: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  }

  const tileBase = 'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl'

  return (
    <div className="space-y-8">
      {/* ── Publicare directă — real connectors, grouped in one bordered list ── */}
      {canEdit && (
        <section className="space-y-3">
          <div>
            <h3 className="text-base font-semibold tracking-tight">Publicare directă</h3>
            <p className="text-sm text-muted-foreground">
              Sincronizează acest vehicul cu platformele conectate.
            </p>
          </div>

          <div className="divide-y overflow-hidden rounded-xl border bg-card text-card-foreground shadow-sm">
            {/* Autovit */}
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 p-4">
              <div className="flex min-w-0 items-center gap-3">
                <span className={`${tileBase} bg-orange-100 text-orange-600 dark:bg-orange-950/50 dark:text-orange-400`}>
                  <Send className="h-5 w-5" />
                </span>
                <div className="min-w-0">
                  <div className="text-sm font-medium leading-tight">Autovit.ro</div>
                  <p className="text-xs text-muted-foreground">
                    Publicare directă, cu previzualizare înainte de trimitere.
                  </p>
                </div>
              </div>
              <AutovitPublishAction vehicleId={vehicleId} canEdit={canEdit} />
            </div>

            {/* Shopify */}
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 p-4">
              <div className="flex min-w-0 items-center gap-3">
                <span className={`${tileBase} bg-emerald-100 text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-400`}>
                  <ShoppingBag className="h-5 w-5" />
                </span>
                <div className="min-w-0">
                  <div className="text-sm font-medium leading-tight">Shopify</div>
                  <p className="text-xs text-muted-foreground">
                    Publică vehiculul în magazinul online conectat.
                  </p>
                </div>
              </div>
              <div className="flex flex-col items-end gap-2">
                <ShopifyPublishControl vehicleId={vehicleId} canEdit={canEdit} />
                <ListingScheduleSelect vehicleId={vehicleId} platform="shopify" />
              </div>
            </div>
          </div>
        </section>
      )}

      {/* ── Alte canale — manually managed channels without a direct integration ── */}
      {hasOtherChannels ? (
        <section className="space-y-3">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <h3 className="text-base font-semibold tracking-tight">Alte canale</h3>
              <p className="text-sm text-muted-foreground">
                Canale gestionate manual, fără sincronizare automată.
              </p>
            </div>
            {canEdit && (
              <div className="flex items-center gap-2">
                {otherUnlisted.length > 0 && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => publishAllMutation.mutate()}
                    disabled={publishAllMutation.isPending}
                  >
                    <Globe className="mr-1.5 h-3.5 w-3.5" />
                    {publishAllMutation.isPending ? 'Se publică...' : 'Publică pe toate'}
                  </Button>
                )}
                {otherListings.some((l) => l.status === 'active') && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => deactivateAllMutation.mutate()}
                    disabled={deactivateAllMutation.isPending}
                  >
                    <PowerOff className="mr-1.5 h-3.5 w-3.5" />
                    Dezactivează toate
                  </Button>
                )}
              </div>
            )}
          </div>

          <div className="divide-y overflow-hidden rounded-xl border bg-card text-card-foreground shadow-sm">
            {otherListings.map((listing) => (
              <div key={listing.id} className="flex items-center justify-between gap-3 p-4">
                <div className="flex min-w-0 items-center gap-3">
                  <span className={`${tileBase} bg-muted text-muted-foreground`}>
                    <Globe className="h-5 w-5" />
                  </span>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium">{listing.platform_name}</span>
                      <Badge variant="outline" className={`text-[10px] ${statusColors[listing.status] ?? ''}`}>
                        {LISTING_STATUS_LABELS[listing.status as ListingStatus] ?? listing.status}
                      </Badge>
                    </div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1"><Eye className="h-3 w-3" /> {listing.views}</span>
                      <span className="flex items-center gap-1"><MessageSquare className="h-3 w-3" /> {listing.inquiries}</span>
                      {listing.published_at && <span>Publicat: {formatDate(listing.published_at)}</span>}
                      {listing.last_sync && <span>Sync: {formatDate(listing.last_sync)}</span>}
                      {listing.error_message && (
                        <span className="text-red-500">{listing.error_message}</span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  {listing.external_url && (
                    <Button variant="ghost" size="sm" asChild>
                      <a href={listing.external_url} target="_blank" rel="noopener noreferrer">
                        <ExternalLink className="h-4 w-4" />
                      </a>
                    </Button>
                  )}
                  {canEdit && listing.status === 'active' && (
                    <Button variant="ghost" size="sm" onClick={() => deactivateMutation.mutate(listing.id)} title="Dezactivează">
                      <PowerOff className="h-4 w-4" />
                    </Button>
                  )}
                  {canEdit && listing.status !== 'active' && (
                    <Button variant="ghost" size="sm" onClick={() => activateMutation.mutate(listing.id)} title="Activează">
                      <Power className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              </div>
            ))}

            {/* Unlisted manual channels — quick publish */}
            {canEdit && otherUnlisted.map((platform) => (
              <div key={platform.id} className="flex items-center justify-between gap-3 p-4">
                <div className="flex min-w-0 items-center gap-3">
                  <span className={`${tileBase} bg-muted text-muted-foreground`}>
                    <Globe className="h-5 w-5" />
                  </span>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{platform.name}</div>
                    <p className="text-xs text-muted-foreground">Nepublicat</p>
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => publishMutation.mutate(platform.id)}
                  disabled={publishMutation.isPending}
                >
                  <Plus className="mr-1 h-3.5 w-3.5" /> Publică
                </Button>
              </div>
            ))}
          </div>
        </section>
      ) : (
        !canEdit && (
          <EmptyState
            icon={<Globe className="h-8 w-8" />}
            title="Nicio platformă configurată"
            description="Configurează platformele din secțiunea CarPark › Publishing."
          />
        )
      )}
    </div>
  )
}

// ── History Tab ────────────────────────────────────────────
function HistoryTab({ history }: { history: Array<{ id: number; old_status: string | null; new_status: string; notes: string | null; changed_by_name: string | null; created_at: string }> }) {
  if (history.length === 0) {
    return <EmptyState title="Fără istoric de status" icon={<Clock className="h-8 w-8" />} />
  }

  return (
    <div className="space-y-3">
      {history.map((entry) => (
        <Card key={entry.id} className="flex items-start gap-3 p-3">
          <div className="mt-0.5 rounded-full bg-muted p-1.5">
            <Clock className="h-3.5 w-3.5 text-muted-foreground" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 text-sm">
              {entry.old_status && (
                <>
                  <Badge variant="outline" className="text-[11px]">
                    {STATUS_LABELS[entry.old_status as VehicleStatus] ?? entry.old_status}
                  </Badge>
                  <span className="text-muted-foreground">&rarr;</span>
                </>
              )}
              <Badge
                variant="secondary"
                className={`text-[11px] ${STATUS_COLORS[entry.new_status] ?? ''}`}
              >
                {STATUS_LABELS[entry.new_status as VehicleStatus] ?? entry.new_status}
              </Badge>
            </div>
            {entry.notes && (
              <p className="mt-1 text-sm text-muted-foreground">{entry.notes}</p>
            )}
          </div>
          <div className="text-right shrink-0">
            <div className="text-xs text-muted-foreground">{formatDate(entry.created_at)}</div>
            {entry.changed_by_name && (
              <div className="text-xs text-muted-foreground">{entry.changed_by_name}</div>
            )}
          </div>
        </Card>
      ))}
    </div>
  )
}

// ── Modifications Tab ──────────────────────────────────────
// DB column name → Romanian label for the audit log. Unmapped fields fall back
// to humanizeSlug ("Snake Case"), so only the commonly-edited ones are listed.
const MODIFICATION_FIELD_LABELS: Record<string, string> = {
  listing_title: 'Titlu anunț',
  listing_description: 'Descriere anunț',
  equipment_options: 'Dotări',
  equipment: 'Dotări (import)',
  optional_packages: 'Pachete opționale',
  cost_lines: 'Linii de cost',
  pricing_sheets: 'Fișe de preț',
  other_costs: 'Alte costuri',
  transport_cost: 'Cost transport',
  purchase_price_net: 'Preț achiziție (net)',
  acquisition_price: 'Preț achiziție (brut)',
  total_cost: 'Cost total',
  minimum_price: 'Preț minim',
  current_price: 'Preț curent',
  list_price: 'Preț de listă',
  promo_price: 'Preț promoțional',
  sale_price: 'Preț vânzare',
  vat_deductible: 'TVA deductibil',
  status: 'Status',
  state: 'Stare',
  brand: 'Marcă',
  model: 'Model',
  variant: 'Variantă',
  generation: 'Generație',
  equipment_level: 'Nivel echipare',
  vin: 'VIN',
  nr_stoc: 'Nr. stoc',
  registration_number: 'Nr. înmatriculare',
  mileage_km: 'Kilometraj',
  year_of_manufacture: 'An fabricație',
  first_registration_date: 'Primă înmatriculare',
  color_exterior: 'Culoare exterior',
  color_interior: 'Culoare interior',
  fuel_type: 'Combustibil',
  transmission: 'Transmisie',
  drive_type: 'Tracțiune',
  body_type: 'Caroserie',
  engine_power_hp: 'Putere (CP)',
  engine_displacement_cc: 'Capacitate cilindrică',
  location_id: 'Locație',
  notes: 'Note',
  internal_notes: 'Note interne',
}

function modificationFieldLabel(field: string): string {
  return MODIFICATION_FIELD_LABELS[field] ?? humanizeSlug(field)
}

// Structured (JSON/JSONB) columns whose stored value should be summarised rather
// than printed raw. Free-text fields are deliberately excluded so a note that
// happens to start with "[" or "{" is never mistaken for JSON.
const JSON_AUDIT_FIELDS = new Set(['cost_lines', 'pricing_sheets', 'equipment'])

// Pull the quoted tokens out of a stored list repr — handles both the Python
// str() form "['a', 'b']" and JSON '["a","b"]'.
function extractQuotedTokens(raw: string): string[] {
  const out: string[] = []
  const re = /['"]([^'"]+)['"]/g
  let m: RegExpExecArray | null
  while ((m = re.exec(raw)) !== null) out.push(m[1])
  return out
}

// Render a stored audit value for display. old/new are str()-ified in the DB,
// so this unwraps the common shapes instead of dumping raw slugs / JSON blobs.
function formatModificationValue(field: string, raw: string | null): string {
  if (raw == null || raw === '' || raw === 'None' || raw === 'null' || raw === '[]' || raw === '{}') {
    return '—'
  }
  if (field === 'equipment_options' || field === 'optional_packages') {
    const slugs = extractQuotedTokens(raw)
    if (slugs.length) return slugs.map(equipmentLabel).join(', ')
  }
  // Only summarise the known structured (JSON/JSONB) columns — never sniff on a
  // leading "["/"{" for free-text fields (notes, titles…), which could legitimately
  // start that way and would otherwise be dropped to "(modificat)".
  const t = raw.trim()
  if (JSON_AUDIT_FIELDS.has(field) && (t.startsWith('[') || t.startsWith('{'))) {
    try {
      const parsed = JSON.parse(t)
      const list = Array.isArray(parsed) ? parsed : [parsed]
      if (field === 'cost_lines' || field === 'pricing_sheets') {
        const parts = list
          .map((l) => {
            const name = l?.description || l?.type || l?.name
            const eur = l?.eur ?? l?.amount ?? l?.price
            return [name, eur != null ? `${eur} EUR` : null].filter(Boolean).join(' – ')
          })
          .filter(Boolean)
        if (parts.length) return parts.join('; ')
      }
      return list.length === 1 ? '1 intrare' : `${list.length} intrări`
    } catch {
      return '(modificat)' // not valid JSON (e.g. a Python dict repr)
    }
  }
  return raw
}

function ModificationsTab({ modifications }: { modifications: Array<{ id: number; field_name: string; old_value: string | null; new_value: string | null; user_name: string | null; created_at: string }> }) {
  if (modifications.length === 0) {
    return <EmptyState title="Fără istoric de modificări" icon={<FileText className="h-8 w-8" />} />
  }

  return (
    <div className="space-y-2">
      {modifications.map((entry) => (
        <Card key={entry.id} className="flex items-start gap-3 p-3">
          <div className="mt-0.5 rounded-full bg-muted p-1.5">
            <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm">
              <span className="font-medium">{modificationFieldLabel(entry.field_name)}</span>
              {': '}
              <span className="text-muted-foreground line-through">{formatModificationValue(entry.field_name, entry.old_value)}</span>
              {' → '}
              <span>{formatModificationValue(entry.field_name, entry.new_value)}</span>
            </div>
          </div>
          <div className="text-right shrink-0">
            <div className="text-xs text-muted-foreground">{formatDate(entry.created_at)}</div>
            {entry.user_name && (
              <div className="text-xs text-muted-foreground">{entry.user_name}</div>
            )}
          </div>
        </Card>
      ))}
    </div>
  )
}

// ── Profitability Summary ──────────────────────────────────
// The four money cards are computed from the vehicle's FORM MODEL (all in EUR).
// Canonical model: purchase_price_net = NET EUR cost basis (used directly, no
// VAT division); acquisition_price = GROSS EUR actually paid (incl. VAT). In
// MARGIN regime (vat_deductible === false) VAT isn't deductible, so net ==
// gross for that car. Acquisition and the extra cost lines are SEPARATE cards
// (no double-counting):
//   Achiziție      = grossAcqEur (acquisition_price, GROSS EUR paid)
//   Costuri totale = Σ cost_lines.eur (Costuri achiziție) + data.total_costs
//                    (recorded Costuri from carpark_vehicle_costs) — both extra
//                    costs, NOT the buy price
//   Profit/Loss    = total_revenues − netAcqEur (cost basis) − Costuri totale, via the econ engine
// The net/gross/econ-input derivation is a pure, unit-tested helper —
// acquisitionProfitInputs() in profitInputs.ts.
// Revenues stay sourced from the profitability endpoint (data.total_revenues).
function ProfitabilitySummary({ data, vehicle }: { data: Profitability; vehicle: Vehicle }) {
  const currency = 'EUR'
  // Canonical acquisition/cost derivation (net/gross EUR, regime, econ inputs)
  // lives in a pure, unit-tested helper — see profitInputs.ts.
  const { regime, vatRate, grossAcqEur, costLinesEur, landedCostEur, purchaseGrossEur, inputVatEur } =
    acquisitionProfitInputs(vehicle)
  // Recorded operational costs (carpark_vehicle_costs — the "Costuri" tab's
  // Cheltuit / Înregistrează cost), summed by the profitability endpoint as
  // data.total_costs. These are SEPARATE from the acquisition cost_lines
  // (Costuri achiziție), so Costuri totale = BOTH, and both are subtracted in the
  // margin. Taken as EUR to match the exact figure the Costuri tab, dispo and
  // analytics already surface (raw SUM(amount), no FX re-convert — avoids a
  // card-vs-tab mismatch; the module treats these amounts as the base currency).
  const recordedCostsEur = Number(data.total_costs) || 0
  const totalCosts = costLinesEur + recordedCostsEur
  const landedTotalEur = landedCostEur + recordedCostsEur
  const totalRevenues = data.total_revenues
  // Selling price = the active (discounted) price, i.e. promotional_price if set
  // else current_price — the value published to Shopify/Autovit and shown in the
  // list. NOT list_price (the higher catalog "Preț listă"), which left cars with
  // no promo showing an inflated "Preț vânzare" (and skewed the margin).
  const sellPrice = Number(vehicle.promotional_price ?? vehicle.current_price) || 0
  const income = totalRevenues > 0 ? totalRevenues : sellPrice
  // Marjă = VAT-adjusted profit net, via the same engine as the Fișă de preț.
  const engineParams: EngineParams = { regime, vatRate, landedCostEur: landedTotalEur, purchaseGrossEur, inputVatEur }
  const e = income > 0 && landedTotalEur > 0 ? econ(income, engineParams) : null
  const margin = e ? e.profitNet : null
  const marginPct = e ? e.marginNet * 100 : null
  const isProfit = (margin ?? 0) >= 0
  return (
    <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 xl:grid-cols-6">
      <Card className="p-3">
        <div className="text-xs text-muted-foreground mb-1">Preț vânzare</div>
        {sellPrice > 0 ? (
          <CurrencyDisplay value={sellPrice} currency={vehicle.price_currency} className="text-lg font-semibold" />
        ) : (
          <span className="text-lg font-semibold text-muted-foreground">—</span>
        )}
      </Card>
      <Card className="p-3">
        <div className="text-xs text-muted-foreground mb-1">Achiziție</div>
        <CurrencyDisplay value={grossAcqEur} currency={currency} className="text-lg font-semibold" />
      </Card>
      <Card className="p-3">
        <div className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
          <TrendingDown className="h-3 w-3" /> Costuri totale
        </div>
        <CurrencyDisplay value={totalCosts} currency={currency} className="text-lg font-semibold text-red-600 dark:text-red-400" />
      </Card>
      <Card className="p-3">
        <div className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
          <TrendingUp className="h-3 w-3" /> Venituri totale
        </div>
        <CurrencyDisplay value={totalRevenues} currency={currency} className="text-lg font-semibold text-green-600 dark:text-green-400" />
      </Card>
      <Card className={`p-3 ${isProfit ? 'bg-green-50 dark:bg-green-950' : 'bg-red-50 dark:bg-red-950'}`}>
        <div className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
          <DollarSign className="h-3 w-3" /> Marjă netă
        </div>
        {margin != null ? (
          <div className="flex items-baseline gap-2">
            <CurrencyDisplay
              value={margin}
              currency={currency}
              showSign
              className={`text-lg font-bold ${isProfit ? 'text-green-700 dark:text-green-300' : 'text-red-700 dark:text-red-300'}`}
            />
            {marginPct != null && (
              <span className={`text-xs font-medium ${isProfit ? 'text-green-700 dark:text-green-300' : 'text-red-700 dark:text-red-300'}`}>
                {marginPct.toFixed(1)}%
              </span>
            )}
          </div>
        ) : (
          <span className="text-lg font-semibold text-muted-foreground">—</span>
        )}
      </Card>
      <Card className="p-3">
        <div className="text-xs text-muted-foreground mb-1">Zile în stoc</div>
        <span className={`text-lg font-semibold ${vehicle.stationary_days > 90 ? 'text-red-600 dark:text-red-400' : ''}`}>
          {vehicle.stationary_days}
        </span>
      </Card>
    </div>
  )
}

// ── Costs Tab ─────────────────────────────────────────────
// Read-only view of the vehicle's acquisition cost lines (the edit-form model,
// stored in cost_lines JSON) — the same costs that feed the profile's Costuri
// totale / Marjă. Edited from the Comercial tab of the edit form.
function AcqCostLines({ vehicle, canEdit }: { vehicle: Vehicle; canEdit: boolean }) {
  const queryClient = useQueryClient()
  const original = useMemo(
    () => parseCostLines(vehicle.cost_lines).map((l) => ({
      type: String(l.type ?? ''),
      description: String(l.description ?? ''),
      eur: typeof l.eur === 'number' ? l.eur : null,
    })),
    [vehicle.cost_lines],
  )
  const [lines, setLines] = useState(original)
  const total = lines.reduce((s, l) => s + (l.eur ?? 0), 0)
  const dirty = JSON.stringify(lines) !== JSON.stringify(original)
  const saveMut = useMutation({
    mutationFn: () => carparkApi.updateVehicle(vehicle.id, { cost_lines: lines.length ? JSON.stringify(lines) : null } as Partial<Vehicle>),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'vehicle', vehicle.id] })
      toast.success('Costuri salvate')
    },
    onError: () => toast.error('Salvarea costurilor a eșuat'),
  })
  const patch = (i: number, k: 'type' | 'description' | 'eur', v: string | number | null) =>
    setLines((ls) => ls.map((l, idx) => (idx === i ? { ...l, [k]: v } : l)))
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold">Costuri achiziție</h3>
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium tabular-nums">Total: {total.toLocaleString('ro-RO')} EUR</span>
          {canEdit && (
            <>
              <Button variant="ghost" size="sm" onClick={() => setLines((ls) => [...ls, { type: '', description: '', eur: null }])}>+ Adaugă linie</Button>
              <Button size="sm" onClick={() => saveMut.mutate()} disabled={!dirty || saveMut.isPending}>{saveMut.isPending ? 'Se salvează…' : 'Salvează'}</Button>
            </>
          )}
        </div>
      </div>
      {lines.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nicio linie de cost.{canEdit ? ' Apasă „Adaugă linie".' : ''}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground">
                <th className="py-1 pr-3 font-normal">Tip</th>
                <th className="py-1 pr-3 font-normal">Descriere</th>
                <th className="py-1 pr-3 font-normal text-right">EUR (net)</th>
                {canEdit && <th className="w-8" />}
              </tr>
            </thead>
            <tbody>
              {lines.map((l, i) => (
                <tr key={i} className="border-t">
                  {canEdit ? (
                    <>
                      <td className="py-1 pr-3"><Input className="h-8" value={l.type} placeholder="Recondiționare…" onChange={(e) => patch(i, 'type', e.target.value)} /></td>
                      <td className="py-1 pr-3"><Input className="h-8" value={l.description} onChange={(e) => patch(i, 'description', e.target.value)} /></td>
                      <td className="py-1 pr-3 text-right"><Input className="h-8 text-right" type="number" step="10" value={l.eur ?? ''} onChange={(e) => patch(i, 'eur', e.target.value === '' ? null : Number(e.target.value))} /></td>
                      <td className="py-1"><Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setLines((ls) => ls.filter((_, idx) => idx !== i))}><X className="h-4 w-4" /></Button></td>
                    </>
                  ) : (
                    <>
                      <td className="py-1 pr-3">{l.type || '-'}</td>
                      <td className="py-1 pr-3">{l.description || '-'}</td>
                      <td className="py-1 pr-3 text-right tabular-nums">{l.eur != null ? l.eur.toLocaleString('ro-RO') : '-'}</td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

function CostsTab({
  vehicleId, costLines, canEdit, currency,
}: {
  vehicleId: number; costLines: VehicleCostLine[]; canEdit: boolean; currency: string
}) {
  const queryClient = useQueryClient()
  const [expandedLineId, setExpandedLineId] = useState<number | null>(null)

  // Dialogs
  const [showAddLine, setShowAddLine] = useState(false)
  const [addLineForm, setAddLineForm] = useState({ cost_type: 'other' as CostType, description: '', planned_amount: '', currency })
  const [addCostLineId, setAddCostLineId] = useState<number | null>(null)
  const [editCostId, setEditCostId] = useState<number | null>(null)
  const [deleteLineId, setDeleteLineId] = useState<number | null>(null)
  const [deleteCostId, setDeleteCostId] = useState<number | null>(null)
  const [costForm, setCostForm] = useState({ amount: '', description: '', supplier_name: '', invoice_number: '', date: new Date().toISOString().slice(0, 10), vat_rate: '19', vat_amount: '' })
  const [linkInvoiceCostId, setLinkInvoiceCostId] = useState<number | null>(null)
  const [invoiceSearch, setInvoiceSearch] = useState('')
  const [editingPlanned, setEditingPlanned] = useState<{ id: number; draft: string } | null>(null)

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['carpark', 'cost-lines', vehicleId] })
    queryClient.invalidateQueries({ queryKey: ['carpark', 'profitability', vehicleId] })
  }

  // Cost line queries for expanded line
  const { data: lineCostsData } = useQuery({
    queryKey: ['carpark', 'line-costs', expandedLineId],
    queryFn: () => carparkApi.getLineCosts(expandedLineId!),
    enabled: !!expandedLineId,
  })
  const lineCosts = lineCostsData?.costs ?? []

  // Invoice search for link dialog
  const { data: invoiceSearchData } = useQuery({
    queryKey: ['carpark', 'invoice-search', invoiceSearch],
    queryFn: () => carparkApi.searchLinkableEntities('invoice', invoiceSearch),
    enabled: linkInvoiceCostId !== null && invoiceSearch.length >= 1,
  })
  const invoiceResults = invoiceSearchData?.results ?? []

  // Mutations
  const createLineMut = useMutation({
    mutationFn: (data: Record<string, unknown>) => carparkApi.createCostLine(vehicleId, data),
    onSuccess: () => { invalidate(); toast.success('Linie de cost adăugată'); setShowAddLine(false); setAddLineForm({ cost_type: 'other', description: '', planned_amount: '', currency }) },
    onError: () => toast.error('Crearea liniei de cost a eșuat'),
  })

  const deleteLineMut = useMutation({
    mutationFn: (id: number) => carparkApi.deleteCostLine(id),
    onSuccess: () => { invalidate(); toast.success('Linie de cost ștearsă'); setDeleteLineId(null); if (expandedLineId === deleteLineId) setExpandedLineId(null) },
    onError: () => toast.error('Ștergerea liniei de cost a eșuat'),
  })

  const updateLineMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) => carparkApi.updateCostLine(id, data),
    onSuccess: () => { invalidate() },
    onError: () => toast.error('Actualizarea liniei de cost a eșuat'),
  })

  const createCostMut = useMutation({
    mutationFn: ({ lineId, data }: { lineId: number; data: Record<string, unknown> }) => carparkApi.createLineCost(lineId, data),
    onSuccess: () => {
      invalidate()
      queryClient.invalidateQueries({ queryKey: ['carpark', 'line-costs', expandedLineId] })
      toast.success('Cost adăugat')
      setAddCostLineId(null)
      setCostForm({ amount: '', description: '', supplier_name: '', invoice_number: '', date: new Date().toISOString().slice(0, 10), vat_rate: '19', vat_amount: '' })
    },
    onError: () => toast.error('Adăugarea costului a eșuat'),
  })

  const updateCostMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) => carparkApi.updateLineCost(id, data),
    onSuccess: () => {
      invalidate()
      queryClient.invalidateQueries({ queryKey: ['carpark', 'line-costs', expandedLineId] })
      toast.success('Cost actualizat')
      setEditCostId(null)
    },
    onError: () => toast.error('Actualizarea costului a eșuat'),
  })

  const deleteCostMut = useMutation({
    mutationFn: (id: number) => carparkApi.deleteLineCost(id),
    onSuccess: () => {
      invalidate()
      queryClient.invalidateQueries({ queryKey: ['carpark', 'line-costs', expandedLineId] })
      toast.success('Cost șters')
      setDeleteCostId(null)
    },
    onError: () => toast.error('Ștergerea costului a eșuat'),
  })

  const linkInvoiceMut = useMutation({
    mutationFn: ({ costId, invoiceId }: { costId: number; invoiceId: number }) =>
      carparkApi.linkCostInvoice(costId, invoiceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'line-costs', expandedLineId] })
      toast.success('Factură asociată')
      setLinkInvoiceCostId(null)
      setInvoiceSearch('')
    },
    onError: () => toast.error('Asocierea facturii a eșuat'),
  })

  const unlinkInvoiceMut = useMutation({
    mutationFn: (costId: number) => carparkApi.linkCostInvoice(costId, null),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'line-costs', expandedLineId] })
      toast.success('Factură disociată')
    },
  })

  // Summaries
  const totalPlanned = costLines.reduce((s, l) => s + Number(l.planned_amount || 0), 0)
  const totalSpent = costLines.reduce((s, l) => s + Number(l.computed_spent ?? l.spent_amount ?? 0), 0)

  const fmt = (v: number) => new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v)

  const openAddCost = (lineId: number) => {
    setCostForm({ amount: '', description: '', supplier_name: '', invoice_number: '', date: new Date().toISOString().slice(0, 10), vat_rate: '19', vat_amount: '' })
    setEditCostId(null)
    setAddCostLineId(lineId)
  }

  const openEditCost = (c: VehicleCost) => {
    setCostForm({
      amount: String(c.amount),
      description: c.description ?? '',
      supplier_name: c.supplier_name ?? '',
      invoice_number: c.invoice_number ?? '',
      date: c.date,
      vat_rate: String(c.vat_rate ?? 19),
      vat_amount: String(c.vat_amount ?? 0),
    })
    setEditCostId(c.id)
    setAddCostLineId(c.cost_line_id)
  }

  const handleCostSubmit = () => {
    const payload = {
      amount: Number(costForm.amount),
      description: costForm.description || null,
      supplier_name: costForm.supplier_name || null,
      invoice_number: costForm.invoice_number || null,
      date: costForm.date,
      vat_rate: costForm.vat_rate ? Number(costForm.vat_rate) : 19,
      vat_amount: costForm.vat_amount ? Number(costForm.vat_amount) : 0,
    }
    if (editCostId) {
      updateCostMut.mutate({ id: editCostId, data: payload })
    } else if (addCostLineId) {
      createCostMut.mutate({ lineId: addCostLineId, data: payload })
    }
  }

  return (
    <div className="space-y-4">
      {/* Summary Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <span className="text-muted-foreground">
            Planificat: <strong className="text-foreground tabular-nums">{fmt(totalPlanned)} {currency}</strong>
          </span>
          <span className="text-muted-foreground">
            Cheltuit: <strong className="text-foreground tabular-nums">{fmt(totalSpent)} {currency}</strong>
          </span>
          {totalPlanned > 0 && (
            <span className="text-muted-foreground">
              Execuție: <strong className={totalSpent > totalPlanned ? 'text-red-500' : 'text-foreground'}>{Math.round((totalSpent / totalPlanned) * 100)}%</strong>
            </span>
          )}
        </div>
        {canEdit && (
          <Button size="sm" onClick={() => setShowAddLine(true)}>
            <Plus className="h-4 w-4 mr-1" /> Adaugă linie
          </Button>
        )}
      </div>

      {/* Cost Lines Table */}
      {costLines.length === 0 ? (
        <EmptyState title="Nicio linie de cost" icon={<DollarSign className="h-8 w-8" />} />
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/40 text-xs text-muted-foreground">
                <th className="w-8 px-2 py-2"></th>
                <th className="text-left px-3 py-2 font-medium">Tip</th>
                <th className="text-left px-3 py-2 font-medium">Descriere</th>
                <th className="text-right px-3 py-2 font-medium">Planificat</th>
                <th className="text-right px-3 py-2 font-medium">Cheltuit</th>
                <th className="text-left px-3 py-2 font-medium w-32">Execuție</th>
                {canEdit && <th className="px-2 py-2 w-24"></th>}
              </tr>
            </thead>
            <tbody className="divide-y">
              {costLines.map((l) => {
                const planned = Number(l.planned_amount || 0)
                const spent = Number(l.computed_spent ?? l.spent_amount ?? 0)
                const exec = planned > 0 ? Math.round((spent / planned) * 100) : 0
                const isExpanded = expandedLineId === l.id
                return (
                  <>{/* eslint-disable-next-line react/jsx-key */}
                    <tr
                      key={l.id}
                      className="cursor-pointer hover:bg-muted/30 transition-colors"
                      onClick={() => setExpandedLineId(isExpanded ? null : l.id)}
                    >
                      <td className="px-2 py-2 text-center">
                        {isExpanded
                          ? <ChevronDown className="h-4 w-4 text-muted-foreground inline" />
                          : <ChevronRight className="h-4 w-4 text-muted-foreground inline" />}
                      </td>
                      <td className="px-3 py-2">
                        <Badge variant="outline" className="text-[11px]">
                          {COST_TYPE_LABELS[l.cost_type] ?? l.cost_type}
                        </Badge>
                      </td>
                      <td className="px-3 py-2 text-muted-foreground">
                        {l.description || '-'}
                        {(l.cost_count ?? 0) > 0 && (
                          <span className="ml-2 text-[10px] text-muted-foreground/60">({l.cost_count} costuri)</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {editingPlanned?.id === l.id ? (
                          <Input
                            type="number"
                            value={editingPlanned.draft}
                            onChange={(e) => setEditingPlanned({ id: l.id, draft: e.target.value })}
                            onClick={(e) => e.stopPropagation()}
                            onBlur={() => {
                              const n = Number(editingPlanned.draft)
                              if (!isNaN(n) && n !== planned) updateLineMut.mutate({ id: l.id, data: { planned_amount: n } })
                              setEditingPlanned(null)
                            }}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') { const n = Number(editingPlanned.draft); if (!isNaN(n) && n !== planned) updateLineMut.mutate({ id: l.id, data: { planned_amount: n } }); setEditingPlanned(null) }
                              if (e.key === 'Escape') setEditingPlanned(null)
                            }}
                            className="h-7 w-28 text-sm text-right tabular-nums ml-auto"
                            autoFocus
                          />
                        ) : (
                          <span
                            className="cursor-pointer hover:bg-muted/50 rounded px-1 -mx-1"
                            onDoubleClick={(e) => { e.stopPropagation(); setEditingPlanned({ id: l.id, draft: String(planned || '') }) }}
                            title="Dublu-clic pentru editare"
                          >
                            {fmt(planned)}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums font-medium">{fmt(spent)}</td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-2">
                          <div className="w-14 h-1.5 rounded-full bg-muted overflow-hidden">
                            <div
                              className={`h-full rounded-full ${exec > 90 ? 'bg-red-500' : exec > 70 ? 'bg-yellow-500' : 'bg-blue-500'}`}
                              style={{ width: `${Math.min(exec, 100)}%` }}
                            />
                          </div>
                          <span className="text-xs text-muted-foreground tabular-nums">{exec}%</span>
                        </div>
                      </td>
                      {canEdit && (
                        <td className="px-2 py-2 text-right whitespace-nowrap">
                          <Button variant="ghost" size="sm" className="h-7 w-7 p-0" title="Înregistrează cost"
                            onClick={(e) => { e.stopPropagation(); openAddCost(l.id) }}>
                            <DollarSign className="h-3 w-3" />
                          </Button>
                          <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-red-500 hover:text-red-600" title="Șterge linia"
                            onClick={(e) => { e.stopPropagation(); setDeleteLineId(l.id) }}>
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </td>
                      )}
                    </tr>

                    {/* Expanded: costs under this line */}
                    {isExpanded && (
                      <tr key={`${l.id}-expand`} className="bg-muted/20 hover:bg-muted/20">
                        <td colSpan={canEdit ? 7 : 6} className="p-0">
                          <div className="px-6 py-3 space-y-3">
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Costuri</span>
                              {canEdit && (
                                <div className="flex gap-1.5">
                                  <Button variant="outline" size="sm" className="h-7 text-xs"
                                    onClick={(e) => { e.stopPropagation(); openAddCost(l.id) }}>
                                    <DollarSign className="h-3 w-3 mr-1" /> Înregistrează cost
                                  </Button>
                                </div>
                              )}
                            </div>
                            {lineCosts.length === 0 ? (
                              <div className="text-xs text-muted-foreground text-center py-3">Niciun cost înregistrat încă.</div>
                            ) : (
                              <div className="rounded-md border bg-background">
                                <table className="w-full text-xs">
                                  <thead>
                                    <tr className="border-b bg-muted/30 text-muted-foreground">
                                      <th className="text-left px-3 py-1.5 font-medium">Dată</th>
                                      <th className="text-right px-3 py-1.5 font-medium">Sumă</th>
                                      <th className="text-right px-3 py-1.5 font-medium">TVA</th>
                                      <th className="text-left px-3 py-1.5 font-medium">Furnizor</th>
                                      <th className="text-left px-3 py-1.5 font-medium">Factură</th>
                                      <th className="text-left px-3 py-1.5 font-medium">Descriere</th>
                                      {canEdit && <th className="px-2 py-1.5 w-24"></th>}
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y">
                                    {lineCosts.map((c) => (
                                      <tr key={c.id} className="hover:bg-muted/20">
                                        <td className="px-3 py-1.5 tabular-nums">{formatDate(c.date)}</td>
                                        <td className="px-3 py-1.5 text-right tabular-nums font-medium">{fmt(Number(c.amount))}</td>
                                        <td className="px-3 py-1.5 text-right tabular-nums text-muted-foreground">
                                          {Number(c.vat_amount) > 0 ? fmt(Number(c.vat_amount)) : '-'}
                                        </td>
                                        <td className="px-3 py-1.5 text-muted-foreground truncate max-w-[120px]">{c.supplier_name || '-'}</td>
                                        <td className="px-3 py-1.5">
                                          {c.invoice_id ? (
                                            <div className="flex items-center gap-1">
                                              <Badge variant="secondary" className="text-[10px] font-mono">
                                                {c.invoice_number_ref || c.invoice_number || `#${c.invoice_id}`}
                                              </Badge>
                                              {canEdit && (
                                                <Button variant="ghost" size="sm" className="h-5 w-5 p-0 text-muted-foreground hover:text-red-500"
                                                  onClick={(e) => { e.stopPropagation(); unlinkInvoiceMut.mutate(c.id) }}>
                                                  <Unlink className="h-3 w-3" />
                                                </Button>
                                              )}
                                            </div>
                                          ) : c.invoice_number ? (
                                            <span className="font-mono text-muted-foreground">{c.invoice_number}</span>
                                          ) : canEdit ? (
                                            <Button variant="ghost" size="sm" className="h-6 text-[10px] px-2 text-muted-foreground"
                                              onClick={(e) => { e.stopPropagation(); setLinkInvoiceCostId(c.id); setInvoiceSearch('') }}>
                                              <Link2 className="h-3 w-3 mr-1" /> Asociază
                                            </Button>
                                          ) : (
                                            <span className="text-muted-foreground">-</span>
                                          )}
                                        </td>
                                        <td className="px-3 py-1.5 text-muted-foreground truncate max-w-[150px]">{c.description || '-'}</td>
                                        {canEdit && (
                                          <td className="px-2 py-1.5 text-right whitespace-nowrap">
                                            <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={(e) => { e.stopPropagation(); openEditCost(c) }}>
                                              <Pencil className="h-3 w-3" />
                                            </Button>
                                            <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-red-500 hover:text-red-600"
                                              onClick={(e) => { e.stopPropagation(); setDeleteCostId(c.id) }}>
                                              <Trash2 className="h-3 w-3" />
                                            </Button>
                                          </td>
                                        )}
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                )
              })}
            </tbody>
          </table>
        </Card>
      )}

      {/* Add Cost Line Dialog */}
      <Dialog open={showAddLine} onOpenChange={setShowAddLine}>
        <DialogContent className="sm:max-w-md" aria-describedby={undefined}>
          <DialogHeader>
            <DialogTitle>Adaugă linie de cost</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Tip</Label>
                <Select value={addLineForm.cost_type} onValueChange={(v) => setAddLineForm((p) => ({ ...p, cost_type: v as CostType }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(COST_TYPE_LABELS).map(([k, label]) => (
                      <SelectItem key={k} value={k}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Sumă planificată</Label>
                <Input type="number" step="0.01" placeholder="0.00" value={addLineForm.planned_amount}
                  onChange={(e) => setAddLineForm((p) => ({ ...p, planned_amount: e.target.value }))} />
              </div>
            </div>
            <div>
              <Label>Descriere</Label>
              <Input placeholder="ex. Asigurare OMNIASIG, Transport din Germania" value={addLineForm.description}
                onChange={(e) => setAddLineForm((p) => ({ ...p, description: e.target.value }))} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAddLine(false)}>Anulează</Button>
            <Button disabled={createLineMut.isPending} onClick={() => createLineMut.mutate({
              cost_type: addLineForm.cost_type,
              description: addLineForm.description || null,
              planned_amount: addLineForm.planned_amount ? Number(addLineForm.planned_amount) : 0,
              currency: addLineForm.currency,
            })}>
              {createLineMut.isPending ? 'Se creează...' : 'Creează'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add/Edit Cost Dialog */}
      <Dialog open={addCostLineId !== null} onOpenChange={(open) => { if (!open) { setAddCostLineId(null); setEditCostId(null) } }}>
        <DialogContent className="sm:max-w-lg" aria-describedby={undefined}>
          <DialogHeader>
            <DialogTitle>{editCostId ? 'Editează cost' : 'Înregistrează cost'}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Sumă (net) *</Label>
                <Input type="number" step="0.01" placeholder="0.00" value={costForm.amount} autoFocus
                  onChange={(e) => setCostForm((p) => ({ ...p, amount: e.target.value }))} />
              </div>
              <div>
                <Label>Dată *</Label>
                <Input type="date" value={costForm.date}
                  onChange={(e) => setCostForm((p) => ({ ...p, date: e.target.value }))} />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <Label>TVA %</Label>
                <Input type="number" step="0.01" value={costForm.vat_rate}
                  onChange={(e) => setCostForm((p) => ({ ...p, vat_rate: e.target.value }))} />
              </div>
              <div>
                <Label>Valoare TVA</Label>
                <Input type="number" step="0.01" placeholder="0.00" value={costForm.vat_amount}
                  onChange={(e) => setCostForm((p) => ({ ...p, vat_amount: e.target.value }))} />
              </div>
              <div>
                <Label>Nr. factură</Label>
                <Input placeholder="Număr factură" value={costForm.invoice_number}
                  onChange={(e) => setCostForm((p) => ({ ...p, invoice_number: e.target.value }))} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Furnizor</Label>
                <Input placeholder="Nume furnizor" value={costForm.supplier_name}
                  onChange={(e) => setCostForm((p) => ({ ...p, supplier_name: e.target.value }))} />
              </div>
              <div>
                <Label>Descriere</Label>
                <Input placeholder="Descriere opțională" value={costForm.description}
                  onChange={(e) => setCostForm((p) => ({ ...p, description: e.target.value }))} />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setAddCostLineId(null); setEditCostId(null) }}>Anulează</Button>
            <Button disabled={!costForm.amount || Number(costForm.amount) <= 0 || createCostMut.isPending || updateCostMut.isPending}
              onClick={handleCostSubmit}>
              {createCostMut.isPending || updateCostMut.isPending ? 'Se salvează...' : editCostId ? 'Actualizează' : 'Înregistrează'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Link Invoice Dialog */}
      <Dialog open={linkInvoiceCostId !== null} onOpenChange={(open) => { if (!open) { setLinkInvoiceCostId(null); setInvoiceSearch('') } }}>
        <DialogContent className="sm:max-w-lg" aria-describedby={undefined}>
          <DialogHeader>
            <DialogTitle>Asociază factură</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input placeholder="Caută facturi..." className="pl-9" value={invoiceSearch}
                onChange={(e) => setInvoiceSearch(e.target.value)} autoFocus />
            </div>
            {invoiceResults && invoiceResults.length > 0 ? (
              <div className="max-h-60 overflow-y-auto rounded-md border">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b bg-muted/30">
                      <th className="text-left px-3 py-1.5 font-medium">Nr. factură</th>
                      <th className="text-left px-3 py-1.5 font-medium">Furnizor</th>
                      <th className="px-2 py-1.5 w-16"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {invoiceResults.map((inv) => (
                      <tr key={inv.id} className="hover:bg-muted/20">
                        <td className="px-3 py-1.5 font-mono">{inv.label}</td>
                        <td className="px-3 py-1.5 text-muted-foreground">{inv.sublabel || '-'}</td>
                        <td className="px-2 py-1.5 text-right">
                          <Button size="sm" className="h-6 text-[10px] px-2" disabled={linkInvoiceMut.isPending}
                            onClick={() => linkInvoiceCostId && linkInvoiceMut.mutate({ costId: linkInvoiceCostId, invoiceId: inv.id })}>
                            Asociază
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : invoiceSearch.length >= 1 ? (
              <div className="text-xs text-center text-muted-foreground py-4">Nicio factură găsită</div>
            ) : (
              <div className="text-xs text-center text-muted-foreground py-4">Scrie pentru a căuta facturi</div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Cost Line Confirmation */}
      <Dialog open={deleteLineId !== null} onOpenChange={(open) => { if (!open) setDeleteLineId(null) }}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Șterge linia de cost</DialogTitle>
            <DialogDescription>Aceasta va șterge linia de cost și toate intrările sale. Acțiunea nu poate fi anulată.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteLineId(null)}>Anulează</Button>
            <Button variant="destructive" disabled={deleteLineMut.isPending}
              onClick={() => deleteLineId && deleteLineMut.mutate(deleteLineId)}>
              {deleteLineMut.isPending ? 'Se șterge...' : 'Șterge'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Cost Entry Confirmation */}
      <Dialog open={deleteCostId !== null} onOpenChange={(open) => { if (!open) setDeleteCostId(null) }}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Șterge cost</DialogTitle>
            <DialogDescription>Ești sigur? Această acțiune nu poate fi anulată.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteCostId(null)}>Anulează</Button>
            <Button variant="destructive" disabled={deleteCostMut.isPending}
              onClick={() => deleteCostId && deleteCostMut.mutate(deleteCostId)}>
              {deleteCostMut.isPending ? 'Se șterge...' : 'Șterge'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ── Revenues Tab ──────────────────────────────────────────
function RevenuesTab({
  vehicleId, revenues, canEdit, currency,
}: {
  vehicleId: number; revenues: VehicleRevenue[]; canEdit: boolean; currency: string
}) {
  const queryClient = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null)
  const [form, setForm] = useState({
    revenue_type: 'sale' as RevenueType,
    amount: '',
    description: '',
    client_name: '',
    invoice_number: '',
    date: new Date().toISOString().slice(0, 10),
    vat_amount: '',
  })

  const resetForm = () => {
    setForm({
      revenue_type: 'sale', amount: '', description: '', client_name: '',
      invoice_number: '', date: new Date().toISOString().slice(0, 10), vat_amount: '',
    })
    setEditingId(null)
    setDialogOpen(false)
  }

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['carpark', 'revenues', vehicleId] })
    queryClient.invalidateQueries({ queryKey: ['carpark', 'profitability', vehicleId] })
  }

  const createMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => carparkApi.createRevenue(vehicleId, data),
    onSuccess: () => { invalidate(); toast.success('Venit adăugat'); resetForm() },
    onError: () => toast.error('Adăugarea venitului a eșuat'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) =>
      carparkApi.updateRevenue(id, data),
    onSuccess: () => { invalidate(); toast.success('Venit actualizat'); resetForm() },
    onError: () => toast.error('Actualizarea venitului a eșuat'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => carparkApi.deleteRevenue(id),
    onSuccess: () => { invalidate(); toast.success('Venit șters'); setDeleteConfirmId(null) },
    onError: () => toast.error('Ștergerea venitului a eșuat'),
  })

  const handleSubmit = () => {
    const payload = {
      revenue_type: form.revenue_type,
      amount: Number(form.amount),
      description: form.description || null,
      client_name: form.client_name || null,
      invoice_number: form.invoice_number || null,
      date: form.date,
      vat_amount: form.vat_amount ? Number(form.vat_amount) : 0,
    }
    if (editingId) {
      updateMutation.mutate({ id: editingId, data: payload })
    } else {
      createMutation.mutate(payload)
    }
  }

  const startEdit = (r: VehicleRevenue) => {
    setForm({
      revenue_type: r.revenue_type,
      amount: String(r.amount),
      description: r.description ?? '',
      client_name: r.client_name ?? '',
      invoice_number: r.invoice_number ?? '',
      date: r.date,
      vat_amount: String(r.vat_amount ?? 0),
    })
    setEditingId(r.id)
    setDialogOpen(true)
  }

  const totalNet = revenues.reduce((s, r) => s + Number(r.amount), 0)
  const totalVat = revenues.reduce((s, r) => s + Number(r.vat_amount ?? 0), 0)
  const totalGross = totalNet + totalVat

  const byType = useMemo(() => {
    const map: Record<string, number> = {}
    revenues.forEach((r) => {
      const key = r.revenue_type
      map[key] = (map[key] ?? 0) + Number(r.amount)
    })
    return Object.entries(map).sort(([, a], [, b]) => b - a)
  }, [revenues])

  const fmt = (v: number) => new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v)

  return (
    <div className="space-y-4">
      {/* Summary Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <span className="text-muted-foreground">
            Net: <span className="font-semibold text-emerald-600 tabular-nums">{fmt(totalNet)} {currency}</span>
          </span>
          {totalVat > 0 && (
            <span className="text-muted-foreground">
              TVA: <span className="font-medium tabular-nums">{fmt(totalVat)} {currency}</span>
            </span>
          )}
          <span className="text-muted-foreground">
            Total: <span className="font-bold text-emerald-600 tabular-nums">{fmt(totalGross)} {currency}</span>
          </span>
        </div>
        {canEdit && (
          <Button size="sm" onClick={() => { resetForm(); setDialogOpen(true) }}>
            <Plus className="h-4 w-4 mr-1" /> Adaugă venit
          </Button>
        )}
      </div>

      {/* Type Breakdown */}
      {byType.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {byType.map(([type, amount]) => {
            const pct = totalNet > 0 ? Math.round((amount / totalNet) * 100) : 0
            return (
              <div key={type} className="flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs">
                <span className="font-medium">{REVENUE_TYPE_LABELS[type as RevenueType] ?? type}</span>
                <span className="tabular-nums text-muted-foreground">{fmt(amount)}</span>
                <span className="text-[10px] text-muted-foreground">({pct}%)</span>
              </div>
            )
          })}
        </div>
      )}

      {/* Revenues Table */}
      {revenues.length === 0 ? (
        <EmptyState title="Niciun venit înregistrat" icon={<TrendingUp className="h-8 w-8" />} />
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/40 text-xs text-muted-foreground">
                <th className="text-left px-3 py-2 font-medium">Dată</th>
                <th className="text-left px-3 py-2 font-medium">Tip</th>
                <th className="text-left px-3 py-2 font-medium hidden sm:table-cell">Client</th>
                <th className="text-left px-3 py-2 font-medium hidden lg:table-cell">Nr. factură</th>
                <th className="text-left px-3 py-2 font-medium hidden md:table-cell">Descriere</th>
                <th className="text-right px-3 py-2 font-medium">Net</th>
                <th className="text-right px-3 py-2 font-medium hidden sm:table-cell">TVA</th>
                <th className="text-right px-3 py-2 font-medium">Total</th>
                {canEdit && <th className="px-2 py-2 w-20"></th>}
              </tr>
            </thead>
            <tbody className="divide-y">
              {revenues.map((r) => {
                const net = Number(r.amount)
                const vat = Number(r.vat_amount ?? 0)
                return (
                  <tr key={r.id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-3 py-2 tabular-nums text-xs">{formatDate(r.date)}</td>
                    <td className="px-3 py-2">
                      <Badge variant="outline" className="text-[11px]">
                        {REVENUE_TYPE_LABELS[r.revenue_type] ?? r.revenue_type}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 hidden sm:table-cell text-muted-foreground truncate max-w-[140px]">{r.client_name || '-'}</td>
                    <td className="px-3 py-2 hidden lg:table-cell font-mono text-xs text-muted-foreground">{r.invoice_number || '-'}</td>
                    <td className="px-3 py-2 hidden md:table-cell text-muted-foreground truncate max-w-[180px]">{r.description || '-'}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmt(net)}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-muted-foreground hidden sm:table-cell">{vat > 0 ? fmt(vat) : '-'}</td>
                    <td className="px-3 py-2 text-right tabular-nums font-medium">{fmt(net + vat)}</td>
                    {canEdit && (
                      <td className="px-2 py-2 text-right whitespace-nowrap">
                        <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => startEdit(r)}>
                          <Pencil className="h-3 w-3" />
                        </Button>
                        <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-red-500 hover:text-red-600" onClick={() => setDeleteConfirmId(r.id)}>
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
            {revenues.length > 1 && (
              <tfoot>
                <tr className="border-t bg-muted/30 font-medium text-xs">
                  <td className="px-3 py-2" colSpan={5}></td>
                  <td className="px-3 py-2 text-right tabular-nums">{fmt(totalNet)}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-muted-foreground hidden sm:table-cell">{totalVat > 0 ? fmt(totalVat) : '-'}</td>
                  <td className="px-3 py-2 text-right tabular-nums font-bold">{fmt(totalGross)}</td>
                  {canEdit && <td></td>}
                </tr>
              </tfoot>
            )}
          </table>
        </Card>
      )}

      {/* Add/Edit Revenue Dialog */}
      <Dialog open={dialogOpen} onOpenChange={(open) => { if (!open) resetForm() }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{editingId ? 'Editează venit' : 'Adaugă venit'}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Tip</Label>
                <Select value={form.revenue_type} onValueChange={(v) => setForm((p) => ({ ...p, revenue_type: v as RevenueType }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(REVENUE_TYPE_LABELS).map(([k, label]) => (
                      <SelectItem key={k} value={k}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Dată</Label>
                <Input type="date" value={form.date} onChange={(e) => setForm((p) => ({ ...p, date: e.target.value }))} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Sumă (net)</Label>
                <Input type="number" step="0.01" placeholder="0.00" value={form.amount} onChange={(e) => setForm((p) => ({ ...p, amount: e.target.value }))} />
              </div>
              <div>
                <Label>Valoare TVA</Label>
                <Input type="number" step="0.01" placeholder="0.00" value={form.vat_amount} onChange={(e) => setForm((p) => ({ ...p, vat_amount: e.target.value }))} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Client</Label>
                <Input placeholder="Nume client" value={form.client_name} onChange={(e) => setForm((p) => ({ ...p, client_name: e.target.value }))} />
              </div>
              <div>
                <Label>Nr. factură</Label>
                <Input placeholder="Număr factură" value={form.invoice_number} onChange={(e) => setForm((p) => ({ ...p, invoice_number: e.target.value }))} />
              </div>
            </div>
            <div>
              <Label>Descriere</Label>
              <Input placeholder="Descriere opțională" value={form.description} onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={resetForm}>Anulează</Button>
            <Button onClick={handleSubmit} disabled={!form.amount || Number(form.amount) <= 0 || createMutation.isPending || updateMutation.isPending}>
              {createMutation.isPending || updateMutation.isPending ? 'Se salvează...' : editingId ? 'Actualizează' : 'Adaugă'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <Dialog open={deleteConfirmId !== null} onOpenChange={(open) => { if (!open) setDeleteConfirmId(null) }}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Șterge venit</DialogTitle>
            <DialogDescription>Ești sigur? Această acțiune nu poate fi anulată.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirmId(null)}>Anulează</Button>
            <Button variant="destructive" disabled={deleteMutation.isPending} onClick={() => deleteConfirmId && deleteMutation.mutate(deleteConfirmId)}>
              {deleteMutation.isPending ? 'Se șterge...' : 'Șterge'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ── Links Tab ──────────────────────────────────────────────
const ENTITY_TYPES: LinkedEntityType[] = ['invoice', 'dms_document', 'dms_folder', 'project', 'hr_event', 'crm_deal', 'crm_client']

function LinksTab({ vehicleId, links, canEdit }: { vehicleId: number; links: VehicleLink[]; canEdit: boolean }) {
  const queryClient = useQueryClient()
  const [filterType, setFilterType] = useState<LinkedEntityType | ''>('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [selectedEntityType, setSelectedEntityType] = useState<LinkedEntityType>('invoice')
  const [searchQuery, setSearchQuery] = useState('')

  const { data: searchData, isFetching: isSearching } = useQuery({
    queryKey: ['carpark', 'link-search', selectedEntityType, searchQuery],
    queryFn: () => carparkApi.searchLinkableEntities(selectedEntityType, searchQuery),
    enabled: dialogOpen && searchQuery.length > 0,
  })

  const searchResults = searchData?.results ?? []

  const linkMutation = useMutation({
    mutationFn: (data: { entity_type: LinkedEntityType; entity_id: number }) =>
      carparkApi.linkEntity(vehicleId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'vehicle-links', vehicleId] })
      toast.success('Link adaugat')
    },
    onError: () => toast.error('Eroare la adaugarea linkului'),
  })

  const unlinkMutation = useMutation({
    mutationFn: (linkId: number) => carparkApi.unlinkEntity(vehicleId, linkId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'vehicle-links', vehicleId] })
      toast.success('Link sters')
    },
    onError: () => toast.error('Eroare la stergerea linkului'),
  })

  const filtered = filterType ? links.filter((l) => l.linked_entity_type === filterType) : links

  const alreadyLinked = new Set(links.map((l) => `${l.linked_entity_type}:${l.linked_entity_id}`))

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 flex-wrap">
          <Button
            variant={filterType === '' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setFilterType('')}
          >
            Toate ({links.length})
          </Button>
          {ENTITY_TYPES.map((et) => {
            const count = links.filter((l) => l.linked_entity_type === et).length
            if (count === 0) return null
            return (
              <Button
                key={et}
                variant={filterType === et ? 'default' : 'outline'}
                size="sm"
                onClick={() => setFilterType(et)}
              >
                {ENTITY_TYPE_LABELS[et]} ({count})
              </Button>
            )
          })}
        </div>
        {canEdit && (
          <Button size="sm" onClick={() => { setDialogOpen(true); setSearchQuery('') }}>
            <Plus className="mr-1 h-3.5 w-3.5" /> Link
          </Button>
        )}
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          icon={<Link2 className="h-10 w-10" />}
          title="Niciun link"
          description="Leaga facturi, documente, proiecte sau alte entitati de acest vehicul"
        />
      ) : (
        <div className="space-y-2">
          {filtered.map((link) => (
            <Card key={link.id} className="p-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3 min-w-0">
                  <Badge variant="outline" className="text-[10px] shrink-0">
                    {ENTITY_TYPE_LABELS[link.linked_entity_type] ?? link.linked_entity_type}
                  </Badge>
                  <div className="min-w-0">
                    <div className="text-sm font-medium truncate">{link.entity_label}</div>
                    {link.entity_sublabel && (
                      <div className="text-xs text-muted-foreground truncate">{link.entity_sublabel}</div>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-xs text-muted-foreground hidden sm:inline">
                    {link.linked_by_name} - {formatDate(link.created_at)}
                  </span>
                  {canEdit && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 px-2 text-red-500"
                      onClick={() => unlinkMutation.mutate(link.id)}
                    >
                      <Unlink className="h-3 w-3" />
                    </Button>
                  )}
                </div>
              </div>
              {link.notes && (
                <div className="mt-1 text-xs text-muted-foreground">{link.notes}</div>
              )}
            </Card>
          ))}
        </div>
      )}

      {/* Link Entity Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Leaga entitate</DialogTitle>
            <DialogDescription>Cauta si selecteaza o entitate de legat</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Tip entitate</Label>
              <Select value={selectedEntityType} onValueChange={(v) => { setSelectedEntityType(v as LinkedEntityType); setSearchQuery('') }}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {ENTITY_TYPES.map((et) => (
                    <SelectItem key={et} value={et}>{ENTITY_TYPE_LABELS[et]}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Cauta</Label>
              <div className="flex items-center gap-2">
                <Search className="h-4 w-4 text-muted-foreground shrink-0" />
                <Input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder={`Cauta ${ENTITY_TYPE_LABELS[selectedEntityType].toLowerCase()}...`}
                />
              </div>
            </div>
            <div className="max-h-60 overflow-y-auto border rounded-md">
              {isSearching ? (
                <div className="p-4 text-center text-sm text-muted-foreground">Se cauta...</div>
              ) : searchResults.length === 0 ? (
                <div className="p-4 text-center text-sm text-muted-foreground">
                  {searchQuery ? 'Niciun rezultat' : 'Scrie pentru a cauta'}
                </div>
              ) : (
                <div className="divide-y">
                  {searchResults.map((r) => {
                    const isLinked = alreadyLinked.has(`${selectedEntityType}:${r.id}`)
                    return (
                      <button
                        key={r.id}
                        className="w-full text-left px-3 py-2 hover:bg-accent text-sm disabled:opacity-50"
                        disabled={isLinked || linkMutation.isPending}
                        onClick={() => {
                          linkMutation.mutate({ entity_type: selectedEntityType, entity_id: r.id })
                        }}
                      >
                        <div className="font-medium">{r.label}</div>
                        {r.sublabel && <div className="text-xs text-muted-foreground">{r.sublabel}</div>}
                        {isLinked && <span className="text-xs text-muted-foreground italic">Deja legat</span>}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Inchide</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ── Loading Skeleton ───────────────────────────────────────
function DetailSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-6 w-48" />
      </div>
      <div className="flex gap-3">
        <Skeleton className="h-6 w-20" />
        <Skeleton className="h-6 w-16" />
        <Skeleton className="h-6 w-32" />
      </div>
      <div className="grid gap-6 lg:grid-cols-[1fr_400px]">
        <Skeleton className="h-80 rounded-lg" />
        <Skeleton className="h-80 rounded-lg" />
      </div>
    </div>
  )
}
