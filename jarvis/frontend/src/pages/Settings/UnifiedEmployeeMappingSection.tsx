import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Users,
  RefreshCw,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Search,
  Link as LinkIcon,
  Unlink,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { toast } from 'sonner'
import {
  identityApi,
  type IdentityUnifiedRow,
  type IdentityUnifiedView,
  type IdentityJarvisUser,
  type IdentityOrphanSincron,
  type IdentityOrphanBiostar,
  type IdentityMappingSource,
} from '@/api/identity'

type StatusFilter = 'all' | 'fully_mapped' | 'sincron_only' | 'biostar_only' | 'unmapped'

function computeStatus(row: IdentityUnifiedRow): Exclude<StatusFilter, 'all'> {
  const hasSincron = (row.sincron_mappings?.length ?? 0) > 0
  const hasBiostar = (row.biostar_mappings?.length ?? 0) > 0
  if (hasSincron && hasBiostar) return 'fully_mapped'
  if (hasSincron) return 'sincron_only'
  if (hasBiostar) return 'biostar_only'
  return 'unmapped'
}

function StatusPill({ status }: { status: Exclude<StatusFilter, 'all'> }) {
  if (status === 'fully_mapped') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-green-500/10 px-2 py-0.5 text-xs font-medium text-green-600">
        <CheckCircle2 className="h-3 w-3" /> Fully mapped
      </span>
    )
  }
  if (status === 'sincron_only') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-600">
        <AlertTriangle className="h-3 w-3" /> Sincron only
      </span>
    )
  }
  if (status === 'biostar_only') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-600">
        <AlertTriangle className="h-3 w-3" /> BioStar only
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-red-500/10 px-2 py-0.5 text-xs font-medium text-red-600">
      <XCircle className="h-3 w-3" /> Unmapped
    </span>
  )
}

function MethodBadge({ method, confidence }: { method?: string | null; confidence?: number | null }) {
  if (!method) return <span className="text-xs text-muted-foreground">—</span>
  const label = method.replace('auto_', '').replace('_', ' ')
  return (
    <span className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
      {label}
      {confidence != null && (
        <span className="text-[10px] font-medium">{Math.round(confidence)}</span>
      )}
    </span>
  )
}

type DialogState =
  | { mode: 'closed' }
  | {
      mode: 'mapSincron'
      orphan: IdentityOrphanSincron
    }
  | {
      mode: 'mapBiostar'
      orphan: IdentityOrphanBiostar
    }

