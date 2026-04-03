import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  CheckCircle,
  XCircle,
  Plug,
  Loader2,
  Save,
  Eye,
  EyeOff,
  ExternalLink,
  Car,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  Image as ImageIcon,
  Download,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { autovitApi } from '@/api/autovit'
import type { AutovitAccount, AutovitAdvert } from '@/api/autovit'
import { toast } from 'sonner'

// ── Helpers ──

function StatusBadge({ status }: { status: string }) {
  if (status === 'connected') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-green-50 px-2.5 py-0.5 text-xs font-medium text-green-700 dark:bg-green-950 dark:text-green-400">
        <CheckCircle className="h-3 w-3" /> Connected
      </span>
    )
  }
  if (status === 'error') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2.5 py-0.5 text-xs font-medium text-red-700 dark:bg-red-950 dark:text-red-400">
        <XCircle className="h-3 w-3" /> Error
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-400">
      <Plug className="h-3 w-3" /> Disconnected
    </span>
  )
}

function formatPrice(params: Record<string, unknown>): string {
  const price = params?.price as Record<string, unknown> | undefined
  if (!price) return '—'
  const amount = price['1'] as number | undefined
  const currency = (price.currency as string) || ''
  if (!amount) return '—'
  return `${amount.toLocaleString('ro-RO', { minimumFractionDigits: 0 })} ${currency}`
}

function getParam(params: Record<string, unknown>, key: string): string {
  const val = params?.[key]
  if (val === null || val === undefined) return '—'
  if (typeof val === 'object') {
    const label = (val as Record<string, unknown>).label
    if (label) return String(label)
    const v = (val as Record<string, unknown>).value ?? (val as Record<string, unknown>)['1']
    if (v !== undefined) return String(v)
  }
  return String(val)
}

// ── Connection Settings Section ──

