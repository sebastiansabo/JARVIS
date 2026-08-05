import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { usePersistedState } from '@/lib/utils'
import { foiParcursApi } from '@/api/foiParcurs'
import DrivingSessionsList from '@/pages/Hub/DrivingSessionsList'
import DrivingCalendar from '@/pages/Hub/DrivingCalendar'
import TestDriveForm from '@/pages/FoiParcurs/TestDriveForm'
import TestDriveReturn from '@/pages/FoiParcurs/TestDriveReturn'

type Overlay = null | { kind: 'new'; departure?: string; ret?: string } | { kind: 'activate'; id: number } | { kind: 'return'; id: number }
type PanelTab = 'sessions' | 'calendar'

export default function HubDrivingPanel() {
  const [tab, setTab] = usePersistedState<PanelTab>('hub-driving-tab', 'sessions')
  const [companyId, setCompanyId] = usePersistedState<number>('hub-driving-company', 0)
  const [brand, setBrand] = usePersistedState<string>('hub-driving-brand', '')
  const [overlay, setOverlay] = useState<Overlay>(null)
  const queryClient = useQueryClient()

  const { data: companiesData } = useQuery({ queryKey: ['fp-companies'], queryFn: () => foiParcursApi.getCompanies() })
  const companies = companiesData?.companies ?? []
  useEffect(() => { if (companyId === 0 && companies.length) setCompanyId(companies[0].id) }, [companies]) // eslint-disable-line react-hooks/exhaustive-deps

  const { data: brandsData } = useQuery({ queryKey: ['fp-brands', companyId], queryFn: () => foiParcursApi.getBrands(companyId), enabled: companyId > 0 })
  const brands = brandsData?.brands ?? []
  useEffect(() => {
    const list = brandsData?.brands ?? []
    if (!list.length) { if (brand !== '') setBrand('') }
    else if (!list.includes(brand)) setBrand(list[0])
  }, [brandsData]) // eslint-disable-line react-hooks/exhaustive-deps

  const closeOverlay = () => setOverlay(null)
  const handleOverlayDone = () => {
    queryClient.invalidateQueries({ queryKey: ['foi-contracts-all'] })
    queryClient.invalidateQueries({ queryKey: ['odometer-history'] })
    setOverlay(null)
  }

  return (
    <div className="space-y-4">
      {/* Company / brand selectors + primary action — mobile-first (iOS) */}
      <div className="space-y-2">
        <div className="flex gap-2">
          <Select value={String(companyId)} onValueChange={(v) => setCompanyId(Number(v))}>
            <SelectTrigger className="h-11 flex-1 rounded-xl text-base"><SelectValue placeholder="Selectează compania" /></SelectTrigger>
            <SelectContent>{companies.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>)}</SelectContent>
          </Select>
          {brands.length > 0 && (
            <Select value={brand} onValueChange={setBrand}>
              <SelectTrigger className="h-11 w-32 shrink-0 rounded-xl text-base"><SelectValue placeholder="Brand" /></SelectTrigger>
              <SelectContent>{brands.map((b) => <SelectItem key={b} value={b}>{b}</SelectItem>)}</SelectContent>
            </Select>
          )}
        </div>
        <Button className="h-11 w-full rounded-xl text-base font-semibold" onClick={() => setOverlay({ kind: 'new' })}>
          <Plus className="mr-1.5 h-4 w-4" /> Driving Session nou
        </Button>
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as PanelTab)}>
        <TabsList>
          <TabsTrigger value="sessions">Sesiuni</TabsTrigger>
          <TabsTrigger value="calendar">Calendar</TabsTrigger>
        </TabsList>
      </Tabs>

      {companyId > 0 && tab === 'sessions' && (
        <DrivingSessionsList
          companyId={companyId}
          brand={brand}
          onActivate={(id) => setOverlay({ kind: 'activate', id })}
          onReturn={(id) => setOverlay({ kind: 'return', id })}
        />
      )}
      {companyId > 0 && tab === 'calendar' && (
        <DrivingCalendar
          companyId={companyId}
          brand={brand}
          onActivate={(id) => setOverlay({ kind: 'activate', id })}
          onReturn={(id) => setOverlay({ kind: 'return', id })}
          onAdd={(departure, ret) => setOverlay({ kind: 'new', departure, ret })}
        />
      )}

      {/* iOS-style modal sheet inside the Hub — full-screen on phones, a centered
          floating card on desktop. Widened to the form's own natural column
          (max-w-2xl, ~50% wider than the old max-w-md) so the fields aren't
          cramped on desktop while staying full-width and responsive on phones. */}
      {overlay && (
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
                onDone={handleOverlayDone}
                onCancel={closeOverlay}
              />
            )}
            {overlay.kind === 'activate' && (
              <TestDriveForm embedded activateId={overlay.id} onDone={handleOverlayDone} onCancel={closeOverlay} />
            )}
            {overlay.kind === 'return' && (
              <TestDriveReturn embedded id={overlay.id} onDone={handleOverlayDone} onCancel={closeOverlay} />
            )}
          </div>
        </div>
      )}
    </div>
  )
}