export function UnifiedEmployeeMappingSection() {
  const qc = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [search, setSearch] = useState('')
  const [dialog, setDialog] = useState<DialogState>({ mode: 'closed' })
  const [dialogSelection, setDialogSelection] = useState<string>('')

  const { data, isLoading, isError } = useQuery<IdentityUnifiedView>({
    queryKey: ['identity', 'employees'],
    queryFn: identityApi.getEmployees,
  })

  const { data: jarvisUsers = [] } = useQuery<IdentityJarvisUser[]>({
    queryKey: ['identity', 'jarvisUsers'],
    queryFn: identityApi.getJarvisUsers,
  })

  const autoMapMut = useMutation({
    mutationFn: () => identityApi.autoMapAll(),
    onSuccess: (res) => {
      const r = res.data
      qc.invalidateQueries({ queryKey: ['identity'] })
      qc.invalidateQueries({ queryKey: ['sincron'] })
      qc.invalidateQueries({ queryKey: ['biostar'] })
      const total = r?.total_mapped ?? 0
      if (total > 0) {
        toast.success(
          `Mapped ${total} employees — Sincron: ${(r?.sincron_cnp ?? 0) + (r?.sincron_name ?? 0)} · BioStar: ${
            (r?.biostar_cnp ?? 0) + (r?.biostar_email ?? 0) + (r?.biostar_name ?? 0) + (r?.biostar_cross ?? 0)
          }`,
        )
      } else {
        toast.info('No new employees to map')
      }
    },
    onError: () => toast.error('Auto-map failed'),
  })

  const setMappingMut = useMutation({
    mutationFn: (vars: {
      userId: number
      source: IdentityMappingSource
      external_id: string
      company_name?: string
    }) =>
      identityApi.setMapping(vars.userId, {
        source: vars.source,
        external_id: vars.external_id,
        company_name: vars.company_name,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['identity'] })
      qc.invalidateQueries({ queryKey: ['sincron'] })
      qc.invalidateQueries({ queryKey: ['biostar'] })
      toast.success('Mapping updated')
      setDialog({ mode: 'closed' })
      setDialogSelection('')
    },
    onError: () => toast.error('Failed to update mapping'),
  })

  const removeMappingMut = useMutation({
    mutationFn: (vars: {
      userId: number
      source: IdentityMappingSource
      external_id: string
      company_name?: string
    }) =>
      identityApi.removeMapping(vars.userId, vars.source, {
        external_id: vars.external_id,
        company_name: vars.company_name,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['identity'] })
      qc.invalidateQueries({ queryKey: ['sincron'] })
      qc.invalidateQueries({ queryKey: ['biostar'] })
      toast.success('Mapping removed')
    },
    onError: () => toast.error('Failed to remove mapping'),
  })

  const filtered = useMemo(() => {
    const rows = data?.users ?? []
    const term = search.trim().toLowerCase()
    return rows.filter((row) => {
      const status = computeStatus(row)
      if (statusFilter !== 'all' && status !== statusFilter) return false
      if (!term) return true
      const haystack = [
        row.name,
        row.email ?? '',
        row.cnp ?? '',
        row.company ?? '',
        row.department ?? '',
        ...(row.biostar_mappings ?? []).map(m => `${m.name ?? ''} ${m.email ?? ''} ${m.user_group_name ?? ''}`),
        ...(row.sincron_mappings ?? []).map(m => `${m.nume ?? ''} ${m.prenume ?? ''} ${m.company_name ?? ''}`),
      ]
        .join(' ')
        .toLowerCase()
      return haystack.includes(term)
    })
  }, [data, statusFilter, search])

  const stats = data?.stats
  const orphanSincron = data?.orphan_sincron ?? []
  const orphanBiostar = data?.orphan_biostar ?? []

  const openMapSincronDialog = (orphan: IdentityOrphanSincron) => {
    setDialogSelection('')
    setDialog({ mode: 'mapSincron', orphan })
  }

  const openMapBiostarDialog = (orphan: IdentityOrphanBiostar) => {
    setDialogSelection('')
    setDialog({ mode: 'mapBiostar', orphan })
  }

  const confirmDialogMapping = () => {
    if (!dialogSelection) return
    const userId = Number(dialogSelection)
    if (!Number.isFinite(userId)) return
    if (dialog.mode === 'mapSincron') {
      setMappingMut.mutate({
        userId,
        source: 'sincron',
        external_id: dialog.orphan.sincron_employee_id,
        company_name: dialog.orphan.company_name,
      })
    } else if (dialog.mode === 'mapBiostar') {
      setMappingMut.mutate({
        userId,
        source: 'biostar',
        external_id: dialog.orphan.biostar_user_id,
      })
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold flex items-center gap-2">
            <Users className="h-4 w-4" />
            Employee Mapping (Unified)
          </h3>
          <p className="text-xs text-muted-foreground">
            Map each JARVIS user to their Sincron HR and BioStar/Pontaje records from one place.
          </p>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => autoMapMut.mutate()}
          disabled={autoMapMut.isPending}
        >
          {autoMapMut.isPending ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          )}
          Auto-map all
        </Button>
      </div>

      {stats && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          <StatCard label="Users" value={stats.total_users} />
          <StatCard label="Fully mapped" value={stats.fully_mapped} tone="green" />
          <StatCard label="Sincron only" value={stats.sincron_only} tone="amber" />
          <StatCard label="BioStar only" value={stats.biostar_only} tone="amber" />
          <StatCard label="Unmapped" value={stats.unmapped_users} tone="red" />
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="h-8 pl-7 text-xs"
            placeholder="Search by name / email / CNP / company"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as StatusFilter)}>
          <SelectTrigger className="h-8 w-40 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="fully_mapped">Fully mapped</SelectItem>
            <SelectItem value="sincron_only">Sincron only</SelectItem>
            <SelectItem value="biostar_only">BioStar only</SelectItem>
            <SelectItem value="unmapped">Unmapped</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[220px]">User</TableHead>
              <TableHead className="w-[160px]">Company / Dept</TableHead>
              <TableHead>Sincron</TableHead>
              <TableHead>BioStar</TableHead>
              <TableHead className="w-[120px]">Status</TableHead>
              <TableHead className="w-[100px] text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-sm text-muted-foreground py-6">
                  <Loader2 className="mx-auto h-4 w-4 animate-spin" />
                </TableCell>
              </TableRow>
            ) : isError ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-sm text-red-600 py-6">
                  Failed to load unified view.
                </TableCell>
              </TableRow>
            ) : filtered.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-sm text-muted-foreground py-6">
                  No users match the current filters.
                </TableCell>
              </TableRow>
            ) : (
              filtered.map((row) => {
                const status = computeStatus(row)
                return (
                  <TableRow key={row.user_id}>
                    <TableCell>
                      <div className="text-sm font-medium">{row.name}</div>
                      <div className="text-xs text-muted-foreground">{row.email ?? '—'}</div>
                      {row.cnp && (
                        <div className="text-[10px] text-muted-foreground font-mono">CNP {row.cnp}</div>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="text-xs">{row.company ?? '—'}</div>
                      <div className="text-[11px] text-muted-foreground">{row.department ?? ''}</div>
                    </TableCell>
                    <TableCell>
                      {row.sincron_mappings && row.sincron_mappings.length > 0 ? (
                        <div className="space-y-1">
                          {row.sincron_mappings.map(m => (
                            <div
                              key={`${m.sincron_employee_id}-${m.company_name}`}
                              className="flex items-center gap-1.5 text-xs"
                            >
                              <MethodBadge method={m.mapping_method} confidence={m.mapping_confidence} />
                              <span>{m.company_name}</span>
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-6 w-6 p-0"
                                onClick={() =>
                                  removeMappingMut.mutate({
                                    userId: row.user_id,
                                    source: 'sincron',
                                    external_id: m.sincron_employee_id,
                                    company_name: m.company_name,
                                  })
                                }
                                title="Remove Sincron mapping"
                              >
                                <Unlink className="h-3 w-3" />
                              </Button>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground">Not mapped</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {row.biostar_mappings && row.biostar_mappings.length > 0 ? (
                        <div className="space-y-1">
                          {row.biostar_mappings.map((b) => (
                            <div
                              key={b.biostar_user_id}
                              className="flex items-center gap-1.5 text-xs"
                            >
                              <MethodBadge
                                method={b.mapping_method}
                                confidence={b.mapping_confidence}
                              />
                              <span className="truncate max-w-[160px]">
                                {b.user_group_name || b.name || b.email || b.biostar_user_id}
                              </span>
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-6 w-6 p-0"
                                onClick={() =>
                                  removeMappingMut.mutate({
                                    userId: row.user_id,
                                    source: 'biostar',
                                    external_id: b.biostar_user_id,
                                  })
                                }
                                title="Remove BioStar mapping"
                              >
                                <Unlink className="h-3 w-3" />
                              </Button>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground">Not mapped</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <StatusPill status={status} />
                    </TableCell>
                    <TableCell className="text-right">
                      {/* Inline edit is done via orphan rows below; per-user quick-map is not shown here
                          since manual remapping for already-mapped users is best done from the
                          existing Sincron/BioStar sections that expose their own pickers. */}
                      <span className="text-xs text-muted-foreground">—</span>
                    </TableCell>
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>
      </div>

      {(orphanSincron.length > 0 || orphanBiostar.length > 0) && (
        <div className="space-y-3 rounded-md border p-3">
          <h4 className="text-sm font-semibold flex items-center gap-2">
            <LinkIcon className="h-3.5 w-3.5" />
            Unmatched externals
          </h4>
          {orphanSincron.length > 0 && (
            <div>
              <div className="text-xs font-medium mb-1">
                Sincron ({orphanSincron.length})
              </div>
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead>Company</TableHead>
                      <TableHead>CNP</TableHead>
                      <TableHead className="text-right w-24">Action</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {orphanSincron.map((emp) => (
                      <TableRow key={`${emp.sincron_employee_id}-${emp.company_name}`}>
                        <TableCell className="text-xs">
                          {emp.nume} {emp.prenume}
                        </TableCell>
                        <TableCell className="text-xs">{emp.company_name}</TableCell>
                        <TableCell className="text-[11px] font-mono">{emp.cnp ?? '—'}</TableCell>
                        <TableCell className="text-right">
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-6 px-2 text-xs"
                            onClick={() => openMapSincronDialog(emp)}
                          >
                            Map
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
          )}
          {orphanBiostar.length > 0 && (
            <div>
              <div className="text-xs font-medium mb-1">
                BioStar ({orphanBiostar.length})
              </div>
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead>Email</TableHead>
                      <TableHead>Group</TableHead>
                      <TableHead className="text-right w-24">Action</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {orphanBiostar.map((emp) => (
                      <TableRow key={emp.biostar_user_id}>
                        <TableCell className="text-xs">{emp.name ?? '—'}</TableCell>
                        <TableCell className="text-xs">{emp.email ?? '—'}</TableCell>
                        <TableCell className="text-xs">{emp.user_group_name ?? '—'}</TableCell>
                        <TableCell className="text-right">
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-6 px-2 text-xs"
                            onClick={() => openMapBiostarDialog(emp)}
                          >
                            Map
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
          )}
        </div>
      )}

      <Dialog
        open={dialog.mode !== 'closed'}
        onOpenChange={(open) => {
          if (!open) {
            setDialog({ mode: 'closed' })
            setDialogSelection('')
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {dialog.mode === 'mapSincron'
                ? 'Map Sincron employee'
                : dialog.mode === 'mapBiostar'
                  ? 'Map BioStar employee'
                  : ''}
            </DialogTitle>
            <DialogDescription>
              {dialog.mode === 'mapSincron' && (
                <>
                  {dialog.orphan.nume} {dialog.orphan.prenume} · {dialog.orphan.company_name}
                </>
              )}
              {dialog.mode === 'mapBiostar' && (
                <>
                  {dialog.orphan.name ?? dialog.orphan.biostar_user_id}
                  {dialog.orphan.email ? ` · ${dialog.orphan.email}` : ''}
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <div className="py-2">
            <Select value={dialogSelection} onValueChange={setDialogSelection}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select JARVIS user..." />
              </SelectTrigger>
              <SelectContent className="max-h-72">
                {jarvisUsers.map((u) => (
                  <SelectItem key={u.id} value={String(u.id)}>
                    {u.name} {u.email ? `(${u.email})` : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button
              variant="ghost"
              onClick={() => {
                setDialog({ mode: 'closed' })
                setDialogSelection('')
              }}
            >
              Cancel
            </Button>
            <Button
              onClick={confirmDialogMapping}
              disabled={!dialogSelection || setMappingMut.isPending}
            >
              {setMappingMut.isPending && (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              )}
              Save mapping
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function StatCard({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone?: 'green' | 'amber' | 'red'
}) {
  const toneClass =
    tone === 'green'
      ? 'text-green-600'
      : tone === 'amber'
        ? 'text-amber-600'
        : tone === 'red'
          ? 'text-red-600'
          : ''
  return (
    <div className="rounded border p-2">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={`text-lg font-semibold ${toneClass}`}>{value}</div>
    </div>
  )
}
