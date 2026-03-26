import { useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { formsApi } from '@/api/forms'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import {
  Plus, Trash2, GripVertical, ArrowLeft, Save, Eye, ChevronUp, ChevronDown,
} from 'lucide-react'
import { toast } from 'sonner'
import { FormRenderer } from '@/components/forms/FormRenderer'
import type { FormField, FieldType } from '@/types/forms'

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

  // Load existing form
  useQuery({
    queryKey: ['form', formId],
    queryFn: () => formsApi.getForm(Number(formId)),
    enabled: isEditing,
    staleTime: 0,
    // @ts-ignore
    onSuccess: (data: any) => {
      setName(data.name || '')
      setDescription(data.description || '')
      setCompanyId(data.company_id)
      setFields(data.schema || [])
      setRequiresApproval(data.requires_approval || false)
      setSettings(data.settings || {})
      setUtmConfig(data.utm_config || { track: [], defaults: {} })
    },
  })

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
            <div className="flex items-center gap-3">
              <Switch checked={requiresApproval} onCheckedChange={setRequiresApproval} />
              <Label>Requires approval for submissions</Label>
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

        {/* Right: Add Field + Field Properties */}
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
              {!['heading', 'paragraph', 'hidden'].includes(selectedField.type) && (
                <>
                  <div>
                    <Label className="text-xs">Placeholder</Label>
                    <Input
                      value={selectedField.placeholder || ''}
                      onChange={(e) => updateField(selectedFieldIdx, { placeholder: e.target.value })}
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <Switch
                      checked={selectedField.required || false}
                      onCheckedChange={(v) => updateField(selectedFieldIdx, { required: v })}
                    />
                    <Label className="text-xs">Required</Label>
                  </div>
                </>
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

          {/* UTM Config */}
          <Tabs defaultValue="utm">
            <TabsList className="w-full">
              <TabsTrigger value="utm" className="flex-1 text-xs">UTM</TabsTrigger>
              <TabsTrigger value="submission" className="flex-1 text-xs">Submission</TabsTrigger>
            </TabsList>
            <TabsContent value="utm" className="rounded-lg border p-3 space-y-2 mt-2">
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
            </TabsContent>
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
