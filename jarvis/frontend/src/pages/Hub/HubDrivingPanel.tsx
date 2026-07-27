import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { usePersistedState } from '@/lib/utils'
import { foiParcursApi } from '@/api/foiParcurs'
import { SessionsTab } from '@/pages/FoiParcurs/index'
import { CalendarTab } from '@/pages/FoiParcurs/CalendarTab'
import TestDriveForm from '@/pages/FoiParcurs/TestDriveForm'
import TestDriveReturn from '@/pages/FoiParcurs/TestDriveReturn'

type Overlay = null | { kind: 'new' } | { kind: 'activate'; id: number } | { kind: 'return'; id: number }
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
      {/* Selector + primary action */}
      <div className="flex flex-wrap items-center gap-2">
        <Select value={String(companyId)} onValueChange={(v) => setCompanyId(Number(v))}>
          <SelectTrigger className="w-56"><SelectValue placeholder="Selectează compania" /></SelectTrigger>
          <SelectContent>{companies.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>)}</SelectContent>
        </Select>
        {brands.length > 0 && (
          <Select value={brand} onValueChange={setBrand}>
            <SelectTrigger className="w-44"><SelectValue placeholder="Brand" /></SelectTrigger>
            <SelectContent>{brands.map((b) => <SelectItem key={b} value={b}>{b}</SelectItem>)}</SelectContent>
          </Select>
        )}
        <Button className="ml-auto" onClick={() => setOverlay({ kind: 'new' })}>
          <Plus className="h-4 w-4 mr-1.5" /> Driving Session nou
        </Button>
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as PanelTab)}>
        <TabsList>
          <TabsTrigger value="sessions">Sesiuni</TabsTrigger>
          <TabsTrigger value="calendar">Calendar</TabsTrigger>
        </TabsList>
      </Tabs>

      {companyId > 0 && tab === 'sessions' && (
        <SessionsTab
          companyId={companyId}
          brand={brand}
          onActivate={(id) => setOverlay({ kind: 'activate', id })}
          onReturn={(id) => setOverlay({ kind: 'return', id })}
        />
      )}
      {companyId > 0 && tab === 'calendar' && <CalendarTab companyId={companyId} brand={brand} />}

      {/* Full-screen overlay inside the Hub */}
      {overlay && (
        <div className="fixed inset-0 z-50 bg-background overflow-y-auto">
          <div className="sticky top-0 z-10 flex items-center justify-end border-b bg-background p-2">
            <Button variant="ghost" size="icon" onClick={closeOverlay}><X className="h-5 w-5" /></Button>
          </div>
          {overlay.kind === 'new' && (
            <TestDriveForm embedded initialCompanyId={companyId || undefined} onDone={handleOverlayDone} onCancel={closeOverlay} />
          )}
          {overlay.kind === 'activate' && (
            <TestDriveForm embedded activateId={overlay.id} onDone={handleOverlayDone} onCancel={closeOverlay} />
          )}
          {overlay.kind === 'return' && (
            <TestDriveReturn embedded id={overlay.id} onDone={handleOverlayDone} onCancel={closeOverlay} />
          )}
        </div>
      )}
    </div>
  )
}
