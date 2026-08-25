import { useState, useEffect, useMemo } from 'react'
import { createPortal } from 'react-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, X, CalendarDays, SlidersHorizontal, Car, UserRound, ChevronLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useHubHeaderSlot } from '@/pages/Hub/hubHeaderSlot'
import SearchMultiSelect from '@/pages/Hub/SearchMultiSelect'
import { cn, usePersistedState, useIsMobile } from '@/lib/utils'
import { foiParcursApi } from '@/api/foiParcurs'
import { sessionStatus } from '@/pages/FoiParcurs/sessionStatus'
import type { DocType } from '@/pages/FoiParcurs/documentType'
import type { FpVehicle } from '@/types/foiParcurs'
import DrivingSessionsList from '@/pages/Hub/DrivingSessionsList'
import DrivingCalendar from '@/pages/Hub/DrivingCalendar'
import DrivingParkList from '@/pages/Hub/DrivingParkList'
import TestDriveForm from '@/pages/FoiParcurs/TestDriveForm'
import TestDriveReturn from '@/pages/FoiParcurs/TestDriveReturn'
import InternalSessionForm from '@/pages/FoiParcurs/InternalSessionForm'
import SessionTypeChooser from '@/pages/FoiParcurs/SessionTypeChooser'

type Overlay = null
  | { kind: 'choose'; departure?: string; ret?: string }
  | { kind: 'new'; departure?: string; ret?: string }
  | { kind: 'new-internal'; departure?: string; ret?: string }
  | { kind: 'activate'; id: number }
  | { kind: 'return'; id: number }
type PanelTab = 'sessions' | 'calendar' | 'park'

// Sentinel company id meaning "all companies" — the list/calendar queries map it
// to an omitted company_id, so the backend returns every company the user can
// see (L0 → all). 0 = "not chosen yet" (auto-selects the first company).
const ALL_COMPANIES = -1
// iOS Human-Interface min touch target — every control is ≥44px tall.
const CTRL_H = 'h-11'

function vehName(v?: FpVehicle, vin?: string | null): string {
  if (v) return [v.mark, v.model].filter(Boolean).join(' ') || v.registration_number || vin || '—'
  return vin || '—'
}

// lucide has no steering-wheel glyph, so this is a small inline one (matches
// lucide's 24px / stroke-2 / round-cap style): rim + hub + left/right/down spokes.
function SteeringWheel({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="12" r="2.5" />
      <path d="M2 12h7.5" />
      <path d="M14.5 12H22" />
      <path d="M12 14.5V22" />
    </svg>
  )
}

