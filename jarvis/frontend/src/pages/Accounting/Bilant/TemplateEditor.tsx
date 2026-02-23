import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Plus, Trash2, GripVertical, Save } from 'lucide-react'
import { toast } from 'sonner'

import { bilantApi } from '@/api/bilant'
import { organizationApi } from '@/api/organization'
import { PageHeader } from '@/components/shared/PageHeader'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import type { BilantTemplateRow, BilantMetricConfig } from '@/types/bilant'

type EditorTab = 'rows' | 'metrics' | 'info'

const ROW_TYPES = ['data', 'total', 'section', 'separator'] as const

const STANDARD_METRICS = [
  { key: 'active_imobilizate', label: 'Active Imobilizate', group: 'summary' },
  { key: 'active_circulante', label: 'Active Circulante', group: 'summary' },
  { key: 'stocuri', label: 'Stocuri', group: 'ratio_input' },
  { key: 'disponibilitati', label: 'Disponibilitati', group: 'ratio_input' },
  { key: 'creante', label: 'Creante', group: 'ratio_input' },
  { key: 'datorii_termen_scurt', label: 'Datorii < 1 an', group: 'ratio_input' },
  { key: 'datorii_termen_lung', label: 'Datorii > 1 an', group: 'ratio_input' },
  { key: 'capitaluri_proprii', label: 'Capitaluri Proprii', group: 'summary' },
  { key: 'capital_social', label: 'Capital Social', group: 'ratio_input' },
]

