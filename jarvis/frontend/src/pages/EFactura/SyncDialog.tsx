import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, Loader2, CheckCircle, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { efacturaApi } from '@/api/efactura'
import type { SyncCompany } from '@/types/efactura'

const PERIOD_PRESETS = [1, 3, 7, 15, 30] as const

export function SyncDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const qc = useQueryClient()
  const [selectedDays, setSelectedDays] = useState<number>(1)
  const [customDays, setCustomDays] = useState('')
  const [useCustom, setUseCustom] = useState(false)
  const [selectedCifs, setSelectedCifs] = useState<Set<string>>(new Set())
  const [initialized, setInitialized] = useState(false)

  const { data: companies = [] } = useQuery({
    queryKey: ['efactura-sync-companies'],
    queryFn: () => efacturaApi.getSyncCompanies(),
  })

  // Auto-select all companies once when they first load
  if (companies.length > 0 && !initialized) {
    setSelectedCifs(new Set(companies.map((c) => c.cif)))
    setInitialized(true)
  }

  const syncMut = useMutation({
    mutationFn: async () => {
      const days = useCustom ? (Number(customDays) || 1) : selectedDays
      const cifs = Array.from(selectedCifs)
      // Sync each selected company
      const results = await Promise.allSettled(
        cifs.map((cif) => efacturaApi.syncSingleCompany(cif, days)),
      )
      return {
        total: cifs.length,
        succeeded: results.filter((r) => r.status === 'fulfilled').length,
        results: results.map((r, i) => ({
          cif: cifs[i],
          company: companies.find((c) => c.cif === cifs[i])?.display_name ?? cifs[i],
          success: r.status === 'fulfilled',
          imported: r.status === 'fulfilled' ? r.value.imported : 0,
          skipped: r.status === 'fulfilled' ? r.value.skipped : 0,
          error: r.status === 'rejected' ? String(r.reason) : undefined,
        })),
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['efactura-unallocated'] })
      qc.invalidateQueries({ queryKey: ['efactura-unallocated-count'] })
      qc.invalidateQueries({ queryKey: ['efactura-hidden-count'] })
      qc.invalidateQueries({ queryKey: ['efactura-bin-count'] })
      qc.invalidateQueries({ queryKey: ['efactura-sync-history'] })
    },
  })

  const toggleCif = (cif: string) => {
    setSelectedCifs((prev) => {
      const next = new Set(prev)
      if (next.has(cif)) next.delete(cif)
      else next.add(cif)
      return next
    })
  }

  const selectAll = () => setSelectedCifs(new Set(companies.map((c) => c.cif)))
  const deselectAll = () => setSelectedCifs(new Set())

  const days = useCustom ? (Number(customDays) || 0) : selectedDays
  const canSync = days > 0 && days <= 90 && selectedCifs.size > 0

  const handleClose = () => {
    syncMut.reset()
    setInitialized(false)
    setSelectedCifs(new Set())
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <RefreshCw className="h-5 w-5" />
            Sync from ANAF
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-5">
          {/* Period */}
          <div className="space-y-2">
            <Label className="text-sm font-semibold">Period</Label>
            <div className="flex flex-wrap gap-2">
              {PERIOD_PRESETS.map((d) => (
                <Button
                  key={d}
                  size="sm"
                  variant={!useCustom && selectedDays === d ? 'default' : 'outline'}
                  onClick={() => { setSelectedDays(d); setUseCustom(false) }}
                >
                  {d} day{d > 1 ? 's' : ''}
                </Button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant={useCustom ? 'default' : 'outline'}
                onClick={() => setUseCustom(true)}
              >
                Custom
              </Button>
              <Input
                type="number"
                placeholder="Enter days"
                className="w-[120px]"
                value={customDays}
                onChange={(e) => { setCustomDays(e.target.value); setUseCustom(true) }}
                min={1}
                max={90}
              />
              <span className="text-sm text-muted-foreground">days (max 90)</span>
            </div>
          </div>

          {/* Companies */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="text-sm font-semibold">Companies</Label>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={selectAll}>
                  Select All
                </Button>
                <Button size="sm" variant="outline" onClick={deselectAll}>
                  Deselect All
                </Button>
              </div>
            </div>
            <div className="max-h-[200px] space-y-1 overflow-y-auto rounded border p-2">
              {companies.length === 0 ? (
                <p className="text-sm text-muted-foreground py-2 text-center">
                  No companies with active connections
                </p>
              ) : (
                companies.map((c: SyncCompany) => (
                  <label
                    key={c.cif}
                    className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 hover:bg-muted/50"
                  >
                    <Checkbox
                      checked={selectedCifs.has(c.cif)}
                      onCheckedChange={() => toggleCif(c.cif)}
                    />
                    <span className="text-sm">
                      {c.display_name} ({c.cif})
                    </span>
                  </label>
                ))
              )}
            </div>
          </div>

          {/* Result banner */}
          {syncMut.isSuccess && syncMut.data && (
            <div className="rounded border border-green-200 bg-green-50 p-3 text-sm dark:border-green-800 dark:bg-green-900/20">
              <div className="flex items-center gap-2 font-medium text-green-700 dark:text-green-400">
                <CheckCircle className="h-4 w-4" />
                Sync complete — {syncMut.data.succeeded}/{syncMut.data.total} companies
              </div>
              <div className="mt-2 space-y-1">
                {syncMut.data.results.map((r) => (
                  <div key={r.cif} className="flex items-center gap-2 text-xs">
                    {r.success ? (
                      <CheckCircle className="h-3 w-3 text-green-600" />
                    ) : (
                      <AlertTriangle className="h-3 w-3 text-red-500" />
                    )}
                    <span className="font-medium">{r.company}</span>
                    {r.success && (
                      <span className="text-muted-foreground">
                        — {r.imported} imported, {r.skipped} skipped
                      </span>
                    )}
                    {!r.success && r.error && (
                      <span className="text-red-600">{r.error}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {syncMut.isError && (
            <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
              <AlertTriangle className="mr-1 inline h-4 w-4" />
              Sync failed: {String(syncMut.error)}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose}>
            {syncMut.isSuccess ? 'Close' : 'Cancel'}
          </Button>
          {!syncMut.isSuccess && (
            <Button
              onClick={() => syncMut.mutate()}
              disabled={!canSync || syncMut.isPending}
            >
              {syncMut.isPending ? (
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="mr-1.5 h-4 w-4" />
              )}
              Start Sync
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
