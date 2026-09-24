import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Pencil, Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { TableSkeleton } from '@/components/shared/TableSkeleton'
import { tdAdminApi, type TdBookingStatus, type TdAdminBooking, type TdOpenSlot } from '@/api/tdAdmin'
import type { UserDetail } from '@/types/users'
import { naiveDate } from '@/lib/naiveDate'

const STATUS_LABEL: Record<TdBookingStatus, string> = {
  pending_confirm: 'În așteptare', confirmed: 'Confirmată', cancelled: 'Anulată',
  expired: 'Expirată', conflict: 'Conflict', completed: 'Finalizată', no_show: 'Neprezentare',
}
const STATUS_VARIANT: Record<TdBookingStatus, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending_confirm: 'outline', confirmed: 'default', cancelled: 'destructive',
  expired: 'secondary', conflict: 'destructive', completed: 'default', no_show: 'destructive',
}

function slotLabel(s: TdOpenSlot): string {
  const car = [s.mark, s.model].filter(Boolean).join(' ') || s.registration_number || s.vin.slice(0, 8)
  const d = naiveDate(s.starts_at)
  const when = d
    ? d.toLocaleString('ro-RO', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
    : s.starts_at
  return `${car} · ${when}`
}

const KEEP = '__keep__'

/** Bookings for a page: per-row advisor reassignment, plus an edit dialog
 *  (client contact / move slot / swap car / status) and delete — all wired to
 *  the company-scoped admin endpoints. */
export default function TdBookingsPanel({ pageId, users }: { pageId: number; users: UserDetail[] }) {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['td-bookings', pageId],
    queryFn: () => tdAdminApi.listBookings(pageId),
  })
  const bookings = data?.bookings ?? []

  const invalidate = () => qc.invalidateQueries({ queryKey: ['td-bookings', pageId] })
  const onErr = (e: any) => toast.error(e?.data?.error || e?.message || 'Operațiunea a eșuat')

  const reassignMut = useMutation({
    mutationFn: (vars: { bookingId: number; advisorUserId: number }) =>
      tdAdminApi.reassignAdvisor(vars.bookingId, vars.advisorUserId),
    onSuccess: () => { toast.success('Consilier reatribuit'); invalidate() },
    onError: onErr,
  })

  // ---- edit dialog ----
  const [carFilter, setCarFilter] = useState<string>('') // '' = all cars, else a vin
  const [editing, setEditing] = useState<TdAdminBooking | null>(null)
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [slotId, setSlotId] = useState<string>(KEEP)
  const [status, setStatus] = useState<string>(KEEP)

  const openEdit = (b: TdAdminBooking) => {
    setEditing(b)
    setName(b.customer_name); setPhone(b.customer_phone_e164); setEmail(b.customer_email)
    setSlotId(KEEP); setStatus(KEEP)
  }

  const { data: slotsData } = useQuery({
    queryKey: ['td-open-slots', pageId],
    queryFn: () => tdAdminApi.listOpenSlots(pageId),
    enabled: !!editing,
  })
  const openSlots = slotsData?.slots ?? []

  const editMut = useMutation({
    mutationFn: (vars: { bid: number; body: Record<string, unknown> }) =>
      tdAdminApi.editBooking(vars.bid, vars.body),
    onSuccess: () => { toast.success('Rezervare actualizată'); setEditing(null); invalidate() },
    onError: onErr,
  })

  const saveEdit = () => {
    if (!editing) return
    const body: Record<string, unknown> = {}
    if (name.trim() !== editing.customer_name) body.name = name.trim()
    if (phone.trim() !== editing.customer_phone_e164) body.phone = phone.trim()
    if (email.trim() !== editing.customer_email) body.email = email.trim()
    if (slotId !== KEEP) body.slot_id = Number(slotId)
    if (status !== KEEP) body.status = status
    if (!Object.keys(body).length) { setEditing(null); return }
    editMut.mutate({ bid: editing.id, body })
  }

  const deleteMut = useMutation({
    mutationFn: (bid: number) => tdAdminApi.deleteBooking(bid),
    onSuccess: () => { toast.success('Rezervare ștearsă'); invalidate() },
    onError: onErr,
  })

  const carLabel = (b: TdAdminBooking) => [b.car_mark, b.car_model].filter(Boolean).join(' ') || b.car_vin || '—'
  const carOptions = Array.from(
    new Map(bookings.filter((b) => b.car_vin).map((b) => [b.car_vin as string, carLabel(b)])).entries(),
  ).sort((a, c) => a[1].localeCompare(c[1]))
  const shown = carFilter ? bookings.filter((b) => b.car_vin === carFilter) : bookings

  if (isLoading) return <TableSkeleton rows={3} columns={6} />

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">Rezervări</h4>
        {carOptions.length > 1 && (
          <Select value={carFilter || 'all'} onValueChange={(v) => setCarFilter(v === 'all' ? '' : v)}>
            <SelectTrigger className="h-8 w-60"><SelectValue placeholder="Toate mașinile" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Toate mașinile</SelectItem>
              {carOptions.map(([vin, label]) => <SelectItem key={vin} value={vin}>{label}</SelectItem>)}
            </SelectContent>
          </Select>
        )}
      </div>
      {!bookings.length ? (
        <p className="text-sm text-muted-foreground">Nicio rezervare încă.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Client</TableHead>
              <TableHead>Mașină</TableHead>
              <TableHead>Contact</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Consilier</TableHead>
              <TableHead className="text-right">Acțiuni</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {shown.map((b) => (
              <TableRow key={b.id}>
                <TableCell className="text-sm font-medium">{b.customer_name}</TableCell>
                <TableCell className="text-sm">{carLabel(b)}</TableCell>
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
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">
                    <Button variant="ghost" size="icon" className="h-8 w-8" aria-label="Editează rezervarea" onClick={() => openEdit(b)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive"
                      aria-label="Șterge rezervarea"
                      disabled={deleteMut.isPending}
                      onClick={() => { if (window.confirm(`Ștergi rezervarea lui ${b.customer_name}? Se eliberează intervalul și se anulează sesiunea planificată.`)) deleteMut.mutate(b.id) }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <Dialog open={!!editing} onOpenChange={(o) => { if (!o) setEditing(null) }}>
        <DialogContent className="max-w-[460px]">
          <DialogHeader><DialogTitle>Editează rezervarea</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="edit-name">Nume client</Label>
              <Input id="edit-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label htmlFor="edit-phone">Telefon (E.164)</Label>
                <Input id="edit-phone" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+40…" />
              </div>
              <div className="space-y-1">
                <Label htmlFor="edit-email">Email</Label>
                <Input id="edit-email" value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
            </div>
            <div className="space-y-1">
              <Label htmlFor="edit-slot">Interval / mașină</Label>
              <Select value={slotId} onValueChange={setSlotId}>
                <SelectTrigger id="edit-slot"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={KEEP}>Păstrează intervalul actual</SelectItem>
                  {openSlots.map((s) => (
                    <SelectItem key={s.id} value={String(s.id)}>{slotLabel(s)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="edit-status">Status</Label>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger id="edit-status"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={KEEP}>Păstrează statusul</SelectItem>
                  {editing?.status === 'pending_confirm' && <SelectItem value="confirmed">Confirmă</SelectItem>}
                  <SelectItem value="cancelled">Anulează</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Renunță</Button>
            <Button onClick={saveEdit} disabled={editMut.isPending}>
              {editMut.isPending ? 'Se salvează…' : 'Salvează'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
