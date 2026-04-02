import { useState, useMemo } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Pencil,
  Trash2,
  Camera,
  Clock,
  FileText,
  ChevronLeft,
  ChevronRight,
  Car,
  ImageIcon,
  X,
  Plus,
  DollarSign,
  TrendingUp,
  TrendingDown,
} from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { CurrencyDisplay } from '@/components/shared/CurrencyDisplay'
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
import { useAuthStore } from '@/stores/authStore'
import { carparkApi } from '@/api/carpark'
import { toast } from 'sonner'
import {
  STATUS_LABELS,
  CATEGORY_LABELS,
  COST_TYPE_LABELS,
  REVENUE_TYPE_LABELS,
  type Vehicle,
  type VehiclePhoto,
  type VehicleCost,
  type VehicleRevenue,
  type VehicleStatus,
  type CostType,
  type RevenueType,
  type Profitability,
} from '@/types/carpark'

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

// ── Status transitions (which statuses can follow which) ───
const STATUS_TRANSITIONS: Record<string, VehicleStatus[]> = {
  ACQUIRED: ['INSPECTION', 'RECONDITIONING', 'IN_TRANSIT', 'RETURNED', 'SCRAPPED'],
  INSPECTION: ['RECONDITIONING', 'READY_FOR_SALE', 'AT_BODYSHOP', 'RETURNED'],
  RECONDITIONING: ['READY_FOR_SALE', 'AT_BODYSHOP', 'INSURANCE_CLAIM'],
  READY_FOR_SALE: ['LISTED', 'RESERVED', 'PRICE_REDUCED', 'TRANSFERRED'],
  LISTED: ['RESERVED', 'SOLD', 'PRICE_REDUCED', 'AUCTION_CANDIDATE', 'RETURNED'],
  RESERVED: ['SOLD', 'LISTED', 'RETURNED'],
  SOLD: ['DELIVERED', 'RETURNED'],
  DELIVERED: ['RETURNED'],
  PRICE_REDUCED: ['LISTED', 'RESERVED', 'SOLD', 'AUCTION_CANDIDATE'],
  AUCTION_CANDIDATE: ['LISTED', 'SOLD', 'SCRAPPED'],
  IN_TRANSIT: ['ACQUIRED', 'INSPECTION'],
  AT_BODYSHOP: ['RECONDITIONING', 'READY_FOR_SALE'],
  INSURANCE_CLAIM: ['RECONDITIONING', 'SCRAPPED'],
  RETURNED: ['ACQUIRED', 'SCRAPPED'],
  SCRAPPED: [],
  TRANSFERRED: [],
}

// ── Helpers ────────────────────────────────────────────────
function formatDate(d: string | null): string {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('ro-RO')
}

function formatKm(km: number): string {
  return new Intl.NumberFormat('ro-RO').format(km) + ' km'
}

