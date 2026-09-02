import { useMemo, useRef, useState, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { ChevronLeft, Check, ChevronsUpDown, X, Clock, History } from 'lucide-react'
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
import { digestApi } from '@/api/digest'
import { profileApi } from '@/api/profile'
import { useAuthStore } from '@/stores/authStore'
import { buildStartSlots, buildDurationOptions, computeReturn } from './leaveSlots'

// Code-defined "Bilet de Invoire" form. Fields live here (not a DB form schema),
// so it deploys with the frontend and is identical in every environment. It
// submits to the internal Invoire endpoint, which stores a form_submission and
// routes it through the approval engine (primary + optional second approver).

const REASONS = ['Personal', 'Medical', 'Familial', 'Oficial', 'Altul']

const localDateStr = (d = new Date()) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const localTimeStr = (d = new Date()) =>
  `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
// Earliest date a Corectie Ore may target: the 1st of the current month
// (current month only). Mirrors the backend guard.
const firstOfCurrentMonthStr = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
}

interface InvoireFormInitial {
  f_bi_leave_date: string
  f_bi_start_time: string
  f_bi_duration_hours: string | number
  f_bi_reason: string
  f_bi_second_approver: string
  f_bi_notes: string
  f_bi_is_correction?: boolean
  f_bi_company?: string
}

export function InvoireForm({ onClose, onSubmitted, submissionId, initial }: {
  onClose: () => void
  onSubmitted: () => void
  submissionId?: number
  initial?: InvoireFormInitial
}) {
  const isEdit = submissionId != null
  const [date, setDate] = useState(() => initial?.f_bi_leave_date || localDateStr())
  const [start, setStart] = useState(() => initial?.f_bi_start_time || '')
  // Number | string: prefill in edit mode carries the original submission's
  // value through untouched (so the resubmitted payload matches what was
  // originally accepted); the Select always writes a number when the user
  // (re)picks a duration. Comparisons below coerce with Number() as needed.
  const [durationHours, setDurationHours] = useState<number | string | null>(() =>
    initial?.f_bi_duration_hours ?? null)
  const [reason, setReason] = useState(() => initial?.f_bi_reason || '')
  // Picked approver ids REPLACE the default direct manager (any one can approve).
  // Empty → the request routes to the org-hierarchy direct manager, as before.
  const [approverIds, setApproverIds] = useState<number[]>(() =>
    String(initial?.f_bi_second_approver || '')
      .split(',').map((s) => Number(s.trim())).filter((n) => Number.isInteger(n) && n > 0))
  const [approverNames, setApproverNames] = useState<Record<number, string>>({})
  const [notes, setNotes] = useState(() => initial?.f_bi_notes || '')
  // Signature/consent were already given on the original submission, so the
  // edit-mode gates start pre-satisfied. Signature itself still comes from
  // the preloaded profile signature (below), not from `initial`.
  const [termsAccepted, setTermsAccepted] = useState(() => isEdit)
  const [signature, setSignature] = useState('')
  const [attempted, setAttempted] = useState(false)

  // Corectie Ore = a backdated bilet for forgotten leave. Permission-gated (matrix
  // hr.leave_permissions.correct, admins always), red, and manager-only. The toggle
  // is hidden entirely for users without the permission.
  const user = useAuthStore((s) => s.user)
  const canCreateCorrection = !!user?.can_access_settings
    || !!user?.permissions?.['hr.leave_permissions.correct']
  const [isCorrection, setIsCorrection] = useState<boolean>(() => !!initial?.f_bi_is_correction)
  const correctionFloor = firstOfCurrentMonthStr()

  // Multi-company: which contract the leave is against. '' → the backend picks the
  // primary (highest norma); the schedule (window/cap/lunch) syncs to the choice.
  const [company, setCompany] = useState<string>(() => initial?.f_bi_company || '')
  const { data: schedRes } = useQuery({
    queryKey: ['leave-schedule', date, company],
    queryFn: () => connecteamApi.getLeaveSchedule(date, company || undefined),
  })
  const sched = schedRes?.data
  const companies = sched?.companies ?? []
  const activeCompany = company || sched?.selected_company || ''
  // Forms-managed content (labels/placeholders/visibility/consent) with coded fallbacks.
  const L = (id: string, fallback: string) => sched?.labels?.[id] || fallback
  const P = (id: string, fallback: string) => sched?.placeholders?.[id] ?? fallback
  // Second approver + notes are standard fields — always shown. A Forms schema that
  // omits them must NOT hide them: the editor auto-generates field ids, so a removed
  // field can't be re-added with the exact id the module looks for (one-way gating
  // that broke prod, where these were absent).
  const showNotes = true
  // A correction always routes to the direct manager only — hide the approver picker.
  const showApprover = !isCorrection
  const termsText = sched?.terms_text || 'Declar că îmi asum responsabilitatea pentru orice eventual eveniment neplăcut care ar putea surveni în legătură cu mine, în această perioadă în care sunt învoit / învoită 🔒'
  // Two separate Time Bank pools shown independently. Personal may go negative;
  // Event is capped — "Ore Libere din Eveniment" can't exceed the event balance.
  const eventReason = sched?.event_hours_reason
  const personalBalance = sched?.time_bank_personal ?? 0
  const eventBalance = sched?.time_bank_event ?? 0
  const hasSplit = typeof sched?.time_bank_event === 'number'
  const eventReasonEnabled = eventBalance >= 0.5
  const fmtHours = (h: number) => (Number.isInteger(h) ? String(h) : h.toFixed(1))
  const durationNum = Number(durationHours) || 0
  // Which pool the selected reason draws from. Lunch ('Pauza de masa') counts for neither.
  const reasonCounts = !!reason && !(sched?.non_counting_reasons ?? []).some(
    (r) => r.trim().toLowerCase() === reason.trim().toLowerCase())
  const isEventReason = !!eventReason && reason === eventReason
  const isPersonalReason = reasonCounts && !isEventReason
  const eventOver = isEventReason && durationNum > eventBalance + 1e-9
  // Lunch ('Pauza de masa') = a per-employee/per-company entitlement: selecting it
  // auto-fills + locks the duration to the Sincron lunch, and is hidden when 0.
  const lunchMin = sched?.lunch_break_minutes ?? 0
  const lunchHours = lunchMin / 60
  const nonCounting = sched?.non_counting_reasons ?? []
  const isLunchReason = !!reason && nonCounting.some((n) => n.trim().toLowerCase() === reason.trim().toLowerCase())
  const startSlots = useMemo(
    () => (sched
      ? buildStartSlots(sched.schedule_start, sched.schedule_end,
          date === localDateStr() && !isCorrection ? localTimeStr() : undefined)
      : []),
    [sched, date, isCorrection])
  const durationOptions = useMemo(
    () => sched && start ? buildDurationOptions(start, sched.schedule_end, sched.day_cap_hours) : [],
    [sched, start])
  // A full-day leave (duration == the day cap) also spans the lunch, so the return
  // adds the employee's lunch break to reflect the real program end (e.g. 17:00).
  const isFullDay = durationNum > 0 && Math.abs(durationNum - (sched?.day_cap_hours ?? 0)) < 1e-9
  const returnTime = start && durationHours
    ? computeReturn(start, Number(durationHours), isFullDay ? (sched?.lunch_break_minutes ?? 0) : 0)
    : ''

  // Default start to first slot; reset duration if it no longer fits. Both
  // guards wait for the schedule-derived options to actually load (non-empty)
  // before resetting — otherwise a prefilled edit-mode value would get wiped
  // out by the very first effect pass, which runs before `sched` resolves.
  useEffect(() => {
    if (startSlots.length && (!start || !startSlots.includes(start))) setStart(startSlots[0])
  }, [startSlots, start])
  useEffect(() => {
    if (!isLunchReason && durationHours && durationOptions.length && !durationOptions.some(o => o.value === Number(durationHours))) setDurationHours(null)
  }, [durationOptions, durationHours, isLunchReason])
  // Pauza de masa: lock the duration to the (selected company's) lunch break.
  useEffect(() => {
    if (isLunchReason && lunchHours > 0 && Number(durationHours) !== lunchHours) setDurationHours(lunchHours)
  }, [isLunchReason, lunchHours, durationHours])

  // Preload the user's saved profile signature.
  const { data: sigRes } = useQuery({ queryKey: ['profile-signature'], queryFn: () => profileApi.getSignature() })
  // Preload the saved profile signature exactly ONCE — otherwise clearing it via
  // "Semnează din nou" would immediately re-populate it (the effect would re-fire
  // because `signature` became empty again), so the canvas never shows.
  const preloadedSig = useRef(false)
  useEffect(() => {
    if (!preloadedSig.current && sigRes?.signature) {
      preloadedSig.current = true
      setSignature(sigRes.signature)
    }
  }, [sigRes])

  const { data: approversRes } = useQuery({
    queryKey: ['leave-approvers'],
    queryFn: () => connecteamApi.getApprovers(),
    staleTime: 10 * 60_000,
  })
  // The direct manager(s) — shown by name when the search box is empty, so you
  // can see the default approver and pick a different one if there are several.
  const approvers = approversRes?.data ?? []

  // Auto-select the direct manager as a named chip on open (create mode only).
  // Edit mode prefills from the saved submission, so leave it untouched. Runs
  // once and only if nothing is picked yet, so a user who clears/changes the
  // chip isn't fought by re-selection.
  const didInitApprover = useRef(false)
  useEffect(() => {
    if (didInitApprover.current || isEdit || !sched) return
    didInitApprover.current = true
    const dm = sched.default_approver
    if (dm?.id && approverIds.length === 0) {
      setApproverIds([dm.id])
      setApproverNames((m) => ({ ...m, [dm.id]: dm.name }))
    }
  }, [sched, isEdit, approverIds.length])

  const [approverOpen, setApproverOpen] = useState(false)
  const [approverSearch, setApproverSearch] = useState('')
  const approverInputRef = useRef<HTMLInputElement>(null)

  // Typing (≥2 chars) searches ALL JARVIS users (not just the manager list);
  // an empty box shows the direct manager(s) from getApprovers.
  const [debouncedApproverSearch, setDebouncedApproverSearch] = useState('')
  useEffect(() => {
    const t = setTimeout(() => setDebouncedApproverSearch(approverSearch), 300)
    return () => clearTimeout(t)
  }, [approverSearch])
  const { data: approverUserRes, isFetching: approverSearching } = useQuery({
    queryKey: ['leave-approver-user-search', debouncedApproverSearch],
    queryFn: () => digestApi.searchUsers(debouncedApproverSearch),
    enabled: debouncedApproverSearch.trim().length >= 2,
    staleTime: 60_000,
  })
  const isApproverSearching = approverSearch.trim().length >= 2
  const approverOptions: { id: number; name: string }[] = isApproverSearching
    ? (approverUserRes?.data ?? []).map((u) => ({ id: u.id, name: u.name }))
    : approvers.map((a) => ({ id: Number(a.id), name: a.name }))
  const nameFor = (id: number) =>
    approverNames[id]
    || approvers.find((a) => Number(a.id) === id)?.name
    || approverOptions.find((o) => o.id === id)?.name
    || `Utilizator #${id}`
  const toggleApprover = (id: number, name: string) => {
    setApproverNames((m) => ({ ...m, [id]: name }))
    setApproverIds((ids) => ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id])
  }
  const approverSummary = approverIds.length === 0
    ? 'Doar managerul direct'
    : approverIds.length === 1
      ? nameFor(approverIds[0])
      : `${approverIds.length} aprobatori`

  // A bilet can't be filed for a day that already passed (create mode only —
  // editing an existing permit must not be blocked by its original past date).
  // A normal bilet can't be backdated; a correction can, but only within the
  // current month.
  const isPastDate = !isEdit && !isCorrection && !!date && date < localDateStr()
  const isBeforeCorrectionFloor = isCorrection && !isEdit && !!date && date < correctionFloor
  const invalid = useMemo(() => ({
    date: !date || isPastDate || isBeforeCorrectionFloor, start: !start,
    duration: !durationHours || eventOver, reason: !reason,
    terms: !termsAccepted, signature: !signature,
  }), [date, isPastDate, isBeforeCorrectionFloor, start, durationHours, eventOver, reason, termsAccepted, signature])

  const submit = useMutation({
    mutationFn: async () => {
      if (signature && signature !== sigRes?.signature) {
        try { await profileApi.saveSignature(signature) } catch { /* non-blocking */ }
      }
      const payload = {
        f_bi_leave_date: date,
        f_bi_start_time: start,
        f_bi_duration_hours: durationHours,
        f_bi_reason: reason,
        // A correction always routes to the direct manager only (empty picker).
        f_bi_second_approver: isCorrection ? '' : approverIds.join(','),
        f_bi_notes: notes,
        f_bi_terms_accepted: termsAccepted,
        f_bi_is_correction: isCorrection,
        // The company contract the leave is against (validated + recorded server-side).
        f_bi_company: activeCompany || undefined,
        signature_image: signature,
      }
      return submissionId
        ? connecteamApi.updateLeavePermit(submissionId, payload)
        : connecteamApi.submitLeavePermit(payload)
    },
    onSuccess: () => {
      toast.success(isEdit ? 'Cererea de învoire a fost actualizată.' : 'Cererea de învoire a fost trimisă spre aprobare.')
      onSubmitted()
      onClose()
    },
    onError: (e: any) => toast.error(e?.response?.data?.error || 'Trimiterea învoirii a eșuat.'),
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
          <h2 className={cn('flex-1 text-center text-sm font-semibold truncate px-2',
            isCorrection && 'text-destructive')}>
            {isCorrection ? 'Corectie Ore' : 'Bilet de Invoire'}
          </h2>
          <div className="w-16" />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-lg px-5 py-6 space-y-5">
          {canCreateCorrection && !isEdit && (
            <div className="grid grid-cols-2 gap-1 rounded-lg border p-1">
              <button type="button" onClick={() => setIsCorrection(false)}
                className={cn('flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition',
                  !isCorrection ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted')}>
                Învoire
              </button>
              <button type="button" onClick={() => setIsCorrection(true)}
                className={cn('flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition',
                  isCorrection ? 'bg-destructive text-destructive-foreground' : 'text-muted-foreground hover:bg-muted')}>
                <History className="h-3.5 w-3.5" /> Corectie Ore
              </button>
            </div>
          )}
          {isCorrection && (
            <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              <History className="mt-0.5 h-4 w-4 shrink-0" />
              <span>Corectie Ore — bilet retroactiv pentru o zi din luna curentă. Se scade din bancă doar după aprobarea managerului direct.</span>
            </div>
          )}
          {companies.length > 1 && (
            <div className="space-y-1">
              <Label>Companie{req}</Label>
              <Select value={activeCompany} onValueChange={setCompany}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Selectați compania" />
                </SelectTrigger>
                <SelectContent>
                  {companies.map((c) => (
                    <SelectItem key={c.company_name} value={c.company_name}>
                      {c.company_name} · {c.schedule_start}–{c.schedule_end} · {fmtHours(c.day_cap_hours)}h
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground px-0.5">Programul, norma și pauza se preiau din contractul companiei alese.</p>
            </div>
          )}
          <div className="space-y-1">
            <Label>{L('f_bi_leave_date', 'Data')}{req}</Label>
            <Input type="date" value={date}
              min={isEdit ? undefined : (isCorrection ? correctionFloor : localDateStr())}
              onChange={(ev) => setDate(ev.target.value)}
              aria-invalid={(attempted && invalid.date) || isPastDate || isBeforeCorrectionFloor ? true : undefined} />
            {isPastDate && (
              <p className="text-xs text-destructive">Nu poți crea un bilet pentru o zi anterioară. Folosește „Corectie Ore".</p>
            )}
            {isBeforeCorrectionFloor && (
              <p className="text-xs text-destructive">Corecția se poate face doar pentru luna curentă.</p>
            )}
          </div>

          {/* Start · Duration · derived return time — all on one inline row.
              The return is computed from start + duration, shown compactly beside
              the controls instead of a full-width row of its own. */}
          <div className="flex items-end gap-3">
            <div className="flex-1 space-y-1">
              <Label>{L('f_bi_start_time', 'Ora de început')}{req}</Label>
              <Select value={start} onValueChange={setStart}>
                <SelectTrigger className="w-full" aria-invalid={attempted && invalid.start ? true : undefined}>
                  <SelectValue placeholder="Selectați ora" />
                </SelectTrigger>
                <SelectContent>
                  {startSlots.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="flex-1 space-y-1">
              <Label>{L('f_bi_hours', 'Durată')}{req}</Label>
              <Select value={durationHours ? String(durationHours) : ''}
                      onValueChange={(v) => setDurationHours(Number(v))} disabled={isLunchReason}>
                <SelectTrigger className="w-full" aria-invalid={(attempted && invalid.duration) || eventOver ? true : undefined}>
                  <SelectValue placeholder="Selectați durata" />
                </SelectTrigger>
                <SelectContent>
                  {durationOptions.map((o) => <SelectItem key={o.value} value={String(o.value)}>{o.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-muted-foreground">Întoarcere</Label>
              <div className="flex h-9 items-center gap-1 whitespace-nowrap px-1 text-sm font-semibold tabular-nums">
                {returnTime ? (
                  <>
                    <Clock className="h-3.5 w-3.5 text-muted-foreground" />
                    {returnTime}
                  </>
                ) : (
                  <span className="font-normal text-muted-foreground">—</span>
                )}
              </div>
            </div>
          </div>
          {sched?.source === 'default' && (
            <p className="-mt-3 text-xs text-muted-foreground px-0.5">Program implicit (fără contract Sincron).</p>
          )}
          {eventOver && (
            <p className="-mt-3 px-0.5 text-xs font-medium text-destructive">
              Nu poți selecta mai mult de {fmtHours(eventBalance)}h din banca de eveniment.
            </p>
          )}
          {isLunchReason && (
            <p className="-mt-3 px-0.5 text-xs text-muted-foreground">
              Durata este pauza de masă ({lunchMin} min) — fixată din contractul companiei.
            </p>
          )}

          <div className="space-y-1">
            <Label>{L('f_bi_reason', 'Motivul')}{req}</Label>
            {hasSplit && (
              <div className="space-y-1.5 rounded-md border bg-muted/40 px-3 py-2 text-sm">
                {/* Personal pool — may go negative */}
                <div className={cn('flex flex-wrap items-center gap-x-2', isPersonalReason && 'font-medium')}>
                  <Clock className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <span className="text-muted-foreground">Sold Personal:</span>
                  <span className={cn('font-semibold', personalBalance < 0 ? 'text-destructive' : 'text-foreground')}>
                    {fmtHours(personalBalance)}h
                  </span>
                  {isPersonalReason && durationNum > 0 && (
                    <>
                      <span className="text-muted-foreground">→ rămas:</span>
                      <span className={cn('font-bold', (personalBalance - durationNum) < 0 ? 'text-destructive' : 'text-foreground')}>
                        {fmtHours(personalBalance - durationNum)}h
                      </span>
                    </>
                  )}
                </div>
                {/* Event pool — capped, never negative */}
                <div className={cn('flex flex-wrap items-center gap-x-2', isEventReason && 'font-medium')}>
                  <History className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <span className="text-muted-foreground">Sold Eveniment:</span>
                  <span className="font-semibold text-foreground">{fmtHours(eventBalance)}h</span>
                  {!eventReasonEnabled && <span className="text-xs text-muted-foreground">(indisponibil)</span>}
                  {isEventReason && durationNum > 0 && (
                    <>
                      <span className="text-muted-foreground">→ rămas:</span>
                      <span className={cn('font-bold', (eventBalance - durationNum) < 0 ? 'text-destructive' : 'text-foreground')}>
                        {fmtHours(eventBalance - durationNum)}h
                      </span>
                    </>
                  )}
                </div>
              </div>
            )}
            <Select value={reason} onValueChange={setReason}>
              <SelectTrigger aria-invalid={attempted && invalid.reason ? true : undefined}>
                <SelectValue placeholder="Selectați motivul" />
              </SelectTrigger>
              <SelectContent>
                {(sched?.reasons?.length ? sched.reasons : REASONS).map((r) => {
                  const isLunch = nonCounting.some((n) => n.trim().toLowerCase() === r.trim().toLowerCase())
                  const disabled = (r === eventReason && !eventReasonEnabled) || (isLunch && lunchMin <= 0)
                  return <SelectItem key={r} value={r} disabled={disabled}>{r}</SelectItem>
                })}
              </SelectContent>
            </Select>
          </div>

          {showApprover && (
          <div className="space-y-1">
            {/* Label is code-owned: the field is now a multi-select, so the stale
                Forms-managed "Al doilea aprobator" label must not override it.
                Required — there is always an approver (the direct manager by
                default, or the picked ones). */}
            <Label>Aprobatori{req}</Label>
            <p className="text-xs text-muted-foreground">
              Managerul tău direct este selectat implicit. Adaugă sau schimbă aprobatorii — cererea le este trimisă tuturor și oricare poate aproba.
            </p>
            <Popover open={approverOpen} onOpenChange={(v) => { setApproverOpen(v); if (v) setTimeout(() => approverInputRef.current?.focus(), 0) }}>
              <PopoverTrigger asChild>
                <Button variant="outline" role="combobox" aria-expanded={approverOpen} className="w-full justify-between font-normal">
                  {approverSummary}
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
                    className={cn('flex w-full items-center rounded-sm px-2 py-1.5 text-sm hover:bg-accent cursor-pointer', approverIds.length === 0 && 'bg-accent')}
                    onClick={() => { setApproverIds([]); setApproverOpen(false); setApproverSearch('') }}>
                    <Check className={cn('mr-2 h-4 w-4', approverIds.length ? 'opacity-0' : 'opacity-100')} />
                    Doar managerul direct
                  </button>
                  {approverOptions.map((a) => (
                    <button type="button" key={a.id}
                      className={cn('flex w-full items-center rounded-sm px-2 py-1.5 text-sm hover:bg-accent cursor-pointer', approverIds.includes(a.id) && 'bg-accent')}
                      onClick={() => toggleApprover(a.id, a.name)}>
                      <Check className={cn('mr-2 h-4 w-4', approverIds.includes(a.id) ? 'opacity-100' : 'opacity-0')} />
                      {a.name}
                    </button>
                  ))}
                  {isApproverSearching && approverSearching && (
                    <p className="px-2 py-2 text-sm text-muted-foreground">Se caută...</p>
                  )}
                  {isApproverSearching && !approverSearching && approverOptions.length === 0 && (
                    <p className="px-2 py-2 text-sm text-muted-foreground">Niciun utilizator găsit</p>
                  )}
                </div>
              </PopoverContent>
            </Popover>
            {approverIds.length > 0 && (
              <div className="flex flex-wrap gap-1.5 pt-1">
                {approverIds.map((id) => (
                  <span key={id} className="inline-flex items-center gap-1 rounded-full bg-secondary px-2.5 py-1 text-xs">
                    {nameFor(id)}
                    <button type="button" className="opacity-60 hover:opacity-100"
                      onClick={() => setApproverIds((ids) => ids.filter((x) => x !== id))} aria-label="Elimină aprobator">
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>
          )}

          {showNotes && (
          <div className="space-y-1">
            <Label>{L('f_bi_notes', 'Detalii suplimentare')}</Label>
            <Textarea value={notes} onChange={(ev) => setNotes(ev.target.value)} rows={3}
              placeholder={P('f_bi_notes', 'Adăugați orice detalii relevante')} />
          </div>
          )}

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
            <span>{termsText}</span>
          </label>

          <Button className="w-full h-12 text-base font-semibold" onClick={handleSubmit} disabled={submit.isPending}>
            {isEdit
              ? (submit.isPending ? 'Se salvează...' : 'Salvează')
              : (submit.isPending ? 'Se trimite...' : 'Trimite spre aprobare')}
          </Button>
        </div>
      </div>
    </div>
  )
}
