import { useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { LOCKOUT_LABELS, type FpVehicle } from '@/types/foiParcurs'

type Cat = 'service' | 'damage' | 'paperwork' | 'other'

export default function LockVehicleDialog({ vehicle, onClose, onSubmit, submitting }: {
  vehicle: FpVehicle
  onClose: () => void
  onSubmit: (data: { category: Cat; note?: string; until?: string | null }) => void
  submitting: boolean
}) {
  const [category, setCategory] = useState<Cat>('service')
  const [note, setNote] = useState('')
  const [until, setUntil] = useState('')
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
            <Select value={category} onValueChange={(v) => setCategory(v as Cat)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {(Object.keys(LOCKOUT_LABELS) as Cat[]).map((k) => (
                  <SelectItem key={k} value={k}>{LOCKOUT_LABELS[k]}</SelectItem>
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
          <Button onClick={() => onSubmit({ category, note: note.trim() || undefined, until: until || null })} disabled={submitting}>
            {submitting ? 'Se blochează…' : 'Blochează'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