function ConnectionSettings({
  account,
  onSaved,
}: {
  account: AutovitAccount
  onSaved: () => void
}) {
  const [form, setForm] = useState({
    email: account.email,
    client_id: account.client_id,
    client_secret: '',
    password: '',
    environment: account.environment || 'production',
  })
  const [showPassword, setShowPassword] = useState(false)
  const [showSecret, setShowSecret] = useState(false)

  const saveMut = useMutation({
    mutationFn: () =>
      autovitApi.saveAccount({
        id: account.id,
        email: form.email,
        client_id: form.client_id,
        client_secret: form.client_secret || undefined,
        password: form.password || undefined,
        environment: form.environment,
      }),
    onSuccess: () => {
      toast.success('Account updated')
      onSaved()
    },
    onError: (err: unknown) => {
      const msg = (err as { error?: string })?.error || 'Failed to save'
      toast.error(msg)
    },
  })

  const testMut = useMutation({
    mutationFn: () => autovitApi.testConnection(account.id),
    onSuccess: (res) => {
      onSaved()
      if (res.success) toast.success(`Connection OK — ${(res.data as { total_adverts?: number })?.total_adverts ?? 0} adverts`)
      else toast.error(res.error || 'Connection failed')
    },
    onError: () => toast.error('Connection test failed'),
  })

  return (
    <div className="rounded-lg border p-5 space-y-4">
      <h3 className="text-sm font-semibold">Connection Settings</h3>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-1.5">
          <Label className="text-xs">Email (username)</Label>
          <Input
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
        </div>
        <div className="grid gap-1.5">
          <Label className="text-xs">Client ID</Label>
          <Input
            value={form.client_id}
            onChange={(e) => setForm({ ...form, client_id: e.target.value })}
          />
        </div>
        <div className="grid gap-1.5">
          <Label className="text-xs">Client Secret</Label>
          <div className="relative">
            <Input
              type={showSecret ? 'text' : 'password'}
              placeholder="••••••• (leave blank to keep)"
              value={form.client_secret}
              onChange={(e) => setForm({ ...form, client_secret: e.target.value })}
            />
            <button
              type="button"
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              onClick={() => setShowSecret(!showSecret)}
            >
              {showSecret ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>
        <div className="grid gap-1.5">
          <Label className="text-xs">Password</Label>
          <div className="relative">
            <Input
              type={showPassword ? 'text' : 'password'}
              placeholder="••••••• (leave blank to keep)"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
            <button
              type="button"
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              onClick={() => setShowPassword(!showPassword)}
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>
      </div>
      <div className="grid gap-1.5 max-w-xs">
        <Label className="text-xs">Environment</Label>
        <Select value={form.environment} onValueChange={(v) => setForm({ ...form, environment: v })}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="production">Production</SelectItem>
            <SelectItem value="sandbox">Sandbox</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="flex gap-2 pt-1">
        <Button size="sm" onClick={() => saveMut.mutate()} disabled={saveMut.isPending || !form.email || !form.client_id}>
          {saveMut.isPending ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Save className="mr-1.5 h-4 w-4" />}
          Save
        </Button>
        <Button size="sm" variant="outline" onClick={() => testMut.mutate()} disabled={testMut.isPending}>
          {testMut.isPending ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Plug className="mr-1.5 h-4 w-4" />}
          Test Connection
        </Button>
      </div>
    </div>
  )
}

// ── Adverts Table ──

function AdvertsSection({ accountId }: { accountId: number }) {
  const [page, setPage] = useState(1)
  const [importingId, setImportingId] = useState<string | null>(null)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['autovit', 'adverts', accountId, page],
    queryFn: () => autovitApi.getAdverts(accountId, page),
    enabled: !!accountId,
  })

  const importMut = useMutation({
    mutationFn: (advertId: string) => autovitApi.importAdvert(accountId, advertId),
    onSuccess: (res) => {
      if (res.success && res.vehicle) {
        toast.success(`Imported ${res.vehicle.brand} ${res.vehicle.model} (VIN: ${res.vehicle.vin})`)
      } else {
        toast.error(res.error || 'Import failed')
      }
      setImportingId(null)
    },
    onError: (err: unknown) => {
      const apiErr = err as { data?: { error?: string; existing_vehicle_id?: number } }
      toast.error(apiErr?.data?.error || 'Import failed')
      setImportingId(null)
    },
  })

  const adverts = data?.results ?? []
  const totalElements = data?.total_elements ?? 0
  const totalPages = data?.total_pages ?? 1
  const currentPage = data?.current_page ?? page

  return (
    <div className="rounded-lg border p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Adverts</h3>
          <p className="text-xs text-muted-foreground">
            {totalElements} active adverts on Autovit.ro
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={() => refetch()} disabled={isLoading}>
          <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {isLoading && !data ? (
        <div className="space-y-2">
          {[...Array(5)].map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : isError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300">
          Failed to load adverts. Make sure the connection is configured correctly.
        </div>
      ) : adverts.length === 0 ? (
        <div className="text-center py-8 text-sm text-muted-foreground">
          No active adverts found for this account.
        </div>
      ) : (
        <>
          <div className="overflow-x-auto rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[60px]">Photo</TableHead>
                  <TableHead>Title</TableHead>
                  <TableHead>Make / Model</TableHead>
                  <TableHead className="text-right">Price</TableHead>
                  <TableHead>Year</TableHead>
                  <TableHead>Mileage</TableHead>
                  <TableHead>Fuel</TableHead>
                  <TableHead className="w-[80px]">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {adverts.map((ad: AutovitAdvert) => {
                  const params = (ad.params || {}) as Record<string, unknown>
                  const photos = (ad.photos || []) as string[]
                  const thumb = photos[0] || null
                  const isImporting = importingId === ad.id
                  return (
                    <TableRow key={ad.id}>
                      <TableCell>
                        {thumb ? (
                          <img
                            src={thumb}
                            alt=""
                            className="h-10 w-14 rounded object-cover"
                          />
                        ) : (
                          <div className="flex h-10 w-14 items-center justify-center rounded bg-muted">
                            <ImageIcon className="h-4 w-4 text-muted-foreground" />
                          </div>
                        )}
                      </TableCell>
                      <TableCell className="max-w-[200px] truncate text-xs font-medium" title={ad.title}>
                        {ad.title}
                      </TableCell>
                      <TableCell className="text-xs">
                        {getParam(params, 'make')} {getParam(params, 'model')}
                      </TableCell>
                      <TableCell className="text-right text-xs font-medium">
                        {formatPrice(params)}
                      </TableCell>
                      <TableCell className="text-xs">{getParam(params, 'year')}</TableCell>
                      <TableCell className="text-xs">
                        {getParam(params, 'mileage') !== '—' ? `${Number(getParam(params, 'mileage')).toLocaleString()} km` : '—'}
                      </TableCell>
                      <TableCell className="text-xs">{getParam(params, 'fuel_type')}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            title="Import to Vehicle Catalog"
                            className="rounded p-1 text-muted-foreground hover:bg-primary/10 hover:text-primary disabled:opacity-50"
                            disabled={isImporting || importMut.isPending}
                            onClick={() => {
                              setImportingId(ad.id)
                              importMut.mutate(ad.id)
                            }}
                          >
                            {isImporting ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Download className="h-3.5 w-3.5" />
                            )}
                          </button>
                          {ad.url && (
                            <a
                              href={ad.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              title="View on Autovit.ro"
                              className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                            >
                              <ExternalLink className="h-3.5 w-3.5" />
                            </a>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-1">
              <p className="text-xs text-muted-foreground">
                Page {currentPage} of {totalPages} ({totalElements} adverts)
              </p>
              <div className="flex gap-1">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={currentPage <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={currentPage >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ── Ad Description Template Section ──

function DescriptionTemplate() {
  const [template, setTemplate] = useState('')
  const [autoReactivate, setAutoReactivate] = useState(false)

  return (
    <div className="rounded-lg border p-5 space-y-4">
      <h3 className="text-sm font-semibold">Ad Settings</h3>

      <div className="flex items-center justify-between rounded-md border p-3">
        <div>
          <p className="text-sm font-medium">Auto-reactivate ads</p>
          <p className="text-xs text-muted-foreground">
            Automatically reactivate expired adverts on Autovit.ro
          </p>
        </div>
        <Switch checked={autoReactivate} onCheckedChange={setAutoReactivate} />
      </div>

      <div className="grid gap-1.5">
        <Label className="text-xs">Ad Description Template</Label>
        <Textarea
          rows={6}
          placeholder="Enter a default description template for your adverts..."
          value={template}
          onChange={(e) => setTemplate(e.target.value)}
          className="text-sm"
        />
        <p className="text-[11px] text-muted-foreground">
          This template will be used as the default description when publishing new adverts.
        </p>
      </div>

      <Button size="sm" disabled>
        <Save className="mr-1.5 h-4 w-4" /> Save Settings
      </Button>
    </div>
  )
}

// ── Main Page ──

export default function AutovitDetail() {
  const { accountId } = useParams<{ accountId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const id = Number(accountId)

  const { data: account, isLoading } = useQuery({
    queryKey: ['autovit', 'account', id],
    queryFn: () => autovitApi.getAccount(id),
    enabled: !!id,
  })

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  if (!account) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
          <ArrowLeft className="mr-1.5 h-4 w-4" /> Back to Connectors
        </Button>
        <div className="rounded-lg border p-8 text-center text-sm text-muted-foreground">
          Account not found.
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex items-center gap-2">
          <Car className="h-5 w-5" />
          <div>
            <h2 className="text-base font-semibold">{account.email}</h2>
            <p className="text-xs text-muted-foreground">Client ID: {account.client_id}</p>
          </div>
        </div>
        <div className="ml-auto">
          <StatusBadge status={account.status} />
        </div>
      </div>

      {/* Connection Settings */}
      <ConnectionSettings
        account={account}
        onSaved={() => qc.invalidateQueries({ queryKey: ['autovit'] })}
      />

      {/* Ad Settings */}
      <DescriptionTemplate />

      {/* Adverts */}
      <AdvertsSection accountId={id} />
    </div>
  )
}
