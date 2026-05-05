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
  Unlink,
  UserPlus,
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { toast } from 'sonner'
import {
  identityApi,
  type IdentityUnifiedRow,
  type IdentityUnifiedView,
  type IdentityJarvisUser,
  type IdentityOrphanSincron,
  type IdentityOrphanBiostar,
  type IdentityOrphanConnecteam,
  type IdentityMappingSource,
  type IdentitySincronMapping,
} from '@/api/identity'

/** Title-case a company name: "AUTOWORLD INTERNATIONAL S.R.L." → "Autoworld International S.R.L." */
function titleCaseCompany(name: string): string {
  return name.replace(/\S+/g, (w) =>
    /^s\.r\.l\.?$/i.test(w) ? 'S.R.L.' : w.charAt(0).toUpperCase() + w.slice(1).toLowerCase(),
  )
}

type StatusFilter = 'all' | 'fully_mapped' | 'sincron_only' | 'biostar_only' | 'unmapped'
type ConfidenceFilter = 'all' | 'high' | 'medium' | 'low'

function computeStatus(row: IdentityUnifiedRow): Exclude<StatusFilter, 'all'> {
  const hasSincron = (row.sincron_mappings?.length ?? 0) > 0
  const hasBiostar = (row.biostar_mappings?.length ?? 0) > 0
  const hasConnecteam = (row.connecteam_mappings?.length ?? 0) > 0
  if (hasSincron && hasBiostar && hasConnecteam) return 'fully_mapped'
  if (hasSincron && hasBiostar) return 'fully_mapped'
  if (hasSincron) return 'sincron_only'
  if (hasBiostar) return 'biostar_only'
  if (hasConnecteam) return 'biostar_only' // partial — shows as partial mapped
  return 'unmapped'
}

