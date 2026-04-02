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
  Database,
  Key,
  Globe,
  Eye,
  EyeOff,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { DateField } from '@/components/ui/date-field'
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
import { sincronApi } from '@/api/sincron'
import type { SincronSyncRun, SincronEmployee } from '@/api/sincron'
import type { BioStarSyncRun } from '@/types/biostar'
import type { CompanyConnection } from '@/types/efactura'
import { FetchMessagesDialog } from './FetchMessagesDialog'
import { api } from '@/api/client'
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

  // Default: last 24h (today and yesterday)
  const today = new Date().toISOString().split('T')[0]
  const yesterday = new Date(Date.now() - 86400000).toISOString().split('T')[0]
  const [syncDateRange, setSyncDateRange] = useState({ start: yesterday, end: today })

  const syncEventsMut = useMutation({
    mutationFn: (params?: { start_date?: string; end_date?: string }) => biostarApi.syncEvents(params),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['biostar'] })
      if (res.success) toast.success(res.data ? `Events synced — ${res.data.fetched} fetched, ${res.data.inserted} new` : 'Event sync started')
      else toast.error(res.error || 'Sync failed')
    },
    onError: (err: unknown) => {
      const msg = (err as { data?: { error?: string } })?.data?.error || 'Event sync failed'
      toast.error(msg)
    },
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
                  {status.last_sync_users ? `Last: ${new Date(status.last_sync_users + 'Z').toLocaleString('ro-RO', { timeZone: 'Europe/Bucharest' })}` : 'Never'}
                </p>
              </div>
              <Button size="sm" variant="outline" onClick={() => syncUsersMut.mutate()} disabled={syncUsersMut.isPending}>
                {syncUsersMut.isPending ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="mr-1 h-3.5 w-3.5" />}
                Sync
              </Button>
            </div>
            <div className="rounded border p-3 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-1.5 text-sm font-medium"><Clock className="h-3.5 w-3.5" /> Events</div>
                  <p className="text-xs text-muted-foreground">
                    {status.last_sync_events ? `Last: ${new Date(status.last_sync_events + 'Z').toLocaleString('ro-RO', { timeZone: 'Europe/Bucharest' })}` : 'Never'}
                  </p>
                </div>
                <Button size="sm" variant="outline" onClick={() => syncEventsMut.mutate(undefined)} disabled={syncEventsMut.isPending}>
                  {syncEventsMut.isPending ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="mr-1 h-3.5 w-3.5" />}
                  Incremental
                </Button>
              </div>
              <div className="flex items-center gap-2">
                <DateField value={syncDateRange.start} onChange={(v) => setSyncDateRange({ ...syncDateRange, start: v })} className="h-8" />
                <span className="text-xs text-muted-foreground">to</span>
                <DateField value={syncDateRange.end} onChange={(v) => setSyncDateRange({ ...syncDateRange, end: v })} className="h-8" />
                <Button size="sm" variant="outline" onClick={() => {
                  const params: { start_date: string; end_date?: string } = {
                    start_date: syncDateRange.start + 'T00:00:00.00Z',
                  }
                  if (syncDateRange.end) params.end_date = syncDateRange.end + 'T23:59:59.00Z'
                  syncEventsMut.mutate(params)
                }} disabled={syncEventsMut.isPending || !syncDateRange.start}>
                  {syncEventsMut.isPending ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="mr-1 h-3.5 w-3.5" />}
                  Sync Period
                </Button>
              </div>
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
    refetchInterval: (query): number => {
      const data = query.state.data as BioStarSyncRun[] | undefined
      return data?.some((r: BioStarSyncRun) => !r.finished_at) ? 3_000 : 30_000
    },
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
                <TableCell className="text-sm">{new Date(run.started_at + 'Z').toLocaleString('ro-RO', { timeZone: 'Europe/Bucharest' })}</TableCell>
                <TableCell>
                  {!run.finished_at ? (
                    <span className="flex items-center gap-1 text-sm text-yellow-600"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Running</span>
                  ) : run.success ? (
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
                    {new Date(job.last_run + 'Z').toLocaleString('ro-RO', { timeZone: 'Europe/Bucharest' })} — {job.last_message}
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
// Push Notifications (Firebase) Section
// ════════════════════════════════════════════════

const pushApi = {
  getConfig: () => fetch('/push/api/config', { credentials: 'include' }).then(r => r.json()),
  saveConfig: (data: { service_account_json: string }) =>
    fetch('/push/api/config', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }).then(r => r.json()),
  testPush: () =>
    fetch('/push/api/test', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' } }).then(r => r.json()),
  getDevices: () =>
    fetch('/push/api/devices', { credentials: 'include' }).then(r => r.json()),
  deleteDevice: (id: number) =>
    fetch(`/push/api/devices/${id}`, { method: 'DELETE', credentials: 'include' }).then(r => r.json()),
}

function PushNotificationSection() {
  const qc = useQueryClient()
  const [saJson, setSaJson] = useState('')
  const [showUpload, setShowUpload] = useState(false)

  const { data: configData } = useQuery({
    queryKey: ['push-config'],
    queryFn: pushApi.getConfig,
  })
  const config = configData?.data

  const { data: devicesData } = useQuery({
    queryKey: ['push-devices'],
    queryFn: pushApi.getDevices,
  })
  const devices = devicesData?.data ?? []

  const saveConfig = useMutation({
    mutationFn: pushApi.saveConfig,
    onSuccess: (res) => {
      if (res.success) {
        toast.success('Firebase config saved')
        setSaJson('')
        setShowUpload(false)
        qc.invalidateQueries({ queryKey: ['push-config'] })
      } else {
        toast.error(res.error || 'Failed to save config')
      }
    },
  })

  const testPush = useMutation({
    mutationFn: pushApi.testPush,
    onSuccess: (res) => {
      if (res.success) toast.success(res.message)
      else toast.error(res.error || 'Test failed')
    },
  })

  const deleteDevice = useMutation({
    mutationFn: pushApi.deleteDevice,
    onSuccess: () => {
      toast.success('Device removed')
      qc.invalidateQueries({ queryKey: ['push-devices'] })
    },
  })

  const isConnected = config?.status === 'connected'

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            {isConnected ? <PlugZap className="h-5 w-5 text-green-500" /> : <Plug className="h-5 w-5 text-muted-foreground" />}
            Push Notifications (Firebase)
          </h2>
          <p className="text-sm text-muted-foreground">Send push notifications to mobile devices via Firebase Cloud Messaging</p>
        </div>
        <StatusBadge status={config?.status || 'disconnected'} />
      </div>

      {/* Connection info */}
      {isConnected && config?.project_id && (
        <div className="rounded-lg border p-4 space-y-2">
          <div className="flex items-center gap-2">
            <CheckCircle className="h-4 w-4 text-green-500" />
            <span className="text-sm font-medium">Connected</span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div>
              <span className="text-muted-foreground">Project ID:</span>{' '}
              <span className="font-mono">{config.project_id}</span>
            </div>
            {config.config?.client_email && (
              <div>
                <span className="text-muted-foreground">Service Account:</span>{' '}
                <span className="font-mono text-xs">{config.config.client_email}</span>
              </div>
            )}
          </div>
          <div className="flex gap-2 pt-2">
            <Button size="sm" variant="outline" onClick={() => setShowUpload(true)}>
              <RefreshCw className="h-3.5 w-3.5 mr-1" /> Update Credentials
            </Button>
            <Button size="sm" variant="outline" onClick={() => testPush.mutate()} disabled={testPush.isPending}>
              {testPush.isPending ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <PlugZap className="h-3.5 w-3.5 mr-1" />}
              Send Test Push
            </Button>
          </div>
        </div>
      )}

      {/* Setup / Upload form */}
      {(!isConnected || showUpload) && (
        <div className="rounded-lg border p-4 space-y-3">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-yellow-500" />
            <span className="text-sm font-medium">
              {isConnected ? 'Update Service Account' : 'Setup Required'}
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            Paste your Firebase service account JSON below. Get it from{' '}
            <a href="https://console.firebase.google.com" target="_blank" rel="noreferrer"
               className="text-primary underline">Firebase Console</a>
            {' → Project Settings → Service Accounts → Generate New Private Key.'}
          </p>
          <textarea
            value={saJson}
            onChange={(e) => setSaJson(e.target.value)}
            placeholder='{"type": "service_account", "project_id": "...", ...}'
            rows={6}
            className="w-full rounded-lg border bg-muted px-3 py-2 text-xs font-mono outline-none resize-y"
          />
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={() => saveConfig.mutate({ service_account_json: saJson })}
              disabled={!saJson.trim() || saveConfig.isPending}
            >
              {saveConfig.isPending ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Save className="h-3.5 w-3.5 mr-1" />}
              Save Configuration
            </Button>
            {showUpload && (
              <Button size="sm" variant="ghost" onClick={() => { setShowUpload(false); setSaJson('') }}>
                Cancel
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Error display */}
      {config?.last_error && (
        <div className="rounded-lg border border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950 p-3 flex items-start gap-2">
          <XCircle className="h-4 w-4 text-red-500 mt-0.5 shrink-0" />
          <p className="text-sm text-red-700 dark:text-red-300">{config.last_error}</p>
        </div>
      )}

      {/* Registered Devices */}
      {devices.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold flex items-center gap-1.5">
            <Users className="h-4 w-4" /> Registered Devices ({devices.length})
          </h3>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>User</TableHead>
                <TableHead>Platform</TableHead>
                <TableHead>Token</TableHead>
                <TableHead>Last Updated</TableHead>
                <TableHead className="w-10"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {devices.map((d: any) => (
                <TableRow key={d.id}>
                  <TableCell className="font-medium">{d.user_name}</TableCell>
                  <TableCell className="capitalize">{d.platform}</TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">{d.token_preview}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {d.updated_at ? new Date(d.updated_at).toLocaleString() : '—'}
                  </TableCell>
                  <TableCell>
                    <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => deleteDevice.mutate(d.id)}>
                      <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

// ════════════════════════════════════════════════
// Business Data APIs Section
// ════════════════════════════════════════════════

interface BusinessConnector {
  id: number
  connector_type: string
  name: string
  status: string
  config: Record<string, unknown>
  credential_fields: Record<string, string>
  last_sync?: string
  last_error?: string
}

const CONNECTOR_META: Record<string, { icon: string; color: string; url: string }> = {
  anaf: { icon: '🏛️', color: 'text-blue-600', url: 'https://www.anaf.ro' },
  termene: { icon: '⚖️', color: 'text-purple-600', url: 'https://termene.ro' },
  risco: { icon: '📊', color: 'text-orange-600', url: 'https://risco.ro' },
  listafirme: { icon: '📋', color: 'text-green-600', url: 'https://listafirme.eu' },
  openapi_ro: { icon: '🔌', color: 'text-cyan-600', url: 'https://openapi.ro' },
  firmeapi: { icon: '⚡', color: 'text-yellow-600', url: 'https://firmeapi.ro' },
}

function BusinessConnectorCard({ connector, onSaved }: { connector: BusinessConnector; onSaved: () => void }) {
  const [editing, setEditing] = useState(false)
  const [creds, setCreds] = useState<Record<string, string>>({})
  const [showValues, setShowValues] = useState(false)

  const meta = CONNECTOR_META[connector.connector_type] || { icon: '🔗', color: 'text-gray-600', url: '#' }
  const description = (connector.config as Record<string, string>)?.description || ''
  const endpoint = (connector.config as Record<string, string>)?.api_endpoint || ''

  const saveMut = useMutation({
    mutationFn: () =>
      api.put<{ success: boolean; connector: BusinessConnector }>(`/api/connectors/${connector.id}`, {
        credentials: creds,
        status: Object.values(creds).some(v => v.trim()) ? 'connected' : connector.status,
      }),
    onSuccess: (res) => {
      if (res.success) {
        toast.success(`${connector.name} updated`)
        setEditing(false)
        setCreds({})
        onSaved()
      }
    },
    onError: () => toast.error('Failed to save'),
  })

  const hasCredentials = Object.values(connector.credential_fields).some(v => v === '••••••')
  const needsCredentials = Object.keys(connector.credential_fields).length > 0 && !hasCredentials

  return (
    <div className="rounded-lg border p-4 space-y-3">
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          <span className="text-2xl">{meta.icon}</span>
          <div>
            <h4 className="font-semibold">{connector.name}</h4>
            {endpoint && (
              <p className="text-xs text-muted-foreground font-mono truncate max-w-[300px]">{endpoint}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={connector.status === 'connected' ? 'active' : connector.status === 'error' ? 'error' : 'inactive'} />
          <a href={meta.url} target="_blank" rel="noreferrer">
            <Globe className="h-4 w-4 text-muted-foreground hover:text-foreground" />
          </a>
        </div>
      </div>

      {description && (
        <p className="text-xs text-muted-foreground leading-relaxed">{description}</p>
      )}

      {/* Credential fields display */}
      {Object.keys(connector.credential_fields).length > 0 && !editing && (
        <div className="flex items-center gap-2 text-sm">
          <Key className="h-3.5 w-3.5 text-muted-foreground" />
          {Object.entries(connector.credential_fields).map(([key, val]) => (
            <span key={key} className="flex items-center gap-1">
              <span className="text-muted-foreground">{key}:</span>
              <span className={val ? 'text-green-600' : 'text-red-500'}>{val || 'not set'}</span>
            </span>
          ))}
        </div>
      )}

      {/* Edit credentials form */}
      {editing && (
        <div className="rounded border p-3 space-y-3 bg-muted/30">
          {Object.keys(connector.credential_fields).map((key) => (
            <div key={key} className="space-y-1">
              <Label className="text-xs">{key}</Label>
              <div className="flex items-center gap-2">
                <Input
                  type={showValues ? 'text' : 'password'}
                  placeholder={connector.credential_fields[key] ? '••••••  (leave blank to keep)' : `Enter ${key}`}
                  value={creds[key] || ''}
                  onChange={(e) => setCreds({ ...creds, [key]: e.target.value })}
                  className="h-8 text-sm"
                />
              </div>
            </div>
          ))}
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setShowValues(!showValues)}
              className="text-xs"
            >
              {showValues ? <EyeOff className="h-3.5 w-3.5 mr-1" /> : <Eye className="h-3.5 w-3.5 mr-1" />}
              {showValues ? 'Hide' : 'Show'}
            </Button>
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={() => saveMut.mutate()} disabled={saveMut.isPending}>
              {saveMut.isPending ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Save className="h-3.5 w-3.5 mr-1" />}
              Save
            </Button>
            <Button size="sm" variant="ghost" onClick={() => { setEditing(false); setCreds({}) }}>Cancel</Button>
          </div>
        </div>
      )}

      {/* Actions */}
      {!editing && Object.keys(connector.credential_fields).length > 0 && (
        <Button size="sm" variant={needsCredentials ? 'default' : 'outline'} onClick={() => setEditing(true)}>
          <Key className="h-3.5 w-3.5 mr-1" />
          {needsCredentials ? 'Configure API Key' : 'Edit Credentials'}
        </Button>
      )}

      {connector.status === 'connected' && !Object.keys(connector.credential_fields).length && (
        <div className="flex items-center gap-1.5 text-xs text-green-600">
          <CheckCircle className="h-3.5 w-3.5" />
          No authentication required — free public API
        </div>
      )}
    </div>
  )
}

function BusinessDataSection() {
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['connectors', 'business'],
    queryFn: () => api.get<{ connectors: BusinessConnector[] }>('/api/connectors', { category: 'business' }),
  })

  const connectors = data?.connectors ?? []

  if (isLoading) {
    return <div className="h-48 animate-pulse rounded-lg border bg-muted/50" />
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold flex items-center gap-2">
          <Database className="h-5 w-5" />
          Business Data APIs
        </h3>
        <p className="text-sm text-muted-foreground mt-0.5">
          Romanian business data providers for client enrichment (fiscal data, risk scores, court cases, shareholders)
        </p>
      </div>

      {connectors.length === 0 ? (
        <EmptyState
          icon={<Database className="h-10 w-10" />}
          title="No business data connectors"
          description="Run database migration to seed business data connectors"
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {connectors.map((c) => (
            <BusinessConnectorCard
              key={c.id}
              connector={c}
              onSaved={() => qc.invalidateQueries({ queryKey: ['connectors', 'business'] })}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ════════════════════════════════════════════════
// Sincron HR Section
// ════════════════════════════════════════════════

const SINCRON_COMPANIES = [
  'AUTOWORLD S.R.L.',
  'AUTOWORLD INSURANCE S.R.L.',
  'AUTOWORLD INTERNATIONAL S.R.L.',
  'AUTOWORLD NEXT S.R.L.',
  'AUTOWORLD ONE S.R.L.',
  'AUTOWORLD PLUS S.R.L.',
  'AUTOWORLD PREMIUM S.R.L.',
  'AUTOWORLD PRESTIGE S.R.L.',
]

function SincronSection() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [tokens, setTokens] = useState<Record<string, string>>({})
  const [showTokens, setShowTokens] = useState<Record<string, boolean>>({})
  const [syncYear, setSyncYear] = useState(new Date().getFullYear())
  const [syncMonth, setSyncMonth] = useState(new Date().getMonth() + 1)

  const { data: status } = useQuery({
    queryKey: ['sincron', 'status'],
    queryFn: sincronApi.getStatus,
    refetchInterval: 30_000,
  })

  const { data: config } = useQuery({
    queryKey: ['sincron', 'config'],
    queryFn: sincronApi.getConfig,
  })

  const saveMut = useMutation({
    mutationFn: () => {
      const nonEmpty = Object.fromEntries(
        Object.entries(tokens).filter(([, v]) => v.trim()),
      )
      return sincronApi.saveConfig(nonEmpty)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sincron'] })
      setShowForm(false)
      toast.success('Sincron configuration saved')
    },
    onError: () => toast.error('Failed to save configuration'),
  })

  const testMut = useMutation({
    mutationFn: () => sincronApi.testConnection(),
    onSuccess: (res) => {
      const total = Object.keys(res.companies || {}).length
      const ok = Object.values(res.companies || {}).filter(c => c.success).length
      if (res.success) toast.success(`All ${total} companies connected`)
      else toast.warning(`${ok}/${total} companies connected`)
    },
    onError: () => toast.error('Connection test failed'),
  })

  const syncMut = useMutation({
    mutationFn: () => sincronApi.syncTimesheetsNow({ year: syncYear, month: syncMonth }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['sincron'] })
      if (res.success) {
        toast.success(`Synced ${res.total_employees} employees, ${res.total_records} records`)
      } else {
        toast.error('Sync had errors')
      }
    },
    onError: () => toast.error('Sync failed'),
  })

  const autoMapMut = useMutation({
    mutationFn: () => sincronApi.autoMap(),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['sincron'] })
      if (res.total_mapped > 0) {
        toast.success(`Mapped ${res.total_mapped} employees (${res.cnp_mapped} by CNP, ${res.name_mapped} by name)`)
      } else {
        toast.info('No new employees to map')
      }
    },
    onError: () => toast.error('Auto-map failed'),
  })

  const handleEditClick = () => {
    // Pre-fill with empty tokens for all companies
    const t: Record<string, string> = {}
    SINCRON_COMPANIES.forEach(c => { t[c] = '' })
    setTokens(t)
    setShowForm(true)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold">Sincron HR (Timesheets)</h3>
        {status && (
          <StatusBadge status={status.connected ? 'active' : 'inactive'} />
        )}
      </div>

      {status?.connected && !showForm ? (
        <div className="rounded-lg border p-4 space-y-4">
          <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
            <div>
              <span className="text-muted-foreground">Companies:</span>
              <p className="font-medium">{status.companies_configured}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Employees:</span>
              <p className="font-medium">{status.employee_count.total} active</p>
            </div>
            <div>
              <span className="text-muted-foreground">Mapped:</span>
              <p className="font-medium">{status.employee_count.mapped} / {status.employee_count.total}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Last Sync:</span>
              <p className="font-medium text-xs">
                {status.last_sync
                  ? new Date(status.last_sync).toLocaleString('ro-RO', { timeZone: 'Europe/Bucharest' })
                  : 'Never'}
              </p>
            </div>
          </div>

          {/* Sync controls */}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex items-center justify-between rounded border p-3">
              <div>
                <div className="flex items-center gap-1.5 text-sm font-medium">
                  <Users className="h-3.5 w-3.5" /> Employee Mapping
                </div>
                <p className="text-xs text-muted-foreground">
                  {status.employee_count.unmapped} unmapped
                </p>
              </div>
              <Button size="sm" variant="outline" onClick={() => autoMapMut.mutate()} disabled={autoMapMut.isPending}>
                {autoMapMut.isPending ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="mr-1 h-3.5 w-3.5" />}
                Auto-Map
              </Button>
            </div>
            <div className="rounded border p-3 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-1.5 text-sm font-medium">
                    <Clock className="h-3.5 w-3.5" /> Timesheet Sync
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Select value={String(syncMonth)} onValueChange={(v) => setSyncMonth(Number(v))}>
                  <SelectTrigger className="h-8 w-24">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Array.from({ length: 12 }, (_, i) => (
                      <SelectItem key={i + 1} value={String(i + 1)}>
                        {new Date(2024, i).toLocaleString('ro-RO', { month: 'short' })}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  type="number"
                  className="h-8 w-20"
                  value={syncYear}
                  onChange={(e) => setSyncYear(Number(e.target.value))}
                  min={2000}
                  max={2100}
                />
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => syncMut.mutate()}
                  disabled={syncMut.isPending}
                >
                  {syncMut.isPending ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="mr-1 h-3.5 w-3.5" />}
                  Sync
                </Button>
              </div>
            </div>
          </div>

          <div className="flex gap-2">
            <Button size="sm" variant="ghost" onClick={handleEditClick}>Edit Tokens</Button>
            <Button size="sm" variant="outline" onClick={() => testMut.mutate()} disabled={testMut.isPending}>
              {testMut.isPending ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Plug className="mr-1.5 h-4 w-4" />}
              Test All
            </Button>
          </div>
        </div>
      ) : (
        <div className="rounded-lg border p-4 space-y-4">
          {!config && !showForm ? (
            <EmptyState
              icon={<PlugZap className="h-10 w-10" />}
              title="Not configured"
              description="Set up Sincron HR API tokens to sync official timesheets."
              action={<Button onClick={handleEditClick}>Configure</Button>}
            />
          ) : (
            <>
              <p className="text-sm text-muted-foreground">
                Enter Bearer tokens for each company. Leave blank to skip a company.
              </p>
              <div className="grid gap-3">
                {SINCRON_COMPANIES.map((company) => (
                  <div key={company} className="grid gap-1">
                    <Label className="text-xs">{company}</Label>
                    <div className="flex gap-2">
                      <Input
                        type={showTokens[company] ? 'text' : 'password'}
                        placeholder={config?.companies_configured?.[company] ? '••••••• (configured)' : 'Bearer token'}
                        value={tokens[company] || ''}
                        onChange={(e) => setTokens({ ...tokens, [company]: e.target.value })}
                        className="h-8 text-xs font-mono"
                      />
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-8 w-8 p-0"
                        onClick={() => setShowTokens({ ...showTokens, [company]: !showTokens[company] })}
                      >
                        {showTokens[company] ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
              <div className="flex gap-2">
                <Button size="sm" onClick={() => saveMut.mutate()} disabled={saveMut.isPending || !Object.values(tokens).some(v => v.trim())}>
                  {saveMut.isPending ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Save className="mr-1.5 h-4 w-4" />}
                  Save
                </Button>
                <Button size="sm" variant="outline" onClick={() => testMut.mutate()} disabled={testMut.isPending}>
                  {testMut.isPending ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Plug className="mr-1.5 h-4 w-4" />}
                  Test
                </Button>
                {showForm && <Button size="sm" variant="ghost" onClick={() => setShowForm(false)}>Cancel</Button>}
              </div>
            </>
          )}
        </div>
      )}

      <SincronSyncHistory />
      <SincronEmployeeMapping />
    </div>
  )
}

function SincronSyncHistory() {
  const { data: status } = useQuery({ queryKey: ['sincron', 'status'], queryFn: sincronApi.getStatus })
  const { data: runs = [] } = useQuery({
    queryKey: ['sincron', 'syncHistory'],
    queryFn: () => sincronApi.getSyncHistory({ limit: 10 }),
    enabled: !!status?.connected,
    refetchInterval: (query): number => {
      const data = query.state.data as SincronSyncRun[] | undefined
      return data?.some((r: SincronSyncRun) => !r.finished_at) ? 3_000 : 30_000
    },
  })

  if (!status?.connected || runs.length === 0) return null

  return (
    <div className="space-y-2">
      <h4 className="text-sm font-medium flex items-center gap-1.5">
        <History className="h-3.5 w-3.5" /> Recent Syncs
      </h4>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-32">Date</TableHead>
            <TableHead>Company</TableHead>
            <TableHead>Period</TableHead>
            <TableHead className="text-right">Employees</TableHead>
            <TableHead className="text-right">Records</TableHead>
            <TableHead>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {runs.map((run: SincronSyncRun) => (
            <TableRow key={run.run_id}>
              <TableCell className="text-xs">
                {new Date(run.started_at).toLocaleString('ro-RO', { timeZone: 'Europe/Bucharest', dateStyle: 'short', timeStyle: 'short' })}
              </TableCell>
              <TableCell className="text-xs">{run.company_name || 'All'}</TableCell>
              <TableCell className="text-xs">{run.month}/{run.year}</TableCell>
              <TableCell className="text-right text-xs">{run.employees_synced}</TableCell>
              <TableCell className="text-right text-xs">{run.records_created}</TableCell>
              <TableCell>
                {run.status === 'completed' ? (
                  <CheckCircle className="h-4 w-4 text-green-500" />
                ) : run.status === 'failed' ? (
                  <XCircle className="h-4 w-4 text-red-500" />
                ) : (
                  <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function SincronEmployeeMapping() {
  const qc = useQueryClient()
  const { data: status } = useQuery({ queryKey: ['sincron', 'status'], queryFn: sincronApi.getStatus })
  const [showMapping, setShowMapping] = useState(false)

  const { data: unmapped = [] } = useQuery({
    queryKey: ['sincron', 'unmapped'],
    queryFn: sincronApi.getUnmapped,
    enabled: !!status?.connected && showMapping,
  })

  const { data: jarvisUsers = [] } = useQuery({
    queryKey: ['sincron', 'jarvisUsers'],
    queryFn: sincronApi.getJarvisUsers,
    enabled: !!status?.connected && showMapping,
  })

  const mapMut = useMutation({
    mutationFn: (params: { sincronId: string; company: string; jarvisId: number }) =>
      sincronApi.updateMapping(params.sincronId, params.company, params.jarvisId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sincron'] })
      toast.success('Employee mapped')
    },
    onError: () => toast.error('Mapping failed'),
  })

  if (!status?.connected || status.employee_count.unmapped === 0) return null

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium flex items-center gap-1.5">
          <AlertTriangle className="h-3.5 w-3.5 text-yellow-500" />
          {status.employee_count.unmapped} Unmapped Employees
        </h4>
        <Button size="sm" variant="ghost" onClick={() => setShowMapping(!showMapping)}>
          {showMapping ? 'Hide' : 'Show'}
        </Button>
      </div>

      {showMapping && unmapped.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Company</TableHead>
              <TableHead>Contract</TableHead>
              <TableHead className="w-48">Map to JARVIS User</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {unmapped.map((emp: SincronEmployee) => (
              <TableRow key={`${emp.sincron_employee_id}-${emp.company_name}`}>
                <TableCell className="text-sm font-medium">{emp.nume} {emp.prenume}</TableCell>
                <TableCell className="text-xs">{emp.company_name}</TableCell>
                <TableCell className="text-xs">{emp.nr_contract}</TableCell>
                <TableCell>
                  <Select
                    onValueChange={(val) => {
                      mapMut.mutate({
                        sincronId: emp.sincron_employee_id,
                        company: emp.company_name,
                        jarvisId: Number(val),
                      })
                    }}
                  >
                    <SelectTrigger className="h-7 text-xs">
                      <SelectValue placeholder="Select user..." />
                    </SelectTrigger>
                    <SelectContent>
                      {jarvisUsers.map((u) => (
                        <SelectItem key={u.id} value={String(u.id)}>
                          {u.name} ({u.email})
                        </SelectItem>
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

// ════════════════════════════════════════════════
// Main Export
// ════════════════════════════════════════════════

export default function ConnectorsTab() {
  return (
    <div className="space-y-8">
      <EFacturaSection />
      <hr className="border-border" />
      <BioStarConnectionSection />
      <hr className="border-border" />
      <SincronSection />
      <hr className="border-border" />
      <PushNotificationSection />
      <hr className="border-border" />
      <BusinessDataSection />
    </div>
  )
}
