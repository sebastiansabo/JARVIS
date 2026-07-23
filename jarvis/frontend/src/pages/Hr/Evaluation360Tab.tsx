import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Target, Plus, AlertTriangle, ShieldCheck, ChevronRight, Users, CheckCircle2, XCircle,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { StatCard } from '@/components/shared/StatCard'
import { cn } from '@/lib/utils'
import {
  eval360Api, NEXT_STATES, STATUS_LABEL, type Cycle, type CycleStatus,
} from '@/api/evaluation360'

function statusBadgeClass(status: CycleStatus): string {
  switch (status) {
    case 'active': return 'bg-green-100 text-green-700 border-green-200 dark:bg-green-950/40 dark:text-green-400'
    case 'draft':
    case 'nomination': return 'bg-muted text-muted-foreground'
    case 'calibration': return 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-400'
    case 'released': return 'bg-violet-100 text-violet-700 border-violet-200 dark:bg-violet-950/40 dark:text-violet-400'
    default: return 'bg-muted text-muted-foreground'
  }
}

export default function Evaluation360Tab({ search }: { search?: string }) {
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState<number | null>(null)

  const cyclesQ = useQuery({ queryKey: ['eval360-cycles'], queryFn: () => eval360Api.listCycles() })
  const cycles = useMemo(() => cyclesQ.data?.cycles ?? [], [cyclesQ.data])
  const filtered = useMemo(
    () => (search ? cycles.filter((c) => c.name.toLowerCase().includes(search.toLowerCase())) : cycles),
    [cycles, search],
  )

  // Default the selection to the first cycle once loaded.
  useEffect(() => {
    if (selectedId == null && cycles.length) setSelectedId(cycles[0].id)
  }, [cycles, selectedId])

  const selected = cycles.find((c) => c.id === selectedId) ?? null

  const progressQ = useQuery({
    queryKey: ['eval360-progress', selectedId],
    queryFn: () => eval360Api.progress(selectedId!),
    enabled: selectedId != null,
  })
  const dryRunQ = useQuery({
    queryKey: ['eval360-dryrun', selectedId],
    queryFn: () => eval360Api.dryRun(selectedId!),
    enabled: selectedId != null,
  })

  const transitionM = useMutation({
    mutationFn: ({ id, target, waive }: { id: number; target: CycleStatus; waive?: boolean }) =>
      eval360Api.transition(id, target, waive),
    onSuccess: () => {
      toast.success('Ciclu actualizat')
      qc.invalidateQueries({ queryKey: ['eval360-cycles'] })
      qc.invalidateQueries({ queryKey: ['eval360-progress', selectedId] })
    },
    onError: (e: unknown) => {
      const msg = e && typeof e === 'object' && 'data' in e
        ? String((e as { data?: { error?: string } }).data?.error ?? 'Eroare')
        : 'Eroare'
      toast.error(msg)
    },
  })

  if (cyclesQ.isLoading) {
    return <div className="space-y-3"><Skeleton className="h-24 w-full" /><Skeleton className="h-40 w-full" /></div>
  }

  if (!cycles.length) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-16 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-full bg-muted">
          <Target className="h-7 w-7 text-muted-foreground/50" />
        </div>
        <div>
          <p className="text-sm font-medium">Niciun ciclu de evaluare 360</p>
          <p className="text-sm text-muted-foreground">Creează primul ciclu pentru a începe.</p>
        </div>
        <CreateCycleDialog onCreated={(c) => { setSelectedId(c.id); qc.invalidateQueries({ queryKey: ['eval360-cycles'] }) }} />
      </div>
    )
  }

  const progress = progressQ.data?.progress
  const dryRun = dryRunQ.data?.dry_run

  return (
    <div className="space-y-4">
      {/* Cycle selector + create */}
      <div className="flex items-center gap-2">
        <Select value={selectedId ? String(selectedId) : ''} onValueChange={(v) => setSelectedId(Number(v))}>
          <SelectTrigger className="w-full max-w-sm"><SelectValue placeholder="Alege un ciclu" /></SelectTrigger>
          <SelectContent>
            {filtered.map((c) => (
              <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <CreateCycleDialog onCreated={(c) => { setSelectedId(c.id); qc.invalidateQueries({ queryKey: ['eval360-cycles'] }) }} />
      </div>

      {selected && (
        <>
          {/* Header: status + advance controls */}
          <Card>
            <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-lg font-semibold tracking-tight">{selected.name}</h2>
                  <Badge variant="outline" className={cn('capitalize', statusBadgeClass(selected.status))}>
                    {STATUS_LABEL[selected.status]}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Centru de control — doar status. Conținutul răspunsurilor nu este vizibil administratorilor.
                  {selected.release_at ? ` · publicare ${selected.release_at}` : ''}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {NEXT_STATES[selected.status].map((target) => (
                  <Button
                    key={target}
                    size="sm"
                    variant={target === 'released' ? 'default' : 'outline'}
                    disabled={transitionM.isPending}
                    onClick={() => transitionM.mutate({ id: selected.id, target })}
                  >
                    → {STATUS_LABEL[target]}
                  </Button>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Stat tiles */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard
              title="Evaluări trimise"
              value={progress ? `${progress.completion_pct}%` : '—'}
              icon={<CheckCircle2 />}
              description={progress ? `${progress.submitted}/${progress.total} trimise` : undefined}
              isLoading={progressQ.isLoading}
            />
            <StatCard
              title="Total evaluatori"
              value={progress ? progress.total : '—'}
              icon={<Users />}
              isLoading={progressQ.isLoading}
            />
            <StatCard
              title="Refuzuri"
              value={progress ? progress.declines_pending : '—'}
              icon={<XCircle />}
              description={progress?.declines_pending ? 'de reînlocuit' : undefined}
              isLoading={progressQ.isLoading}
            />
            <StatCard
              title="Departamente"
              value={progress ? progress.by_department.length : '—'}
              icon={<Target />}
              isLoading={progressQ.isLoading}
            />
          </div>

          {/* Completion by department */}
          <Card>
            <CardContent className="py-4">
              <p className="text-sm font-semibold mb-3">Completare pe departament</p>
              {progressQ.isLoading ? (
                <Skeleton className="h-24 w-full" />
              ) : progress && progress.by_department.length ? (
                <div className="space-y-2.5">
                  {progress.by_department.map((d) => {
                    const behind = d.completion_pct < 70
                    return (
                      <div key={d.department} className="flex items-center gap-3">
                        <span className="w-28 shrink-0 truncate text-sm">{d.department}</span>
                        <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-muted">
                          <div
                            className={cn('h-full rounded-full', behind ? 'bg-orange-500' : 'bg-blue-500')}
                            style={{ width: `${Math.max(2, d.completion_pct)}%` }}
                          />
                        </div>
                        <span className="w-20 shrink-0 text-right text-sm font-semibold tabular-nums">
                          {d.completion_pct}%
                          <span className="ml-1 text-xs font-normal text-muted-foreground">{d.submitted}/{d.total}</span>
                        </span>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  Fără evaluatori alocați încă — repartizează nominalizările pentru a vedea progresul.
                </p>
              )}
            </CardContent>
          </Card>

          {/* Cycle health checks */}
          <Card>
            <CardContent className="py-4">
              <p className="text-sm font-semibold">Verificări de sănătate</p>
              <p className="text-xs text-muted-foreground mb-3">Validare dry-run</p>
              <div className="divide-y divide-border/60">
                <HealthRow
                  label="Participanți cu < 3 colegi eligibili"
                  ok={!dryRun || dryRun.participants_missing_peers.length === 0}
                  loading={dryRunQ.isLoading}
                  bad={dryRun ? `${dryRun.participants_missing_peers.length} semnalate — realocă` : ''}
                  good="OK"
                />
                <HealthRow
                  label="Încărcare evaluator > 8 alocări"
                  ok={!dryRun || dryRun.overloaded_reviewers.length === 0}
                  loading={dryRunQ.isLoading}
                  warn
                  bad={dryRun ? `${dryRun.overloaded_reviewers.length} supraîncărcați` : ''}
                  good="OK"
                />
                <HealthRow
                  label="Prag anonimat (min n=3)"
                  ok
                  loading={false}
                  good="Blocat · impus"
                  icon={<ShieldCheck className="h-3.5 w-3.5" />}
                />
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

function HealthRow({
  label, ok, loading, bad, good, warn, icon,
}: {
  label: string; ok: boolean; loading: boolean; bad?: string; good: string; warn?: boolean; icon?: ReactNode
}) {
  return (
    <div className="flex items-center justify-between py-2.5 text-sm">
      <span>{label}</span>
      {loading ? (
        <Skeleton className="h-4 w-24" />
      ) : ok ? (
        <span className="flex items-center gap-1 font-medium text-green-600">
          {icon ?? <CheckCircle2 className="h-3.5 w-3.5" />}{good}
        </span>
      ) : (
        <span className={cn('flex items-center gap-1 font-medium', warn ? 'text-orange-600' : 'text-red-600')}>
          <AlertTriangle className="h-3.5 w-3.5" />{bad}
        </span>
      )}
    </div>
  )
}

function CreateCycleDialog({ onCreated }: { onCreated: (c: Cycle) => void }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [reviewEnd, setReviewEnd] = useState('')
  const [releaseAt, setReleaseAt] = useState('')

  const createM = useMutation({
    mutationFn: () => eval360Api.createCycle({
      name: name.trim(),
      timeline: {
        ...(reviewEnd ? { review_end: reviewEnd } : {}),
        ...(releaseAt ? { release_at: releaseAt } : {}),
      },
    }),
    onSuccess: (res) => {
      toast.success('Ciclu creat')
      setOpen(false); setName(''); setReviewEnd(''); setReleaseAt('')
      onCreated(res.cycle)
    },
    onError: () => toast.error('Nu s-a putut crea ciclul'),
  })

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm"><Plus className="h-4 w-4 mr-1" />Ciclu nou</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Ciclu de evaluare 360 nou</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="cycle-name">Nume</Label>
            <Input id="cycle-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Q3 2026 · Evaluare 360" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="cycle-review-end">Sfârșit evaluare</Label>
              <Input id="cycle-review-end" type="date" value={reviewEnd} onChange={(e) => setReviewEnd(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cycle-release">Publicare</Label>
              <Input id="cycle-release" type="date" value={releaseAt} onChange={(e) => setReleaseAt(e.target.value)} />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>Anulează</Button>
          <Button disabled={!name.trim() || createM.isPending} onClick={() => createM.mutate()}>
            Creează<ChevronRight className="h-4 w-4 ml-1" />
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
