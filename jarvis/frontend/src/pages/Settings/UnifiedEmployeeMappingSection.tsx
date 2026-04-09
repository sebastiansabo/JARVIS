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
  | {
      mode: 'mapSincronForUser'
      userId: number
      userName: string
    }
  | {
      mode: 'mapBiostarForUser'
      userId: number
      userName: string
    }

export function UnifiedEmployeeMappingSection() {
  const qc = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [search, setSearch] = useState('')
  const [dialog, setDialog] = useState<DialogState>({ mode: 'closed' })
  const [dialogSelection, setDialogSelection] = useState<string>('')
  const [dialogMultiSelection, setDialogMultiSelection] = useState<Set<string>>(new Set())
  const [dialogSearch, setDialogSearch] = useState('')

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

  const filteredJarvisUsers = useMemo(() => {
    const term = dialogSearch.trim().toLowerCase()
    if (!term) return jarvisUsers
    return jarvisUsers.filter(
      (u) =>
        (u.name ?? '').toLowerCase().includes(term) ||
        (u.email ?? '').toLowerCase().includes(term),
    )
  }, [jarvisUsers, dialogSearch])

  const filteredOrphanSincronForDialog = useMemo(() => {
    const term = dialogSearch.trim().toLowerCase()
    if (!term) return orphanSincron
    return orphanSincron.filter(
      (e) =>
        `${e.nume ?? ''} ${e.prenume ?? ''} ${e.company_name ?? ''} ${e.cnp ?? ''}`
          .toLowerCase()
          .includes(term),
    )
  }, [orphanSincron, dialogSearch])

  const filteredOrphanBiostarForDialog = useMemo(() => {
    const term = dialogSearch.trim().toLowerCase()
    if (!term) return orphanBiostar
    return orphanBiostar.filter(
      (e) =>
        `${e.name ?? ''} ${e.email ?? ''} ${e.user_group_name ?? ''}`
          .toLowerCase()
          .includes(term),
    )
  }, [orphanBiostar, dialogSearch])

  const openMapSincronDialog = (orphan: IdentityOrphanSincron) => {
    setDialogSelection('')
    setDialogSearch('')
    setDialog({ mode: 'mapSincron', orphan })
  }

  const openMapBiostarDialog = (orphan: IdentityOrphanBiostar) => {
    setDialogSelection('')
    setDialogSearch('')
    setDialog({ mode: 'mapBiostar', orphan })
  }

  const openMapSincronForUser = (userId: number, userName: string) => {
    setDialogSelection('')
    setDialogMultiSelection(new Set())
    setDialogSearch('')
    setDialog({ mode: 'mapSincronForUser', userId, userName })
  }

  const openMapBiostarForUser = (userId: number, userName: string) => {
    setDialogSelection('')
    setDialogMultiSelection(new Set())
    setDialogSearch('')
    setDialog({ mode: 'mapBiostarForUser', userId, userName })
  }

  const toggleMultiSelection = (val: string) => {
    setDialogMultiSelection((prev) => {
      const next = new Set(prev)
      if (next.has(val)) next.delete(val)
      else next.add(val)
      return next
    })
  }

  const confirmDialogMapping = async () => {
    if (dialog.mode === 'mapSincron') {
      if (!dialogSelection) return
      const userId = Number(dialogSelection)
      if (!Number.isFinite(userId)) return
      setMappingMut.mutate({
        userId,
        source: 'sincron',
        external_id: dialog.orphan.sincron_employee_id,
        company_name: dialog.orphan.company_name,
      })
    } else if (dialog.mode === 'mapBiostar') {
      if (!dialogSelection) return
      const userId = Number(dialogSelection)
      if (!Number.isFinite(userId)) return
      setMappingMut.mutate({
        userId,
        source: 'biostar',
        external_id: dialog.orphan.biostar_user_id,
      })
    } else if (dialog.mode === 'mapSincronForUser') {
      // Multi-select: map all checked orphan Sincron records to this user
      if (dialogMultiSelection.size === 0) return
      const promises = Array.from(dialogMultiSelection).map((val) => {
        const [extId, ...rest] = val.split('::')
        const companyName = rest.join('::')
        return identityApi.setMapping(dialog.userId, {
          source: 'sincron',
          external_id: extId,
          company_name: companyName || undefined,
        })
      })
      try {
        await Promise.all(promises)
        qc.invalidateQueries({ queryKey: ['identity'] })
        qc.invalidateQueries({ queryKey: ['sincron'] })
        toast.success(`Mapped ${dialogMultiSelection.size} Sincron record(s)`)
        setDialog({ mode: 'closed' })
        setDialogSelection('')
        setDialogMultiSelection(new Set())
        setDialogSearch('')
      } catch {
        toast.error('Failed to save some mappings')
      }
    } else if (dialog.mode === 'mapBiostarForUser') {
      if (!dialogSelection) return
      setMappingMut.mutate({
        userId: dialog.userId,
        source: 'biostar',
        external_id: dialogSelection,
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
                      <div className="flex items-center justify-end gap-1">
                        {(status === 'biostar_only' || status === 'unmapped') && (
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-6 px-2 text-xs"
                            onClick={() => openMapSincronForUser(row.user_id, row.name)}
                            title="Map Sincron employee"
                          >
                            + Sincron
                          </Button>
                        )}
                        {(status === 'sincron_only' || status === 'unmapped') && (
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-6 px-2 text-xs"
                            onClick={() => openMapBiostarForUser(row.user_id, row.name)}
                            title="Map BioStar employee"
                          >
                            + BioStar
                          </Button>
                        )}
                      </div>
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
            setDialogMultiSelection(new Set())
            setDialogSearch('')
          }
        }}
      >
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {dialog.mode === 'mapSincron'
                ? 'Map Sincron employee'
                : dialog.mode === 'mapBiostar'
                  ? 'Map BioStar employee'
                  : dialog.mode === 'mapSincronForUser'
                    ? 'Map Sincron → user'
                    : dialog.mode === 'mapBiostarForUser'
                      ? 'Map BioStar → user'
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
              {dialog.mode === 'mapSincronForUser' && (
                <>Select one or more Sincron records to link to <strong>{dialog.userName}</strong></>
              )}
              {dialog.mode === 'mapBiostarForUser' && (
                <>Select an unmatched BioStar record to link to <strong>{dialog.userName}</strong></>
              )}
            </DialogDescription>
          </DialogHeader>

          {/* Search input */}
          <div className="relative">
            <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="h-8 pl-7 text-xs"
              placeholder={
                dialog.mode === 'mapSincronForUser'
                  ? 'Search by name / company / CNP...'
                  : dialog.mode === 'mapBiostarForUser'
                    ? 'Search by name / email / group...'
                    : 'Search by name / email...'
              }
              value={dialogSearch}
              onChange={(e) => setDialogSearch(e.target.value)}
              autoFocus
            />
          </div>

          {/* Scrollable list */}
          <div className="max-h-64 overflow-y-auto rounded border">
            {(dialog.mode === 'mapSincron' || dialog.mode === 'mapBiostar') &&
              filteredJarvisUsers.map((u) => (
                <button
                  key={u.id}
                  type="button"
                  className={`w-full text-left px-3 py-2 text-sm hover:bg-accent transition-colors ${
                    dialogSelection === String(u.id) ? 'bg-accent font-medium' : ''
                  }`}
                  onClick={() => setDialogSelection(String(u.id))}
                >
                  {u.name}
                  {u.email && (
                    <span className="ml-1 text-xs text-muted-foreground">({u.email})</span>
                  )}
                </button>
              ))}
            {dialog.mode === 'mapSincronForUser' &&
              filteredOrphanSincronForDialog.map((e) => {
                const val = `${e.sincron_employee_id}::${e.company_name}`
                const checked = dialogMultiSelection.has(val)
                return (
                  <button
                    key={val}
                    type="button"
                    className={`w-full text-left px-3 py-2 text-sm hover:bg-accent transition-colors flex items-center gap-2 ${
                      checked ? 'bg-accent/60' : ''
                    }`}
                    onClick={() => toggleMultiSelection(val)}
                  >
                    <span
                      className={`inline-flex h-4 w-4 shrink-0 items-center justify-center rounded border text-[10px] ${
                        checked
                          ? 'bg-primary border-primary text-primary-foreground'
                          : 'border-muted-foreground/40'
                      }`}
                    >
                      {checked && '✓'}
                    </span>
                    <span>
                      {e.nume} {e.prenume}
                      <span className="ml-1 text-xs text-muted-foreground">
                        · {e.company_name}
                      </span>
                      {e.cnp && (
                        <span className="ml-1 text-[10px] font-mono text-muted-foreground">
                          CNP {e.cnp}
                        </span>
                      )}
                    </span>
                  </button>
                )
              })}
            {dialog.mode === 'mapBiostarForUser' &&
              filteredOrphanBiostarForDialog.map((e) => (
                <button
                  key={e.biostar_user_id}
                  type="button"
                  className={`w-full text-left px-3 py-2 text-sm hover:bg-accent transition-colors ${
                    dialogSelection === e.biostar_user_id ? 'bg-accent font-medium' : ''
                  }`}
                  onClick={() => setDialogSelection(e.biostar_user_id)}
                >
                  {e.name ?? e.biostar_user_id}
                  {e.email && (
                    <span className="ml-1 text-xs text-muted-foreground">({e.email})</span>
                  )}
                  {e.user_group_name && (
                    <span className="ml-1 text-xs text-muted-foreground">
                      · {e.user_group_name}
                    </span>
                  )}
                </button>
              ))}
            {((dialog.mode === 'mapSincron' || dialog.mode === 'mapBiostar') &&
              filteredJarvisUsers.length === 0) ||
            (dialog.mode === 'mapSincronForUser' && filteredOrphanSincronForDialog.length === 0) ||
            (dialog.mode === 'mapBiostarForUser' && filteredOrphanBiostarForDialog.length === 0) ? (
              <div className="px-3 py-4 text-center text-xs text-muted-foreground">
                No results match &ldquo;{dialogSearch}&rdquo;
              </div>
            ) : null}
          </div>

          <DialogFooter>
            <Button
              variant="ghost"
              onClick={() => {
                setDialog({ mode: 'closed' })
                setDialogSelection('')
                setDialogMultiSelection(new Set())
                setDialogSearch('')
              }}
            >
              Cancel
            </Button>
            <Button
              onClick={confirmDialogMapping}
              disabled={
                dialog.mode === 'mapSincronForUser'
                  ? dialogMultiSelection.size === 0
                  : !dialogSelection || setMappingMut.isPending
              }
            >
              {setMappingMut.isPending && (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              )}
              {dialog.mode === 'mapSincronForUser' && dialogMultiSelection.size > 0
                ? `Save ${dialogMultiSelection.size} mapping(s)`
                : 'Save mapping'}
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
