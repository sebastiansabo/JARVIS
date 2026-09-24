import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Car, User, Euro, Wrench, Clock, FileText, Camera } from 'lucide-react'
import { buybackApi } from '@/api/buyback'
import { useAuth } from '@/hooks/useAuth'
import { mediaUrl } from '@/lib/media'
import { recordStatus } from './recordStatus'
import PhotoGallery from './PhotoGallery'
import ActionPanel from './ActionPanel'
import type { BuybackOffer, BuybackEvent } from '@/types/buyback'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/shared/EmptyState'

// ── Field row — label/value pair, null-safe ("—" for missing). ──
function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="space-y-0.5">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-sm">{value ?? '—'}</p>
    </div>
  )
}

function yesNo(v: boolean | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return v ? 'Da' : 'Nu'
}

function fmtDate(v: string | null | undefined): string {
  if (!v) return '—'
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return v
  return d.toLocaleDateString('ro-RO', { day: '2-digit', month: 'short', year: 'numeric' })
}

function fmtDateTime(v: string | null | undefined): string {
  if (!v) return '—'
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return v
  return d.toLocaleString('ro-RO', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function fmtEur(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return `${v.toLocaleString('ro-RO')} €`
}

// Latest offer overall (by created_at, tie-broken by id) — used for the
// "Ofertă curentă" price row, independent of ActionPanel's pending-only pick.
function latestOffer(offers: BuybackOffer[]): BuybackOffer | undefined {
  if (!offers.length) return undefined
  return offers.reduce((latest, o) => {
    const oTime = new Date(o.created_at).getTime()
    const latestTime = new Date(latest.created_at).getTime()
    if (oTime !== latestTime) return oTime > latestTime ? o : latest
    return o.id > latest.id ? o : latest
  })
}

const DECISION_LABEL: Record<string, string> = {
  pending: 'În așteptare',
  accepted: 'Acceptată',
  declined: 'Refuzată',
}

const EVENT_ACTION_LABEL: Record<string, string> = {
  created: 'Solicitare creată',
  status_changed: 'Status schimbat',
  inspection_updated: 'Inspecție actualizată',
  inspection_report_uploaded: 'Raport inspecție încărcat',
}

function eventLabel(ev: BuybackEvent): string {
  return EVENT_ACTION_LABEL[ev.action] ?? ev.action
}

function eventDetail(ev: BuybackEvent): string | null {
  const details = ev.details
  if (!details) return null
  if (ev.action === 'status_changed' && (details.from || details.to)) {
    const from = typeof details.from === 'string' ? recordStatus(details.from).label : String(details.from ?? '—')
    const to = typeof details.to === 'string' ? recordStatus(details.to).label : String(details.to ?? '—')
    return `${from} → ${to}`
  }
  const entries = Object.entries(details).filter(([, v]) => v !== null && v !== undefined && v !== '')
  if (!entries.length) return null
  return entries.map(([k, v]) => `${k}: ${v}`).join(', ')
}

function DetailSkeleton() {
  return (
    <div className="space-y-4 p-4 md:p-6">
      <div className="flex items-center gap-4">
        <Skeleton className="h-8 w-24" />
        <Skeleton className="h-6 w-48" />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-64 rounded-lg" />
        <Skeleton className="h-64 rounded-lg" />
      </div>
    </div>
  )
}

export default function BuyBackDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const recordId = Number(id)

  const isAdmin = ['admin', 'superadmin'].includes((user?.role_name ?? '').toLowerCase())
  const canEditPhotos = isAdmin || !!user?.permissions?.['buyback.record.edit']

  const { data, isLoading, isError } = useQuery({
    queryKey: ['buyback-record', recordId],
    queryFn: () => buybackApi.getRecord(recordId),
    enabled: !!recordId,
  })

  if (isLoading) return <DetailSkeleton />

  if (isError || !data) {
    return (
      <div className="p-4 md:p-6">
        <EmptyState
          icon={<Car className="h-12 w-12" />}
          title="Solicitare negăsită"
          action={
            <Button variant="outline" asChild>
              <Link to="/app/buyback">Înapoi la listă</Link>
            </Button>
          }
        />
      </div>
    )
  }

  const { record, offers, photos, events } = data
  const rs = recordStatus(record.status)
  const offer = latestOffer(offers)

  return (
    <div className="space-y-4 p-4 md:p-6">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" onClick={() => navigate('/app/buyback')}>
          <ArrowLeft className="h-4 w-4 mr-1" />Înapoi
        </Button>
        <h1 className="text-lg font-semibold">{`${record.brand} ${record.model}`}</h1>
        <Badge className={rs.badgeClass}>{rs.label}</Badge>
        <span className="font-mono text-xs text-muted-foreground">{record.record_code}</span>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2"><Car className="h-4 w-4" />Vehicul</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3">
            <Field label="Marca" value={record.brand} />
            <Field label="Model" value={record.model} />
            <Field label="Varianta" value={record.variant} />
            <Field label="Echipare" value={record.equipment} />
            <Field label="VIN" value={<span className="font-mono">{record.vin}</span>} />
            <Field label="Rulaj (km)" value={record.mileage_km != null ? record.mileage_km.toLocaleString('ro-RO') : null} />
            <Field label="Capacitate cilindrică (cm³)" value={record.engine_capacity_cm3} />
            <Field label="Combustibil" value={record.fuel_type} />
            <Field label="Transmisie" value={record.transmission} />
            <Field label="Cutie de viteze" value={record.gearbox} />
            <Field label="Data fabricație" value={fmtDate(record.manufacture_date)} />
            <Field label="Data prima înmatriculare" value={fmtDate(record.first_registration_date)} />
            <Field label="Istoric service la zi" value={yesNo(record.service_history_uptodate)} />
            <Field label="Roți extra" value={yesNo(record.extra_wheels)} />
            <Field label="Nr. chei" value={record.keys_count} />
            <Field label="Condiție generală" value={record.general_condition != null ? `${record.general_condition}/5` : null} />
            <Field label="Daune" value={yesNo(record.has_damage)} />
            {record.has_damage && (
              <div className="col-span-2">
                <Field label="Detalii daune" value={record.damage_details} />
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2"><User className="h-4 w-4" />Vânzător &amp; Trade-in</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3">
            <Field label="Tip client" value={record.client_type} />
            <Field label="Status TVA" value={record.vat_status} />
            <Field label="Nume vânzător" value={record.seller_name} />
            <Field label="Email" value={record.seller_email} />
            <Field label="Telefon" value={record.seller_phone} />
            <Field label="CUI" value={record.seller_cui} />
            <Field label="Trade-in" value={yesNo(record.is_trade_in)} />
            {record.is_trade_in && (
              <>
                <Field label="Vehicul țintă" value={record.target_vehicle_text} />
                <Field label="Vehicul CarPark (ID)" value={record.target_carpark_vehicle_id} />
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2"><Euro className="h-4 w-4" />Prețuri</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3">
            <Field label="Preț cerut" value={fmtEur(record.client_asking_price_eur)} />
            <Field
              label="Ofertă curentă"
              value={
                offer
                  ? `${fmtEur(offer.amount_eur)} (${DECISION_LABEL[offer.client_decision] ?? offer.client_decision})`
                  : null
              }
            />
            {record.status === 'BOUGHT' && <Field label="Preț achiziție" value={fmtEur(record.purchase_price_eur)} />}
            <Field label="Cost recondiționare" value={fmtEur(record.reconditioning_cost_eur)} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2"><Wrench className="h-4 w-4" />Inspecție</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3">
            <Field label="Rating" value={record.inspection_rating != null ? `${record.inspection_rating}/5` : null} />
            <Field label="Cost recondiționare" value={fmtEur(record.reconditioning_cost_eur)} />
            <div className="col-span-2">
              <Field label="Notițe inspecție" value={record.inspection_notes} />
            </div>
            <div className="col-span-2">
              <p className="text-xs text-muted-foreground">Raport</p>
              {record.inspection_report_key ? (
                <a
                  href={mediaUrl(record.inspection_report_key)}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
                >
                  <FileText className="h-3.5 w-3.5" />Vezi raportul
                </a>
              ) : (
                <p className="text-sm">—</p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2"><Camera className="h-4 w-4" />Poze</CardTitle>
        </CardHeader>
        <CardContent>
          <PhotoGallery recordId={recordId} photos={photos} canEdit={canEditPhotos} />
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2"><Clock className="h-4 w-4" />Istoric</CardTitle>
          </CardHeader>
          <CardContent>
            {!events.length ? (
              <p className="text-sm text-muted-foreground">Niciun eveniment</p>
            ) : (
              <ul className="space-y-3">
                {events.map((ev) => (
                  <li key={ev.id} className="flex gap-3 text-sm">
                    <div className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                    <div>
                      <p className="font-medium">{eventLabel(ev)}</p>
                      <p className="text-xs text-muted-foreground">{fmtDateTime(ev.created_at)}</p>
                      {eventDetail(ev) && <p className="text-xs text-muted-foreground">{eventDetail(ev)}</p>}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <ActionPanel record={record} offers={offers} />
      </div>
    </div>
  )
}