// Phone-only control surface: a fixed bottom pill mirroring the Hub's global nav
// pill (Hub/index.tsx). The active view (Sesiuni/Calendar/Parc) expands to icon +
// label like that pill; Back/Filtre are icon-only; New is a filled primary circle
// (the main action, kept last/rightmost). Every control is ≥44px (h-11 / w-11).
function DrivingBottomBar({ tab, onTab, activeFilters, onFilters, onNew, onBack }: {
  tab: PanelTab
  onTab: (t: PanelTab) => void
  activeFilters: number
  onFilters: () => void
  onNew: () => void
  onBack?: () => void
}) {
  const base = 'flex h-11 items-center justify-center rounded-full transition-all'
  const tabCls = (on: boolean) => cn(base, on ? 'gap-1.5 bg-zinc-700 px-3 text-white dark:bg-zinc-600' : 'w-11 text-zinc-400')
  return (
    <div className="fixed inset-x-0 bottom-0 z-40 pb-[env(safe-area-inset-bottom)] sm:hidden">
      <div className="mx-4 mb-2 rounded-[22px] bg-zinc-900 shadow-lg dark:bg-zinc-800">
        <div className="flex items-center justify-around gap-0.5 px-1.5 py-1.5">
          {onBack && (
            <button type="button" onClick={onBack} aria-label="Înapoi la Hub" className={cn(base, 'w-11 text-zinc-400')}>
              <ChevronLeft className="h-5 w-5 shrink-0" />
            </button>
          )}
          <button type="button" onClick={() => onTab('sessions')} aria-label="Sesiuni" className={tabCls(tab === 'sessions')}>
            <SteeringWheel className="h-5 w-5 shrink-0" />
            {tab === 'sessions' && <span className="text-[11px] font-semibold">Sesiuni</span>}
          </button>
          <button type="button" onClick={() => onTab('calendar')} aria-label="Calendar" className={tabCls(tab === 'calendar')}>
            <CalendarDays className="h-5 w-5 shrink-0" />
            {tab === 'calendar' && <span className="text-[11px] font-semibold">Calendar</span>}
          </button>
          <button type="button" onClick={() => onTab('park')} aria-label="Parc" className={tabCls(tab === 'park')}>
            <Car className="h-5 w-5 shrink-0" />
            {tab === 'park' && <span className="text-[11px] font-semibold">Parc</span>}
          </button>
          <button type="button" onClick={onFilters} aria-label="Filtre" className={cn(base, 'relative w-11 text-zinc-400')}>
            <SlidersHorizontal className="h-5 w-5 shrink-0" />
            {activeFilters > 0 && (
              <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-bold leading-none text-primary-foreground">
                {activeFilters}
              </span>
            )}
          </button>
          <button type="button" onClick={onNew} aria-label="Sesiune nouă" className={cn(base, 'w-11 bg-primary text-primary-foreground shadow-sm active:scale-95')}>
            <Plus className="h-5 w-5 shrink-0" />
          </button>
        </div>
      </div>
    </div>
  )
}

