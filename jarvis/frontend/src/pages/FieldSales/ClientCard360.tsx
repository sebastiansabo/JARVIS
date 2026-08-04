import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Calendar, Euro,
  Shield, TrendingUp, AlertTriangle, RefreshCw,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  fieldSalesApi,
  type FSClientProfile, type FSClientFleetVehicle, type FSSaleSummary,
  type FSVisitSummary, type FSInventoryMatch, type FSAnafData,
} from '@/api/fieldSales'

type ApiErr = { data?: { error?: string } } | null

const VISIT_TYPE_LABELS: Record<string, string> = {
  fleet_review: 'Revizuire flota',
  renewal_discussion: 'Discutie reinnoire',
  test_drive_followup: 'Follow-up test drive',
  service_followup: 'Follow-up service',
  new_acquisition: 'Achizitie noua',
  contract_negotiation: 'Negociere contract',
  prospecting: 'Prospectare',
  general: 'General',
}

const PRIORITY_LABELS: Record<string, string> = { high: 'Prioritate ridicata', medium: 'Prioritate medie', low: 'Prioritate scazuta' }
const PRIORITY_STYLES: Record<string, string> = {
  high: 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300',
  medium: 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300',
  low: 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300',
}

function formatDate(d: string | null): string {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('ro-RO', { day: '2-digit', month: 'short', year: 'numeric' })
}

