// CarPark vehicle Detail — "Vânzare" tab: the primary sales view for a
// vehicle. Shows the recorded sale (if any), the reservation history, a row
// of guarded lifecycle actions (Rezervă/Vinde/Livrează/Redeschide — reusing
// the same dialogs as the Dispo workspace, see ../Dispo/*Dialog.tsx), and a
// finance-gated profitability mini-panel.
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  BookmarkCheck,
  DollarSign,
  PackageCheck,
  RotateCcw,
  User,
  CalendarClock,
  History,
  TrendingUp,
  TrendingDown,
  Wallet,
  Pencil,
} from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { CurrencyDisplay } from '@/components/shared/CurrencyDisplay'
import { ClientSearchSelect, type ClientSearchSelection } from '@/components/shared/ClientSearchSelect'
import { useAuthStore } from '@/stores/authStore'
import { carparkApi } from '@/api/carpark'
import { carparkDispoApi } from '@/api/carparkDispo'
import type { DispoRow, DispoReservation, Vehicle, VehicleStatus } from '@/types/carpark'
import { ReserveDialog } from '../Dispo/ReserveDialog'
import { SellDialog } from '../Dispo/SellDialog'
import { DeliverDialog } from '../Dispo/DeliverDialog'
import { ReopenDialog } from '../Dispo/ReopenDialog'
import { apiErrorMessage } from '../Dispo/dispoApiError'

function formatDate(d: string | null): string {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('ro-RO')
}

// ── Action-availability rules ──────────────────────────────
// Mirrors ../Dispo/DispoRowActions.tsx's gating exactly (kept as a separate
// copy rather than an import — same convention ReopenDialog.tsx already
// uses for its own mirrored REOPEN_TARGETS table — so this tab doesn't take
// on a cross-directory dependency on the workspace's dropdown-menu component).
const RESERVE_HIDDEN_STATUSES = new Set<VehicleStatus>([
  'RESERVED', 'SOLD', 'DELIVERED', 'RETURNED', 'SCRAPPED', 'TRANSFERRED', 'INSURANCE_CLAIM',
])
const SELLABLE_STATUSES = new Set<VehicleStatus>([
  'READY_FOR_SALE', 'LISTED', 'PRICE_REDUCED', 'AUCTION_CANDIDATE', 'RESERVED',
])

type DialogKind = 'reserve' | 'sell' | 'deliver' | 'reopen' | null

// Builds a DispoRow-shaped object out of the Detail page's Vehicle record
// (+ the active reservation, for the reservation_* columns DispoRow carries
// that the raw vehicle record doesn't) so the reused Dispo dialogs — which
// only take a `row: DispoRow` prop — can be opened straight from here.
// Fields the dialogs never read (doc_types, supplier_payment_date, ...) get
// inert placeholders; only what ReserveDialog/SellDialog/DeliverDialog/
// ReopenDialog actually consult needs to be accurate.
function buildDispoRow(vehicle: Vehicle, activeReservation: DispoReservation | null): DispoRow {
  return {
    id: vehicle.id,
    vin: vehicle.vin,
    nr_stoc: vehicle.nr_stoc,
    brand: vehicle.brand,
    model: vehicle.model,
    variant: vehicle.variant,
    status: vehicle.status,
    source: vehicle.source,
    location_text: vehicle.location_text,
    sale_type: vehicle.sale_type,
    salesperson_user_id: vehicle.salesperson_user_id,
    acquisition_manager_id: vehicle.acquisition_manager_id,
    acquisition_date: vehicle.acquisition_date,
    listing_date: vehicle.listing_date,
    sale_date: vehicle.sale_date,
    delivery_date: vehicle.delivery_date,
    supplier_payment_date: null,
    stock_removed_date: vehicle.stock_removed_date,
    days_in_stock: vehicle.stationary_days,
    current_price: vehicle.current_price,
    list_price: vehicle.list_price,
    promotional_price: vehicle.promotional_price,
    sale_price: vehicle.sale_price,
    gw_file_number: vehicle.gw_file_number,
    is_impus: vehicle.is_impus,
    missing_civ: vehicle.missing_civ,
    stock_removed: vehicle.stock_removed,
    buyer_name: vehicle.buyer_name,
    buyer_client_id: vehicle.buyer_client_id,
    company_id: vehicle.company_id,
    reservation_id: activeReservation?.id ?? null,
    reservation_end: activeReservation?.reservation_end ?? null,
    reservation_client_name: activeReservation?.client_name ?? null,
    reservation_deposit_amount: activeReservation?.deposit_amount ?? null,
    reservation_deposit_paid: activeReservation?.deposit_paid ?? null,
    doc_types: [],
    acquisition_price: vehicle.acquisition_price,
  }
}

