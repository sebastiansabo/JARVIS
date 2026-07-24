import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Plus, ChevronLeft, ChevronRight, FileText, Layers, Trash2, GripVertical,
  CheckCircle2, GitFork, Send, Archive, Pencil,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import {
  eval360Library, TEMPLATE_STATUS_LABEL,
  type Competency, type TemplateSummary, type TemplateQuestion, type QuestionType,
} from '@/api/evaluation360'

const AUDIENCES = ['self', 'manager', 'peer', 'direct_report'] as const

/** Collapse a template's per-audience prompts into the single line the editor
 *  shows (they are authored together in this MVP). */
function promptOf(q: TemplateQuestion): string {
  return q.text_by_audience?.peer || Object.values(q.text_by_audience || {})[0] || ''
}
function fanText(text: string): Record<string, string> {
  return Object.fromEntries(AUDIENCES.map((a) => [a, text]))
}

function statusBadgeClass(status: TemplateSummary['status']): string {
  switch (status) {
    case 'published': return 'bg-green-100 text-green-700 border-green-200 dark:bg-green-950/40 dark:text-green-400'
    case 'archived': return 'bg-muted text-muted-foreground'
    default: return 'bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-400'
  }
}

export default function TemplateLibrary() {
  const [editingId, setEditingId] = useState<number | 'new' | null>(null)

  if (editingId != null) {
    return <TemplateEditor templateId={editingId} onBack={() => setEditingId(null)} />
  }
  return (
    <div className="space-y-6">
      <TemplatesSection onEdit={setEditingId} />
      <CompetenciesSection />
    </div>
  )
}

// ── Templates ────────────────────────────────────────────────────────────────

