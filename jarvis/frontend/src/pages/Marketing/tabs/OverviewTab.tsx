import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { Separator } from '@/components/ui/separator'
import { Pencil } from 'lucide-react'
import { marketingApi } from '@/api/marketing'
import type { MktProject } from '@/types/marketing'
import { ApprovalWidget } from '@/components/shared/ApprovalWidget'
import { OkrCard } from './OkrCard'
import { statusColors, fmt, fmtDate } from './utils'

export function OverviewTab({ project }: { project: MktProject }) {
  const queryClient = useQueryClient()
  const budget = typeof project.total_budget === 'string' ? parseFloat(project.total_budget as string) : (project.total_budget ?? 0)
  const spent = typeof project.total_spent === 'string' ? parseFloat(project.total_spent as string) : (project.total_spent ?? 0)
  const burn = budget ? Math.round((spent / budget) * 100) : 0

  const [editingDesc, setEditingDesc] = useState(false)
  const [descDraft, setDescDraft] = useState(project.description ?? '')

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
          <div className="grid grid-cols-3 gap-4 text-center">
            <div>
              <div className="text-lg font-bold">{fmt(budget, project.currency)}</div>
              <div className="text-xs text-muted-foreground">Total Budget</div>
            </div>
            <div>
              <div className="text-lg font-bold">{fmt(spent, project.currency)}</div>
              <div className="text-xs text-muted-foreground">Spent</div>
            </div>
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
              <Textarea
                value={descDraft}
                onChange={(e) => setDescDraft(e.target.value)}
                placeholder="Add project details, goals, scope, notes..."
                rows={6}
                className="text-sm"
              />
              <div className="flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={() => setEditingDesc(false)}>Cancel</Button>
                <Button size="sm" disabled={saveMut.isPending} onClick={() => saveMut.mutate(descDraft)}>
                  {saveMut.isPending ? 'Saving...' : 'Save'}
                </Button>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground whitespace-pre-wrap">
              {project.description || 'No description yet. Click Edit to add details.'}
            </p>
          )}
        </div>

        {/* Objective & Audience */}
        {project.objective && (
          <div className="space-y-1">
            <h3 className="font-semibold text-sm">Objective</h3>
            <p className="text-sm text-muted-foreground whitespace-pre-wrap">{project.objective}</p>
          </div>
        )}
        {project.target_audience && (
          <div className="space-y-1">
            <h3 className="font-semibold text-sm">Target Audience</h3>
            <p className="text-sm text-muted-foreground">{project.target_audience}</p>
          </div>
        )}
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
          {project.external_ref && (
            <>
              <Separator />
              <div className="flex justify-between">
                <span className="text-muted-foreground">External Ref</span>
                <span>{project.external_ref}</span>
              </div>
            </>
          )}
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
