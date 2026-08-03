import { useEffect, useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { X } from 'lucide-react'
import { foiParcursApi } from '@/api/foiParcurs'
import type { FpVehicle } from '@/types/foiParcurs'

const STATE_LABEL: Record<string, string> = {
  active: 'Activ', upcoming: 'Programat', past: 'Trecut', cancelled: 'Anulat',
}

export default function ScheduleBlockDialog({ vehicle, onClose }: {
  vehicle: FpVehicle
  onClose: () => void
}) {
  const qc = useQueryClient()
  const { data: reasonsData } = useQuery({
    queryKey: ['fp-lockout-reasons', 'active'],
    queryFn: () => foiParcursApi.getLockoutReasons(true),
    staleTime: 60_000,
  })
  const reasons = reasonsData?.reasons ?? []
  const { data: blocksData, refetch: refetchBlocks } = useQuery({
    queryKey: ['fp-scheduled-blocks', vehicle.id],
    queryFn: () => foiParcursApi.getScheduledBlocks(vehicle.id),
  })
  const blocks = (blocksData?.blocks ?? []).filter((b) => b.state !== 'cancelled')

  const [category, setCategory] = useState('')
  const [note, setNote] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [error, setError] = useState('')

  useEffect(() => { if (!category && reasons.length) setCategory(reasons[0].slug) }, [reasons]) // eslint-disable-line react-hooks/exhaustive-deps

  const datesValid = startDate && endDate && endDate >= startDate
  // Live overlap check across the whole window (reuses the conflicts endpoint).
  const { data: conflictData } = useQuery({
    queryKey: ['fp-conflicts', vehicle.vin, startDate, endDate],
    queryFn: () => foiParcursApi.getVehicleConflicts(vehicle.vin, { from: startDate, to: `${endDate} 23:59:59` }),
    enabled: !!datesValid,
  })
  const conflicts = useMemo(() => (datesValid ? conflictData?.conflicts ?? [] : []), [conflictData, datesValid])

  const reasonLabel = (slug?: string | null) => reasons.find((r) => r.slug === slug)?.label || slug || '—'

  const createMut = useMutation({
    mutationFn: () => foiParcursApi.createScheduledBlock(vehicle.id, {
      category, start_date: startDate, end_date: endDate,
      note: note.trim() || undefined, allow_conflicts: conflicts.length > 0,
    }),
    onSuccess: (res) => {
      if (!res.success) { setError(res.error || 'Eroare la programare'); return }
      setError(''); setNote(''); setStartDate(''); setEndDate('')
      refetchBlocks(); qc.invalidateQueries({ queryKey: ['fp-vehicles'] })
    },
  })
  const cancelMut = useMutation({
    mutationFn: (blockId: number) => foiParcursApi.cancelScheduledBlock(vehicle.id, blockId),
    onSuccess: () => { refetchBlocks(); qc.invalidateQueries({ queryKey: ['fp-vehicles'] }) },
  })

  const submit = () => {
    if (!datesValid) { setError('Alege un interval valid'); return }
    if (!category) { setError('Alege un motiv'); return }
    createMut.mutate()
  }

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Programează blocare</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            {[vehicle.mark, vehicle.model].filter(Boolean).join(' ')} — {vehicle.registration_number || vehicle.vin}
          </p>

          {blocks.length > 0 && (
            <div className="rounded border p-2 space-y-1">
              <Label className="text-xs">Blocări existente</Label>
              {blocks.map((b) => (
                <div key={b.id} className="flex items-center justify-between text-xs">
                  <span>
                    <span className="font-medium">{STATE_LABEL[b.state]}</span>{' '}
                    {b.start_date} → {b.end_date} · {reasonLabel(b.category)}
                  </span>
                  <Button variant="ghost" size="sm" className="h-6 w-6 p-0"
                    title="Anulează blocarea" onClick={() => cancelMut.mutate(b.id)}
                    disabled={cancelMut.isPending}>
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
            </div>
          )}

          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5">
              <Label className="text-xs" htmlFor="fp-block-start">De la</Label>
              <Input id="fp-block-start" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs" htmlFor="fp-block-end">Până la</Label>
              <Input id="fp-block-end" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="text-sm" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Motiv</Label>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger><SelectValue placeholder="Alege motivul" /></SelectTrigger>
              <SelectContent>
                {reasons.map((r) => (<SelectItem key={r.slug} value={r.slug}>{r.label}</SelectItem>))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Detalii (opțional)</Label>
            <Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} className="text-sm" />
          </div>

          {conflicts.length > 0 && (
            <div className="rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-800 dark:bg-amber-950/30 dark:text-amber-300">
              <p className="font-semibold">Sesiuni care se suprapun ({conflicts.length}):</p>
              <ul className="mt-1 list-disc pl-4">
                {conflicts.map((c) => (
                  <li key={c.id}>{c.status} · {c.client_name || '—'} · {c.departure_datetime}</li>
                ))}
              </ul>
            </div>
          )}
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Închide</Button>
          <Button onClick={submit} disabled={createMut.isPending || !datesValid || !category}>
            {createMut.isPending ? 'Se programează…'
              : conflicts.length > 0 ? 'Programează oricum' : 'Programează'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