// ── Detail Field ───────────────────────────────────────────
function Field({ label, value, className }: { label: string; value: React.ReactNode; className?: string }) {
  return (
    <div className={className}>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm font-medium">{value ?? '-'}</dd>
    </div>
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

  const { data: costsData } = useQuery({
    queryKey: ['carpark', 'costs', id],
    queryFn: () => carparkApi.getCosts(id),
    enabled: !!id,
  })

  const { data: revenuesData } = useQuery({
    queryKey: ['carpark', 'revenues', id],
    queryFn: () => carparkApi.getRevenues(id),
    enabled: !!id,
  })

  const { data: profitData } = useQuery({
    queryKey: ['carpark', 'profitability', id],
    queryFn: () => carparkApi.getProfitability(id),
    enabled: !!id,
  })

  const vehicle = data?.vehicle
  const history = historyData?.history ?? []
  const modifications = modsData?.modifications ?? []
  const costs = costsData?.costs ?? []
  const revenues = revenuesData?.revenues ?? []

  // Status change dialog
  const [statusDialogOpen, setStatusDialogOpen] = useState(false)
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
      toast.success('Status updated')
      setStatusDialogOpen(false)
      setNewStatus('')
      setStatusNotes('')
    },
    onError: () => toast.error('Failed to update status'),
  })

  const deleteMutation = useMutation({
    mutationFn: () => carparkApi.deleteVehicle(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark'] })
      toast.success('Vehicle deleted')
      navigate('/app/carpark')
    },
    onError: () => toast.error('Failed to delete vehicle'),
  })

  // Available next statuses
  const nextStatuses = useMemo(() => {
    if (!vehicle) return []
    return STATUS_TRANSITIONS[vehicle.status] ?? []
  }, [vehicle])

  if (isLoading) return <DetailSkeleton />
  if (isError || !vehicle) {
    return (
      <EmptyState
        icon={<Car className="h-12 w-12" />}
        title="Vehicle not found"
        action={
          <Button variant="outline" asChild>
            <Link to="/app/carpark">Back to catalog</Link>
          </Button>
        }
      />
    )
  }

  const photos = vehicle.photos ?? []

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        title={`${vehicle.brand} ${vehicle.model}`}
        breadcrumbs={[
          { label: 'CarPark', href: '/app/carpark' },
          { label: `${vehicle.brand} ${vehicle.model}` },
        ]}
        actions={
          <div className="flex items-center gap-2">
            {canEdit && nextStatuses.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setStatusDialogOpen(true)}
              >
                Change Status
              </Button>
            )}
            {canEdit && (
              <Button size="sm" asChild>
                <Link to={`/app/carpark/${id}/edit`}>
                  <Pencil className="mr-1 h-3.5 w-3.5" />
                  Edit
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
                Delete
              </Button>
            )}
          </div>
        }
      />

      {/* Status + Key Info Bar */}
      <div className="flex flex-wrap items-center gap-3">
        <Badge
          variant="secondary"
          className={`text-sm ${STATUS_COLORS[vehicle.status] ?? ''}`}
        >
          {STATUS_LABELS[vehicle.status] ?? vehicle.status}
        </Badge>
        <Badge variant="outline">{CATEGORY_LABELS[vehicle.category] ?? vehicle.category}</Badge>
        {vehicle.nr_stoc && (
          <span className="text-sm text-muted-foreground">#{vehicle.nr_stoc}</span>
        )}
        <span className="text-sm text-muted-foreground">VIN: {vehicle.vin}</span>
      </div>

      {/* Photo Gallery + Info Grid */}
      <div className="grid gap-6 lg:grid-cols-[1fr_400px]">
        {/* Photos */}
        <PhotoGallery photos={photos} onPhotoClick={setLightboxIndex} />

        {/* Quick Info Card */}
        <Card className="p-4 space-y-4 h-fit">
          {vehicle.current_price != null && (
            <div>
              <div className="text-xs text-muted-foreground">Price</div>
              <CurrencyDisplay
                value={vehicle.current_price}
                currency={vehicle.price_currency}
                className="text-2xl font-bold"
              />
              {vehicle.list_price != null && vehicle.list_price !== vehicle.current_price && (
                <div className="text-sm text-muted-foreground line-through">
                  {new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2 }).format(vehicle.list_price)} {vehicle.price_currency}
                </div>
              )}
            </div>
          )}
          <Separator />
          <dl className="grid grid-cols-2 gap-3">
            <Field
              label="Year"
              value={vehicle.year_of_manufacture}
            />
            <Field
              label="Mileage"
              value={vehicle.mileage_km > 0 ? formatKm(vehicle.mileage_km) : '-'}
            />
            <Field label="Fuel" value={vehicle.fuel_type} />
            <Field label="Transmission" value={vehicle.transmission} />
            <Field label="Body" value={vehicle.body_type} />
            <Field label="Power" value={vehicle.engine_power_hp ? `${vehicle.engine_power_hp} HP` : null} />
            <Field label="Color" value={vehicle.color_exterior} />
            <Field label="Doors" value={vehicle.doors} />
          </dl>
          <Separator />
          <dl className="grid grid-cols-2 gap-3">
            <Field label="Acquisition" value={formatDate(vehicle.acquisition_date)} />
            <Field label="Days in Stock" value={
              <span className={vehicle.stationary_days > 90 ? 'text-red-600 font-medium' : ''}>
                {vehicle.stationary_days}
              </span>
            } />
            <Field label="Location" value={vehicle.location_text ?? vehicle.location_name} />
            <Field label="Parking" value={vehicle.parking_spot} />
          </dl>
        </Card>
      </div>

      {/* Tabbed sections */}
      {/* Profitability summary */}
      {profitData && <ProfitabilitySummary data={profitData} currency={vehicle.price_currency || 'RON'} />}

      <Tabs defaultValue="details">
        <TabsList>
          <TabsTrigger value="details">Details</TabsTrigger>
          <TabsTrigger value="pricing">Pricing</TabsTrigger>
          <TabsTrigger value="costs">Costs ({costs.length})</TabsTrigger>
          <TabsTrigger value="revenues">Revenues ({revenues.length})</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
          <TabsTrigger value="modifications">Changes</TabsTrigger>
        </TabsList>

        <TabsContent value="details" className="mt-4">
          <DetailsTab vehicle={vehicle} />
        </TabsContent>

        <TabsContent value="pricing" className="mt-4">
          <PricingTab vehicle={vehicle} />
        </TabsContent>

        <TabsContent value="costs" className="mt-4">
          <CostsTab vehicleId={id} costs={costs} canEdit={canEdit} currency={vehicle.price_currency || 'RON'} />
        </TabsContent>

        <TabsContent value="revenues" className="mt-4">
          <RevenuesTab vehicleId={id} revenues={revenues} canEdit={canEdit} currency={vehicle.price_currency || 'RON'} />
        </TabsContent>

        <TabsContent value="history" className="mt-4">
          <HistoryTab history={history} />
        </TabsContent>

        <TabsContent value="modifications" className="mt-4">
          <ModificationsTab modifications={modifications} />
        </TabsContent>
      </Tabs>

      {/* Status Change Dialog */}
      <Dialog open={statusDialogOpen} onOpenChange={setStatusDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Change Vehicle Status</DialogTitle>
            <DialogDescription>
              Current status: {STATUS_LABELS[vehicle.status]}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <Select value={newStatus} onValueChange={setNewStatus}>
              <SelectTrigger>
                <SelectValue placeholder="Select new status" />
              </SelectTrigger>
              <SelectContent>
                {nextStatuses.map((s) => (
                  <SelectItem key={s} value={s}>
                    {STATUS_LABELS[s] ?? s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Textarea
              placeholder="Notes (optional)"
              value={statusNotes}
              onChange={(e) => setStatusNotes(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setStatusDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={!newStatus || statusMutation.isPending}
              onClick={() => statusMutation.mutate({ status: newStatus, notes: statusNotes || undefined })}
            >
              {statusMutation.isPending ? 'Updating...' : 'Update Status'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Vehicle</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete {vehicle.brand} {vehicle.model} (VIN: {vehicle.vin})?
              This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={deleteMutation.isPending}
              onClick={() => deleteMutation.mutate()}
            >
              {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
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
function PhotoGallery({
  photos,
  onPhotoClick,
}: {
  photos: VehiclePhoto[]
  onPhotoClick: (index: number) => void
}) {
  if (photos.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-dashed bg-muted/30">
        <div className="text-center">
          <Camera className="mx-auto h-8 w-8 text-muted-foreground" />
          <p className="mt-2 text-sm text-muted-foreground">No photos</p>
        </div>
      </div>
    )
  }

  const primary = photos[0]
  const rest = photos.slice(1, 5)

  return (
    <div className="grid gap-2 grid-cols-4 grid-rows-2 h-80">
      {/* Primary large */}
      <div
        className="col-span-2 row-span-2 cursor-pointer overflow-hidden rounded-lg"
        onClick={() => onPhotoClick(0)}
      >
        <img
          src={primary.url}
          alt="Primary"
          className="h-full w-full object-cover hover:scale-105 transition-transform"
        />
      </div>
      {/* Secondary photos */}
      {rest.map((photo, i) => (
        <div
          key={photo.id}
          className="relative cursor-pointer overflow-hidden rounded-lg"
          onClick={() => onPhotoClick(i + 1)}
        >
          <img
            src={photo.thumbnail_url || photo.url}
            alt={`Photo ${i + 2}`}
            className="h-full w-full object-cover hover:scale-105 transition-transform"
          />
          {i === rest.length - 1 && photos.length > 5 && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/50 text-white font-semibold">
              +{photos.length - 5}
            </div>
          )}
        </div>
      ))}
      {/* Placeholder slots */}
      {rest.length < 4 &&
        Array.from({ length: 4 - rest.length }).map((_, i) => (
          <div
            key={`empty-${i}`}
            className="flex items-center justify-center rounded-lg bg-muted"
          >
            <ImageIcon className="h-5 w-5 text-muted-foreground" />
          </div>
        ))}
    </div>
  )
}

// ── Photo Lightbox ─────────────────────────────────────────
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
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/90">
      <button
        onClick={onClose}
        className="absolute right-4 top-4 text-white/80 hover:text-white"
      >
        <X className="h-6 w-6" />
      </button>

      <button
        onClick={() => onNavigate((index - 1 + photos.length) % photos.length)}
        className="absolute left-4 text-white/80 hover:text-white"
      >
        <ChevronLeft className="h-8 w-8" />
      </button>

      <img
        src={photos[index].url}
        alt={`Photo ${index + 1}`}
        className="max-h-[85vh] max-w-[90vw] object-contain"
      />

      <button
        onClick={() => onNavigate((index + 1) % photos.length)}
        className="absolute right-4 text-white/80 hover:text-white"
      >
        <ChevronRight className="h-8 w-8" />
      </button>

      <div className="absolute bottom-4 text-white/70 text-sm">
        {index + 1} / {photos.length}
      </div>
    </div>
  )
}

// ── Details Tab ────────────────────────────────────────────
function DetailsTab({ vehicle: v }: { vehicle: Vehicle }) {
  return (
    <div className="grid gap-6 md:grid-cols-2">
      {/* Identification */}
      <Card className="p-4">
        <h3 className="text-sm font-semibold mb-3">Identification</h3>
        <dl className="grid grid-cols-2 gap-3">
          <Field label="VIN" value={v.vin} />
          <Field label="Stock #" value={v.nr_stoc} />
          <Field label="Registration" value={v.registration_number} />
          <Field label="Chassis Code" value={v.chassis_code} />
          <Field label="Emission Code" value={v.emission_code} />
          <Field label="First Registration" value={formatDate(v.first_registration_date)} />
        </dl>
      </Card>

      {/* Technical */}
      <Card className="p-4">
        <h3 className="text-sm font-semibold mb-3">Technical</h3>
        <dl className="grid grid-cols-2 gap-3">
          <Field label="Engine" value={v.engine_displacement_cc ? `${v.engine_displacement_cc} cc` : null} />
          <Field label="Power" value={v.engine_power_hp ? `${v.engine_power_hp} HP (${v.engine_power_kw} kW)` : null} />
          <Field label="Torque" value={v.engine_torque_nm ? `${v.engine_torque_nm} Nm` : null} />
          <Field label="Drive" value={v.drive_type} />
          <Field label="CO2" value={v.co2_emissions ? `${v.co2_emissions} g/km` : null} />
          <Field label="Euro Standard" value={v.euro_standard} />
          <Field label="Fuel Consumption" value={v.fuel_consumption} />
          <Field label="Seats" value={v.seats} />
        </dl>
      </Card>

      {/* Condition */}
      <Card className="p-4">
        <h3 className="text-sm font-semibold mb-3">Condition & Warranty</h3>
        <dl className="grid grid-cols-2 gap-3">
          <Field label="First Owner" value={v.is_first_owner ? 'Yes' : 'No'} />
          <Field label="Accident History" value={v.has_accident_history ? 'Yes' : 'No'} />
          <Field label="Service Book" value={v.has_service_book ? 'Yes' : 'No'} />
          <Field label="Tuning" value={v.has_tuning ? 'Yes' : 'No'} />
          <Field label="Manufacturer Warranty" value={v.has_manufacturer_warranty ? `Yes (until ${formatDate(v.manufacturer_warranty_date)})` : 'No'} />
          <Field label="Dealer Warranty" value={v.has_dealer_warranty ? `${v.dealer_warranty_months} months` : 'No'} />
        </dl>
      </Card>

      {/* Source & Acquisition */}
      <Card className="p-4">
        <h3 className="text-sm font-semibold mb-3">Source & Acquisition</h3>
        <dl className="grid grid-cols-2 gap-3">
          <Field label="Source" value={v.source} />
          <Field label="Supplier" value={v.supplier_name} />
          <Field label="Supplier CIF" value={v.supplier_cif} />
          <Field label="Contract #" value={v.purchase_contract_number} />
          <Field label="Contract Date" value={formatDate(v.purchase_contract_date)} />
          <Field label="Owner" value={v.owner_name} />
        </dl>
      </Card>

      {/* Equipment */}
      {v.equipment && Object.keys(v.equipment).length > 0 && (
        <Card className="p-4 md:col-span-2">
          <h3 className="text-sm font-semibold mb-3">Equipment</h3>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {Object.entries(v.equipment).map(([category, items]) => (
              <div key={category}>
                <h4 className="text-xs font-medium text-muted-foreground mb-1">{category}</h4>
                <ul className="space-y-0.5">
                  {items.map((item, i) => (
                    <li key={i} className="text-sm">{item}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Notes */}
      {(v.notes || v.internal_notes) && (
        <Card className="p-4 md:col-span-2">
          <h3 className="text-sm font-semibold mb-3">Notes</h3>
          {v.notes && (
            <div className="mb-3">
              <div className="text-xs text-muted-foreground mb-1">Public Notes</div>
              <p className="text-sm whitespace-pre-wrap">{v.notes}</p>
            </div>
          )}
          {v.internal_notes && (
            <div>
              <div className="text-xs text-muted-foreground mb-1">Internal Notes</div>
              <p className="text-sm whitespace-pre-wrap">{v.internal_notes}</p>
            </div>
          )}
        </Card>
      )}
    </div>
  )
}

// ── Pricing Tab ────────────────────────────────────────────
function PricingTab({ vehicle: v }: { vehicle: Vehicle }) {
  return (
    <div className="grid gap-6 md:grid-cols-2">
      <Card className="p-4">
        <h3 className="text-sm font-semibold mb-3">Sale Pricing</h3>
        <dl className="grid grid-cols-2 gap-3">
          <Field label="Current Price" value={v.current_price != null ? <CurrencyDisplay value={v.current_price} currency={v.price_currency} /> : null} />
          <Field label="List Price" value={v.list_price != null ? <CurrencyDisplay value={v.list_price} currency={v.price_currency} /> : null} />
          <Field label="Promotional Price" value={v.promotional_price != null ? <CurrencyDisplay value={v.promotional_price} currency={v.price_currency} /> : null} />
          <Field label="Minimum Price" value={v.minimum_price != null ? <CurrencyDisplay value={v.minimum_price} currency={v.price_currency} /> : null} />
          <Field label="VAT Included" value={v.price_includes_vat ? 'Yes' : 'No'} />
          <Field label="Negotiable" value={v.is_negotiable ? 'Yes' : 'No'} />
          <Field label="Margin Scheme" value={v.margin_scheme ? 'Yes' : 'No'} />
          <Field label="Financing" value={v.eligible_for_financing ? 'Yes' : 'No'} />
        </dl>
      </Card>

      <Card className="p-4">
        <h3 className="text-sm font-semibold mb-3">Acquisition Costs</h3>
        <dl className="grid grid-cols-2 gap-3">
          <Field label="Purchase Price" value={v.purchase_price_net != null ? <CurrencyDisplay value={v.purchase_price_net} currency={v.purchase_price_currency} /> : null} />
          <Field label="Acquisition Value" value={v.acquisition_value != null ? <CurrencyDisplay value={v.acquisition_value} currency={v.acquisition_currency} /> : null} />
          <Field label="VAT" value={v.acquisition_vat != null ? <CurrencyDisplay value={v.acquisition_vat} currency={v.acquisition_currency} /> : null} />
          <Field label="Reconditioning" value={v.reconditioning_cost != null ? <CurrencyDisplay value={v.reconditioning_cost} currency={v.price_currency} /> : null} />
          <Field label="Transport" value={v.transport_cost != null ? <CurrencyDisplay value={v.transport_cost} currency={v.price_currency} /> : null} />
          <Field label="Registration" value={v.registration_cost != null ? <CurrencyDisplay value={v.registration_cost} currency={v.price_currency} /> : null} />
          <Field label="Other Costs" value={v.other_costs != null ? <CurrencyDisplay value={v.other_costs} currency={v.price_currency} /> : null} />
          <Field label="Total Cost" value={v.total_cost != null ? <CurrencyDisplay value={v.total_cost} currency={v.price_currency} className="font-bold" /> : null} />
        </dl>
      </Card>

      {v.sale_price != null && (
        <Card className="p-4 md:col-span-2">
          <h3 className="text-sm font-semibold mb-3">Sale Info</h3>
          <dl className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Field label="Sale Price" value={<CurrencyDisplay value={v.sale_price} currency={v.price_currency} />} />
            <Field label="Sale Date" value={formatDate(v.sale_date)} />
            <Field label="Gross Margin" value={
              v.total_cost != null ? (
                <CurrencyDisplay value={v.sale_price - v.total_cost} currency={v.price_currency} showSign />
              ) : '-'
            } />
          </dl>
        </Card>
      )}
    </div>
  )
}

// ── History Tab ────────────────────────────────────────────
function HistoryTab({ history }: { history: Array<{ id: number; old_status: string | null; new_status: string; notes: string | null; changed_by_name: string | null; created_at: string }> }) {
  if (history.length === 0) {
    return <EmptyState title="No status history" icon={<Clock className="h-8 w-8" />} />
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
function ModificationsTab({ modifications }: { modifications: Array<{ id: number; field_name: string; old_value: string | null; new_value: string | null; user_name: string | null; created_at: string }> }) {
  if (modifications.length === 0) {
    return <EmptyState title="No modification history" icon={<FileText className="h-8 w-8" />} />
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
              <span className="font-medium">{entry.field_name}</span>
              {': '}
              <span className="text-muted-foreground line-through">{entry.old_value ?? 'null'}</span>
              {' → '}
              <span>{entry.new_value ?? 'null'}</span>
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
function ProfitabilitySummary({ data, currency }: { data: Profitability; currency: string }) {
  const isProfit = data.profit >= 0
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Card className="p-3">
        <div className="text-xs text-muted-foreground mb-1">Acquisition</div>
        <CurrencyDisplay value={data.acquisition_price} currency={currency} className="text-lg font-semibold" />
      </Card>
      <Card className="p-3">
        <div className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
          <TrendingDown className="h-3 w-3" /> Total Costs
        </div>
        <CurrencyDisplay value={data.total_costs} currency={currency} className="text-lg font-semibold text-red-600 dark:text-red-400" />
      </Card>
      <Card className="p-3">
        <div className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
          <TrendingUp className="h-3 w-3" /> Total Revenue
        </div>
        <CurrencyDisplay value={data.total_revenues} currency={currency} className="text-lg font-semibold text-green-600 dark:text-green-400" />
      </Card>
      <Card className={`p-3 ${isProfit ? 'bg-green-50 dark:bg-green-950' : 'bg-red-50 dark:bg-red-950'}`}>
        <div className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
          <DollarSign className="h-3 w-3" /> Profit / Loss
        </div>
        <CurrencyDisplay
          value={data.profit}
          currency={currency}
          showSign
          className={`text-lg font-bold ${isProfit ? 'text-green-700 dark:text-green-300' : 'text-red-700 dark:text-red-300'}`}
        />
      </Card>
    </div>
  )
}

// ── Costs Tab ─────────────────────────────────────────────
function CostsTab({
  vehicleId, costs, canEdit, currency,
}: {
  vehicleId: number; costs: VehicleCost[]; canEdit: boolean; currency: string
}) {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState({
    cost_type: 'other' as CostType,
    amount: '',
    description: '',
    supplier_name: '',
    invoice_number: '',
    date: new Date().toISOString().slice(0, 10),
    vat_rate: '19',
    vat_amount: '',
  })

  const resetForm = () => {
    setForm({
      cost_type: 'other', amount: '', description: '', supplier_name: '',
      invoice_number: '', date: new Date().toISOString().slice(0, 10),
      vat_rate: '19', vat_amount: '',
    })
    setEditingId(null)
    setShowForm(false)
  }

  const createMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => carparkApi.createCost(vehicleId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'costs', vehicleId] })
      queryClient.invalidateQueries({ queryKey: ['carpark', 'profitability', vehicleId] })
      toast.success('Cost added')
      resetForm()
    },
    onError: () => toast.error('Failed to add cost'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) =>
      carparkApi.updateCost(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'costs', vehicleId] })
      queryClient.invalidateQueries({ queryKey: ['carpark', 'profitability', vehicleId] })
      toast.success('Cost updated')
      resetForm()
    },
    onError: () => toast.error('Failed to update cost'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => carparkApi.deleteCost(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'costs', vehicleId] })
      queryClient.invalidateQueries({ queryKey: ['carpark', 'profitability', vehicleId] })
      toast.success('Cost deleted')
    },
    onError: () => toast.error('Failed to delete cost'),
  })

  const handleSubmit = () => {
    const payload = {
      cost_type: form.cost_type,
      amount: Number(form.amount),
      description: form.description || null,
      supplier_name: form.supplier_name || null,
      invoice_number: form.invoice_number || null,
      date: form.date,
      vat_rate: form.vat_rate ? Number(form.vat_rate) : 19,
      vat_amount: form.vat_amount ? Number(form.vat_amount) : 0,
    }
    if (editingId) {
      updateMutation.mutate({ id: editingId, data: payload })
    } else {
      createMutation.mutate(payload)
    }
  }

  const startEdit = (c: VehicleCost) => {
    setForm({
      cost_type: c.cost_type,
      amount: String(c.amount),
      description: c.description ?? '',
      supplier_name: c.supplier_name ?? '',
      invoice_number: c.invoice_number ?? '',
      date: c.date,
      vat_rate: String(c.vat_rate ?? 19),
      vat_amount: String(c.vat_amount ?? 0),
    })
    setEditingId(c.id)
    setShowForm(true)
  }

  const totalCosts = costs.reduce((s, c) => s + Number(c.amount), 0)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-sm text-muted-foreground">
          Total: <CurrencyDisplay value={totalCosts} currency={currency} className="font-semibold text-foreground" />
        </div>
        {canEdit && (
          <Button size="sm" variant="outline" onClick={() => { resetForm(); setShowForm(!showForm) }}>
            <Plus className="h-4 w-4 mr-1" /> Add Cost
          </Button>
        )}
      </div>

      {showForm && (
        <Card className="p-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <Label>Type</Label>
              <Select value={form.cost_type} onValueChange={(v) => setForm((p) => ({ ...p, cost_type: v as CostType }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(COST_TYPE_LABELS).map(([k, label]) => (
                    <SelectItem key={k} value={k}>{label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Amount</Label>
              <Input type="number" step="0.01" value={form.amount} onChange={(e) => setForm((p) => ({ ...p, amount: e.target.value }))} />
            </div>
            <div>
              <Label>VAT Rate %</Label>
              <Input type="number" step="0.01" value={form.vat_rate} onChange={(e) => setForm((p) => ({ ...p, vat_rate: e.target.value }))} />
            </div>
            <div>
              <Label>VAT Amount</Label>
              <Input type="number" step="0.01" value={form.vat_amount} onChange={(e) => setForm((p) => ({ ...p, vat_amount: e.target.value }))} />
            </div>
            <div>
              <Label>Date</Label>
              <Input type="date" value={form.date} onChange={(e) => setForm((p) => ({ ...p, date: e.target.value }))} />
            </div>
            <div>
              <Label>Supplier</Label>
              <Input value={form.supplier_name} onChange={(e) => setForm((p) => ({ ...p, supplier_name: e.target.value }))} />
            </div>
            <div>
              <Label>Invoice #</Label>
              <Input value={form.invoice_number} onChange={(e) => setForm((p) => ({ ...p, invoice_number: e.target.value }))} />
            </div>
            <div>
              <Label>Description</Label>
              <Input value={form.description} onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))} />
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <Button variant="ghost" size="sm" onClick={resetForm}>Cancel</Button>
            <Button size="sm" onClick={handleSubmit} disabled={!form.amount || Number(form.amount) <= 0}>
              {editingId ? 'Update' : 'Add'}
            </Button>
          </div>
        </Card>
      )}

      {costs.length === 0 ? (
        <EmptyState title="No costs recorded" icon={<DollarSign className="h-8 w-8" />} />
      ) : (
        <div className="border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="text-left p-2 font-medium">Date</th>
                <th className="text-left p-2 font-medium">Type</th>
                <th className="text-left p-2 font-medium hidden sm:table-cell">Supplier</th>
                <th className="text-left p-2 font-medium hidden md:table-cell">Description</th>
                <th className="text-right p-2 font-medium">Amount</th>
                {canEdit && <th className="p-2 w-20"></th>}
              </tr>
            </thead>
            <tbody className="divide-y">
              {costs.map((c) => (
                <tr key={c.id} className="hover:bg-muted/30">
                  <td className="p-2">{formatDate(c.date)}</td>
                  <td className="p-2">
                    <Badge variant="outline" className="text-[11px]">
                      {COST_TYPE_LABELS[c.cost_type] ?? c.cost_type}
                    </Badge>
                  </td>
                  <td className="p-2 hidden sm:table-cell text-muted-foreground">{c.supplier_name ?? '-'}</td>
                  <td className="p-2 hidden md:table-cell text-muted-foreground truncate max-w-[200px]">{c.description ?? '-'}</td>
                  <td className="p-2 text-right">
                    <CurrencyDisplay value={c.amount} currency={c.currency} />
                  </td>
                  {canEdit && (
                    <td className="p-2 text-right">
                      <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => startEdit(c)}>
                        <Pencil className="h-3 w-3" />
                      </Button>
                      <Button variant="ghost" size="sm" className="h-7 px-2 text-red-500" onClick={() => deleteMutation.mutate(c.id)}>
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
  )
}

// ── Revenues Tab ──────────────────────────────────────────
function RevenuesTab({
  vehicleId, revenues, canEdit, currency,
}: {
  vehicleId: number; revenues: VehicleRevenue[]; canEdit: boolean; currency: string
}) {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
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
    setShowForm(false)
  }

  const createMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => carparkApi.createRevenue(vehicleId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'revenues', vehicleId] })
      queryClient.invalidateQueries({ queryKey: ['carpark', 'profitability', vehicleId] })
      toast.success('Revenue added')
      resetForm()
    },
    onError: () => toast.error('Failed to add revenue'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) =>
      carparkApi.updateRevenue(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'revenues', vehicleId] })
      queryClient.invalidateQueries({ queryKey: ['carpark', 'profitability', vehicleId] })
      toast.success('Revenue updated')
      resetForm()
    },
    onError: () => toast.error('Failed to update revenue'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => carparkApi.deleteRevenue(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'revenues', vehicleId] })
      queryClient.invalidateQueries({ queryKey: ['carpark', 'profitability', vehicleId] })
      toast.success('Revenue deleted')
    },
    onError: () => toast.error('Failed to delete revenue'),
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
    setShowForm(true)
  }

  const totalRevenues = revenues.reduce((s, r) => s + Number(r.amount), 0)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-sm text-muted-foreground">
          Total: <CurrencyDisplay value={totalRevenues} currency={currency} className="font-semibold text-foreground" />
        </div>
        {canEdit && (
          <Button size="sm" variant="outline" onClick={() => { resetForm(); setShowForm(!showForm) }}>
            <Plus className="h-4 w-4 mr-1" /> Add Revenue
          </Button>
        )}
      </div>

      {showForm && (
        <Card className="p-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <Label>Type</Label>
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
              <Label>Amount</Label>
              <Input type="number" step="0.01" value={form.amount} onChange={(e) => setForm((p) => ({ ...p, amount: e.target.value }))} />
            </div>
            <div>
              <Label>VAT Amount</Label>
              <Input type="number" step="0.01" value={form.vat_amount} onChange={(e) => setForm((p) => ({ ...p, vat_amount: e.target.value }))} />
            </div>
            <div>
              <Label>Date</Label>
              <Input type="date" value={form.date} onChange={(e) => setForm((p) => ({ ...p, date: e.target.value }))} />
            </div>
            <div>
              <Label>Client</Label>
              <Input value={form.client_name} onChange={(e) => setForm((p) => ({ ...p, client_name: e.target.value }))} />
            </div>
            <div>
              <Label>Invoice #</Label>
              <Input value={form.invoice_number} onChange={(e) => setForm((p) => ({ ...p, invoice_number: e.target.value }))} />
            </div>
            <div className="sm:col-span-2">
              <Label>Description</Label>
              <Input value={form.description} onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))} />
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <Button variant="ghost" size="sm" onClick={resetForm}>Cancel</Button>
            <Button size="sm" onClick={handleSubmit} disabled={!form.amount || Number(form.amount) <= 0}>
              {editingId ? 'Update' : 'Add'}
            </Button>
          </div>
        </Card>
      )}

      {revenues.length === 0 ? (
        <EmptyState title="No revenues recorded" icon={<DollarSign className="h-8 w-8" />} />
      ) : (
        <div className="border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="text-left p-2 font-medium">Date</th>
                <th className="text-left p-2 font-medium">Type</th>
                <th className="text-left p-2 font-medium hidden sm:table-cell">Client</th>
                <th className="text-left p-2 font-medium hidden md:table-cell">Description</th>
                <th className="text-right p-2 font-medium">Amount</th>
                {canEdit && <th className="p-2 w-20"></th>}
              </tr>
            </thead>
            <tbody className="divide-y">
              {revenues.map((r) => (
                <tr key={r.id} className="hover:bg-muted/30">
                  <td className="p-2">{formatDate(r.date)}</td>
                  <td className="p-2">
                    <Badge variant="outline" className="text-[11px]">
                      {REVENUE_TYPE_LABELS[r.revenue_type] ?? r.revenue_type}
                    </Badge>
                  </td>
                  <td className="p-2 hidden sm:table-cell text-muted-foreground">{r.client_name ?? '-'}</td>
                  <td className="p-2 hidden md:table-cell text-muted-foreground truncate max-w-[200px]">{r.description ?? '-'}</td>
                  <td className="p-2 text-right">
                    <CurrencyDisplay value={r.amount} currency={r.currency} />
                  </td>
                  {canEdit && (
                    <td className="p-2 text-right">
                      <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => startEdit(r)}>
                        <Pencil className="h-3 w-3" />
                      </Button>
                      <Button variant="ghost" size="sm" className="h-7 px-2 text-red-500" onClick={() => deleteMutation.mutate(r.id)}>
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
