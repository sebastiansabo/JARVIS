import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { RotateCcw, Trash2, Archive } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { EmptyState } from '@/components/shared/EmptyState'
import { QueryError } from '@/components/QueryError'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { cn } from '@/lib/utils'
import { efacturaApi } from '@/api/efactura'
import { columnDefMap, type ColumnDef, type InvoiceRow } from './unallocated/UnallocatedColumns'

const BIN_COLUMNS = ['supplier', 'invoice_number', 'date', 'direction', 'amount', 'company']

export default function BinTab({ search = '' }: { search?: string }) {
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [confirmPurge, setConfirmPurge] = useState<number[] | null>(null)

  const cols = useMemo(
    () => BIN_COLUMNS.map((k) => columnDefMap.get(k)).filter(Boolean) as ColumnDef[],
    [],
  )

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['efactura-bin', { page, search }],
    queryFn: () => efacturaApi.getBin({ page, limit: 50, search: search || undefined }),
  })

  const invoices = (data?.invoices ?? []) as InvoiceRow[]
  const pagination = data?.pagination

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['efactura-bin'] })
    qc.invalidateQueries({ queryKey: ['efactura-bin-count'] })
    qc.invalidateQueries({ queryKey: ['efactura-unallocated'] })
    qc.invalidateQueries({ queryKey: ['efactura-unallocated-count'] })
    setSelectedIds(new Set())
    setConfirmPurge(null)
  }

  const restoreMut = useMutation({
    mutationFn: (ids: number[]) => efacturaApi.bulkRestoreBin(ids),
    onSuccess: invalidate,
  })

  const purgeMut = useMutation({
    mutationFn: (ids: number[]) => efacturaApi.bulkPermanentDelete(ids),
    onSuccess: invalidate,
  })

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    if (selectedIds.size === invoices.length) setSelectedIds(new Set())
    else setSelectedIds(new Set(invoices.map((i) => i.id)))
  }

  const selectedArr = Array.from(selectedIds)

  if (isError) return <QueryError message="Failed to load the Bin" onRetry={() => refetch()} />

  return (
    <div className="space-y-4">
      {/* Bulk actions */}
      {selectedIds.size > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded border bg-muted/30 px-3 py-2">
          <span className="text-sm font-medium">{selectedIds.size} selected</span>
          <Button size="sm" variant="outline" onClick={() => restoreMut.mutate(selectedArr)} disabled={restoreMut.isPending}>
            <RotateCcw className="mr-1 h-3 w-3" /> Restore
          </Button>
          <Button size="sm" variant="outline" className="text-destructive" onClick={() => setConfirmPurge(selectedArr)}>
            <Trash2 className="mr-1 h-3 w-3" /> Delete permanently
          </Button>
        </div>
      )}

      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => <div key={i} className="h-12 animate-pulse rounded bg-muted" />)}
        </div>
      ) : invoices.length === 0 ? (
        <EmptyState icon={<Archive className="h-10 w-10" />} title="Bin is empty" description="Deleted invoices appear here for 10 days before being permanently removed." />
      ) : (
        <div className="overflow-x-auto rounded border">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/50">
              <tr>
                <th className="w-10 px-3 py-2">
                  <Checkbox
                    checked={selectedIds.size === invoices.length && invoices.length > 0}
                    onCheckedChange={toggleAll}
                    aria-label="Select all"
                  />
                </th>
                {cols.map((c) => (
                  <th key={c.key} className={cn('px-3 py-2 text-left font-medium text-muted-foreground', c.align === 'right' && 'text-right')}>
                    {c.label}
                  </th>
                ))}
                <th className="px-3 py-2 text-right font-medium text-muted-foreground">Actions</th>
              </tr>
            </thead>
            <tbody>
              {invoices.map((inv) => (
                <tr key={inv.id} className="border-b last:border-0 hover:bg-muted/30">
                  <td className="px-3 py-2">
                    <Checkbox checked={selectedIds.has(inv.id)} onCheckedChange={() => toggleSelect(inv.id)} aria-label={`Select ${inv.id}`} />
                  </td>
                  {cols.map((c) => (
                    <td key={c.key} className={cn('px-3 py-2', c.align === 'right' && 'text-right')}>
                      {c.render(inv)}
                    </td>
                  ))}
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-end gap-1">
                      <Button size="icon" variant="ghost" className="h-7 w-7" title="Restore" onClick={() => restoreMut.mutate([inv.id])}>
                        <RotateCcw className="h-3.5 w-3.5" />
                      </Button>
                      <Button size="icon" variant="ghost" className="h-7 w-7 text-destructive" title="Delete permanently" onClick={() => setConfirmPurge([inv.id])}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {pagination && pagination.total_pages > 1 && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>{pagination.total} in Bin</span>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Prev</Button>
            <span>Page {pagination.page} / {pagination.total_pages}</span>
            <Button size="sm" variant="outline" disabled={page >= pagination.total_pages} onClick={() => setPage((p) => p + 1)}>Next</Button>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirmPurge != null}
        onOpenChange={(o) => { if (!o) setConfirmPurge(null) }}
        title="Delete permanently"
        description={
          confirmPurge
            ? `Permanently delete ${confirmPurge.length} invoice${confirmPurge.length === 1 ? '' : 's'}? This cannot be undone.`
            : ''
        }
        confirmLabel="Delete permanently"
        destructive
        onConfirm={() => { if (confirmPurge) purgeMut.mutate(confirmPurge) }}
      />
    </div>
  )
}
