import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { TableSkeleton } from '@/components/shared/TableSkeleton'
import { tdAdminApi } from '@/api/tdAdmin'

/** Availability windows (date + time range) a page's slots are materialized
 *  from. Backed by a real `useQuery` against GET .../pages/<id>/windows,
 *  invalidated after add, so the table survives a reload (unlike the old
 *  session-local `useState` this replaced). No DELETE route exists yet, so
 *  removal is still out of scope here. */
export default function TdWindowsPanel({ pageId }: { pageId: number }) {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['td-windows', pageId],
    queryFn: () => tdAdminApi.listWindows(pageId),
  })
  const windows = data?.windows ?? []

  const [date, setDate] = useState('')
  const [start, setStart] = useState('09:00')
  const [end, setEnd] = useState('17:00')

  const addMut = useMutation({
    mutationFn: () => tdAdminApi.addWindow(pageId, { window_date: date, start_time: start, end_time: end }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['td-windows', pageId] })
      setDate('')
    },
    onError: (e: any) => toast.error(e?.data?.error || e?.message || 'Adăugarea intervalului a eșuat'),
  })

  if (isLoading) return <TableSkeleton rows={2} columns={3} />

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold">Intervale disponibile</h4>
      <div className="flex flex-wrap items-end gap-2">
        <div className="space-y-1.5">
          <Label className="text-xs">Data</Label>
          <Input type="date" className="h-8 w-40" value={date} onChange={(e) => setDate(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">De la</Label>
          <Input type="time" className="h-8 w-28" value={start} onChange={(e) => setStart(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Până la</Label>
          <Input type="time" className="h-8 w-28" value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
        <Button size="sm" className="h-8" disabled={!date || !start || !end || addMut.isPending} onClick={() => addMut.mutate()}>
          <Plus className="mr-1.5 h-4 w-4" />{addMut.isPending ? 'Se adaugă…' : 'Adaugă'}
        </Button>
      </div>

      {!windows.length ? (
        <p className="text-sm text-muted-foreground">Niciun interval adăugat.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Data</TableHead>
              <TableHead>De la</TableHead>
              <TableHead>Până la</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {windows.map((w) => (
              <TableRow key={w.id}>
                <TableCell className="text-sm">{w.window_date}</TableCell>
                <TableCell className="text-sm">{w.start_time}</TableCell>
                <TableCell className="text-sm">{w.end_time}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