export default function HubDrivingPanel({ onBack, documentType = 'sales' }: { onBack?: () => void; documentType?: DocType }) {
  const isService = documentType === 'service'
  // Persist Sales and Service panel state under distinct keys so the two zones
  // keep independent tab/company/brand selections (and Sales keys stay exactly
  // as they were — byte-unchanged for existing users).
  const ns = isService ? 'hub-service' : 'hub-driving'
  const [tab, setTab] = usePersistedState<PanelTab>(`${ns}-tab`, 'sessions')
  const [companyId, setCompanyId] = usePersistedState<number>(`${ns}-company`, 0)
  const [brand, setBrand] = usePersistedState<string>(`${ns}-brand`, '')
  // Courtesy stock is multi-brand (independent of the dealership franchise), so
  // the Service context never filters by brand — children always get ''.
  const effBrand = isService ? '' : brand
  const [carFilter, setCarFilter] = useState<string[]>([])          // selected VINs; [] = all
  const [consultantFilter, setConsultantFilter] = useState<string[]>([]) // advisor names; [] = all
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [overlay, setOverlay] = useState<Overlay>(null)
  const queryClient = useQueryClient()
  const isMobile = useIsMobile()

  const { data: companiesData } = useQuery({ queryKey: ['fp-companies'], queryFn: () => foiParcursApi.getCompanies() })
  const companies = companiesData?.companies ?? []
  useEffect(() => { if (companyId === 0 && companies.length) setCompanyId(companies[0].id) }, [companies]) // eslint-disable-line react-hooks/exhaustive-deps

  const { data: brandsData } = useQuery({ queryKey: ['fp-brands', companyId], queryFn: () => foiParcursApi.getBrands(companyId), enabled: companyId > 0 })
  const brands = brandsData?.brands ?? []
  useEffect(() => {
    const list = brandsData?.brands ?? []
    // Keep '' = "All brands" as the default; only reset a now-invalid *specific*
    // brand back to "all".
    if (!list.length) { if (brand !== '') setBrand('') }
    else if (brand !== '' && !list.includes(brand)) setBrand('')
  }, [brandsData]) // eslint-disable-line react-hooks/exhaustive-deps

  const hasCompany = companyId !== 0 // a real company OR "all companies"

  // Contracts + vehicles feed the Filtre modal's car/consultant option lists.
  // Same query keys as the list/calendar → React Query serves them from one
  // shared cache (no extra network round-trip).
  const { data: contractsData } = useQuery({
    queryKey: ['foi-contracts-all', companyId, documentType],
    queryFn: () => foiParcursApi.getContracts({ company_id: companyId > 0 ? companyId : undefined, per_page: 1000, sort_by: 'created_at', sort_dir: 'DESC', document_type: documentType }),
    enabled: hasCompany,
    staleTime: 30_000,
  })
  const { data: vehiclesData } = useQuery({ queryKey: ['fp-vehicles', documentType], queryFn: () => foiParcursApi.getVehicles(true, documentType), staleTime: 30_000 })
  const vinVehicle = useMemo(() => new Map((vehiclesData?.vehicles ?? []).map((v) => [v.vin, v] as const)), [vehiclesData])

  // Distinct cars + consultants across the (brand-scoped) upcoming/live sessions.
  // Car search haystack spans car/plate/VIN/id/consultant; consultant by name.
  const { carOptions, consultantOptions } = useMemo(() => {
    const cars = new Map<string, { label: string; search: string }>()
    const consultants = new Map<string, { label: string; search: string }>()
    for (const c of contractsData?.contracts ?? []) {
      const vh = c.vin ? vinVehicle.get(c.vin) : undefined
      if (brand && c.vin && (vh?.brand ?? '').trim() !== brand && (vh?.mark ?? '').trim() !== brand) continue
      const k = sessionStatus(c).key
      if (k !== 'planificat' && k !== 'driving' && k !== 'intarziat') continue
      const advisor = (c.advisor_name ?? '').trim()
      if (c.vin) {
        const existing = cars.get(c.vin)
        if (!existing) {
          const plate = (vh?.registration_number ?? '').trim()
          const label = plate ? `${vehName(vh, c.vin)} · ${plate}` : vehName(vh, c.vin)
          cars.set(c.vin, { label, search: [label, c.vin, plate, vh?.id != null ? String(vh.id) : '', advisor].join(' ').toLowerCase() })
        } else if (advisor && !existing.search.includes(advisor.toLowerCase())) {
          existing.search += ' ' + advisor.toLowerCase()
        }
      }
      if (advisor && !consultants.has(advisor)) consultants.set(advisor, { label: advisor, search: advisor.toLowerCase() })
    }
    return {
      carOptions: Array.from(cars, ([value, o]) => ({ value, ...o })).sort((a, b) => a.label.localeCompare(b.label)),
      consultantOptions: Array.from(consultants, ([value, o]) => ({ value, ...o })).sort((a, b) => a.label.localeCompare(b.label)),
    }
  }, [contractsData, brand, vinVehicle])

  const activeFilters = carFilter.length + consultantFilter.length + (brand ? 1 : 0)
  const resetFilters = () => { setBrand(''); setCarFilter([]); setConsultantFilter([]) }

  const closeOverlay = () => setOverlay(null)
  const handleOverlayDone = () => {
    queryClient.invalidateQueries({ queryKey: ['foi-contracts-all'] })
    queryClient.invalidateQueries({ queryKey: ['odometer-history'] })
    setOverlay(null)
  }

  const headerSlot = useHubHeaderSlot()

  // Inline nav (portaled onto the "‹ Hub / Driving Sessions" title row when the
  // breadcrumb exposes a slot): Sessions/Calendar switch · new-session · Filtre.
  const inlineActions = (
    <div className="flex items-center gap-2">
      <Tabs value={tab} onValueChange={(v) => setTab(v as PanelTab)}>
        {/* Icon + label view switch (desktop only — phones use the bottom pill). */}
        <TabsList className="rounded-xl group-data-[orientation=horizontal]/tabs:h-11">
          <TabsTrigger value="sessions" aria-label="Sesiuni" className="gap-1.5 rounded-lg px-2.5 lg:px-3"><SteeringWheel className="size-5" /><span className="hidden lg:inline">Sesiuni</span></TabsTrigger>
          <TabsTrigger value="calendar" aria-label="Calendar" className="gap-1.5 rounded-lg px-2.5 lg:px-3"><CalendarDays className="size-5" /><span className="hidden lg:inline">Calendar</span></TabsTrigger>
          <TabsTrigger value="park" aria-label="Parc" className="gap-1.5 rounded-lg px-2.5 lg:px-3"><Car className="size-5" /><span className="hidden lg:inline">Parc</span></TabsTrigger>
        </TabsList>
      </Tabs>
      <Button variant="outline" aria-label="Filtre" className={`${CTRL_H} shrink-0 gap-1.5 rounded-xl px-2.5 lg:px-3`} onClick={() => setFiltersOpen(true)}>
        <SlidersHorizontal className="h-4 w-4" />
        <span className="hidden lg:inline">Filtre</span>
        {activeFilters > 0 && <span className="rounded-full bg-primary px-1.5 text-[11px] font-bold leading-5 text-primary-foreground">{activeFilters}</span>}
      </Button>
      <Button aria-label="Sesiune nouă" className={`${CTRL_H} shrink-0 gap-1.5 rounded-xl px-2.5 lg:px-3`} onClick={() => setOverlay({ kind: 'choose' })}>
        <Plus className="h-5 w-5" />
        <span className="hidden lg:inline">Sesiune nouă</span>
      </Button>
    </div>
  )

  return (
    <div className="space-y-4">
      {/* Desktop: controls sit inline on the breadcrumb title row. Phones get the
          fixed bottom pill below instead, so skip the header toolbar there. */}
      {/* Controls live in the Hub header slot on ALL widths — the mobile
          breadcrumb renders that slot too, so phones get icon-only controls on
          the title row. Inline fallback stays desktop-only. */}
      {headerSlot ? createPortal(inlineActions, headerSlot) : (!isMobile && <div className="flex justify-end">{inlineActions}</div>)}

      {hasCompany && tab === 'sessions' && (
        <DrivingSessionsList
          companyId={companyId}
          brand={effBrand}
          carFilter={carFilter}
          consultantFilter={consultantFilter}
          documentType={documentType}
          onActivate={(id) => setOverlay({ kind: 'activate', id })}
          onReturn={(id) => setOverlay({ kind: 'return', id })}
        />
      )}
      {hasCompany && tab === 'calendar' && (
        <DrivingCalendar
          companyId={companyId}
          brand={effBrand}
          carFilter={carFilter}
          consultantFilter={consultantFilter}
          documentType={documentType}
          onActivate={(id) => setOverlay({ kind: 'activate', id })}
          onReturn={(id) => setOverlay({ kind: 'return', id })}
          onAdd={(departure, ret) => setOverlay({ kind: 'choose', departure, ret })}
        />
      )}
      {hasCompany && tab === 'park' && (
        <DrivingParkList companyId={companyId} brand={effBrand} carFilter={carFilter} documentType={documentType} />
      )}

      {/* Filtre modal — company / brand / cars / consultant, shared by all views. */}
      <Dialog open={filtersOpen} onOpenChange={setFiltersOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Filtre</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <p className="text-xs font-semibold text-muted-foreground">Companie</p>
              <Select value={String(companyId)} onValueChange={(v) => setCompanyId(Number(v))}>
                <SelectTrigger className={`${CTRL_H} w-full rounded-lg text-base`}><SelectValue placeholder="Selectează compania" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={String(ALL_COMPANIES)}>Toate companiile</SelectItem>
                  {companies.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {!isService && brands.length > 0 && (
              <div className="space-y-1.5">
                <p className="text-xs font-semibold text-muted-foreground">Marcă</p>
                <Select value={brand || 'all'} onValueChange={(v) => setBrand(v === 'all' ? '' : v)}>
                  <SelectTrigger className={`${CTRL_H} w-full rounded-lg text-base`}><SelectValue placeholder="Brand" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Toate mărcile</SelectItem>
                    {brands.map((b) => <SelectItem key={b} value={b}>{b}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="space-y-1.5">
              <p className="text-xs font-semibold text-muted-foreground">Mașini</p>
              <SearchMultiSelect options={carOptions} value={carFilter} onChange={setCarFilter} allLabel="Toate mașinile" placeholder="Caută: mașină, consilier, nr., VIN…" icon={Car} countNoun={['mașină', 'mașini']} />
            </div>
            <div className="space-y-1.5">
              <p className="text-xs font-semibold text-muted-foreground">Consilier</p>
              <SearchMultiSelect options={consultantOptions} value={consultantFilter} onChange={setConsultantFilter} allLabel="Toți consilierii" placeholder="Caută consilier…" icon={UserRound} countNoun={['consilier', 'consilieri']} />
            </div>
            <div className="flex items-center justify-between pt-1">
              <Button variant="ghost" className={CTRL_H} onClick={resetFilters} disabled={activeFilters === 0}>Resetează</Button>
              <Button className={CTRL_H} onClick={() => setFiltersOpen(false)}>Gata</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Step 1 of "+ Sesiune nouă" — Client (existing TD form) vs Intern (slim
          driving log). A separate, compact dialog — not the full-screen sheet
          below, which is sized for the forms themselves. */}
      <SessionTypeChooser
        open={overlay?.kind === 'choose'}
        onOpenChange={(o) => { if (!o) closeOverlay() }}
        // Service (courtesy) zone: Rent-a-car + Internal, no client test-drive.
        // Sales zone: client + internal, unchanged.
        showRental={isService}
        showClient={!isService}
        onPick={(type) => {
          if (!overlay || overlay.kind !== 'choose') return
          const { departure, ret } = overlay
          // 'internal' → the slim internal log; 'client' and 'rental' both open
          // the TestDriveForm ('rental' just runs it in service context via the
          // panel's documentType, so the same overlay kind serves both).
          setOverlay(type === 'internal' ? { kind: 'new-internal', departure, ret } : { kind: 'new', departure, ret })
        }}
      />

      {/* iOS-style modal sheet inside the Hub — full-screen on phones, a centered
          floating card on desktop. */}
      {overlay && overlay.kind !== 'choose' && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-black/40 backdrop-blur-sm">
          <div className="mx-auto min-h-full w-full max-w-2xl bg-background shadow-2xl sm:my-8 sm:min-h-0 sm:rounded-2xl">
            <div className="sticky top-0 z-10 flex items-center justify-end border-b bg-background/95 p-2 backdrop-blur sm:rounded-t-2xl">
              <Button variant="ghost" size="icon" onClick={closeOverlay}><X className="h-5 w-5" /></Button>
            </div>
            {overlay.kind === 'new' && (
              <TestDriveForm
                embedded
                initialCompanyId={companyId || undefined}
                initialDeparture={overlay.departure}
                initialReturn={overlay.ret}
                initialDocumentType={documentType}
                onDone={handleOverlayDone}
                onCancel={closeOverlay}
              />
            )}
            {overlay.kind === 'new-internal' && (
              <InternalSessionForm
                embedded
                // companyId can be ALL_COMPANIES (-1, "Toate companiile") — pass
                // undefined for it so the internal form's picker shows every
                // vehicle instead of filtering on company_id === -1 (empty).
                initialCompanyId={companyId > 0 ? companyId : undefined}
                initialDeparture={overlay.departure}
                initialReturn={overlay.ret}
                onDone={handleOverlayDone}
                onCancel={closeOverlay}
              />
            )}
            {overlay.kind === 'activate' && (
              <TestDriveForm embedded activateId={overlay.id} initialDocumentType={documentType} onDone={handleOverlayDone} onCancel={closeOverlay} />
            )}
            {overlay.kind === 'return' && (
              <TestDriveReturn embedded id={overlay.id} onDone={handleOverlayDone} onCancel={closeOverlay} />
            )}
          </div>
        </div>
      )}

      {/* Phone fallback control surface — only when there's no header slot to
          portal into (the breadcrumb normally provides one on mobile too). */}
      {isMobile && !headerSlot && (
        <DrivingBottomBar
          tab={tab}
          onTab={setTab}
          activeFilters={activeFilters}
          onFilters={() => setFiltersOpen(true)}
          onNew={() => setOverlay({ kind: 'choose' })}
          onBack={onBack}
        />
      )}
    </div>
  )
}
