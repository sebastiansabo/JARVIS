import { useMemo, useRef, useState } from 'react'
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
import { connecteamApi } from '@/api/connecteam'
import { fmtDuration, durationLinkError, type DurationLink } from './FormRenderer'

// Code-defined "Bilet de Invoire" form. Fields live here (not a DB form schema),
// so it deploys with the frontend and is identical in every environment. It
// submits to the internal Invoire endpoint, which stores a form_submission and
// routes it through the approval engine (primary + optional second approver).

const REASONS = ['Personal', 'Medical', 'Familial', 'Oficial', 'Altul']
const DUR_LINK: DurationLink = { hours: 'h', start: 's', end: 'e' }

function parseHM(v: string): number | null {
  const m = v.match(/^(\d{1,2}):(\d{1,2})$/)
  if (!m) return null
  const h = +m[1], mi = +m[2]
  return h > 23 || mi > 59 ? null : h * 60 + mi
}

function toHM(mins: number): string {
  const t = Math.max(0, Math.min(1439, Math.round(mins)))
  return `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`
}

function nowHM(): string {
  const d = new Date()
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

export function InvoireForm({ onClose, onSubmitted }: { onClose: () => void; onSubmitted: () => void }) {
  const start0 = nowHM()
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [start, setStart] = useState(start0)
  const [end, setEnd] = useState(() => toHM((parseHM(start0) ?? 0) + 60))
  const [reason, setReason] = useState('')
  const [secondApprover, setSecondApprover] = useState('')
  const [notes, setNotes] = useState('')
  const [attempted, setAttempted] = useState(false)
  const [endTouched, setEndTouched] = useState(false)

  // Default to a 1-hour interval: the end follows the start (+1h) until the user
  // edits the end time manually.
  const changeStart = (v: string) => {
    setStart(v)
    if (!endTouched) {
      const m = parseHM(v)
      if (m !== null) setEnd(toHM(m + 60))
    }
  }
  const changeEnd = (v: string) => { setEnd(v); setEndTouched(true) }

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

  const s = parseHM(start), e = parseHM(end)
  const durationStr = s !== null && e !== null && e > s ? fmtDuration(e - s) : ''
  const intervalError = durationLinkError(DUR_LINK, { s: start, e: end })

  const invalid = useMemo(() => ({
    date: !date,
    start: !start,
    end: !end || !!intervalError,
    reason: !reason,
  }), [date, start, end, reason, intervalError])

  const submit = useMutation({
    mutationFn: () => connecteamApi.submitLeavePermit({
      f_bi_leave_date: date,
      f_bi_start_time: start,
      f_bi_end_time: end,
      f_bi_reason: reason,
      f_bi_second_approver: secondApprover,
      f_bi_notes: notes,
    }),
    onSuccess: () => {
      toast.success('Cererea de învoire a fost trimisă spre aprobare.')
      onSubmitted()
      onClose()
    },
    onError: () => toast.error('Trimiterea învoirii a eșuat.'),
  })

  const handleSubmit = () => {
    setAttempted(true)
    if (invalid.date || invalid.start || invalid.end || invalid.reason) return
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
              <Input type="time" value={start} onChange={(ev) => changeStart(ev.target.value)}
                aria-invalid={attempted && invalid.start ? true : undefined} />
            </div>
            <div className="space-y-1">
              <Label>Ora de sfârșit{req}</Label>
              <Input type="time" value={end} onChange={(ev) => changeEnd(ev.target.value)}
                aria-invalid={(attempted && invalid.end) || !!intervalError ? true : undefined} />
            </div>
          </div>
          {intervalError && <p className="text-xs text-destructive -mt-2">{intervalError}</p>}

          <div className="space-y-1">
            <Label>Durată</Label>
            <p className="text-xs text-muted-foreground">Se calculează automat din interval.</p>
            <Input readOnly tabIndex={-1} value={durationStr} placeholder="—"
              className="bg-muted/50 text-muted-foreground cursor-default" />
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

          <Button className="w-full h-12 text-base font-semibold" onClick={handleSubmit} disabled={submit.isPending}>
            {submit.isPending ? 'Se trimite...' : 'Trimite spre aprobare'}
          </Button>
        </div>
      </div>
    </div>
  )
}
