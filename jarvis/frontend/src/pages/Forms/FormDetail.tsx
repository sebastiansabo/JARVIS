import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { formsApi } from '@/api/forms'
import { PageHeader } from '@/components/shared/PageHeader'
import { TableSkeleton } from '@/components/shared/TableSkeleton'
import { SearchInput } from '@/components/shared/SearchInput'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Pencil, ExternalLink, Download, ArrowLeft } from 'lucide-react'
import { toast } from 'sonner'
import type { FormSubmission } from '@/types/forms'

const submissionStatusConfig: Record<string, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  new: { label: 'New', variant: 'default' },
  read: { label: 'Read', variant: 'secondary' },
  flagged: { label: 'Flagged', variant: 'outline' },
  approved: { label: 'Approved', variant: 'default' },
  rejected: { label: 'Rejected', variant: 'destructive' },
}

export default function FormDetail() {
  const { formId } = useParams<{ formId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [selectedSubmission, setSelectedSubmission] = useState<FormSubmission | null>(null)
  const [searchQuery, setSearchQuery] = useState('')

  const { data: form, isLoading } = useQuery({
    queryKey: ['form', formId],
    queryFn: () => formsApi.getForm(Number(formId)),
    enabled: !!formId,
  })

  const { data: submissionsData, isLoading: loadingSubs } = useQuery({
    queryKey: ['form-submissions', formId, searchQuery],
    queryFn: () => formsApi.listSubmissions(Number(formId), {
      search: searchQuery || undefined,
      limit: 50,
    }),
    enabled: !!formId,
  })

  const publishMutation = useMutation({
    mutationFn: () => formsApi.publishForm(Number(formId)),
    onSuccess: () => {
      toast.success('Form published!')
      queryClient.invalidateQueries({ queryKey: ['form', formId] })
    },
    onError: (err: any) => toast.error(err?.error || 'Failed to publish'),
  })

  const disableMutation = useMutation({
    mutationFn: () => formsApi.disableForm(Number(formId)),
    onSuccess: () => {
      toast.success('Form disabled')
      queryClient.invalidateQueries({ queryKey: ['form', formId] })
    },
    onError: () => toast.error('Failed to disable form'),
  })

  if (isLoading) return <TableSkeleton />
  if (!form) return <p className="text-muted-foreground">Form not found.</p>

  const submissions = submissionsData?.submissions ?? []
  const schema = form.published_schema || form.schema || []

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={() => navigate('/app/forms')}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <PageHeader
          title={form.name}
          actions={
            <div className="flex gap-2">
              {form.status === 'published' && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    navigator.clipboard.writeText(`${window.location.origin}/forms/public/${form.slug}`)
                    toast.success('Public link copied!')
                  }}
                >
                  <ExternalLink className="h-4 w-4 mr-2" /> Copy Link
                </Button>
              )}
              <Button variant="outline" size="sm" onClick={() => navigate(`/app/forms/builder/${form.id}`)}>
                <Pencil className="h-4 w-4 mr-2" /> Edit
              </Button>
              {form.status === 'draft' && (
                <Button size="sm" onClick={() => publishMutation.mutate()} disabled={publishMutation.isPending}>
                  Publish
                </Button>
              )}
              {form.status === 'published' && (
                <Button variant="destructive" size="sm" onClick={() => disableMutation.mutate()}>
                  Disable
                </Button>
              )}
            </div>
          }
        />
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="rounded-lg border p-3">
          <p className="text-sm text-muted-foreground">Status</p>
          <Badge variant={form.status === 'published' ? 'default' : 'secondary'}>
            {form.status}
          </Badge>
        </div>
        <div className="rounded-lg border p-3">
          <p className="text-sm text-muted-foreground">Submissions</p>
          <p className="text-2xl font-bold">{form.submission_count ?? 0}</p>
        </div>
        <div className="rounded-lg border p-3">
          <p className="text-sm text-muted-foreground">Version</p>
          <p className="text-2xl font-bold">{form.version}</p>
        </div>
        <div className="rounded-lg border p-3">
          <p className="text-sm text-muted-foreground">Fields</p>
          <p className="text-2xl font-bold">{schema.length}</p>
        </div>
      </div>

      <Tabs defaultValue="submissions">
        <TabsList>
          <TabsTrigger value="submissions">Submissions</TabsTrigger>
          <TabsTrigger value="schema">Fields</TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
        </TabsList>

        <TabsContent value="submissions" className="space-y-4 mt-4">
          <div className="flex items-center justify-between gap-4">
            <SearchInput
              value={searchQuery}
              onChange={setSearchQuery}
              placeholder="Search submissions..."
            />
            <Button
              variant="outline"
              size="sm"
              onClick={() => window.open(formsApi.getExportUrl(Number(formId)), '_blank')}
            >
              <Download className="h-4 w-4 mr-2" /> Export CSV
            </Button>
          </div>

          {loadingSubs ? (
            <TableSkeleton />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>#</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Submitted</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {submissions.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                      No submissions yet.
                    </TableCell>
                  </TableRow>
                ) : (
                  submissions.map((sub, idx) => {
                    const sc = submissionStatusConfig[sub.status] ?? submissionStatusConfig.new
                    return (
                      <TableRow
                        key={sub.id}
                        className="cursor-pointer"
                        onClick={() => setSelectedSubmission(sub)}
                      >
                        <TableCell>{idx + 1}</TableCell>
                        <TableCell>{sub.respondent_name || '—'}</TableCell>
                        <TableCell>{sub.respondent_email || '—'}</TableCell>
                        <TableCell className="text-sm">{sub.source}</TableCell>
                        <TableCell>
                          <Badge variant={sc.variant}>{sc.label}</Badge>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {new Date(sub.created_at).toLocaleString('ro-RO')}
                        </TableCell>
                      </TableRow>
                    )
                  })
                )}
              </TableBody>
            </Table>
          )}
        </TabsContent>

        <TabsContent value="schema" className="mt-4">
          <div className="space-y-2">
            {schema.length === 0 ? (
              <p className="text-muted-foreground">No fields defined yet.</p>
            ) : (
              schema.map((field: any, idx: number) => (
                <div key={field.id || idx} className="flex items-center gap-4 rounded-lg border p-3">
                  <span className="text-sm font-mono text-muted-foreground w-8">{idx + 1}</span>
                  <div className="flex-1">
                    <p className="font-medium">{field.label || field.type}</p>
                    <p className="text-sm text-muted-foreground">
                      {field.type}
                      {field.required && ' (required)'}
                    </p>
                  </div>
                  {field.options && (
                    <p className="text-sm text-muted-foreground">
                      {field.options.length} option{field.options.length !== 1 ? 's' : ''}
                    </p>
                  )}
                </div>
              ))
            )}
          </div>
        </TabsContent>

        <TabsContent value="settings" className="mt-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="rounded-lg border p-4 space-y-2">
              <h3 className="font-semibold">General</h3>
              <p className="text-sm"><span className="text-muted-foreground">Company:</span> {form.company_name}</p>
              <p className="text-sm"><span className="text-muted-foreground">Owner:</span> {form.owner_name}</p>
              <p className="text-sm"><span className="text-muted-foreground">Requires Approval:</span> {form.requires_approval ? 'Yes' : 'No'}</p>
              <p className="text-sm"><span className="text-muted-foreground">Slug:</span> {form.slug}</p>
            </div>
            <div className="rounded-lg border p-4 space-y-2">
              <h3 className="font-semibold">Submission Settings</h3>
              <p className="text-sm"><span className="text-muted-foreground">Thank-you message:</span> {form.settings?.thank_you_message || 'Default'}</p>
              <p className="text-sm"><span className="text-muted-foreground">Redirect URL:</span> {form.settings?.redirect_url || 'None'}</p>
              <p className="text-sm"><span className="text-muted-foreground">Submission Limit:</span> {form.settings?.submission_limit || 'Unlimited'}</p>
            </div>
            <div className="rounded-lg border p-4 space-y-2">
              <h3 className="font-semibold">UTM Configuration</h3>
              <p className="text-sm"><span className="text-muted-foreground">Tracked params:</span> {(form.utm_config?.track ?? ['utm_source', 'utm_medium', 'utm_campaign']).join(', ')}</p>
              {form.utm_config?.defaults && Object.keys(form.utm_config.defaults).length > 0 && (
                <p className="text-sm"><span className="text-muted-foreground">Defaults:</span> {JSON.stringify(form.utm_config.defaults)}</p>
              )}
            </div>
          </div>
        </TabsContent>
      </Tabs>

      {/* Submission detail dialog */}
      <Dialog open={!!selectedSubmission} onOpenChange={() => setSelectedSubmission(null)}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Submission #{selectedSubmission?.id}</DialogTitle>
          </DialogHeader>
          {selectedSubmission && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-2 text-sm">
                <p><span className="text-muted-foreground">Name:</span> {selectedSubmission.respondent_name || '—'}</p>
                <p><span className="text-muted-foreground">Email:</span> {selectedSubmission.respondent_email || '—'}</p>
                <p><span className="text-muted-foreground">Phone:</span> {selectedSubmission.respondent_phone || '—'}</p>
                <p><span className="text-muted-foreground">Source:</span> {selectedSubmission.source}</p>
                <p><span className="text-muted-foreground">IP:</span> {selectedSubmission.respondent_ip || '—'}</p>
                <p><span className="text-muted-foreground">Status:</span> {selectedSubmission.status}</p>
              </div>

              {/* UTM Data */}
              {selectedSubmission.utm_data && Object.keys(selectedSubmission.utm_data).length > 0 && (
                <div>
                  <h4 className="font-semibold text-sm mb-1">UTM Data</h4>
                  <div className="rounded border p-2 text-sm space-y-1">
                    {Object.entries(selectedSubmission.utm_data).map(([k, v]) => (
                      <p key={k}><span className="text-muted-foreground">{k}:</span> {v}</p>
                    ))}
                  </div>
                </div>
              )}

              {/* Answers */}
              <div>
                <h4 className="font-semibold text-sm mb-1">Answers</h4>
                <div className="rounded border divide-y">
                  {(selectedSubmission.form_schema_snapshot || []).map((field: any) => {
                    if (field.type === 'heading' || field.type === 'paragraph') return null
                    const value = (selectedSubmission.answers as any)?.[field.id]
                    return (
                      <div key={field.id} className="p-2 text-sm">
                        <p className="text-muted-foreground">{field.label}</p>
                        <p className="font-medium">
                          {Array.isArray(value) ? value.join(', ') : (value ?? '—')}
                        </p>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
