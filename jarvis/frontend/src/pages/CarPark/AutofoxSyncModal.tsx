import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, RefreshCw, Check, Camera, ImageOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { autofoxApi } from '@/api/autofox'
import { toast } from 'sonner'

/**
 * Per-vehicle "Sync from AutoFox" picker: lists the processed photos AutoFox
 * has for this VIN, lets the user choose which to import into the vehicle's
 * gallery. Read-only against AutoFox; already-imported photos are shown but
 * cannot be re-selected.
 */
export function AutofoxSyncModal({
  open,
  onOpenChange,
  vin,
  vehicleId,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  vin: string
  vehicleId: number
}) {
  const qc = useQueryClient()
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['autofox', 'sync', vin],
    queryFn: () => autofoxApi.listPhotos(vin),
    enabled: open && !!vin,
    refetchOnWindowFocus: false,
  })
  const photos = data?.photos ?? []
  const selectable = photos.filter((p) => !p.already_imported)
  const allSelected = selectable.length > 0 && selectable.every((p) => selected.has(p.conversion_id))

  const importMut = useMutation({
    mutationFn: () => autofoxApi.importPhotos(vin, Array.from(selected)),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['carpark', 'vehicle', vehicleId] })
      const errs = res.errors?.length ? ` (${res.errors.length} erori)` : ''
      toast.success(`${res.created} poze importate din AutoFox${errs}`)
      setSelected(new Set())
      onOpenChange(false)
    },
    onError: () => toast.error('Importul din AutoFox a eșuat'),
  })

  const toggle = (id: string) =>
    setSelected((prev) => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })

  const toggleAll = () =>
    setSelected(allSelected ? new Set() : new Set(selectable.map((p) => p.conversion_id)))

  const close = (v: boolean) => {
    if (!v) setSelected(new Set())
    onOpenChange(v)
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Camera className="h-5 w-5" /> Sincronizează poze din AutoFox
          </DialogTitle>
        </DialogHeader>

        <div className="text-sm text-muted-foreground">
          VIN <span className="font-mono">{vin}</span>
        </div>

        {isLoading || isFetching ? (
          <div className="flex h-48 items-center justify-center text-muted-foreground">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Se încarcă din AutoFox…
          </div>
        ) : isError ? (
          <div className="flex h-48 flex-col items-center justify-center gap-2 text-sm text-red-600">
            <ImageOff className="h-6 w-6" />
            {(error as { data?: { error?: string } })?.data?.error ||
              'Nu s-au putut încărca pozele din AutoFox.'}
            <Button size="sm" variant="outline" onClick={() => refetch()}>
              <RefreshCw className="mr-1 h-3.5 w-3.5" /> Reîncearcă
            </Button>
          </div>
        ) : photos.length === 0 ? (
          <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
            Nicio poză procesată în AutoFox pentru acest VIN.
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                {photos.length} disponibile · {selected.size} selectate
              </span>
              <Button size="sm" variant="ghost" onClick={toggleAll} disabled={!selectable.length}>
                {allSelected ? 'Deselectează tot' : 'Selectează tot'}
              </Button>
            </div>
            <div className="grid max-h-[55vh] grid-cols-3 gap-3 overflow-y-auto p-1 sm:grid-cols-4">
              {photos.map((p) => {
                const sel = selected.has(p.conversion_id)
                const done = p.already_imported
                return (
                  <button
                    key={p.conversion_id}
                    type="button"
                    disabled={done}
                    onClick={() => !done && toggle(p.conversion_id)}
                    className={`relative overflow-hidden rounded-lg border-2 ${
                      sel ? 'border-primary' : 'border-transparent'
                    } ${done ? 'cursor-default opacity-50' : 'hover:border-muted-foreground'}`}
                  >
                    <img
                      src={autofoxApi.imageProxyUrl(p.path)}
                      alt={p.conversion_id}
                      loading="lazy"
                      className="aspect-square w-full bg-muted object-cover"
                    />
                    {done && (
                      <span className="absolute inset-x-0 bottom-0 bg-black/60 py-0.5 text-center text-[10px] text-white">
                        Importată
                      </span>
                    )}
                    {sel && (
                      <span className="absolute right-1 top-1 rounded-full bg-primary p-0.5 text-primary-foreground">
                        <Check className="h-3.5 w-3.5" />
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          </>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => close(false)}>
            Anulează
          </Button>
          <Button onClick={() => importMut.mutate()} disabled={!selected.size || importMut.isPending}>
            {importMut.isPending ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
            Importă{selected.size ? ` (${selected.size})` : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
