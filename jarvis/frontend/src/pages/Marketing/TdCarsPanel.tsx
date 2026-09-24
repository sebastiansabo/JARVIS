import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { AlertTriangle, Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { TableSkeleton } from '@/components/shared/TableSkeleton'
import { tdAdminApi, type TdSessionConflict } from '@/api/tdAdmin'
import { naiveDate } from '@/lib/naiveDate'
import { foiParcursApi } from '@/api/foiParcurs'
import type { UserDetail } from '@/types/users'
import type { FpVehicle } from '@/types/foiParcurs'

const NONE = '__none__'

const conflictFmt = new Intl.DateTimeFormat('ro-RO', {
  day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
})
/** Short "30 sep 08:00 – 5 oct 08:00 · Client" label for an overlapping session.
 *  Uses naiveDate (wall-clock, zone stripped) like the rest of the TD calendar —
 *  session times are stored as local-wall-clock labelled +00, so `new Date`
 *  would shift them by the viewer's offset. */
function conflictLabel(cf: TdSessionConflict): string {
  const depD = naiveDate(cf.departure_datetime)
  const retD = cf.return_datetime ? naiveDate(cf.return_datetime) : null
  const dep = depD ? conflictFmt.format(depD) : '—'
  const ret = retD ? ' – ' + conflictFmt.format(retD) : ''
  const who = cf.client_name ? ` · ${cf.client_name}` : ''
  return `${dep}${ret}${who}`
}

/** Friendly label for a Driving Park vehicle: plate + make/model, falling
 *  back to the VIN when the plate isn't set. Mirrors TestDriveForm.tsx's
 *  vehicle picker label. */
function vehicleLabel(v: FpVehicle): string {
  const plate = v.registration_number || v.vin
  const makeModel = [v.mark, v.model].filter(Boolean).join(' ')
  return makeModel ? `${plate} — ${makeModel}` : plate
}

/** Cars attached to a booking page (vin + optional default advisor). Backed
 *  by a real `useQuery` against GET .../pages/<id>/cars, invalidated after
 *  add/remove, so the table survives a reload (unlike the old session-local
 *  `useState` this replaced).
 *
 *  The "car" picker is tenant-scoped to the page's own `companyId` (the
 *  selected page's company, not the Marketing module's global filter) so
 *  booked cars are real Driving Park fleet vehicles that fit the driving
 *  calendar + availability alongside other sessions -- not free-text VINs. */
export default function TdCarsPanel({ pageId, companyId, users }: {
  pageId: number
  companyId: number
  users: UserDetail[]
}) {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['td-cars', pageId],
    queryFn: () => tdAdminApi.listCars(pageId),
  })
  const cars = data?.cars ?? []

  const { data: vehiclesData, isLoading: vehiclesLoading } = useQuery({
    queryKey: ['fp-vehicles-active'],
    queryFn: () => foiParcursApi.getVehicles(true),
    staleTime: 60_000,
  })
  const allVehicles = vehiclesData?.vehicles ?? []

  // Tenant-gate to the page's own company, then drop cars already on this
  // page -- the backend has UNIQUE(page_id, vin) and would 409 on a repeat.
  const addedVins = useMemo(() => new Set(cars.map((c) => c.vin)), [cars])
  const availableVehicles = useMemo(
    () => allVehicles.filter((v) => v.company_id === companyId && !addedVins.has(v.vin)),
    [allVehicles, companyId, addedVins],
  )

  const [vehicleId, setVehicleId] = useState('')
  const [advisorId, setAdvisorId] = useState(NONE)

  const selectedVehicle = availableVehicles.find((v) => String(v.id) === vehicleId) ?? null

  const addMut = useMutation({
    mutationFn: () => {
      if (!selectedVehicle) throw new Error('Selectează o mașină')
      return tdAdminApi.addCar(pageId, {
        vin: selectedVehicle.vin,
        vehicle_id: selectedVehicle.id,
        default_advisor_user_id: advisorId === NONE ? undefined : Number(advisorId),
      })
    },
    onSuccess: (car) => {
      qc.invalidateQueries({ queryKey: ['td-cars', pageId] })
      setVehicleId('')
      setAdvisorId(NONE)
      // Warn (non-blocking) if the just-added car is already booked during the
      // event — it will show no slots on the public form until it's free.
      if (car?.conflicts?.length) {
        toast.warning('Mașina are deja o cursă în perioada evenimentului', {
          description: `${carLabel(car.vin)}: ${car.conflicts.map(conflictLabel).join('; ')}. Nu va apărea liberă în formular cât timp e ocupată.`,
        })
      }
    },
    onError: (e: any) => toast.error(e?.data?.error || e?.message || 'Adăugarea mașinii a eșuat'),
  })

  const removeMut = useMutation({
    mutationFn: (carId: number) => tdAdminApi.removeCar(carId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['td-cars', pageId] }),
    onError: (e: any) => toast.error(e?.data?.error || e?.message || 'Ștergerea a eșuat'),
  })

  const advisorName = (id: number | null) => (id ? users.find((u) => u.id === id)?.name ?? `#${id}` : '—')
  const carLabel = (vin: string) => {
    const v = allVehicles.find((x) => x.vin === vin)
    return v ? vehicleLabel(v) : vin
  }

  if (isLoading) return <TableSkeleton rows={2} columns={3} />

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold">Mașini</h4>
      <div className="flex flex-wrap items-end gap-2">
        <div className="space-y-1.5">
          <Label className="text-xs">Mașină (Driving Park)</Label>
          <Select value={vehicleId} onValueChange={setVehicleId} disabled={!companyId}>
            <SelectTrigger className="h-8 w-64">
              <SelectValue placeholder={companyId ? 'Selectează mașina' : 'Selectează o companie'} />
            </SelectTrigger>
            <SelectContent>
              {availableVehicles.map((v) => (
                <SelectItem key={v.id} value={String(v.id)}>{vehicleLabel(v)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {!companyId && <p className="text-xs text-muted-foreground">Selectează o companie</p>}
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Consilier implicit</Label>
          <Select value={advisorId} onValueChange={setAdvisorId}>
            <SelectTrigger className="h-8 w-48"><SelectValue placeholder="Fără consilier" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>Fără consilier</SelectItem>
              {users.filter((u) => u.is_active).map((u) => (
                <SelectItem key={u.id} value={String(u.id)}>{u.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button
          size="sm" className="h-8"
          disabled={!companyId || !selectedVehicle || addMut.isPending || vehiclesLoading}
          onClick={() => addMut.mutate()}
        >
          <Plus className="mr-1.5 h-4 w-4" />{addMut.isPending ? 'Se adaugă…' : 'Adaugă'}
        </Button>
      </div>

      {!cars.length ? (
        <p className="text-sm text-muted-foreground">Nicio mașină adăugată.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Mașină</TableHead>
              <TableHead>VIN</TableHead>
              <TableHead>Consilier implicit</TableHead>
              <TableHead className="text-right">Acțiuni</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {cars.map((c) => (
              <TableRow key={c.id}>
                <TableCell className="text-sm">
                  <div className="flex items-center gap-1.5">
                    {carLabel(c.vin)}
                    {!!c.conflicts?.length && <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-500" />}
                  </div>
                  {!!c.conflicts?.length && (
                    <div className="mt-0.5 text-xs text-amber-600 dark:text-amber-400">
                      Ocupată în perioada evenimentului: {c.conflicts.map(conflictLabel).join('; ')}
                    </div>
                  )}
                </TableCell>
                <TableCell className="font-mono text-xs">{c.vin}</TableCell>
                <TableCell className="text-sm">{advisorName(c.default_advisor_user_id)}</TableCell>
                <TableCell className="text-right">
                  <Button variant="ghost" size="icon" className="h-7 w-7" disabled={removeMut.isPending}
                    onClick={() => removeMut.mutate(c.id)} aria-label={`Șterge ${c.vin}`}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
