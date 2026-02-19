import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Separator } from '@/components/ui/separator'
import { Pencil } from 'lucide-react'
import { marketingApi } from '@/api/marketing'
import type { MktProject } from '@/types/marketing'
import { ApprovalWidget } from '@/components/shared/ApprovalWidget'
import { RichTextEditor, RichTextDisplay } from '@/components/shared/RichTextEditor'
import { OkrCard } from './OkrCard'
import { statusColors, fmt, fmtDate } from './utils'

export function OverviewTab({ project }: { project: MktProject }) {
  const queryClient = useQueryClient()
  const budget = typeof project.total_budget === 'string' ? parseFloat(project.total_budget as string) : (project.total_budget ?? 0)
  const spent = typeof project.total_spent === 'string' ? parseFloat(project.total_spent as string) : (project.total_spent ?? 0)
  const eventCost = typeof project.event_cost === 'string' ? parseFloat(project.event_cost as string) : (project.event_cost ?? 0)
  const budgetSpent = spent - eventCost
  const burn = budget ? Math.round((spent / budget) * 100) : 0

  const [editingDesc, setEditingDesc] = useState(false)
  const [descDraft, setDescDraft] = useState(project.description ?? '')
  const [editingObj, setEditingObj] = useState(false)
  const [objDraft, setObjDraft] = useState(project.objective ?? '')
  const [editingAud, setEditingAud] = useState(false)
  const [audDraft, setAudDraft] = useState(project.target_audience ?? '')
  const [editingRef, setEditingRef] = useState(false)
  const [refDraft, setRefDraft] = useState(project.external_ref ?? '')

  const { data: kpisData } = useQuery({
    queryKey: ['mkt-project-kpis', project.id],
    queryFn: () => marketingApi.getProjectKpis(project.id),
  })
  const overviewKpis = (kpisData?.kpis ?? []).filter((k) => k.show_on_overview)

  const saveMut = useMutation({
    mutationFn: (desc: string) => marketingApi.updateProject(project.id, { description: desc }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-project', project.id] })
      setEditingDesc(false)
    },
  })

  const saveFieldMut = useMutation({
    mutationFn: (fields: Partial<MktProject>) => marketingApi.updateProject(project.id, fields),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-project', project.id] })
      setEditingObj(false)
      setEditingAud(false)
      setEditingRef(false)
    },
  })

  const kpiStatusColors: Record<string, string> = {
    no_data: 'text-gray-500',
    on_track: 'text-green-600',
    at_risk: 'text-yellow-600',
    behind: 'text-red-600',
    exceeded: 'text-emerald-600',
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Left column: details */}
      <div className="lg:col-span-2 space-y-6">
        {/* Budget summary */}
        <div className="rounded-lg border p-4 space-y-3">
          <h3 className="font-semibold text-sm">Budget</h3>
          <div className={`grid gap-4 text-center ${eventCost > 0 ? 'grid-cols-4' : 'grid-cols-3'}`}>
            <div>
              <div className="text-lg font-bold">{fmt(budget, project.currency)}</div>
              <div className="text-xs text-muted-foreground">Total Budget</div>
            </div>
            <div>
              <div className="text-lg font-bold">{fmt(eventCost > 0 ? budgetSpent : spent, project.currency)}</div>
              <div className="text-xs text-muted-foreground">{eventCost > 0 ? 'Budget Spent' : 'Spent'}</div>
            </div>
            {eventCost > 0 && (
              <div>
                <div className="text-lg font-bold">{fmt(eventCost, project.currency)}</div>
                <div className="text-xs text-muted-foreground">Event Costs</div>
              </div>
            )}
            <div>
              <div className={`text-lg font-bold ${burn > 90 ? 'text-red-500' : burn > 70 ? 'text-yellow-500' : ''}`}>{burn}%</div>
              <div className="text-xs text-muted-foreground">Burn Rate</div>
            </div>
          </div>
          <div className="w-full h-2 rounded-full bg-muted overflow-hidden">
            <div
              className={`h-full rounded-full ${burn > 90 ? 'bg-red-500' : burn > 70 ? 'bg-yellow-500' : 'bg-blue-500'}`}
              style={{ width: `${Math.min(burn, 100)}%` }}
            />
          </div>
        </div>

        {/* KPI Overview — only KPIs marked show_on_overview */}
        {overviewKpis.length > 0 && (
          <div className="rounded-lg border p-4 space-y-3">
            <h3 className="font-semibold text-sm">Key Metrics</h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {overviewKpis.map((k) => {
                const target = Number(k.target_value) || 0
                const current = Number(k.current_value) || 0
                const isLowerBetter = k.direction === 'lower'
                const pct = target
                  ? Math.round(isLowerBetter ? (target / Math.max(current, 0.01)) * 100 : (current / target) * 100)
                  : 0
                return (
                  <div key={k.id} className="rounded-lg border p-3 space-y-1">
                    <div className="text-xs text-muted-foreground truncate">{k.kpi_name}</div>
                    <div className="flex items-baseline gap-1.5">
                      <span className="text-lg font-bold tabular-nums">
                        {current.toLocaleString('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}
                        {k.unit === 'percentage' ? '%' : k.unit === 'currency' ? ` ${k.currency || 'RON'}` : ''}
                      </span>
                      {target > 0 && (
                        <span className="text-xs text-muted-foreground">/ {target.toLocaleString('ro-RO')}</span>
                      )}
                    </div>
                    {target > 0 && (
                      <div className="w-full h-1.5 rounded-full bg-muted overflow-hidden">
                        <div
                          className={`h-full rounded-full ${pct >= 100 ? 'bg-green-500' : pct >= 70 ? 'bg-blue-500' : pct >= 40 ? 'bg-yellow-500' : 'bg-red-500'}`}
                          style={{ width: `${Math.min(pct, 100)}%` }}
                        />
                      </div>
                    )}
                    <div className={`text-[10px] font-medium ${kpiStatusColors[k.status] ?? ''}`}>
                      {k.status.replace('_', ' ')}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* OKR Card */}
        <OkrCard projectId={project.id} kpis={kpisData?.kpis ?? []} />

        {/* Project Description — editable */}
        <div className="rounded-lg border p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-sm">Project Description</h3>
            {!editingDesc && (
              <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => { setDescDraft(project.description ?? ''); setEditingDesc(true) }}>
                <Pencil className="h-3 w-3 mr-1" /> Edit
              </Button>
            )}
          </div>
          {editingDesc ? (
            <div className="space-y-2">
              <RichTextEditor
                content={descDraft}
                onChange={setDescDraft}
                placeholder="Add project details, goals, scope, notes..."
              />
              <div className="flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={() => setEditingDesc(false)}>Cancel</Button>
                <Button size="sm" disabled={saveMut.isPending} onClick={() => saveMut.mutate(descDraft)}>
                  {saveMut.isPending ? 'Saving...' : 'Save'}
                </Button>
              </div>
            </div>
          ) : (
            project.description && project.description !== '<p></p>' ? (
              <RichTextDisplay content={project.description} className="text-sm" />
            ) : (
              <p className="text-sm text-muted-foreground">No description yet. Click Edit to add details.</p>
            )
          )}
        </div>

        {/* Objective — always visible, editable */}
        <div className="rounded-lg border p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-sm">Objective *</h3>
            {!editingObj && (
              <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => { setObjDraft(project.objective ?? ''); setEditingObj(true) }}>
                <Pencil className="h-3 w-3 mr-1" /> Edit
              </Button>
            )}
          </div>
          {editingObj ? (
            <div className="space-y-2">
              <Textarea
                value={objDraft}
                onChange={(e) => setObjDraft(e.target.value)}
                placeholder="What does success look like?"
                rows={3}
                className="text-sm"
              />
              <div className="flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={() => setEditingObj(false)}>Cancel</Button>
                <Button size="sm" disabled={saveFieldMut.isPending} onClick={() => saveFieldMut.mutate({ objective: objDraft } as Partial<MktProject>)}>
                  {saveFieldMut.isPending ? 'Saving...' : 'Save'}
                </Button>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground whitespace-pre-wrap">
              {project.objective || 'No objective set. Click Edit to add one.'}
            </p>
          )}
        </div>

        {/* Target Audience — always visible, editable */}
        <div className="rounded-lg border p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-sm">Target Audience *</h3>
            {!editingAud && (
              <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => { setAudDraft(project.target_audience ?? ''); setEditingAud(true) }}>
                <Pencil className="h-3 w-3 mr-1" /> Edit
              </Button>
            )}
          </div>
          {editingAud ? (
            <div className="space-y-2">
              <Input
                value={audDraft}
                onChange={(e) => setAudDraft(e.target.value)}
                placeholder="e.g., Males 25-45, urban, car enthusiasts"
                className="text-sm"
              />
              <div className="flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={() => setEditingAud(false)}>Cancel</Button>
                <Button size="sm" disabled={saveFieldMut.isPending} onClick={() => saveFieldMut.mutate({ target_audience: audDraft } as Partial<MktProject>)}>
                  {saveFieldMut.isPending ? 'Saving...' : 'Save'}
                </Button>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              {project.target_audience || 'No target audience set. Click Edit to add one.'}
            </p>
          )}
        </div>
      </div>

      {/* Right column: metadata */}
      <div className="space-y-4">
        <div className="rounded-lg border p-4 space-y-3 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Status</span>
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${statusColors[project.status] ?? ''}`}>
              {(project.status ?? '').replace('_', ' ')}
            </span>
          </div>
          <Separator />
          <div className="flex justify-between">
            <span className="text-muted-foreground">Type</span>
            <span className="capitalize">{(project.project_type ?? '').replace('_', ' ')}</span>
          </div>
          <Separator />
          <div className="flex justify-between">
            <span className="text-muted-foreground">Start Date</span>
            <span>{fmtDate(project.start_date)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">End Date</span>
            <span>{fmtDate(project.end_date)}</span>
          </div>
          <Separator />
          <div className="flex justify-between">
            <span className="text-muted-foreground">Owner</span>
            <span>{project.owner_name ?? '—'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Created</span>
            <span>{fmtDate(project.created_at)}</span>
          </div>
          <Separator />
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">External Ref</span>
              {!editingRef && (
                <Button variant="ghost" size="sm" className="h-6 px-1.5 text-xs" onClick={() => { setRefDraft(project.external_ref ?? ''); setEditingRef(true) }}>
                  <Pencil className="h-3 w-3" />
                </Button>
              )}
            </div>
            {editingRef ? (
              <div className="space-y-1.5">
                <Input
                  value={refDraft}
                  onChange={(e) => setRefDraft(e.target.value)}
                  placeholder="PO number, agency ref, etc."
                  className="text-sm h-8"
                />
                <div className="flex justify-end gap-1.5">
                  <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setEditingRef(false)}>Cancel</Button>
                  <Button size="sm" className="h-7 text-xs" disabled={saveFieldMut.isPending} onClick={() => saveFieldMut.mutate({ external_ref: refDraft } as Partial<MktProject>)}>
                    {saveFieldMut.isPending ? 'Saving...' : 'Save'}
                  </Button>
                </div>
              </div>
            ) : (
              <span className="text-sm">{project.external_ref || '—'}</span>
            )}
          </div>
        </div>

        {/* Channel Mix */}
        {project.channel_mix?.length > 0 && (
          <div className="rounded-lg border p-4 space-y-2">
            <h3 className="font-semibold text-sm">Channels</h3>
            <div className="flex flex-wrap gap-1.5">
              {project.channel_mix.map((ch) => (
                <Badge key={ch} variant="secondary" className="text-xs">
                  {ch.replace('_', ' ')}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Team preview */}
        {project.members && project.members.length > 0 && (
          <div className="rounded-lg border p-4 space-y-2">
            <h3 className="font-semibold text-sm">Team ({project.members.length})</h3>
            <div className="space-y-1">
              {project.members.slice(0, 5).map((m) => (
                <div key={m.id} className="flex items-center justify-between text-sm">
                  <span>{m.user_name}</span>
                  <Badge variant="outline" className="text-xs">{m.role}</Badge>
                </div>
              ))}
              {project.members.length > 5 && (
                <span className="text-xs text-muted-foreground">+{project.members.length - 5} more</span>
              )}
            </div>
          </div>
        )}

        {/* Approval Status */}
        <div className="rounded-lg border p-4">
          <ApprovalWidget
            entityType="mkt_project"
            entityId={project.id}
            showApproverPicker
            onSubmit={async ({ approverId }) => {
              await marketingApi.submitApproval(project.id, approverId)
            }}
          />
        </div>
      </div>
    </div>
  )
}
