import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Target, ChevronLeft, ChevronRight, Clock, Send, CheckCircle2, HelpCircle } from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import MyReports from './MyReports'
import TeamReports from './TeamReports'
import Help from './Help'
import Evaluation360Tab from '../Hr/Evaluation360Tab'
import { useAuthStore } from '@/stores/authStore'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import {
  eval360Api, RELATIONSHIP_LABEL,
  type MyAssignment, type Question, type Answer, type CompetencyAnchors,
} from '@/api/evaluation360'
import { Timeline, type TimelineNode } from './Timeline'

const NOT_OBSERVED = 'not_observed'
const commentKey = (id: number) => `${id}:c`   // per-rating optional comment, stored alongside the value in draft
const COMMENT_MIN = 40   // spec §6.2: comments shorter than this get one gentle "add an example" nudge
const LOCALE = 'ro'   // spec §6.2: anchors are i18n per user; UI is single-locale for now
type DraftValue = string | number | null

/** The competency's behavioral anchors in the active locale, if the template carries them. */
function anchorsFor(q: Question): CompetencyAnchors | undefined {
  const map = q.competency_level_descriptors
  if (!map || Array.isArray(map)) return undefined   // '[]' default → no anchors
  return map[LOCALE] ?? Object.values(map)[0]
}

export default function Evaluations() {
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [view, setView] = useState<'todo' | 'reports' | 'team' | 'cycles' | 'help'>('todo')
  const isHrAdmin = useAuthStore((s) => s.user?.can_access_hr) ?? false
  const crumb = { todo: 'De completat', reports: 'Rapoartele mele', team: 'Echipa', cycles: 'Administrare', help: 'Ajutor' }[view]

  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader
        title="Evaluări 360"
        breadcrumbs={[{ label: 'Evaluări 360' }, { label: crumb }]}
        actions={selectedId == null ? (
          <Tabs value={view} onValueChange={(v) => setView(v as 'todo' | 'reports' | 'team' | 'cycles' | 'help')}>
            <TabsList>
              <TabsTrigger value="todo">De completat</TabsTrigger>
              <TabsTrigger value="reports">Rapoartele mele</TabsTrigger>
              <TabsTrigger value="team">Echipa</TabsTrigger>
              {isHrAdmin && <TabsTrigger value="cycles">Administrare</TabsTrigger>}
              <TabsTrigger value="help"><HelpCircle className="mr-1 h-3.5 w-3.5" />Ajutor</TabsTrigger>
            </TabsList>
          </Tabs>
        ) : undefined}
      />
      {selectedId != null
        ? <EvaluationForm assignmentId={selectedId} onBack={() => setSelectedId(null)} />
        : view === 'todo' ? <Inbox onOpen={setSelectedId} />
          : view === 'reports' ? <MyReports />
            : view === 'team' ? <TeamReports />
              : view === 'help' ? <Help />
                : <Evaluation360Tab />}
    </div>
  )
}

function Inbox({ onOpen }: { onOpen: (id: number) => void }) {
  const q = useQuery({ queryKey: ['eval360-my-assignments'], queryFn: () => eval360Api.myAssignments() })
  const items = q.data?.assignments ?? []

  if (q.isLoading) return <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-16 w-full" />)}</div>
  if (!items.length) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-full bg-muted">
          <CheckCircle2 className="h-7 w-7 text-muted-foreground/50" />
        </div>
        <p className="text-sm font-medium">Nicio evaluare de completat</p>
        <p className="text-sm text-muted-foreground">Vei fi notificat când primești evaluări noi.</p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border divide-y">
      {items.map((a) => <InboxRow key={a.id} a={a} onOpen={() => onOpen(a.id)} />)}
    </div>
  )
}

function InboxRow({ a, onOpen }: { a: MyAssignment; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/50"
    >
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-blue-100 text-blue-600 dark:bg-blue-950/40 dark:text-blue-400">
          <Target className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{a.subject_name}</p>
          <p className="truncate text-xs text-muted-foreground">{a.cycle_name}</p>
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {a.total > 0 && (
          <span className="hidden items-center gap-1 text-xs text-muted-foreground sm:flex tabular-nums">
            {a.answered}/{a.total} · ~{a.est_minutes} min
          </span>
        )}
        <Badge variant="secondary">{RELATIONSHIP_LABEL[a.relationship] ?? a.relationship}</Badge>
        {a.status === 'in_progress' && <Badge variant="outline" className="text-amber-600 border-amber-200">În lucru</Badge>}
        {a.review_end && <span className="hidden items-center gap-1 text-xs text-muted-foreground sm:flex"><Clock className="h-3 w-3" />{a.review_end}</span>}
        <ChevronRight className="h-4 w-4 text-muted-foreground" />
      </div>
    </button>
  )
}

