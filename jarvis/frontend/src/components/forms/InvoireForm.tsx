import { useMemo, useRef, useState, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { ChevronLeft, Check, ChevronsUpDown } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Checkbox } from '@/components/ui/checkbox'
import SignatureCanvas from '@/components/shared/SignatureCanvas'
import { connecteamApi } from '@/api/connecteam'
import { profileApi } from '@/api/profile'
import { buildStartSlots, buildDurationOptions, computeReturn } from './leaveSlots'

// Code-defined "Bilet de Invoire" form. Fields live here (not a DB form schema),
// so it deploys with the frontend and is identical in every environment. It
// submits to the internal Invoire endpoint, which stores a form_submission and
// routes it through the approval engine (primary + optional second approver).

const REASONS = ['Personal', 'Medical', 'Familial', 'Oficial', 'Altul']

export function InvoireForm({ onClose, onSubmitted }: { onClose: () => void; onSubmitted: () => void }) {
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [start, setStart] = useState('')
  const [durationHours, setDurationHours] = useState<number | null>(null)
  const [reason, setReason] = useState('')
  const [secondApprover, setSecondApprover] = useState('')
  const [notes, setNotes] = useState('')
  const [termsAccepted, setTermsAccepted] = useState(false)
  const [signature, setSignature] = useState('')
  const [attempted, setAttempted] = useState(false)

  const { data: schedRes } = useQuery({
    queryKey: ['leave-schedule', date],
    queryFn: () => connecteamApi.getLeaveSchedule(date),
  })
  const sched = schedRes?.data
  const startSlots = useMemo(() => sched ? buildStartSlots(sched.schedule_start, sched.schedule_end) : [], [sched])
  const durationOptions = useMemo(
    () => sched && start ? buildDurationOptions(start, sched.schedule_end, sched.day_cap_hours) : [],
    [sched, start])
  const returnTime = start && durationHours ? computeReturn(start, durationHours) : ''

  // Default start to first slot; reset duration if it no longer fits.
  useEffect(() => {
    if (startSlots.length && !start) setStart(startSlots[0])
  }, [startSlots, start])
  useEffect(() => {
    if (durationHours && !durationOptions.some(o => o.value === durationHours)) setDurationHours(null)
  }, [durationOptions, durationHours])

  // Preload the user's saved profile signature.
  const { data: sigRes } = useQuery({ queryKey: ['profile-signature'], queryFn: () => profileApi.getSignature() })
  useEffect(() => {
    if (sigRes?.signature && !signature) setSignature(sigRes.signature)
  }, [sigRes, signature])

  const { data: approversRes } = useQuery({
    queryKey: ['leave-approvers'],
    queryFn: () => connecteamApi.getApprovers(),
    staleTime: 10 * 60_000,
  })
  const approvers = approversRes?.data ?? []

  const [approverOpen, setApproverOpen] = useState(false)
  const [approverSearch, setApproverSearch] = useState('')
  const approverInputRef = useRef<HTMLInputElement>(null)
  const selectedApproverName = secondApprover
    ? (approvers.find((a) => String(a.id) === secondApprover)?.name ?? 'Doar managerul direct')
    : 'Doar managerul direct'
  const filteredApprovers = approverSearch.trim()
    ? approvers.filter((a) => a.name.toLowerCase().includes(approverSearch.toLowerCase()))
    : approvers

  const invalid = useMemo(() => ({
    date: !date, start: !start, duration: !durationHours, reason: !reason,
    terms: !termsAccepted, signature: !signature,
  }), [date, start, durationHours, reason, termsAccepted, signature])

  const submit = useMutation({
    mutationFn: async () => {
      if (signature && signature !== sigRes?.signature) {
        try { await profileApi.saveSignature(signature) } catch { /* non-blocking */ }
      }
      return connecteamApi.submitLeavePermit({
        f_bi_leave_date: date,
        f_bi_start_time: start,
        f_bi_duration_hours: durationHours,
        f_bi_reason: reason,
        f_bi_second_approver: secondApprover,
        f_bi_notes: notes,
        f_bi_terms_accepted: termsAccepted,
        signature_image: signature,
      })
    },
    onSuccess: () => {
      toast.success('Cererea de învoire a fost trimisă spre aprobare.')
      onSubmitted()
      onClose()
    },
    onError: () => toast.error('Trimiterea învoirii a eșuat.'),
  })

  const handleSubmit = () => {
    setAttempted(true)
    if (Object.values(invalid).some(Boolean)) return
    submit.mutate()
  }

  const req = <span className="text-destructive ml-0.5">*</span>

  return (
    <div className="fixed inset-0 z-50 bg-background flex flex-col animate-in slide-in-from-right duration-200">
      <div className="shrink-0 border-b bg-background/95 backdrop-blur">
        <div className="flex items-center h-12 px-4">
          <Button variant="ghost" size="sm" className="h-8 gap-1.5 text-xs" onClick={onClose}>
            <ChevronLeft className="h-4 w-4" /> Înapoi
          </Button>
          <h2 className="flex-1 text-center text-sm font-semibold truncate px-2">Bilet de Invoire</h2>
          <div className="w-16" />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-lg px-5 py-6 space-y-5">
          <div className="space-y-1">
            <Label>Data{req}</Label>
            <Input type="date" value={date} onChange={(ev) => setDate(ev.target.value)}
              aria-invalid={attempted && invalid.date ? true : undefined} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Ora de început{req}</Label>
              <Select value={start} onValueChange={setStart}>
                <SelectTrigger aria-invalid={attempted && invalid.start ? true : undefined}>
                  <SelectValue placeholder="Selectați ora" />
                </SelectTrigger>
                <SelectContent>
                  {startSlots.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Durată{req}</Label>
              <Select value={durationHours ? String(durationHours) : ''}
                      onValueChange={(v) => setDurationHours(Number(v))}>
                <SelectTrigger aria-invalid={attempted && invalid.duration ? true : undefined}>
                  <SelectValue placeholder="Selectați durata" />
                </SelectTrigger>
                <SelectContent>
                  {durationOptions.map((o) => <SelectItem key={o.value} value={String(o.value)}>{o.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1">
            <Label>Ora de întoarcere</Label>
            <Input readOnly tabIndex={-1} value={returnTime} placeholder="—"
              className="bg-muted/50 text-muted-foreground cursor-default" />
            {sched?.source === 'default' && (
              <p className="text-xs text-muted-foreground">Program implicit (fără contract Sincron).</p>
            )}
          </div>

          <div className="space-y-1">
            <Label>Motivul{req}</Label>
            <Select value={reason} onValueChange={setReason}>
              <SelectTrigger aria-invalid={attempted && invalid.reason ? true : undefined}>
                <SelectValue placeholder="Selectați motivul" />
              </SelectTrigger>
              <SelectContent>
                {REASONS.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label>Al doilea aprobator (opțional)</Label>
            <p className="text-xs text-muted-foreground">Oricare dintre aprobatori poate aproba.</p>
            <Popover open={approverOpen} onOpenChange={(v) => { setApproverOpen(v); if (v) setTimeout(() => approverInputRef.current?.focus(), 0) }}>
              <PopoverTrigger asChild>
                <Button variant="outline" role="combobox" aria-expanded={approverOpen} className="w-full justify-between font-normal">
                  {selectedApproverName}
                  <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
                <div className="p-2 border-b">
                  <Input ref={approverInputRef} placeholder="Caută utilizator..." value={approverSearch}
                    onChange={(ev) => setApproverSearch(ev.target.value)} className="h-8" />
                </div>
                <div className="max-h-60 overflow-y-auto p-1">
                  <button type="button"
                    className={cn('flex w-full items-center rounded-sm px-2 py-1.5 text-sm hover:bg-accent cursor-pointer', !secondApprover && 'bg-accent')}
                    onClick={() => { setSecondApprover(''); setApproverOpen(false); setApproverSearch('') }}>
                    <Check className={cn('mr-2 h-4 w-4', secondApprover ? 'opacity-0' : 'opacity-100')} />
                    Doar managerul direct
                  </button>
                  {filteredApprovers.map((a) => (
                    <button type="button" key={a.id}
                      className={cn('flex w-full items-center rounded-sm px-2 py-1.5 text-sm hover:bg-accent cursor-pointer', secondApprover === String(a.id) && 'bg-accent')}
                      onClick={() => { setSecondApprover(String(a.id)); setApproverOpen(false); setApproverSearch('') }}>
                      <Check className={cn('mr-2 h-4 w-4', secondApprover === String(a.id) ? 'opacity-100' : 'opacity-0')} />
                      {a.name}
                    </button>
                  ))}
                  {filteredApprovers.length === 0 && (
                    <p className="px-2 py-2 text-sm text-muted-foreground">Niciun rezultat</p>
                  )}
                </div>
              </PopoverContent>
            </Popover>
          </div>

          <div className="space-y-1">
            <Label>Detalii suplimentare</Label>
            <Textarea value={notes} onChange={(ev) => setNotes(ev.target.value)} rows={3}
              placeholder="Adăugați orice detalii relevante" />
          </div>

          <div className="space-y-2">
            <Label>Semnătură{req}</Label>
            {signature
              ? (<div className="rounded border p-2">
                   <img src={signature} alt="semnătură" className="h-24 object-contain" />
                   <Button variant="ghost" size="sm" className="mt-1 text-xs"
                     onClick={() => setSignature('')}>Semnează din nou</Button>
                 </div>)
              : (<SignatureCanvas onSave={setSignature} saveLabel="Confirmă semnătura" height={160} />)}
            {attempted && invalid.signature && <p className="text-xs text-destructive">Semnătura este obligatorie.</p>}
          </div>

          <label className="flex items-start gap-2 text-sm">
            <Checkbox className="mt-0.5" checked={termsAccepted}
              onCheckedChange={(v) => setTermsAccepted(!!v)}
              aria-invalid={attempted && invalid.terms ? true : undefined} />
            <span>Declar că îmi asum responsabilitatea pentru orice eventual eveniment neplăcut care ar putea surveni în legătură cu mine, în această perioadă în care sunt învoit / învoită 🔒</span>
          </label>

          <Button className="w-full h-12 text-base font-semibold" onClick={handleSubmit} disabled={submit.isPending}>
            {submit.isPending ? 'Se trimite...' : 'Trimite spre aprobare'}
          </Button>
        </div>
      </div>
    </div>
  )
}
