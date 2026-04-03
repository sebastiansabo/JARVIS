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
  ChevronDown,
  ChevronRight,
  Car,
  ImageIcon,
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
  type FloorPrice,
  type Promotion,
  type PublishingPlatform,
  type VehicleLink,
  type LinkedEntityType,
  ENTITY_TYPE_LABELS,
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

  const { data: costLinesData } = useQuery({
    queryKey: ['carpark', 'cost-lines', id],
    queryFn: () => carparkApi.getCostLines(id),
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

  const { data: pricingHistoryData } = useQuery({
    queryKey: ['carpark', 'pricing-history', id],
    queryFn: () => carparkApi.getPricingHistory(id),
    enabled: !!id,
  })

  const { data: floorPriceData } = useQuery({
    queryKey: ['carpark', 'floor-price', id],
    queryFn: () => carparkApi.getFloorPrice(id),
    enabled: !!id,
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

      {/* Profitability summary */}
      {profitData && <ProfitabilitySummary data={profitData} currency={vehicle.price_currency || 'RON'} />}

      <Tabs defaultValue="details">
        <TabsList>
          <TabsTrigger value="details">Detalii</TabsTrigger>
          <TabsTrigger value="pricing">Pricing</TabsTrigger>
          <TabsTrigger value="costs">Costs ({costLines.length})</TabsTrigger>
          <TabsTrigger value="revenues">Revenues ({revenues.length})</TabsTrigger>
          <TabsTrigger value="listings">Listings ({listings.length})</TabsTrigger>
          <TabsTrigger value="links">Links ({vehicleLinks.length})</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
          <TabsTrigger value="modifications">Changes</TabsTrigger>
        </TabsList>

        <TabsContent value="details" className="mt-4">
          <DetailsTab vehicle={vehicle} photos={photos} onPhotoClick={setLightboxIndex} />
        </TabsContent>

        <TabsContent value="pricing" className="mt-4">
          <PricingTab
            vehicle={vehicle}
            pricingHistory={pricingHistory}
            floorPrice={floorPriceData ?? null}
            promotions={vehiclePromos}
          />
        </TabsContent>

        <TabsContent value="costs" className="mt-4">
          <CostsTab vehicleId={id} costLines={costLines} canEdit={canEdit} currency={vehicle.price_currency || 'EUR'} />
        </TabsContent>

        <TabsContent value="revenues" className="mt-4">
          <RevenuesTab vehicleId={id} revenues={revenues} canEdit={canEdit} currency={vehicle.price_currency || 'RON'} />
        </TabsContent>

        <TabsContent value="listings" className="mt-4">
          <ListingsTab vehicleId={id} listings={listings} platforms={platforms} canEdit={canEdit} />
        </TabsContent>

        <TabsContent value="links" className="mt-4">
          <LinksTab vehicleId={id} links={vehicleLinks} canEdit={canEdit} />
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
function DetailsTab({ vehicle: v, photos, onPhotoClick }: { vehicle: Vehicle; photos: VehiclePhoto[]; onPhotoClick: (index: number) => void }) {
  return (
    <div className="space-y-6">
      {/* Photo Gallery + Quick Info */}
      <div className="grid gap-6 lg:grid-cols-[1fr_400px]">
        <PhotoGallery photos={photos} onPhotoClick={onPhotoClick} />

        <Card className="p-4 space-y-4 h-fit">
          {v.current_price != null && (
            <div>
              <div className="text-xs text-muted-foreground">Price</div>
              <CurrencyDisplay
                value={v.current_price}
                currency={v.price_currency}
                className="text-2xl font-bold"
              />
              {v.list_price != null && v.list_price !== v.current_price && (
                <div className="text-sm text-muted-foreground line-through">
                  {new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2 }).format(v.list_price)} {v.price_currency}
                </div>
              )}
            </div>
          )}
          <Separator />
          <dl className="grid grid-cols-2 gap-3">
            <Field label="Year" value={v.year_of_manufacture} />
            <Field label="Mileage" value={v.mileage_km > 0 ? formatKm(v.mileage_km) : '-'} />
            <Field label="Fuel" value={v.fuel_type} />
            <Field label="Transmission" value={v.transmission} />
            <Field label="Body" value={v.body_type} />
            <Field label="Power" value={v.engine_power_hp ? `${v.engine_power_hp} HP` : null} />
            <Field label="Color" value={v.color_exterior} />
            <Field label="Doors" value={v.doors} />
          </dl>
          <Separator />
          <dl className="grid grid-cols-2 gap-3">
            <Field label="Acquisition" value={formatDate(v.acquisition_date)} />
            <Field label="Days in Stock" value={
              <span className={v.stationary_days > 90 ? 'text-red-600 font-medium' : ''}>
                {v.stationary_days}
              </span>
            } />
            <Field label="Location" value={v.location_text ?? v.location_name} />
            <Field label="Parking" value={v.parking_spot} />
          </dl>
        </Card>
      </div>

      {/* Detail cards */}
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
    </div>
  )
}

// ── Pricing Tab ────────────────────────────────────────────
function PricingTab({
  vehicle: v,
  pricingHistory,
  floorPrice,
  promotions,
}: {
  vehicle: Vehicle
  pricingHistory: PricingHistoryEntry[]
  floorPrice: FloorPrice | null
  promotions: Promotion[]
}) {
  return (
    <div className="space-y-6">
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

      {/* Floor Price */}
      {floorPrice && floorPrice.floor_price > 0 && (
        <Card className="p-4">
          <h3 className="text-sm font-semibold mb-3">Floor Price Analysis</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-xs text-muted-foreground">Floor Price</div>
              <div className="text-lg font-bold">
                <CurrencyDisplay value={floorPrice.floor_price} currency={v.price_currency} />
              </div>
              <Badge variant="outline" className="mt-1 text-[10px]">
                {floorPrice.binding_constraint === 'minimum_price' ? 'Preț minim' :
                 floorPrice.binding_constraint === 'cost_plus_margin' ? 'Cost + marjă' : 'Recuperare achiziție'}
              </Badge>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Min. Price Set</div>
              <div className="text-sm font-medium">
                <CurrencyDisplay value={floorPrice.components.minimum_price} currency={v.price_currency} />
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Cost + {floorPrice.components.min_margin_percent}% Margin</div>
              <div className="text-sm font-medium">
                <CurrencyDisplay value={floorPrice.components.cost_plus_margin} currency={v.price_currency} />
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Purchase Recovery</div>
              <div className="text-sm font-medium">
                <CurrencyDisplay value={floorPrice.components.purchase_recovery} currency={v.price_currency} />
              </div>
            </div>
          </div>
          {v.current_price != null && v.current_price < floorPrice.floor_price && (
            <div className="mt-3 flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
              <TrendingDown className="h-4 w-4" />
              Current price is below the calculated floor price
            </div>
          )}
        </Card>
      )}

      {/* Active Promotions */}
      {promotions.length > 0 && (
        <Card className="p-4">
          <h3 className="text-sm font-semibold mb-3">Active Promotions</h3>
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
        </Card>
      )}

      {/* Pricing History */}
      {pricingHistory.length > 0 && (
        <Card className="p-4">
          <h3 className="text-sm font-semibold mb-3">Pricing History</h3>
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

  const publishMutation = useMutation({
    mutationFn: (platformId: number) => carparkApi.publishVehicle(vehicleId, platformId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'listings', vehicleId] })
      toast.success('Publicat cu succes')
    },
    onError: () => toast.error('Eroare la publicare'),
  })

  const publishAllMutation = useMutation({
    mutationFn: () => carparkApi.publishVehicleAll(vehicleId),
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

  const statusColors: Record<string, string> = {
    active: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
    draft: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300',
    inactive: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
    expired: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
    error: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  }

  return (
    <div className="space-y-4">
      {/* Actions bar */}
      {canEdit && (
        <div className="flex items-center gap-2">
          {unlistedPlatforms.length > 0 && (
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
          {listings.some((l) => l.status === 'active') && (
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

      {/* Current listings */}
      {listings.length === 0 && unlistedPlatforms.length === 0 ? (
        <EmptyState
          icon={<Globe className="h-8 w-8" />}
          title="Nicio platformă configurată"
          description="Configurează platformele din secțiunea CarPark > Publishing"
        />
      ) : (
        <div className="space-y-2">
          {listings.map((listing) => (
            <Card key={listing.id} className="flex items-center justify-between p-3">
              <div className="flex items-center gap-3">
                <Globe className="h-5 w-5 text-muted-foreground" />
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{listing.platform_name}</span>
                    <Badge variant="outline" className={`text-[10px] ${statusColors[listing.status] ?? ''}`}>
                      {LISTING_STATUS_LABELS[listing.status as ListingStatus] ?? listing.status}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
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
              <div className="flex items-center gap-1">
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
            </Card>
          ))}

          {/* Unlisted platforms — quick publish buttons */}
          {canEdit && unlistedPlatforms.map((platform) => (
            <Card key={platform.id} className="flex items-center justify-between p-3 opacity-60">
              <div className="flex items-center gap-3">
                <Globe className="h-5 w-5 text-muted-foreground" />
                <span className="text-sm">{platform.name}</span>
                <Badge variant="outline" className="text-[10px]">Nepublicat</Badge>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => publishMutation.mutate(platform.id)}
                disabled={publishMutation.isPending}
              >
                <Plus className="mr-1 h-3.5 w-3.5" /> Publică
              </Button>
            </Card>
          ))}
        </div>
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
    onSuccess: () => { invalidate(); toast.success('Cost line added'); setShowAddLine(false); setAddLineForm({ cost_type: 'other', description: '', planned_amount: '', currency }) },
    onError: () => toast.error('Failed to create cost line'),
  })

  const deleteLineMut = useMutation({
    mutationFn: (id: number) => carparkApi.deleteCostLine(id),
    onSuccess: () => { invalidate(); toast.success('Cost line deleted'); setDeleteLineId(null); if (expandedLineId === deleteLineId) setExpandedLineId(null) },
    onError: () => toast.error('Failed to delete cost line'),
  })

  const updateLineMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) => carparkApi.updateCostLine(id, data),
    onSuccess: () => { invalidate() },
    onError: () => toast.error('Failed to update cost line'),
  })

  const createCostMut = useMutation({
    mutationFn: ({ lineId, data }: { lineId: number; data: Record<string, unknown> }) => carparkApi.createLineCost(lineId, data),
    onSuccess: () => {
      invalidate()
      queryClient.invalidateQueries({ queryKey: ['carpark', 'line-costs', expandedLineId] })
      toast.success('Cost added')
      setAddCostLineId(null)
      setCostForm({ amount: '', description: '', supplier_name: '', invoice_number: '', date: new Date().toISOString().slice(0, 10), vat_rate: '19', vat_amount: '' })
    },
    onError: () => toast.error('Failed to add cost'),
  })

  const updateCostMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) => carparkApi.updateLineCost(id, data),
    onSuccess: () => {
      invalidate()
      queryClient.invalidateQueries({ queryKey: ['carpark', 'line-costs', expandedLineId] })
      toast.success('Cost updated')
      setEditCostId(null)
    },
    onError: () => toast.error('Failed to update cost'),
  })

  const deleteCostMut = useMutation({
    mutationFn: (id: number) => carparkApi.deleteLineCost(id),
    onSuccess: () => {
      invalidate()
      queryClient.invalidateQueries({ queryKey: ['carpark', 'line-costs', expandedLineId] })
      toast.success('Cost deleted')
      setDeleteCostId(null)
    },
    onError: () => toast.error('Failed to delete cost'),
  })

  const linkInvoiceMut = useMutation({
    mutationFn: ({ costId, invoiceId }: { costId: number; invoiceId: number }) =>
      carparkApi.linkCostInvoice(costId, invoiceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'line-costs', expandedLineId] })
      toast.success('Invoice linked')
      setLinkInvoiceCostId(null)
      setInvoiceSearch('')
    },
    onError: () => toast.error('Failed to link invoice'),
  })

  const unlinkInvoiceMut = useMutation({
    mutationFn: (costId: number) => carparkApi.linkCostInvoice(costId, null),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'line-costs', expandedLineId] })
      toast.success('Invoice unlinked')
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
            Planned: <strong className="text-foreground tabular-nums">{fmt(totalPlanned)} {currency}</strong>
          </span>
          <span className="text-muted-foreground">
            Spent: <strong className="text-foreground tabular-nums">{fmt(totalSpent)} {currency}</strong>
          </span>
          {totalPlanned > 0 && (
            <span className="text-muted-foreground">
              Execution: <strong className={totalSpent > totalPlanned ? 'text-red-500' : 'text-foreground'}>{Math.round((totalSpent / totalPlanned) * 100)}%</strong>
            </span>
          )}
        </div>
        {canEdit && (
          <Button size="sm" onClick={() => setShowAddLine(true)}>
            <Plus className="h-4 w-4 mr-1" /> Add Line
          </Button>
        )}
      </div>

      {/* Cost Lines Table */}
      {costLines.length === 0 ? (
        <EmptyState title="No cost lines" icon={<DollarSign className="h-8 w-8" />} />
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/40 text-xs text-muted-foreground">
                <th className="w-8 px-2 py-2"></th>
                <th className="text-left px-3 py-2 font-medium">Type</th>
                <th className="text-left px-3 py-2 font-medium">Description</th>
                <th className="text-right px-3 py-2 font-medium">Planned</th>
                <th className="text-right px-3 py-2 font-medium">Spent</th>
                <th className="text-left px-3 py-2 font-medium w-32">Execution</th>
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
                          <span className="ml-2 text-[10px] text-muted-foreground/60">({l.cost_count} costs)</span>
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
                            title="Double-click to edit"
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
                          <Button variant="ghost" size="sm" className="h-7 w-7 p-0" title="Record Cost"
                            onClick={(e) => { e.stopPropagation(); openAddCost(l.id) }}>
                            <DollarSign className="h-3 w-3" />
                          </Button>
                          <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-red-500 hover:text-red-600" title="Delete Line"
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
                              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Costs</span>
                              {canEdit && (
                                <div className="flex gap-1.5">
                                  <Button variant="outline" size="sm" className="h-7 text-xs"
                                    onClick={(e) => { e.stopPropagation(); openAddCost(l.id) }}>
                                    <DollarSign className="h-3 w-3 mr-1" /> Record Cost
                                  </Button>
                                </div>
                              )}
                            </div>
                            {lineCosts.length === 0 ? (
                              <div className="text-xs text-muted-foreground text-center py-3">No costs recorded yet.</div>
                            ) : (
                              <div className="rounded-md border bg-background">
                                <table className="w-full text-xs">
                                  <thead>
                                    <tr className="border-b bg-muted/30 text-muted-foreground">
                                      <th className="text-left px-3 py-1.5 font-medium">Date</th>
                                      <th className="text-right px-3 py-1.5 font-medium">Amount</th>
                                      <th className="text-right px-3 py-1.5 font-medium">VAT</th>
                                      <th className="text-left px-3 py-1.5 font-medium">Supplier</th>
                                      <th className="text-left px-3 py-1.5 font-medium">Invoice</th>
                                      <th className="text-left px-3 py-1.5 font-medium">Description</th>
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
                                              <Link2 className="h-3 w-3 mr-1" /> Link
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
            <DialogTitle>Add Cost Line</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Type</Label>
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
                <Label>Planned Amount</Label>
                <Input type="number" step="0.01" placeholder="0.00" value={addLineForm.planned_amount}
                  onChange={(e) => setAddLineForm((p) => ({ ...p, planned_amount: e.target.value }))} />
              </div>
            </div>
            <div>
              <Label>Description</Label>
              <Input placeholder="e.g. Insurance OMNIASIG, Transport from Germany" value={addLineForm.description}
                onChange={(e) => setAddLineForm((p) => ({ ...p, description: e.target.value }))} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAddLine(false)}>Cancel</Button>
            <Button disabled={createLineMut.isPending} onClick={() => createLineMut.mutate({
              cost_type: addLineForm.cost_type,
              description: addLineForm.description || null,
              planned_amount: addLineForm.planned_amount ? Number(addLineForm.planned_amount) : 0,
              currency: addLineForm.currency,
            })}>
              {createLineMut.isPending ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add/Edit Cost Dialog */}
      <Dialog open={addCostLineId !== null} onOpenChange={(open) => { if (!open) { setAddCostLineId(null); setEditCostId(null) } }}>
        <DialogContent className="sm:max-w-lg" aria-describedby={undefined}>
          <DialogHeader>
            <DialogTitle>{editCostId ? 'Edit Cost' : 'Record Cost'}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Amount (net) *</Label>
                <Input type="number" step="0.01" placeholder="0.00" value={costForm.amount} autoFocus
                  onChange={(e) => setCostForm((p) => ({ ...p, amount: e.target.value }))} />
              </div>
              <div>
                <Label>Date *</Label>
                <Input type="date" value={costForm.date}
                  onChange={(e) => setCostForm((p) => ({ ...p, date: e.target.value }))} />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <Label>VAT %</Label>
                <Input type="number" step="0.01" value={costForm.vat_rate}
                  onChange={(e) => setCostForm((p) => ({ ...p, vat_rate: e.target.value }))} />
              </div>
              <div>
                <Label>VAT Amount</Label>
                <Input type="number" step="0.01" placeholder="0.00" value={costForm.vat_amount}
                  onChange={(e) => setCostForm((p) => ({ ...p, vat_amount: e.target.value }))} />
              </div>
              <div>
                <Label>Invoice #</Label>
                <Input placeholder="Invoice number" value={costForm.invoice_number}
                  onChange={(e) => setCostForm((p) => ({ ...p, invoice_number: e.target.value }))} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Supplier</Label>
                <Input placeholder="Supplier name" value={costForm.supplier_name}
                  onChange={(e) => setCostForm((p) => ({ ...p, supplier_name: e.target.value }))} />
              </div>
              <div>
                <Label>Description</Label>
                <Input placeholder="Optional description" value={costForm.description}
                  onChange={(e) => setCostForm((p) => ({ ...p, description: e.target.value }))} />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setAddCostLineId(null); setEditCostId(null) }}>Cancel</Button>
            <Button disabled={!costForm.amount || Number(costForm.amount) <= 0 || createCostMut.isPending || updateCostMut.isPending}
              onClick={handleCostSubmit}>
              {createCostMut.isPending || updateCostMut.isPending ? 'Saving...' : editCostId ? 'Update' : 'Record'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Link Invoice Dialog */}
      <Dialog open={linkInvoiceCostId !== null} onOpenChange={(open) => { if (!open) { setLinkInvoiceCostId(null); setInvoiceSearch('') } }}>
        <DialogContent className="sm:max-w-lg" aria-describedby={undefined}>
          <DialogHeader>
            <DialogTitle>Link Invoice</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input placeholder="Search invoices..." className="pl-9" value={invoiceSearch}
                onChange={(e) => setInvoiceSearch(e.target.value)} autoFocus />
            </div>
            {invoiceResults && invoiceResults.length > 0 ? (
              <div className="max-h-60 overflow-y-auto rounded-md border">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b bg-muted/30">
                      <th className="text-left px-3 py-1.5 font-medium">Invoice #</th>
                      <th className="text-left px-3 py-1.5 font-medium">Supplier</th>
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
                            Link
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : invoiceSearch.length >= 1 ? (
              <div className="text-xs text-center text-muted-foreground py-4">No invoices found</div>
            ) : (
              <div className="text-xs text-center text-muted-foreground py-4">Type to search invoices</div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Cost Line Confirmation */}
      <Dialog open={deleteLineId !== null} onOpenChange={(open) => { if (!open) setDeleteLineId(null) }}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete Cost Line</DialogTitle>
            <DialogDescription>This will delete the cost line and all its cost entries. This cannot be undone.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteLineId(null)}>Cancel</Button>
            <Button variant="destructive" disabled={deleteLineMut.isPending}
              onClick={() => deleteLineId && deleteLineMut.mutate(deleteLineId)}>
              {deleteLineMut.isPending ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Cost Entry Confirmation */}
      <Dialog open={deleteCostId !== null} onOpenChange={(open) => { if (!open) setDeleteCostId(null) }}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete Cost</DialogTitle>
            <DialogDescription>Are you sure? This action cannot be undone.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteCostId(null)}>Cancel</Button>
            <Button variant="destructive" disabled={deleteCostMut.isPending}
              onClick={() => deleteCostId && deleteCostMut.mutate(deleteCostId)}>
              {deleteCostMut.isPending ? 'Deleting...' : 'Delete'}
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
    onSuccess: () => { invalidate(); toast.success('Revenue added'); resetForm() },
    onError: () => toast.error('Failed to add revenue'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) =>
      carparkApi.updateRevenue(id, data),
    onSuccess: () => { invalidate(); toast.success('Revenue updated'); resetForm() },
    onError: () => toast.error('Failed to update revenue'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => carparkApi.deleteRevenue(id),
    onSuccess: () => { invalidate(); toast.success('Revenue deleted'); setDeleteConfirmId(null) },
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
            <Plus className="h-4 w-4 mr-1" /> Add Revenue
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
        <EmptyState title="No revenues recorded" icon={<TrendingUp className="h-8 w-8" />} />
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/40 text-xs text-muted-foreground">
                <th className="text-left px-3 py-2 font-medium">Date</th>
                <th className="text-left px-3 py-2 font-medium">Type</th>
                <th className="text-left px-3 py-2 font-medium hidden sm:table-cell">Client</th>
                <th className="text-left px-3 py-2 font-medium hidden lg:table-cell">Invoice #</th>
                <th className="text-left px-3 py-2 font-medium hidden md:table-cell">Description</th>
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
            <DialogTitle>{editingId ? 'Edit Revenue' : 'Add Revenue'}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="grid grid-cols-2 gap-3">
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
                <Label>Date</Label>
                <Input type="date" value={form.date} onChange={(e) => setForm((p) => ({ ...p, date: e.target.value }))} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Amount (net)</Label>
                <Input type="number" step="0.01" placeholder="0.00" value={form.amount} onChange={(e) => setForm((p) => ({ ...p, amount: e.target.value }))} />
              </div>
              <div>
                <Label>VAT Amount</Label>
                <Input type="number" step="0.01" placeholder="0.00" value={form.vat_amount} onChange={(e) => setForm((p) => ({ ...p, vat_amount: e.target.value }))} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Client</Label>
                <Input placeholder="Client name" value={form.client_name} onChange={(e) => setForm((p) => ({ ...p, client_name: e.target.value }))} />
              </div>
              <div>
                <Label>Invoice #</Label>
                <Input placeholder="Invoice number" value={form.invoice_number} onChange={(e) => setForm((p) => ({ ...p, invoice_number: e.target.value }))} />
              </div>
            </div>
            <div>
              <Label>Description</Label>
              <Input placeholder="Optional description" value={form.description} onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={resetForm}>Cancel</Button>
            <Button onClick={handleSubmit} disabled={!form.amount || Number(form.amount) <= 0 || createMutation.isPending || updateMutation.isPending}>
              {createMutation.isPending || updateMutation.isPending ? 'Saving...' : editingId ? 'Update' : 'Add'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <Dialog open={deleteConfirmId !== null} onOpenChange={(open) => { if (!open) setDeleteConfirmId(null) }}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete Revenue</DialogTitle>
            <DialogDescription>Are you sure? This action cannot be undone.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirmId(null)}>Cancel</Button>
            <Button variant="destructive" disabled={deleteMutation.isPending} onClick={() => deleteConfirmId && deleteMutation.mutate(deleteConfirmId)}>
              {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
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
