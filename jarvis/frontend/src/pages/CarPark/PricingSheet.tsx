import { useMemo, useState } from 'react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import {
  type EngineParams,
  type VatRegime,
  econ,
  breakevenPrice,
  priceForProfit,
  maxPurchasePrice,
} from './pricingEngine'

// Tenant settings (spec §3.2) — defaults for this slice; to move to real settings.
const STANDARD_VAT = 21
const WARRANTY_RESERVE_PCT = 1.5

// ── Versioned pricing sheet (Fișă de preț) ────────────────────────────────
// The editable inputs the user chose; a sheet snapshot wraps these with an
// id/status/dates. `list_price`/`promotional_price` are the published prices.
export interface SheetInputs {
  list_price: number | null
  promotional_price: number | null
  price_currency: string
  target: number
  finRate: number
  targetDays: number
  warrantyPct: number
  anchor: number
  comps: number | null
  anchorDate: string
}

export interface PricingSheetSnapshot extends SheetInputs {
  id: string
  status: 'draft' | 'published'
  created_at: string
  published_at: string | null
  // Derived at save time so the history table renders without re-running the engine.
  breakeven?: number
  critic?: number
}

// The engine-relevant inputs (subset of SheetInputs, prices excluded).
export interface PricingInputs {
  target: number
  finRate: number
  targetDays: number
  warrantyPct: number
  anchor: number
  comps: number | null
  anchorDate: string
}

const STAGES = [
  { d: 'Zi 0–14', adj: 0, act: 'Preț listă full. Fără promo.' },
  { d: 'Zi 15–30', adj: -0.015, act: '−1,5%. Alertă achizitor, re-verificare ancoră.' },
  { d: 'Zi 31–45', adj: -0.03, act: '−3%. Activare promo, refacere anunț.' },
  { d: 'Zi 46–60', adj: -0.05, act: '−5%. Critic devine ținta de negociere.' },
  { d: 'Zi 61–90', adj: -0.08, act: '−8%. Revizuire management. Exit pregătit.' },
  { d: 'Zi 90+', adj: -0.09, act: 'Cea mai bună ofertă ≥ breakeven. Exit.' },
]
const STAGE_START = [0, 15, 31, 46, 61, 91]
const stageIndex = (d: number) => (d <= 14 ? 0 : d <= 30 ? 1 : d <= 45 ? 2 : d <= 60 ? 3 : d <= 90 ? 4 : 5)

type FormLike = Record<string, unknown>
type Line = { eur: number | null }

const num = (v: unknown) => (typeof v === 'number' ? v : Number(v) || 0)
const nf = (v: number) => new Intl.NumberFormat('ro-RO').format(Math.round(v))
const fmtEur = (v: number) => `${nf(v)} €`
const fmtPct = (v: number) => `${v < 0 ? '−' : ''}${new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(Math.abs(v) * 100)}%`
const money = (v: number) => `${v < 0 ? '−' : ''}${fmtEur(Math.abs(v))}`

export type PricingModel = ReturnType<typeof computePricingModel>

