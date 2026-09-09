import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Save, Tags } from 'lucide-react'
import { toast } from 'sonner'
import { PageHeader } from '@/components/shared/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { shopifyApi } from '@/api/shopify'

type MappingEntry = { target_gid?: string; target_label?: string; shopify_attribute_gid?: string }
type MappingState = Record<string, Record<string, MappingEntry>>

const NATIVE_DIMS = new Set(['fuel_type', 'transmission', 'drive_type', 'color', 'condition'])

const ATTR_GID: Record<string, string> = {
  fuel_type: 'gid://shopify/TaxonomyAttribute/2177',
  transmission: 'gid://shopify/TaxonomyAttribute/2699',
  drive_type: 'gid://shopify/TaxonomyAttribute/2576',
  color: 'gid://shopify/TaxonomyAttribute/1',
  condition: 'gid://shopify/TaxonomyAttribute/2680',
}

const DIM_LABELS: Record<string, string> = {
  fuel_type: 'Combustibil',
  transmission: 'Transmisie',
  drive_type: 'Tracțiune',
  color: 'Culoare',
  condition: 'Stare',
  brand: 'Marcă',
  body_type: 'Caroserie',
  category: 'Categorie',
}

function formatDimLabel(dim: string): string {
  return DIM_LABELS[dim] || dim.replace(/_/g, ' ')
}

function isMapped(entry: MappingEntry | undefined): boolean {
  return !!(entry && (entry.target_gid || entry.target_label))
}

function entriesEqual(a: MappingEntry | undefined, b: MappingEntry | undefined): boolean {
  return (a?.target_gid || '') === (b?.target_gid || '')
    && (a?.target_label || '') === (b?.target_label || '')
    && (a?.shopify_attribute_gid || '') === (b?.shopify_attribute_gid || '')
}

export default function ShopifyTaxonomy() {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['shopify', 'taxonomy'],
    queryFn: shopifyApi.getTaxonomy,
  })

  const [pending, setPending] = useState<MappingState>({})

  // Seed local editable state whenever fresh data arrives (initial load or after save).
  useEffect(() => {
    if (data) setPending(data.mapping ?? {})
  }, [data])

  const saveMut = useMutation({
    mutationFn: (mappings: Array<{ dimension: string; source_value: string } & MappingEntry>) =>
      shopifyApi.saveTaxonomy(mappings),
    onSuccess: () => {
      toast.success('Mapare salvată')
      qc.invalidateQueries({ queryKey: ['shopify', 'taxonomy'] })
    },
    onError: (err: unknown) => {
      toast.error((err as { data?: { error?: string } })?.data?.error || 'Salvare eșuată')
    },
  })

  const changes = useMemo(() => {
    if (!data) return []
    const out: Array<{ dimension: string; source_value: string } & MappingEntry> = []
    for (const dim of data.dimensions) {
      for (const src of data.sources[dim] ?? []) {
        const current = pending[dim]?.[src]
        const original = data.mapping[dim]?.[src]
        if (!entriesEqual(current, original) && isMapped(current)) {
          out.push({
            dimension: dim,
            source_value: src,
            target_gid: current?.target_gid,
            target_label: current?.target_label,
            shopify_attribute_gid: current?.shopify_attribute_gid,
          })
        }
      }
    }
    return out
  }, [data, pending])

  function updateNative(dim: string, src: string, id: string, allowed: { id: string; name: string }[]) {
    const opt = allowed.find((o) => o.id === id)
    setPending((prev) => ({
      ...prev,
      [dim]: {
        ...prev[dim],
        [src]: { target_gid: id, target_label: opt?.name ?? id, shopify_attribute_gid: ATTR_GID[dim] },
      },
    }))
  }

  function updateFreeText(dim: string, src: string, value: string) {
    setPending((prev) => ({
      ...prev,
      [dim]: {
        ...prev[dim],
        [src]: dim === 'category'
          ? { target_gid: value || undefined, target_label: value || undefined, shopify_attribute_gid: undefined }
          : { target_label: value || undefined, shopify_attribute_gid: undefined },
      },
    }))
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

  return (
    <div className="space-y-5">
      <PageHeader
        title="Taxonomy mapping"
        breadcrumbs={[
          { label: 'Connectors', onClick: () => navigate(-1) },
          { label: 'Shopify — Taxonomy mapping' },
        ]}
        description="Asociază fiecare valoare din CarPark cu valoarea corespunzătoare din taxonomia Shopify."
        actions={
          <Button
            size="sm"
            onClick={() => saveMut.mutate(changes)}
            disabled={saveMut.isPending || changes.length === 0}
          >
            {saveMut.isPending ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-1.5 h-4 w-4" />
            )}
            Salvează{changes.length > 0 ? ` (${changes.length})` : ''}
          </Button>
        }
      />

      {data.dimensions.map((dim) => {
        const sources = data.sources[dim] ?? []
        const allowed = data.allowed_values[dim] ?? []
        const isNative = NATIVE_DIMS.has(dim)

        return (
          <div key={dim} className="rounded-lg border p-5 space-y-3">
            <div className="flex items-center gap-2">
              <Tags className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold">{formatDimLabel(dim)}</h3>
              <span className="text-xs text-muted-foreground">({sources.length} valori)</span>
            </div>

            {sources.length === 0 ? (
              <p className="text-xs text-muted-foreground">Nicio valoare distinctă găsită în CarPark.</p>
            ) : (
              <div className="divide-y">
                {sources.map((src) => {
                  const current = pending[dim]?.[src]
                  const mapped = isMapped(current)

                  return (
                    <div key={src} className="flex flex-col gap-2 py-2.5 sm:flex-row sm:items-center sm:justify-between">
                      <div className="flex min-w-0 items-center gap-2">
                        <span className="truncate text-sm font-medium" title={src}>{src}</span>
                        {!mapped && (
                          <Badge variant="destructive" className="shrink-0">Nemapat</Badge>
                        )}
                      </div>
                      <div className="w-full sm:w-72 shrink-0">
                        {isNative ? (
                          <Select
                            value={current?.target_gid || undefined}
                            onValueChange={(v) => updateNative(dim, src, v, allowed)}
                          >
                            <SelectTrigger className="w-full">
                              <SelectValue placeholder="Selectează valoare Shopify..." />
                            </SelectTrigger>
                            <SelectContent>
                              {allowed.map((opt) => (
                                <SelectItem key={opt.id} value={opt.id}>{opt.name}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        ) : (
                          <Input
                            value={current?.target_label || ''}
                            placeholder={dim === 'category' ? 'Sub-categorie (GID)...' : 'Valoare Shopify...'}
                            onChange={(e) => updateFreeText(dim, src, e.target.value)}
                          />
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