function getMinConfidence(row: IdentityUnifiedRow): number | null {
  const confidences = [
    ...(row.sincron_mappings ?? []).map(m => m.mapping_confidence),
    ...(row.biostar_mappings ?? []).map(m => m.mapping_confidence),
    ...(row.connecteam_mappings ?? []).map(m => m.mapping_confidence),
  ].filter((c): c is number => c != null)
  if (confidences.length === 0) return null
  return Math.min(...confidences)
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
  const tone =
    confidence != null && confidence >= 95
      ? 'border-green-500/60 text-green-700'
      : confidence != null && confidence >= 80
        ? 'border-amber-500/60 text-amber-700'
        : ''
  return (
    <span className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground ${tone}`}>
      {label}
      {confidence != null && (
        <span className="text-[10px] font-medium">{Math.round(confidence)}</span>
      )}
    </span>
  )
}

function SincronScheduleInfo({ m }: { m: IdentitySincronMapping }) {
  const parts: string[] = []
  if (m.norma_lucru != null) parts.push(`${m.norma_lucru}h`)
  if (m.schedule_start && m.schedule_end) parts.push(`${m.schedule_start}-${m.schedule_end}`)
  if (parts.length === 0) return null
  return (
    <span className="text-[10px] text-muted-foreground">
      {parts.join(' / ')}
      {m.nr_contract && <> · #{m.nr_contract}</>}
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
      mode: 'mapConnecteam'
      orphan: IdentityOrphanConnecteam
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
  | {
      mode: 'mapConnecteamForUser'
      userId: number
      userName: string
    }

export function UnifiedEmployeeMappingSection() {
  const qc = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [companyFilter, setCompanyFilter] = useState<string>('all')
  const [confidenceFilter, setConfidenceFilter] = useState<ConfidenceFilter>('all')
  const [search, setSearch] = useState('')
  const [contentTab, setContentTab] = useState<'users' | 'orphans'>('users')
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
      qc.invalidateQueries({ queryKey: ['connecteam'] })
      const total = r?.total_mapped ?? 0
      if (total > 0) {
        toast.success(
          `Mapped ${total} employees — Sincron: ${(r?.sincron_cnp ?? 0) + (r?.sincron_name ?? 0)} · BioStar: ${
            (r?.biostar_cnp ?? 0) + (r?.biostar_email ?? 0) + (r?.biostar_name ?? 0) + (r?.biostar_cross ?? 0)
          } · Connecteam: ${r?.connecteam_name ?? 0}`,
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
      qc.invalidateQueries({ queryKey: ['connecteam'] })
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
      qc.invalidateQueries({ queryKey: ['connecteam'] })
      toast.success('Mapping removed')
    },
    onError: () => toast.error('Failed to remove mapping'),
  })

  const createFromSincronMut = useMutation({
    mutationFn: (vars: { sincron_employee_id: string; company_name: string }) =>
      identityApi.createFromSincron(vars),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['identity'] })
      qc.invalidateQueries({ queryKey: ['sincron'] })
      const msg = (res.data as any)?.message ?? 'User created & mapped'
      toast.success(msg)
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.error ?? 'Failed to create user'
      toast.error(msg)
    },
  })

  // Derive unique companies for the filter dropdown
  const companies = useMemo(() => {
    const rows = data?.users ?? []
    const set = new Set<string>()
    for (const r of rows) {
      if (r.company) set.add(r.company)
    }
    return Array.from(set).sort()
  }, [data])

  const filtered = useMemo(() => {
    const rows = data?.users ?? []
    const term = search.trim().toLowerCase()
    return rows.filter((row) => {
      const status = computeStatus(row)
      if (statusFilter !== 'all' && status !== statusFilter) return false
      if (companyFilter !== 'all' && row.company?.toLowerCase() !== companyFilter.toLowerCase()) return false
      if (confidenceFilter !== 'all') {
        const minConf = getMinConfidence(row)
        if (minConf === null && confidenceFilter !== 'low') return false
        if (minConf !== null) {
          if (confidenceFilter === 'high' && minConf < 95) return false
          if (confidenceFilter === 'medium' && (minConf < 80 || minConf >= 95)) return false
          if (confidenceFilter === 'low' && minConf >= 80) return false
        }
      }
      if (!term) return true
      const haystack = [
        row.name,
        row.email ?? '',
        row.cnp ?? '',
        row.company ?? '',
        row.department ?? '',
        ...(row.biostar_mappings ?? []).map(m => `${m.name ?? ''} ${m.email ?? ''} ${m.user_group_name ?? ''}`),
        ...(row.sincron_mappings ?? []).map(m => `${m.nume ?? ''} ${m.prenume ?? ''} ${m.company_name ?? ''}`),
        ...(row.connecteam_mappings ?? []).map(m => m.connecteam_user_name ?? ''),
      ]
        .join(' ')
        .toLowerCase()
      return haystack.includes(term)
    })
  }, [data, statusFilter, companyFilter, confidenceFilter, search])

  const stats = data?.stats
  const orphanSincron = data?.orphan_sincron ?? []
  const orphanBiostar = data?.orphan_biostar ?? []
  const orphanConnecteam = data?.orphan_connecteam ?? []
  const totalOrphans = orphanSincron.length + orphanBiostar.length + orphanConnecteam.length

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

  const filteredOrphanConnecteamForDialog = useMemo(() => {
    const term = dialogSearch.trim().toLowerCase()
    if (!term) return orphanConnecteam
    return orphanConnecteam.filter(
      (e) =>
        (e.connecteam_user_name ?? '').toLowerCase().includes(term),
    )
  }, [orphanConnecteam, dialogSearch])

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

  const openMapConnecteamDialog = (orphan: IdentityOrphanConnecteam) => {
    setDialogSelection('')
    setDialogSearch('')
    setDialog({ mode: 'mapConnecteam', orphan })
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

  const openMapConnecteamForUser = (userId: number, userName: string) => {
    setDialogSelection('')
    setDialogSearch('')
    setDialog({ mode: 'mapConnecteamForUser', userId, userName })
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
      if (dialogMultiSelection.size === 0) return
      const promises = Array.from(dialogMultiSelection).map((extId) =>
        identityApi.setMapping(dialog.userId, {
          source: 'biostar',
          external_id: extId,
        }),
      )
      try {
        await Promise.all(promises)
        qc.invalidateQueries({ queryKey: ['identity'] })
        qc.invalidateQueries({ queryKey: ['biostar'] })
        toast.success(`Mapped ${dialogMultiSelection.size} BioStar record(s)`)
        setDialog({ mode: 'closed' })
        setDialogSelection('')
        setDialogMultiSelection(new Set())
        setDialogSearch('')
      } catch {
        toast.error('Failed to save some mappings')
      }
    } else if (dialog.mode === 'mapConnecteam') {
      if (!dialogSelection) return
      const userId = Number(dialogSelection)
      if (!Number.isFinite(userId)) return
      setMappingMut.mutate({
        userId,
        source: 'connecteam',
        external_id: String(dialog.orphan.connecteam_user_id),
      })
    } else if (dialog.mode === 'mapConnecteamForUser') {
      if (!dialogSelection) return
      setMappingMut.mutate({
        userId: dialog.userId,
        source: 'connecteam',
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
        <Select value={companyFilter} onValueChange={setCompanyFilter}>
          <SelectTrigger className="h-8 w-44 text-xs">
            <SelectValue placeholder="All companies" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All companies</SelectItem>
            {companies.map(c => (
              <SelectItem key={c} value={c}>{titleCaseCompany(c)}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={confidenceFilter} onValueChange={(v) => setConfidenceFilter(v as ConfidenceFilter)}>
          <SelectTrigger className="h-8 w-36 text-xs">
            <SelectValue placeholder="Confidence" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All confidence</SelectItem>
            <SelectItem value="high">High (95+)</SelectItem>
            <SelectItem value="medium">Medium (80-94)</SelectItem>
            <SelectItem value="low">Low (&lt;80)</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Tabs value={contentTab} onValueChange={(v) => setContentTab(v as 'users' | 'orphans')}>
        <TabsList>
          <TabsTrigger value="users">All Users ({filtered.length})</TabsTrigger>
          <TabsTrigger value="orphans">
            Unmapped Externals{totalOrphans > 0 && ` (${totalOrphans})`}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="users" className="mt-3">
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[220px]">User</TableHead>
                  <TableHead className="w-[160px]">Company / Dept</TableHead>
                  <TableHead>Sincron</TableHead>
                  <TableHead>BioStar</TableHead>
                  <TableHead className="hidden lg:table-cell">Connecteam</TableHead>
                  <TableHead className="w-[120px]">Status</TableHead>
                  <TableHead className="w-[100px] text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoading ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center text-sm text-muted-foreground py-6">
                      <Loader2 className="mx-auto h-4 w-4 animate-spin" />
                    </TableCell>
                  </TableRow>
                ) : isError ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center text-sm text-red-600 py-6">
                      Failed to load unified view.
                    </TableCell>
                  </TableRow>
                ) : filtered.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center text-sm text-muted-foreground py-6">
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
                            <div className="space-y-1.5">
                              {row.sincron_mappings.map(m => (
                                <div
                                  key={`${m.sincron_employee_id}-${m.company_name}`}
                                  className="flex flex-col gap-0.5"
                                >
                                  <div className="flex items-center gap-1.5 text-xs">
                                    <MethodBadge method={m.mapping_method} confidence={m.mapping_confidence} />
                                    <span className="truncate max-w-[140px]">{m.company_name}</span>
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
                                  <SincronScheduleInfo m={m} />
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
                        <TableCell className="hidden lg:table-cell">
                          {row.connecteam_mappings && row.connecteam_mappings.length > 0 ? (
                            <div className="space-y-1">
                              {row.connecteam_mappings.map((c) => (
                                <div
                                  key={c.connecteam_user_id}
                                  className="flex items-center gap-1.5 text-xs"
                                >
                                  <MethodBadge
                                    method={c.mapping_method}
                                    confidence={c.mapping_confidence}
                                  />
                                  <span className="truncate max-w-[160px]">
                                    {c.connecteam_user_name || String(c.connecteam_user_id)}
                                  </span>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    className="h-6 w-6 p-0"
                                    onClick={() =>
                                      removeMappingMut.mutate({
                                        userId: row.user_id,
                                        source: 'connecteam',
                                        external_id: String(c.connecteam_user_id),
                                      })
                                    }
                                    title="Remove Connecteam mapping"
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
                            {!row.sincron_mappings?.length && (
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
                            {!row.biostar_mappings?.length && (
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
                            {!row.connecteam_mappings?.length && (
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-6 px-2 text-xs hidden lg:inline-flex"
                                onClick={() => openMapConnecteamForUser(row.user_id, row.name)}
                                title="Map Connecteam user"
                              >
                                + Connecteam
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
        </TabsContent>

        <TabsContent value="orphans" className="mt-3">
          {totalOrphans === 0 ? (
            <div className="rounded-md border p-8 text-center">
              <CheckCircle2 className="mx-auto h-8 w-8 text-green-500 mb-2" />
              <p className="text-sm font-medium">All external records are mapped</p>
              <p className="text-xs text-muted-foreground mt-1">No orphan Sincron, BioStar, or Connecteam records found.</p>
            </div>
          ) : (
            <div className="space-y-4">
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
                          <TableHead className="text-right w-36">Action</TableHead>
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
                              <div className="flex items-center justify-end gap-1">
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="h-6 px-2 text-xs"
                                  onClick={() => openMapSincronDialog(emp)}
                                >
                                  Map
                                </Button>
                                <Button
                                  size="sm"
                                  className="h-6 px-2 text-xs"
                                  disabled={createFromSincronMut.isPending}
                                  onClick={() =>
                                    createFromSincronMut.mutate({
                                      sincron_employee_id: emp.sincron_employee_id,
                                      company_name: emp.company_name,
                                    })
                                  }
                                >
                                  <UserPlus className="h-3 w-3 mr-1" />
                                  Create
                                </Button>
                              </div>
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
              {orphanConnecteam.length > 0 && (
                <div>
                  <div className="text-xs font-medium mb-1">
                    Connecteam ({orphanConnecteam.length})
                  </div>
                  <div className="rounded-md border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Name</TableHead>
                          <TableHead className="text-right w-24">Action</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {orphanConnecteam.map((emp) => (
                          <TableRow key={emp.connecteam_user_id}>
                            <TableCell className="text-xs">{emp.connecteam_user_name ?? '—'}</TableCell>
                            <TableCell className="text-right">
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-6 px-2 text-xs"
                                onClick={() => openMapConnecteamDialog(emp)}
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
        </TabsContent>
      </Tabs>

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
                  : dialog.mode === 'mapConnecteam'
                    ? 'Map Connecteam user'
                    : dialog.mode === 'mapSincronForUser'
                      ? 'Map Sincron → user'
                      : dialog.mode === 'mapBiostarForUser'
                        ? 'Map BioStar → user'
                        : dialog.mode === 'mapConnecteamForUser'
                          ? 'Map Connecteam → user'
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
              {dialog.mode === 'mapConnecteam' && (
                <>
                  {dialog.orphan.connecteam_user_name ?? String(dialog.orphan.connecteam_user_id)}
                </>
              )}
              {dialog.mode === 'mapSincronForUser' && (
                <>Select one or more Sincron records to link to <strong>{dialog.userName}</strong></>
              )}
              {dialog.mode === 'mapBiostarForUser' && (
                <>Select one or more BioStar records to link to <strong>{dialog.userName}</strong></>
              )}
              {dialog.mode === 'mapConnecteamForUser' && (
                <>Select an unmatched Connecteam user to link to <strong>{dialog.userName}</strong></>
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
                    : dialog.mode === 'mapConnecteamForUser'
                      ? 'Search by name...'
                      : 'Search by name / email...'
              }
              value={dialogSearch}
              onChange={(e) => setDialogSearch(e.target.value)}
              autoFocus
            />
          </div>

          {/* Scrollable list */}
          <div className="max-h-64 overflow-y-auto rounded border">
            {(dialog.mode === 'mapSincron' || dialog.mode === 'mapBiostar' || dialog.mode === 'mapConnecteam') &&
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
              filteredOrphanBiostarForDialog.map((e) => {
                const val = e.biostar_user_id
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
                      {e.name ?? e.biostar_user_id}
                      {e.email && (
                        <span className="ml-1 text-xs text-muted-foreground">({e.email})</span>
                      )}
                      {e.user_group_name && (
                        <span className="ml-1 text-xs text-muted-foreground">
                          · {e.user_group_name}
                        </span>
                      )}
                    </span>
                  </button>
                )
              })}
            {dialog.mode === 'mapConnecteamForUser' &&
              filteredOrphanConnecteamForDialog.map((e) => (
                <button
                  key={e.connecteam_user_id}
                  type="button"
                  className={`w-full text-left px-3 py-2 text-sm hover:bg-accent transition-colors ${
                    dialogSelection === String(e.connecteam_user_id) ? 'bg-accent font-medium' : ''
                  }`}
                  onClick={() => setDialogSelection(String(e.connecteam_user_id))}
                >
                  {e.connecteam_user_name ?? String(e.connecteam_user_id)}
                </button>
              ))}
            {((dialog.mode === 'mapSincron' || dialog.mode === 'mapBiostar' || dialog.mode === 'mapConnecteam') &&
              filteredJarvisUsers.length === 0) ||
            (dialog.mode === 'mapSincronForUser' && filteredOrphanSincronForDialog.length === 0) ||
            (dialog.mode === 'mapBiostarForUser' && filteredOrphanBiostarForDialog.length === 0) ||
            (dialog.mode === 'mapConnecteamForUser' && filteredOrphanConnecteamForDialog.length === 0) ? (
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
                dialog.mode === 'mapSincronForUser' || dialog.mode === 'mapBiostarForUser'
                  ? dialogMultiSelection.size === 0
                  : !dialogSelection || setMappingMut.isPending
              }
            >
              {setMappingMut.isPending && (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              )}
              {(dialog.mode === 'mapSincronForUser' || dialog.mode === 'mapBiostarForUser') && dialogMultiSelection.size > 0
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
