import { useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import type { FoiContract } from '@/types/foiParcurs'

// datetime-local wants 'YYYY-MM-DDTHH:MM'; strip seconds/timezone off the stored ISO.
const toLocalInput = (iso?: string | null) => (iso ? iso.slice(0, 16) : '')

export interface CorrectionPayload {
  departure_datetime: string | null
  return_datetime: string | null
  km_start: number
  km_end: number
}

export interface CorrectionState {
  departure: string
  ret: string
  kmStart: string
  kmEnd: string
}

// Pure validation for the correction form. IMPORTANT: a blank KM field is
// invalid (required) — never coerce '' to 0, which would silently zero the
// odometer this tool exists to protect.
export function correctionErrors(st: CorrectionState): { km: string | null; date: string | null } {
  const ks = Number(st.kmStart)
  const ke = Number(st.kmEnd)
  let km: string | null = null
  if (st.kmStart.trim() === '' || st.kmEnd.trim() === '') {
    km = 'KM start și KM final sunt obligatorii'
  } else if (!Number.isFinite(ks) || !Number.isFinite(ke)) {
    km = 'KM trebuie să fie numere'
  } else if (ke < ks) {
    km = `KM final (${ke}) nu poate fi mai mic decât KM start (${ks})`
  }
  const date = st.departure && st.ret && st.ret < st.departure
    ? 'Data retur nu poate fi înaintea plecării'
    : null
  return { km, date }
}

// Admin-only modal to correct a session's drive date(s) and odometer readings —
// the fix for date↔odometer anomalies (wrong date / overlapping km). Editing the
// odometer re-sorts the car's rows and re-computes gaps on save.
export default function CorrectSessionDialog({ session, onClose, onSubmit, submitting }: {
  session: FoiContract
  onClose: () => void
  onSubmit: (data: CorrectionPayload) => void
  submitting: boolean
}) {
  const [departure, setDeparture] = useState(toLocalInput(session.departure_datetime || session.created_at))
  const [ret, setRet] = useState(toLocalInput(session.return_datetime))
  const [kmStart, setKmStart] = useState(String(session.km_start ?? ''))
  const [kmEnd, setKmEnd] = useState(String(session.km_end ?? ''))

  const errs = correctionErrors({ departure, ret, kmStart, kmEnd })
  const canSave = !errs.km && !errs.date && !submitting

  const submit = () => {
    if (!canSave) return
    onSubmit({
      departure_datetime: departure || null,
      return_datetime: ret || null,
      km_start: Number(kmStart),
      km_end: Number(kmEnd),
    })
  }

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Corectează sesiunea</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          {session.client_name || session.advisor_name || '—'} · KM {session.km_start} – {session.km_end}
        </p>

        <div className="grid grid-cols-2 gap-3 pt-1">
          <div className="space-y-1.5">
            <Label className="text-xs">Data plecare</Label>
            <Input type="datetime-local" value={departure} onChange={(e) => setDeparture(e.target.value)} className="text-sm" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Data retur</Label>
            <Input type="datetime-local" value={ret} onChange={(e) => setRet(e.target.value)} className="text-sm" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">KM start</Label>
            <Input type="number" value={kmStart} onChange={(e) => setKmStart(e.target.value)} className="text-sm" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">KM final</Label>
            <Input type="number" value={kmEnd} onChange={(e) => setKmEnd(e.target.value)} className="text-sm" />
          </div>
        </div>

        {(errs.km || errs.date) && (
          <p className="text-xs text-red-600 dark:text-red-400">{errs.km || errs.date}</p>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Anulează</Button>
          <Button onClick={submit} disabled={!canSave}>{submitting ? 'Se salvează…' : 'Salvează'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
