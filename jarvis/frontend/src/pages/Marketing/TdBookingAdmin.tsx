import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { CalendarClock, Lock, Plus, Settings, Unlock, Upload, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { EmptyState } from '@/components/shared/EmptyState'
import { TableSkeleton } from '@/components/shared/TableSkeleton'
import { MultiSelectPills } from '@/components/shared/MultiSelectPills'
import { foiParcursApi } from '@/api/foiParcurs'
import { hrApi } from '@/api/hr'
import { usersApi } from '@/api/users'
import { tdAdminApi, type TdAdminPage } from '@/api/tdAdmin'
import type { UserDetail } from '@/types/users'
import TdCarsPanel from './TdCarsPanel'
import TdWindowsPanel from './TdWindowsPanel'
import TdBookingsPanel from './TdBookingsPanel'
import TdBookingHelp from './TdBookingHelp'

const NONE = '__none__'

// Event logo: read client-side into a base64 data URL and ship it inline in
// the create/update payload -- mirrors the company-logo pattern
// (organization/routes.py's api_upload_company_logo, "Stores as base64 data
// URL in DB"), but skips the multipart round trip since this page has no
// id yet at create time. No Spaces/object storage involved.
const MAX_LOGO_BYTES = 1.5 * 1024 * 1024 // 1.5MB

function readLogoAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('read failed'))
    reader.onload = () => resolve(reader.result as string)
    reader.readAsDataURL(file)
  })
}

/** Compact logo upload/preview control shared by the Create and Setări
 *  dialogs. `value` is the current base64 data URL (or null/undefined when
 *  no logo is set); `onChange` receives the new data URL, or null on remove. */
function LogoUploadField({ value, onChange }: {
  value?: string | null
  onChange: (dataUrl: string | null) => void
}) {
  const [busy, setBusy] = useState(false)

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (!file.type.startsWith('image/')) {
      toast.error('Fișierul trebuie să fie o imagine')
      return
    }
    if (file.size > MAX_LOGO_BYTES) {
      toast.error('Logo prea mare (max 1.5MB)')
      return
    }
    setBusy(true)
    try {
      onChange(await readLogoAsDataUrl(file))
    } catch {
      toast.error('Nu am putut citi fișierul')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-1.5">
      <Label className="text-xs">Logo eveniment</Label>
      <div className="flex items-center gap-3">
        {value ? (
          <div className="relative">
            <img src={value} alt="Logo eveniment" className="h-10 w-auto max-w-[140px] rounded border object-contain p-1" />
            <button
              type="button"
              onClick={() => onChange(null)}
              disabled={busy}
              className="absolute -right-1.5 -top-1.5 rounded-full bg-destructive p-0.5 text-destructive-foreground shadow-sm hover:bg-destructive/90"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        ) : (
          <div className="flex h-10 w-20 items-center justify-center rounded border border-dashed text-muted-foreground">
            <Upload className="h-4 w-4" />
          </div>
        )}
        <label className="cursor-pointer">
          <input type="file" accept="image/*" className="hidden" onChange={handleFile} disabled={busy} />
          <span className="text-xs font-medium text-primary hover:underline">
            {busy ? 'Se încarcă…' : value ? 'Schimbă' : 'Încarcă'}
          </span>
        </label>
      </div>
    </div>
  )
}
const STATUS_LABEL: Record<TdAdminPage['status'], string> = { draft: 'Ciornă', open: 'Deschisă', closed: 'Închisă' }
const STATUS_VARIANT: Record<TdAdminPage['status'], 'secondary' | 'default' | 'outline'> = {
  draft: 'secondary', open: 'default', closed: 'outline',
}

/** `datetime-local` inputs work in the browser's local time with no
 *  timezone suffix -- these mirror CampaignEditor.tsx's (HappyBoard)
 *  isoToLocal/localToIso helpers for the same round trip. */
