import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { foiParcursApi } from '@/api/foiParcurs'
import type { FpVehicle } from '@/types/foiParcurs'

export default function ArchiveVehicleDialog({ vehicle, onClose, onSubmit, submitting }: {
  vehicle: FpVehicle
  onClose: () => void
  onSubmit: (data: { category: string; note?: string }) => void
  submitting: boolean
}) {
  // Reasons are configurable (FP Settings → Motive arhivare); show only active ones.
  const { data: reasonsData } = useQuery({
    queryKey: ['fp-archive-reasons', 'active'],
    queryFn: () => foiParcursApi.getArchiveReasons(true),
    staleTime: 60_000,
  })
  const reasons = reasonsData?.reasons ?? []
  const [category, setCategory] = useState('')
  const [note, setNote] = useState('')

  // Default to the first active reason once loaded.
  useEffect(() => {
    if (!category && reasons.length) setCategory(reasons[0].slug)
  }, [reasons]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Arhivează vehiculul</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            {[vehicle.mark, vehicle.model].filter(Boolean).join(' ')} — {vehicle.registration_number || vehicle.vin}
          </p>
          <p className="text-xs text-muted-foreground">
            Mașina nu va mai apărea în listă (poate fi restaurată din tab-ul Arhivate).
          </p>
          <div className="space-y-1.5">
            <Label className="text-xs">Motiv arhivare</Label>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger><SelectValue placeholder="Alege motivul" /></SelectTrigger>
              <SelectContent>
                {reasons.map((r) => (
                  <SelectItem key={r.slug} value={r.slug}>{r.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {reasons.length === 0 && (
              <p className="text-xs text-muted-foreground">
                Niciun motiv activ. Adaugă unul în Setări → Motive arhivare.
              </p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Detalii (opțional)</Label>
            <Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2}
              placeholder="Ex: vândut către client, predat pe…" className="text-sm" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Anulează</Button>
          <Button
            onClick={() => onSubmit({ category, note: note.trim() || undefined })}
            disabled={submitting || !category}
          >
            {submitting ? 'Se arhivează…' : 'Arhivează'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
