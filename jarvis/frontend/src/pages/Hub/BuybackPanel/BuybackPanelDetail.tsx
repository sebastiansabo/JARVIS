import { useQuery } from '@tanstack/react-query'
import { ChevronLeft } from 'lucide-react'
import { buybackApi } from '@/api/buyback'
import { recordStatus } from '@/pages/BuyBack/recordStatus'
import { pickLatestOffer } from '@/pages/BuyBack/offerUtils'
import { mediaUrl } from '@/lib/media'
import type { BuybackPhoto } from '@/types/buyback'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import BuybackOffersPanel from '@/pages/Hub/BuybackPanel/BuybackOffersPanel'

const DECISION_LABEL: Record<string, string> = {
  pending: 'În așteptare',
  accepted: 'Acceptată',
  declined: 'Refuzată',
}

/** cdn edge url first, else the /api/media proxy (data:/http pass through
 *  mediaUrl untouched). Mirrors PhotoGallery's photoSrc + mobile Detail. */
function photoSrc(p: BuybackPhoto): string {
  return p.cdn_url || mediaUrl(p.thumbnail_url || p.url)
}

function toLabel(list: { value: string; label: string }[] | undefined, value: string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  return list?.find((o) => o.value === value)?.label ?? value
}

function rawEquipment(v: string | null | undefined): string {
  if (!v) return '—'
  const parts = v.split(',').map((s) => s.trim()).filter(Boolean)
  return parts.length ? parts.join(', ') : '—'
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

function fmtEur(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return `${v.toLocaleString('ro-RO')} €`
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1">
      <span className="shrink-0 text-sm text-muted-foreground">{label}</span>
      <span className="break-words text-right text-sm font-medium">{value}</span>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border bg-card p-4">
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</p>
      {children}
    </section>
  )
}

/** In-panel BuyBack detail for the Hub launcher — the read-only summary
 *  (vehicle / seller / prices / photos) mirroring the mobile app's Detail
 *  screen. Offer/decision actions are added by BuybackOffersPanel. The full
 *  console (inspection / finalize / reopen / edit) stays at /app/buyback/:id. */
export default function BuybackPanelDetail({ id, onBack }: { id: number; onBack: () => void }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['buyback-record', id],
    queryFn: () => buybackApi.getRecord(id),
    staleTime: 30_000,
  })
  const { data: lookups } = useQuery({
    queryKey: ['buyback-options'],
    queryFn: () => buybackApi.getLookupOptions(),
    staleTime: 300_000,
  })

  const header = (title: string, subtitle?: React.ReactNode, badge?: React.ReactNode) => (
    <div className="flex items-center gap-3">
      <Button variant="ghost" size="sm" onClick={onBack}>
        <ChevronLeft className="mr-1 h-4 w-4" />
        Înapoi
      </Button>
      <div className="min-w-0 flex-1">
        <h2 className="truncate text-base font-semibold">{title}</h2>
        {subtitle && <p className="truncate font-mono text-xs text-muted-foreground">{subtitle}</p>}
      </div>
      {badge}
    </div>
  )

  if (isLoading) {
    return (
      <div className="space-y-4">
        {header('BuyBack')}
        <div className="flex justify-center py-12">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-foreground" />
        </div>
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="space-y-4">
        {header('BuyBack')}
        <p className="py-12 text-center text-sm text-destructive">Solicitare negăsită</p>
      </div>
    )
  }

  const { record, offers, photos } = data
  const status = recordStatus(record.status)
  const currentOffer = pickLatestOffer(offers)

  return (
    <div className="space-y-4">
      {header(
        `${record.brand} ${record.model}`,
        record.record_code,
        <Badge className={status.badgeClass}>{status.label}</Badge>
      )}

      <div className="space-y-3">
        <BuybackOffersPanel id={id} record={record} offers={offers} />

        <Section title="Vehicul">
          <Field label="Marca" value={record.brand || '—'} />
          <Field label="Model" value={record.model || '—'} />
          <Field label="Varianta" value={record.variant || '—'} />
          <Field label="Echipare" value={rawEquipment(record.equipment)} />
          <Field label="VIN" value={<span className="font-mono">{record.vin || '—'}</span>} />
          <Field label="Rulaj (km)" value={record.mileage_km != null ? record.mileage_km.toLocaleString('ro-RO') : '—'} />
          <Field label="Capacitate cilindrică (cm³)" value={record.engine_capacity_cm3 ?? '—'} />
          <Field label="Combustibil" value={toLabel(lookups?.fuel_types, record.fuel_type)} />
          <Field label="Transmisie" value={toLabel(lookups?.transmissions, record.transmission)} />
          <Field label="Cutie de viteze" value={toLabel(lookups?.gearboxes, record.gearbox)} />
          <Field label="Data fabricație" value={fmtDate(record.manufacture_date)} />
          <Field label="Data prima înmatriculare" value={fmtDate(record.first_registration_date)} />
          <Field label="Istoric service la zi" value={yesNo(record.service_history_uptodate)} />
          <Field label="Roți extra" value={yesNo(record.extra_wheels)} />
          <Field label="Nr. chei" value={record.keys_count ?? '—'} />
          <Field label="Condiție generală" value={record.general_condition != null ? `${record.general_condition}/5` : '—'} />
          <Field label="Daune" value={yesNo(record.has_damage)} />
          {record.has_damage && <Field label="Detalii daune" value={record.damage_details || '—'} />}
        </Section>

        <Section title="Vânzător & Trade-in">
          <Field label="Tip client" value={toLabel(lookups?.client_types, record.client_type)} />
          <Field label="Status TVA" value={toLabel(lookups?.vat_statuses, record.vat_status)} />
          <Field label="Nume vânzător" value={record.seller_name || '—'} />
          <Field label="Email" value={record.seller_email || '—'} />
          <Field label="Telefon" value={record.seller_phone || '—'} />
          <Field label="CUI" value={record.seller_cui || '—'} />
          <Field label="Trade-in" value={yesNo(record.is_trade_in)} />
          {record.is_trade_in && <Field label="Vehicul țintă" value={record.target_vehicle_text || '—'} />}
        </Section>

        <Section title="Prețuri">
          <Field label="Preț cerut" value={fmtEur(record.client_asking_price_eur)} />
          <Field
            label="Ofertă curentă"
            value={
              currentOffer
                ? `${fmtEur(currentOffer.amount_eur)} (${DECISION_LABEL[currentOffer.client_decision] ?? currentOffer.client_decision})`
                : '—'
            }
          />
          {record.status === 'BOUGHT' && <Field label="Preț achiziție" value={fmtEur(record.purchase_price_eur)} />}
        </Section>

        <Section title="Poze">
          {photos.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nicio poză</p>
          ) : (
            <div className="grid grid-cols-4 gap-2">
              {photos.map((p) => {
                const src = photoSrc(p)
                return src ? (
                  <img key={p.id} src={src} alt="" className="aspect-square w-full rounded-md border object-cover" />
                ) : null
              })}
            </div>
          )}
        </Section>
      </div>
    </div>
  )
}
