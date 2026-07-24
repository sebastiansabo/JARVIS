import { useEffect, useRef, useState } from 'react'
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

  useEffect(() => {
    if (formQ.data) setDraft({ ...formQ.data.draft })
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
  // Comment-quality nudge state (hooks MUST stay above the early returns below).
  const nudgedRef = useRef<Set<number>>(new Set())
  const nudgeM = useMutation({ mutationFn: (questionId: number) => eval360Api.commentNudge(assignmentId, questionId) })

  if (formQ.isLoading) return <Skeleton className="h-64 w-full" />
  if (formQ.isError || !formQ.data) return <p className="py-12 text-center text-sm text-muted-foreground">Nu s-a putut încărca evaluarea.</p>

  const { assignment, questions, is_submitted } = formQ.data
  const relationship = assignment.relationship

  const setValue = (q: Question, value: DraftValue) => {
    setDraft((d) => ({ ...d, [String(q.id)]: value }))
    saveM.mutate({ [String(q.id)]: value })   // idempotent per-question autosave
  }

  const setComment = (q: Question, value: string) => {
    const k = commentKey(q.id)
    setDraft((d) => ({ ...d, [k]: value }))
    saveM.mutate({ [k]: value })
  }

  // A short, non-empty comment gets one gentle prompt for a concrete example —
  // fired once per question, never blocks submit. (Hooks declared above.)
  const nudgeComment = (q: Question, value: string) => {
    const len = value.trim().length
    if (len > 0 && len < COMMENT_MIN && !nudgedRef.current.has(q.id)) {
      nudgedRef.current.add(q.id)
      nudgeM.mutate(q.id)
    }
  }

  const ratingQuestions = questions.filter((q) => q.type === 'rating' || q.type === 'behavioral_frequency')
  const answeredRequired = ratingQuestions
    .filter((q) => q.required)
    .every((q) => draft[String(q.id)] != null && draft[String(q.id)] !== '')
  const answeredCount = ratingQuestions.filter((q) => draft[String(q.id)] != null).length

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

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-4 w-4" /> Înapoi
      </button>

      <Card>
        <CardContent className="flex items-center justify-between gap-3 py-4">
          <div>
            <h2 className="text-lg font-semibold tracking-tight">{assignment.subject_name}</h2>
            <p className="text-xs text-muted-foreground">
              {assignment.cycle_name} · <span className="font-medium">{RELATIONSHIP_LABEL[relationship] ?? relationship}</span>
            </p>
          </div>
          {!is_submitted && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              {saveM.isError ? (
                <span className="text-amber-600">Nesalvat</span>
              ) : saveM.isPending ? (
                <span>Se salvează…</span>
              ) : saveM.isSuccess ? (
                <span className="flex items-center gap-1 text-green-600"><CheckCircle2 className="h-3 w-3" /> Salvat</span>
              ) : null}
              <span className="tabular-nums">{answeredCount}/{ratingQuestions.length} completate</span>
            </div>
          )}
        </CardContent>
      </Card>

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
          {questions.map((q) => (
            <QuestionCard
              key={q.id}
              q={q}
              relationship={relationship}
              value={draft[String(q.id)] ?? null}
              onChange={(v) => setValue(q, v)}
              comment={typeof draft[commentKey(q.id)] === 'string' ? (draft[commentKey(q.id)] as string) : ''}
              onComment={(v) => setComment(q, v)}
              onNudge={(v) => nudgeComment(q, v)}
            />
          ))}

          <div className="flex items-center justify-end gap-2 pb-8">
            <Button
              disabled={!answeredRequired || submitM.isPending}
              onClick={() => submitM.mutate(buildAnswers())}
            >
              <Send className="h-4 w-4 mr-1" /> Trimite evaluarea
            </Button>
          </div>
        </>
      )}
    </div>
  )
}

function QuestionCard({
  q, relationship, value, onChange, comment, onComment, onNudge,
}: {
  q: Question; relationship: string; value: DraftValue; onChange: (v: DraftValue) => void
  comment: string; onComment: (v: string) => void; onNudge: (v: string) => void
}) {
  const shortComment = comment.trim().length > 0 && comment.trim().length < COMMENT_MIN
  if (q.type === 'open_text') {
    return (
      <Card><CardContent className="py-4 space-y-2">
        {q.competency_name && <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{q.competency_name}</p>}
        <p className="text-sm">{questionText(q, relationship)}</p>
        <Textarea
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Un exemplu concret ajută cel mai mult…"
          rows={3}
        />
      </CardContent></Card>
    )
  }

  const notObserved = value === NOT_OBSERVED
  const anchors = anchorsFor(q)
  const hasLevels = anchors?.levels?.length === 5
  return (
    <Card><CardContent className="py-4 space-y-3">
      {q.competency_name && <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{q.competency_name}</p>}
      <p className="text-sm">{questionText(q, relationship)}{q.required && <span className="text-destructive"> *</span>}</p>

      {/* Behavioral anchors (spec §6.2): shown before the scale, from template data */}
      {(hasLevels || q.competency_definition) && (
        <div className="rounded-md bg-muted/40 px-3 py-2">
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
        <div className="flex justify-between px-0.5 text-[11px] font-medium text-muted-foreground">
          <span>{anchors?.min_label}</span>
          <span>{anchors?.max_label}</span>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => onChange(n)}
            className={cn(
              'h-10 w-10 rounded-lg border text-sm font-semibold transition-colors',
              value === n ? 'border-primary bg-primary text-primary-foreground' : 'hover:bg-muted',
            )}
          >
            {n}
          </button>
        ))}
        <button
          type="button"
          onClick={() => onChange(NOT_OBSERVED)}
          className={cn(
            'h-10 rounded-lg border px-3 text-xs font-medium transition-colors',
            notObserved ? 'border-primary bg-secondary text-foreground' : 'text-muted-foreground hover:bg-muted',
          )}
        >
          Nu am observat
        </button>
      </div>
      <Textarea
        value={comment}
        onChange={(e) => onComment(e.target.value)}
        onBlur={(e) => onNudge(e.target.value)}
        placeholder="Comentariu (opțional) — un exemplu concret ajută"
        rows={2}
      />
      {shortComment && (
        <p className="text-xs text-amber-600">Ce a făcut concret? Un exemplu ajută.</p>
      )}
    </CardContent></Card>
  )
}
