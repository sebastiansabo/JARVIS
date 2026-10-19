import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, RefreshCw, Tags } from 'lucide-react'
import { toast } from 'sonner'
import { PageHeader } from '@/components/shared/PageHeader'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
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
import { autovitApi } from '@/api/autovit'
import type { AutovitTaxonomyCacheRow, AutovitTaxonomySourceRow } from '@/api/autovit'

// Render order for the per-dimension sections — make/model first (they gate
// every publish), then the other REQUIRED dims, then optional equipment.
const DIMENSION_ORDER = [
  'make', 'model', 'fuel_type', 'body_type', 'color', 'gearbox', 'drive',
  'pollution_standard', 'equipment',
] as const

const DIM_LABELS: Record<string, string> = {
  make: 'Marcă',
  model: 'Model',
  fuel_type: 'Combustibil',
  body_type: 'Caroserie',
  color: 'Culoare',
  gearbox: 'Cutie de viteze',
  drive: 'Tracțiune',
  pollution_standard: 'Normă de poluare',
  equipment: 'Dotări',
}

function formatDimLabel(dim: string): string {
  return DIM_LABELS[dim] || dim.replace(/_/g, ' ')
}

function formatOption(code: string, label?: string | null): string {
  return label ? `${label} (${code})` : code
}

/** Suggestions first (already ranked by the backend), then the rest of the
 * synced cache as a fallback — `model` options are scoped to the row's
 * resolved Autovit make code (Task 3's make-scoping rule). */
function useOptions(
  row: AutovitTaxonomySourceRow,
  dimension: string,
  cache: AutovitTaxonomyCacheRow[],
) {
  const makeCode = dimension === 'model' ? row.resolved_make_code : undefined
  return useMemo(() => {
    const seen = new Set<string>()
    const suggested: { code: string; label: string | null }[] = []
    for (const s of row.suggestions) {
      if (seen.has(s.target_code)) continue
      seen.add(s.target_code)
      suggested.push({ code: s.target_code, label: s.target_label })
    }
    const rest: { code: string; label: string | null }[] = []
    for (const c of cache) {
      if (c.dimension !== dimension) continue
      if (dimension === 'model' && c.make !== makeCode) continue
      if (seen.has(c.code)) continue
      seen.add(c.code)
      rest.push({ code: c.code, label: c.ro_label })
    }
    return { suggested, rest }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [row.suggestions, cache, dimension, makeCode])
}

function TaxonomyRow({
  dimension,
  row,
  cache,
  saving,
  onSave,
  onClear,
}: {
  dimension: string
  row: AutovitTaxonomySourceRow
  cache: AutovitTaxonomyCacheRow[]
  saving: boolean
  onSave: (targetCode: string, targetLabel: string | null) => void
  onClear: () => void
}) {
  const mapped = !!row.target_code
  const { suggested, rest } = useOptions(row, dimension, cache)
  const allOptions = [...suggested, ...rest]

  return (
    <TableRow>
      <TableCell className="font-medium">
        <div className="flex items-center gap-2">
          <span className="truncate" title={row.source_value}>{row.source_value}</span>
          {!mapped && <Badge variant="destructive">Nemapat</Badge>}
        </div>
      </TableCell>
      <TableCell className="min-w-[260px]">
        <div className="flex items-center gap-2">
          <Select
            value={row.target_code ?? undefined}
            onValueChange={(v) => {
              const opt = allOptions.find((o) => o.code === v)
              onSave(v, opt?.label ?? null)
            }}
            disabled={saving}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder="Selectează cod Autovit..." />
            </SelectTrigger>
            <SelectContent>
              {suggested.length > 0 && (
                <SelectGroup>
                  <SelectLabel>Sugestii</SelectLabel>
                  {suggested.map((o) => (
                    <SelectItem key={o.code} value={o.code}>
                      {formatOption(o.code, o.label)}
                    </SelectItem>
                  ))}
                </SelectGroup>
              )}
              <SelectGroup>
                <SelectLabel>Toate valorile</SelectLabel>
                {rest.map((o) => (
                  <SelectItem key={o.code} value={o.code}>
                    {formatOption(o.code, o.label)}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
          {mapped && (
            <Button size="sm" variant="ghost" onClick={onClear} disabled={saving}>
              Șterge
            </Button>
          )}
        </div>
      </TableCell>
    </TableRow>
  )
}

function EmptySources() {
  return <p className="text-xs text-muted-foreground">Nicio valoare distinctă găsită în CarPark.</p>
}

function SimpleDimensionTable({
  dimension,
  rows,
  cache,
  pendingKey,
  onSave,
}: {
  dimension: string
  rows: AutovitTaxonomySourceRow[]
  cache: AutovitTaxonomyCacheRow[]
  pendingKey: string | null
  onSave: (row: AutovitTaxonomySourceRow, targetCode: string | null, targetLabel: string | null) => void
}) {
  if (rows.length === 0) return <EmptySources />
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Valoare CarPark</TableHead>
          <TableHead>Cod Autovit</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TaxonomyRow
            key={row.source_value}
            dimension={dimension}
            row={row}
            cache={cache}
            saving={pendingKey === row.source_value}
            onSave={(code, label) => onSave(row, code, label)}
            onClear={() => onSave(row, null, null)}
          />
        ))}
      </TableBody>
    </Table>
  )
}

