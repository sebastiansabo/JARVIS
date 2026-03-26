import { useState, useCallback, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { formsApi } from '@/api/forms'
import { usersApi } from '@/api/users'
import { approvalsApi } from '@/api/approvals'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import {
  Plus, Trash2, GripVertical, ArrowLeft, Save, Eye, ChevronUp, ChevronDown,
} from 'lucide-react'
import { toast } from 'sonner'
import { FormRenderer } from '@/components/forms/FormRenderer'
import type { FormField, FieldType, ApprovalConfig } from '@/types/forms'

const FIELD_TYPES: { value: FieldType; label: string; group: string }[] = [
  { value: 'short_text', label: 'Short Text', group: 'Input' },
  { value: 'long_text', label: 'Long Text', group: 'Input' },
  { value: 'email', label: 'Email', group: 'Input' },
  { value: 'phone', label: 'Phone', group: 'Input' },
  { value: 'number', label: 'Number', group: 'Input' },
  { value: 'date', label: 'Date', group: 'Input' },
  { value: 'dropdown', label: 'Dropdown', group: 'Selection' },
  { value: 'radio', label: 'Radio', group: 'Selection' },
  { value: 'checkbox', label: 'Checkbox', group: 'Selection' },
  { value: 'file_upload', label: 'File Upload', group: 'Special' },
  { value: 'signature', label: 'Signature', group: 'Special' },
  { value: 'heading', label: 'Heading', group: 'Display' },
  { value: 'paragraph', label: 'Paragraph', group: 'Display' },
  { value: 'hidden', label: 'Hidden Field', group: 'Special' },
]

function generateId() {
  return `f_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`
}

export default function FormBuilder() {
  const { formId } = useParams<{ formId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const isEditing = !!formId

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [companyId, setCompanyId] = useState<number | undefined>(undefined)
  const [fields, setFields] = useState<FormField[]>([])
  const [selectedFieldIdx, setSelectedFieldIdx] = useState<number | null>(null)
  const [showPreview, setShowPreview] = useState(false)
  const [requiresApproval, setRequiresApproval] = useState(false)
  const [settings, setSettings] = useState<Record<string, any>>({})
  const [utmConfig, setUtmConfig] = useState<Record<string, any>>({
    track: ['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content'],
    defaults: {},
  })
  const [approvalConfig, setApprovalConfig] = useState<ApprovalConfig>({})

  // Load existing form — use useEffect instead of onSuccess (RQ v5)
  const { data: formData } = useQuery({
    queryKey: ['form', formId],
    queryFn: () => formsApi.getForm(Number(formId)),
    enabled: isEditing,
    staleTime: 0,
  })

  useEffect(() => {
    if (formData) {
      setName(formData.name || '')
      setDescription(formData.description || '')
      setCompanyId(formData.company_id)
      setFields(formData.schema || [])
      setRequiresApproval(formData.requires_approval || false)
      setSettings(formData.settings || {})
      setUtmConfig(formData.utm_config || { track: [], defaults: {} })
      setApprovalConfig(formData.approval_config || {})
    }
  }, [formData])

  // Fetch company users for notification pickers
  const { data: companyUsers = [] } = useQuery({
    queryKey: ['company-users'],
    queryFn: () => usersApi.getUsers(),
  })

  // Fetch approval flows
  const { data: flowsData } = useQuery({
    queryKey: ['approval-flows'],
    queryFn: () => approvalsApi.getFlows(true),
  })
  const approvalFlows = flowsData?.flows || []

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        name,
        description,
        company_id: companyId,
        schema: fields,
        settings,
        utm_config: utmConfig,
        requires_approval: requiresApproval,
        approval_config: requiresApproval ? approvalConfig : {},
      }
      if (isEditing) {
        await formsApi.updateForm(Number(formId), payload)
        return { id: Number(formId) }
      }
      return formsApi.createForm(payload)
    },
    onSuccess: (data) => {
      toast.success('Form saved!')
      queryClient.invalidateQueries({ queryKey: ['forms'] })
      if (!isEditing && data?.id) {
        navigate(`/app/forms/builder/${data.id}`, { replace: true })
      }
    },
    onError: () => toast.error('Failed to save form'),
  })

  // Field operations
  const addField = useCallback((type: FieldType) => {
    const newField: FormField = {
      id: generateId(),
      type,
      label: type === 'heading' ? 'Section Title' : type === 'paragraph' ? 'Description text' : '',
      required: false,
      order: fields.length + 1,
      ...((['dropdown', 'radio', 'checkbox'].includes(type)) ? { options: ['Option 1', 'Option 2'] } : {}),
    }
    setFields([...fields, newField])
    setSelectedFieldIdx(fields.length)
  }, [fields])

  const updateField = useCallback((idx: number, updates: Partial<FormField>) => {
    setFields((prev) => prev.map((f, i) => (i === idx ? { ...f, ...updates } : f)))
  }, [])

  const removeField = useCallback((idx: number) => {
    setFields((prev) => prev.filter((_, i) => i !== idx))
    setSelectedFieldIdx(null)
  }, [])

  const moveField = useCallback((idx: number, direction: -1 | 1) => {
    const newIdx = idx + direction
    if (newIdx < 0 || newIdx >= fields.length) return
    setFields((prev) => {
      const copy = [...prev]
      ;[copy[idx], copy[newIdx]] = [copy[newIdx], copy[idx]]
      return copy.map((f, i) => ({ ...f, order: i + 1 }))
    })
    setSelectedFieldIdx(newIdx)
  }, [fields.length])

  // Approval config helpers
  const toggleUserInList = (key: 'notify_on_submit' | 'notify_on_approve' | 'notify_on_reject', userId: number) => {
    setApprovalConfig((prev) => {
      const list = prev[key] || []
      const next = list.includes(userId) ? list.filter((id) => id !== userId) : [...list, userId]
      return { ...prev, [key]: next }
    })
  }

  const selectedField = selectedFieldIdx !== null ? fields[selectedFieldIdx] : null

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => navigate('/app/forms')}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <h1 className="text-xl font-bold">{isEditing ? 'Edit Form' : 'New Form'}</h1>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setShowPreview(true)}>
            <Eye className="h-4 w-4 mr-2" /> Preview
          </Button>
          <Button size="sm" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
            <Save className="h-4 w-4 mr-2" /> Save
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Form Meta + Field List */}
        <div className="lg:col-span-2 space-y-4">
          {/* Form metadata */}
          <div className="rounded-lg border p-4 space-y-3">
            <div>
              <Label>Form Name</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Form name..." />
            </div>
            <div>
              <Label>Description</Label>
              <Textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Optional description..." rows={2} />
            </div>
          </div>

          {/* Fields */}
          <div className="rounded-lg border p-4 space-y-2">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold">Fields ({fields.length})</h2>
            </div>
            {fields.length === 0 ? (
              <p className="text-muted-foreground text-sm py-4 text-center">
                No fields yet. Add a field from the panel on the right.
              </p>
            ) : (
              <div className="space-y-1">
                {fields.map((field, idx) => (
                  <div
                    key={field.id}
                    className={`flex items-center gap-2 rounded-lg border p-2 cursor-pointer hover:bg-accent/50 transition-colors ${
                      selectedFieldIdx === idx ? 'border-primary bg-accent/30' : ''
                    }`}
                    onClick={() => setSelectedFieldIdx(idx)}
                  >
                    <GripVertical className="h-4 w-4 text-muted-foreground shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{field.label || `(${field.type})`}</p>
                      <p className="text-xs text-muted-foreground">
                        {field.type}{field.required ? ' *' : ''}
                      </p>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={(e) => { e.stopPropagation(); moveField(idx, -1) }} disabled={idx === 0}>
                        <ChevronUp className="h-3 w-3" />
                      </Button>
                      <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={(e) => { e.stopPropagation(); moveField(idx, 1) }} disabled={idx === fields.length - 1}>
                        <ChevronDown className="h-3 w-3" />
                      </Button>
                      <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-destructive" onClick={(e) => { e.stopPropagation(); removeField(idx) }}>
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right: Add Field + Field Properties + Config Tabs */}
        <div className="space-y-4">
          {/* Add Field */}
          <div className="rounded-lg border p-4 space-y-2">
            <h3 className="font-semibold text-sm">Add Field</h3>
            <div className="grid grid-cols-2 gap-1">
              {FIELD_TYPES.map((ft) => (
                <Button
                  key={ft.value}
                  variant="outline"
                  size="sm"
                  className="justify-start text-xs h-8"
                  onClick={() => addField(ft.value)}
                >
                  <Plus className="h-3 w-3 mr-1 shrink-0" />
                  {ft.label}
                </Button>
              ))}
            </div>
          </div>

          {/* Field Properties */}
          {selectedField && selectedFieldIdx !== null && (
            <div className="rounded-lg border p-4 space-y-3">
              <h3 className="font-semibold text-sm">Field Properties</h3>
              <div>
                <Label className="text-xs">Label</Label>
                <Input
                  value={selectedField.label}
                  onChange={(e) => updateField(selectedFieldIdx, { label: e.target.value })}
                />
              </div>
              {!['heading', 'paragraph', 'hidden', 'signature'].includes(selectedField.type) && (
                <>
                  <div>
                    <Label className="text-xs">Placeholder</Label>
                    <Input
                      value={selectedField.placeholder || ''}
                      onChange={(e) => updateField(selectedFieldIdx, { placeholder: e.target.value })}
                    />
                  </div>
                </>
              )}
              {!['heading', 'paragraph'].includes(selectedField.type) && (
                <div className="flex items-center gap-2">
                  <Switch
                    checked={selectedField.required || false}
                    onCheckedChange={(v) => updateField(selectedFieldIdx, { required: v })}
                  />
                  <Label className="text-xs">Required</Label>
                </div>
              )}
              {/* Options for select types */}
              {['dropdown', 'radio', 'checkbox'].includes(selectedField.type) && (
                <div className="space-y-2">
                  <Label className="text-xs">Options</Label>
                  {(selectedField.options || []).map((opt, optIdx) => (
                    <div key={optIdx} className="flex gap-1">
                      <Input
                        value={opt}
                        onChange={(e) => {
                          const newOpts = [...(selectedField.options || [])]
                          newOpts[optIdx] = e.target.value
                          updateField(selectedFieldIdx, { options: newOpts })
                        }}
                        className="h-7 text-sm"
                      />
                      <Button
                        variant="ghost" size="sm" className="h-7 w-7 p-0 text-destructive shrink-0"
                        onClick={() => {
                          const newOpts = (selectedField.options || []).filter((_, i) => i !== optIdx)
                          updateField(selectedFieldIdx, { options: newOpts })
                        }}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  ))}
                  <Button
                    variant="outline" size="sm" className="w-full h-7 text-xs"
                    onClick={() => {
                      updateField(selectedFieldIdx, {
                        options: [...(selectedField.options || []), `Option ${(selectedField.options || []).length + 1}`],
                      })
                    }}
                  >
                    <Plus className="h-3 w-3 mr-1" /> Add Option
                  </Button>
                </div>
              )}
            </div>
          )}

          {/* Config Tabs */}
          <Tabs defaultValue="approval">
            <TabsList className="w-full">
              <TabsTrigger value="approval" className="flex-1 text-xs">Approval</TabsTrigger>
              <TabsTrigger value="utm" className="flex-1 text-xs">UTM</TabsTrigger>
              <TabsTrigger value="submission" className="flex-1 text-xs">Submission</TabsTrigger>
            </TabsList>

            {/* Approval Tab */}
            <TabsContent value="approval" className="rounded-lg border p-3 space-y-3 mt-2">
              <div className="flex items-center gap-2">
                <Switch checked={requiresApproval} onCheckedChange={setRequiresApproval} />
                <Label className="text-xs font-medium">Requires approval</Label>
              </div>

              {requiresApproval && (
                <>
                  {/* Approval Flow picker */}
                  <div>
                    <Label className="text-xs">Approval Flow</Label>
                    <Select
                      value={approvalConfig.flow_id ? String(approvalConfig.flow_id) : ''}
                      onValueChange={(v) => setApprovalConfig({ ...approvalConfig, flow_id: v ? Number(v) : undefined })}
                    >
                      <SelectTrigger className="h-8 text-xs">
                        <SelectValue placeholder="Auto-match by entity type" />
                      </SelectTrigger>
                      <SelectContent>
                        {approvalFlows.map((flow: any) => (
                          <SelectItem key={flow.id} value={String(flow.id)}>
                            {flow.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Notify on Submit */}
                  <UserPickerSection
                    label="Notify on submission"
                    users={companyUsers}
                    selectedIds={approvalConfig.notify_on_submit || []}
                    onToggle={(id) => toggleUserInList('notify_on_submit', id)}
                  />

                  {/* Notify on Approve */}
                  <UserPickerSection
                    label="Notify on approval"
                    users={companyUsers}
                    selectedIds={approvalConfig.notify_on_approve || []}
                    onToggle={(id) => toggleUserInList('notify_on_approve', id)}
                  />

                  {/* Notify on Reject */}
                  <UserPickerSection
                    label="Notify on rejection"
                    users={companyUsers}
                    selectedIds={approvalConfig.notify_on_reject || []}
                    onToggle={(id) => toggleUserInList('notify_on_reject', id)}
                  />

                  {/* Notify respondent */}
                  <div className="flex items-center gap-2">
                    <Switch
                      checked={approvalConfig.notify_respondent || false}
                      onCheckedChange={(v) => setApprovalConfig({ ...approvalConfig, notify_respondent: v })}
                    />
                    <Label className="text-xs">Notify respondent by email</Label>
                  </div>

                  {/* Requires signature */}
                  <div className="flex items-center gap-2">
                    <Switch
                      checked={approvalConfig.requires_signature || false}
                      onCheckedChange={(v) => setApprovalConfig({ ...approvalConfig, requires_signature: v })}
                    />
                    <Label className="text-xs">Require signature on approval</Label>
                  </div>

                  {approvalConfig.requires_signature && (
                    <div>
                      <Label className="text-xs">Who signs</Label>
                      <Select
                        value={approvalConfig.signature_signer || 'respondent'}
                        onValueChange={(v: 'respondent' | 'approver' | 'owner') =>
                          setApprovalConfig({ ...approvalConfig, signature_signer: v })
                        }
                      >
                        <SelectTrigger className="h-8 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="respondent">Respondent</SelectItem>
                          <SelectItem value="approver">Approver</SelectItem>
                          <SelectItem value="owner">Form Owner</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  )}
                </>
              )}
            </TabsContent>

            {/* UTM Tab */}
            <TabsContent value="utm" className="rounded-lg border p-3 space-y-3 mt-2">
              <div className="space-y-2">
                <Label className="text-xs">Tracked UTM Parameters</Label>
                <div className="flex flex-wrap gap-1">
                  {['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content'].map((param) => {
                    const isTracked = (utmConfig.track || []).includes(param)
                    return (
                      <Button
                        key={param}
                        variant={isTracked ? 'default' : 'outline'}
                        size="sm"
                        className="h-6 text-xs"
                        onClick={() => {
                          const track = isTracked
                            ? (utmConfig.track || []).filter((t: string) => t !== param)
                            : [...(utmConfig.track || []), param]
                          setUtmConfig({ ...utmConfig, track })
                        }}
                      >
                        {param.replace('utm_', '')}
                      </Button>
                    )
                  })}
                </div>
              </div>

              {/* UTM Defaults */}
              <div className="space-y-2">
                <Label className="text-xs">Default Values</Label>
                <p className="text-xs text-muted-foreground">
                  Set fallback values for UTM parameters when not provided in the URL.
                </p>
                {(utmConfig.track || []).map((param: string) => (
                  <div key={param} className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground w-20 shrink-0 truncate">{param.replace('utm_', '')}</span>
                    <Input
                      value={(utmConfig.defaults || {})[param] || ''}
                      onChange={(e) => {
                        const defaults = { ...(utmConfig.defaults || {}) }
                        if (e.target.value) {
                          defaults[param] = e.target.value
                        } else {
                          delete defaults[param]
                        }
                        setUtmConfig({ ...utmConfig, defaults })
                      }}
                      placeholder="No default"
                      className="h-7 text-xs"
                    />
                  </div>
                ))}
              </div>
            </TabsContent>

            {/* Submission Tab */}
            <TabsContent value="submission" className="rounded-lg border p-3 space-y-2 mt-2">
              <div>
                <Label className="text-xs">Thank-you Message</Label>
                <Input
                  value={settings.thank_you_message || ''}
                  onChange={(e) => setSettings({ ...settings, thank_you_message: e.target.value })}
                  placeholder="Thank you for your submission!"
                />
              </div>
              <div>
                <Label className="text-xs">Redirect URL</Label>
                <Input
                  value={settings.redirect_url || ''}
                  onChange={(e) => setSettings({ ...settings, redirect_url: e.target.value })}
                  placeholder="https://..."
                />
              </div>
              <div>
                <Label className="text-xs">Submission Limit</Label>
                <Input
                  type="number"
                  value={settings.submission_limit || ''}
                  onChange={(e) => setSettings({ ...settings, submission_limit: e.target.value ? Number(e.target.value) : undefined })}
                  placeholder="Unlimited"
                />
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </div>

      {/* Preview Dialog */}
      <Dialog open={showPreview} onOpenChange={setShowPreview}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Form Preview</DialogTitle>
          </DialogHeader>
          <FormRenderer schema={fields} onSubmit={(answers) => { toast.info('Preview submit: ' + JSON.stringify(answers).slice(0, 100)) }} />
        </DialogContent>
      </Dialog>
    </div>
  )
}

/** Collapsible user picker with checkboxes */
function UserPickerSection({ label, users, selectedIds, onToggle }: {
  label: string
  users: any[]
  selectedIds: number[]
  onToggle: (id: number) => void
}) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="space-y-1">
      <button
        type="button"
        className="flex items-center justify-between w-full text-xs font-medium text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <span>{label} {selectedIds.length > 0 && `(${selectedIds.length})`}</span>
        <ChevronDown className={`h-3 w-3 transition-transform ${expanded ? 'rotate-180' : ''}`} />
      </button>
      {expanded && (
        <div className="max-h-32 overflow-y-auto rounded border p-1 space-y-0.5">
          {users.map((u: any) => (
            <label key={u.id} className="flex items-center gap-2 px-1.5 py-0.5 rounded hover:bg-accent/50 cursor-pointer">
              <Checkbox
                checked={selectedIds.includes(u.id)}
                onCheckedChange={() => onToggle(u.id)}
              />
              <span className="text-xs truncate">{u.name || u.email}</span>
            </label>
          ))}
          {users.length === 0 && (
            <p className="text-xs text-muted-foreground px-1.5 py-1">No users found</p>
          )}
        </div>
      )}
    </div>
  )
}