function formatEUR(v: number | null): string {
  if (v == null) return '-'
  return new Intl.NumberFormat('ro-RO', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(v)
}

// Compact single-line empty state — replaces the old big centered icon block,
// which wasted vertical space once the card had room to lay out real content.
function EmptyLine({ text }: { text: string }) {
  return <p className="py-2 text-sm text-muted-foreground">{text}</p>
}

// ── Header ──
function HeaderSection({ clientId, clientName, profile }: {
  clientId: number
  clientName?: string
  profile: Pick<FSClientProfile, 'client_type' | 'industry' | 'fleet_size' | 'priority' | 'renewal_score'> | null
}) {
  return (
    <div className="rounded-2xl bg-card border p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-lg font-bold text-foreground truncate">{clientName || `Client #${clientId}`}</h2>
          {profile && (
            <p className="text-xs text-muted-foreground mt-0.5">
              {profile.client_type === 'company' ? 'Firma' : 'Persoana fizica'}
              {profile.industry ? ` - ${profile.industry}` : ''}
              {profile.fleet_size > 0 ? ` - ${profile.fleet_size} vehicule` : ''}
            </p>
          )}
        </div>
        {profile && (
          <div className="flex shrink-0 flex-col items-end gap-1.5">
            <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide', PRIORITY_STYLES[profile.priority] ?? PRIORITY_STYLES.medium)}>
              {PRIORITY_LABELS[profile.priority] ?? profile.priority}
            </span>
            {profile.renewal_score > 60 && (
              <span className="rounded-full bg-amber-100 dark:bg-amber-900/40 px-2 py-0.5 text-[10px] font-bold text-amber-700 dark:text-amber-300">
                {profile.renewal_score}% reinnoire
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Fiscal (ANAF) ──
// `fiscal` is the raw ANAF lookup dict as returned by the backend — flat keys
// (denumire/cui/adresa/nrRegCom/scpTVA/telefon/stare_inregistrare), NOT the
// normalized company_name/is_vat_payer/is_inactive/fetched_at shape.
function FiscalSection({ fiscal, onRefresh, refreshing }: {
  fiscal: FSAnafData | null
  onRefresh: () => void
  refreshing: boolean
}) {
  const isVatPayer = fiscal?.scpTVA === true
  const stareRaw = typeof fiscal?.stare_inregistrare === 'string' ? fiscal.stare_inregistrare : ''
  const hasStare = stareRaw.trim().length > 0
  const isActive = hasStare && stareRaw.toUpperCase().includes('INREG')

  return (
    <div className="rounded-2xl bg-card border p-4 h-full">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Date ANAF</h3>
        <button
          onClick={onRefresh}
          disabled={refreshing}
          className="flex items-center gap-1.5 rounded-full bg-secondary px-2.5 py-1.5 text-xs font-semibold text-foreground touch-target active:bg-secondary/80 transition-colors disabled:opacity-60"
        >
          <RefreshCw className={cn('h-3.5 w-3.5', refreshing && 'animate-spin')} />
          Reimprospateaza
        </button>
      </div>

      {!fiscal ? (
        <EmptyLine text="Date fiscale indisponibile" />
      ) : (
        <div className="space-y-3">
          {fiscal.denumire && (
            <div>
              <p className="text-xs text-muted-foreground">Denumire</p>
              <p className="text-sm font-medium text-foreground break-words">{fiscal.denumire}</p>
            </div>
          )}
          {fiscal.adresa && (
            <div>
              <p className="text-xs text-muted-foreground">Adresa</p>
              <p className="text-sm text-foreground break-words">{fiscal.adresa}</p>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            <span className={cn('rounded-full px-2.5 py-1 text-xs font-semibold', isVatPayer
              ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300'
              : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400')}
            >
              {isVatPayer ? 'Platitor TVA' : 'Neplatitor TVA'}
            </span>
            {hasStare && (
              <span className={cn('rounded-full px-2.5 py-1 text-xs font-semibold', isActive
                ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300'
                : 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300')}
              >
                {isActive ? 'Activ' : 'Inactiv'}
              </span>
            )}
          </div>

          {(fiscal.cui || fiscal.nrRegCom || fiscal.telefon) && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2">
              {fiscal.cui && (
                <div>
                  <p className="text-xs text-muted-foreground">CUI</p>
                  <p className="text-sm text-foreground break-words">{fiscal.cui}</p>
                </div>
              )}
              {fiscal.nrRegCom && (
                <div>
                  <p className="text-xs text-muted-foreground">Nr. Reg. Com</p>
                  <p className="text-sm text-foreground break-words">{fiscal.nrRegCom}</p>
                </div>
              )}
              {fiscal.telefon && (
                <div>
                  <p className="text-xs text-muted-foreground">Telefon</p>
                  <p className="text-sm text-foreground break-words">{fiscal.telefon}</p>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Fleet ──
function FleetSection({ vehicles }: { vehicles: FSClientFleetVehicle[] }) {
  return (
    <div className="rounded-2xl bg-card border p-4 space-y-3 h-full">
      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
        Flota ({vehicles.length})
      </h3>
      {vehicles.length === 0 ? (
        <EmptyLine text="Niciun vehicul in flota" />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {vehicles.map((v) => {
            const financingExpiring = v.financing_expiry && new Date(v.financing_expiry) <= new Date(Date.now() + 90 * 86400000)
            const warrantyExpiring = v.warranty_expiry && new Date(v.warranty_expiry) <= new Date(Date.now() + 90 * 86400000)
            return (
              <div
                key={v.id}
                className={cn('rounded-xl border p-3', v.renewal_candidate && 'border-amber-300 dark:border-amber-700 bg-amber-50/50 dark:bg-amber-900/10')}
              >
                <div className="flex items-start justify-between gap-2 mb-1.5">
                  <div className="min-w-0 flex-1">
                    <h4 className="text-sm font-semibold text-foreground truncate">{v.vehicle_make} {v.vehicle_model}</h4>
                    <p className="text-xs text-muted-foreground">
                      {v.vehicle_year} {v.license_plate ? `- ${v.license_plate}` : ''}
                    </p>
                  </div>
                  {v.renewal_candidate && (
                    <span className="shrink-0 rounded-full bg-amber-100 dark:bg-amber-900/40 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-700 dark:text-amber-300">
                      Reinnoire
                    </span>
                  )}
                </div>

                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  {v.financing_type && (
                    <span className="flex items-center gap-1"><Euro className="h-3 w-3" />{v.financing_type}</span>
                  )}
                  {v.estimated_mileage != null && <span>{(v.estimated_mileage / 1000).toFixed(0)}k km</span>}
                  {v.vin && <span className="font-mono text-[10px]">{v.vin.slice(-6)}</span>}
                </div>

                {(financingExpiring || warrantyExpiring || v.renewal_reason) && (
                  <div className="mt-2 space-y-1">
                    {financingExpiring && (
                      <div className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400">
                        <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                        Finantare expira: {formatDate(v.financing_expiry)}
                      </div>
                    )}
                    {warrantyExpiring && (
                      <div className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400">
                        <Shield className="h-3.5 w-3.5 shrink-0" />
                        Garantie expira: {formatDate(v.warranty_expiry)}
                      </div>
                    )}
                    {v.renewal_reason && (
                      <div className="flex items-center gap-1.5 text-xs text-blue-600 dark:text-blue-400">
                        <TrendingUp className="h-3.5 w-3.5 shrink-0" />
                        {v.renewal_reason}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Last Purchases ──
function PurchasesSection({ purchases }: { purchases: FSSaleSummary[] }) {
  return (
    <div className="rounded-2xl bg-card border p-4 space-y-3">
      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
        Ultimele achizitii ({purchases.length})
      </h3>
      {purchases.length === 0 ? (
        <EmptyLine text="Nicio achizitie inregistrata" />
      ) : (
        purchases.map((p) => (
          <div key={p.id} className="rounded-xl border p-3">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <h4 className="text-sm font-semibold text-foreground truncate">{p.brand} {p.model_name}</h4>
                <p className="text-xs text-muted-foreground mt-0.5">{formatDate(p.contract_date)} - {p.source}</p>
              </div>
              {p.sale_price_net != null && (
                <span className="shrink-0 text-sm font-bold text-foreground">{formatEUR(p.sale_price_net)}</span>
              )}
            </div>
            {p.vin && <p className="text-xs text-muted-foreground mt-1.5 font-mono truncate">VIN: {p.vin}</p>}
          </div>
        ))
      )}
    </div>
  )
}

// ── Visit History ──
function VisitHistorySection({ visits }: { visits: FSVisitSummary[] }) {
  return (
    <div className="rounded-2xl bg-card border p-4 space-y-3">
      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
        Istoric vizite ({visits.length})
      </h3>
      {visits.length === 0 ? (
        <EmptyLine text="Niciun istoric de vizite" />
      ) : (
        <div className="space-y-2">
          {visits.map((vh) => (
            <div key={vh.id} className="flex items-start gap-3 py-2 border-b border-border/50 last:border-0">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary">
                <Calendar className="h-4 w-4 text-muted-foreground" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium text-foreground">{VISIT_TYPE_LABELS[vh.visit_type] ?? vh.visit_type}</p>
                  <span className="text-xs text-muted-foreground shrink-0">{formatDate(vh.planned_date)}</span>
                </div>
                {vh.visit_summary && (
                  <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{vh.visit_summary}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Inventory Matches ──
function InventoryMatchesSection({ matches }: { matches: FSInventoryMatch[] }) {
  return (
    <div className="rounded-2xl bg-card border p-4 space-y-3">
      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
        Potriviri din stoc ({matches.length})
      </h3>
      {matches.length === 0 ? (
        <EmptyLine text="Nicio potrivire in stoc" />
      ) : (
        matches.map((m) => (
          <div key={m.id} className="rounded-xl border p-3">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <h4 className="text-sm font-semibold text-foreground truncate">{m.brand} {m.model_name}</h4>
                <p className="text-xs text-muted-foreground mt-0.5">{m.model_year}</p>
              </div>
              <span className="shrink-0 text-sm font-bold text-foreground">{formatEUR(m.sale_price_net)}</span>
            </div>
            {m.vin && <p className="text-xs text-muted-foreground mt-1.5 font-mono truncate">VIN: {m.vin}</p>}
          </div>
        ))
      )}
    </div>
  )
}

// ── Main Component ──
export default function ClientCard360({ clientId, clientName }: { clientId: number; clientName?: string }) {
  const queryClient = useQueryClient()

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['field-sales-client360', clientId],
    queryFn: () => fieldSalesApi.getClient360(clientId),
    enabled: clientId > 0,
  })
  const fetchErr = error as ApiErr

  const refreshFiscalMutation = useMutation({
    mutationFn: () => fieldSalesApi.refreshFiscal(clientId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['field-sales-client360', clientId] })
    },
  })
  const refreshErr = refreshFiscalMutation.error as ApiErr

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-foreground" />
        <p className="text-sm text-muted-foreground mt-3">Se incarca datele clientului...</p>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <AlertTriangle className="h-7 w-7 text-destructive mb-2" />
        <p className="text-sm text-destructive text-center">
          {fetchErr?.data?.error ?? 'Nu s-au putut incarca datele clientului'}
        </p>
      </div>
    )
  }

  const profile = data?.profile ?? null
  const fleet = data?.fleet ?? []
  const purchases = data?.last_purchases ?? []
  const visitHistory = data?.visit_history ?? []
  const inventoryMatches = data?.inventory_matches ?? []
  const fiscal = data?.fiscal ?? null

  return (
    <div className="space-y-4 p-4 sm:p-6">
      <HeaderSection clientId={clientId} clientName={clientName} profile={profile} />

      {/* Fiscal + Fleet read as two peer "info" panels — pair them on desktop
          so the card uses the extra horizontal space instead of one narrow
          column of stacked cards. Fleet gets the wider slot since it lays
          out its own sub-grid of vehicle cards. */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-1 space-y-2">
          <FiscalSection
            fiscal={fiscal}
            onRefresh={() => refreshFiscalMutation.mutate()}
            refreshing={refreshFiscalMutation.isPending}
          />
          {refreshFiscalMutation.isError && (
            <p className="text-xs text-destructive text-center">
              {refreshErr?.data?.error ?? 'Eroare la actualizarea datelor fiscale'}
            </p>
          )}
        </div>
        <div className="lg:col-span-2">
          <FleetSection vehicles={fleet} />
        </div>
      </div>

      {/* Chronological / scannable lists — lay these out side by side once
          there's room instead of stacking them full-width. */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        <PurchasesSection purchases={purchases} />
        <VisitHistorySection visits={visitHistory} />
        <InventoryMatchesSection matches={inventoryMatches} />
      </div>
    </div>
  )
}
