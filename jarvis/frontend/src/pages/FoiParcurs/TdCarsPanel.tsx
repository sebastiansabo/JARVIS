import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { TableSkeleton } from '@/components/shared/TableSkeleton'
import { tdAdminApi } from '@/api/tdAdmin'
import type { UserDetail } from '@/types/users'

const NONE = '__none__'

/** Cars attached to a booking page (vin + optional default advisor). Backed
 *  by a real `useQuery` against GET .../pages/<id>/cars, invalidated after
 *  add/remove, so the table survives a reload (unlike the old session-local
 *  `useState` this replaced). */
export default function TdCarsPanel({ pageId, users }: {
  pageId: number
  users: UserDetail[]
}) {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['td-cars', pageId],
    queryFn: () => tdAdminApi.listCars(pageId),
  })
  const cars = data?.cars ?? []

  const [vin, setVin] = useState('')
  const [advisorId, setAdvisorId] = useState(NONE)

  const addMut = useMutation({
    mutationFn: () => tdAdminApi.addCar(pageId, {
      vin: vin.trim(),
      default_advisor_user_id: advisorId === NONE ? undefined : Number(advisorId),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['td-cars', pageId] })
      setVin('')
      setAdvisorId(NONE)
    },
    onError: (e: any) => toast.error(e?.data?.error || e?.message || 'Adăugarea mașinii a eșuat'),
  })

  const removeMut = useMutation({
    mutationFn: (carId: number) => tdAdminApi.removeCar(carId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['td-cars', pageId] }),
    onError: (e: any) => toast.error(e?.data?.error || e?.message || 'Ștergerea a eșuat'),
  })

  const advisorName = (id: number | null) => (id ? users.find((u) => u.id === id)?.name ?? `#${id}` : '—')

  if (isLoading) return <TableSkeleton rows={2} columns={3} />

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