function TemplatesSection({ onEdit }: { onEdit: (id: number | 'new') => void }) {
  const q = useQuery({ queryKey: ['eval360-templates'], queryFn: () => eval360Library.listTemplates() })
  const templates = q.data?.templates ?? []

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Șabloane de formular</h3>
        </div>
        <Button size="sm" onClick={() => onEdit('new')}><Plus className="h-4 w-4 mr-1" />Șablon nou</Button>
      </div>

      {q.isLoading ? (
        <Skeleton className="h-28 w-full" />
      ) : !templates.length ? (
        <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">
          Niciun șablon încă. Creează unul, adaugă câteva competențe și publică-l pentru a-l folosi într-un ciclu.
        </CardContent></Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {templates.map((t) => (
            <Card key={t.id} className="transition-colors hover:border-primary/40">
              <CardContent className="py-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="truncate text-sm font-semibold">{t.name}</p>
                      <span className="text-xs text-muted-foreground tabular-nums">v{t.version}</span>
                    </div>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {t.question_count} întrebări · folosit în {t.cycle_count} cicluri
                    </p>
                  </div>
                  <Badge variant="outline" className={cn('shrink-0', statusBadgeClass(t.status))}>
                    {TEMPLATE_STATUS_LABEL[t.status]}
                  </Badge>
                </div>
                <div className="mt-3 flex items-center justify-end">
                  <Button variant="ghost" size="sm" onClick={() => onEdit(t.id)}>
                    {t.status === 'published' ? <>Vezi / versiune nouă</> : <><Pencil className="h-3.5 w-3.5 mr-1" />Editează</>}
                    <ChevronRight className="h-4 w-4 ml-1" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

function TemplateEditor({ templateId, onBack }: { templateId: number | 'new'; onBack: () => void }) {
  const qc = useQueryClient()
  const isNew = templateId === 'new'

  const compQ = useQuery({ queryKey: ['eval360-competencies'], queryFn: () => eval360Library.listCompetencies() })
  const competencies = useMemo(() => compQ.data?.competencies ?? [], [compQ.data])

  const tplQ = useQuery({
    queryKey: ['eval360-template', templateId],
    queryFn: () => eval360Library.getTemplate(templateId as number),
    enabled: !isNew,
  })

  const [name, setName] = useState('')
  const [questions, setQuestions] = useState<TemplateQuestion[]>([])
  const [loaded, setLoaded] = useState(false)

  // Hydrate once the template detail arrives (or immediately for a new one).
  if (!loaded) {
    if (isNew) { setLoaded(true) }
    else if (tplQ.data) {
      setName(tplQ.data.template.name)
      setQuestions(tplQ.data.questions.map((x) => ({ ...x })))
      setLoaded(true)
    }
  }

  const status = tplQ.data?.template.status
  const isPublished = status === 'published'
  const isArchived = status === 'archived'
  const version = tplQ.data?.template.version

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ['eval360-templates'] })
    qc.invalidateQueries({ queryKey: ['eval360-template', templateId] })
  }

  const saveM = useMutation({
    mutationFn: () => {
      const payload = {
        name: name.trim(),
        competency_ids: [...new Set(questions.map((q) => q.competency_id).filter((x): x is number => x != null))],
        questions,
      }
      return isNew ? eval360Library.createTemplate(payload) : eval360Library.saveTemplate(templateId as number, payload)
    },
    onSuccess: (res) => {
      invalidateAll()
      if (res.forked) toast.success(`Șablon publicat — s-a creat versiunea v${res.template.version} (ciornă)`)
      else toast.success('Șablon salvat')
      onBack()
    },
    onError: () => toast.error('Nu s-a putut salva șablonul'),
  })

  const publishM = useMutation({
    mutationFn: () => eval360Library.publishTemplate(templateId as number),
    onSuccess: () => { invalidateAll(); toast.success('Șablon publicat — gata de folosit într-un ciclu'); onBack() },
    onError: (e: unknown) => toast.error(errMsg(e, 'Nu s-a putut publica')),
  })
  const forkM = useMutation({
    mutationFn: () => eval360Library.forkTemplate(templateId as number),
    onSuccess: () => { invalidateAll(); toast.success('S-a creat o versiune nouă (ciornă) — editeaz-o liber') },
    onError: () => toast.error('Nu s-a putut crea versiunea'),
  })
  const archiveM = useMutation({
    mutationFn: () => eval360Library.archiveTemplate(templateId as number),
    onSuccess: () => { invalidateAll(); toast.success('Șablon arhivat'); onBack() },
    onError: () => toast.error('Nu s-a putut arhiva'),
  })

  const readOnly = isPublished || isArchived
  const addQuestion = (competency_id: number | null, type: QuestionType = 'rating') =>
    setQuestions((qs) => [...qs, { competency_id, type, required: true, text_by_audience: {} }])
  const setQuestion = (i: number, patch: Partial<TemplateQuestion>) =>
    setQuestions((qs) => qs.map((q, idx) => (idx === i ? { ...q, ...patch } : q)))
  const removeQuestion = (i: number) => setQuestions((qs) => qs.filter((_, idx) => idx !== i))

  if (!isNew && (tplQ.isLoading || !loaded)) return <Skeleton className="h-64 w-full" />

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-4 w-4" /> Înapoi la bibliotecă
      </button>

      <Card>
        <CardContent className="space-y-3 py-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-muted-foreground" />
              <h2 className="text-base font-semibold">{isNew ? 'Șablon nou' : 'Editează șablon'}</h2>
              {version != null && <span className="text-xs text-muted-foreground tabular-nums">v{version}</span>}
              {status && (
                <Badge variant="outline" className={statusBadgeClass(status)}>{TEMPLATE_STATUS_LABEL[status]}</Badge>
              )}
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="tpl-name">Nume șablon</Label>
            <Input id="tpl-name" value={name} disabled={readOnly}
              onChange={(e) => setName(e.target.value)} placeholder="Evaluare 360 · Model standard" />
          </div>
          {isPublished && (
            <p className="rounded-lg bg-muted/60 px-3 py-2 text-xs text-muted-foreground">
              Șablon publicat — imutabil. Ca să-l modifici, apasă <span className="font-medium">Versiune nouă</span>;
              se creează o ciornă (v{(version ?? 1) + 1}) fără să afectezi ciclurile care îl folosesc.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Question list */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold">Întrebări ({questions.length})</p>
        </div>
        {questions.length === 0 && (
          <Card><CardContent className="py-6 text-center text-sm text-muted-foreground">
            Nicio întrebare. Adaugă câte una pe competență (rating 1–5) sau o întrebare deschisă.
          </CardContent></Card>
        )}
        {questions.map((q, i) => (
          <QuestionRow
            key={i} index={i} q={q} competencies={competencies} readOnly={readOnly}
            onChange={(patch) => setQuestion(i, patch)} onRemove={() => removeQuestion(i)}
          />
        ))}

        {!readOnly && (
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <AddCompetencyQuestion competencies={competencies} onAdd={(cid) => addQuestion(cid, 'rating')} />
            <Button variant="outline" size="sm" onClick={() => addQuestion(null, 'open_text')}>
              <Plus className="h-4 w-4 mr-1" />Întrebare deschisă
            </Button>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex flex-wrap items-center justify-end gap-2 border-t pt-4">
        {isPublished && (
          <Button variant="outline" size="sm" disabled={forkM.isPending} onClick={() => forkM.mutate()}>
            <GitFork className="h-4 w-4 mr-1" />Versiune nouă
          </Button>
        )}
        {!isArchived && !isNew && (
          <Button variant="ghost" size="sm" className="text-muted-foreground" disabled={archiveM.isPending} onClick={() => archiveM.mutate()}>
            <Archive className="h-4 w-4 mr-1" />Arhivează
          </Button>
        )}
        {!readOnly && (
          <>
            <Button variant="outline" size="sm" disabled={!name.trim() || saveM.isPending} onClick={() => saveM.mutate()}>
              Salvează ciorna
            </Button>
            {!isNew && (
              <Button size="sm" disabled={!questions.length || publishM.isPending} onClick={() => publishM.mutate()}>
                <Send className="h-4 w-4 mr-1" />Publică
              </Button>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function QuestionRow({
  index, q, competencies, readOnly, onChange, onRemove,
}: {
  index: number; q: TemplateQuestion; competencies: Competency[]; readOnly: boolean
  onChange: (patch: Partial<TemplateQuestion>) => void; onRemove: () => void
}) {
  const compName = competencies.find((c) => c.id === q.competency_id)?.name
  return (
    <Card>
      <CardContent className="flex items-start gap-3 py-3">
        <div className="mt-2 flex items-center gap-1 text-muted-foreground">
          <GripVertical className="h-4 w-4" />
          <span className="text-xs tabular-nums">{index + 1}</span>
        </div>
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary" className="text-[11px]">
              {q.type === 'open_text' ? 'Deschisă' : 'Rating 1–5'}
            </Badge>
            {compName && <Badge variant="outline" className="text-[11px]">{compName}</Badge>}
            {q.type !== 'open_text' && (
              <label className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground">
                <input type="checkbox" checked={q.required} disabled={readOnly}
                  onChange={(e) => onChange({ required: e.target.checked })} />
                Obligatorie
              </label>
            )}
          </div>
          <Textarea
            rows={2}
            value={promptOf(q)}
            disabled={readOnly}
            onChange={(e) => onChange({ text_by_audience: fanText(e.target.value) })}
            placeholder={q.type === 'open_text'
              ? 'ex. Ce ar trebui să înceapă / să oprească această persoană?'
              : 'ex. Cât de eficient comunică ideile complexe?'}
          />
        </div>
        {!readOnly && (
          <Button variant="ghost" size="icon" className="shrink-0 text-muted-foreground hover:text-destructive" onClick={onRemove}>
            <Trash2 className="h-4 w-4" />
          </Button>
        )}
      </CardContent>
    </Card>
  )
}

function AddCompetencyQuestion({ competencies, onAdd }: { competencies: Competency[]; onAdd: (cid: number) => void }) {
  const [value, setValue] = useState('')
  return (
    <div className="flex items-center gap-2">
      <Select value={value} onValueChange={(v) => { onAdd(Number(v)); setValue('') }}>
        <SelectTrigger className="h-9 w-56"><SelectValue placeholder="+ Adaugă din competență" /></SelectTrigger>
        <SelectContent>
          {competencies.length === 0 && <div className="px-2 py-1.5 text-xs text-muted-foreground">Nicio competență definită</div>}
          {competencies.map((c) => (
            <SelectItem key={c.id} value={String(c.id)}>{c.name}{c.cluster ? ` · ${c.cluster}` : ''}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

// ── Competencies ─────────────────────────────────────────────────────────────

function CompetenciesSection() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['eval360-competencies'], queryFn: () => eval360Library.listCompetencies(true) })
  const competencies = q.data?.competencies ?? []
  const grouped = useMemo(() => {
    const m = new Map<string, Competency[]>()
    for (const c of competencies) {
      const key = c.cluster || 'Fără grup'
      if (!m.has(key)) m.set(key, [])
      m.get(key)!.push(c)
    }
    return [...m.entries()]
  }, [competencies])

  const [name, setName] = useState('')
  const [cluster, setCluster] = useState('')

  const createM = useMutation({
    mutationFn: () => eval360Library.createCompetency({ name: name.trim(), cluster: cluster.trim() || undefined }),
    onSuccess: () => {
      setName(''); setCluster('')
      qc.invalidateQueries({ queryKey: ['eval360-competencies'] })
      toast.success('Competență adăugată')
    },
    onError: () => toast.error('Nu s-a putut adăuga competența'),
  })
  const toggleM = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      eval360Library.updateCompetency(id, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['eval360-competencies'] }),
    onError: () => toast.error('Nu s-a putut actualiza'),
  })

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold">Bibliotecă de competențe</h3>
      </div>

      <Card>
        <CardContent className="flex flex-wrap items-end gap-2 py-4">
          <div className="min-w-[12rem] flex-1 space-y-1.5">
            <Label htmlFor="comp-name">Competență nouă</Label>
            <Input id="comp-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="ex. Comunicare" />
          </div>
          <div className="w-40 space-y-1.5">
            <Label htmlFor="comp-cluster">Grup (opțional)</Label>
            <Input id="comp-cluster" value={cluster} onChange={(e) => setCluster(e.target.value)} placeholder="ex. Leadership" />
          </div>
          <Button disabled={!name.trim() || createM.isPending} onClick={() => createM.mutate()}>
            <Plus className="h-4 w-4 mr-1" />Adaugă
          </Button>
        </CardContent>
      </Card>

      {q.isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : competencies.length === 0 ? (
        <p className="py-4 text-center text-sm text-muted-foreground">Nicio competență definită încă.</p>
      ) : (
        <div className="space-y-4">
          {grouped.map(([group, items]) => (
            <div key={group}>
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{group}</p>
              <div className="flex flex-wrap gap-2">
                {items.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => toggleM.mutate({ id: c.id, is_active: !c.is_active })}
                    title={c.is_active ? 'Activă — click pentru a dezactiva' : 'Inactivă — click pentru a reactiva'}
                    className={cn(
                      'flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition-colors',
                      c.is_active ? 'hover:bg-muted' : 'opacity-50 line-through hover:opacity-80',
                    )}
                  >
                    {c.name}
                    {c.usage_count > 0 && (
                      <span className="rounded-full bg-muted px-1.5 text-[10px] tabular-nums text-muted-foreground">{c.usage_count}</span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function errMsg(e: unknown, fallback: string): string {
  return e && typeof e === 'object' && 'data' in e
    ? String((e as { data?: { error?: string } }).data?.error ?? fallback)
    : fallback
}