function isoToLocal(iso?: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function localToIso(local: string): string | null {
  if (!local) return null
  const d = new Date(local)
  return Number.isNaN(d.getTime()) ? null : d.toISOString()
}

/** True when two opens_at/closes_at values represent the same instant --
 *  compares by timestamp (not string) since the DB's ISO format and
 *  localToIso's toISOString() output differ byte-for-byte even when equal
 *  (e.g. "+00:00" vs ".000Z"). */
function isoEqual(a: string | null, b: string | null): boolean {
  if (a === b) return true
  if (!a || !b) return false
  const ta = new Date(a).getTime()
  const tb = new Date(b).getTime()
  return !Number.isNaN(ta) && !Number.isNaN(tb) && ta === tb
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
  const [settingsOpen, setSettingsOpen] = useState(false)
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
                onClick={() => setSettingsOpen(true)}
              >
                <Settings className="mr-1.5 h-4 w-4" />Setări
              </Button>
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

      {selectedPage && (
        <EventSettingsDialog
          open={settingsOpen}
          onOpenChange={setSettingsOpen}
          page={selectedPage}
          users={userList}
          onSaved={() => qc.invalidateQueries({ queryKey: ['td-pages', companyId] })}
        />
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
  const [logoUrl, setLogoUrl] = useState<string | null>(null)

  const reset = () => {
    setCompanyId(defaultCompanyId ? String(defaultCompanyId) : ''); setSlug(''); setTitle('')
    setEventId(NONE); setLogoUrl(null)
  }

  const createMut = useMutation({
    mutationFn: () => tdAdminApi.createPage({
      company_id: Number(companyId),
      slug: slug.trim(),
      title: title.trim() || undefined,
      event_id: eventId === NONE ? undefined : Number(eventId),
      logo_url: logoUrl || undefined,
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
          <LogoUploadField value={logoUrl} onChange={setLogoUrl} />
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

/** Editable event metadata -- Titlu/Intro/Mesaj de mulțumire, the notified
 *  advisor list, the booking window (opens_at/closes_at) and the slotting
 *  parameters. Wired to the already-existing `tdAdminApi.updatePage`
 *  (PATCH .../pages/<id>), which whitelists these exact
 *  mkt_td_booking_pages columns (see _PAGE_COLS in
 *  td_booking_repository.py) -- this dialog is the first UI writer of any
 *  of them (the create flow only sets title/event_id/slug). Re-syncs its
 *  local form state from `page` every time it's opened, so switching the
 *  selected page (or a background refetch) can't leave stale values behind. */
function EventSettingsDialog({ open, onOpenChange, page, users, onSaved }: {
  open: boolean
  onOpenChange: (o: boolean) => void
  page: TdAdminPage
  users: UserDetail[]
  onSaved: () => void
}) {
  const [title, setTitle] = useState('')
  const [intro, setIntro] = useState('')
  const [thankYou, setThankYou] = useState('')
  const [logoUrl, setLogoUrl] = useState<string | null>(null)
  const [notifyIds, setNotifyIds] = useState<(number | string)[]>([])
  const [opensAt, setOpensAt] = useState('')
  const [closesAt, setClosesAt] = useState('')
  const [minLead, setMinLead] = useState('')
  const [slotMinutes, setSlotMinutes] = useState('')
  const [bufferMinutes, setBufferMinutes] = useState('')
  const [maxPerContact, setMaxPerContact] = useState('')

  useEffect(() => {
    if (!open) return
    setTitle(page.title ?? '')
    setIntro(page.intro ?? '')
    setThankYou(page.thank_you ?? '')
    setLogoUrl(page.logo_url ?? null)
    setNotifyIds(page.notify_user_ids ?? [])
    setOpensAt(isoToLocal(page.opens_at))
    setClosesAt(isoToLocal(page.closes_at))
    setMinLead(String(page.min_lead_minutes ?? ''))
    setSlotMinutes(String(page.slot_minutes ?? ''))
    setBufferMinutes(String(page.buffer_minutes ?? ''))
    setMaxPerContact(String(page.max_bookings_per_contact ?? ''))
  }, [open, page])

  const userOptions = users.filter((u) => u.is_active).map((u) => ({ value: u.id, label: u.name }))

  const saveMut = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {}

      const nextTitle = title.trim() || null
      if (nextTitle !== (page.title ?? null)) body.title = nextTitle
      const nextIntro = intro.trim() || null
      if (nextIntro !== (page.intro ?? null)) body.intro = nextIntro
      const nextThankYou = thankYou.trim() || null
      if (nextThankYou !== (page.thank_you ?? null)) body.thank_you = nextThankYou
      if (logoUrl !== (page.logo_url ?? null)) body.logo_url = logoUrl

      const nextNotifyIds = notifyIds.map(Number)
      const origNotifyIds = page.notify_user_ids ?? []
      const sameNotify = nextNotifyIds.length === origNotifyIds.length
        && [...nextNotifyIds].sort((a, b) => a - b).every((v, i) => v === [...origNotifyIds].sort((a, b) => a - b)[i])
      if (!sameNotify) body.notify_user_ids = nextNotifyIds

      const nextOpensAt = localToIso(opensAt)
      if (!isoEqual(nextOpensAt, page.opens_at)) body.opens_at = nextOpensAt
      const nextClosesAt = localToIso(closesAt)
      if (!isoEqual(nextClosesAt, page.closes_at)) body.closes_at = nextClosesAt

      const nextMinLead = minLead === '' ? null : Number(minLead)
      if (nextMinLead !== null && nextMinLead !== page.min_lead_minutes) body.min_lead_minutes = nextMinLead
      const nextSlotMinutes = slotMinutes === '' ? null : Number(slotMinutes)
      if (nextSlotMinutes !== null && nextSlotMinutes !== page.slot_minutes) body.slot_minutes = nextSlotMinutes
      const nextBufferMinutes = bufferMinutes === '' ? null : Number(bufferMinutes)
      if (nextBufferMinutes !== null && nextBufferMinutes !== page.buffer_minutes) body.buffer_minutes = nextBufferMinutes
      const nextMaxPerContact = maxPerContact === '' ? null : Number(maxPerContact)
      if (nextMaxPerContact !== null && nextMaxPerContact !== page.max_bookings_per_contact) {
        body.max_bookings_per_contact = nextMaxPerContact
      }

      return tdAdminApi.updatePage(page.id, body)
    },
    onSuccess: () => {
      toast.success('Setări salvate')
      onSaved()
      onOpenChange(false)
    },
    onError: (e: any) => toast.error(e?.data?.error || e?.message || 'Salvarea setărilor a eșuat'),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader><DialogTitle>Setări eveniment</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label className="text-xs">Titlu</Label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Intro</Label>
            <Textarea rows={3} value={intro} onChange={(e) => setIntro(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Mesaj de mulțumire</Label>
            <Textarea rows={3} value={thankYou} onChange={(e) => setThankYou(e.target.value)} />
          </div>
          <LogoUploadField value={logoUrl} onChange={setLogoUrl} />
          <div className="space-y-1.5">
            <Label className="text-xs">Consilieri notificați</Label>
            <MultiSelectPills
              options={userOptions}
              selected={notifyIds}
              onChange={setNotifyIds}
              placeholder="Fără consilieri notificați"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Deschidere</Label>
              <Input type="datetime-local" value={opensAt} onChange={(e) => setOpensAt(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Închidere</Label>
              <Input type="datetime-local" value={closesAt} onChange={(e) => setClosesAt(e.target.value)} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Timp minim înainte (min)</Label>
              <Input type="number" min={0} value={minLead} onChange={(e) => setMinLead(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Max programări / contact</Label>
              <Input type="number" min={1} value={maxPerContact} onChange={(e) => setMaxPerContact(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Durată interval (min)</Label>
              <Input type="number" min={1} value={slotMinutes} onChange={(e) => setSlotMinutes(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Pauză între intervale (min)</Label>
              <Input type="number" min={0} value={bufferMinutes} onChange={(e) => setBufferMinutes(e.target.value)} />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Anulează</Button>
          <Button disabled={saveMut.isPending} onClick={() => saveMut.mutate()}>
            {saveMut.isPending ? 'Se salvează…' : 'Salvează'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
