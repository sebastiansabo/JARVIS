import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Plus, ChevronLeft, ChevronRight, Check, Users, Search, X, Building2, FileText, CalendarClock, Network,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import {
  eval360Api, eval360Library, eval360Population,
  type Cycle, type EligibleEmployee, type SincronOrgNode,
} from '@/api/evaluation360'

const STEPS = ['Detalii', 'Participanți', 'Confirmare'] as const

export default function CycleBuilder({ onCreated }: { onCreated: (c: Cycle) => void }) {
  const [open, setOpen] = useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm"><Plus className="h-4 w-4 mr-1" />Ciclu nou</Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl">
        {open && <BuilderBody onDone={(c) => { setOpen(false); onCreated(c) }} onCancel={() => setOpen(false)} />}
      </DialogContent>
    </Dialog>
  )
}

function BuilderBody({ onDone, onCancel }: { onDone: (c: Cycle) => void; onCancel: () => void }) {
  const qc = useQueryClient()
  const [step, setStep] = useState(0)

  // Step 1 — details
  const [name, setName] = useState('')
  const [templateId, setTemplateId] = useState('')
  const [reviewEnd, setReviewEnd] = useState('')
  const [releaseAt, setReleaseAt] = useState('')
  const [autoPeers, setAutoPeers] = useState(4)

  // Step 2 — population
  const [selected, setSelected] = useState<Record<number, EligibleEmployee>>({})
  const [popSource, setPopSource] = useState<'dept' | 'sincron'>('dept')
  const [activeDepts, setActiveDepts] = useState<Set<string>>(new Set())
  const [activeNodes, setActiveNodes] = useState<Set<number>>(new Set())
  const [nodeMembers, setNodeMembers] = useState<Record<number, number[]>>({})
  const [search, setSearch] = useState('')

  const templatesQ = useQuery({ queryKey: ['eval360-templates'], queryFn: () => eval360Library.listTemplates() })
  const templates = (templatesQ.data?.templates ?? []).filter((t) => t.status !== 'archived')
  const publishedExist = templates.some((t) => t.status === 'published')

  const deptQ = useQuery({ queryKey: ['eval360-departments'], queryFn: () => eval360Population.departments() })
  const departments = deptQ.data?.departments ?? []

  const orgQ = useQuery({
    queryKey: ['eval360-sincron-org'],
    queryFn: () => eval360Population.sincronOrgTree(),
    enabled: popSource === 'sincron',
  })
  // Group org nodes by company, preserving the server's ordering.
  const orgByCompany = useMemo(() => {
    const m = new Map<string, SincronOrgNode[]>()
    for (const n of orgQ.data?.nodes ?? []) {
      if (!m.has(n.company_name)) m.set(n.company_name, [])
      m.get(n.company_name)!.push(n)
    }
    return [...m.entries()]
  }, [orgQ.data])

  const searchQ = useQuery({
    queryKey: ['eval360-emp-search', search],
    queryFn: () => eval360Population.eligibleEmployees({ search }),
    enabled: search.trim().length >= 2,
  })

  const selectedList = useMemo(() => Object.values(selected), [selected])
  const selectedCount = selectedList.length

  const toggleDept = async (dept: string) => {
    if (activeDepts.has(dept)) {
      setSelected((prev) => {
        const next = { ...prev }
        for (const id of Object.keys(next)) if (next[Number(id)].department === dept) delete next[Number(id)]
        return next
      })
      setActiveDepts((prev) => { const n = new Set(prev); n.delete(dept); return n })
    } else {
      const { employees } = await qc.fetchQuery({
        queryKey: ['eval360-dept-emps', dept],
        queryFn: () => eval360Population.eligibleEmployees({ department: dept }),
      })
      setSelected((prev) => {
        const next = { ...prev }
        for (const e of employees) next[e.id] = e
        return next
      })
      setActiveDepts((prev) => new Set(prev).add(dept))
    }
  }

  const toggleNode = async (node: SincronOrgNode) => {
    if (activeNodes.has(node.id)) {
      // Remove this node's members, keeping any still contributed by another active node.
      const keep = new Set<number>()
      for (const [nid, ids] of Object.entries(nodeMembers)) {
        if (Number(nid) !== node.id && activeNodes.has(Number(nid))) ids.forEach((i) => keep.add(i))
      }
      const drop = nodeMembers[node.id] || []
      setSelected((prev) => {
        const next = { ...prev }
        for (const id of drop) if (!keep.has(id)) delete next[id]
        return next
      })
      setActiveNodes((prev) => { const s = new Set(prev); s.delete(node.id); return s })
    } else {
      const { employees } = await qc.fetchQuery({
        queryKey: ['eval360-sincron-members', node.id],
        queryFn: () => eval360Population.sincronOrgMembers(node.id),
      })
      setSelected((prev) => {
        const next = { ...prev }
        for (const e of employees) next[e.id] = e
        return next
      })
      setNodeMembers((prev) => ({ ...prev, [node.id]: employees.map((e) => e.id) }))
      setActiveNodes((prev) => new Set(prev).add(node.id))
    }
  }

  const addOne = (e: EligibleEmployee) => setSelected((prev) => ({ ...prev, [e.id]: e }))
  const removeOne = (id: number) => setSelected((prev) => { const n = { ...prev }; delete n[id]; return n })

  const createM = useMutation({
    mutationFn: async () => {
      const { cycle } = await eval360Api.createCycle({
        name: name.trim(),
        template_id: templateId ? Number(templateId) : null,
        timeline: {
          ...(reviewEnd ? { review_end: reviewEnd } : {}),
          ...(releaseAt ? { release_at: releaseAt } : {}),
        },
        participant_ids: selectedList.map((e) => e.id),
      })
      const { generated } = await eval360Api.generateAssignments(cycle.id, autoPeers)
      return { cycle, generated }
    },
    onSuccess: ({ cycle, generated }) => {
      qc.invalidateQueries({ queryKey: ['eval360-cycles'] })
      toast.success(`Ciclu creat · ${generated.assignments} evaluări generate pentru ${generated.subjects} participanți`)
      onDone(cycle)
    },
    onError: () => toast.error('Nu s-a putut crea ciclul'),
  })

  const canNext = step === 0 ? name.trim().length > 0 : step === 1 ? selectedCount > 0 : true

  return (
    <>
      <DialogHeader>
        <DialogTitle>Ciclu de evaluare 360 nou</DialogTitle>
      </DialogHeader>

      {/* Step indicator */}
      <div className="flex items-center gap-2">
        {STEPS.map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <div className={cn(
              'flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold',
              i < step ? 'bg-primary text-primary-foreground'
                : i === step ? 'border-2 border-primary text-primary'
                  : 'border border-muted-foreground/30 text-muted-foreground',
            )}>
              {i < step ? <Check className="h-3.5 w-3.5" /> : i + 1}
            </div>
            <span className={cn('text-xs', i === step ? 'font-medium' : 'text-muted-foreground')}>{s}</span>
            {i < STEPS.length - 1 && <div className="h-px w-6 bg-border" />}
          </div>
        ))}
      </div>

      <div className="max-h-[60vh] overflow-y-auto pr-1">
        {step === 0 && (
          <div className="space-y-4 py-1">
            <div className="space-y-1.5">
              <Label htmlFor="cb-name">Nume ciclu</Label>
              <Input id="cb-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Q3 2026 · Evaluare 360" />
            </div>
            <div className="space-y-1.5">
              <Label className="flex items-center gap-1.5"><FileText className="h-3.5 w-3.5" />Șablon de formular</Label>
              {templatesQ.isLoading ? <Skeleton className="h-9 w-full" /> : (
                <Select value={templateId} onValueChange={setTemplateId}>
                  <SelectTrigger><SelectValue placeholder="Alege un șablon" /></SelectTrigger>
                  <SelectContent>
                    {templates.map((t) => (
                      <SelectItem key={t.id} value={String(t.id)}>
                        {t.name} · v{t.version}{t.status !== 'published' ? ' (ciornă)' : ''}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              {!templatesQ.isLoading && !publishedExist && (
                <p className="text-xs text-amber-600">
                  Niciun șablon publicat. Poți continua, dar formularele vor fi goale până publici un șablon din Bibliotecă.
                </p>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="cb-review-end" className="flex items-center gap-1.5"><CalendarClock className="h-3.5 w-3.5" />Sfârșit evaluare</Label>
                <Input id="cb-review-end" type="date" value={reviewEnd} onChange={(e) => setReviewEnd(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="cb-release">Publicare rapoarte</Label>
                <Input id="cb-release" type="date" value={releaseAt} onChange={(e) => setReleaseAt(e.target.value)} />
              </div>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-4 py-1">
            <div>
              {/* Source toggle: free-text departments vs the Sincron organigram */}
              <div className="mb-3 inline-flex rounded-lg border bg-muted/40 p-0.5 text-sm">
                <button type="button" onClick={() => setPopSource('dept')}
                  className={cn('flex items-center gap-1.5 rounded-md px-3 py-1.5 font-medium transition-colors',
                    popSource === 'dept' ? 'bg-background shadow-sm' : 'text-muted-foreground hover:text-foreground')}>
                  <Building2 className="h-4 w-4" />Departamente
                </button>
                <button type="button" onClick={() => setPopSource('sincron')}
                  className={cn('flex items-center gap-1.5 rounded-md px-3 py-1.5 font-medium transition-colors',
                    popSource === 'sincron' ? 'bg-background shadow-sm' : 'text-muted-foreground hover:text-foreground')}>
                  <Network className="h-4 w-4" />Organigramă Sincron
                </button>
              </div>

              {popSource === 'sincron' ? (
                orgQ.isLoading ? <Skeleton className="h-24 w-full" />
                  : orgByCompany.length === 0 ? (
                    <p className="py-3 text-sm text-muted-foreground">
                      Organigrama Sincron nu are noduri în această bază de date.
                    </p>
                  ) : (
                    <div className="space-y-3">
                      {orgByCompany.map(([company, nodes]) => (
                        <div key={company}>
                          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{company}</p>
                          <div className="flex flex-wrap gap-2">
                            {nodes.map((n) => {
                              const on = activeNodes.has(n.id)
                              const empty = n.member_count === 0
                              return (
                                <button key={n.id} type="button" disabled={empty}
                                  onClick={() => toggleNode(n)}
                                  style={{ marginLeft: (n.level - 1) * 12 }}
                                  className={cn(
                                    'flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition-colors',
                                    empty ? 'cursor-not-allowed opacity-40'
                                      : on ? 'border-primary bg-primary/10 text-primary' : 'hover:bg-muted',
                                  )}>
                                  {on && <Check className="h-3.5 w-3.5" />}{n.name}
                                  <span className="rounded-full bg-muted px-1.5 text-[10px] tabular-nums text-muted-foreground">{n.member_count}</span>
                                </button>
                              )
                            })}
                          </div>
                        </div>
                      ))}
                    </div>
                  )
              ) : (
                deptQ.isLoading ? <Skeleton className="h-16 w-full" /> : (
                  <div className="flex flex-wrap gap-2">
                    {departments.map((d) => {
                      const on = activeDepts.has(d.department)
                      return (
                        <button
                          key={d.department}
                          type="button"
                          onClick={() => toggleDept(d.department)}
                          className={cn(
                            'flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition-colors',
                            on ? 'border-primary bg-primary/10 text-primary' : 'hover:bg-muted',
                          )}
                        >
                          {on && <Check className="h-3.5 w-3.5" />}{d.department}
                          <span className="rounded-full bg-muted px-1.5 text-[10px] tabular-nums text-muted-foreground">{d.count}</span>
                        </button>
                      )
                    })}
                  </div>
                )
              )}
            </div>

            <div>
              <Label className="flex items-center gap-1.5"><Search className="h-3.5 w-3.5" />Sau caută persoane</Label>
              <Input className="mt-2" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Scrie un nume (min. 2 litere)…" />
              {search.trim().length >= 2 && (
                <div className="mt-2 max-h-40 overflow-y-auto rounded-lg border divide-y">
                  {searchQ.isLoading ? <div className="p-3"><Skeleton className="h-4 w-32" /></div>
                    : (searchQ.data?.employees ?? []).length === 0 ? (
                      <p className="p-3 text-sm text-muted-foreground">Niciun rezultat.</p>
                    ) : (searchQ.data?.employees ?? []).map((e) => (
                      <button key={e.id} type="button" onClick={() => addOne(e)}
                        className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-muted/50">
                        <span>{e.name}<span className="ml-2 text-xs text-muted-foreground">{e.department}</span></span>
                        {selected[e.id] ? <Check className="h-4 w-4 text-green-600" /> : <Plus className="h-4 w-4 text-muted-foreground" />}
                      </button>
                    ))}
                </div>
              )}
            </div>

            <div>
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">Selectați ({selectedCount})</p>
                {selectedCount > 0 && (
                  <Button variant="ghost" size="sm" className="h-7 text-xs text-muted-foreground"
                    onClick={() => { setSelected({}); setActiveDepts(new Set()); setActiveNodes(new Set()); setNodeMembers({}) }}>
                    Golește
                  </Button>
                )}
              </div>
              {selectedCount === 0 ? (
                <p className="py-3 text-sm text-muted-foreground">Niciun participant selectat încă.</p>
              ) : (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {selectedList.map((e) => (
                    <span key={e.id} className="flex items-center gap-1 rounded-full bg-muted px-2.5 py-1 text-xs">
                      {e.name}
                      <button type="button" onClick={() => removeOne(e.id)} className="text-muted-foreground hover:text-destructive">
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4 py-1">
            <div className="rounded-xl border divide-y">
              <SummaryRow label="Nume" value={name || '—'} />
              <SummaryRow label="Șablon" value={templates.find((t) => String(t.id) === templateId)?.name ?? 'Fără șablon'} />
              <SummaryRow label="Participanți" value={`${selectedCount}`} icon={<Users className="h-3.5 w-3.5" />} />
              <SummaryRow label="Sfârșit evaluare" value={reviewEnd || '—'} />
              <SummaryRow label="Publicare" value={releaseAt || '—'} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cb-peers">Colegi (peers) per participant</Label>
              <Input id="cb-peers" type="number" min={0} max={8} value={autoPeers}
                onChange={(e) => setAutoPeers(Math.max(0, Math.min(8, Number(e.target.value) || 0)))} className="w-24" />
              <p className="text-xs text-muted-foreground">
                Se generează automat: autoevaluare + {autoPeers} colegi din același departament + subordonații direcți (dacă există).
                Reviewerii sunt invitați imediat; ciclul rămâne în <span className="font-medium">Draft</span> până îl activezi.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Footer nav */}
      <div className="flex items-center justify-between border-t pt-3">
        <Button variant="ghost" size="sm" onClick={step === 0 ? onCancel : () => setStep((s) => s - 1)}>
          {step === 0 ? 'Anulează' : <><ChevronLeft className="h-4 w-4 mr-1" />Înapoi</>}
        </Button>
        {step < 2 ? (
          <Button size="sm" disabled={!canNext} onClick={() => setStep((s) => s + 1)}>
            Continuă<ChevronRight className="h-4 w-4 ml-1" />
          </Button>
        ) : (
          <Button size="sm" disabled={createM.isPending || selectedCount === 0} onClick={() => createM.mutate()}>
            {createM.isPending ? 'Se creează…' : 'Creează + generează evaluări'}
          </Button>
        )}
      </div>
    </>
  )
}

function SummaryRow({ label, value, icon }: { label: string; value: string; icon?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between px-3 py-2.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="flex items-center gap-1.5 font-medium">{icon}{value}</span>
    </div>
  )
}
