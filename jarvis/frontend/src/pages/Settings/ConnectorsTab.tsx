import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plug,
  PlugZap,
  Plus,
  Trash2,
  ExternalLink,
  RefreshCw,
  Shield,
  ShieldOff,
  AlertTriangle,
  Download,
  Eraser,
  CheckCircle,
  XCircle,
  Loader2,
  Users,
  Clock,
  Save,
  History,
  Timer,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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
} from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Switch } from '@/components/ui/switch'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { EmptyState } from '@/components/shared/EmptyState'
import { efacturaApi } from '@/api/efactura'
import { biostarApi } from '@/api/biostar'
import type { CompanyConnection } from '@/types/efactura'
import { FetchMessagesDialog } from './FetchMessagesDialog'
import { toast } from 'sonner'

// ════════════════════════════════════════════════
// e-Factura Section (unchanged)
// ════════════════════════════════════════════════

function ConnectionCard({
  conn,
  onDelete,
  onOAuthConnect,
  onOAuthRevoke,
  onRefreshToken,
  onFetchMessages,
  onCleanup,
}: {
  conn: CompanyConnection
  onDelete: (cif: string) => void
  onOAuthConnect: (cif: string) => void
  onOAuthRevoke: (cif: string) => void
  onRefreshToken: (cif: string) => void
  onFetchMessages: (conn: CompanyConnection) => void
  onCleanup: (conn: CompanyConnection) => void
}) {
  const { data: oauthStatus } = useQuery({
    queryKey: ['efactura-oauth-status', conn.cif],
    queryFn: () => efacturaApi.getOAuthStatus(conn.cif),
    refetchInterval: 60_000,
  })

  const statusColor =
    conn.status === 'active'
      ? 'text-green-600 dark:text-green-400'
      : conn.status === 'error'
        ? 'text-red-600 dark:text-red-400'
        : 'text-yellow-600 dark:text-yellow-400'

  const isAuthenticated = oauthStatus?.authenticated ?? false

  return (
    <div className="rounded-lg border p-4 space-y-3">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="font-semibold text-lg">{conn.display_name}</h3>
          <p className="text-sm text-muted-foreground">CIF: {conn.cif}</p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={conn.status} />
          <span className="text-xs text-muted-foreground capitalize">
            {conn.environment}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-sm">
        <div>
          <span className="text-muted-foreground">Status: </span>
          <span className={statusColor}>{conn.status}</span>
        </div>
        <div>
          <span className="text-muted-foreground">Last sync: </span>
          <span>{conn.last_sync_at ? new Date(conn.last_sync_at).toLocaleString('ro-RO') : 'Never'}</span>
        </div>
        {conn.status_message && (
          <div className="col-span-2">
            <span className="text-muted-foreground">Message: </span>
            <span className="text-yellow-600">{conn.status_message}</span>
          </div>
        )}
      </div>

      {/* OAuth section */}
      <div className="rounded border p-3 space-y-2 bg-muted/30">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {isAuthenticated ? (
              <Shield className="h-4 w-4 text-green-600" />
            ) : (
              <ShieldOff className="h-4 w-4 text-muted-foreground" />
            )}
            <span className="text-sm font-medium">
              ANAF OAuth: {isAuthenticated ? 'Connected' : 'Not connected'}
            </span>
          </div>
          {isAuthenticated && oauthStatus?.expires_at && (
            <span className="text-xs text-muted-foreground">
              Expires: {new Date(oauthStatus.expires_at).toLocaleDateString('ro-RO')}
            </span>
          )}
        </div>

        {isAuthenticated && oauthStatus?.expires_in_seconds != null && oauthStatus.expires_in_seconds < 86400 * 7 && (
          <div className="flex items-center gap-1 text-xs text-yellow-600">
            <AlertTriangle className="h-3 w-3" />
            Token expires soon
          </div>
        )}

        <div className="flex gap-2">
          {isAuthenticated ? (
            <>
              <Button size="sm" variant="outline" onClick={() => onRefreshToken(conn.cif)}>
                <RefreshCw className="mr-1 h-3 w-3" /> Refresh Token
              </Button>
              <Button size="sm" variant="destructive" onClick={() => onOAuthRevoke(conn.cif)}>
                <ShieldOff className="mr-1 h-3 w-3" /> Disconnect
              </Button>
            </>
          ) : (
            <Button size="sm" onClick={() => onOAuthConnect(conn.cif)}>
              <ExternalLink className="mr-1 h-3 w-3" /> Connect to ANAF
            </Button>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          {isAuthenticated && (
            <Button size="sm" variant="outline" onClick={() => onFetchMessages(conn)}>
              <Download className="mr-1 h-3 w-3" /> Fetch Messages
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={() => onCleanup(conn)}>
            <Eraser className="mr-1 h-3 w-3" /> Clean Up
          </Button>
        </div>
        <Button size="sm" variant="ghost" className="text-destructive" onClick={() => onDelete(conn.cif)}>
          <Trash2 className="mr-1 h-3 w-3" /> Remove
        </Button>
      </div>
    </div>
  )
}

function EFacturaSection() {
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const [fetchTarget, setFetchTarget] = useState<CompanyConnection | null>(null)
  const [cleanupTarget, setCleanupTarget] = useState<CompanyConnection | null>(null)
  const [newConn, setNewConn] = useState({ cif: '', display_name: '', environment: 'test' })

  const { data: connections = [], isLoading } = useQuery({
    queryKey: ['efactura-connections'],
    queryFn: () => efacturaApi.getConnections(),
  })

  const createMut = useMutation({
    mutationFn: () => efacturaApi.createConnection(newConn),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['efactura-connections'] })
      setShowAdd(false)
      setNewConn({ cif: '', display_name: '', environment: 'test' })
    },
  })

  const deleteMut = useMutation({
    mutationFn: (cif: string) => efacturaApi.deleteConnection(cif),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['efactura-connections'] })
      setDeleteTarget(null)
    },
  })

  const revokeMut = useMutation({
    mutationFn: (cif: string) => efacturaApi.oauthRevoke(cif),
    onSuccess: (_d, cif) => {
      qc.invalidateQueries({ queryKey: ['efactura-oauth-status', cif] })
    },
  })

  const refreshMut = useMutation({
    mutationFn: (cif: string) => efacturaApi.refreshOAuth(cif),
    onSuccess: (_d, cif) => {
      qc.invalidateQueries({ queryKey: ['efactura-oauth-status', cif] })
    },
  })

  const cleanupMut = useMutation({
    mutationFn: (cif: string) => efacturaApi.cleanupOldUnallocated(cif),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['efactura-unallocated'] })
      qc.invalidateQueries({ queryKey: ['efactura-unallocated-count'] })
    },
  })

  const handleOAuthConnect = (cif: string) => {
    window.open(efacturaApi.oauthAuthorizeUrl(cif), '_blank')
  }

  if (isLoading) {
    return <div className="h-48 animate-pulse rounded-lg border bg-muted/50" />
  }

  return (
    <>
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold">e-Factura</h3>
        <Button size="sm" onClick={() => setShowAdd(true)}>
          <Plus className="mr-1.5 h-4 w-4" /> Add Connection
        </Button>
      </div>

      {connections.length === 0 ? (
        <EmptyState
          icon={<Plug className="h-10 w-10" />}
          title="No connections"
          description="Add a company connection to start using e-Factura"
          action={
            <Button onClick={() => setShowAdd(true)}>
              <PlugZap className="mr-1.5 h-4 w-4" /> Add Connection
            </Button>
          }
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {connections.map((conn) => (
            <ConnectionCard
              key={conn.id}
              conn={conn}
              onDelete={setDeleteTarget}
              onOAuthConnect={handleOAuthConnect}
              onOAuthRevoke={(cif) => revokeMut.mutate(cif)}
              onRefreshToken={(cif) => refreshMut.mutate(cif)}
              onFetchMessages={setFetchTarget}
              onCleanup={setCleanupTarget}
            />
          ))}
        </div>
      )}

      {/* Add Connection Dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Connection</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>CIF (Tax ID)</Label>
              <Input
                placeholder="e.g. 12345678"
                value={newConn.cif}
                onChange={(e) => setNewConn({ ...newConn, cif: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label>Display Name</Label>
              <Input
                placeholder="e.g. AUTOWORLD SRL"
                value={newConn.display_name}
                onChange={(e) => setNewConn({ ...newConn, display_name: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label>Environment</Label>
              <Select value={newConn.environment} onValueChange={(v) => setNewConn({ ...newConn, environment: v })}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="test">Test (Sandbox)</SelectItem>
                  <SelectItem value="production">Production</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAdd(false)}>Cancel</Button>
            <Button
              onClick={() => createMut.mutate()}
              disabled={!newConn.cif || !newConn.display_name || createMut.isPending}
            >
              {createMut.isPending ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={() => setDeleteTarget(null)}
        title="Delete Connection"
        description={`Remove connection for CIF ${deleteTarget}? This will not delete imported invoices.`}
        onConfirm={() => deleteTarget && deleteMut.mutate(deleteTarget)}
        destructive
      />

      <ConfirmDialog
        open={!!cleanupTarget}
        onOpenChange={() => setCleanupTarget(null)}
        title="Clean Up Old Invoices"
        description={`Permanently delete unallocated invoices older than 15 days for ${cleanupTarget?.display_name} (${cleanupTarget?.cif})?`}
        onConfirm={() => {
          if (cleanupTarget) cleanupMut.mutate(cleanupTarget.cif)
          setCleanupTarget(null)
        }}
        destructive
      />

      {cleanupMut.isSuccess && cleanupMut.data && (
        <div className="fixed bottom-4 right-4 z-50 flex items-center gap-2 rounded border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700 shadow-lg dark:border-green-800 dark:bg-green-900/90 dark:text-green-300">
          <CheckCircle className="h-4 w-4" />
          Cleaned up {cleanupMut.data.deleted} old invoice(s)
        </div>
      )}
      {cleanupMut.isPending && (
        <div className="fixed bottom-4 right-4 z-50 flex items-center gap-2 rounded border bg-background px-4 py-3 text-sm shadow-lg">
          <Loader2 className="h-4 w-4 animate-spin" />
          Cleaning up...
        </div>
      )}

      {fetchTarget && (
        <FetchMessagesDialog
          open={!!fetchTarget}
          onOpenChange={(v) => { if (!v) setFetchTarget(null) }}
          cif={fetchTarget.cif}
          displayName={fetchTarget.display_name}
        />
      )}
    </>
  )
}

// ════════════════════════════════════════════════
// BioStar 2 Section
// ════════════════════════════════════════════════

function BioStarConnectionSection() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ host: '', port: '443', login_id: '', password: '', verify_ssl: false })

  const { data: config } = useQuery({
    queryKey: ['biostar', 'config'],
    queryFn: biostarApi.getConfig,
  })

  const { data: status } = useQuery({
    queryKey: ['biostar', 'status'],
    queryFn: biostarApi.getStatus,
    refetchInterval: 30_000,
  })

  const saveMut = useMutation({
    mutationFn: () =>
      biostarApi.saveConfig({
        host: form.host,
        port: Number(form.port),
        login_id: form.login_id,
        password: form.password,
        verify_ssl: form.verify_ssl,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['biostar'] })
      setShowForm(false)
      toast.success('Connection saved')
    },
    onError: () => toast.error('Failed to save connection'),
  })

  const testMut = useMutation({
    mutationFn: () =>
      biostarApi.testConnection({
        host: form.host || config?.host,
        port: Number(form.port) || config?.port,
        login_id: form.login_id || config?.login_id,
        password: form.password || undefined,
      }),
    onSuccess: (res) => {
      if (res.success) {
        qc.invalidateQueries({ queryKey: ['biostar', 'status'] })
        toast.success(`Connected — ${res.data?.total_users} users found`)
      } else {
        toast.error(res.error || 'Connection failed')
      }
    },
    onError: () => toast.error('Connection test failed'),
  })

  const syncUsersMut = useMutation({
    mutationFn: biostarApi.syncUsers,
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['biostar'] })
      if (res.success) toast.success(`Users synced — ${res.data?.fetched} fetched, ${res.data?.mapped} mapped`)
      else toast.error(res.error || 'Sync failed')
    },
    onError: () => toast.error('User sync failed'),
  })

  const syncEventsMut = useMutation({
    mutationFn: () => biostarApi.syncEvents(),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['biostar'] })
      if (res.success) toast.success(`Events synced — ${res.data?.fetched} fetched, ${res.data?.inserted} new`)
      else toast.error(res.error || 'Sync failed')
    },
    onError: () => toast.error('Event sync failed'),
  })

  const handleEditClick = () => {
    setForm({
      host: config?.host || '',
      port: String(config?.port || 443),
      login_id: config?.login_id || '',
      password: '',
      verify_ssl: config?.verify_ssl || false,
    })
    setShowForm(true)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold">BioStar 2 (Pontaje)</h3>
        {status && (
          <StatusBadge status={status.connected ? 'active' : status.status === 'error' ? 'error' : 'inactive'} />
        )}
      </div>

      {status?.connected && !showForm ? (
        <div className="rounded-lg border p-4 space-y-4">
          <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
            <div>
              <span className="text-muted-foreground">Host:</span>
              <p className="font-medium">{status.host}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Employees:</span>
              <p className="font-medium">{status.employee_count.active} active</p>
            </div>
            <div>
              <span className="text-muted-foreground">Mapped:</span>
              <p className="font-medium">{status.employee_count.mapped} / {status.employee_count.active}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Punch Logs:</span>
              <p className="font-medium">{status.event_count.toLocaleString()}</p>
            </div>
          </div>

          {/* Sync controls */}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex items-center justify-between rounded border p-3">
              <div>
                <div className="flex items-center gap-1.5 text-sm font-medium"><Users className="h-3.5 w-3.5" /> Employees</div>
                <p className="text-xs text-muted-foreground">
                  {status.last_sync_users ? `Last: ${new Date(status.last_sync_users).toLocaleString('ro-RO')}` : 'Never'}
                </p>
              </div>
              <Button size="sm" variant="outline" onClick={() => syncUsersMut.mutate()} disabled={syncUsersMut.isPending}>
                {syncUsersMut.isPending ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="mr-1 h-3.5 w-3.5" />}
                Sync
              </Button>
            </div>
            <div className="flex items-center justify-between rounded border p-3">
              <div>
                <div className="flex items-center gap-1.5 text-sm font-medium"><Clock className="h-3.5 w-3.5" /> Events</div>
                <p className="text-xs text-muted-foreground">
                  {status.last_sync_events ? `Last: ${new Date(status.last_sync_events).toLocaleString('ro-RO')}` : 'Never'}
                </p>
              </div>
              <Button size="sm" variant="outline" onClick={() => syncEventsMut.mutate()} disabled={syncEventsMut.isPending}>
                {syncEventsMut.isPending ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="mr-1 h-3.5 w-3.5" />}
                Sync
              </Button>
            </div>
          </div>

          <Button size="sm" variant="ghost" onClick={handleEditClick}>Edit Connection</Button>
        </div>
      ) : (
        <div className="rounded-lg border p-4 space-y-4">
          {!config && !showForm ? (
            <EmptyState
              icon={<PlugZap className="h-10 w-10" />}
              title="Not configured"
              description="Set up your BioStar 2 connection to start syncing."
              action={<Button onClick={() => setShowForm(true)}>Configure</Button>}
            />
          ) : (
            <>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="grid gap-2">
                  <Label>Host / IP</Label>
                  <Input placeholder="e.g. 10.124.133.100" value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} />
                </div>
                <div className="grid gap-2">
                  <Label>Port</Label>
                  <Input type="number" value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} />
                </div>
                <div className="grid gap-2">
                  <Label>Login ID</Label>
                  <Input value={form.login_id} onChange={(e) => setForm({ ...form, login_id: e.target.value })} />
                </div>
                <div className="grid gap-2">
                  <Label>Password</Label>
                  <Input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder={config ? '••••••• (leave blank to keep)' : ''} />
                </div>
              </div>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => testMut.mutate()} disabled={testMut.isPending || (!form.host && !config?.host)}>
                  {testMut.isPending ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Plug className="mr-1.5 h-4 w-4" />}
                  Test
                </Button>
                <Button size="sm" onClick={() => saveMut.mutate()} disabled={saveMut.isPending || !form.host || !form.login_id || !form.password}>
                  {saveMut.isPending ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Save className="mr-1.5 h-4 w-4" />}
                  Save
                </Button>
                {showForm && <Button size="sm" variant="ghost" onClick={() => setShowForm(false)}>Cancel</Button>}
              </div>
            </>
          )}
        </div>
      )}

      <BioStarCronJobs />
      <BioStarSyncHistory />
    </div>
  )
}