// Pure engine model for a vehicle + one set of inputs. Shared by the editor
// (live inputs) and the standalone Zona de preț (fed from the last saved fișă).
export function computePricingModel(form: FormLike, costLines: Line[], inp: PricingInputs) {
  const { target, finRate, targetDays, warrantyPct, anchor, comps, anchorDate } = inp
  const regime: VatRegime = form.vat_deductible === false ? 'MARGIN' : 'NORMAL'
  // The purchase VAT (from the Achiziție card) is what was paid. In MARGIN it's
  // non-deductible; the resale margin is taxed at the standard rate.
  const purchaseVatRate = num(form.purchase_vat_rate) || STANDARD_VAT
  const vatRate = regime === 'MARGIN' ? STANDARD_VAT : purchaseVatRate
  const curs = num(form.acquisition_exchange_rate)
  const netLei = num(form.acquisition_price)
  let netEur = curs > 0 ? netLei / curs : 0
  let grossEur = netEur * (1 + purchaseVatRate / 100) // what was actually paid
  // Fallback: cars with only `purchase_price_net` (the GROSS EUR paid) and no
  // acquisition_price/kurs still get a basis, so the Fișă/Zona never blank out.
  if (netEur <= 0) {
    grossEur = num(form.purchase_price_net)
    netEur = purchaseVatRate > 0 ? grossEur / (1 + purchaseVatRate / 100) : grossEur
  }
  // Cost basis: MARGIN keeps the non-deductible VAT in the cost (gross); NORMAL
  // reclaims the input VAT, so only the net is a real cost.
  const costBasisEur = regime === 'MARGIN' ? grossEur : netEur
  const inputVatEur = regime === 'NORMAL' ? grossEur - netEur : 0

  const toEur = (v: unknown) => {
    const p = num(v)
    if (p <= 0) return 0
    return (form.price_currency as string) === 'RON' && curs > 0 ? p / curs : p
  }
  const listEur = toEur(form.list_price)
  const promoEur = toEur(form.promotional_price)

  const costLinesEur = costLines.reduce((s, l) => s + num(l.eur), 0)
  const financingEur = costBasisEur * (finRate / 100) * targetDays
  const warrantyEur = listEur * (warrantyPct / 100)
  const landedCostEur = costBasisEur + costLinesEur + financingEur + warrantyEur

  const params: EngineParams = { regime, vatRate, landedCostEur, purchaseGrossEur: grossEur, inputVatEur }
  const be = breakevenPrice(params)
  const critic = priceForProfit(target, params)

  let realDays = 0
  const ds = form.acquisition_date as string
  if (ds) {
    const d = new Date(ds)
    if (!Number.isNaN(d.getTime())) realDays = Math.max(0, Math.round((Date.now() - d.getTime()) / 86400000))
  }

  // Comparables count: null (not entered) is NOT zero — the band is undefined
  // until a real number is given, and only an actual count < 5 is a thin segment.
  const compsMissing = comps == null
  const band = compsMissing
    ? null
    : comps < 5 ? { t: 'segment subțire · listă 100–105%', mul: 1.025 }
      : comps <= 15 ? { t: 'segment normal · listă 97–100%', mul: 0.985 }
        : { t: 'marfă de volum · listă 93–97%', mul: 0.95 }
  const negBuf = form.is_negotiable === false ? 1 : 1.03
  const anchorReady = anchor > 0 && band != null
  const anchorEff = anchorReady ? anchor * band!.mul : 0
  const suggested = anchorReady ? anchor * band!.mul * negBuf * (1 + STAGES[stageIndex(realDays)].adj) : 0
  const mb = anchorReady
    ? maxPurchasePrice({ regime, vatRate, anchorEffectiveEur: anchorEff, manualCostLinesEur: costLinesEur, financingFactor: (finRate / 100) * targetDays, warrantyPct: warrantyPct / 100, profitTarget: target })
    : null

  // Anchor freshness — the median is worthless without a date; warn past 30 days.
  let anchorAge: number | null = null
  if (anchorDate) {
    const ad = new Date(anchorDate)
    if (!Number.isNaN(ad.getTime())) anchorAge = Math.max(0, Math.round((Date.now() - ad.getTime()) / 86400000))
  }
  const anchorStale = anchorAge != null && anchorAge > 30
  const anchorDateMissing = anchor > 0 && !anchorDate

  return {
    regime, vatRate, curs, netEur, grossEur, costBasisEur, landedCostEur, financingEur, warrantyEur, costLinesEur,
    listEur, promoEur, be, critic, band, compsMissing, anchorReady, anchorEff, suggested, mb,
    anchorAge, anchorStale, anchorDateMissing, params, negBuf, hasBasis: costBasisEur > 0,
    realDays, anchor, finRate,
  }
}

