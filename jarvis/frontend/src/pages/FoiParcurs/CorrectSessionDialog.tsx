import { useMemo, useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { FoiContract } from '@/types/foiParcurs'
import { sessionStatus } from './sessionStatus'
import { useUsersDirectory } from './useUsersDirectory'

// datetime-local wants 'YYYY-MM-DDTHH:MM'; strip seconds/timezone off the stored ISO.
const toLocalInput = (iso?: string | null) => (iso ? iso.slice(0, 16) : '')

export interface CorrectionPayload {
  departure_datetime: string | null
  return_datetime: string | null
  km_start: number | null
  km_end: number | null
  advisor_name: string
}

export interface CorrectionState {
  departure: string
  ret: string
  kmStart: string
  kmEnd: string
}

// Pure validation for the correction form. IMPORTANT: a blank KM field is never
// coerced to 0 — that would silently zero the odometer this tool protects.
// km_start is always required; km_end is required only for a finalized session
// (`kmEndRequired`) — an in-progress session hasn't returned yet, so its final
// odometer is legitimately unknown. A provided km_end is still validated.
export function correctionErrors(st: CorrectionState, kmEndRequired = true): { km: string | null; date: string | null } {
  const ksBlank = st.kmStart.trim() === ''
  const keBlank = st.kmEnd.trim() === ''
  const ks = Number(st.kmStart)
  const ke = Number(st.kmEnd)
  let km: string | null = null
  if (ksBlank) {
    km = 'KM start este obligatoriu'
  } else if (keBlank && kmEndRequired) {
    km = 'KM final este obligatoriu'
  } else if (!Number.isFinite(ks) || (!keBlank && !Number.isFinite(ke))) {
    km = 'KM trebuie să fie numere'
  } else if (!keBlank && ke < ks) {
    km = `KM final (${ke}) nu poate fi mai mic decât KM start (${ks})`
  }
  const date = st.departure && st.ret && st.ret < st.departure
    ? 'Data retur nu poate fi înaintea plecării'
    : null
  return { km, date }
}

// Admin-only modal to correct a session's drive date(s), odometer readings and
// consilier — the fix for date↔odometer anomalies and a mis-assigned advisor.
// Editing the odometer re-sorts the car's rows and re-computes gaps on save.
// For an in-progress session KM final is optional (the car hasn't returned).
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
  const [advisorName, setAdvisorName] = useState((session.advisor_name ?? '').trim())

  // Consilier options: the active users of the session's company (falling back
  // to all active users if the company name doesn't match any), always
  // including the current advisor so a legacy/free-typed name isn't lost.
  const { users } = useUsersDirectory()
  const advisorOptions = useMemo(() => {
    const active = users.filter((u) => u.is_active)
    const scoped = session.company_name ? active.filter((u) => u.company === session.company_name) : active
    const names = new Set((scoped.length ? scoped : active).map((u) => (u.name || '').trim()).filter(Boolean))
    const current = (session.advisor_name ?? '').trim()
    if (current) names.add(current)
    return Array.from(names).sort((a, b) => a.localeCompare(b))
  }, [users, session.company_name, session.advisor_name])

  // Final odometer is only mandatory once the session is finalized.
  const kmEndRequired = sessionStatus(session).key === 'finalizat'
  const errs = correctionErrors({ departure, ret, kmStart, kmEnd }, kmEndRequired)
  const canSave = !errs.km && !errs.date && advisorName.trim() !== '' && !submitting

  const submit = () => {
    if (!canSave) return
    onSubmit({
      departure_datetime: departure || null,
      return_datetime: ret || null,
      km_start: kmStart.trim() === '' ? null : Number(kmStart),
      km_end: kmEnd.trim() === '' ? null : Number(kmEnd),
      advisor_name: advisorName.trim(),
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

        <div className="space-y-1.5 pt-1">
          <Label className="text-xs">Consilier</Label>
          <Select value={advisorName} onValueChange={setAdvisorName}>
            <SelectTrigger className="text-sm"><SelectValue placeholder="Alege consilier" /></SelectTrigger>
            <SelectContent>
              {advisorOptions.map((n) => <SelectItem key={n} value={n}>{n}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

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
            <Label className="text-xs">
              KM final {!kmEndRequired && <span className="font-normal text-muted-foreground">(opțional)</span>}
            </Label>
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
