import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { CheckCircle2, ShieldCheck } from 'lucide-react'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { cn } from '@/lib/utils'
import { ApiError } from '@/api/client'
import { pulseApi } from '@/api/happy'
import type { HappyPulse, HappyPulseAnswers, HappyPulseQuestion } from '@/types/happy'

const LIKERT_SCALE = [1, 2, 3, 4, 5]
const ENPS_SCALE = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

interface ScaleQuestionProps {
  values: number[]
  selected: number | undefined
  onSelect: (v: number) => void
  minLabel?: string
  maxLabel?: string
}

function ScaleQuestion({ values, selected, onSelect, minLabel, maxLabel }: ScaleQuestionProps) {
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap gap-1.5">
        {values.map((v) => (
          <button
            key={v}
            type="button"
            aria-pressed={selected === v}
            onClick={() => onSelect(v)}
            className={cn(
              'h-9 min-w-9 flex-1 rounded-md border text-sm font-medium transition-colors',
              selected === v
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-border hover:bg-accent/50',
            )}
          >
            {v}
          </button>
        ))}
      </div>
      {(minLabel || maxLabel) && (
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>{minLabel}</span>
          <span>{maxLabel}</span>
        </div>
      )}
    </div>
  )
}

interface PulseFormProps {
  pulse: HappyPulse
  questions: HappyPulseQuestion[]
  anonymityNotice: string
  TitleWrapper: React.ComponentType<{ className?: string; children?: React.ReactNode }>
  onClose: () => void
}

function PulseForm({ pulse, questions, anonymityNotice, TitleWrapper, onClose }: PulseFormProps) {
  const queryClient = useQueryClient()
  const [answers, setAnswers] = useState<HappyPulseAnswers>({})
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)

  const setAnswer = (position: number, value: number | string) => {
    setAnswers((prev) => ({ ...prev, [`q${position}`]: value }))
  }

  // Every non-optional question (all but `open`) must be answered.
  const allRequiredAnswered = questions.every(
    (q) => q.qtype === 'open' || answers[`q${q.position}`] !== undefined,
  )
  const canSubmit = allRequiredAnswered && !submitting

  const handleSubmit = async () => {
    if (!canSubmit) return
    setSubmitting(true)
    try {
      await pulseApi.respond(pulse.id, answers)
      toast.success('Mulțumim pentru răspuns.')
      queryClient.invalidateQueries({ queryKey: ['happy', 'pulse'] })
      setDone(true)
    } catch (err) {
      const code = err instanceof ApiError ? (err.data as { code?: string } | null)?.code : undefined
      if (code === 'already_responded') {
        toast.error('Ai răspuns deja la acest pulse.')
        queryClient.invalidateQueries({ queryKey: ['happy', 'pulse'] })
        setDone(true)
      } else if (code === 'not_invited') {
        toast.error('Nu ești invitat la acest pulse.')
        setSubmitting(false)
      } else if (code === 'not_open') {
        toast.error('Acest pulse nu mai este deschis.')
        setSubmitting(false)
      } else {
        toast.error('Nu am putut trimite răspunsul.')
        setSubmitting(false)
      }
    }
  }

  if (done) {
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-center">
        <TitleWrapper className="sr-only">{pulse.title}</TitleWrapper>
        <CheckCircle2 className="h-10 w-10 text-green-600" />
        <p className="text-base font-semibold">Mulțumim, ai răspuns.</p>
        <p className="max-w-xs text-sm text-muted-foreground">
          Răspunsul tău este anonim și contribuie la rezultatele pe echipă.
        </p>
        <Button variant="outline" onClick={onClose}>
          Închide
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <TitleWrapper className="text-lg font-semibold leading-snug">{pulse.title}</TitleWrapper>

      {/* Anonymity notice — MUST appear above the first question (trust requirement). */}
      <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/40 p-3 text-sm">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        <p className="text-muted-foreground">{anonymityNotice}</p>
      </div>

      <div className="space-y-5">
        {questions.map((q, qi) => {
          const key = `q${q.position}`
          const current = answers[key]
          return (
            <div key={q.position} className="space-y-2">
              <p className="text-sm font-medium">
                {qi + 1}. {q.prompt_ro}
                {q.qtype === 'open' && (
                  <span className="ml-1 font-normal text-muted-foreground">(opțional)</span>
                )}
              </p>

              {q.qtype === 'open' ? (
                <Textarea
                  value={typeof current === 'string' ? current : ''}
                  onChange={(e) => setAnswer(q.position, e.target.value)}
                  placeholder="Scrie un răspuns…"
                  rows={3}
                />
              ) : q.qtype === 'enps' ? (
                <ScaleQuestion
                  values={ENPS_SCALE}
                  selected={typeof current === 'number' ? current : undefined}
                  onSelect={(v) => setAnswer(q.position, v)}
                  minLabel="Deloc probabil"
                  maxLabel="Foarte probabil"
                />
              ) : (
                // likert5 and single (no options provided) both render as a 1–5 scale
                <ScaleQuestion
                  values={LIKERT_SCALE}
                  selected={typeof current === 'number' ? current : undefined}
                  onSelect={(v) => setAnswer(q.position, v)}
                  minLabel="Dezacord total"
                  maxLabel="Acord total"
                />
              )}
            </div>
          )
        })}
      </div>

      <div className="flex flex-col-reverse gap-2 pt-1 sm:flex-row sm:justify-end">
        <Button variant="ghost" onClick={onClose}>
          Mai târziu
        </Button>
        <Button disabled={!canSubmit} onClick={handleSubmit}>
          Trimite răspunsul
        </Button>
      </div>
    </div>
  )
}

export interface PulseSheetProps {
  pulse: HappyPulse
  questions: HappyPulseQuestion[]
  anonymityNotice: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * Anonymous Pulse respondent surface. Desktop = Dialog, mobile = bottom Sheet.
 * The anonymity notice renders prominently above the first question. No identity
 * is ever captured or displayed (spec §7.5).
 */
export function PulseSheet({ pulse, questions, anonymityNotice, open, onOpenChange }: PulseSheetProps) {
  const isMobile = useIsMobile()
  const close = () => onOpenChange(false)

  if (isMobile) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="bottom" className="max-h-[92vh] overflow-y-auto rounded-t-3xl">
          <div className="px-1 pb-2">
            <PulseForm
              pulse={pulse}
              questions={questions}
              anonymityNotice={anonymityNotice}
              TitleWrapper={SheetTitle}
              onClose={close}
            />
          </div>
        </SheetContent>
      </Sheet>
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[560px]">
        <PulseForm
          pulse={pulse}
          questions={questions}
          anonymityNotice={anonymityNotice}
          TitleWrapper={DialogTitle}
          onClose={close}
        />
      </DialogContent>
    </Dialog>
  )
}

export default PulseSheet
