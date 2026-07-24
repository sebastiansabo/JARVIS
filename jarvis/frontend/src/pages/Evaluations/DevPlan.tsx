import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus, Trash2, Sparkles, CheckCircle2, Calendar } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { eval360DevPlan, type DevPlanGoal } from '@/api/evaluation360'

interface Props {
  cycleId: number
  employeeId: number
  /** Competency id→name options for the goal picker (from the report). */
  competencies?: { id: number; name: string }[]
}

/** Development plan: a manager-authored DRAFT (employee doesn't see it until
 *  finalized), with rich goals (competency · title · description · target date),
 *  AI/deterministic generation, and a save-draft / finalize flow. Editable only by
 *  the participant's manager or HR (server-enforced via can_edit). */
export function DevPlan({ cycleId, employeeId, competencies = [] }: Props) {
  const qc = useQueryClient()
  const q = useQuery({
    queryKey: ['eval360-devplan', cycleId, employeeId],
    queryFn: () => eval360DevPlan.get(cycleId, employeeId),
  })
  const [goals, setGoals] = useState<DevPlanGoal[]>([])

  useEffect(() => { if (q.data?.plan) setGoals(normalize(q.data.plan.goals ?? [])) }, [q.data])

  const invalidate = () => qc.invalidateQueries({ queryKey: ['eval360-devplan', cycleId, employeeId] })
  const errMsg = (e: unknown) => e && typeof e === 'object' && 'data' in e ? String((e as { data?: { error?: string } }).data?.error ?? 'Eroare') : 'Eroare'

  const saveM = useMutation({
    mutationFn: (g: DevPlanGoal[]) => eval360DevPlan.save(cycleId, employeeId, g, linkedFrom(g)),
    onSuccess: () => { toast.success('Ciornă salvată'); invalidate() },
    onError: (e: unknown) => toast.error(errMsg(e)),
  })
  const finalizeM = useMutation({
    mutationFn: () => eval360DevPlan.finalize(cycleId, employeeId),
    onSuccess: () => { toast.success('Plan finalizat'); invalidate() },
    onError: (e: unknown) => toast.error(errMsg(e)),
  })
  const generateM = useMutation({
    mutationFn: (mode: 'ai' | 'seed') => eval360DevPlan.generate(cycleId, employeeId, mode),
    onSuccess: (r) => { setGoals((g) => [...g, ...normalize(r.suggestion.goals)]); toast.success('Sugestii generate') },
    onError: () => toast.error('Generarea a eșuat'),
  })

  const addCheckinM = useMutation({
    mutationFn: (date: string) => eval360DevPlan.addCheckin(q.data!.plan!.id, date),
    onSuccess: () => { toast.success('Check-in adăugat'); invalidate() },
  })
  const completeM = useMutation({
    mutationFn: (id: number) => eval360DevPlan.completeCheckin(id),
    onSuccess: () => { toast.success('Check-in finalizat'); invalidate() },
  })
  const [newCheckin, setNewCheckin] = useState('')

  if (q.isLoading) return <Skeleton className="h-40 w-full" />

  const plan = q.data?.plan
  const checkins = q.data?.checkins ?? []
  const canEdit = q.data?.can_edit ?? false
  const isFinal = (plan?.status ?? 'draft') === 'finalized'

  // Employee viewing a draft: the server hid the plan (plan=null) — show nothing.
  if (!canEdit && !plan) return null

  const compName = (id?: number | null) => competencies.find((c) => c.id === id)?.name
  const patchGoal = (i: number, patch: Partial<DevPlanGoal>) => setGoals((gs) => gs.map((g, idx) => idx === i ? { ...g, ...patch } : g))
  const canFinalize = goals.some((g) => (g.title ?? '').trim().length > 0)

  return (
    <Card><CardContent className="py-4 space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">Plan de dezvoltare</p>
        <Badge variant={isFinal ? 'secondary' : 'outline'} className={isFinal ? 'text-green-600' : 'text-amber-600 border-amber-200'}>
          {isFinal ? 'Finalizat' : 'Ciornă'}
        </Badge>
      </div>

      {canEdit && (
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">
            {isFinal ? 'Vizibil pentru angajat.' : 'Ciornă — angajatul nu vede planul până la finalizare.'}
          </p>
          <Button size="sm" variant="ghost" disabled={generateM.isPending} onClick={() => generateM.mutate('ai')}>
            <Sparkles className="h-4 w-4 mr-1" /> Generează cu AI
          </Button>
        </div>
      )}

      <div className="space-y-2">
        <p className="text-sm font-semibold">Obiective de dezvoltare</p>
        {goals.map((g, i) => (
          <div key={i} className="rounded-lg border p-3 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              {canEdit ? (
                <select
                  className="rounded-md border bg-background px-2 py-1 text-sm"
                  value={g.competency_id ?? ''}
                  onChange={(e) => patchGoal(i, { competency_id: e.target.value ? Number(e.target.value) : null })}
                >
                  <option value="">Competență…</option>
                  {competencies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              ) : (
                <span className="text-sm font-medium">{compName(g.competency_id) ?? 'Obiectiv'}</span>
              )}
              {canEdit ? (
                <input
                  type="date"
                  className="rounded-md border bg-background px-2 py-1 text-sm"
                  value={g.target_date ?? ''}
                  onChange={(e) => patchGoal(i, { target_date: e.target.value || null })}
                />
              ) : g.target_date ? <span className="text-xs text-muted-foreground">până la {g.target_date}</span> : null}
              {canEdit && (
                <button className="ml-auto text-muted-foreground hover:text-destructive" onClick={() => setGoals((gs) => gs.filter((_, idx) => idx !== i))}>
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </div>
            {canEdit ? (
              <>
                <Input value={g.title ?? ''} onChange={(e) => patchGoal(i, { title: e.target.value })} placeholder="Obiectiv (ex. Preia rolul de mentor pentru un coleg nou)" />
                <Textarea rows={2} value={g.description ?? ''} onChange={(e) => patchGoal(i, { description: e.target.value })} placeholder="Cum? Acțiuni concrete…" />
              </>
            ) : (
              <>
                {g.title && <p className="text-sm">{g.title}</p>}
                {g.description && <p className="text-sm text-muted-foreground">{g.description}</p>}
              </>
            )}
          </div>
        ))}
        {!goals.length && (
          <p className="text-sm text-muted-foreground">{canEdit ? 'Niciun obiectiv încă — adaugă sau generează cu AI.' : 'Niciun obiectiv de dezvoltare.'}</p>
        )}
        {canEdit && (
          <Button size="sm" variant="ghost" onClick={() => setGoals((gs) => [...gs, { competency_id: null, title: '', description: '', target_date: null }])}>
            <Plus className="h-4 w-4 mr-1" /> Adaugă obiectiv
          </Button>
        )}
      </div>

      {canEdit && (
        <div className="flex items-center gap-2 border-t pt-3">
          <Button size="sm" variant="outline" disabled={saveM.isPending} onClick={() => saveM.mutate(goals)}>Salvează ciorna</Button>
          <Button size="sm" disabled={!canFinalize || finalizeM.isPending} onClick={() => saveM.mutateAsync(goals).then(() => finalizeM.mutate())}>
            Finalizează planul
          </Button>
        </div>
      )}

      {/* Check-ins — schedule progress reviews once the plan exists (feeds D4). */}
      {plan && (canEdit || checkins.length > 0) && (
        <div className="space-y-2 border-t pt-3">
          <p className="text-xs font-medium text-muted-foreground">Check-in-uri</p>
          {checkins.map((c) => (
            <div key={c.id} className="flex items-center justify-between gap-2 text-sm">
              <span className="flex items-center gap-1"><Calendar className="h-3.5 w-3.5 text-muted-foreground" />{c.scheduled_date ?? '—'}</span>
              {c.completed_at
                ? <span className="flex items-center gap-1 text-xs text-green-600"><CheckCircle2 className="h-3.5 w-3.5" />finalizat</span>
                : canEdit
                  ? <Button size="sm" variant="ghost" disabled={completeM.isPending} onClick={() => completeM.mutate(c.id)}>Finalizează</Button>
                  : <span className="text-xs text-muted-foreground">programat</span>}
            </div>
          ))}
          {canEdit && (
            <div className="flex gap-2">
              <Input type="date" value={newCheckin} onChange={(e) => setNewCheckin(e.target.value)} />
              <Button size="sm" variant="outline" disabled={!newCheckin || addCheckinM.isPending} onClick={() => { addCheckinM.mutate(newCheckin); setNewCheckin('') }}>
                <Plus className="h-4 w-4" />
              </Button>
            </div>
          )}
        </div>
      )}
    </CardContent></Card>
  )
}

/** Migrate legacy `{text}` goals to the rich shape and fill defaults. */
function normalize(goals: DevPlanGoal[]): DevPlanGoal[] {
  return goals.map((g) => ({
    competency_id: g.competency_id ?? null,
    title: g.title ?? g.text ?? '',
    description: g.description ?? '',
    target_date: g.target_date ?? null,
  }))
}

function linkedFrom(goals: DevPlanGoal[]): number[] {
  return [...new Set(goals.map((g) => g.competency_id).filter((x): x is number => x != null))]
}
