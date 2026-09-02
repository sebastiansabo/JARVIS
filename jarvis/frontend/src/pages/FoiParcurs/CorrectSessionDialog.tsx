import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ImagePlus, Loader2, X } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { FoiContract } from '@/types/foiParcurs'
import { foiParcursApi } from '@/api/foiParcurs'
import { fileToCompressedDataUrl } from '@/lib/imageCompress'
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
  // Client identity recorded on the foaie — only sent for client-facing TD
  // sessions, never internal driving logs. An absent driver_license_photo means
  // "leave the stored photo untouched"; an empty string clears the field.
  client_name?: string
  client_phone?: string | null
  driver_license_number?: string | null
  driver_license_expiry?: string | null
  driver_license_photo?: string | null
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

  // Client identity recorded on THIS foaie — editable only for client-facing
  // sessions (an internal driving log has no client). Text fields prefill from
  // the list row; the licence photo isn't in the list payload, so it's hydrated
  // from the detail endpoint below.
  const isClientEditable = !session.is_internal
  const [clientName, setClientName] = useState((session.client_name ?? '').trim())
  const [clientPhone, setClientPhone] = useState((session.client_phone ?? '').trim())
  const [licenseNumber, setLicenseNumber] = useState((session.driver_license_number ?? '').trim())
  const [licenseExpiry, setLicenseExpiry] = useState((session.driver_license_expiry ?? '').slice(0, 10))
  const [licensePhoto, setLicensePhoto] = useState<string | null>(session.driver_license_photo ?? null)
  const [photoBusy, setPhotoBusy] = useState(false)
  // Marks the photo as user-edited so (a) the detail hydrate never overwrites a
  // fresh upload and (b) submit only sends the photo when it actually changed —
  // re-posting a ~155 kB data URL on every KM fix would be wasteful.
  const photoTouched = useRef(false)

  // The list row omits driver_license_photo (large data URL); fetch the detail
  // to show/replace the current photo. Only for editable client sessions.
  const { data: detail } = useQuery({
    queryKey: ['fp-contract', session.id],
    queryFn: () => foiParcursApi.getContract(session.id),
    enabled: isClientEditable,
  })
  useEffect(() => {
    const p = detail?.contract?.driver_license_photo
    if (p && !photoTouched.current) setLicensePhoto(p)
  }, [detail])

  const handleLicenseFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setPhotoBusy(true)
    const compressed = await fileToCompressedDataUrl(file)
    setPhotoBusy(false)
    if (compressed) { photoTouched.current = true; setLicensePhoto(compressed) }
  }

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
      ...(isClientEditable ? {
        client_name: clientName.trim(),
        client_phone: clientPhone.trim() || null,
        driver_license_number: licenseNumber.trim() || null,
        driver_license_expiry: licenseExpiry.trim() || null,
        // Omit the photo unless the user changed it → the backend keeps the
        // stored one; an explicit clear sends null.
        ...(photoTouched.current ? { driver_license_photo: licensePhoto || null } : {}),
      } : {}),
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

        {isClientEditable && (
          <div className="space-y-2.5 rounded-md border bg-muted/40 p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Client / permis (pe această foaie)
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs">Client</Label>
                <Input value={clientName} onChange={(e) => setClientName(e.target.value)} placeholder="Nume client" className="text-sm" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Telefon</Label>
                <Input value={clientPhone} onChange={(e) => setClientPhone(e.target.value)} placeholder="07..." inputMode="tel" className="text-sm" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Serie/nr permis</Label>
                <Input value={licenseNumber} onChange={(e) => setLicenseNumber(e.target.value)} placeholder="Serie/număr" className="text-sm" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Valabilitate</Label>
                <Input type="date" value={licenseExpiry} onChange={(e) => setLicenseExpiry(e.target.value)} className="text-sm" />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Poză permis</Label>
              {licensePhoto ? (
                <div className="flex items-center gap-3">
                  <img src={licensePhoto} alt="Permis de conducere" className="h-16 w-28 rounded-md object-cover border" />
                  <label className="cursor-pointer text-xs font-medium text-primary hover:underline">
                    Schimbă
                    <input type="file" accept="image/*" className="hidden" onChange={handleLicenseFile} />
                  </label>
                  <Button
                    type="button" variant="ghost" size="sm" className="text-destructive"
                    onClick={() => { photoTouched.current = true; setLicensePhoto(null) }}
                  >
                    <X className="h-3.5 w-3.5 mr-1" />Șterge
                  </Button>
                </div>
              ) : (
                <label className="flex h-16 w-full cursor-pointer flex-col items-center justify-center gap-1 rounded-md border-2 border-dashed text-muted-foreground hover:bg-accent transition-colors">
                  {photoBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ImagePlus className="h-4 w-4" />}
                  <span className="text-xs font-medium">Adaugă poza permisului</span>
                  <input type="file" accept="image/*" className="hidden" onChange={handleLicenseFile} />
                </label>
              )}
            </div>
          </div>
        )}

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