function ModelTable({
  rows,
  cache,
  pendingKey,
  onSave,
}: {
  rows: AutovitTaxonomySourceRow[]
  cache: AutovitTaxonomyCacheRow[]
  pendingKey: string | null
  onSave: (row: AutovitTaxonomySourceRow, targetCode: string | null, targetLabel: string | null) => void
}) {
  const grouped = useMemo(() => {
    const byMake = new Map<string, AutovitTaxonomySourceRow[]>()
    for (const row of rows) {
      const make = row.make || '—'
      if (!byMake.has(make)) byMake.set(make, [])
      byMake.get(make)!.push(row)
    }
    return Array.from(byMake.entries()).sort((a, b) => a[0].localeCompare(b[0]))
  }, [rows])

  if (rows.length === 0) return <EmptySources />

  return (
    <div className="space-y-4">
      {grouped.map(([make, modelRows]) => (
        <div key={make}>
          <h4 className="mb-1.5 text-xs font-semibold text-muted-foreground">{make}</h4>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Model</TableHead>
                <TableHead>Cod Autovit</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {modelRows.map((row) => (
                <TaxonomyRow
                  key={row.source_value}
                  dimension="model"
                  row={row}
                  cache={cache}
                  saving={pendingKey === `${make}:${row.source_value}`}
                  onSave={(code, label) => onSave(row, code, label)}
                  onClear={() => onSave(row, null, null)}
                />
              ))}
            </TableBody>
          </Table>
        </div>
      ))}
    </div>
  )
}

export default function AutovitTaxonomy() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [accountId, setAccountId] = useState<string>('')
  const [pendingKey, setPendingKey] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['autovit', 'taxonomy'],
    queryFn: autovitApi.getTaxonomy,
  })

  const { data: accounts = [] } = useQuery({
    queryKey: ['autovit', 'accounts'],
    queryFn: autovitApi.getAccounts,
  })

  const saveMut = useMutation({
    mutationFn: (data: {
      dimension: string
      source_value: string
      make: string | null
      target_code: string | null
      target_label: string | null
    }) => autovitApi.saveTaxonomyMap(data),
    onSuccess: () => {
      toast.success('Mapare salvată')
      qc.invalidateQueries({ queryKey: ['autovit', 'taxonomy'] })
    },
    onError: (err: unknown) => {
      toast.error((err as { data?: { error?: string } })?.data?.error || 'Salvare eșuată')
    },
    onSettled: () => setPendingKey(null),
  })

  const syncMut = useMutation({
    mutationFn: (id: number) => autovitApi.syncTaxonomy(id),
    onSuccess: (res) => {
      if (res.success) {
        toast.success(`Taxonomie sincronizată — ${res.synced ?? 0} valori`)
        qc.invalidateQueries({ queryKey: ['autovit', 'taxonomy'] })
      } else {
        toast.error(res.error || 'Sincronizare eșuată')
      }
    },
    onError: (err: unknown) => {
      toast.error((err as { data?: { error?: string } })?.data?.error || 'Sincronizare eșuată')
    },
  })

  function handleSave(
    dimension: string,
    row: AutovitTaxonomySourceRow,
    targetCode: string | null,
    targetLabel: string | null,
  ) {
    const key = dimension === 'model' ? `${row.make}:${row.source_value}` : row.source_value
    setPendingKey(key)
    saveMut.mutate({
      dimension,
      source_value: row.source_value,
      make: dimension === 'model' ? row.resolved_make_code ?? null : null,
      target_code: targetCode,
      target_label: targetLabel,
    })
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }

  if (!data) {
    return (
      <div className="rounded-lg border p-8 text-center text-sm text-muted-foreground">
        Nu s-a putut încărca maparea de taxonomie.
      </div>
    )
  }

  const sources = data.sources ?? {}
  const cache = data.cache ?? []
  const connectedAccounts = accounts.filter((a) => a.status === 'connected')

  return (
    <div className="space-y-5">
      <PageHeader
        title="Taxonomy mapping"
        breadcrumbs={[
          { label: 'Connectors', onClick: () => navigate(-1) },
          { label: 'Autovit — Taxonomy mapping' },
        ]}
        description="Asociază fiecare valoare din CarPark cu codul exact Autovit (Autovit e sursa de adevăr)."
        actions={
          <div className="flex items-center gap-2">
            <Select value={accountId} onValueChange={setAccountId}>
              <SelectTrigger className="w-56">
                <SelectValue placeholder="Alege cont Autovit..." />
              </SelectTrigger>
              <SelectContent>
                {connectedAccounts.map((acc) => (
                  <SelectItem key={acc.id} value={String(acc.id)}>{acc.email}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              size="sm"
              onClick={() => accountId && syncMut.mutate(Number(accountId))}
              disabled={!accountId || syncMut.isPending}
            >
              {syncMut.isPending ? (
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="mr-1.5 h-4 w-4" />
              )}
              Sincronizează taxonomia
            </Button>
          </div>
        }
      />

      {DIMENSION_ORDER.map((dim) => {
        const rows = sources[dim] ?? []
        return (
          <div key={dim} className="rounded-lg border p-5 space-y-3">
            <div className="flex items-center gap-2">
              <Tags className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold">{formatDimLabel(dim)}</h3>
              <span className="text-xs text-muted-foreground">({rows.length} valori)</span>
            </div>
            {dim === 'model' ? (
              <ModelTable
                rows={rows}
                cache={cache}
                pendingKey={pendingKey}
                onSave={(row, code, label) => handleSave('model', row, code, label)}
              />
            ) : (
              <SimpleDimensionTable
                dimension={dim}
                rows={rows}
                cache={cache}
                pendingKey={pendingKey}
                onSave={(row, code, label) => handleSave(dim, row, code, label)}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
