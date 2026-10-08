import { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Car, X, SlidersHorizontal, Check, ChevronDown, Download } from 'lucide-react'
import { buybackApi } from '@/api/buyback'
import { recordStatus, STATUS_FILTER_OPTIONS } from '@/pages/BuyBack/recordStatus'
import { pickLatestOffer } from '@/pages/BuyBack/offerUtils'
import { usePermissions } from '@/pages/BuyBack/usePermissions'
import { useAuth } from '@/hooks/useAuth'
import { mediaUrl } from '@/lib/media'
import BuyBackForm from '@/pages/BuyBack/BuyBackForm'
import BuybackPanelDetail from '@/pages/Hub/BuybackPanel/BuybackPanelDetail'
import { useHubHeaderSlot } from '@/pages/Hub/hubHeaderSlot'
import type { BuybackRecord } from '@/types/buyback'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { EmptyState } from '@/components/shared/EmptyState'
import { TableSkeleton } from '@/components/shared/TableSkeleton'
import { SearchInput } from '@/components/shared/SearchInput'
import { cn, useIsMobile, usePersistedState } from '@/lib/utils'

// BuyBack for the Hub launcher — functionally identical to the mobile app:
// a filterable list → an in-panel read-only detail with offer/decision
// actions → a "Solicitare nouă" intake overlay (reuses `BuyBackForm`). The
// full back-office console (inspection / finalize / reopen / edit) stays at
// /app/buyback. Mirrors `HubDrivingPanel`'s list↔detail↔overlay structure.
type Overlay = null | { kind: 'new' }

const DECISION_LABEL: Record<string, string> = {
  pending: 'În așteptare',
  accepted: 'Acceptată',
  declined: 'Refuzată',
}
const fmtEur = (v: number | null | undefined) => (v == null ? '—' : `${v.toLocaleString('ro-RO')} €`)

/** Expanded card body (lazy): a quick summary of a record — year, mileage,
 *  current-offer resolution, a damage/inspection report download, and a
 *  "Vezi detalii" button to the full in-panel detail. Fetches the record on
 *  expand only (for offers); specs + report key come from the list row. */
function BuybackCardSummary({ record, onOpenDetail }: { record: BuybackRecord; onOpenDetail: () => void }) {
  const { data } = useQuery({
    queryKey: ['buyback-record', record.id],
    queryFn: () => buybackApi.getRecord(record.id),
    staleTime: 30_000,
  })
  const currentOffer = pickLatestOffer(data?.offers ?? [])
  const year = (record.first_registration_date || record.manufacture_date || '').slice(0, 4) || '—'

  return (
    <div className="border-t px-3 py-2.5 text-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            <span className="text-muted-foreground">
              An: <span className="font-medium text-foreground">{year}</span>
            </span>
            <span className="text-muted-foreground">
              Rulaj:{' '}
              <span className="font-medium text-foreground">
                {record.mileage_km != null ? `${record.mileage_km.toLocaleString('ro-RO')} km` : '—'}
              </span>
            </span>
          </div>
          <div className="text-muted-foreground">
            Ofertă curentă:{' '}
            <span className="font-medium text-foreground">
              {currentOffer
                ? `${fmtEur(currentOffer.amount_eur)} · ${DECISION_LABEL[currentOffer.client_decision] ?? currentOffer.client_decision}`
                : '—'}
            </span>
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          {record.inspection_report_key && (
            <a href={mediaUrl(record.inspection_report_key)} target="_blank" rel="noreferrer">
              <Button size="sm" variant="outline">
                <Download className="mr-1 h-4 w-4" />
                Raport avarii
              </Button>
            </a>
          )}
          <Button size="sm" onClick={onOpenDetail}>
            Vezi detalii
          </Button>
        </div>
      </div>
    </div>
  )
}