export function PricingSheet({
  form,
  costLines,
  editable = false,
  locked = false,
  initial,
  onPriceChange,
  onSaveDraft,
  onPublish,
  saving = false,
}: {
  form: FormLike
  costLines: Line[]
  editable?: boolean
  /** Read-only: the active sheet is published and past its 24h edit window. */
  locked?: boolean
  /** Seed the engine params/prices from the active sheet. */
  initial?: Partial<SheetInputs>
  onPriceChange?: (field: 'list_price' | 'promotional_price', value: number | null) => void
  onSaveDraft?: (inputs: SheetInputs, derived: { breakeven: number; critic: number }) => void
  onPublish?: (inputs: SheetInputs, derived: { breakeven: number; critic: number }) => void
  saving?: boolean
}) {
  const [target, setTarget] = useState(initial?.target ?? 600)
  const [finRate, setFinRate] = useState(initial?.finRate ?? 0.05) // %/day
  const [targetDays, setTargetDays] = useState(initial?.targetDays ?? 45)
  const [warrantyPct, setWarrantyPct] = useState(initial?.warrantyPct ?? WARRANTY_RESERVE_PCT)
  const [anchor, setAnchor] = useState(initial?.anchor ?? 0)
  const [comps, setComps] = useState<number | null>(initial?.comps ?? null) // null = not entered (≠ 0)
  const [anchorDate, setAnchorDate] = useState(initial?.anchorDate ?? '')

  const ro = !editable || locked // inputs read-only

  const m = useMemo(
    () => computePricingModel(form, costLines, { target, finRate, targetDays, warrantyPct, anchor, comps, anchorDate }),
    [form, costLines, target, finRate, targetDays, warrantyPct, anchor, comps, anchorDate],
  )

  if (!m.hasBasis) {
    return (
      <Card className="p-4 text-sm text-muted-foreground">
        Fișa de preț — introdu prețul de achiziție și cursul pentru calcule.
      </Card>
    )
  }

  const { params, listEur, promoEur, be, critic } = m
  const L = listEur > 0 ? econ(listEur, params) : null
  const P = promoEur > 0 ? econ(promoEur, params) : null
  const negotiation = listEur > 0 ? listEur - critic : 0
  const bad = 'text-red-600 dark:text-red-400'
  const profitCls = (v: number) => (v >= target ? 'text-emerald-600 dark:text-emerald-400' : v >= 0 ? 'text-amber-600 dark:text-amber-400' : bad)

  const buildInputs = (): SheetInputs => ({
    list_price: num(form.list_price) || null,
    promotional_price: num(form.promotional_price) || null,
    price_currency: (form.price_currency as string) || 'EUR',
    target, finRate, targetDays, warrantyPct, anchor, comps, anchorDate,
  })
  // Publishing needs only a list price; comparables just refine the anchor band.
  const publishBlocked = listEur <= 0

  // Acquisition breakdown for the info card — `grossEur` is what was paid
  // (VAT-inclusive), `netEur` the VAT-exclusive base; the fișă cost basis is
  // gross for MARGIN (VAT non-deductible), net for NORMAL.
  const pvr = num(form.purchase_vat_rate) || 0
  const acqGross = m.grossEur
  const acqNet = m.netEur
  const acqVat = Math.max(0, acqGross - acqNet)

  // Save/publish actions — hoisted into the fișă header, inline with the title
  // and the TVA badge. `saveButtons` is just the two buttons; the explanatory
  // note stays with the price inputs below.
  const saveButtons = editable && !locked ? (
    <>
      <Button type="button" variant="outline" size="sm" onClick={() => onSaveDraft?.(buildInputs(), { breakeven: be, critic })} disabled={saving}>
        {saving ? 'Se salvează…' : 'Salvează ciornă'}
      </Button>
      <Button type="button" size="sm" onClick={() => onPublish?.(buildInputs(), { breakeven: be, critic })} disabled={saving || publishBlocked}>
        {saving ? 'Se salvează…' : 'Publică prețul'}
      </Button>
    </>
  ) : null

  // Pricing-specific KPIs only. Marjă netă / Zile în stoc live in the page-level
  // strip; breakeven/critic/listă are owned by the Zona ladder — Breakeven is
  // kept here as the single numeric echo.
  const tiles = [
    { t: 'Profit net (listă)', v: L ? money(L.profitNet) : '—', s: `la critic: ${money(econ(critic, params).profitNet)}`, cls: L ? profitCls(L.profitNet) : '' },
    { t: 'Marjă negociere', v: money(negotiation), s: listEur > 0 ? `${fmtPct(negotiation / listEur)} din listă` : '', cls: negotiation >= 0 ? '' : bad },
    { t: 'TVA de plată', v: L ? fmtEur(Math.max(0, L.vatDue)) : '—', s: m.regime === 'MARGIN' ? 'regim marjă · pe spread' : 'TVA normal' },
    { t: 'Breakeven', v: fmtEur(be), s: `critic ${fmtEur(critic)} · țintă ${fmtEur(target)}` },
  ]

  return (
    <div className="space-y-4">
      {/* KPI tiles */}
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border lg:grid-cols-4">
        {tiles.map((k) => (
          <div key={k.t} className="bg-card p-3">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{k.t}</div>
            <div className={`mt-1 text-lg font-semibold tabular-nums ${k.cls}`}>{k.v}</div>
            {k.s && <div className="mt-0.5 text-[11px] text-muted-foreground tabular-nums">{k.s}</div>}
          </div>
        ))}
      </div>

      {/* Breakdown + derived + params + anchor */}
      <Card className="p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">Fișa de preț</h3>
          <div className="flex flex-wrap items-center gap-2">
            {saveButtons}
            <Badge variant="outline" className="uppercase">{m.regime === 'MARGIN' ? 'Regim marjă · art. 312' : 'TVA normal'}</Badge>
          </div>
        </div>

        {editable && (
          <div className="mb-4 space-y-3 border-b pb-3">
            <div className="grid items-end gap-3 sm:grid-cols-2">
              <NumField label={`Preț listă (${(form.price_currency as string) || 'EUR'})`} value={num(form.list_price)} step={10} disabled={locked} onChange={(v) => onPriceChange?.('list_price', v || null)} />
              <NumField label={`Preț promo (${(form.price_currency as string) || 'EUR'})`} value={num(form.promotional_price)} step={10} disabled={locked} onChange={(v) => onPriceChange?.('promotional_price', v || null)} placeholder="opțional" />
            </div>
            {locked ? (
              <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
                Fișă blocată — editabilă doar 24h după publicare. Deschideți o fișă nouă pentru a modifica prețul.
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                {publishBlocked && <span>Adăugați prețul de listă pentru a publica.</span>}
                <span>Ciorna nu setează prețul mașinii; publicarea da.</span>
              </div>
            )}
          </div>
        )}

        {/* Achiziție — what was paid + the cost basis the fișă uses. */}
        <div className="mb-4 rounded-md border bg-muted/30 p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Achiziție</span>
            <Badge variant="outline" className="text-[10px] uppercase">{m.regime === 'MARGIN' ? 'TVA nedeductibil' : 'TVA deductibil'}</Badge>
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs tabular-nums sm:grid-cols-4">
            <div><dt className="text-muted-foreground">Preț achiziție (brut)</dt><dd className="font-semibold">{fmtEur(acqGross)}</dd></div>
            <div><dt className="text-muted-foreground">din care TVA{pvr ? ` (${pvr}%)` : ''}</dt><dd className="font-medium">{fmtEur(acqVat)}</dd></div>
            <div><dt className="text-muted-foreground">Net achiziție</dt><dd className="font-medium">{fmtEur(acqNet)}</dd></div>
            <div><dt className="text-muted-foreground">Curs</dt><dd className="font-medium">{m.curs > 0 ? new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 4, maximumFractionDigits: 4 }).format(m.curs) : '—'}</dd></div>
          </dl>
          <div className="mt-2 flex items-baseline justify-between border-t pt-2 text-xs">
            <span className="text-muted-foreground">Bază cost folosită în fișă {m.regime === 'MARGIN' ? '(brut — regim marjă)' : '(net — TVA dedus)'}</span>
            <b className="tabular-nums">{fmtEur(m.costBasisEur)}</b>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <Breakdown title="La preț listă" e={L} landed={params.landedCostEur} target={target} />
          <Breakdown title="La preț promo" e={P} landed={params.landedCostEur} target={target} />
        </div>
        {/* Cost composition — makes the "other costs" transparent (financing + warranty are computed, not manual) */}
        <div className="mt-3 border-t pt-3">
          <div className="mb-1 text-xs font-semibold">Compoziție cost total (landed)</div>
          <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 text-xs tabular-nums">
            <dt className="text-muted-foreground">Bază cost (net)</dt>
            <dd className="text-right font-medium">{fmtEur(m.costBasisEur)}</dd>
            {m.costLinesEur > 0 && (
              <>
                <dt className="text-muted-foreground">Costuri manuale (linii)</dt>
                <dd className="text-right font-medium">{fmtEur(m.costLinesEur)}</dd>
              </>
            )}
            <dt className="text-muted-foreground">Cost finanțare <span className="text-muted-foreground/60">({new Intl.NumberFormat('ro-RO', { maximumFractionDigits: 2 }).format(finRate)}%/zi × {targetDays} zile × bază)</span></dt>
            <dd className="text-right font-medium">{fmtEur(m.financingEur)}</dd>
            <dt className="text-muted-foreground">Rezervă garanție <span className="text-muted-foreground/60">({new Intl.NumberFormat('ro-RO', { maximumFractionDigits: 2 }).format(warrantyPct)}% × preț listă)</span></dt>
            <dd className="text-right font-medium">{fmtEur(m.warrantyEur)}</dd>
            <dt className="border-t pt-1 font-semibold">Cost total (landed, net)</dt>
            <dd className="border-t pt-1 text-right font-semibold">{fmtEur(m.landedCostEur)}</dd>
          </dl>
        </div>
        <div className="mt-4 grid gap-3 border-t pt-3 sm:grid-cols-3">
          <NumField label="Profit țintă (€)" value={target} step={50} disabled={ro} onChange={setTarget} />
          <NumField label="Finanțare %/zi" value={finRate} step={0.01} disabled={ro} onChange={setFinRate} />
          <NumField label="Rezervă garanție %" value={warrantyPct} step={0.5} disabled={ro} onChange={setWarrantyPct} />

          <NumField label="Zile țintă" value={targetDays} step={5} disabled={ro} onChange={setTargetDays} />
          {/* Piața — the market's asking price for this car, not ours. */}
          <NumField label="Preț mediu Piață (€)" value={anchor} step={50} disabled={ro} onChange={setAnchor} placeholder="mediană anunțuri" />
          <div className="space-y-1">
            <Label className="text-xs">Nr anunțuri Auto similare</Label>
            <Input type="number" step={1} min={0} value={comps ?? ''} placeholder="introduceți" disabled={ro}
              onChange={(e) => setComps(e.target.value === '' ? null : Number(e.target.value))} />
            <p className={`text-[10px] ${m.compsMissing ? 'text-red-600 dark:text-red-400' : 'text-muted-foreground'}`}>
              {m.compsMissing ? 'Introduceți nr. anunțuri (obligatoriu pentru publicare)' : m.band?.t}
            </p>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Data preț mediu</Label>
            <Input type="date" value={anchorDate} disabled={ro} onChange={(e) => setAnchorDate(e.target.value)} />
            <p className={`text-[10px] ${m.anchorDateMissing || m.anchorStale ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground'}`}>
              {m.anchorDateMissing ? 'Adăugați data — ancora fără dată nu e de încredere'
                : m.anchorAge == null ? 'Data la care a fost cules prețul mediu'
                : m.anchorStale ? `Veche de ${m.anchorAge} zile — reîmprospătați comparabilele`
                : `Acum ${m.anchorAge} zile`}
            </p>
          </div>
        </div>
        {m.mb && (
          <div className={`mt-3 rounded-md border px-3 py-2 text-xs ${m.netEur > m.mb.net ? 'border-red-300 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300' : 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300'}`}>
            <b>Preț maxim achiziție</b> pentru țintă {fmtEur(target)} la ancoră: <b>{fmtEur(m.mb.net)}</b>
            {m.regime === 'NORMAL' && ` (${fmtEur(m.mb.gross)} brut)`} ·{' '}
            {m.netEur > m.mb.net ? `achiziția depășește plafonul cu ${fmtEur(m.netEur - m.mb.net)}.` : `marjă față de plafon: ${fmtEur(m.mb.net - m.netEur)}.`}
            {m.suggested > 0 && <> · Sugerat azi: <b>{fmtEur(Math.round(m.suggested / 10) * 10)}</b>.</>}
          </div>
        )}
        {/* Save/publish also here, under the max-bid box, so the user can act
            without scrolling back to the header. */}
        {saveButtons && (
          <div className="mt-4 flex flex-wrap items-center gap-2 border-t pt-3">
            {saveButtons}
            <span className="text-[11px] text-muted-foreground">Ciorna nu setează prețul mașinii; publicarea da.</span>
          </div>
        )}
      </Card>
    </div>
  )
}