export default function TemplateEditor() {
  const { templateId } = useParams<{ templateId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [tab, setTab] = useState<EditorTab>('rows')
  const [editingRow, setEditingRow] = useState<number | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<{ type: 'row' | 'metric'; id: number; name: string } | null>(null)

  // Template info state
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [companyId, setCompanyId] = useState<string>('')
  const [isDefault, setIsDefault] = useState(false)

  const { data: companiesData } = useQuery({
    queryKey: ['companies-config'],
    queryFn: () => organizationApi.getCompaniesConfig(),
  })
  const companies = companiesData || []

  const { data, isLoading } = useQuery({
    queryKey: ['bilant-template', templateId],
    queryFn: () => bilantApi.getTemplate(Number(templateId)),
    enabled: !!templateId,
  })

  const template = data?.template
  const rows = data?.rows || []
  const metricConfigs = data?.metrics || []

  // Sync state when template loads
  useEffect(() => {
    if (template) {
      setName(template.name)
      setDescription(template.description || '')
      setCompanyId(template.company_id ? String(template.company_id) : '')
      setIsDefault(template.is_default)
    }
  }, [template])

  // ── Mutations ──

  const updateTplMut = useMutation({
    mutationFn: (data: Record<string, unknown>) => bilantApi.updateTemplate(Number(templateId), data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bilant-template', templateId] }); toast.success('Template updated') },
  })

  const addRowMut = useMutation({
    mutationFn: (data: Partial<BilantTemplateRow>) => bilantApi.addRow(Number(templateId), data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bilant-template', templateId] }); toast.success('Row added') },
  })

  const updateRowMut = useMutation({
    mutationFn: ({ id, ...data }: Partial<BilantTemplateRow> & { id: number }) => bilantApi.updateRow(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bilant-template', templateId] }) },
  })

  const deleteRowMut = useMutation({
    mutationFn: (id: number) => bilantApi.deleteRow(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bilant-template', templateId] }); toast.success('Row deleted') },
  })

  const setMetricMut = useMutation({
    mutationFn: (data: Partial<BilantMetricConfig>) => bilantApi.setMetricConfig(Number(templateId), data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bilant-template', templateId] }); toast.success('Metric saved') },
  })

  const deleteMetricMut = useMutation({
    mutationFn: (id: number) => bilantApi.deleteMetricConfig(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bilant-template', templateId] }); toast.success('Metric removed') },
  })

  const handleDelete = () => {
    if (!deleteTarget) return
    if (deleteTarget.type === 'row') deleteRowMut.mutate(deleteTarget.id)
    else deleteMetricMut.mutate(deleteTarget.id)
    setDeleteTarget(null)
  }

  const handleSaveInfo = () => {
    updateTplMut.mutate({
      name: name.trim(),
      description: description.trim() || null,
      company_id: companyId && companyId !== 'global' ? Number(companyId) : null,
      is_default: isDefault,
    })
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-96" />
        <Skeleton className="h-96" />
      </div>
    )
  }

  if (!template) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={() => navigate('/app/accounting/bilant?tab=templates')}>
          <ArrowLeft className="mr-1.5 h-4 w-4" /> Back
        </Button>
        <p className="text-sm text-destructive">Template not found</p>
      </div>
    )
  }

  const tabs: { key: EditorTab; label: string }[] = [
    { key: 'rows', label: `Rows (${rows.length})` },
    { key: 'metrics', label: `Metrics (${metricConfigs.length})` },
    { key: 'info', label: 'Info' },
  ]

  // Available nr_rd values for metric mapping
  const availableRows = rows.filter(r => r.nr_rd).map(r => ({ nr_rd: r.nr_rd!, desc: r.description }))

  return (
    <div className="space-y-4">
      <PageHeader
        title={template.name}
        description={`v${template.version} — ${rows.length} rows`}
        breadcrumbs={[
          { label: 'Accounting', href: '/app/accounting' },
          { label: 'Bilant', href: '/app/accounting/bilant?tab=templates' },
          { label: template.name },
        ]}
        actions={
          <div className="flex items-center gap-2">
            {template.is_default && <Badge variant="secondary" className="bg-blue-100 text-blue-800">Default</Badge>}
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
      </div>

      {/* Rows Tab */}
      {tab === 'rows' && (
        <div className="space-y-3">
          <div className="flex justify-end">
            <Button
              size="sm"
              onClick={() => addRowMut.mutate({
                description: 'New Row',
                row_type: 'data',
                sort_order: rows.length,
              })}
            >
              <Plus className="mr-1.5 h-4 w-4" />
              Add Row
            </Button>
          </div>

          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8" />
                  <TableHead className="w-16">Nr.Rd</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead className="w-32">CT Formula</TableHead>
                  <TableHead className="w-32">RD Formula</TableHead>
                  <TableHead className="w-20">Type</TableHead>
                  <TableHead className="w-12">Bold</TableHead>
                  <TableHead className="w-16">Indent</TableHead>
                  <TableHead className="w-16">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <EditableRow
                    key={row.id}
                    row={row}
                    isEditing={editingRow === row.id}
                    onStartEdit={() => setEditingRow(row.id)}
                    onSave={(data) => {
                      updateRowMut.mutate({ id: row.id, ...data })
                      setEditingRow(null)
                    }}
                    onCancel={() => setEditingRow(null)}
                    onDelete={() => setDeleteTarget({ type: 'row', id: row.id, name: row.description || `Row ${row.nr_rd}` })}
                  />
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}

      {/* Metrics Tab */}
      {tab === 'metrics' && (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Map template row numbers (Nr.Rd) to standard financial metrics used for ratio calculations.
          </p>

          <div className="grid gap-3">
            {STANDARD_METRICS.map(sm => {
              const existing = metricConfigs.find(mc => mc.metric_key === sm.key)
              return (
                <Card key={sm.key} className="gap-0 py-0">
                  <CardContent className="flex items-center justify-between px-4 py-3">
                    <div>
                      <p className="text-sm font-medium">{sm.label}</p>
                      <p className="text-xs text-muted-foreground">{sm.key} ({sm.group})</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Select
                        value={existing?.nr_rd || ''}
                        onValueChange={(nr_rd) => {
                          if (nr_rd === 'none') {
                            if (existing) deleteMetricMut.mutate(existing.id)
                          } else {
                            setMetricMut.mutate({
                              metric_key: sm.key,
                              metric_label: sm.label,
                              nr_rd,
                              metric_group: sm.group as 'summary' | 'ratio_input',
                            })
                          }
                        }}
                      >
                        <SelectTrigger className="h-8 w-[200px] text-xs">
                          <SelectValue placeholder="Not mapped" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">Not mapped</SelectItem>
                          {availableRows.map(r => (
                            <SelectItem key={r.nr_rd} value={r.nr_rd}>
                              Rd.{r.nr_rd} — {r.desc.substring(0, 40)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      {existing && (
                        <Badge variant="secondary" className="bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400">
                          Rd.{existing.nr_rd}
                        </Badge>
                      )}
                    </div>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </div>
      )}

      {/* Info Tab */}
      {tab === 'info' && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Template Settings</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Name</Label>
                <Input value={name} onChange={e => setName(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>Company</Label>
                <Select value={companyId || 'global'} onValueChange={setCompanyId}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="global">Global (all companies)</SelectItem>
                    {companies.map(c => (
                      <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label>Description</Label>
              <Input value={description} onChange={e => setDescription(e.target.value)} placeholder="Optional description" />
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={isDefault} onCheckedChange={setIsDefault} />
              <Label>Default template</Label>
            </div>
            <div className="flex justify-end">
              <Button onClick={handleSaveInfo} disabled={!name.trim() || updateTplMut.isPending}>
                <Save className="mr-1.5 h-4 w-4" />
                Save Changes
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Delete Confirm */}
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={() => setDeleteTarget(null)}
        title={`Delete ${deleteTarget?.type}?`}
        description={`Delete "${deleteTarget?.name}"?`}
        onConfirm={handleDelete}
        confirmLabel="Delete"
        variant="destructive"
      />
    </div>
  )
}

// ── Editable Row ──

interface EditableRowProps {
  row: BilantTemplateRow
  isEditing: boolean
  onStartEdit: () => void
  onSave: (data: Partial<BilantTemplateRow>) => void
  onCancel: () => void
  onDelete: () => void
}

function EditableRow({ row, isEditing, onStartEdit, onSave, onCancel, onDelete }: EditableRowProps) {
  const [nr_rd, setNrRd] = useState(row.nr_rd || '')
  const [desc, setDesc] = useState(row.description)
  const [formulaCt, setFormulaCt] = useState(row.formula_ct || '')
  const [formulaRd, setFormulaRd] = useState(row.formula_rd || '')
  const [rowType, setRowType] = useState(row.row_type)
  const [isBold, setIsBold] = useState(row.is_bold)
  const [indent, setIndent] = useState(row.indent_level)

  useEffect(() => {
    setNrRd(row.nr_rd || '')
    setDesc(row.description)
    setFormulaCt(row.formula_ct || '')
    setFormulaRd(row.formula_rd || '')
    setRowType(row.row_type)
    setIsBold(row.is_bold)
    setIndent(row.indent_level)
  }, [row])

  if (!isEditing) {
    return (
      <TableRow className="cursor-pointer hover:bg-muted/50" onDoubleClick={onStartEdit}>
        <TableCell><GripVertical className="h-3.5 w-3.5 text-muted-foreground" /></TableCell>
        <TableCell className="text-xs font-mono">{row.nr_rd || ''}</TableCell>
        <TableCell>
          <span
            className={`text-xs ${row.row_type === 'section' ? 'font-semibold uppercase text-muted-foreground' : ''} ${row.is_bold ? 'font-semibold' : ''}`}
            style={{ paddingLeft: `${(row.indent_level || 0) * 12}px` }}
          >
            {row.description}
          </span>
        </TableCell>
        <TableCell className="text-xs font-mono text-muted-foreground">{row.formula_ct || ''}</TableCell>
        <TableCell className="text-xs font-mono text-muted-foreground">{row.formula_rd || ''}</TableCell>
        <TableCell><Badge variant="outline" className="text-[10px]">{row.row_type}</Badge></TableCell>
        <TableCell>{row.is_bold ? 'B' : ''}</TableCell>
        <TableCell className="text-xs">{row.indent_level || 0}</TableCell>
        <TableCell>
          <Button variant="ghost" size="icon" className="h-6 w-6 text-destructive" onClick={onDelete}>
            <Trash2 className="h-3 w-3" />
          </Button>
        </TableCell>
      </TableRow>
    )
  }

  return (
    <TableRow className="bg-muted/30">
      <TableCell />
      <TableCell>
        <Input value={nr_rd} onChange={e => setNrRd(e.target.value)} className="h-7 text-xs w-14" />
      </TableCell>
      <TableCell>
        <Input value={desc} onChange={e => setDesc(e.target.value)} className="h-7 text-xs" />
      </TableCell>
      <TableCell>
        <Input value={formulaCt} onChange={e => setFormulaCt(e.target.value)} className="h-7 text-xs font-mono" placeholder="ct formula" />
      </TableCell>
      <TableCell>
        <Input value={formulaRd} onChange={e => setFormulaRd(e.target.value)} className="h-7 text-xs font-mono" placeholder="rd formula" />
      </TableCell>
      <TableCell>
        <Select value={rowType} onValueChange={(v) => setRowType(v as BilantTemplateRow['row_type'])}>
          <SelectTrigger className="h-7 text-[10px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ROW_TYPES.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
          </SelectContent>
        </Select>
      </TableCell>
      <TableCell>
        <Switch checked={isBold} onCheckedChange={setIsBold} />
      </TableCell>
      <TableCell>
        <Input type="number" value={indent} onChange={e => setIndent(Number(e.target.value))} className="h-7 text-xs w-12" min={0} max={5} />
      </TableCell>
      <TableCell>
        <div className="flex gap-1">
          <Button
            size="sm"
            className="h-6 px-2 text-xs"
            onClick={() => onSave({
              nr_rd: nr_rd || null,
              description: desc,
              formula_ct: formulaCt || null,
              formula_rd: formulaRd || null,
              row_type: rowType,
              is_bold: isBold,
              indent_level: indent,
            })}
          >
            Save
          </Button>
          <Button size="sm" variant="outline" className="h-6 px-2 text-xs" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </TableCell>
    </TableRow>
  )
}
