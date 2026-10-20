import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ChevronsUpDown, Loader2, RefreshCw, Sparkles, Tags } from 'lucide-react'
import { toast } from 'sonner'
import { PageHeader } from '@/components/shared/PageHeader'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
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
import { autovitApi } from '@/api/autovit'
import type { AutovitTaxonomyCacheRow, AutovitTaxonomySourceRow } from '@/api/autovit'

type Opt = { code: string; label: string | null }

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
    const suggested: Opt[] = []
    for (const s of row.suggestions) {
      if (seen.has(s.target_code)) continue
      seen.add(s.target_code)
      suggested.push({ code: s.target_code, label: s.target_label })
    }
    const rest: Opt[] = []
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

// Searchable combobox: type to filter the Autovit codes/labels, suggestions
// pinned on top. (shadcn Select can't search; cmdk isn't installed — built from
// Popover + Input + a scrollable list.)
function CodeCombobox({
  value,
  valueLabel,
  suggested,
  rest,
  disabled,
  onSelect,
}: {
  value: string | null
  valueLabel?: string | null
  suggested: Opt[]
  rest: Opt[]
  disabled?: boolean
  onSelect: (code: string, label: string | null) => void
}) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  // Prefer the matching cache/suggestion option; fall back to the stored
  // target_label so a mapped value still shows before the cache is synced.
  const current = useMemo(() => {
    const hit = [...suggested, ...rest].find((o) => o.code === value)
    if (hit) return hit
    return value ? { code: value, label: valueLabel ?? null } : null
  }, [suggested, rest, value, valueLabel])
  const match = (o: Opt) => {
    if (!q.trim()) return true
    const hay = `${o.label ?? ''} ${o.code}`.toLowerCase()
    return q.toLowerCase().split(/\s+/).filter(Boolean).every((w) => hay.includes(w))
  }
  const fSug = suggested.filter(match)
  const fRest = rest.filter(match)
  const pick = (o: Opt) => {
    onSelect(o.code, o.label)
    setOpen(false)
    setQ('')
  }
  const Item = ({ o }: { o: Opt }) => (
    <button
      type="button"
      onClick={() => pick(o)}
      className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-accent"
    >
      <Check className={`h-3.5 w-3.5 shrink-0 ${o.code === value ? 'opacity-100' : 'opacity-0'}`} />
      <span className="truncate">{formatOption(o.code, o.label)}</span>
    </button>
  )

  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); if (!o) setQ('') }}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          disabled={disabled}
          className="w-full justify-between font-normal"
        >
          <span className="truncate">
            {current ? formatOption(current.code, current.label)
              : <span className="text-muted-foreground">Selectează cod Autovit...</span>}
          </span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(34rem,90vw)] p-0" align="start">
        <div className="border-b p-2">
          <Input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Caută cod Autovit..."
            className="h-8"
          />
        </div>
        <div className="max-h-72 overflow-y-auto p-1">
            {fSug.length > 0 && (
              <>
                <div className="px-2 py-1 text-xs font-medium text-muted-foreground">Sugestii</div>
                {fSug.map((o) => <Item key={`s-${o.code}`} o={o} />)}
                <div className="my-1 h-px bg-border" />
              </>
            )}
            <div className="px-2 py-1 text-xs font-medium text-muted-foreground">Toate valorile</div>
            {fSug.length === 0 && fRest.length === 0 ? (
              <div className="px-2 py-3 text-center text-xs text-muted-foreground">Niciun rezultat</div>
            ) : (
              fRest.map((o) => <Item key={`r-${o.code}`} o={o} />)
            )}
        </div>
      </PopoverContent>
    </Popover>
  )
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
  const top = !mapped && suggested.length > 0 ? suggested[0] : null

  return (
    <TableRow>
      <TableCell className="font-medium">
        <div className="flex items-center gap-2">
          <span className="truncate" title={row.source_value}>{row.source_value}</span>
          {!mapped && <Badge variant="destructive">Nemapat</Badge>}
        </div>
      </TableCell>
      <TableCell className="min-w-[320px]">
        <div className="flex items-center gap-2">
          <CodeCombobox
            value={row.target_code ?? null}
            valueLabel={row.target_label}
            suggested={suggested}
            rest={rest}
            disabled={saving}
            onSelect={(code, label) => onSave(code, label)}
          />
          {top && (
            <Button
              size="sm"
              variant="secondary"
              className="shrink-0 whitespace-nowrap"
              onClick={() => onSave(top.code, top.label)}
              disabled={saving}
              title={`Acceptă sugestia: ${formatOption(top.code, top.label)}`}
            >
              {saving
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <Check className="mr-1 h-3.5 w-3.5" />}
              <span className="max-w-[140px] truncate">{top.label ?? top.code}</span>
            </Button>
          )}
          {mapped && (
            <Button size="sm" variant="ghost" className="shrink-0" onClick={onClear} disabled={saving}>
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
  const [bulkDim, setBulkDim] = useState<string | null>(null)

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

  // Bulk-accept the top suggestion for every still-unmapped row in a dimension.
  // Fires the saves in parallel, then refreshes once (avoids a per-row refetch storm).
  async function acceptAllSuggestions(dimension: string, rows: AutovitTaxonomySourceRow[]) {
    const targets = rows.filter((r) => !r.target_code && r.suggestions.length > 0)
    if (targets.length === 0) return
    setBulkDim(dimension)
    try {
      await Promise.all(
        targets.map((r) => autovitApi.saveTaxonomyMap({
          dimension,
          source_value: r.source_value,
          make: dimension === 'model' ? r.resolved_make_code ?? null : null,
          target_code: r.suggestions[0].target_code,
          target_label: r.suggestions[0].target_label,
        })),
      )
      toast.success(`${targets.length} sugestii acceptate`)
    } catch (err) {
      toast.error((err as { data?: { error?: string } })?.data?.error || 'Acceptarea sugestiilor a eșuat')
    } finally {
      setBulkDim(null)
      qc.invalidateQueries({ queryKey: ['autovit', 'taxonomy'] })
    }
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
        const suggestable = rows.filter((r) => !r.target_code && r.suggestions.length > 0).length
        const unmapped = rows.filter((r) => !r.target_code).length
        return (
          <div key={dim} className="rounded-lg border p-5 space-y-3">
            <div className="flex items-center gap-2">
              <Tags className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold">{formatDimLabel(dim)}</h3>
              <span className="text-xs text-muted-foreground">
                ({rows.length} valori{unmapped > 0 ? `, ${unmapped} nemapate` : ''})
              </span>
              <div className="ml-auto">
                {suggestable > 0 && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => acceptAllSuggestions(dim, rows)}
                    disabled={bulkDim === dim}
                    title="Acceptă sugestia de top pentru toate valorile nemapate care au una"
                  >
                    {bulkDim === dim
                      ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                      : <Sparkles className="mr-1.5 h-3.5 w-3.5" />}
                    Acceptă sugestiile ({suggestable})
                  </Button>
                )}
              </div>
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
