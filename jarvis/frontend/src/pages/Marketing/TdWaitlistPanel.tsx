import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ClipboardList } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { EmptyState } from '@/components/shared/EmptyState'
import { TableSkeleton } from '@/components/shared/TableSkeleton'
import { tdAdminApi, type TdWaitlistStatus } from '@/api/tdAdmin'

const STATUS_LABEL: Record<TdWaitlistStatus, string> = {
  new: 'Nou', contacted: 'Contactat', done: 'Rezolvat', dismissed: 'Respins',
}
const STATUSES: TdWaitlistStatus[] = ['new', 'contacted', 'done', 'dismissed']

/** Waiting-list requests for an event (mkt_td_waitlist) — contact + optional
 *  preferred car (VIN) / note; staff move each through a status. */
export default function TdWaitlistPanel({ pageId }: { pageId: number }) {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['td-waitlist', pageId],
    queryFn: () => tdAdminApi.listWaitlist(pageId),
  })
  const entries = data?.waitlist ?? []
  const statusMut = useMutation({
    mutationFn: (v: { id: number; status: TdWaitlistStatus }) => tdAdminApi.updateWaitlist(v.id, v.status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['td-waitlist', pageId] }),
    onError: (e: any) => toast.error(e?.data?.error || e?.message || 'Actualizarea a eșuat'),
  })
  if (isLoading) return <TableSkeleton rows={3} columns={5} />
  if (!entries.length) {
    return (
      <EmptyState
        icon={<ClipboardList className="h-10 w-10" />}
        title="Nicio cerere pe lista de așteptare"
        description="Cererile clienților care nu au găsit un interval apar aici."
      />
    )
  }
  return (
    <Card className="overflow-hidden py-0">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Client</TableHead>
            <TableHead>Contact</TableHead>
            <TableHead>Preferință</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Data</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {entries.map((w) => (
            <TableRow key={w.id}>
              <TableCell className="text-sm font-medium">{w.customer_name}</TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {w.customer_phone_e164}
                {w.customer_email && <><br />{w.customer_email}</>}
              </TableCell>
              <TableCell className="text-sm">
                {w.preferred_car_vin && <div className="font-mono text-xs">{w.preferred_car_vin}</div>}
                {w.note && <div className="text-xs text-muted-foreground">{w.note}</div>}
                {!w.preferred_car_vin && !w.note && <span className="text-muted-foreground">—</span>}
              </TableCell>
              <TableCell>
                <Select
                  value={w.status}
                  onValueChange={(v) => statusMut.mutate({ id: w.id, status: v as TdWaitlistStatus })}
                  disabled={statusMut.isPending}
                >
                  <SelectTrigger className="h-8 w-36"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {STATUSES.map((s) => <SelectItem key={s} value={s}>{STATUS_LABEL[s]}</SelectItem>)}
                  </SelectContent>
                </Select>
              </TableCell>
              <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                {new Date(w.created_at).toLocaleDateString('ro-RO')}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  )
}
