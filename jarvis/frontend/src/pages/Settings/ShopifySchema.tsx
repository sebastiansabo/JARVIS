import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Plus, RefreshCw, Save } from 'lucide-react'
import { toast } from 'sonner'
import { PageHeader } from '@/components/shared/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { shopifyApi, type FieldMapRow } from '@/api/shopify'

const TRANSFORMS = ['raw', 'int', 'year', 'ro_value', 'ro_list', 'dotari'] as const

const VALUE_DIMENSIONS = [
  'fuel_type',
  'transmission',
  'drive_type',
  'color_exterior',
  'body_type',
  'state',
]

type FieldKey = string // `${target_namespace}.${target_key}`

function fieldKey(row: Pick<FieldMapRow, 'target_namespace' | 'target_key'>): FieldKey {
  return `${row.target_namespace}.${row.target_key}`
}

type NewFieldDraft = { namespace: string; key: string; type: string; source_expr: string; transform: string }

export default function ShopifySchema() {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['shopify', 'schema'],
    queryFn: shopifyApi.getSchema,
  })

  // Field-map editable state, keyed by `namespace.key`.
  const [fieldEdits, setFieldEdits] = useState<Record<FieldKey, { source_expr: string; transform: string; is_active: boolean }>>({})
  // New unmapped-field drafts, keyed by `namespace.key`.
  const [newDrafts, setNewDrafts] = useState<Record<FieldKey, NewFieldDraft>>({})
  // Which new-field drafts have been explicitly added via "Adaugă" (only these are saved).
  const [addedFields, setAddedFields] = useState<Set<FieldKey>>(new Set())
  // Value-map editable state, nested by dimension then source_value.
  const [valueEdits, setValueEdits] = useState<Record<string, Record<string, string>>>({})
  const [addValueDim, setAddValueDim] = useState<string>('')
  const [addValueSrc, setAddValueSrc] = useState<string>('')
  const [addValueRo, setAddValueRo] = useState<string>('')

  useEffect(() => {
    if (!data) return
    setFieldEdits({})
    setNewDrafts({})
    setAddedFields(new Set())
    setValueEdits({})
  }, [data])

  const staleSet = useMemo(() => {
    const s = new Set<string>()
    for (const row of data?.field_map ?? []) {
      if (row.last_seen_in_store === false) s.add(fieldKey(row))
    }
    return s
  }, [data])

  const typeChangedSet = useMemo(() => {
    const s = new Set<string>()
    for (const row of data?.drift?.type_changed ?? []) {
      s.add(`${row.target_namespace}.${row.target_key}`)
    }
    return s
  }, [data])

  const mappedTargets = useMemo(() => {
    const s = new Set<string>()
    for (const row of data?.field_map ?? []) s.add(fieldKey(row))
    return s
  }, [data])

  const unmappedNew = useMemo(() => {
    return (data?.drift?.new ?? []).filter((n) => !mappedTargets.has(`${n.namespace}.${n.key}`))
  }, [data, mappedTargets])

  const syncMut = useMutation({
    mutationFn: shopifyApi.syncSchema,
    onSuccess: (res) => {
      const drift = res.drift ?? {}
      toast.success(`${drift.new?.length ?? 0} noi, ${drift.stale?.length ?? 0} lipsă`)
      qc.invalidateQueries({ queryKey: ['shopify', 'schema'] })
    },
    onError: (err: unknown) => {
      toast.error((err as { data?: { error?: string } })?.data?.error || 'Sincronizare eșuată')
    },
  })

  const saveMut = useMutation({
    mutationFn: ({
      field_entries,
      value_entries,
    }: {
      field_entries: Partial<FieldMapRow>[]
      value_entries: { dimension: string; source_value: string; ro_value: string }[]
    }) => shopifyApi.saveSchema(field_entries, value_entries),
    onSuccess: () => {
      toast.success('Schema salvată')
      qc.invalidateQueries({ queryKey: ['shopify', 'schema'] })
    },
    onError: (err: unknown) => {
      toast.error((err as { data?: { error?: string } })?.data?.error || 'Salvare eșuată')
    },
  })

  function updateField(row: FieldMapRow, patch: Partial<{ source_expr: string; transform: string; is_active: boolean }>) {
    const key = fieldKey(row)
    setFieldEdits((prev) => ({
      ...prev,
      [key]: {
        source_expr: prev[key]?.source_expr ?? row.source_expr ?? '',
        transform: prev[key]?.transform ?? row.transform,
        is_active: prev[key]?.is_active ?? row.is_active,
        ...patch,
      },
    }))
  }

  function updateNewDraft(namespace: string, key: string, type: string, patch: Partial<NewFieldDraft>) {
    const k = `${namespace}.${key}`
    setNewDrafts((prev) => {
      const base: NewFieldDraft = prev[k] ?? { namespace, key, type, source_expr: '', transform: 'raw' }
      return { ...prev, [k]: { ...base, ...patch } }
    })
  }

  function commitNewDraft(namespace: string, key: string) {
    const k = `${namespace}.${key}`
    setAddedFields((prev) => new Set(prev).add(k))
  }

  function updateValue(dimension: string, sourceValue: string, roValue: string) {
    setValueEdits((prev) => ({
      ...prev,
      [dimension]: { ...prev[dimension], [sourceValue]: roValue },
    }))
  }

  const fieldChangeCount = Object.keys(fieldEdits).length + addedFields.size
  const valueChangeCount = Object.values(valueEdits).reduce((sum, rec) => sum + Object.keys(rec).length, 0)
  const totalChanges = fieldChangeCount + valueChangeCount

  function handleSave() {
    const field_entries: Partial<FieldMapRow>[] = []
    for (const row of data?.field_map ?? []) {
      const key = fieldKey(row)
      const edit = fieldEdits[key]
      if (!edit) continue
      field_entries.push({
        target_namespace: row.target_namespace,
        target_key: row.target_key,
        target_type: row.target_type,
        source_expr: edit.source_expr,
        transform: edit.transform,
        is_active: edit.is_active,
      })
    }
    for (const k of addedFields) {
      const draft = newDrafts[k]
      if (!draft || !draft.source_expr.trim()) continue
      field_entries.push({
        target_namespace: draft.namespace,
        target_key: draft.key,
        target_type: draft.type,
        source_expr: draft.source_expr,
        transform: draft.transform,
        is_active: true,
      })
    }

    const value_entries: { dimension: string; source_value: string; ro_value: string }[] = []
    for (const [dimension, rec] of Object.entries(valueEdits)) {
      for (const [source_value, ro_value] of Object.entries(rec)) {
        value_entries.push({ dimension, source_value, ro_value })
      }
    }

    saveMut.mutate({ field_entries, value_entries })
  }

  function handleAddValue() {
    if (!addValueDim.trim() || !addValueSrc.trim()) return
    updateValue(addValueDim.trim(), addValueSrc.trim(), addValueRo)
    setAddValueSrc('')
    setAddValueRo('')
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }

  if (!data) {
    return (
      <div className="rounded-lg border p-8 text-center text-sm text-muted-foreground">
        Nu s-a putut încărca schema de mapare.
      </div>
    )
  }

  const valueDims = Array.from(new Set([...Object.keys(data.value_map ?? {}), ...VALUE_DIMENSIONS]))

  return (
    <div className="space-y-5">
      <PageHeader
        title="Schema mapping"
        breadcrumbs={[
          { label: 'Connectors', onClick: () => navigate(-1) },
          { label: 'Shopify — Schema mapping' },
        ]}
        description="Maparea câmpurilor CarPark → metafields Shopify și traducerile RO ale valorilor."
        actions={
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => syncMut.mutate()}
              disabled={syncMut.isPending}
            >
              {syncMut.isPending ? (
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="mr-1.5 h-4 w-4" />
              )}
              Sync schema
            </Button>
            <Button
              size="sm"
              onClick={handleSave}
              disabled={saveMut.isPending || totalChanges === 0}
            >
              {saveMut.isPending ? (
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
              ) : (
                <Save className="mr-1.5 h-4 w-4" />
              )}
              Salvează{totalChanges > 0 ? ` (${totalChanges})` : ''}
            </Button>
          </div>
        }
      />

      {/* Field map */}
      <div className="rounded-lg border p-5 space-y-3">
        <h3 className="text-sm font-semibold">Field map</h3>
        {(data.field_map ?? []).length === 0 ? (
          <p className="text-xs text-muted-foreground">Niciun câmp mapat momentan.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Sursă CarPark</TableHead>
                <TableHead>Target metafield</TableHead>
                <TableHead>Tip</TableHead>
                <TableHead>Transform</TableHead>
                <TableHead>Activ</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.field_map.map((row) => {
                const key = fieldKey(row)
                const edit = fieldEdits[key]
                const sourceExpr = edit?.source_expr ?? row.source_expr ?? ''
                const transform = edit?.transform ?? row.transform
                const isActive = edit?.is_active ?? row.is_active
                const isStale = staleSet.has(key)
                const isTypeChanged = typeChangedSet.has(key)

                return (
                  <TableRow key={key}>
                    <TableCell>
                      <Input
                        value={sourceExpr}
                        placeholder="ex: brand, model, custom.equipment..."
                        onChange={(e) => updateField(row, { source_expr: e.target.value })}
                        className="min-w-48"
                      />
                    </TableCell>
                    <TableCell className="font-mono text-xs">{key}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{row.target_type}</Badge>
                    </TableCell>
                    <TableCell>
                      <Select
                        value={transform}
                        onValueChange={(v) => updateField(row, { transform: v })}
                      >
                        <SelectTrigger className="w-36">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {TRANSFORMS.map((t) => (
                            <SelectItem key={t} value={t}>{t}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell>
                      <Checkbox
                        checked={isActive}
                        onCheckedChange={(v) => updateField(row, { is_active: v === true })}
                      />
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        {isStale && <Badge variant="destructive">STALE</Badge>}
                        {isTypeChanged && (
                          <Badge className="border-amber-500/30 bg-amber-500/15 text-amber-600 dark:text-amber-400">
                            TYPE-CHANGED
                          </Badge>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </div>

      {/* Unmapped store fields */}
      <div className="rounded-lg border p-5 space-y-3">
        <h3 className="text-sm font-semibold">Câmpuri noi în magazin (nemapate)</h3>
        {unmappedNew.length === 0 ? (
          <p className="text-xs text-muted-foreground">Niciun câmp nou nemapat.</p>
        ) : (
          <div className="divide-y">
            {unmappedNew.map((n) => {
              const k = `${n.namespace}.${n.key}`
              const draft = newDrafts[k]
              const isAdded = addedFields.has(k)
              return (
                <div key={k} className="flex flex-col gap-2 py-2.5 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="font-mono text-xs">{k}</span>
                    <Badge variant="outline">{n.type}</Badge>
                    <Badge variant="secondary">NOU</Badge>
                  </div>
                  <div className="flex w-full items-center gap-2 sm:w-auto">
                    <Input
                      value={draft?.source_expr ?? ''}
                      placeholder="Sursă CarPark..."
                      onChange={(e) => updateNewDraft(n.namespace, n.key, n.type, { source_expr: e.target.value })}
                      className="w-full sm:w-56"
                    />
                    <Select
                      value={draft?.transform ?? 'raw'}
                      onValueChange={(v) => updateNewDraft(n.namespace, n.key, n.type, { transform: v })}
                    >
                      <SelectTrigger className="w-32 shrink-0">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {TRANSFORMS.map((t) => (
                          <SelectItem key={t} value={t}>{t}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      size="sm"
                      variant={isAdded ? 'secondary' : 'outline'}
                      disabled={!draft?.source_expr?.trim()}
                      onClick={() => commitNewDraft(n.namespace, n.key)}
                    >
                      <Plus className="mr-1 h-3 w-3" /> {isAdded ? 'Adăugat' : 'Adaugă'}
                    </Button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Value map */}
      <div className="rounded-lg border p-5 space-y-4">
        <h3 className="text-sm font-semibold">Value map (traduceri RO)</h3>

        {valueDims.map((dim) => {
          const sources = data.value_map?.[dim] ?? {}
          const sourceKeys = Object.keys(sources)
          if (sourceKeys.length === 0) return null

          return (
            <div key={dim} className="space-y-2">
              <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{dim}</h4>
              <div className="divide-y">
                {sourceKeys.map((src) => {
                  const value = valueEdits[dim]?.[src] ?? sources[src]
                  return (
                    <div key={src} className="flex flex-col gap-2 py-2 sm:flex-row sm:items-center sm:justify-between">
                      <span className="truncate text-sm" title={src}>{src}</span>
                      <div className="flex items-center gap-2 sm:w-72">
                        <span className="text-muted-foreground text-xs">→</span>
                        <Input
                          value={value}
                          onChange={(e) => updateValue(dim, src, e.target.value)}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}

        {/* Add new value */}
        <div className="flex flex-col gap-2 border-t pt-3 sm:flex-row sm:items-center">
          <Select value={addValueDim} onValueChange={setAddValueDim}>
            <SelectTrigger className="w-full sm:w-44">
              <SelectValue placeholder="Dimensiune..." />
            </SelectTrigger>
            <SelectContent>
              {valueDims.map((dim) => (
                <SelectItem key={dim} value={dim}>{dim}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            value={addValueSrc}
            placeholder="Valoare sursă..."
            onChange={(e) => setAddValueSrc(e.target.value)}
            className="w-full sm:w-48"
          />
          <span className="text-muted-foreground text-xs shrink-0">→</span>
          <Input
            value={addValueRo}
            placeholder="Valoare RO..."
            onChange={(e) => setAddValueRo(e.target.value)}
            className="w-full sm:w-48"
          />
          <Button
            size="sm"
            variant="outline"
            disabled={!addValueDim.trim() || !addValueSrc.trim()}
            onClick={handleAddValue}
          >
            <Plus className="mr-1 h-3 w-3" /> Adaugă valoare
          </Button>
        </div>
      </div>
    </div>
  )
}
