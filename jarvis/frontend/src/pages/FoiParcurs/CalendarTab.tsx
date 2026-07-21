import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, ChevronRight, PlayCircle, XIcon, FileText } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { foiParcursApi } from '@/api/foiParcurs'
import type { FoiContract } from '@/types/foiParcurs'
import { sessionStatus } from './sessionStatus'
import { naiveDate } from '@/lib/naiveDate'

const WEEKDAY_LABELS = ['Lun', 'Mar', 'Mie', 'Joi', 'Vin', 'Sâm', 'Dum']

function dayKey(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** 6-week (42-day) Monday-first grid covering `cursor`'s month, padded with
 *  leading/trailing days from the adjacent months so every week row is full.
 *  Plain Date math — no calendar library is installed in this project. */
function monthGrid(cursor: Date): Date[] {
  const year = cursor.getFullYear()
  const month = cursor.getMonth()
  const firstOfMonth = new Date(year, month, 1)
  const startOffset = (firstOfMonth.getDay() + 6) % 7 // Mon=0 .. Sun=6
  const gridStart = new Date(year, month, 1 - startOffset)
  return Array.from({ length: 42 }, (_, i) => new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + i))
}

/** Month-grid calendar of planned/live/finished TD sessions, keyed on
 *  departure_datetime. Data reuses the same ['foi-contracts-all', companyId]
 *  query as SessionsTab (per_page:1000, filtered client-side — the backend's
 *  GET /contracts has no date_from/date_to/route_type filter), so switching
 *  between Sesiuni Driving and Calendar doesn't refetch. */
