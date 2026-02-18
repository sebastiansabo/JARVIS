import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog'
import { cn } from '@/lib/utils'
import {
  Pencil, Plus, Trash2, Check, RefreshCw, Link2, Info, Loader2, X,
  ChevronDown, ChevronRight, Sparkles,
} from 'lucide-react'
import { marketingApi } from '@/api/marketing'
import type { MktProjectKpi, MktKeyResult } from '@/types/marketing'

type SuggestedKr = { title: string; target_value: number; unit: string; linked_kpi_id: number | null }

export function OkrCard({ projectId, kpis }: { projectId: number; kpis: MktProjectKpi[] }) {
  const queryClient = useQueryClient()
  const [collapsedIds, setCollapsedIds] = useState<Set<number>>(new Set())
  const [addingObjective, setAddingObjective] = useState(false)
  const [newObjTitle, setNewObjTitle] = useState('')
  const [editingObjId, setEditingObjId] = useState<number | null>(null)
  const [editObjTitle, setEditObjTitle] = useState('')
  const [addingKrForObj, setAddingKrForObj] = useState<number | null>(null)
  const [newKr, setNewKr] = useState({ title: '', target_value: '100', unit: 'number', linked_kpi_id: '' })
  const [editingKrId, setEditingKrId] = useState<number | null>(null)
  const [editKrValue, setEditKrValue] = useState('')
  const [editingKrFull, setEditingKrFull] = useState<{ id: number; title: string; target_value: string; unit: string } | null>(null)
  const [suggestions, setSuggestions] = useState<Record<number, SuggestedKr[]>>({})

  const { data } = useQuery({
    queryKey: ['mkt-objectives', projectId],
    queryFn: () => marketingApi.getObjectives(projectId),
  })
  const objectives = data?.objectives ?? []

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['mkt-objectives', projectId] })

  const createObjMut = useMutation({
    mutationFn: (title: string) => marketingApi.createObjective(projectId, { title }),
    onSuccess: () => { invalidate(); setAddingObjective(false); setNewObjTitle('') },
  })
  const updateObjMut = useMutation({
    mutationFn: ({ id, title }: { id: number; title: string }) => marketingApi.updateObjective(id, { title }),
    onSuccess: () => { invalidate(); setEditingObjId(null) },
  })
  const deleteObjMut = useMutation({
    mutationFn: (id: number) => marketingApi.deleteObjective(id),
    onSuccess: invalidate,
  })
  const createKrMut = useMutation({
    mutationFn: ({ objId, data: d }: { objId: number; data: { title: string; target_value: number; unit: string; linked_kpi_id?: number | null } }) =>
      marketingApi.createKeyResult(objId, d),
    onSuccess: () => { invalidate(); setAddingKrForObj(null); setNewKr({ title: '', target_value: '100', unit: 'number', linked_kpi_id: '' }) },
  })
  const updateKrMut = useMutation({
    mutationFn: ({ id, data: d }: { id: number; data: Partial<MktKeyResult> }) => marketingApi.updateKeyResult(id, d),
    onSuccess: () => { invalidate(); setEditingKrId(null) },
  })
  const deleteKrMut = useMutation({
    mutationFn: (id: number) => marketingApi.deleteKeyResult(id),
    onSuccess: invalidate,
  })
  const syncMut = useMutation({
    mutationFn: () => marketingApi.syncOkrKpis(projectId),
    onSuccess: invalidate,
  })
  const suggestMut = useMutation({
    mutationFn: (objectiveId: number) => marketingApi.suggestKeyResults(projectId, objectiveId),
    onSuccess: (data, objectiveId) => {
      setSuggestions((prev) => ({ ...prev, [objectiveId]: data.suggestions }))
    },
  })

  const acceptSuggestion = (objId: number, suggestion: SuggestedKr) => {
    createKrMut.mutate({ objId, data: suggestion })
    setSuggestions((prev) => {
      const remaining = (prev[objId] ?? []).filter((s) => s !== suggestion)
      if (remaining.length === 0) { const { [objId]: _, ...rest } = prev; return rest }
      return { ...prev, [objId]: remaining }
    })
  }

  const toggleExpand = (id: number) => {
    setCollapsedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const progressColor = (pct: number) =>
    pct >= 100 ? 'bg-green-500' : pct >= 70 ? 'bg-blue-500' : pct >= 40 ? 'bg-yellow-500' : 'bg-red-500'

  const hasLinkedKpis = objectives.some((o) => o.key_results.some((kr) => kr.linked_kpi_id))
  const kpiMap = Object.fromEntries(kpis.map((k) => [k.id, k.kpi_name]))

  return (
    <div className="rounded-lg border p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <h3 className="font-semibold text-sm">Objectives & Key Results</h3>
          <Popover>
            <PopoverTrigger asChild>
              <button className="text-muted-foreground hover:text-foreground">
                <Info className="h-3.5 w-3.5" />
              </button>
            </PopoverTrigger>
            <PopoverContent className="w-80 text-xs" side="right" align="start">
              <div className="space-y-2">
                <p className="font-semibold text-sm">OKR Examples</p>
                <div className="space-y-1.5 pl-3 border-l-2 border-muted">
                  <p className="font-medium">Objective: <span className="font-normal italic">"Increase brand awareness in Bucharest"</span></p>
                  <ul className="list-disc pl-4 space-y-0.5 text-muted-foreground">
                    <li>Reach 50,000 FB impressions (target: 50000, Number)</li>
                    <li>Get 500 page followers (target: 500, Number)</li>
                    <li>CTR above 3% (target: 3, Percentage — link to KPI)</li>
                  </ul>
                </div>
                <div className="space-y-1.5 pl-3 border-l-2 border-muted">
                  <p className="font-medium">Objective: <span className="font-normal italic">"Drive dealer traffic from digital"</span></p>
                  <ul className="list-disc pl-4 space-y-0.5 text-muted-foreground">
                    <li>Generate 200 qualified leads (target: 200, Number)</li>
                    <li>Cost per lead under 5,000 RON (target: 5000, Currency)</li>
                  </ul>
                </div>
                <p className="text-[10px] text-muted-foreground">Tip: Link key results to KPIs for auto-sync. Use the Sparkles button to get AI suggestions.</p>
              </div>
            </PopoverContent>
          </Popover>
        </div>
        <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => setAddingObjective(true)}>
          <Plus className="h-3 w-3 mr-1" /> Add Objective
        </Button>
      </div>

      {objectives.length === 0 && !addingObjective && (
        <p className="text-sm text-muted-foreground">No objectives yet. Add one to start tracking OKRs.</p>
      )}

      <div className="space-y-2">
        {objectives.map((obj) => {
          const expanded = !collapsedIds.has(obj.id)
          const objSuggestions = suggestions[obj.id]
          return (
            <div key={obj.id} className="rounded-lg border">
              {/* Objective header */}
              <div
                className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-muted/50"
                onClick={() => toggleExpand(obj.id)}
              >
                {expanded ? <ChevronDown className="h-3.5 w-3.5 shrink-0" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0" />}
                {editingObjId === obj.id ? (
                  <Input
                    autoFocus
                    value={editObjTitle}
                    onChange={(e) => setEditObjTitle(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && editObjTitle.trim()) updateObjMut.mutate({ id: obj.id, title: editObjTitle.trim() })
                      if (e.key === 'Escape') setEditingObjId(null)
                    }}
                    onBlur={() => { if (editObjTitle.trim() && editObjTitle.trim() !== obj.title) updateObjMut.mutate({ id: obj.id, title: editObjTitle.trim() }); else setEditingObjId(null) }}
                    onClick={(e) => e.stopPropagation()}
                    className="h-7 text-sm font-medium"
                  />
                ) : (
                  <span
                    className="text-sm font-medium flex-1 truncate"
                    onDoubleClick={(e) => { e.stopPropagation(); setEditingObjId(obj.id); setEditObjTitle(obj.title) }}
                  >
                    {obj.title}
                  </span>
                )}
                <span className="text-xs font-medium tabular-nums ml-auto shrink-0">{Math.round(obj.progress)}%</span>
                <div className="w-16 h-1.5 rounded-full bg-muted overflow-hidden shrink-0">
                  <div className={`h-full rounded-full ${progressColor(obj.progress)}`} style={{ width: `${Math.min(obj.progress, 100)}%` }} />
                </div>
                <div className="flex items-center gap-0.5 shrink-0" onClick={(e) => e.stopPropagation()}>
                  <Button
                    variant="ghost" size="sm" className="h-6 w-6 p-0"
                    title="AI Suggest Key Results"
                    disabled={suggestMut.isPending}
                    onClick={() => suggestMut.mutate(obj.id)}
                  >
                    {suggestMut.isPending && suggestMut.variables === obj.id
                      ? <Loader2 className="h-3 w-3 animate-spin" />
                      : <Sparkles className="h-3 w-3 text-amber-500" />}
                  </Button>
                  <Button
                    variant="ghost" size="sm" className="h-6 w-6 p-0"
                    onClick={() => { setEditingObjId(obj.id); setEditObjTitle(obj.title) }}
                  >
                    <Pencil className="h-3 w-3" />
                  </Button>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-destructive hover:text-destructive">
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Delete Objective</AlertDialogTitle>
                        <AlertDialogDescription>
                          This will delete the objective and all its key results. This action cannot be undone.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={() => deleteObjMut.mutate(obj.id)}>Delete</AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </div>

              {/* Key Results */}
              {expanded && (
                <div className="px-3 pb-3 space-y-1.5">
                  {obj.key_results.map((kr) => (
                    <div key={kr.id}>
                      {editingKrFull?.id === kr.id ? (
                        /* Full KR edit row */
                        <div className="flex items-center gap-1.5 py-1">
                          <Input
                            autoFocus
                            value={editingKrFull.title}
                            onChange={(e) => setEditingKrFull((p) => p ? { ...p, title: e.target.value } : p)}
                            className="h-7 text-xs flex-1"
                            placeholder="Key result title"
                            onKeyDown={(e) => {
                              if (e.key === 'Escape') setEditingKrFull(null)
                              if (e.key === 'Enter' && editingKrFull.title.trim()) {
                                updateKrMut.mutate({ id: kr.id, data: { title: editingKrFull.title.trim(), target_value: parseFloat(editingKrFull.target_value) || 100, unit: editingKrFull.unit } })
                                setEditingKrFull(null)
                              }
                            }}
                          />
                          <Input
                            type="number"
                            value={editingKrFull.target_value}
                            onChange={(e) => setEditingKrFull((p) => p ? { ...p, target_value: e.target.value } : p)}
                            className="h-7 text-xs w-20"
                            placeholder="Target"
                          />
                          <Select value={editingKrFull.unit} onValueChange={(v) => setEditingKrFull((p) => p ? { ...p, unit: v } : p)}>
                            <SelectTrigger className="h-7 text-xs w-24"><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="number">Number</SelectItem>
                              <SelectItem value="currency">Currency</SelectItem>
                              <SelectItem value="percentage">%</SelectItem>
                            </SelectContent>
                          </Select>
                          <Button
                            variant="ghost" size="sm" className="h-6 w-6 p-0"
                            onClick={() => {
                              if (editingKrFull.title.trim()) {
                                updateKrMut.mutate({ id: kr.id, data: { title: editingKrFull.title.trim(), target_value: parseFloat(editingKrFull.target_value) || 100, unit: editingKrFull.unit } })
                              }
                              setEditingKrFull(null)
                            }}
                          >
                            <Check className="h-3 w-3 text-green-600" />
                          </Button>
                          <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => setEditingKrFull(null)}>
                            <X className="h-3 w-3" />
                          </Button>
                        </div>
                      ) : (
                        /* Normal KR display row */
                        <div className="flex items-center gap-2 group">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5 text-xs">
                              {kr.linked_kpi_id && <span title={`Linked to KPI: ${kr.linked_kpi_name}`}><Link2 className="h-3 w-3 text-blue-500 shrink-0" /></span>}
                              <span className="truncate text-muted-foreground">{kr.title}</span>
                              <span className="ml-auto tabular-nums font-medium shrink-0">
                                {editingKrId === kr.id ? (
                                  <Input
                                    autoFocus
                                    type="number"
                                    value={editKrValue}
                                    onChange={(e) => setEditKrValue(e.target.value)}
                                    onKeyDown={(e) => {
                                      if (e.key === 'Enter') { updateKrMut.mutate({ id: kr.id, data: { current_value: parseFloat(editKrValue) || 0 } }); setEditingKrId(null) }
                                      if (e.key === 'Escape') setEditingKrId(null)
                                    }}
                                    onBlur={() => { updateKrMut.mutate({ id: kr.id, data: { current_value: parseFloat(editKrValue) || 0 } }); setEditingKrId(null) }}
                                    className="h-5 w-16 text-xs px-1 inline"
                                    onClick={(e) => e.stopPropagation()}
                                  />
                                ) : (
                                  <button
                                    className={cn('hover:underline', kr.linked_kpi_id ? 'cursor-default' : 'cursor-pointer')}
                                    onClick={() => { if (!kr.linked_kpi_id) { setEditingKrId(kr.id); setEditKrValue(String(kr.current_value ?? 0)) } }}
                                    disabled={!!kr.linked_kpi_id}
                                    title={kr.linked_kpi_id ? 'Synced from KPI — click Sync to update' : 'Click to edit value'}
                                  >
                                    {Number(kr.current_value ?? 0).toLocaleString('ro-RO', { maximumFractionDigits: 1 })}
                                  </button>
                                )}
                                <span className="text-muted-foreground">/{Number(kr.target_value ?? 0).toLocaleString('ro-RO')}</span>
                                {kr.unit === 'percentage' && '%'}
                              </span>
                              <span className="text-[10px] tabular-nums w-8 text-right shrink-0">{Math.round(kr.progress)}%</span>
                            </div>
                            <div className="w-full h-1 rounded-full bg-muted overflow-hidden mt-0.5">
                              <div className={`h-full rounded-full ${progressColor(kr.progress)}`} style={{ width: `${Math.min(kr.progress, 100)}%` }} />
                            </div>
                          </div>
                          <Button
                            variant="ghost" size="sm"
                            className="h-5 w-5 p-0 opacity-0 group-hover:opacity-100 shrink-0"
                            onClick={() => setEditingKrFull({ id: kr.id, title: kr.title, target_value: String(kr.target_value ?? 100), unit: kr.unit })}
                          >
                            <Pencil className="h-2.5 w-2.5" />
                          </Button>
                          <Button
                            variant="ghost" size="sm"
                            className="h-5 w-5 p-0 opacity-0 group-hover:opacity-100 text-destructive hover:text-destructive shrink-0"
                            onClick={() => deleteKrMut.mutate(kr.id)}
                          >
                            <Trash2 className="h-2.5 w-2.5" />
                          </Button>
                        </div>
                      )}
                    </div>
                  ))}

                  {/* AI Suggestions */}
                  {objSuggestions && objSuggestions.length > 0 && (
                    <div className="rounded-md border border-amber-200 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-950/20 p-2 space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium flex items-center gap-1 text-amber-700 dark:text-amber-400">
                          <Sparkles className="h-3 w-3" /> AI Suggestions
                        </span>
                        <button className="text-muted-foreground hover:text-foreground" onClick={() => setSuggestions((prev) => { const { [obj.id]: _, ...rest } = prev; return rest })}>
                          <X className="h-3 w-3" />
                        </button>
                      </div>
                      {objSuggestions.map((s, i) => (
                        <div key={i} className="flex items-center gap-2 text-xs">
                          <Button
                            variant="ghost" size="sm" className="h-5 w-5 p-0 shrink-0 text-green-600 hover:text-green-700"
                            onClick={() => acceptSuggestion(obj.id, s)}
                            title="Accept suggestion"
                          >
                            <Check className="h-3 w-3" />
                          </Button>
                          {s.linked_kpi_id && <span title={`Link to: ${kpiMap[s.linked_kpi_id] ?? 'KPI'}`}><Link2 className="h-3 w-3 text-blue-500 shrink-0" /></span>}
                          <span className="flex-1 truncate">{s.title}</span>
                          <span className="tabular-nums text-muted-foreground shrink-0">
                            {s.target_value.toLocaleString('ro-RO')} {s.unit === 'percentage' ? '%' : s.unit === 'currency' ? 'RON' : ''}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Add KR inline form */}
                  {addingKrForObj === obj.id ? (
                    <div className="space-y-2 pt-2 border-t">
                      <Input
                        autoFocus placeholder="Key result title" value={newKr.title}
                        onChange={(e) => setNewKr((p) => ({ ...p, title: e.target.value }))}
                        className="h-9 text-xs"
                        onKeyDown={(e) => {
                          if (e.key === 'Escape') setAddingKrForObj(null)
                        }}
                      />
                      <div className="grid grid-cols-[80px_110px_1fr] gap-2">
                        <Input
                          type="number" placeholder="Target" value={newKr.target_value}
                          onChange={(e) => setNewKr((p) => ({ ...p, target_value: e.target.value }))}
                          className="h-9 text-xs"
                        />
                        <Select value={newKr.unit} onValueChange={(v) => setNewKr((p) => ({ ...p, unit: v }))}>
                          <SelectTrigger className="h-9 text-xs">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="number">Number</SelectItem>
                            <SelectItem value="currency">Currency</SelectItem>
                            <SelectItem value="percentage">Percentage</SelectItem>
                          </SelectContent>
                        </Select>
                        <Select value={newKr.linked_kpi_id} onValueChange={(v) => setNewKr((p) => ({ ...p, linked_kpi_id: v }))}>
                          <SelectTrigger className="h-9 text-xs">
                            <SelectValue placeholder="Link KPI (optional)" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="none">No KPI link</SelectItem>
                            {kpis.map((k) => (
                              <SelectItem key={k.id} value={String(k.id)}>{k.kpi_name}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="flex justify-end gap-1.5">
                        <Button variant="outline" size="sm" className="h-7 text-xs px-3" onClick={() => setAddingKrForObj(null)}>Cancel</Button>
                        <Button
                          size="sm" className="h-7 text-xs px-3"
                          disabled={!newKr.title.trim() || createKrMut.isPending}
                          onClick={() => {
                            const linkedId = newKr.linked_kpi_id && newKr.linked_kpi_id !== 'none' ? parseInt(newKr.linked_kpi_id) : null
                            createKrMut.mutate({
                              objId: obj.id,
                              data: { title: newKr.title.trim(), target_value: parseFloat(newKr.target_value) || 100, unit: newKr.unit, linked_kpi_id: linkedId },
                            })
                          }}
                        >
                          Add
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <button
                      className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 pt-1"
                      onClick={() => { setAddingKrForObj(obj.id); setNewKr({ title: '', target_value: '100', unit: 'number', linked_kpi_id: '' }) }}
                    >
                      <Plus className="h-3 w-3" /> Add Key Result
                    </button>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Add Objective inline */}
      {addingObjective && (
        <div className="flex gap-2">
          <Input
            autoFocus placeholder="Objective title" value={newObjTitle}
            onChange={(e) => setNewObjTitle(e.target.value)}
            className="h-8 text-sm"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && newObjTitle.trim()) createObjMut.mutate(newObjTitle.trim())
              if (e.key === 'Escape') { setAddingObjective(false); setNewObjTitle('') }
            }}
          />
          <Button size="sm" className="h-8" disabled={!newObjTitle.trim() || createObjMut.isPending} onClick={() => createObjMut.mutate(newObjTitle.trim())}>
            Add
          </Button>
          <Button variant="outline" size="sm" className="h-8" onClick={() => { setAddingObjective(false); setNewObjTitle('') }}>
            Cancel
          </Button>
        </div>
      )}

      {/* Sync button */}
      {hasLinkedKpis && (
        <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => syncMut.mutate()} disabled={syncMut.isPending}>
          <RefreshCw className={cn('h-3 w-3 mr-1', syncMut.isPending && 'animate-spin')} />
          Sync KPI Values
        </Button>
      )}
    </div>
  )
}