/** Standalone "Zona de preț" — always on top of the Pricing tab, fed by the
 *  last saved fișă (via a PricingModel). Holds its own day-simulation state. */
export function PriceZone({ model: m }: { model: PricingModel }) {
  const [daysOverride, setDaysOverride] = useState<number | null>(null)
  if (!m.hasBasis) return null

  const { grossEur, landedCostEur, be, critic, listEur, anchor, regime, costBasisEur, finRate } = m
  const days = daysOverride == null ? m.realDays : daysOverride
  const si = stageIndex(days)
  const negotiation = listEur > 0 ? listEur - critic : 0

  return (
    <Card className="p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Zona de preț</h3>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>Simulează zile</span>
          <input type="range" min={0} max={120} step={1} value={Math.min(120, days)} onChange={(e) => setDaysOverride(Number(e.target.value))} className="w-40 accent-blue-500" aria-label="Zile în stoc" />
          <b className="min-w-[56px] tabular-nums text-foreground">{days} zile</b>
          <button type="button" onClick={() => setDaysOverride(null)} className="rounded border px-2 py-0.5 hover:bg-muted">azi</button>
          <Badge variant="outline" className={si >= 4 ? 'border-red-400 text-red-600 dark:text-red-400' : si >= 2 ? 'border-amber-400 text-amber-600 dark:text-amber-400' : 'border-emerald-400 text-emerald-600 dark:text-emerald-400'}>
            {STAGES[si].d} · {STAGES[si].adj ? fmtPct(STAGES[si].adj) : 'full'}
          </Badge>
        </div>
      </div>
      <PriceLadder achiz={grossEur} cost={landedCostEur} be={be} critic={critic} lista={listEur} anchor={anchor} regime={regime} />
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {STAGES.map((s, i) => (
          <button
            key={s.d}
            type="button"
            onClick={() => setDaysOverride(STAGE_START[i])}
            className={`rounded-md border p-2 text-left text-[11px] leading-snug ${i === si ? 'border-blue-400 bg-blue-50 dark:bg-blue-950/40' : 'hover:bg-muted'}`}
          >
            <b className="block text-xs tabular-nums">{s.d}{m.anchorReady && m.band ? ` · ${fmtEur(Math.round(anchor * m.band.mul * m.negBuf * (1 + s.adj) / 10) * 10)}` : ''}</b>
            <span className="text-muted-foreground">{s.act}</span>
            <div className="mt-0.5 text-[10px] text-muted-foreground">{i === si ? `← acum, ziua ${days}` : 'click pentru simulare'}</div>
          </button>
        ))}
      </div>
      <p className="mt-3 text-[11px] text-muted-foreground">
        Marjă de negociere protejată: {money(negotiation)}. Cost de a ține mașina încă 45 zile (finanțare + ~1,75%/lună depreciere): ≈ {fmtEur(costBasisEur * (finRate / 100) * 45 + listEur * 0.0175 * 1.5)}.
      </p>
    </Card>
  )
}

