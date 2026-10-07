import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Inbox, Trash2, Copy, Check, Webhook, Phone, Mail, Building2, UserPlus, Download, UserCheck } from 'lucide-react'
import { cn, useDebounce } from '@/lib/utils'
import { marketingApi } from '@/api/marketing'
import type { MktProjectLead, MktLeadStatus, MktWebhookCreated, MktMember } from '@/types/marketing'
import { fmtDatetime } from './utils'

const UNASSIGNED = '__unassigned__'

const STATUSES: MktLeadStatus[] = ['new', 'contacted', 'qualified', 'converted', 'discarded']

const STATUS_LABEL: Record<MktLeadStatus, string> = {
  new: 'New', contacted: 'Contacted', qualified: 'Qualified',
  converted: 'Converted', discarded: 'Discarded',
}

const STATUS_COLOR: Record<MktLeadStatus, string> = {
  new: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-200',
  contacted: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
  qualified: 'bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-200',
  converted: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-200',
  discarded: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
}

/* ── Copy-to-clipboard button ───────────────────────────── */

function CopyButton({ value, label = 'Copy' }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <Button
      size="sm" variant="outline" className="h-7 shrink-0"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        } catch { /* clipboard unavailable — user can select manually */ }
      }}
    >
      {copied ? <Check className="h-3.5 w-3.5 mr-1" /> : <Copy className="h-3.5 w-3.5 mr-1" />}
      {copied ? 'Copied' : label}
    </Button>
  )
}

/* ── Webhook setup dialog ───────────────────────────────── */