export default function HubBuybackPanel() {
  const queryClient = useQueryClient()
  const [overlay, setOverlay] = useState<Overlay>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [expanded, setExpanded] = useState<Set<number>>(() => new Set())
  const [statuses, setStatuses] = useState<string[]>([])
  const [q, setQ] = useState('')
  const toggleStatus = (v: string) =>
    setStatuses((prev) => (prev.includes(v) ? prev.filter((s) => s !== v) : [...prev, v]))

  const { can } = usePermissions()
  const { user } = useAuth()
  const canCreate = can('buyback.record.create')
  const headerSlot = useHubHeaderSlot()
  const isMobile = useIsMobile()
  const [filtersOpen, setFiltersOpen] = useState(false)

  // Tenant filter (mirrors the Driving Hub): a persisted company selector.
  // `null` = not yet chosen → default to the user's own company on first
  // access; `-1` = "Toate companiile"; a positive id = a specific company.
  // The persisted value is kept across refreshes.
  const [companyId, setCompanyId] = usePersistedState<number | null>('hub-buyback-company', null)
  const { data: companiesData } = useQuery({
    queryKey: ['buyback-companies'],
    queryFn: () => buybackApi.getCompanies(),
    staleTime: 300_000,
  })
  const companies = companiesData?.companies ?? []
  useEffect(() => {
    if (companyId === null && companies.length) {
      const own = typeof user?.company_id === 'number' ? user.company_id : null
      setCompanyId(own && companies.some((c) => c.id === own) ? own : -1)
    }
  }, [companyId, companies, user?.company_id]) // eslint-disable-line react-hooks/exhaustive-deps
  const renderCompanySelect = (triggerClass: string) =>
    companies.length > 1 ? (
      <Select value={companyId == null ? undefined : String(companyId)} onValueChange={(v) => setCompanyId(Number(v))}>
        <SelectTrigger className={triggerClass}>
          <SelectValue placeholder="Companie" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="-1">Toate companiile</SelectItem>
          {companies.map((c) => (
            <SelectItem key={c.id} value={String(c.id)}>
              {c.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    ) : null

  // Inline breadcrumb controls, portaled into the Hub header slot (fallback to
  // normal flow when no slot is mounted, e.g. tests). On mobile a status-filter
  // button replaces the pill row (which stays on desktop); the filled variant
  // signals an active filter.
  const inlineActions = (
    <>
      {isMobile && (
        <Button
          variant={statuses.length ? 'default' : 'outline'}
          size="icon"
          aria-label="Filtre"
          onClick={() => setFiltersOpen(true)}
        >
          <SlidersHorizontal className="h-4 w-4" />
        </Button>
      )}
      {canCreate && (
        <Button size="icon" aria-label="Solicitare nouă" onClick={() => setOverlay({ kind: 'new' })}>
          <Plus className="h-4 w-4" />
        </Button>
      )}
    </>
  )

  const { data, isLoading, isError } = useQuery({
    queryKey: ['buyback-records', 'hub', { statuses, q, companyId }],
    queryFn: () =>
      buybackApi.listRecords({
        status: statuses.length ? statuses.join(',') : undefined,
        q: q.trim() || undefined,
        company_id: companyId && companyId > 0 ? companyId : undefined,
        // Full set — the Hub panel groups/counts client-side. Backend caps at 1000.
        per_page: 1000,
        sort_by: 'created_at',
        sort_dir: 'DESC',
      }),
    staleTime: 30_000,
  })
  const records = data?.records ?? []

  const toggleExpand = (id: number) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const closeOverlay = () => setOverlay(null)
  const handleDone = (record: BuybackRecord) => {
    queryClient.invalidateQueries({ queryKey: ['buyback-records'] })
    setOverlay(null)
    setSelectedId(record.id)
  }

  // In-panel detail (mobile parity): tapping a record opens it here rather
  // than navigating to the full /app/buyback console.
  if (selectedId != null) {
    return <BuybackPanelDetail id={selectedId} onBack={() => setSelectedId(null)} />
  }

  return (
    <div className="space-y-4">
      {headerSlot ? createPortal(inlineActions, headerSlot) : inlineActions}

      {/* Desktop: status pills + search inline on one row. Mobile: a full-width
          search here; status filtering moves to the header "Filtre" modal. */}
      {isMobile ? (
        <SearchInput
          value={q}
          onChange={setQ}
          placeholder="Caută cod, VIN, vânzător, client..."
          className="w-full [&>div]:flex-1 [&>div]:min-w-0"
        />
      ) : (
        <div className="flex flex-wrap items-center gap-1.5">
          {renderCompanySelect('h-8 w-[180px]')}
          <button
            type="button"
            onClick={() => setStatuses([])}
            className={cn(
              'rounded-full px-3 py-1 text-xs font-medium transition-colors',
              statuses.length === 0 ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground'
            )}
          >
            Toate
          </button>
          {STATUS_FILTER_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => toggleStatus(opt.value)}
              className={cn(
                'rounded-full px-3 py-1 text-xs font-medium transition-colors',
                statuses.includes(opt.value) ? recordStatus(opt.value).badgeClass : 'bg-secondary text-muted-foreground'
              )}
            >
              {opt.label}
            </button>
          ))}
          <SearchInput
            value={q}
            onChange={setQ}
            placeholder="Caută cod, VIN, vânzător, client..."
            className="ml-auto max-w-xs"
          />
        </div>
      )}

      {isLoading ? (
        <TableSkeleton rows={6} columns={4} />
      ) : isError ? (
        <EmptyState
          icon={<Car className="h-10 w-10" />}
          title="Eroare la încărcarea solicitărilor"
          description="Nu am putut încărca lista. Verifică conexiunea și încearcă din nou."
        />
      ) : !records.length ? (
        <EmptyState
          icon={<Car className="h-10 w-10" />}
          title="Nicio solicitare"
          description="Nu există solicitări BuyBack încă."
        />
      ) : (
        <div className="space-y-2">
          {records.map((r) => {
            const rs = recordStatus(r.status)
            const isExpanded = expanded.has(r.id)
            return (
              <Card key={r.id} className={cn('overflow-hidden p-0', rs.rowClass)}>
                <button
                  type="button"
                  aria-expanded={isExpanded}
                  onClick={() => toggleExpand(r.id)}
                  className="flex w-full items-center justify-between gap-3 p-3 text-left transition-colors hover:bg-muted/40"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-muted-foreground">{r.record_code}</span>
                      <span className="truncate text-sm font-medium">{`${r.brand} ${r.model}`}</span>
                    </div>
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">
                      {r.seller_name || '—'} · {r.vin}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <div className="flex flex-col items-end gap-1">
                      <Badge className={rs.badgeClass}>{rs.label}</Badge>
                      {r.client_asking_price_eur != null && (
                        <span className="text-xs text-muted-foreground">
                          {r.client_asking_price_eur.toLocaleString('ro-RO')} €
                        </span>
                      )}
                    </div>
                    <ChevronDown
                      className={cn(
                        'h-4 w-4 shrink-0 text-muted-foreground transition-transform',
                        isExpanded && 'rotate-180'
                      )}
                    />
                  </div>
                </button>
                {isExpanded && <BuybackCardSummary record={r} onOpenDetail={() => setSelectedId(r.id)} />}
              </Card>
            )
          })}
        </div>
      )}

      {/* iOS-style modal sheet — full-screen on phones, a centered floating
          card on desktop. Mirrors HubDrivingPanel's intake overlay. */}
      {overlay?.kind === 'new' && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-black/40 backdrop-blur-sm" onClick={closeOverlay}>
          <div
            className="mx-auto min-h-full w-full max-w-2xl bg-background shadow-2xl sm:my-8 sm:min-h-0 sm:rounded-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="sticky top-0 z-10 flex items-center justify-end border-b bg-background/95 p-2 backdrop-blur sm:rounded-t-2xl">
              <Button variant="ghost" size="icon" aria-label="Închide" onClick={closeOverlay}>
                <X className="h-5 w-5" />
              </Button>
            </div>
            <BuyBackForm embedded onDone={handleDone} onCancel={closeOverlay} />
          </div>
        </div>
      )}

      {/* Mobile status-filter modal (opened from the header "Filtre" button —
          replaces the desktop pill row). */}
      <Dialog open={filtersOpen} onOpenChange={setFiltersOpen}>
        <DialogContent className="max-w-xs">
          <DialogHeader>
            <DialogTitle>Filtre</DialogTitle>
          </DialogHeader>
          {companies.length > 1 && (
            <div className="space-y-1.5">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Companie</p>
              {renderCompanySelect('h-11 w-full')}
            </div>
          )}
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Status</p>
            <button
              type="button"
              onClick={() => setStatuses([])}
              className={cn(
                'w-full rounded-lg px-3 py-2 text-left text-sm font-medium transition-colors',
                statuses.length === 0 ? 'bg-secondary' : 'hover:bg-muted'
              )}
            >
              Toate
            </button>
            {STATUS_FILTER_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => toggleStatus(opt.value)}
                className={cn(
                  'flex w-full items-center justify-between rounded-lg px-3 py-2 text-left transition-colors',
                  statuses.includes(opt.value) ? 'bg-secondary' : 'hover:bg-muted'
                )}
              >
                <Badge className={recordStatus(opt.value).badgeClass}>{opt.label}</Badge>
                {statuses.includes(opt.value) && <Check className="h-4 w-4 text-primary" />}
              </button>
            ))}
          </div>
          <DialogFooter className="sm:justify-between">
            {statuses.length > 0 ? (
              <Button variant="ghost" onClick={() => setStatuses([])}>
                Șterge filtrele
              </Button>
            ) : (
              <span />
            )}
            <Button onClick={() => setFiltersOpen(false)}>Gata</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
