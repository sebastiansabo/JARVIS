import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { TableSkeleton } from '@/components/shared/TableSkeleton'
import { tdAdminApi, type TdBookingStatus } from '@/api/tdAdmin'
import type { UserDetail } from '@/types/users'

const STATUS_LABEL: Record<TdBookingStatus, string> = {
  pending_confirm: 'În așteptare', confirmed: 'Confirmată', cancelled: 'Anulată',
  expired: 'Expirată', conflict: 'Conflict', completed: 'Finalizată', no_show: 'Neprezentare',
}
const STATUS_VARIANT: Record<TdBookingStatus, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending_confirm: 'outline', confirmed: 'default', cancelled: 'destructive',
  expired: 'secondary', conflict: 'destructive', completed: 'default', no_show: 'destructive',
}

/** Bookings for a page, with per-row advisor reassignment. Unlike Cars/Windows,
 *  the backend DOES expose GET .../bookings, so this is a normal query. */
export default function TdBookingsPanel({ pageId, users }: { pageId: number; users: UserDetail[] }) {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['td-bookings', pageId],
    queryFn: () => tdAdminApi.listBookings(pageId),
  })
  const bookings = data?.bookings ?? []

  const reassignMut = useMutation({
    mutationFn: (vars: { bookingId: number; advisorUserId: number }) =>
      tdAdminApi.reassignAdvisor(vars.bookingId, vars.advisorUserId),
    onSuccess: () => {
      toast.success('Consilier reatribuit')
      qc.invalidateQueries({ queryKey: ['td-bookings', pageId] })
    },
    onError: (e: any) => toast.error(e?.data?.error || e?.message || 'Reatribuirea a eșuat'),
  })

  if (isLoading) return <TableSkeleton rows={3} columns={4} />

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold">Rezervări</h4>
      {!bookings.length ? (
        <p className="text-sm text-muted-foreground">Nicio rezervare încă.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Client</TableHead>
              <TableHead>Contact</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Consilier</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {bookings.map((b) => (
              <TableRow key={b.id}>
                <TableCell className="text-sm font-medium">{b.customer_name}</TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  <div>{b.customer_phone_e164}</div>
                  <div>{b.customer_email}</div>
                </TableCell>
                <TableCell><Badge variant={STATUS_VARIANT[b.status]}>{STATUS_LABEL[b.status]}</Badge></TableCell>
                <TableCell>
                  <Select
                    value={b.advisor_user_id ? String(b.advisor_user_id) : ''}
                    onValueChange={(v) => reassignMut.mutate({ bookingId: b.id, advisorUserId: Number(v) })}
                  >
                    <SelectTrigger className="h-8 w-44"><SelectValue placeholder="Alege consilier" /></SelectTrigger>
                    <SelectContent>
                      {users.filter((u) => u.is_active).map((u) => (
                        <SelectItem key={u.id} value={String(u.id)}>{u.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