function WebhookDialog({ projectId, open, onOpenChange }: {
  projectId: number; open: boolean; onOpenChange: (v: boolean) => void
}) {
  const queryClient = useQueryClient()
  const [label, setLabel] = useState('')
  const [created, setCreated] = useState<MktWebhookCreated | null>(null)

  const { data } = useQuery({
    queryKey: ['mkt-project-webhooks', projectId],
    queryFn: () => marketingApi.getProjectWebhooks(projectId),
    enabled: open,
  })
  const webhooks = data?.webhooks ?? []
  const webhookUrl = data?.webhook_url ?? ''

  const createMut = useMutation({
    mutationFn: () => marketingApi.createWebhook(projectId, label.trim()),
    onSuccess: (res) => {
      setCreated(res)
      setLabel('')
      queryClient.invalidateQueries({ queryKey: ['mkt-project-webhooks', projectId] })
    },
  })

  const revokeMut = useMutation({
    mutationFn: (webhookId: number) => marketingApi.revokeWebhook(projectId, webhookId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mkt-project-webhooks', projectId] }),
  })

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) setCreated(null) }}>
      <DialogContent className="sm:max-w-2xl" aria-describedby={undefined}>
        <DialogHeader><DialogTitle>Lead webhook (Zapier)</DialogTitle></DialogHeader>
        <div className="space-y-5">
          <div className="space-y-1.5">
            <div className="text-sm font-medium">Webhook URL</div>
            <div className="flex items-center gap-2">
              <code className="flex-1 rounded-md border bg-muted px-3 py-2 text-xs break-all">
                POST {webhookUrl}
              </code>
              {webhookUrl && <CopyButton value={webhookUrl} />}
            </div>
            <p className="text-xs text-muted-foreground">
              In Zapier use “Webhooks → POST”, send JSON, and add header
              <code className="mx-1">Authorization: Bearer &lt;token&gt;</code>. The project is
              selected by the token — no project id needed in the body.
            </p>
          </div>

          {/* Freshly-minted token — shown ONCE */}
          {created && (
            <div className="rounded-md border border-amber-300 bg-amber-50 dark:bg-amber-950/40 p-3 space-y-2">
              <div className="text-sm font-medium text-amber-800 dark:text-amber-200">
                Token “{created.label}” created — copy it now, it won’t be shown again.
              </div>
              <div className="flex items-center gap-2">
                <code className="flex-1 rounded bg-background border px-3 py-2 text-xs break-all">{created.token}</code>
                <CopyButton value={created.token} />
              </div>
            </div>
          )}

          {/* Create new token */}
          <div className="space-y-1.5">
            <div className="text-sm font-medium">Create a token</div>
            <div className="flex items-center gap-2">
              <Input
                placeholder="Label (e.g. Facebook Lead Ads)"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
              />
              <Button size="sm" disabled={!label.trim() || createMut.isPending}
                onClick={() => createMut.mutate()}>
                Create
              </Button>
            </div>
          </div>

          {/* Existing tokens */}
          {webhooks.length > 0 && (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Label</TableHead>
                    <TableHead>Token</TableHead>
                    <TableHead>Last used</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="w-10" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {webhooks.map((w) => (
                    <TableRow key={w.id}>
                      <TableCell className="text-sm font-medium">{w.label}</TableCell>
                      <TableCell className="text-xs font-mono text-muted-foreground">{w.token_prefix}…</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{fmtDatetime(w.last_used_at)}</TableCell>
                      <TableCell>
                        {w.is_active
                          ? <Badge variant="outline" className="text-xs">Active</Badge>
                          : <Badge variant="secondary" className="text-xs">Revoked</Badge>}
                      </TableCell>
                      <TableCell>
                        {w.is_active && (
                          <Button variant="ghost" size="icon" className="h-7 w-7"
                            disabled={revokeMut.isPending}
                            onClick={() => revokeMut.mutate(w.id)}>
                            <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

/* ── Main tab ───────────────────────────────────────────── */

export function LeadsTab({ projectId }: { projectId: number }) {
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<MktLeadStatus | 'all'>('all')
  const [assigneeFilter, setAssigneeFilter] = useState<string>('all')
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounce(search, 300)
  const [showWebhooks, setShowWebhooks] = useState(false)

  const assignedParam = assigneeFilter === 'all'
    ? undefined
    : (assigneeFilter === UNASSIGNED ? 'unassigned' : assigneeFilter)

  const { data } = useQuery({
    queryKey: ['mkt-project-leads', projectId, statusFilter, assigneeFilter, debouncedSearch],
    queryFn: () => marketingApi.getProjectLeads(projectId, {
      status: statusFilter === 'all' ? undefined : statusFilter,
      assigned_to: assignedParam,
      search: debouncedSearch || undefined,
    }),
  })
  const leads: MktProjectLead[] = data?.leads ?? []
  const counts = data?.status_counts ?? {}
  const total = Object.values(counts).reduce((a, b) => a + Number(b), 0)

  const { data: membersData } = useQuery({
    queryKey: ['mkt-project-members', projectId],
    queryFn: () => marketingApi.getMembers(projectId),
  })
  const members: MktMember[] = membersData?.members ?? []

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['mkt-project-leads', projectId] })

  const statusMut = useMutation({
    mutationFn: ({ leadId, status }: { leadId: number; status: MktLeadStatus }) =>
      marketingApi.updateLead(projectId, leadId, { status }),
    onSuccess: invalidate,
  })

  const assignMut = useMutation({
    mutationFn: ({ leadId, assigned_to }: { leadId: number; assigned_to: number | null }) =>
      marketingApi.updateLead(projectId, leadId, { assigned_to }),
    onSuccess: invalidate,
  })

  const convertMut = useMutation({
    mutationFn: (leadId: number) => marketingApi.convertLead(projectId, leadId),
    onSuccess: (res) => {
      invalidate()
      queryClient.invalidateQueries({ queryKey: ['mkt-project-clients', projectId] })
      alert(res.created ? 'New CRM client created and linked to this project.'
                        : 'Linked to an existing CRM client and marked converted.')
    },
    onError: () => alert('Could not convert this lead.'),
  })

  const deleteMut = useMutation({
    mutationFn: (leadId: number) => marketingApi.deleteLead(projectId, leadId),
    onSuccess: invalidate,
  })

  const exportHref = marketingApi.leadsExportUrl(projectId, {
    status: statusFilter === 'all' ? undefined : statusFilter,
    assigned_to: assignedParam,
    search: debouncedSearch || undefined,
  })

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {/* Status filter chips */}
        <div className="flex flex-wrap gap-1.5">
          <button
            onClick={() => setStatusFilter('all')}
            className={cn('rounded-full px-3 py-1 text-xs font-medium border transition-colors',
              statusFilter === 'all' ? 'bg-primary text-primary-foreground border-primary' : 'bg-background hover:bg-muted')}
          >
            All {total > 0 && <span className="opacity-70">({total})</span>}
          </button>
          {STATUSES.map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={cn('rounded-full px-3 py-1 text-xs font-medium border transition-colors',
                statusFilter === s ? 'bg-primary text-primary-foreground border-primary' : 'bg-background hover:bg-muted')}
            >
              {STATUS_LABEL[s]} {Number(counts[s] ?? 0) > 0 && <span className="opacity-70">({Number(counts[s])})</span>}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <Select value={assigneeFilter} onValueChange={setAssigneeFilter}>
            <SelectTrigger className="h-8 w-[150px] text-xs"><SelectValue placeholder="Assignee" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all" className="text-xs">All assignees</SelectItem>
              <SelectItem value={UNASSIGNED} className="text-xs">Unassigned</SelectItem>
              {members.map((m) => (
                <SelectItem key={m.user_id} value={String(m.user_id)} className="text-xs">{m.user_name ?? `User ${m.user_id}`}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            className="h-8 w-44"
            placeholder="Search leads..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <Button asChild size="sm" variant="outline">
            <a href={exportHref} download><Download className="h-3.5 w-3.5 mr-1.5" /> Export</a>
          </Button>
          <Button size="sm" variant="outline" onClick={() => setShowWebhooks(true)}>
            <Webhook className="h-3.5 w-3.5 mr-1.5" /> Webhook
          </Button>
        </div>
      </div>

      {leads.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <Inbox className="mx-auto h-8 w-8 mb-2 opacity-40" />
          <div>No leads yet</div>
          <div className="text-xs mt-1">Connect Zapier via the “Webhook” button to start receiving leads here.</div>
        </div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Received</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Contact</TableHead>
                <TableHead>Company</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Message</TableHead>
                <TableHead>Assigned</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-20" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {leads.map((l) => (
                <TableRow key={l.id}>
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">{fmtDatetime(l.created_at)}</TableCell>
                  <TableCell className="text-sm font-medium">{l.contact_name ?? '—'}</TableCell>
                  <TableCell>
                    <div className="flex flex-col gap-0.5">
                      {l.phone && (
                        <span className="flex items-center gap-1 text-xs text-muted-foreground">
                          <Phone className="h-3 w-3" /> {l.phone}
                        </span>
                      )}
                      {l.email && (
                        <span className="flex items-center gap-1 text-xs text-muted-foreground">
                          <Mail className="h-3 w-3" /> {l.email}
                        </span>
                      )}
                      {!l.phone && !l.email && <span className="text-xs text-muted-foreground">—</span>}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">
                    {l.company_name ? (
                      <span className="flex items-center gap-1">
                        <Building2 className="h-3 w-3 text-muted-foreground" /> {l.company_name}
                      </span>
                    ) : '—'}
                  </TableCell>
                  <TableCell className="text-xs">
                    <div className="flex flex-col gap-0.5">
                      {l.source && <Badge variant="outline" className="w-fit text-xs">{l.source}</Badge>}
                      {l.utm_campaign && <span className="text-muted-foreground">{l.utm_campaign}</span>}
                      {!l.source && !l.utm_campaign && <span className="text-muted-foreground">—</span>}
                    </div>
                  </TableCell>
                  <TableCell className="max-w-[16rem] text-sm text-muted-foreground truncate" title={l.message ?? undefined}>
                    {l.message ?? l.model_of_interest ?? '—'}
                  </TableCell>
                  <TableCell>
                    <Select
                      value={l.assigned_to != null ? String(l.assigned_to) : UNASSIGNED}
                      onValueChange={(v) => assignMut.mutate({ leadId: l.id, assigned_to: v === UNASSIGNED ? null : Number(v) })}
                    >
                      <SelectTrigger className="h-7 w-[130px] text-xs"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value={UNASSIGNED} className="text-xs text-muted-foreground">Unassigned</SelectItem>
                        {members.map((m) => (
                          <SelectItem key={m.user_id} value={String(m.user_id)} className="text-xs">{m.user_name ?? `User ${m.user_id}`}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell>
                    <Select value={l.status} onValueChange={(v) => statusMut.mutate({ leadId: l.id, status: v as MktLeadStatus })}>
                      <SelectTrigger className={cn('h-7 w-[120px] text-xs border-0', STATUS_COLOR[l.status])}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {STATUSES.map((s) => (
                          <SelectItem key={s} value={s} className="text-xs">{STATUS_LABEL[s]}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1">
                      {l.converted_client_id ? (
                        <Badge variant="outline" className="text-xs text-emerald-600 border-emerald-300">
                          <UserCheck className="h-3 w-3 mr-1" /> CRM
                        </Badge>
                      ) : (
                        <Button
                          variant="ghost" size="icon" className="h-7 w-7"
                          title="Convert to CRM client"
                          disabled={convertMut.isPending}
                          onClick={() => {
                            if (confirm('Create/link a CRM client from this lead and mark it converted?'))
                              convertMut.mutate(l.id)
                          }}
                        >
                          <UserPlus className="h-3.5 w-3.5 text-muted-foreground" />
                        </Button>
                      )}
                      <Button variant="ghost" size="icon" className="h-7 w-7"
                        onClick={() => deleteMut.mutate(l.id)}>
                        <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <WebhookDialog projectId={projectId} open={showWebhooks} onOpenChange={setShowWebhooks} />
    </div>
  )
}
