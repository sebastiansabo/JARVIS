import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Pencil, GripVertical, ChevronDown, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { toast } from 'sonner'
import { approvalsApi } from '@/api/approvals'
import { rolesApi } from '@/api/roles'
import { usersApi } from '@/api/users'
import { organizationApi } from '@/api/organization'
import type { ApprovalFlow, ApprovalStep } from '@/types/approvals'
import type { Role } from '@/types/roles'
import type { UserDetail } from '@/types/users'
import type { DepartmentStructure } from '@/types/organization'

const ENTITY_TYPES = [
  { value: 'invoice', label: 'Invoice' },
  { value: 'efactura_invoice', label: 'e-Factura Invoice' },
  { value: 'transaction', label: 'Bank Transaction' },
  { value: 'event', label: 'HR Event' },
  { value: 'bonus', label: 'HR Bonus' },
  { value: 'employee', label: 'Employee' },
]

const APPROVER_TYPES = [
  { value: 'user', label: 'Specific User' },
  { value: 'role', label: 'Role' },
  { value: 'department_manager', label: 'Department Manager' },
]

export default function ApprovalsTab() {
  return (
    <div className="space-y-6">
      <FlowsSection />
    </div>
  )
}

function FlowsSection() {
  const queryClient = useQueryClient()
  const [showFlowDialog, setShowFlowDialog] = useState(false)
  const [editFlow, setEditFlow] = useState<ApprovalFlow | null>(null)
  const [deleteFlowId, setDeleteFlowId] = useState<number | null>(null)
  const [expandedFlowId, setExpandedFlowId] = useState<number | null>(null)

  const { data: flowsData, isLoading } = useQuery({
    queryKey: ['settings', 'approval-flows'],
    queryFn: () => approvalsApi.getFlows(false),
  })
  const flows = flowsData?.flows ?? []

  const deleteMutation = useMutation({
    mutationFn: (id: number) => approvalsApi.deleteFlow(id),
    onSuccess: () => {
      toast.success('Flow deactivated')
      setDeleteFlowId(null)
      queryClient.invalidateQueries({ queryKey: ['settings', 'approval-flows'] })
    },
    onError: () => toast.error('Failed to deactivate flow'),
  })

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Approval Flows</CardTitle>
          <CardDescription>Configure approval workflows for different entity types</CardDescription>
        </div>
        <Button size="sm" onClick={() => { setEditFlow(null); setShowFlowDialog(true) }}>
          <Plus className="mr-1.5 h-4 w-4" />
          New Flow
        </Button>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading...</div>
        ) : flows.length === 0 ? (
          <EmptyState
            title="No approval flows"
            description="Create a flow to define approval workflows"
          />
        ) : (
          <div className="space-y-2">
            {flows.map((flow) => (
              <div key={flow.id} className="rounded-md border">
                <div
                  className="flex cursor-pointer items-center gap-3 px-4 py-3"
                  onClick={() => setExpandedFlowId(expandedFlowId === flow.id ? null : flow.id)}
                >
                  {expandedFlowId === flow.id ? (
                    <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
                  ) : (
                    <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm">{flow.name}</span>
                      <Badge variant={flow.is_active ? 'default' : 'secondary'} className="text-xs">
                        {flow.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                      <Badge variant="outline" className="text-xs">{flow.entity_type}</Badge>
                    </div>
                    {flow.description && (
                      <p className="mt-0.5 text-xs text-muted-foreground">{flow.description}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 px-2"
                      onClick={() => { setEditFlow(flow); setShowFlowDialog(true) }}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 px-2 text-destructive hover:text-destructive"
                      onClick={() => setDeleteFlowId(flow.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
                {expandedFlowId === flow.id && (
                  <div className="border-t px-4 py-3">
                    <StepsEditor flowId={flow.id} />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>

      {showFlowDialog && (
        <FlowDialog
          flow={editFlow}
          open={showFlowDialog}
          onClose={() => { setShowFlowDialog(false); setEditFlow(null) }}
        />
      )}

      <ConfirmDialog
        open={deleteFlowId !== null}
        onOpenChange={() => setDeleteFlowId(null)}
        title="Deactivate Flow"
        description="This will deactivate the flow. Existing pending requests will continue to completion."
        onConfirm={() => deleteFlowId && deleteMutation.mutate(deleteFlowId)}
        variant="destructive"
      />
    </Card>
  )
}

// ── Flow Create/Edit Dialog ──

interface FlowDialogProps {
  flow: ApprovalFlow | null
  open: boolean
  onClose: () => void
}

function FlowDialog({ flow, open, onClose }: FlowDialogProps) {
  const queryClient = useQueryClient()
  const isEdit = flow !== null

  const { data: structure = [] } = useQuery({
    queryKey: ['organization-structure'],
    queryFn: () => organizationApi.getStructure(),
  })

  const companies = [...new Set(structure.map((s: DepartmentStructure) => s.company))]

  const [form, setForm] = useState({
    name: flow?.name ?? '',
    slug: flow?.slug ?? '',
    entity_type: flow?.entity_type ?? '',
    description: flow?.description ?? '',
    priority: flow?.priority ?? 0,
    auto_reject_after_hours: flow?.auto_reject_after_hours ?? '',
    is_active: flow?.is_active ?? true,
  })

  const createMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => approvalsApi.createFlow(data as Partial<ApprovalFlow>),
    onSuccess: () => {
      toast.success('Flow created')
      queryClient.invalidateQueries({ queryKey: ['settings', 'approval-flows'] })
      onClose()
    },
    onError: () => toast.error('Failed to create flow'),
  })

  const updateMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => approvalsApi.updateFlow(flow!.id, data as Partial<ApprovalFlow>),
    onSuccess: () => {
      toast.success('Flow updated')
      queryClient.invalidateQueries({ queryKey: ['settings', 'approval-flows'] })
      onClose()
    },
    onError: () => toast.error('Failed to update flow'),
  })

  const autoSlug = (name: string) => name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

  const handleSave = () => {
    if (!form.name || !form.slug || !form.entity_type) {
      toast.error('Name, slug, and entity type are required')
      return
    }
    const data: Record<string, unknown> = {
      name: form.name,
      slug: form.slug,
      entity_type: form.entity_type,
      description: form.description || null,
      priority: Number(form.priority) || 0,
      auto_reject_after_hours: form.auto_reject_after_hours ? Number(form.auto_reject_after_hours) : null,
      is_active: form.is_active,
    }
    if (isEdit) {
      updateMutation.mutate(data)
    } else {
      createMutation.mutate(data)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit Flow' : 'New Approval Flow'}</DialogTitle>
          <DialogDescription>
            Define when this flow triggers and how approvals are routed.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Name</Label>
              <Input
                value={form.name}
                onChange={(e) => {
                  const name = e.target.value
                  setForm(f => ({ ...f, name, slug: isEdit ? f.slug : autoSlug(name) }))
                }}
                placeholder="Invoice Approval"
              />
            </div>
            <div>
              <Label>Slug</Label>
              <Input
                value={form.slug}
                onChange={(e) => setForm(f => ({ ...f, slug: e.target.value }))}
                placeholder="invoice-approval"
              />
            </div>
          </div>
          <div>
            <Label>Entity Type</Label>
            <Select value={form.entity_type} onValueChange={(v) => setForm(f => ({ ...f, entity_type: v }))}>
              <SelectTrigger><SelectValue placeholder="Select entity type" /></SelectTrigger>
              <SelectContent>
                {ENTITY_TYPES.map(et => (
                  <SelectItem key={et.value} value={et.value}>{et.label}</SelectItem>
                ))}
                {companies.map(c => (
                  <SelectItem key={`company:${c}`} value={`company:${c}`}>{c} (Company)</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Description</Label>
            <Textarea
              value={form.description}
              onChange={(e) => setForm(f => ({ ...f, description: e.target.value }))}
              placeholder="Optional description..."
              rows={2}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Priority (higher = checked first)</Label>
              <Input
                type="number"
                value={form.priority}
                onChange={(e) => setForm(f => ({ ...f, priority: Number(e.target.value) }))}
              />
            </div>
            <div>
              <Label>Auto-reject after (hours)</Label>
              <Input
                type="number"
                value={form.auto_reject_after_hours}
                onChange={(e) => setForm(f => ({ ...f, auto_reject_after_hours: e.target.value }))}
                placeholder="None"
              />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Switch checked={form.is_active} onCheckedChange={(v) => setForm(f => ({ ...f, is_active: v }))} />
            <Label>Active</Label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSave} disabled={createMutation.isPending || updateMutation.isPending}>
            {isEdit ? 'Save Changes' : 'Create Flow'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Steps Editor (shown when flow is expanded) ──

function StepsEditor({ flowId }: { flowId: number }) {
  const queryClient = useQueryClient()
  const [showStepDialog, setShowStepDialog] = useState(false)
  const [editStep, setEditStep] = useState<ApprovalStep | null>(null)
  const [deleteStepId, setDeleteStepId] = useState<number | null>(null)

  const { data: flowData, isLoading } = useQuery({
    queryKey: ['settings', 'approval-flow', flowId],
    queryFn: () => approvalsApi.getFlow(flowId),
  })
  const steps = flowData?.steps ?? []

  const { data: roles = [] } = useQuery({
    queryKey: ['settings', 'roles'],
    queryFn: () => rolesApi.getRoles(),
  })

  const { data: users = [] } = useQuery({
    queryKey: ['users-list'],
    queryFn: () => usersApi.getUsers(),
  })

  const { data: structure = [] } = useQuery({
    queryKey: ['organization-structure'],
    queryFn: () => organizationApi.getStructure(),
  })

  const deleteStepMutation = useMutation({
    mutationFn: (stepId: number) => approvalsApi.deleteStep(flowId, stepId),
    onSuccess: () => {
      toast.success('Step deleted')
      setDeleteStepId(null)
      queryClient.invalidateQueries({ queryKey: ['settings', 'approval-flow', flowId] })
    },
    onError: () => toast.error('Failed to delete step'),
  })

  if (isLoading) return <div className="text-sm text-muted-foreground">Loading steps...</div>

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium">Steps ({steps.length})</h4>
        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => { setEditStep(null); setShowStepDialog(true) }}>
          <Plus className="mr-1 h-3 w-3" />
          Add Step
        </Button>
      </div>

      {steps.length === 0 ? (
        <p className="text-sm text-muted-foreground">No steps defined. Add at least one step for this flow to work.</p>
      ) : (
        <div className="space-y-1.5">
          {steps
            .sort((a, b) => (a.step_order ?? 0) - (b.step_order ?? 0))
            .map((step, idx) => (
              <div key={step.id} className="flex items-center gap-2 rounded-md border bg-muted/30 px-3 py-2">
                <GripVertical className="h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 text-sm">
                    <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-medium">
                      {idx + 1}
                    </span>
                    <span className="font-medium">{step.name}</span>
                    <Badge variant="outline" className="text-xs">
                      {step.approver_type === 'user' ? 'User' : step.approver_type === 'role' ? 'Role' : 'Dept Manager'}
                    </Badge>
                    {step.approver_role_name && (
                      <span className="text-xs text-muted-foreground">{step.approver_role_name}</span>
                    )}
                    {step.approver_user_id && (
                      <span className="text-xs text-muted-foreground">
                        {(users as UserDetail[]).find(u => u.id === step.approver_user_id)?.name || `User #${step.approver_user_id}`}
                      </span>
                    )}
                  </div>
                  <div className="flex gap-3 mt-0.5 text-xs text-muted-foreground">
                    {step.requires_all && <span>Requires all</span>}
                    {(step.min_approvals ?? 0) > 1 && <span>Min {step.min_approvals} approvals</span>}
                    {step.timeout_hours && <span>Timeout: {step.timeout_hours}h</span>}
                    {step.reminder_after_hours && <span>Reminder: {step.reminder_after_hours}h</span>}
                  </div>
                </div>
                <div className="flex gap-1">
                  <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => { setEditStep(step); setShowStepDialog(true) }}>
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 px-2 text-destructive hover:text-destructive"
                    onClick={() => setDeleteStepId(step.id)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            ))}
        </div>
      )}

      {showStepDialog && (
        <StepDialog
          flowId={flowId}
          step={editStep}
          open={showStepDialog}
          onClose={() => { setShowStepDialog(false); setEditStep(null) }}
          roles={roles as Role[]}
          users={users as UserDetail[]}
          structure={structure as DepartmentStructure[]}
        />
      )}

      <ConfirmDialog
        open={deleteStepId !== null}
        onOpenChange={() => setDeleteStepId(null)}
        title="Delete Step"
        description="This step will be permanently removed from the flow."
        onConfirm={() => deleteStepId && deleteStepMutation.mutate(deleteStepId)}
        variant="destructive"
      />
    </div>
  )
}

// ── Step Create/Edit Dialog ──

interface StepDialogProps {
  flowId: number
  step: ApprovalStep | null
  open: boolean
  onClose: () => void
  roles: Role[]
  users: UserDetail[]
  structure: DepartmentStructure[]
}

function StepDialog({ flowId, step, open, onClose, roles, users, structure }: StepDialogProps) {
  const queryClient = useQueryClient()
  const isEdit = step !== null

  const departments = [...new Set(structure.map(s => `${s.company} / ${s.department}`))]

  const [form, setForm] = useState({
    name: step?.name ?? '',
    approver_type: step?.approver_type ?? 'role',
    approver_user_id: step?.approver_user_id ? String(step.approver_user_id) : '',
    approver_role_name: step?.approver_role_name ?? '',
    requires_all: step?.requires_all ?? false,
    min_approvals: step?.min_approvals ?? 1,
    timeout_hours: step?.timeout_hours ? String(step.timeout_hours) : '',
    reminder_after_hours: step?.reminder_after_hours ? String(step.reminder_after_hours) : '',
  })

  const createMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => approvalsApi.createStep(flowId, data),
    onSuccess: () => {
      toast.success('Step added')
      queryClient.invalidateQueries({ queryKey: ['settings', 'approval-flow', flowId] })
      onClose()
    },
    onError: () => toast.error('Failed to add step'),
  })

  const updateMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => approvalsApi.updateStep(flowId, step!.id, data),
    onSuccess: () => {
      toast.success('Step updated')
      queryClient.invalidateQueries({ queryKey: ['settings', 'approval-flow', flowId] })
      onClose()
    },
    onError: () => toast.error('Failed to update step'),
  })

  const handleSave = () => {
    if (!form.name || !form.approver_type) {
      toast.error('Name and approver type are required')
      return
    }
    const data: Record<string, unknown> = {
      name: form.name,
      approver_type: form.approver_type,
      approver_user_id: form.approver_user_id ? Number(form.approver_user_id) : null,
      approver_role_name: form.approver_role_name || null,
      requires_all: form.requires_all,
      min_approvals: Number(form.min_approvals) || 1,
      timeout_hours: form.timeout_hours ? Number(form.timeout_hours) : null,
      reminder_after_hours: form.reminder_after_hours ? Number(form.reminder_after_hours) : null,
    }
    if (isEdit) {
      updateMutation.mutate(data)
    } else {
      createMutation.mutate(data)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit Step' : 'Add Step'}</DialogTitle>
          <DialogDescription>Configure who needs to approve at this step.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div>
            <Label>Step Name</Label>
            <Input
              value={form.name}
              onChange={(e) => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="e.g., Manager Approval"
            />
          </div>
          <div>
            <Label>Approver Type</Label>
            <Select value={form.approver_type ?? ''} onValueChange={(v) => setForm(f => ({ ...f, approver_type: v as 'user' | 'role' | 'department_manager' }))}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {APPROVER_TYPES.map(at => (
                  <SelectItem key={at.value} value={at.value}>{at.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {form.approver_type === 'user' && (
            <div>
              <Label>Approver User</Label>
              <Select value={form.approver_user_id} onValueChange={(v) => setForm(f => ({ ...f, approver_user_id: v }))}>
                <SelectTrigger><SelectValue placeholder="Select user" /></SelectTrigger>
                <SelectContent>
                  {users.filter(u => u.is_active).map(u => (
                    <SelectItem key={u.id} value={String(u.id)}>{u.name} ({u.role_name})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {form.approver_type === 'role' && (
            <div>
              <Label>Role</Label>
              <Select value={form.approver_role_name} onValueChange={(v) => setForm(f => ({ ...f, approver_role_name: v }))}>
                <SelectTrigger><SelectValue placeholder="Select role" /></SelectTrigger>
                <SelectContent>
                  {roles.map(r => (
                    <SelectItem key={r.id} value={r.name}>{r.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {form.approver_type === 'department_manager' && (
            <div>
              <Label>Department (manager will be resolved at runtime)</Label>
              <Select value={form.approver_role_name} onValueChange={(v) => setForm(f => ({ ...f, approver_role_name: v }))}>
                <SelectTrigger><SelectValue placeholder="Select department" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__entity_department__">Entity's Department (dynamic)</SelectItem>
                  {departments.map(d => (
                    <SelectItem key={d} value={d}>{d}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Min Approvals</Label>
              <Input
                type="number"
                min={1}
                value={form.min_approvals}
                onChange={(e) => setForm(f => ({ ...f, min_approvals: Number(e.target.value) }))}
              />
            </div>
            <div className="flex items-end gap-2 pb-1">
              <Switch checked={form.requires_all} onCheckedChange={(v) => setForm(f => ({ ...f, requires_all: v }))} />
              <Label>Require all</Label>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Timeout (hours)</Label>
              <Input
                type="number"
                value={form.timeout_hours}
                onChange={(e) => setForm(f => ({ ...f, timeout_hours: e.target.value }))}
                placeholder="None"
              />
            </div>
            <div>
              <Label>Reminder after (hours)</Label>
              <Input
                type="number"
                value={form.reminder_after_hours}
                onChange={(e) => setForm(f => ({ ...f, reminder_after_hours: e.target.value }))}
                placeholder="None"
              />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSave} disabled={createMutation.isPending || updateMutation.isPending}>
            {isEdit ? 'Save Changes' : 'Add Step'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
