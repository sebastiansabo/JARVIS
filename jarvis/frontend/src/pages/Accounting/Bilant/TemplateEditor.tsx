import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Plus, Trash2, GripVertical, Save, HelpCircle } from 'lucide-react'
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
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import type { BilantTemplateRow, BilantMetricConfig, MetricGroup } from '@/types/bilant'

type EditorTab = 'rows' | 'metrics' | 'info'

const ROW_TYPES = ['data', 'total', 'section', 'separator'] as const

const METRIC_GROUPS: { key: MetricGroup; label: string; description: string }[] = [
  { key: 'summary', label: 'Summary', description: 'Stat cards — maps a row (Nr.Rd) to a value' },
  { key: 'ratio_input', label: 'Ratio Inputs', description: 'Hidden data sources for ratios — maps a row (Nr.Rd) to a value' },
  { key: 'derived', label: 'Derived', description: 'Computed summary cards — uses a formula over other metric keys' },
  { key: 'ratio', label: 'Ratios', description: 'Financial ratios — computed via formula, shown as ratio cards' },
  { key: 'structure', label: 'Structure', description: 'Chart breakdown items — maps a row to assets or liabilities side' },
]

const DISPLAY_FORMATS = [
  { value: 'currency', label: 'Currency (RON)' },
  { value: 'ratio', label: 'Ratio (x.xx)' },
  { value: 'percent', label: 'Percent (%)' },
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
          <div className="flex items-center justify-between">
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="ghost" size="sm" className="text-muted-foreground">
                  <HelpCircle className="mr-1.5 h-4 w-4" />
                  Formula Syntax
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-80 text-xs" side="bottom" align="start">
                <div className="space-y-3">
                  <div>
                    <p className="font-semibold mb-1">CT Formula (Account References)</p>
                    <div className="space-y-1 text-muted-foreground">
                      <p><code className="font-mono text-primary">1011</code> — sum accounts starting with 1011</p>
                      <p><code className="font-mono text-primary">1011+1012</code> — add multiple account prefixes</p>
                      <p><code className="font-mono text-primary">201-2801</code> — subtract (SFD-SFC net)</p>
                      <p><code className="font-mono text-primary">+/-411</code> — dynamic sign (debit if positive)</p>
                      <p><code className="font-mono text-primary">dinct.472</code> — "din contul" (from account)</p>
                    </div>
                  </div>
                  <div>
                    <p className="font-semibold mb-1">RD Formula (Row References)</p>
                    <div className="space-y-1 text-muted-foreground">
                      <p><code className="font-mono text-primary">01+02+03</code> — sum of rows</p>
                      <p><code className="font-mono text-primary">10-11</code> — subtract rows</p>
                      <p><code className="font-mono text-primary">01 la 06</code> — range (expands to 01+02+...+06)</p>
                    </div>
                  </div>
                  <p className="text-muted-foreground italic">Type a number in CT formula to get account suggestions.</p>
                </div>
              </PopoverContent>
            </Popover>
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
        <MetricsTab
          metricConfigs={metricConfigs}
          availableRows={availableRows}
          onSave={(data) => setMetricMut.mutate(data)}
          onDelete={(id) => setDeleteTarget({ type: 'metric', id, name: metricConfigs.find(m => m.id === id)?.metric_label || 'metric' })}
          isSaving={setMetricMut.isPending}
        />
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
        <FormulaInput value={formulaCt} onChange={setFormulaCt} placeholder="ct formula" />
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

// ── Formula Input with Account Autocomplete ──

function FormulaInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [suggestions, setSuggestions] = useState<{ code: string; name: string; account_class: number; account_type: string }[]>([])
  const [selectedIdx, setSelectedIdx] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null)

  // Extract the last number token being typed (after operators like +, -, space)
  const getLastToken = useCallback((text: string): string | null => {
    const match = text.match(/(\d+)$/)
    return match ? match[1] : null
  }, [])

  const fetchSuggestions = useCallback((prefix: string) => {
    if (prefix.length < 1) { setSuggestions([]); return }
    bilantApi.autocompleteAccounts(prefix).then(res => {
      setSuggestions(res.accounts || [])
      setSelectedIdx(0)
    }).catch(() => setSuggestions([]))
  }, [])

  const handleChange = (text: string) => {
    onChange(text)
    const token = getLastToken(text)
    if (token && token.length >= 1) {
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => fetchSuggestions(token), 150)
      setShowSuggestions(true)
    } else {
      setSuggestions([])
      setShowSuggestions(false)
    }
  }

  const insertSuggestion = (code: string) => {
    const token = getLastToken(value)
    if (token) {
      const before = value.slice(0, value.length - token.length)
      onChange(before + code)
    } else {
      onChange(value + code)
    }
    setShowSuggestions(false)
    setSuggestions([])
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!showSuggestions || suggestions.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIdx(i => Math.min(i + 1, suggestions.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIdx(i => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' || e.key === 'Tab') {
      e.preventDefault()
      insertSuggestion(suggestions[selectedIdx].code)
    } else if (e.key === 'Escape') {
      setShowSuggestions(false)
    }
  }

  // Close suggestions on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowSuggestions(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  return (
    <div ref={containerRef} className="relative">
      <Input
        value={value}
        onChange={e => handleChange(e.target.value)}
        onKeyDown={handleKeyDown}
        onFocus={() => { const t = getLastToken(value); if (t) { fetchSuggestions(t); setShowSuggestions(true) } }}
        className="h-7 text-xs font-mono"
        placeholder={placeholder}
      />
      {showSuggestions && suggestions.length > 0 && (
        <div className="absolute left-0 top-full z-50 mt-1 max-h-48 w-72 overflow-y-auto rounded-md border bg-popover shadow-md">
          {suggestions.map((s, i) => (
            <button
              key={s.code}
              className={`flex w-full items-center gap-2 px-2 py-1.5 text-left text-xs hover:bg-accent ${i === selectedIdx ? 'bg-accent' : ''}`}
              onMouseDown={(e) => { e.preventDefault(); insertSuggestion(s.code) }}
            >
              <span className="font-mono font-medium text-primary">{s.code}</span>
              <span className="truncate text-muted-foreground">{s.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}


// ── Dynamic Metrics Tab ──

interface MetricsTabProps {
  metricConfigs: BilantMetricConfig[]
  availableRows: { nr_rd: string; desc: string }[]
  onSave: (data: Partial<BilantMetricConfig>) => void
  onDelete: (id: number) => void
  isSaving: boolean
}

const EMPTY_METRIC: Partial<BilantMetricConfig> = {
  metric_key: '',
  metric_label: '',
  nr_rd: null,
  metric_group: 'summary',
  formula_expr: null,
  display_format: 'currency',
  interpretation: null,
  threshold_good: null,
  threshold_warning: null,
  structure_side: null,
}

function MetricsTab({ metricConfigs, availableRows, onSave, onDelete, isSaving }: MetricsTabProps) {
  const [showDialog, setShowDialog] = useState(false)
  const [editForm, setEditForm] = useState<Partial<BilantMetricConfig>>(EMPTY_METRIC)
  const [editingId, setEditingId] = useState<number | null>(null)

  const openAdd = (group?: MetricGroup) => {
    setEditForm({ ...EMPTY_METRIC, metric_group: group || 'summary', sort_order: metricConfigs.length })
    setEditingId(null)
    setShowDialog(true)
  }

  const openEdit = (cfg: BilantMetricConfig) => {
    setEditForm({ ...cfg })
    setEditingId(cfg.id)
    setShowDialog(true)
  }

  const handleSave = () => {
    if (!editForm.metric_key?.trim() || !editForm.metric_label?.trim()) {
      toast.error('Key and label are required')
      return
    }
    onSave(editForm)
    setShowDialog(false)
  }

  const groupedConfigs = METRIC_GROUPS.map(g => ({
    ...g,
    configs: metricConfigs.filter(c => c.metric_group === g.key),
  }))

  const needsNrRd = editForm.metric_group === 'summary' || editForm.metric_group === 'ratio_input' || editForm.metric_group === 'structure'
  const needsFormula = editForm.metric_group === 'ratio' || editForm.metric_group === 'derived'
  const needsStructureSide = editForm.metric_group === 'structure'
  const needsThresholds = editForm.metric_group === 'ratio'

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Configure metrics for summary cards, financial ratios, and structure charts.
        </p>
        <Button size="sm" onClick={() => openAdd()}>
          <Plus className="mr-1.5 h-4 w-4" />
          Add Metric
        </Button>
      </div>

      {metricConfigs.length === 0 && (
        <Card className="py-8">
          <CardContent className="text-center text-sm text-muted-foreground">
            No metrics configured yet. Click "Add Metric" to get started.
          </CardContent>
        </Card>
      )}

      {groupedConfigs.map(group => {
        if (group.configs.length === 0) return null
        return (
          <div key={group.key} className="space-y-2">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold">{group.label}</h3>
                <p className="text-xs text-muted-foreground">{group.description}</p>
              </div>
              <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => openAdd(group.key)}>
                <Plus className="mr-1 h-3 w-3" />
                Add
              </Button>
            </div>
            <div className="grid gap-2">
              {group.configs.map(cfg => (
                <Card key={cfg.id} className="gap-0 py-0">
                  <CardContent className="flex items-center justify-between px-4 py-2.5">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate">{cfg.metric_label}</p>
                        <p className="text-xs text-muted-foreground font-mono">{cfg.metric_key}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {cfg.nr_rd && (
                        <Badge variant="secondary" className="bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400 text-xs">
                          Rd.{cfg.nr_rd}
                        </Badge>
                      )}
                      {cfg.formula_expr && (
                        <Badge variant="secondary" className="bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400 text-xs font-mono max-w-40 truncate">
                          {cfg.formula_expr}
                        </Badge>
                      )}
                      {cfg.structure_side && (
                        <Badge variant="outline" className="text-xs">{cfg.structure_side}</Badge>
                      )}
                      {cfg.display_format !== 'currency' && (
                        <Badge variant="outline" className="text-xs">{cfg.display_format}</Badge>
                      )}
                      <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => openEdit(cfg)}>
                        Edit
                      </Button>
                      <Button variant="ghost" size="icon" className="h-6 w-6 text-destructive" onClick={() => onDelete(cfg.id)}>
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )
      })}

      {/* Add/Edit Metric Dialog */}
      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editingId ? 'Edit Metric' : 'Add Metric'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Key (unique identifier)</Label>
                <Input
                  value={editForm.metric_key || ''}
                  onChange={e => setEditForm(f => ({ ...f, metric_key: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_') }))}
                  placeholder="e.g. lichiditate_curenta"
                  className="font-mono text-sm"
                  disabled={!!editingId}
                />
              </div>
              <div className="space-y-2">
                <Label>Label</Label>
                <Input
                  value={editForm.metric_label || ''}
                  onChange={e => {
                    const label = e.target.value
                    setEditForm(f => ({
                      ...f,
                      metric_label: label,
                      ...(!editingId && !f.metric_key ? { metric_key: label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/_+$/, '') } : {}),
                    }))
                  }}
                  placeholder="e.g. Lichiditate Curenta"
                />
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Group</Label>
                <Select
                  value={editForm.metric_group || 'summary'}
                  onValueChange={(v) => setEditForm(f => ({ ...f, metric_group: v as MetricGroup }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {METRIC_GROUPS.map(g => (
                      <SelectItem key={g.key} value={g.key}>{g.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Display Format</Label>
                <Select
                  value={editForm.display_format || 'currency'}
                  onValueChange={(v) => setEditForm(f => ({ ...f, display_format: v as 'currency' | 'ratio' | 'percent' }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {DISPLAY_FORMATS.map(f => (
                      <SelectItem key={f.value} value={f.value}>{f.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {needsNrRd && (
              <div className="space-y-2">
                <Label>Row Mapping (Nr.Rd)</Label>
                <Select
                  value={editForm.nr_rd || 'none'}
                  onValueChange={(v) => setEditForm(f => ({ ...f, nr_rd: v === 'none' ? null : v }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select row" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Not mapped</SelectItem>
                    {availableRows.map(r => (
                      <SelectItem key={r.nr_rd} value={r.nr_rd}>
                        Rd.{r.nr_rd} — {r.desc.substring(0, 50)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {needsFormula && (
              <div className="space-y-2">
                <Label>Formula Expression</Label>
                <Input
                  value={editForm.formula_expr || ''}
                  onChange={e => setEditForm(f => ({ ...f, formula_expr: e.target.value }))}
                  placeholder="e.g. active_circulante / datorii_termen_scurt"
                  className="font-mono text-sm"
                />
                <p className="text-xs text-muted-foreground">
                  Use metric keys with +, -, *, / and parentheses. E.g. <code>active_circulante / datorii_termen_scurt</code>
                </p>
              </div>
            )}

            {needsStructureSide && (
              <div className="space-y-2">
                <Label>Structure Side</Label>
                <Select
                  value={editForm.structure_side || 'assets'}
                  onValueChange={(v) => setEditForm(f => ({ ...f, structure_side: v as 'assets' | 'liabilities' }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="assets">Assets</SelectItem>
                    <SelectItem value="liabilities">Liabilities</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}

            {needsThresholds && (
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>Threshold Good</Label>
                  <Input
                    type="number"
                    step="0.01"
                    value={editForm.threshold_good ?? ''}
                    onChange={e => setEditForm(f => ({ ...f, threshold_good: e.target.value ? Number(e.target.value) : null }))}
                    placeholder="e.g. 1.0"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Threshold Warning</Label>
                  <Input
                    type="number"
                    step="0.01"
                    value={editForm.threshold_warning ?? ''}
                    onChange={e => setEditForm(f => ({ ...f, threshold_warning: e.target.value ? Number(e.target.value) : null }))}
                    placeholder="e.g. 0.5"
                  />
                </div>
              </div>
            )}

            <div className="space-y-2">
              <Label>Interpretation</Label>
              <Textarea
                value={editForm.interpretation || ''}
                onChange={e => setEditForm(f => ({ ...f, interpretation: e.target.value || null }))}
                placeholder="e.g. Ideal > 1"
                rows={2}
              />
            </div>

            <div className="space-y-2">
              <Label>Sort Order</Label>
              <Input
                type="number"
                value={editForm.sort_order ?? 0}
                onChange={e => setEditForm(f => ({ ...f, sort_order: Number(e.target.value) }))}
                className="w-20"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDialog(false)}>Cancel</Button>
            <Button onClick={handleSave} disabled={isSaving}>
              {editingId ? 'Update' : 'Add'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
