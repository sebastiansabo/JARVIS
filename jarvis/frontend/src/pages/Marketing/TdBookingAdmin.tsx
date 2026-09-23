import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { CalendarClock, Lock, Plus, Unlock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { EmptyState } from '@/components/shared/EmptyState'
import { TableSkeleton } from '@/components/shared/TableSkeleton'
import { foiParcursApi } from '@/api/foiParcurs'
import { hrApi } from '@/api/hr'
import { usersApi } from '@/api/users'
import { tdAdminApi, type TdAdminPage } from '@/api/tdAdmin'
import TdCarsPanel from './TdCarsPanel'
import TdWindowsPanel from './TdWindowsPanel'
import TdBookingsPanel from './TdBookingsPanel'
import TdBookingHelp from './TdBookingHelp'

const NONE = '__none__'
const STATUS_LABEL: Record<TdAdminPage['status'], string> = { draft: 'Ciornă', open: 'Deschisă', closed: 'Închisă' }
const STATUS_VARIANT: Record<TdAdminPage['status'], 'secondary' | 'default' | 'outline'> = {
  draft: 'secondary', open: 'default', closed: 'outline',
}

/** Staff admin for public test-drive booking pages ("Evenimente TD" in the
 *  Marketing module) -- create a page → add cars (+ default advisor) → add
 *  availability windows → Materialize slots → Open the page → track/reassign
 *  bookings. Consumes `tdAdminApi` (src/api/tdAdmin.ts), the authed
 *  counterpart of the public `/td/<slug>` flow (src/api/td.ts,
 *  src/pages/Public/PublicTdBooking.tsx).
 *
 *  `companyId` scopes the page list and the Create dialog's default company.
 *  As a standalone Marketing route it defaults to 0 ("Toate companiile") --
 *  every company's pages are listed and the Create dialog forces an explicit
 *  company choice. */
export default function TdBookingAdmin({ companyId = 0 }: { companyId?: number }) {
  const qc = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [selectedPageId, setSelectedPageId] = useState<number | null>(null)

  const { data: companiesData } = useQuery({
    queryKey: ['fp-companies'],
    queryFn: () => foiParcursApi.getCompanies(),
    staleTime: 60_000,
  })
  const companies = companiesData?.companies ?? []

  const { data: events } = useQuery({
    queryKey: ['hr-events-td-admin'],
    queryFn: () => hrApi.getEvents(),
    staleTime: 60_000,
  })

  // Generic staff user list (id + name), the same source Settings → Approvals
  // uses for its "specific user" approver picker -- TestDriveForm's own
  // "advisor" field is a free-text name, not a user id, so it can't back the
  // FK-typed `advisor_user_id` this admin UI needs.
  const { data: users } = useQuery({
    queryKey: ['td-admin-users'],
    queryFn: () => usersApi.getUsers(),
    staleTime: 60_000,
  })
  const userList = users ?? []

  const { data: pagesData, isLoading: pagesLoading } = useQuery({
    queryKey: ['td-pages', companyId],
    queryFn: () => tdAdminApi.listPages(companyId || undefined),
  })
  const pages = pagesData?.pages ?? []
  const selectedPage = pages.find((p) => p.id === selectedPageId) ?? null

  const selectPage = (id: number) => {
    setSelectedPageId(id)
  }

  const setStatusMut = useMutation({
    mutationFn: (vars: { id: number; status: string }) => tdAdminApi.setStatus(vars.id, vars.status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['td-pages', companyId] }),
    onError: (e: any) => toast.error(e?.data?.error || e?.message || 'Schimbarea statusului a eșuat'),
  })

  const materializeMut = useMutation({
    mutationFn: (id: number) => tdAdminApi.materialize(id),
    onSuccess: (res) => toast.success(`${res.inserted} sloturi create`),
    onError: (e: any) => toast.error(e?.data?.error || e?.message || 'Generarea sloturilor a eșuat'),
  })

  const companyName = (id: number) => companies.find((c) => c.id === id)?.company ?? `#${id}`

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold">Pagini programare Test Drive</h3>
          <p className="text-sm text-muted-foreground">Pagini publice de programare (evenimente, lansări) — mașini, intervale și rezervări.</p>
        </div>
        <div className="flex items-center gap-2">
          <TdBookingHelp />
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="mr-1.5 h-4 w-4" />Pagină nouă
          </Button>
        </div>
      </div>

      {pagesLoading ? (
        <TableSkeleton rows={4} columns={5} />
      ) : !pages.length ? (
        <EmptyState
          icon={<CalendarClock className="h-10 w-10" />}
          title="Nicio pagină de programare"
          description="Creează prima pagină cu butonul de mai sus."
        />
      ) : (
        <Card className="overflow-hidden py-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Slug</TableHead>
                <TableHead>Titlu</TableHead>
                <TableHead>Companie</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Creat</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pages.map((p) => (
                <TableRow
                  key={p.id}
                  className={`cursor-pointer hover:bg-muted/50 ${p.id === selectedPageId ? 'bg-muted/40' : ''}`}
                  onClick={() => selectPage(p.id)}
                >
                  <TableCell className="font-mono text-xs">{p.slug}</TableCell>
                  <TableCell className="text-sm">{p.title || '—'}</TableCell>
                  <TableCell className="text-sm">{companyName(p.company_id)}</TableCell>
                  <TableCell><Badge variant={STATUS_VARIANT[p.status]}>{STATUS_LABEL[p.status]}</Badge></TableCell>
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                    {new Date(p.created_at).toLocaleDateString('ro-RO')}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      {selectedPage && (
        <Card className="space-y-6 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <h3 className="text-base font-semibold">{selectedPage.title || selectedPage.slug}</h3>
              <Badge variant={STATUS_VARIANT[selectedPage.status]}>{STATUS_LABEL[selectedPage.status]}</Badge>
              <span className="font-mono text-xs text-muted-foreground">/td/{selectedPage.slug}</span>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline" size="sm" className="h-8"
                disabled={materializeMut.isPending}
                onClick={() => materializeMut.mutate(selectedPage.id)}
              >
                <CalendarClock className="mr-1.5 h-4 w-4" />Materializează sloturi
              </Button>
              <Button
                variant="outline" size="sm" className="h-8"
                disabled={selectedPage.status === 'open' || setStatusMut.isPending}
                onClick={() => setStatusMut.mutate({ id: selectedPage.id, status: 'open' })}
              >
                <Unlock className="mr-1.5 h-4 w-4" />Deschide
              </Button>
              <Button
                variant="outline" size="sm" className="h-8"
                disabled={selectedPage.status === 'closed' || setStatusMut.isPending}
                onClick={() => setStatusMut.mutate({ id: selectedPage.id, status: 'closed' })}
              >
                <Lock className="mr-1.5 h-4 w-4" />Închide
              </Button>
            </div>
          </div>

          <TdCarsPanel pageId={selectedPage.id} companyId={selectedPage.company_id} users={userList} />
          <TdWindowsPanel pageId={selectedPage.id} />
          <TdBookingsPanel pageId={selectedPage.id} users={userList} />
        </Card>
      )}

      <CreatePageDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        companies={companies}
        events={events ?? []}
        defaultCompanyId={companyId || undefined}
        onCreated={(page) => {
          qc.invalidateQueries({ queryKey: ['td-pages', companyId] })
          selectPage(page.id)
        }}
      />
    </div>
  )
}

function CreatePageDialog({ open, onOpenChange, companies, events, defaultCompanyId, onCreated }: {
  open: boolean
  onOpenChange: (o: boolean) => void
  companies: { id: number; company: string }[]
  events: { id: number; name: string }[]
  defaultCompanyId?: number
  onCreated: (page: TdAdminPage) => void
}) {
  const [companyId, setCompanyId] = useState<string>(defaultCompanyId ? String(defaultCompanyId) : '')
  const [slug, setSlug] = useState('')
  const [title, setTitle] = useState('')
  const [eventId, setEventId] = useState(NONE)

  const reset = () => { setCompanyId(defaultCompanyId ? String(defaultCompanyId) : ''); setSlug(''); setTitle(''); setEventId(NONE) }

  const createMut = useMutation({
    mutationFn: () => tdAdminApi.createPage({
      company_id: Number(companyId),
      slug: slug.trim(),
      title: title.trim() || undefined,
      event_id: eventId === NONE ? undefined : Number(eventId),
    }),
    onSuccess: (page) => {
      toast.success('Pagină creată')
      onCreated(page)
      reset()
      onOpenChange(false)
    },
    onError: (e: any) => toast.error(e?.data?.error || e?.message || 'Crearea paginii a eșuat'),
  })

  const canSave = !!companyId && !!slug.trim()

  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) reset() }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>Pagină nouă de programare</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label className="text-xs">Companie *</Label>
            <Select value={companyId} onValueChange={setCompanyId}>
              <SelectTrigger><SelectValue placeholder="Selectează compania" /></SelectTrigger>
              <SelectContent>
                {companies.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Slug *</Label>
            <Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="ex: bmw-x5-td" />
            <p className="text-xs text-muted-foreground">Pagina publică va fi la /td/{slug || '…'}</p>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Titlu</Label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Ex: Test Drive BMW X5" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Eveniment (opțional)</Label>
            <Select value={eventId} onValueChange={setEventId}>
              <SelectTrigger><SelectValue placeholder="Fără eveniment" /></SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>Fără eveniment</SelectItem>
                {events.map((e) => (
                  <SelectItem key={e.id} value={String(e.id)}>{e.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Anulează</Button>
          <Button disabled={!canSave || createMut.isPending} onClick={() => createMut.mutate()}>
            {createMut.isPending ? 'Se creează…' : 'Creează'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
