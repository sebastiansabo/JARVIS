import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Pencil, Save, Bot, RefreshCw, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Separator } from '@/components/ui/separator'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { EmptyState } from '@/components/shared/EmptyState'
import { marketingApi } from '@/api/marketing'
import { settingsApi } from '@/api/settings'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { toast } from 'sonner'
import type { MktKpiDefinition, KpiBenchmarks } from '@/types/marketing'
import type { DropdownOption } from '@/types/settings'

const UNITS = [
  { value: 'number', label: 'Number' },
  { value: 'currency', label: 'Currency' },
  { value: 'percentage', label: 'Percentage' },
  { value: 'ratio', label: 'Ratio' },
]

const DIRECTIONS = [
  { value: 'higher', label: 'Higher is better' },
  { value: 'lower', label: 'Lower is better' },
]

const CATEGORIES = ['performance', 'financial', 'engagement', 'conversion', 'brand']

export default function MarketingTab() {
  return (
    <div className="space-y-6">
      <ChannelOptionsSection />
      <KpiDefinitionsSection />
    </div>
  )
}

/* ── Channel Options (mkt_channel) ──────────────────────── */

function ChannelOptionsSection() {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [editOpt, setEditOpt] = useState<DropdownOption | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { data: options = [], isLoading } = useQuery({
    queryKey: ['dropdown-options', 'mkt_channel'],
    queryFn: () => settingsApi.getDropdownOptions('mkt_channel'),
    staleTime: 5 * 60_000,
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['dropdown-options', 'mkt_channel'] })

  const createMut = useMutation({
    mutationFn: (data: Partial<DropdownOption>) => settingsApi.addDropdownOption(data),
    onSuccess: () => { invalidate(); setShowForm(false); toast.success('Channel added') },
    onError: (e: any) => toast.error(e?.message || 'Failed to create'),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<DropdownOption> }) =>
      settingsApi.updateDropdownOption(id, data),
    onSuccess: () => { invalidate(); setShowForm(false); setEditOpt(null); toast.success('Channel updated') },
    onError: (e: any) => toast.error(e?.message || 'Failed to update'),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => settingsApi.deleteDropdownOption(id),
    onSuccess: () => { invalidate(); setDeleteId(null); toast.success('Channel deleted') },
    onError: (e: any) => toast.error(e?.message || 'Failed to delete'),
  })

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Channel Options</CardTitle>
            <CardDescription>
              Manage the marketing channels available in project budget lines and channel mix.
            </CardDescription>
          </div>
          <Button size="sm" onClick={() => { setEditOpt(null); setShowForm(true) }}>
            <Plus className="mr-1.5 h-4 w-4" />
            Add Channel
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : options.length === 0 ? (
          <EmptyState title="No channels" description="Add your first marketing channel." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Value</TableHead>
                <TableHead>Label</TableHead>
                <TableHead>Order</TableHead>
                <TableHead>Active</TableHead>
                <TableHead className="w-24">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {options.map((opt) => (
                <TableRow key={opt.id}>
                  <TableCell className="font-mono text-xs">{opt.value}</TableCell>
                  <TableCell className="font-medium">{opt.label}</TableCell>
                  <TableCell>{opt.sort_order}</TableCell>
                  <TableCell>{opt.is_active ? 'Yes' : 'No'}</TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="sm" onClick={() => { setEditOpt(opt); setShowForm(true) }}>
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setDeleteId(opt.id)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>

      <ChannelFormDialog
        open={showForm || !!editOpt}
        option={editOpt}
        optionCount={options.length}
        onClose={() => { setShowForm(false); setEditOpt(null) }}
        onSave={(data) => {
          if (editOpt) {
            updateMut.mutate({ id: editOpt.id, data })
          } else {
            createMut.mutate(data)
          }
        }}
        isPending={createMut.isPending || updateMut.isPending}
      />

      <ConfirmDialog
        open={!!deleteId}
        onOpenChange={() => setDeleteId(null)}
        title="Delete Channel"
        description="This will remove the channel option. Existing budget lines using it won't be affected."
        onConfirm={() => deleteId && deleteMut.mutate(deleteId)}
        destructive
      />
    </Card>
  )
}

function ChannelFormDialog({ open, option, optionCount, onClose, onSave, isPending }: {
  open: boolean; option: DropdownOption | null; optionCount: number
  onClose: () => void; onSave: (data: Partial<DropdownOption>) => void; isPending: boolean
}) {
  const [value, setValue] = useState('')
  const [label, setLabel] = useState('')
  const [sortOrder, setSortOrder] = useState(0)
  const [isActive, setIsActive] = useState(true)

  const resetForm = () => {
    if (option) {
      setValue(option.value); setLabel(option.label)
      setSortOrder(option.sort_order); setIsActive(option.is_active)
    } else {
      setValue(''); setLabel(''); setSortOrder(optionCount + 1); setIsActive(true)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); else resetForm() }}>
      <DialogContent className="sm:max-w-md" onOpenAutoFocus={resetForm}>
        <DialogHeader>
          <DialogTitle>{option ? 'Edit Channel' : 'Add Channel'}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Value (key)</Label>
              <Input
                value={value}
                onChange={(e) => setValue(e.target.value.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, ''))}
                placeholder="google_ads"
                className="font-mono text-sm"
                disabled={!!option}
              />
            </div>
            <div className="grid gap-2">
              <Label>Label</Label>
              <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Google Ads" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Sort Order</Label>
              <Input type="number" value={sortOrder} onChange={(e) => setSortOrder(Number(e.target.value))} />
            </div>
            <div className="flex items-center gap-2 pt-6">
              <Switch checked={isActive} onCheckedChange={setIsActive} />
              <Label className="text-sm">{isActive ? 'Active' : 'Inactive'}</Label>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            disabled={!value || !label || isPending}
            onClick={() => onSave({
              dropdown_type: 'mkt_channel',
              value,
              label,
              sort_order: sortOrder,
              is_active: isActive,
            })}
          >
            <Save className="mr-1.5 h-4 w-4" />
            {isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function KpiDefinitionsSection() {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [editDef, setEditDef] = useState<MktKpiDefinition | null>(null)

  const { data: defsData, isLoading } = useQuery({
    queryKey: ['mkt-kpi-definitions-all'],
    queryFn: () => marketingApi.getKpiDefinitions(false),
    staleTime: 10 * 60_000,
  })
  const definitions = defsData?.definitions ?? []

  const createMut = useMutation({
    mutationFn: (data: Partial<MktKpiDefinition>) => marketingApi.createKpiDefinition(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-kpi-definitions'] })
      queryClient.invalidateQueries({ queryKey: ['mkt-kpi-definitions-all'] })
      setShowForm(false)
      toast.success('KPI definition created')
    },
    onError: (e: any) => toast.error(e?.message || 'Failed to create'),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<MktKpiDefinition> }) =>
      marketingApi.updateKpiDefinition(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-kpi-definitions'] })
      queryClient.invalidateQueries({ queryKey: ['mkt-kpi-definitions-all'] })
      setEditDef(null)
      setShowForm(false)
      toast.success('KPI definition updated')
    },
    onError: (e: any) => toast.error(e?.message || 'Failed to update'),
  })

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>KPI Definitions</CardTitle>
            <CardDescription>
              Manage reusable KPI templates with formulas. These definitions are available across all marketing projects.
            </CardDescription>
          </div>
          <Button size="sm" onClick={() => { setEditDef(null); setShowForm(true) }}>
            <Plus className="mr-1.5 h-4 w-4" />
            Add Definition
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : definitions.length === 0 ? (
          <EmptyState title="No KPI definitions" description="Add your first KPI template." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Slug</TableHead>
                <TableHead>Unit</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Formula</TableHead>
                <TableHead>Benchmarks</TableHead>
                <TableHead>Active</TableHead>
                <TableHead className="w-16">Edit</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {definitions.map((d) => (
                <TableRow key={d.id} className={!d.is_active ? 'opacity-50' : ''}>
                  <TableCell className="font-medium">{d.name}</TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">{d.slug}</TableCell>
                  <TableCell className="text-xs">{d.unit}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-xs">{d.category}</Badge>
                  </TableCell>
                  <TableCell className="font-mono text-xs max-w-[180px] truncate">
                    {d.formula || <span className="text-muted-foreground">—</span>}
                  </TableCell>
                  <TableCell>
                    {d.benchmarks?.segments?.length ? (
                      <Badge variant="secondary" className="text-[10px]">
                        {d.benchmarks.segments.length} segment{d.benchmarks.segments.length > 1 ? 's' : ''}
                      </Badge>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant={d.is_active ? 'default' : 'secondary'} className="text-[10px]">
                      {d.is_active ? 'Yes' : 'No'}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Button variant="ghost" size="sm" onClick={() => { setEditDef(d); setShowForm(true) }}>
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>

      <KpiDefFormDialog
        open={showForm}
        definition={editDef}
        onClose={() => { setShowForm(false); setEditDef(null) }}
        onSave={(data) => {
          if (editDef) {
            updateMut.mutate({ id: editDef.id, data })
          } else {
            createMut.mutate(data)
          }
        }}
        isPending={createMut.isPending || updateMut.isPending}
      />
    </Card>
  )
}

interface FormState {
  name: string
  slug: string
  unit: string
  direction: string
  category: string
  formula: string
  description: string
  is_active: boolean
}

const emptyForm: FormState = {
  name: '', slug: '', unit: 'number', direction: 'higher',
  category: 'performance', formula: '', description: '', is_active: true,
}

function KpiDefFormDialog({ open, definition, onClose, onSave, isPending }: {
  open: boolean; definition: MktKpiDefinition | null; onClose: () => void
  onSave: (data: Partial<MktKpiDefinition>) => void; isPending: boolean
}) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<FormState>(emptyForm)
  const [formulaVars, setFormulaVars] = useState<string[]>([])
  const [formulaError, setFormulaError] = useState<string | null>(null)
  const [validating, setValidating] = useState(false)
  const [benchmarks, setBenchmarks] = useState<KpiBenchmarks | null>(null)

  const benchmarkMut = useMutation({
    mutationFn: (defId: number) => marketingApi.generateBenchmarks(defId),
    onSuccess: (data) => {
      setBenchmarks(data.benchmarks)
      queryClient.invalidateQueries({ queryKey: ['mkt-kpi-definitions'] })
      queryClient.invalidateQueries({ queryKey: ['mkt-kpi-definitions-all'] })
      toast.success('Benchmarks generated')
    },
    onError: (e: any) => toast.error(e?.message || 'Failed to generate benchmarks'),
  })

  const resetForm = () => {
    if (definition) {
      setForm({
        name: definition.name,
        slug: definition.slug,
        unit: definition.unit,
        direction: definition.direction,
        category: definition.category,
        formula: definition.formula || '',
        description: definition.description || '',
        is_active: definition.is_active,
      })
      setFormulaVars(definition.variables ?? [])
      setFormulaError(null)
      setBenchmarks(definition.benchmarks)
    } else {
      setForm(emptyForm)
      setFormulaVars([])
      setFormulaError(null)
      setBenchmarks(null)
    }
  }

  // Auto-generate slug from name (only for new definitions)
  useEffect(() => {
    if (!definition && form.name) {
      const slug = form.name
        .toLowerCase()
        .replace(/[^a-z0-9\s]/g, '')
        .replace(/\s+/g, '_')
        .substring(0, 30)
      setForm((f) => ({ ...f, slug }))
    }
  }, [form.name, definition])

  const validateFormula = async (formula: string) => {
    if (!formula.trim()) {
      setFormulaVars([])
      setFormulaError(null)
      return
    }
    setValidating(true)
    try {
      const res = await marketingApi.validateFormula(formula)
      if (res.valid) {
        setFormulaVars(res.variables)
        setFormulaError(null)
      } else {
        setFormulaVars([])
        setFormulaError(res.error)
      }
    } catch {
      setFormulaError('Validation failed')
    } finally {
      setValidating(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); else resetForm() }}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto" onOpenAutoFocus={resetForm}>
        <DialogHeader>
          <DialogTitle>{definition ? 'Edit KPI Definition' : 'Add KPI Definition'}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Name</Label>
              <Input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Cost Per Lead"
              />
            </div>
            <div className="grid gap-2">
              <Label>Slug</Label>
              <Input
                value={form.slug}
                onChange={(e) => setForm({ ...form, slug: e.target.value })}
                placeholder="cpl"
                className="font-mono text-sm"
              />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div className="grid gap-2">
              <Label>Unit</Label>
              <Select value={form.unit} onValueChange={(v) => setForm({ ...form, unit: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {UNITS.map((u) => <SelectItem key={u.value} value={u.value}>{u.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>Direction</Label>
              <Select value={form.direction} onValueChange={(v) => setForm({ ...form, direction: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {DIRECTIONS.map((d) => <SelectItem key={d.value} value={d.value}>{d.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>Category</Label>
              <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-2">
            <Label>Formula</Label>
            <Input
              value={form.formula}
              onChange={(e) => setForm({ ...form, formula: e.target.value })}
              onBlur={() => validateFormula(form.formula)}
              placeholder="spent / leads"
              className="font-mono text-sm"
            />
            <div className="min-h-[20px]">
              {validating && <span className="text-xs text-muted-foreground">Validating...</span>}
              {formulaError && <span className="text-xs text-destructive">{formulaError}</span>}
              {!formulaError && formulaVars.length > 0 && (
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-muted-foreground">Variables:</span>
                  {formulaVars.map((v) => (
                    <Badge key={v} variant="secondary" className="text-[10px] h-5">{v}</Badge>
                  ))}
                </div>
              )}
              {!form.formula.trim() && (
                <span className="text-xs text-muted-foreground">Leave empty for raw/manual KPIs (no formula)</span>
              )}
            </div>
          </div>
          <div className="grid gap-2">
            <Label>Description</Label>
            <Textarea
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              rows={2}
              placeholder="What this KPI measures..."
            />
          </div>
          {definition && (
            <div className="flex items-center gap-2">
              <Switch
                checked={form.is_active}
                onCheckedChange={(v) => setForm({ ...form, is_active: v })}
              />
              <Label className="text-sm">{form.is_active ? 'Active' : 'Inactive'}</Label>
            </div>
          )}

          {/* Benchmarks section (only for existing definitions) */}
          {definition && (
            <>
              <Separator />
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label className="text-sm font-medium">Industry Benchmarks</Label>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={benchmarkMut.isPending}
                    onClick={() => definition && benchmarkMut.mutate(definition.id)}
                  >
                    {benchmarkMut.isPending ? (
                      <RefreshCw className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Bot className="mr-1.5 h-3.5 w-3.5" />
                    )}
                    {benchmarkMut.isPending ? 'Generating...' : benchmarks ? 'Regenerate' : 'Generate with AI'}
                  </Button>
                </div>
                {benchmarks?.segments?.length ? (
                  <div className="space-y-2">
                    {benchmarks.segments.map((seg, i) => (
                      <div key={i} className="rounded-md border px-3 py-2 space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-medium">{seg.name}</span>
                          <span className="text-[10px] text-muted-foreground">{seg.source}</span>
                        </div>
                        <div className="flex gap-4 text-xs">
                          <span className="text-muted-foreground">
                            Avg: <span className="font-medium text-foreground">{seg.average}</span>
                          </span>
                          <span className="text-muted-foreground">
                            Good: <span className="font-medium text-blue-600 dark:text-blue-400">{seg.good}</span>
                          </span>
                          <span className="text-muted-foreground">
                            Excellent: <span className="font-medium text-green-600 dark:text-green-400">{seg.excellent}</span>
                          </span>
                        </div>
                      </div>
                    ))}
                    {benchmarks.generated_at && (
                      <p className="text-[10px] text-muted-foreground">
                        Generated: {new Date(benchmarks.generated_at).toLocaleDateString('ro-RO')}
                      </p>
                    )}
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    No benchmarks yet. Click "Generate with AI" to get industry-standard benchmark data for this KPI.
                  </p>
                )}
              </div>
            </>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            disabled={!form.name || !form.slug || !!formulaError || isPending}
            onClick={() =>
              onSave({
                name: form.name,
                slug: form.slug,
                unit: form.unit as any,
                direction: form.direction as any,
                category: form.category,
                formula: form.formula.trim() || null,
                description: form.description.trim() || null,
                is_active: form.is_active,
              } as any)
            }
          >
            <Save className="mr-1.5 h-4 w-4" />
            {isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