// ── Sale record card ────────────────────────────────────────
function SaleRecordCard({
  vehicle,
  canViewFinance,
  canEdit,
  onBuyerUpdated,
}: {
  vehicle: Vehicle
  canViewFinance: boolean
  canEdit: boolean
  onBuyerUpdated: () => void
}) {
  const hasSale = vehicle.sale_price != null || vehicle.sale_date != null
  const margin =
    vehicle.sale_price != null && vehicle.total_cost != null ? vehicle.sale_price - vehicle.total_cost : null

  const [editingBuyer, setEditingBuyer] = useState(false)
  const buyerMutation = useMutation({
    mutationFn: (client: ClientSearchSelection) =>
      carparkApi.updateVehicle(vehicle.id, { buyer_client_id: client.id, buyer_name: client.name }),
    onSuccess: () => {
      toast.success('Cumpărător actualizat')
      onBuyerUpdated()
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Eroare la salvare')),
  })

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold">Vânzare</h3>
        <div className="flex flex-wrap items-center gap-1">
          {vehicle.is_impus && (
            <Badge variant="destructive" className="text-[10px] font-normal">IMPUS</Badge>
          )}
          {vehicle.missing_civ && (
            <Badge variant="outline" className="text-[10px] font-normal border-amber-500 text-amber-600 dark:text-amber-400">
              LIPSĂ CIV
            </Badge>
          )}
          {vehicle.stock_removed && (
            <Badge variant="secondary" className="text-[10px] font-normal">
              SCOS DIN EVIDENȚĂ{vehicle.stock_removed_date ? ` (${formatDate(vehicle.stock_removed_date)})` : ''}
            </Badge>
          )}
        </div>
      </div>

      {!hasSale ? (
        <p className="text-sm text-muted-foreground">Vehiculul nu a fost încă vândut.</p>
      ) : (
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <div>
            <dt className="text-xs text-muted-foreground">Tip vânzare</dt>
            <dd className="text-sm font-medium">{vehicle.sale_type ?? '-'}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Cumpărător</dt>
            <dd className="text-sm font-medium">
              {editingBuyer ? (
                <ClientSearchSelect
                  value={{ id: vehicle.buyer_client_id, name: vehicle.buyer_name }}
                  companyId={vehicle.company_id ?? undefined}
                  open
                  onOpenChange={(o) => { if (!o) setEditingBuyer(false) }}
                  onSelect={(client) => {
                    setEditingBuyer(false)
                    if (client.id === vehicle.buyer_client_id && client.name === (vehicle.buyer_name ?? '')) return
                    buyerMutation.mutate(client)
                  }}
                />
              ) : (
                <span className="inline-flex items-center gap-1.5">
                  {vehicle.buyer_name ?? (vehicle.buyer_client_id ? `Client #${vehicle.buyer_client_id} (CRM)` : '-')}
                  {canEdit && (
                    <button
                      type="button"
                      onClick={() => setEditingBuyer(true)}
                      className="text-muted-foreground hover:text-foreground"
                      aria-label="Editează cumpărătorul"
                      title="Editează cumpărătorul"
                    >
                      <Pencil className="h-3 w-3" />
                    </button>
                  )}
                </span>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Preț vânzare</dt>
            <dd className="text-sm font-medium">
              {vehicle.sale_price != null ? (
                <CurrencyDisplay value={vehicle.sale_price} currency={vehicle.price_currency} />
              ) : '-'}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Data vânzării</dt>
            <dd className="text-sm font-medium">{formatDate(vehicle.sale_date)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Nr. dosar GW</dt>
            <dd className="text-sm font-medium">{vehicle.gw_file_number ?? '-'}</dd>
          </div>
          {canViewFinance && margin != null && (
            <div>
              <dt className="text-xs text-muted-foreground">Marjă</dt>
              <dd className="text-sm font-medium">
                <CurrencyDisplay value={margin} currency={vehicle.price_currency} showSign />
              </dd>
            </div>
          )}
        </dl>
      )}
    </Card>
  )
}

// ── Reservation widget ──────────────────────────────────────
function ReservationCard({ vehicleId }: { vehicleId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['carpark', 'reservations', vehicleId],
    queryFn: () => carparkDispoApi.getReservations(vehicleId),
    enabled: !!vehicleId,
  })

  const reservations = data?.reservations ?? []
  const active = reservations.find((r) => r.status === 'active') ?? null
  const history = reservations
    .filter((r) => r.id !== active?.id)
    .sort((a, b) => new Date(b.reservation_start).getTime() - new Date(a.reservation_start).getTime())

  return (
    <Card className="p-4">
      <h3 className="text-sm font-semibold mb-3 flex items-center gap-1.5">
        <BookmarkCheck className="h-4 w-4" /> Rezervare
      </h3>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Se încarcă...</p>
      ) : !active && history.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nicio rezervare înregistrată.</p>
      ) : (
        <div className="space-y-4">
          {active && (
            <div className="rounded-md border border-purple-300 bg-purple-50 p-3 dark:border-purple-800 dark:bg-purple-950/30">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-sm font-medium">
                  <User className="h-3.5 w-3.5" /> {active.client_name ?? 'Client necunoscut'}
                </div>
                <Badge variant="secondary" className="text-[10px]">Activă</Badge>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-muted-foreground sm:grid-cols-3">
                <div className="flex items-center gap-1">
                  <CalendarClock className="h-3 w-3" />
                  Până la {formatDate(active.reservation_end)}
                </div>
                <div>
                  Avans:{' '}
                  {active.deposit_amount > 0 ? (
                    <CurrencyDisplay value={active.deposit_amount} className="text-xs" />
                  ) : '-'}
                  {active.deposit_amount > 0 && (active.deposit_paid ? ' (plătit)' : ' (neplătit)')}
                </div>
                {active.client_company && <div>{active.client_company}</div>}
              </div>
              {active.notes && <p className="mt-1.5 text-xs text-muted-foreground">{active.notes}</p>}
            </div>
          )}

          {history.length > 0 && (
            <div>
              <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <History className="h-3.5 w-3.5" /> Istoric rezervări
              </div>
              <ul className="space-y-1.5">
                {history.map((r) => (
                  <li key={r.id} className="flex items-center justify-between text-xs text-muted-foreground border-b last:border-0 pb-1.5 last:pb-0">
                    <span>{r.client_name ?? 'Client necunoscut'}</span>
                    <span className="flex items-center gap-2">
                      <Badge variant="outline" className="text-[10px] font-normal">
                        {r.status === 'cancelled' ? 'Anulată' : r.status === 'converted' ? 'Finalizată' : r.status}
                      </Badge>
                      {formatDate(r.reservation_start)} — {formatDate(r.reservation_end)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

// ── Profitability mini-panel ────────────────────────────────
function ProfitabilityPanel({ vehicleId, currency }: { vehicleId: number; currency: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['carpark', 'profitability', vehicleId],
    queryFn: () => carparkApi.getProfitability(vehicleId),
    enabled: !!vehicleId,
  })

  if (isLoading || !data) return null

  const isProfit = data.profit >= 0

  return (
    <Card className="p-4">
      <h3 className="text-sm font-semibold mb-3 flex items-center gap-1.5">
        <Wallet className="h-4 w-4" /> Profitabilitate
      </h3>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div>
          <div className="text-xs text-muted-foreground">Total investit</div>
          <CurrencyDisplay value={data.total_invested} currency={currency} className="text-base font-semibold" />
        </div>
        <div>
          <div className="text-xs text-muted-foreground flex items-center gap-1">
            <TrendingDown className="h-3 w-3" /> Costuri totale
          </div>
          <CurrencyDisplay value={data.total_costs} currency={currency} className="text-base font-semibold text-red-600 dark:text-red-400" />
        </div>
        <div>
          <div className="text-xs text-muted-foreground flex items-center gap-1">
            <TrendingUp className="h-3 w-3" /> Venituri totale
          </div>
          <CurrencyDisplay value={data.total_revenues} currency={currency} className="text-base font-semibold text-green-600 dark:text-green-400" />
        </div>
        <div>
          <div className="text-xs text-muted-foreground flex items-center gap-1">
            <DollarSign className="h-3 w-3" /> Profit
          </div>
          <CurrencyDisplay
            value={data.profit}
            currency={currency}
            showSign
            className={`text-base font-bold ${isProfit ? 'text-green-700 dark:text-green-300' : 'text-red-700 dark:text-red-300'}`}
          />
        </div>
      </div>
    </Card>
  )
}

// ── Main tab ─────────────────────────────────────────────────
export function VanzareTab({ vehicle, onChanged }: { vehicle: Vehicle; onChanged?: () => void }) {
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const canEdit = !!user?.can_edit_carpark
  const canDelete = !!user?.can_delete_carpark
  const canViewFinance = !!user?.can_view_carpark_finance

  const [dialog, setDialog] = useState<DialogKind>(null)

  const { data: reservationsData } = useQuery({
    queryKey: ['carpark', 'reservations', vehicle.id],
    queryFn: () => carparkDispoApi.getReservations(vehicle.id),
    enabled: !!vehicle.id,
  })
  const activeReservation = useMemo(
    () => reservationsData?.reservations.find((r) => r.status === 'active') ?? null,
    [reservationsData],
  )

  const row = useMemo(() => buildDispoRow(vehicle, activeReservation), [vehicle, activeReservation])

  const canReserve = canEdit && !RESERVE_HIDDEN_STATUSES.has(vehicle.status)
  const canSell = canEdit && SELLABLE_STATUSES.has(vehicle.status)
  const canDeliver = canEdit && vehicle.status === 'SOLD'
  const canReopen = canDelete && (vehicle.status === 'SOLD' || vehicle.status === 'DELIVERED')

  // Fired from each reused dialog's onSuccess (in addition to its own
  // ['carpark', 'dispo'] invalidation) so the Detail page's vehicle record,
  // the reservation widget, the timeline and the profitability panel all
  // refresh immediately instead of waiting for a manual reload.
  function handleActionSuccess() {
    queryClient.invalidateQueries({ queryKey: ['carpark', 'vehicle', vehicle.id] })
    queryClient.invalidateQueries({ queryKey: ['carpark', 'reservations', vehicle.id] })
    queryClient.invalidateQueries({ queryKey: ['carpark', 'timeline', vehicle.id] })
    queryClient.invalidateQueries({ queryKey: ['carpark', 'profitability', vehicle.id] })
    // Best-effort: the Dispo workspace summary may not be mounted, but if
    // it is (or gets mounted later) it shouldn't show stale data either.
    queryClient.invalidateQueries({ queryKey: ['carpark', 'dispo'] })
    onChanged?.()
  }

  return (
    <div className="space-y-4">
      {(canReserve || canSell || canDeliver || canReopen) && (
        <div className="flex flex-wrap items-center gap-2">
          {canReserve && (
            <Button size="sm" variant="outline" onClick={() => setDialog('reserve')}>
              <BookmarkCheck className="mr-1.5 h-3.5 w-3.5" /> Rezervă
            </Button>
          )}
          {canSell && (
            <Button size="sm" onClick={() => setDialog('sell')}>
              <DollarSign className="mr-1.5 h-3.5 w-3.5" /> Vinde
            </Button>
          )}
          {canDeliver && (
            <Button size="sm" onClick={() => setDialog('deliver')}>
              <PackageCheck className="mr-1.5 h-3.5 w-3.5" /> Livrează
            </Button>
          )}
          {canReopen && (
            <Button size="sm" variant="outline" onClick={() => setDialog('reopen')}>
              <RotateCcw className="mr-1.5 h-3.5 w-3.5" /> Redeschide
            </Button>
          )}
        </div>
      )}

      <SaleRecordCard
        vehicle={vehicle}
        canViewFinance={canViewFinance}
        canEdit={canEdit}
        onBuyerUpdated={handleActionSuccess}
      />
      <ReservationCard vehicleId={vehicle.id} />
      {canViewFinance && <ProfitabilityPanel vehicleId={vehicle.id} currency={vehicle.price_currency || 'RON'} />}

      {dialog === 'reserve' && (
        <ReserveDialog row={row} onClose={() => setDialog(null)} onSuccess={handleActionSuccess} />
      )}
      {dialog === 'sell' && (
        <SellDialog row={row} onClose={() => setDialog(null)} onSuccess={handleActionSuccess} />
      )}
      {dialog === 'deliver' && (
        <DeliverDialog row={row} onClose={() => setDialog(null)} onSuccess={handleActionSuccess} />
      )}
      {dialog === 'reopen' && (
        <ReopenDialog row={row} onClose={() => setDialog(null)} onSuccess={handleActionSuccess} />
      )}
    </div>
  )
}

export default VanzareTab
