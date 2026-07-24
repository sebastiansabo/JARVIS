import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus, X, CheckCircle2, Calendar } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { eval360DevPlan, type DevPlanGoal } from '@/api/evaluation360'

/** Development plan (goals + check-ins). Editable by the participant's manager
 *  and HR only; the participant sees it read-only (server-enforced via can_edit). */
export function DevPlan({ cycleId, employeeId }: { cycleId: number; employeeId: number }) {
  const qc = useQueryClient()
  const q = useQuery({
    queryKey: ['eval360-devplan', cycleId, employeeId],
    queryFn: () => eval360DevPlan.get(cycleId, employeeId),
  })
  const [goals, setGoals] = useState<DevPlanGoal[]>([])
  const [newGoal, setNewGoal] = useState('')
  const [newCheckin, setNewCheckin] = useState('')

  useEffect(() => { if (q.data?.plan) setGoals(q.data.plan.goals ?? []) }, [q.data])

  const invalidate = () => qc.invalidateQueries({ queryKey: ['eval360-devplan', cycleId, employeeId] })
  const saveM = useMutation({
    mutationFn: (g: DevPlanGoal[]) => eval360DevPlan.save(cycleId, employeeId, g, []),
    onSuccess: () => { toast.success('Plan salvat'); invalidate() },
    onError: () => toast.error('Nu s-a putut salva'),
  })
  const addCheckinM = useMutation({
    mutationFn: (date: string) => eval360DevPlan.addCheckin(q.data!.plan!.id, date),
    onSuccess: () => { toast.success('Check-in adăugat'); invalidate() },
  })
  const completeM = useMutation({
    mutationFn: (id: number) => eval360DevPlan.completeCheckin(id),
    onSuccess: () => { toast.success('Check-in finalizat'); invalidate() },
  })

  if (q.isLoading) return <Skeleton className="h-40 w-full" />

  const plan = q.data?.plan
  const checkins = q.data?.checkins ?? []
  const canEdit = q.data?.can_edit ?? false

  const addGoal = () => {
    if (!newGoal.trim()) return
    const g = [...goals, { text: newGoal.trim() }]
    setGoals(g); setNewGoal(''); saveM.mutate(g)
  }
  const removeGoal = (i: number) => {
    const g = goals.filter((_, idx) => idx !== i)
    setGoals(g); saveM.mutate(g)
  }

  return (
    <Card><CardContent className="py-4 space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">Plan de dezvoltare</p>
        {!canEdit && <span className="text-xs text-muted-foreground">Gestionat de manager / HR</span>}
      </div>

      <div className="space-y-2">
        {goals.map((g, i) => (
          <div key={i} className="flex items-center gap-2">
            <span className="flex-1 text-sm">{g.text}</span>
            {canEdit && <button onClick={() => removeGoal(i)} className="text-muted-foreground hover:text-destructive"><X className="h-4 w-4" /></button>}
          </div>
        ))}
        {!goals.length && !canEdit && <p className="text-sm text-muted-foreground">Niciun obiectiv de dezvoltare încă.</p>}
        {canEdit && (
          <div className="flex gap-2">
            <Input value={newGoal} onChange={(e) => setNewGoal(e.target.value)} placeholder="Un obiectiv de dezvoltare…" onKeyDown={(e) => e.key === 'Enter' && addGoal()} />
            <Button size="sm" variant="outline" onClick={addGoal}><Plus className="h-4 w-4" /></Button>
          </div>
        )}
      </div>

      {plan && (
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
          {!checkins.length && !canEdit && <p className="text-sm text-muted-foreground">Niciun check-in programat.</p>}
          {canEdit && (
            <div className="flex gap-2">
              <Input type="date" value={newCheckin} onChange={(e) => setNewCheckin(e.target.value)} />
              <Button size="sm" variant="outline" disabled={!newCheckin || addCheckinM.isPending} onClick={() => { addCheckinM.mutate(newCheckin); setNewCheckin('') }}><Plus className="h-4 w-4" /></Button>
            </div>
          )}
        </div>
      )}
    </CardContent></Card>
  )
}
