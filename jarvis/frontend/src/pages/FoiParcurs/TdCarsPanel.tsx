import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { tdAdminApi, type TdAdminCar } from '@/api/tdAdmin'
import type { UserDetail } from '@/types/users'

const NONE = '__none__'

/** Cars attached to a booking page (vin + optional default advisor).
 *
 *  GOTCHA: td_admin.py only exposes POST .../cars and DELETE /cars/<id> --
 *  there is no GET list route for a page's cars. So this table is fed by
 *  the parent's local `cars` state (seeded empty per page, kept in sync from
 *  each mutation's response) rather than a useQuery -- it only reflects what
 *  was added in the current session and won't survive a reload. Follow-up:
 *  add GET /marketing/api/td/pages/<id>/cars on the backend so this can
 *  become a real query like TdBookingsPanel. */
export default function TdCarsPanel({ pageId, users, cars, onCarsChange }: {
  pageId: number
  users: UserDetail[]
  cars: TdAdminCar[]
  onCarsChange: (cars: TdAdminCar[]) => void
}) {
  const [vin, setVin] = useState('')
  const [advisorId, setAdvisorId] = useState(NONE)

  const addMut = useMutation({
    mutationFn: () => tdAdminApi.addCar(pageId, {
      vin: vin.trim(),
      default_advisor_user_id: advisorId === NONE ? undefined : Number(advisorId),
    }),
    onSuccess: (car) => {
      onCarsChange([...cars, car])
      setVin('')
      setAdvisorId(NONE)
    },
    onError: (e: any) => toast.error(e?.data?.error || e?.message || 'Adăugarea mașinii a eșuat'),
  })

  const removeMut = useMutation({
    mutationFn: (carId: number) => tdAdminApi.removeCar(carId),
    onSuccess: (_r, carId) => onCarsChange(cars.filter((c) => c.id !== carId)),
    onError: (e: any) => toast.error(e?.data?.error || e?.message || 'Ștergerea a eșuat'),
  })

  const advisorName = (id: number | null) => (id ? users.find((u) => u.id === id)?.name ?? `#${id}` : '—')

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold">Mașini</h4>
      <div className="flex flex-wrap items-end gap-2">
        <div className="space-y-1.5">
          <Label className="text-xs">VIN</Label>
          <Input className="h-8 w-48" value={vin} onChange={(e) => setVin(e.target.value)} placeholder="VIN" />
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
        <Button size="sm" className="h-8" disabled={!vin.trim() || addMut.isPending} onClick={() => addMut.mutate()}>
          <Plus className="mr-1.5 h-4 w-4" />{addMut.isPending ? 'Se adaugă…' : 'Adaugă'}
        </Button>
      </div>

      {!cars.length ? (
        <p className="text-sm text-muted-foreground">Nicio mașină adăugată.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>VIN</TableHead>
              <TableHead>Consilier implicit</TableHead>
              <TableHead className="text-right">Acțiuni</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {cars.map((c) => (
              <TableRow key={c.id}>
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