function NumField({ label, value, step, onChange, placeholder, hint, disabled }: {
  label: string; value: number; step: number; onChange: (v: number) => void; placeholder?: string; hint?: string; disabled?: boolean
}) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <Input type="number" step={step} value={value || ''} placeholder={placeholder} disabled={disabled} onChange={(e) => onChange(Number(e.target.value) || 0)} className="h-9" />
      {hint && <p className="text-[10px] text-muted-foreground">{hint}</p>}
    </div>
  )
}

function Breakdown({ title, e, landed, target }: {
  title: string; e: ReturnType<typeof econ> | null; landed: number; target: number
}) {
  if (!e) return (
    <div>
      <div className="mb-1 text-xs font-semibold">{title}</div>
      <div className="text-sm text-muted-foreground">fără preț</div>
    </div>
  )
  const cls = e.profitNet >= target ? 'text-emerald-600 dark:text-emerald-400' : e.profitNet >= 0 ? 'text-amber-600 dark:text-amber-400' : 'text-red-600 dark:text-red-400'
  const rows: [string, string, string?][] = [
    ['Net încasat', fmtEur(e.netRevenue)],
    ['TVA de plată', `−${fmtEur(Math.max(0, e.vatDue))}`, 'text-red-600 dark:text-red-400'],
    ['Cost total', `−${fmtEur(landed)}`, 'text-red-600 dark:text-red-400'],
    ['Profit net', money(e.profitNet), cls],
    ['Marjă netă · Adaos', `${fmtPct(e.marginNet)} · ${fmtPct(e.markup)}`, cls],
  ]
  return (
    <div>
      <div className="mb-1 text-xs font-semibold">{title} · {fmtEur(e.price)}</div>
      <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 text-xs tabular-nums">
        {rows.map(([k, v, c]) => (
          <div key={k} className="contents">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className={`text-right font-medium ${c ?? ''}`}>{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

/** Horizontal price band with staggered labels, zones, anchor marker and negotiation bracket. */
function PriceLadder({ achiz, cost, be, critic, lista, anchor, regime }: {
  achiz: number; cost: number; be: number; critic: number; lista: number; anchor: number; regime: VatRegime
}) {
  const vals = [achiz, cost, be, critic, lista, anchor].filter((v) => v > 0)
  if (vals.length < 2) return <div className="text-xs text-muted-foreground">Date insuficiente pentru scară.</div>
  const lo = Math.min(...vals) * 0.97
  const hi = Math.max(...vals) * 1.03
  const x = (v: number) => 30 + ((v - lo) / (hi - lo)) * 940
  const Xb = x(be), Xk = x(critic), Xl = lista > 0 ? x(lista) : Xk
  const bandTop = 76, bandH = 46
  const zones: [number, number, string, string, string][] = [
    [30, Xb, 'fill-red-500/15', 'PIERDERE', 'fill-red-600 dark:fill-red-400'],
    [Xb, Xk, 'fill-amber-500/15', 'SUB PRAG', 'fill-amber-600 dark:fill-amber-400'],
    [Xk, Math.max(Xk, Xl), 'fill-emerald-500/15', 'ZONĂ SĂNĂTOASĂ', 'fill-emerald-600 dark:fill-emerald-400'],
    [Math.max(Xk, Xl), 970, 'fill-muted', 'PESTE PIAȚĂ', 'fill-muted-foreground'],
  ]
  // `short` is used when several markers collapse onto one price (same value ⇒
  // same x); a lone marker keeps its `full` descriptive name.
  const above: { x: number; full: string; short: string; val: number }[] = [
    { x: x(achiz), full: regime === 'NORMAL' ? 'Preț achiziție (brut)' : 'Preț achiziție', short: 'Achiziție', val: achiz },
    { x: Xb, full: 'Breakeven', short: 'Breakeven', val: be },
    { x: Xk, full: 'Preț critic', short: 'Critic', val: critic },
  ]
  if (lista > 0) above.push({ x: Xl, full: 'Preț listă', short: 'Listă', val: lista })
  return (
    <div className="overflow-x-auto">
      <svg viewBox="0 -28 1000 228" className="h-auto w-full min-w-[720px]" role="img" aria-label="Scara de preț">
        {(() => {
          // Render zone labels only when the zone is wide enough AND far enough
          // from the previous label — avoids overlap when zones collapse (e.g.
          // an underwater car where breakeven sits above the list price).
          let lastLabelX = -Infinity
          return zones.map(([x0, x1, fill, label, tcls], i) => {
            if (x1 <= x0) return null
            const cx = (x0 + x1) / 2
            const showLabel = x1 - x0 > 70 && cx - lastLabelX > 96
            if (showLabel) lastLabelX = cx
            return (
              <g key={i}>
                <rect x={x0} y={bandTop} width={Math.max(0, x1 - x0)} height={bandH} className={fill} />
                {showLabel && (
                  <text x={cx} y={bandTop + 27} textAnchor="middle" className={`${tcls} text-[9.5px] font-bold tracking-widest`}>{label}</text>
                )}
              </g>
            )
          })
        })()}
        <rect x={30} y={bandTop} width={940} height={bandH} fill="none" className="stroke-border" />
        {(() => {
          // First MERGE markers that round to the same price (identical x) — e.g.
          // achiz = breakeven = critic when there are no added costs and no
          // target — so three identical labels become one. Then stagger the
          // survivors across up to 3 levels (30px apart, fits a name+value block)
          // for any near-but-distinct prices. The viewBox has top headroom so the
          // highest level is never clipped.
          const byVal = new Map<number, { x: number; val: number; parts: string[]; full: string }>()
          for (const mk of above) {
            const key = Math.round(mk.val)
            const g = byVal.get(key)
            if (g) g.parts.push(mk.short)
            else byVal.set(key, { x: mk.x, val: mk.val, parts: [mk.short], full: mk.full })
          }
          const merged = [...byVal.values()].map((g) => ({
            x: g.x, val: g.val, label: g.parts.length === 1 ? g.full : g.parts.join(' · '),
          }))
          const lvlY = [44, 14, -16]
          const lastX = [-Infinity, -Infinity, -Infinity]
          const level: number[] = []
          for (const idx of merged.map((_, i) => i).sort((p, q) => merged[p].x - merged[q].x)) {
            let lvl = 0
            while (lvl < 2 && merged[idx].x - lastX[lvl] < 120) lvl++
            lastX[lvl] = merged[idx].x
            level[idx] = lvl
          }
          return merged.map((g, i) => {
            const y = lvlY[level[i]]
            return (
              <g key={g.val}>
                <line x1={g.x} y1={y + 22} x2={g.x} y2={bandTop} className="stroke-foreground" strokeWidth={1.2} />
                <text x={g.x} y={y} textAnchor="middle" className="fill-muted-foreground text-[10.5px] font-semibold">{g.label}</text>
                <text x={g.x} y={y + 15} textAnchor="middle" className="fill-foreground text-[12px] font-semibold tabular-nums">{nf(g.val)}</text>
              </g>
            )
          })
        })()}
        {/* cost total below */}
        <line x1={x(cost)} y1={bandTop + bandH} x2={x(cost)} y2={140} className="stroke-muted-foreground" strokeDasharray="3 3" />
        <text x={x(cost)} y={156} textAnchor="middle" className="fill-muted-foreground text-[11.5px] font-semibold">{regime === 'NORMAL' ? 'Cost total (net)' : 'Cost total'}</text>
        <text x={x(cost)} y={174} textAnchor="middle" className="fill-foreground text-[13px] font-semibold tabular-nums">{nf(cost)}</text>
        {/* anchor */}
        {anchor > 0 && (
          <>
            <line x1={x(anchor)} y1={70} x2={x(anchor)} y2={128} className="stroke-blue-500" strokeWidth={1.5} strokeDasharray="4 3" />
            <text x={x(anchor)} y={66} textAnchor="middle" className="fill-blue-600 dark:fill-blue-400 text-[12px] font-semibold tabular-nums">ancoră {nf(anchor)}</text>
          </>
        )}
        {/* negotiation bracket */}
        {lista > critic && (
          <>
            <path d={`M${Xk} 132 L${Xk} 144 L${Xl} 144 L${Xl} 132`} fill="none" className="stroke-blue-500" strokeWidth={1.5} />
            <text x={(Xk + Xl) / 2} y={164} textAnchor="middle" className="fill-blue-600 dark:fill-blue-400 text-[12px] font-semibold tabular-nums">negociere {nf(lista - critic)} € ({fmtPct((lista - critic) / lista)})</text>
          </>
        )}
      </svg>
    </div>
  )
}