function questionText(q: Question, relationship: string): string {
  return q.text_by_audience?.[relationship]
    || q.text_by_audience?.peer
    || q.competency_name
    || 'Întrebare'
}

export function EvaluationForm({ assignmentId, onBack }: { assignmentId: number; onBack: () => void }) {
  const qc = useQueryClient()
  const formQ = useQuery({
    queryKey: ['eval360-form', assignmentId],
    queryFn: () => eval360Api.getForm(assignmentId),
  })
  const [draft, setDraft] = useState<Record<string, DraftValue>>({})
  const [step, setStep] = useState(0)

  useEffect(() => {
    if (!formQ.data) return
    setDraft({ ...formQ.data.draft })
    // Resume on the first unanswered rating step (or the summary if all done).
    const qs = formQ.data.questions
    const firstUnanswered = qs.findIndex(
      (q) => (q.type === 'rating' || q.type === 'behavioral_frequency') && formQ.data!.draft[String(q.id)] == null)
    setStep(firstUnanswered === -1 ? qs.length : Math.max(0, firstUnanswered))
  }, [formQ.data])

  const saveM = useMutation({
    mutationFn: (patch: Record<string, DraftValue>) => eval360Api.saveDraft(assignmentId, patch),
  })
  const submitM = useMutation({
    mutationFn: (answers: Answer[]) => eval360Api.submit(assignmentId, answers),
    onSuccess: () => {
      toast.success('Evaluare trimisă')
      qc.invalidateQueries({ queryKey: ['eval360-my-assignments'] })
      onBack()
    },
    onError: () => toast.error('Nu s-a putut trimite'),
  })
  const nudgedRef = useRef<Set<number>>(new Set())
  const nudgeM = useMutation({ mutationFn: (questionId: number) => eval360Api.commentNudge(assignmentId, questionId) })

  // Persist a rating and auto-advance ~450ms later (unless the user already moved).
  const pickRating = (q: Question, value: DraftValue, atStep: number, lastStep: number) => {
    setDraft((d) => ({ ...d, [String(q.id)]: value }))
    saveM.mutate({ [String(q.id)]: value })
    window.setTimeout(() => setStep((cur) => (cur === atStep ? Math.min(atStep + 1, lastStep) : cur)), 450)
  }

  // Keyboard: 1–5 rate the current step (auto-advance); ← / → navigate.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const data = formQ.data
      if (!data || data.is_submitted) return
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'TEXTAREA' || tag === 'INPUT' || tag === 'SELECT') return
      const lastStep = data.questions.length
      if (e.key === 'ArrowRight') setStep((s) => Math.min(s + 1, lastStep))
      else if (e.key === 'ArrowLeft') setStep((s) => Math.max(s - 1, 0))
      else if (/^[1-5]$/.test(e.key) && step < data.questions.length) {
        const q = data.questions[step]
        if (q.type === 'rating' || q.type === 'behavioral_frequency') pickRating(q, Number(e.key), step, lastStep)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formQ.data, step])

  if (formQ.isLoading) return <Skeleton className="h-64 w-full" />
  if (formQ.isError || !formQ.data) return <p className="py-12 text-center text-sm text-muted-foreground">Nu s-a putut încărca evaluarea.</p>

  const { assignment, questions, is_submitted } = formQ.data
  const relationship = assignment.relationship
  const isRating = (q: Question) => q.type === 'rating' || q.type === 'behavioral_frequency'
  const lastStep = questions.length   // the summary step index

  const stepAnswered = (q: Question) => isRating(q)
    ? draft[String(q.id)] != null
    : (!q.required || (typeof draft[String(q.id)] === 'string' && (draft[String(q.id)] as string).trim() !== ''))
  const answeredRequired = questions.filter((q) => q.required).every(stepAnswered)
  const answeredCount = questions.filter((q) => draft[String(q.id)] != null && draft[String(q.id)] !== '').length
  const estMin = Math.max(1, Math.round(Math.max(0, questions.length - answeredCount) * 0.75))

  const setComment = (q: Question, value: string) => {
    const k = commentKey(q.id)
    setDraft((d) => ({ ...d, [k]: value }))
    saveM.mutate({ [k]: value })
  }
  const nudgeComment = (q: Question, value: string) => {
    const len = value.trim().length
    if (len > 0 && len < COMMENT_MIN && !nudgedRef.current.has(q.id)) {
      nudgedRef.current.add(q.id)
      nudgeM.mutate(q.id)
    }
  }

  const buildAnswers = (): Answer[] => questions.map((q) => {
    const v = draft[String(q.id)]
    if (q.type === 'open_text') {
      return { question_id: q.id, competency_id: q.competency_id, rating: null, not_observed: false, comment: typeof v === 'string' ? v : '' }
    }
    const cv = draft[commentKey(q.id)]
    const comment = typeof cv === 'string' ? cv : ''
    if (v === NOT_OBSERVED) return { question_id: q.id, competency_id: q.competency_id, rating: null, not_observed: true, comment }
    return { question_id: q.id, competency_id: q.competency_id, rating: typeof v === 'number' ? v : null, not_observed: false, comment }
  })

  const initials = (assignment.subject_name || '?').split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase()
  const saved: ReactNode = saveM.isError
    ? <span className="text-amber-600">Nesalvat</span>
    : saveM.isPending ? <span>Se salvează…</span>
      : saveM.isSuccess ? <span className="flex items-center gap-1 text-green-600"><CheckCircle2 className="h-3 w-3" /> Salvat</span> : null

  const railNodes: TimelineNode[] = [
    ...questions.map((q, i) => {
      const v = draft[String(q.id)]
      return {
        label: q.competency_name ?? `#${i + 1}`,
        state: (i === step ? 'current' : (stepAnswered(q) || i < step) ? 'done' : 'todo') as TimelineNode['state'],
        badge: isRating(q) && v != null && i !== step ? (v === NOT_OBSERVED ? 'N/O' : String(v)) : undefined,
      }
    }),
    { label: 'Trimite', state: (step === lastStep ? 'current' : 'todo') as TimelineNode['state'] },
  ]

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <button onClick={onBack} className="flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-4 w-4" /> Înapoi
      </button>

      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-bold text-primary-foreground">{initials}</div>
        <div className="min-w-0">
          <p className="truncate text-base font-semibold tracking-tight">{assignment.subject_name}</p>
          <p className="truncate text-xs text-muted-foreground">{RELATIONSHIP_LABEL[relationship] ?? relationship} · {assignment.cycle_name}</p>
        </div>
        {!is_submitted && (
          <div className="ml-auto text-right text-xs text-muted-foreground">
            <div className="flex items-center justify-end gap-1">{saved}</div>
            <div>~{estMin} min rămase{assignment.review_end ? ` · termen ${assignment.review_end}` : ''}</div>
          </div>
        )}
      </div>

      {is_submitted ? (
        <Card><CardContent className="flex items-center gap-2 py-6 text-sm text-green-600">
          <CheckCircle2 className="h-5 w-5" /> Ai trimis deja această evaluare. Răspunsurile sunt finale.
        </CardContent></Card>
      ) : !questions.length ? (
        <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">
          Formularul nu are încă întrebări configurate pentru acest ciclu.
        </CardContent></Card>
      ) : (
        <>
          <div className="overflow-x-auto pb-1"><Timeline nodes={railNodes} current={step} onSelect={setStep} /></div>

          {step === lastStep ? (
            <Card><CardContent className="py-6 space-y-4">
              <div>
                <p className="text-[11px] font-bold uppercase tracking-widest text-primary">Rezumat</p>
                <h2 className="mt-1 text-xl font-semibold">Gata de trimis?</h2>
              </div>
              <div className="rounded-xl border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
                {answeredCount}/{questions.length} evaluate. După trimitere, răspunsurile devin definitive și anonime în raport. Poți sări înapoi pe orice pas din timeline ca să modifici.
              </div>
              <div className="flex items-center">
                <span className="text-xs text-muted-foreground">{saved}</span>
                <div className="ml-auto flex gap-2">
                  <Button variant="outline" onClick={() => setStep((s) => Math.max(0, s - 1))}>Înapoi</Button>
                  <Button disabled={!answeredRequired || submitM.isPending} onClick={() => submitM.mutate(buildAnswers())}>
                    <Send className="h-4 w-4 mr-1" /> Trimite evaluarea
                  </Button>
                </div>
              </div>
            </CardContent></Card>
          ) : (
            <StepCard
              q={questions[step]} stepNo={step + 1} total={questions.length} relationship={relationship}
              value={draft[String(questions[step].id)] ?? null}
              onRate={(v) => pickRating(questions[step], v, step, lastStep)}
              onOpenText={(v) => { const q = questions[step]; setDraft((d) => ({ ...d, [String(q.id)]: v })); saveM.mutate({ [String(q.id)]: v }) }}
              comment={typeof draft[commentKey(questions[step].id)] === 'string' ? (draft[commentKey(questions[step].id)] as string) : ''}
              onComment={(v) => setComment(questions[step], v)}
              onNudge={(v) => nudgeComment(questions[step], v)}
              saved={saved}
              canBack={step > 0} onBack={() => setStep((s) => Math.max(0, s - 1))}
              canNext={stepAnswered(questions[step])} onNext={() => setStep((s) => Math.min(lastStep, s + 1))}
            />
          )}
          <p className="text-center text-xs text-muted-foreground">Fiecare răspuns se salvează instant — poți reveni oricând, de pe orice dispozitiv.</p>
        </>
      )}
    </div>
  )
}