export function CalendarTab({ companyId, brand }: { companyId: number; brand: string }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [cursor, setCursor] = useState(() => new Date())
  const [selected, setSelected] = useState<FoiContract | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['foi-contracts-all', companyId],
    queryFn: () =>
      foiParcursApi.getContracts({ company_id: companyId || undefined, per_page: 1000, sort_by: 'created_at', sort_dir: 'DESC' }),
    staleTime: 30_000,
  })
  const { data: vehiclesData } = useQuery({
    queryKey: ['fp-vehicles'],
    queryFn: () => foiParcursApi.getVehicles(),
    staleTime: 30_000,
  })
  const vehiclesList = vehiclesData?.vehicles ?? []
  const vinBrand = new Map(vehiclesList.map((v) => [v.vin, v.brand]))
  const vinVehicle = new Map(vehiclesList.map((v) => [v.vin, v]))

  const discardMutation = useMutation({
    mutationFn: (id: number) => foiParcursApi.discardTestDrive(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['foi-contracts-all'] })
      setSelected(null)
    },
  })

  const tdContracts = (data?.contracts ?? []).filter(
    (c) => c.route_type === 'TD' && c.departure_datetime && (!brand || vinBrand.get(c.vin) === brand),
  )

  const byDay = useMemo(() => {
    const map = new Map<string, FoiContract[]>()
    for (const c of tdContracts) {
      const key = dayKey(naiveDate(c.departure_datetime)!)
      const list = map.get(key) ?? []
      list.push(c)
      map.set(key, list)
    }
    return map
  }, [tdContracts])

  const grid = useMemo(() => monthGrid(cursor), [cursor])
  const currentMonth = cursor.getMonth()
  const todayKey = dayKey(new Date())
  const monthLabel = cursor.toLocaleDateString('ro-RO', { month: 'long', year: 'numeric' })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="sm" onClick={() => setCursor(new Date())}>Azi</Button>
          <Button variant="outline" size="icon" onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))}>
            <ChevronRight className="h-4 w-4" />
          </Button>
          <h3 className="text-base font-semibold capitalize ml-2">{monthLabel}</h3>
        </div>
        {isLoading && <span className="text-xs text-muted-foreground">Se încarcă...</span>}
      </div>

      <Card className="overflow-hidden">
        <div className="grid grid-cols-7 border-b bg-muted/40">
          {WEEKDAY_LABELS.map((d) => (
            <div key={d} className="px-2 py-1.5 text-center text-xs font-medium text-muted-foreground">{d}</div>
          ))}
        </div>
        <div className="grid grid-cols-7">
          {grid.map((d) => {
            const key = dayKey(d)
            const inMonth = d.getMonth() === currentMonth
            const isToday = key === todayKey
            const events = byDay.get(key) ?? []
            return (
              <div
                key={key}
                className={cn('min-h-[104px] border-b border-r p-1.5 space-y-1', !inMonth && 'bg-muted/20 text-muted-foreground')}
              >
                <div className={cn('text-xs font-medium', isToday && 'inline-flex h-5 w-5 items-center justify-center rounded-full bg-primary text-primary-foreground')}>
                  {d.getDate()}
                </div>
                <div className="space-y-1">
                  {events.slice(0, 3).map((c) => {
                    const ss = sessionStatus(c)
                    const v = vinVehicle.get(c.vin)
                    const carLabel = v ? [v.brand || v.mark, v.model].filter(Boolean).join(' ') : c.vin.slice(0, 8)
                    const time = c.departure_datetime
                      ? naiveDate(c.departure_datetime)!.toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' })
                      : ''
                    return (
                      <button
                        key={c.id}
                        type="button"
                        onClick={() => setSelected(c)}
                        className={cn('w-full truncate rounded px-1.5 py-0.5 text-left text-[11px] font-medium text-white hover:opacity-90', ss.badgeClass)}
                        title={`${time} ${carLabel} — ${c.client_name || '—'}`}
                      >
                        {time} {carLabel}
                      </button>
                    )
                  })}
                  {events.length > 3 && (
                    <div className="text-[10px] text-muted-foreground px-1.5">+{events.length - 3} altele</div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </Card>

      {selected && (
        <Dialog open onOpenChange={(o) => { if (!o) setSelected(null) }}>
          <DialogContent className="max-w-sm">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                Detalii sesiune
                <Badge className={cn('text-xs', sessionStatus(selected).badgeClass)}>{sessionStatus(selected).label}</Badge>
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-1.5 text-sm">
              <p><span className="text-muted-foreground">Client:</span> {selected.client_name || '—'}</p>
              <p><span className="text-muted-foreground">Consilier:</span> {selected.advisor_name || '—'}</p>
              <p>
                <span className="text-muted-foreground">Mașină:</span>{' '}
                {(() => {
                  const v = vinVehicle.get(selected.vin)
                  return v ? `${[v.brand || v.mark, v.model].filter(Boolean).join(' ')} — ${v.registration_number || v.vin}` : selected.vin
                })()}
              </p>
              <p><span className="text-muted-foreground">Plecare:</span> {selected.departure_datetime ? naiveDate(selected.departure_datetime)!.toLocaleString('ro-RO') : '—'}</p>
              <p><span className="text-muted-foreground">Retur:</span> {selected.return_datetime ? naiveDate(selected.return_datetime)!.toLocaleString('ro-RO') : '—'}</p>
            </div>
            <DialogFooter className="flex-col sm:flex-row gap-2">
              {selected.status === 'PLANNED' && (
                <>
                  <Button
                    variant="outline"
                    className="w-full sm:w-auto"
                    onClick={() => {
                      if (confirm('Renunți la această sesiune planificată? Acțiunea nu poate fi anulată.')) {
                        discardMutation.mutate(selected.id)
                      }
                    }}
                    disabled={discardMutation.isPending}
                  >
                    <XIcon className="mr-1.5 h-4 w-4" />Discard
                  </Button>
                  <Button className="w-full sm:w-auto" onClick={() => navigate(`/app/foi-parcurs/test-drive?activate=${selected.id}`)}>
                    <PlayCircle className="mr-1.5 h-4 w-4" />Începe sesiunea
                  </Button>
                </>
              )}
              {selected.status !== 'PLANNED' && selected.status !== 'PENDING' && (
                <a href={foiParcursApi.getContractPdfUrl(selected.id, 'legal')} target="_blank" rel="noopener" className="w-full sm:w-auto">
                  <Button variant="outline" className="w-full"><FileText className="mr-1.5 h-4 w-4" />PDF</Button>
                </a>
              )}
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  )
}