function BioStarSyncHistory() {
  const { data: status } = useQuery({ queryKey: ['biostar', 'status'], queryFn: biostarApi.getStatus })
  const { data: runs = [] } = useQuery({
    queryKey: ['biostar', 'syncHistory'],
    queryFn: () => biostarApi.getSyncHistory({ limit: 10 }),
    enabled: !!status?.connected,
    refetchInterval: 30_000,
  })

  if (!status?.connected || runs.length === 0) return null

  return (
    <div className="space-y-2">
      <h4 className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground"><History className="h-3.5 w-3.5" /> Sync History</h4>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Type</TableHead>
              <TableHead>Date</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Fetched</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="hidden sm:table-cell">Errors</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {runs.map((run) => (
              <TableRow key={run.run_id}>
                <TableCell className="capitalize text-sm">{run.sync_type}</TableCell>
                <TableCell className="text-sm">{new Date(run.started_at).toLocaleString('ro-RO')}</TableCell>
                <TableCell>
                  {run.success ? (
                    <span className="flex items-center gap-1 text-sm text-green-600"><CheckCircle className="h-3.5 w-3.5" /> OK</span>
                  ) : (
                    <span className="flex items-center gap-1 text-sm text-red-600"><XCircle className="h-3.5 w-3.5" /> Failed</span>
                  )}
                </TableCell>
                <TableCell className="text-sm">{run.records_fetched}</TableCell>
                <TableCell className="text-sm">{run.records_created}</TableCell>
                <TableCell className="hidden sm:table-cell text-sm">
                  {run.errors_count > 0 ? <span className="text-red-600">{run.errors_count}</span> : '0'}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

// ════════════════════════════════════════════════
// BioStar Cron Jobs
// ════════════════════════════════════════════════

function BioStarCronJobs() {
  const qc = useQueryClient()
  const { data: cronJobs = [] } = useQuery({
    queryKey: ['biostar', 'cronJobs'],
    queryFn: biostarApi.getCronJobs,
  })

  const updateMut = useMutation({
    mutationFn: biostarApi.updateCronJobs,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['biostar', 'cronJobs'] })
      toast.success('Cron jobs updated')
    },
    onError: () => toast.error('Failed to update cron jobs'),
  })

  const toggleJob = (jobId: string, enabled: boolean) => {
    const updated = cronJobs.map((j) =>
      j.id === jobId ? { id: j.id, enabled, hour: j.hour, minute: j.minute } : { id: j.id, enabled: j.enabled, hour: j.hour, minute: j.minute },
    )
    updateMut.mutate(updated)
  }

  const updateSchedule = (jobId: string, hour: number, minute: number) => {
    const updated = cronJobs.map((j) =>
      j.id === jobId ? { id: j.id, enabled: j.enabled, hour, minute } : { id: j.id, enabled: j.enabled, hour: j.hour, minute: j.minute },
    )
    updateMut.mutate(updated)
  }

  if (cronJobs.length === 0) return null

  return (
    <div className="space-y-2">
      <h4 className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground">
        <Timer className="h-3.5 w-3.5" /> Scheduled Jobs
      </h4>
      <div className="space-y-2">
        {cronJobs.map((job) => (
          <div key={job.id} className="flex items-center gap-3 rounded border p-3">
            <Switch
              checked={job.enabled}
              onCheckedChange={(v) => toggleJob(job.id, v)}
              disabled={updateMut.isPending}
            />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{job.label}</span>
                <span className="text-xs text-muted-foreground">{job.description}</span>
              </div>
              {job.last_run && (
                <div className="flex items-center gap-1.5 mt-0.5">
                  {job.last_success ? (
                    <CheckCircle className="h-3 w-3 text-green-600" />
                  ) : (
                    <XCircle className="h-3 w-3 text-red-500" />
                  )}
                  <span className="text-xs text-muted-foreground">
                    {new Date(job.last_run).toLocaleString('ro-RO')} — {job.last_message}
                  </span>
                </div>
              )}
            </div>
            <Select
              value={`${String(job.hour).padStart(2, '0')}:${String(job.minute).padStart(2, '0')}`}
              onValueChange={(v) => {
                const [h, m] = v.split(':').map(Number)
                updateSchedule(job.id, h, m)
              }}
            >
              <SelectTrigger className="w-24 h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Array.from({ length: 24 }, (_, h) => (
                  <SelectItem key={h} value={`${String(h).padStart(2, '0')}:00`}>
                    {String(h).padStart(2, '0')}:00
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ))}
      </div>
    </div>
  )
}

// ════════════════════════════════════════════════
// Main Export
// ════════════════════════════════════════════════

export default function ConnectorsTab() {
  return (
    <div className="space-y-8">
      <EFacturaSection />
      <hr className="border-border" />
      <BioStarConnectionSection />
    </div>
  )
}