function StepCard({
  q, stepNo, total, relationship, value, onRate, onOpenText, comment, onComment, onNudge, saved,
  canBack, onBack, canNext, onNext,
}: {
  q: Question; stepNo: number; total: number; relationship: string; value: DraftValue
  onRate: (v: DraftValue) => void; onOpenText: (v: string) => void
  comment: string; onComment: (v: string) => void; onNudge: (v: string) => void; saved: ReactNode
  canBack: boolean; onBack: () => void; canNext: boolean; onNext: () => void
}) {
  const isText = q.type === 'open_text'
  const notObserved = value === NOT_OBSERVED
  const anchors = anchorsFor(q)
  const hasLevels = anchors?.levels?.length === 5
  const shortComment = comment.trim().length > 0 && comment.trim().length < COMMENT_MIN
  return (
    <Card><CardContent className="py-6 space-y-4">
      <div>
        <p className="text-[11px] font-bold uppercase tracking-widest text-primary">Pasul {stepNo} din {total}{q.competency_name ? ` · ${q.competency_name}` : ''}</p>
        <h2 className="mt-1 text-lg font-semibold">{questionText(q, relationship)}</h2>
      </div>

      {isText ? (
        <Textarea
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onOpenText(e.target.value)}
          placeholder="Un exemplu concret ajută cel mai mult…"
          rows={4}
        />
      ) : (
        <>
          {/* Behavioral anchors (spec §6.2): shown before the scale, from template data */}
          {(hasLevels || q.competency_definition) && (
            <div className="rounded-xl border bg-muted/40 px-4 py-3">
              {hasLevels ? (
                <ul className="space-y-0.5">
                  {anchors!.levels!.map((lvl, i) => (
                    <li key={i} className="flex gap-2 text-xs text-muted-foreground">
                      <span className="font-semibold text-foreground tabular-nums">{i + 1}</span>
                      <span>{lvl}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-muted-foreground">{q.competency_definition}</p>
              )}
            </div>
          )}

          {(anchors?.min_label || anchors?.max_label) && (
            <div className="flex justify-between px-1 text-xs font-medium text-muted-foreground">
              <span>{anchors?.min_label}</span>
              <span>{anchors?.max_label}</span>
            </div>
          )}

          <div className="flex gap-2">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => onRate(n)}
                className={cn(
                  'h-14 flex-1 rounded-xl border-2 text-lg font-bold transition-all',
                  value === n ? 'scale-[1.03] border-primary bg-primary text-primary-foreground' : 'border-border hover:border-primary',
                )}
              >
                {n}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={() => onRate(NOT_OBSERVED)}
            className={cn(
              'w-full rounded-xl border-2 border-dashed px-3 py-3 text-sm font-medium transition-colors',
              notObserved ? 'border-primary bg-secondary text-foreground' : 'border-border text-muted-foreground hover:border-muted-foreground',
            )}
          >
            Nu am observat — exclus din scor
          </button>

          <Textarea
            value={comment}
            onChange={(e) => onComment(e.target.value)}
            onBlur={(e) => onNudge(e.target.value)}
            placeholder="Opțional: un exemplu concret face feedbackul de 10× mai util…"
            rows={3}
          />
          {shortComment && (
            <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:bg-amber-950/30 dark:text-amber-400">
              Ce a făcut concret? O situație reală ajută mai mult decât un adjectiv.
            </p>
          )}
        </>
      )}

      <div className="flex items-center pt-1">
        <span className="text-xs text-muted-foreground">{saved}</span>
        <div className="ml-auto flex gap-2">
          {canBack && <Button variant="outline" onClick={onBack}>Înapoi</Button>}
          <Button disabled={!canNext} onClick={onNext}>Continuă</Button>
        </div>
      </div>
    </CardContent></Card>
  )
}
