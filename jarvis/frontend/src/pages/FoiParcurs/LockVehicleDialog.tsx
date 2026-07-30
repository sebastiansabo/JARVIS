import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { foiParcursApi } from '@/api/foiParcurs'
import type { FpVehicle } from '@/types/foiParcurs'

export default function LockVehicleDialog({ vehicle, onClose, onSubmit, submitting }: {
  vehicle: FpVehicle
  onClose: () => void
  onSubmit: (data: { category: string; note?: string; until?: string | null }) => void
  submitting: boolean
}) {
  // Reasons are configurable (FP Settings → Motive blocare); show only active ones.
  const { data: reasonsData } = useQuery({
    queryKey: ['fp-lockout-reasons', 'active'],
    queryFn: () => foiParcursApi.getLockoutReasons(true),
    staleTime: 60_000,
  })
  const reasons = reasonsData?.reasons ?? []
  const [category, setCategory] = useState('')
  const [note, setNote] = useState('')
  const [until, setUntil] = useState('')

  // Default to the first active reason once loaded.
  useEffect(() => {
    if (!category && reasons.length) setCategory(reasons[0].slug)
  }, [reasons]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Blochează în parcul auto</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            {[vehicle.mark, vehicle.model].filter(Boolean).join(' ')} — {vehicle.registration_number || vehicle.vin}
          </p>
          <div className="space-y-1.5">
            <Label className="text-xs">Motiv</Label>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger><SelectValue placeholder="Alege motivul" /></SelectTrigger>
              <SelectContent>
                {reasons.map((r) => (
                  <SelectItem key={r.slug} value={r.slug}>{r.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Detalii (opțional)</Label>
            <Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2}
              placeholder="Ex: bară față avariată, RCA expirat…" className="text-sm" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Blocat până la (opțional)</Label>
            <Input type="date" value={until} onChange={(e) => setUntil(e.target.value)} className="text-sm" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Anulează</Button>
          <Button
            onClick={() => onSubmit({ category, note: note.trim() || undefined, until: until || null })}
            disabled={submitting || !category}
          >
            {submitting ? 'Se blochează…' : 'Blochează'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
