import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Scale, Plus, Upload, FileSpreadsheet, Trash2, Copy, Eye, Download, Pencil } from 'lucide-react'
import { toast } from 'sonner'

import { bilantApi } from '@/api/bilant'
import { organizationApi } from '@/api/organization'
import { PageHeader } from '@/components/shared/PageHeader'
import { StatCard } from '@/components/shared/StatCard'
import { EmptyState } from '@/components/shared/EmptyState'
import { useTabParam } from '@/hooks/useTabParam'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { UploadDialog } from './UploadDialog'
import type { BilantTemplate, BilantGeneration } from '@/types/bilant'

type MainTab = 'generations' | 'templates'

const statusColors: Record<string, string> = {
  completed: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400',
  processing: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  error: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
}

function fmt(n: number | null | undefined): string {
  if (n == null) return '-'
  return new Intl.NumberFormat('ro-RO').format(n)
}

function fmtDate(s: string | null | undefined): string {
  if (!s) return '-'
  return new Date(s).toLocaleDateString('ro-RO', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

export default function Bilant() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [tab, setTab] = useTabParam<MainTab>('generations')
  const [companyFilter, setCompanyFilter] = useState<string>('')
  const [showUpload, setShowUpload] = useState(false)
  const [showNewTemplate, setShowNewTemplate] = useState(false)
  const [newTemplateName, setNewTemplateName] = useState('')
  const [newTemplateCompany, setNewTemplateCompany] = useState<string>('')
  const [deleteTarget, setDeleteTarget] = useState<{ type: 'generation' | 'template'; id: number; name: string } | null>(null)

  // ── Queries ──

  const { data: companiesData } = useQuery({
    queryKey: ['companies-config'],
    queryFn: () => organizationApi.getCompaniesConfig(),
  })
  const companies = companiesData || []

  const { data: generationsData, isLoading: genLoading } = useQuery({
    queryKey: ['bilant-generations', companyFilter],
    queryFn: () => bilantApi.listGenerations({ company_id: companyFilter ? Number(companyFilter) : undefined, limit: 100 }),
  })
  const generations = generationsData?.generations || []
  const genTotal = generationsData?.total || 0

  const { data: templatesData, isLoading: tplLoading } = useQuery({
    queryKey: ['bilant-templates', companyFilter],
    queryFn: () => bilantApi.listTemplates(companyFilter ? Number(companyFilter) : undefined),
  })
  const templates = templatesData?.templates || []

  // ── Mutations ──

  const deleteGenMut = useMutation({
    mutationFn: (id: number) => bilantApi.deleteGeneration(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bilant-generations'] }); toast.success('Generation deleted') },
  })

  const deleteTplMut = useMutation({
    mutationFn: (id: number) => bilantApi.deleteTemplate(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bilant-templates'] }); toast.success('Template deleted') },
  })

  const duplicateTplMut = useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) => bilantApi.duplicateTemplate(id, name),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bilant-templates'] }); toast.success('Template duplicated') },
  })

  const createTplMut = useMutation({
    mutationFn: (data: { name: string; company_id?: number }) => bilantApi.createTemplate(data),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['bilant-templates'] })
      toast.success('Template created')
      setShowNewTemplate(false)
      setNewTemplateName('')
      if (res.id) navigate(`/app/accounting/bilant/templates/${res.id}`)
    },
  })

  const handleDelete = () => {
    if (!deleteTarget) return
    if (deleteTarget.type === 'generation') deleteGenMut.mutate(deleteTarget.id)
    else deleteTplMut.mutate(deleteTarget.id)
    setDeleteTarget(null)
  }

  // ── Stats ──
  const completedCount = generations.filter(g => g.status === 'completed').length
  const uniqueCompanies = new Set(generations.map(g => g.company_id)).size

  // ── Tabs ──
  const tabs: { key: MainTab; label: string }[] = [
    { key: 'generations', label: 'Generations' },
    { key: 'templates', label: 'Templates' },
  ]

  return (
    <div className="space-y-4">
      <PageHeader
        title="Bilant"
        description="Balance sheet generator — upload Balanta, generate Bilant with financial ratios"
        breadcrumbs={[
          { label: 'Accounting', href: '/app/accounting' },
          { label: 'Bilant' },
        ]}
        actions={
          <div className="flex items-center gap-2">
            {tab === 'generations' && (
              <Button size="sm" onClick={() => setShowUpload(true)}>
                <Upload className="mr-1.5 h-4 w-4" />
                New Generation
              </Button>
            )}
            {tab === 'templates' && (
              <Button size="sm" onClick={() => setShowNewTemplate(true)}>
                <Plus className="mr-1.5 h-4 w-4" />
                New Template
              </Button>
            )}
          </div>
        }
      />

      {/* Tabs */}
      <div className="flex items-center gap-4 border-b">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`pb-2 text-sm font-medium transition-colors ${
              tab === t.key
                ? 'border-b-2 border-primary text-foreground'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {t.label}
          </button>
        ))}

        <div className="ml-auto pb-2">
          <Select value={companyFilter} onValueChange={setCompanyFilter}>
            <SelectTrigger className="h-8 w-[180px] text-xs">
              <SelectValue placeholder="All companies" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All companies</SelectItem>
              {companies.map(c => (
                <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Generations Tab */}
      {tab === 'generations' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard title="Total Generations" value={fmt(genTotal)} icon={<Scale className="h-4 w-4" />} isLoading={genLoading} />
            <StatCard title="Completed" value={fmt(completedCount)} icon={<FileSpreadsheet className="h-4 w-4" />} isLoading={genLoading} />
            <StatCard title="Companies" value={fmt(uniqueCompanies)} isLoading={genLoading} />
            <StatCard title="Templates" value={fmt(templates.length)} isLoading={tplLoading} />
          </div>

          {generations.length === 0 && !genLoading ? (
            <EmptyState
              icon={<Scale className="h-12 w-12" />}
              title="No generations yet"
              description="Upload a Balanta Excel file to generate your first Bilant"
              action={
                <Button size="sm" onClick={() => setShowUpload(true)}>
                  <Upload className="mr-1.5 h-4 w-4" />
                  Upload Balanta
                </Button>
              }
            />
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Company</TableHead>
                    <TableHead>Period</TableHead>
                    <TableHead>Template</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead>By</TableHead>
                    <TableHead className="w-[100px]">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {generations.map(g => (
                    <GenerationRow
                      key={g.id}
                      gen={g}
                      onView={() => navigate(`/app/accounting/bilant/${g.id}`)}
                      onDownload={() => bilantApi.downloadGeneration(g.id)}
                      onDelete={() => setDeleteTarget({ type: 'generation', id: g.id, name: `${g.company_name} - ${g.period_label || g.id}` })}
                    />
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      )}

      {/* Templates Tab */}
      {tab === 'templates' && (
        <div className="space-y-4">
          {templates.length === 0 && !tplLoading ? (
            <EmptyState
              icon={<FileSpreadsheet className="h-12 w-12" />}
              title="No templates"
              description="Create a template to define the Bilant structure"
              action={
                <Button size="sm" onClick={() => setShowNewTemplate(true)}>
                  <Plus className="mr-1.5 h-4 w-4" />
                  New Template
                </Button>
              }
            />
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Company</TableHead>
                    <TableHead>Rows</TableHead>
                    <TableHead>Default</TableHead>
                    <TableHead>Version</TableHead>
                    <TableHead className="w-[100px]">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {templates.map(t => (
                    <TemplateRow
                      key={t.id}
                      tpl={t}
                      onEdit={() => navigate(`/app/accounting/bilant/templates/${t.id}`)}
                      onDuplicate={() => duplicateTplMut.mutate({ id: t.id, name: `${t.name} (Copy)` })}
                      onDelete={() => setDeleteTarget({ type: 'template', id: t.id, name: t.name })}
                    />
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      )}

      {/* Upload Dialog */}
      <UploadDialog
        open={showUpload}
        onOpenChange={setShowUpload}
        companies={companies}
        templates={templates}
      />

      {/* New Template Dialog */}
      <Dialog open={showNewTemplate} onOpenChange={setShowNewTemplate}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>New Template</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Name</Label>
              <Input value={newTemplateName} onChange={e => setNewTemplateName(e.target.value)} placeholder="e.g. Standard Romanian Bilant" />
            </div>
            <div className="space-y-2">
              <Label>Company (optional)</Label>
              <Select value={newTemplateCompany} onValueChange={setNewTemplateCompany}>
                <SelectTrigger>
                  <SelectValue placeholder="Global (all companies)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="global">Global (all companies)</SelectItem>
                  {companies.map(c => (
                    <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowNewTemplate(false)}>Cancel</Button>
              <Button
                disabled={!newTemplateName.trim() || createTplMut.isPending}
                onClick={() => createTplMut.mutate({
                  name: newTemplateName.trim(),
                  company_id: newTemplateCompany && newTemplateCompany !== 'global' ? Number(newTemplateCompany) : undefined,
                })}
              >
                Create
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={() => setDeleteTarget(null)}
        title={`Delete ${deleteTarget?.type}?`}
        description={`Are you sure you want to delete "${deleteTarget?.name}"? This action cannot be undone.`}
        onConfirm={handleDelete}
        confirmLabel="Delete"
        variant="destructive"
      />
    </div>
  )
}

// ── Row Components ──

function GenerationRow({ gen, onView, onDownload, onDelete }: {
  gen: BilantGeneration
  onView: () => void
  onDownload: () => void
  onDelete: () => void
}) {
  return (
    <TableRow className="cursor-pointer hover:bg-muted/50" onClick={onView}>
      <TableCell className="font-medium">{gen.company_name || '-'}</TableCell>
      <TableCell>{gen.period_label || '-'}</TableCell>
      <TableCell className="text-muted-foreground text-xs">{gen.template_name || '-'}</TableCell>
      <TableCell>
        <Badge variant="secondary" className={statusColors[gen.status] || ''}>
          {gen.status}
        </Badge>
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">{fmtDate(gen.created_at)}</TableCell>
      <TableCell className="text-xs text-muted-foreground">{gen.generated_by_name || '-'}</TableCell>
      <TableCell>
        <div className="flex items-center gap-1" onClick={e => e.stopPropagation()}>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onView} title="View">
            <Eye className="h-3.5 w-3.5" />
          </Button>
          {gen.status === 'completed' && (
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onDownload} title="Download">
              <Download className="h-3.5 w-3.5" />
            </Button>
          )}
          <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={onDelete} title="Delete">
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </TableCell>
    </TableRow>
  )
}

function TemplateRow({ tpl, onEdit, onDuplicate, onDelete }: {
  tpl: BilantTemplate
  onEdit: () => void
  onDuplicate: () => void
  onDelete: () => void
}) {
  return (
    <TableRow>
      <TableCell className="font-medium">{tpl.name}</TableCell>
      <TableCell className="text-muted-foreground text-xs">{tpl.company_name || 'Global'}</TableCell>
      <TableCell>{tpl.row_count}</TableCell>
      <TableCell>
        {tpl.is_default && <Badge variant="secondary" className="bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400">Default</Badge>}
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">v{tpl.version}</TableCell>
      <TableCell>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onEdit} title="Edit">
            <Pencil className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onDuplicate} title="Duplicate">
            <Copy className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={onDelete} title="Delete">
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </TableCell>
    </TableRow>
  )
}
