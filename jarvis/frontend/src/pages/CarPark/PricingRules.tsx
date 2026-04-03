import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus, Play, Trash2, Pencil, AlertTriangle, Clock, Zap,
  Search, X, Car, Link2, Users,
} from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { EmptyState } from '@/components/shared/EmptyState'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { carparkApi } from '@/api/carpark'
import { marketingApi } from '@/api/marketing'
import { usersApi } from '@/api/users'
import { useAuthStore } from '@/stores/authStore'
import { toast } from 'sonner'
import {
  ACTION_TYPE_LABELS,
  CATEGORY_LABELS,
  type PricingRule,
  type PricingActionType,
  type AgingVehicle,
  type RuleExecutionResult,
  type VehicleCatalogItem,
  type TargetMode,
} from '@/types/carpark'

function formatDate(d: string | null): string {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('ro-RO')
}

function formatCurrency(val: number): string {
  return new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(val)
}

const TARGET_MODE_LABELS: Record<TargetMode, string> = {
  criteria: 'Criterii',
  manual: 'Manual',
  both: 'Ambele',
}

const EMPTY_RULE: Partial<PricingRule> = {
  name: '',
  description: '',
  is_active: true,
  priority: 0,
  action_type: 'reduce_percent',
  action_value: 0,
  frequency: 'daily',
  project_id: null,
  target_mode: 'criteria',
}

export default function PricingRulesPage() {
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const canEdit = user?.can_edit_carpark ?? false

  const [ruleDialogOpen, setRuleDialogOpen] = useState(false)
  const [editingRule, setEditingRule] = useState<Partial<PricingRule> | null>(null)
  const [execResult, setExecResult] = useState<RuleExecutionResult | null>(null)
  const [execDialogOpen, setExecDialogOpen] = useState(false)
  const [vehicleDialogRuleId, setVehicleDialogRuleId] = useState<number | null>(null)
  const [vehicleDialogRuleName, setVehicleDialogRuleName] = useState('')
  const [approverId, setApproverId] = useState<number | null>(null)

  const { data: rulesData, isLoading } = useQuery({
    queryKey: ['carpark', 'pricing-rules'],
    queryFn: () => carparkApi.getPricingRules(),
  })

  const { data: agingData } = useQuery({
    queryKey: ['carpark', 'aging-vehicles'],
    queryFn: () => carparkApi.getAgingVehicles(),
  })

  const { data: projectsData } = useQuery({
    queryKey: ['marketing', 'projects-list'],
    queryFn: () => marketingApi.listProjects({ status: 'approved' }),
  })

  const { data: usersData } = useQuery({
    queryKey: ['users-list'],
    queryFn: () => usersApi.getUsers(),
  })

  const rules = rulesData?.rules ?? []
  const agingVehicles = agingData?.vehicles ?? []
  const projects = projectsData?.projects ?? []
  const allUsers = usersData ?? []

  const createMutation = useMutation({
    mutationFn: (data: Partial<PricingRule>) => carparkApi.createPricingRule(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'pricing-rules'] })
      toast.success('Regulă creată')
      setRuleDialogOpen(false)
      setEditingRule(null)
    },
    onError: () => toast.error('Eroare la crearea regulii'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<PricingRule> }) =>
      carparkApi.updatePricingRule(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'pricing-rules'] })
      toast.success('Regulă actualizată')
      setRuleDialogOpen(false)
      setEditingRule(null)
    },
    onError: () => toast.error('Eroare la actualizare'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => carparkApi.deletePricingRule(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'pricing-rules'] })
      toast.success('Regulă ștearsă')
    },
    onError: () => toast.error('Eroare la ștergere'),
  })

  const executeMutation = useMutation({
    mutationFn: ({ id, dryRun, approver }: { id: number; dryRun: boolean; approver?: number }) =>
      carparkApi.executePricingRule(id, dryRun, approver),
    onSuccess: (result) => {
      setExecResult(result)
      setExecDialogOpen(true)
      if (!result.dry_run) {
        queryClient.invalidateQueries({ queryKey: ['carpark'] })
        toast.success(`Regulă executată: ${result.applied_count} vehicule actualizate`)
      }
    },
    onError: () => toast.error('Eroare la executarea regulii'),
  })

  function openNewRule() {
    setEditingRule({ ...EMPTY_RULE })
    setRuleDialogOpen(true)
  }

  function openEditRule(rule: PricingRule) {
    setEditingRule({ ...rule })
    setRuleDialogOpen(true)
  }

  function saveRule() {
    if (!editingRule) return
    if (editingRule.id) {
      updateMutation.mutate({ id: editingRule.id, data: editingRule })
    } else {
      createMutation.mutate(editingRule)
    }
  }

  const isSaving = createMutation.isPending || updateMutation.isPending

  return (
    <div className="space-y-6">
      <PageHeader
        title="Reguli de Preț"
        description="Motor de prețuri dinamice — reguli automate de ajustare a prețurilor"
        actions={
          canEdit ? (
            <Button onClick={openNewRule}>
              <Plus className="mr-2 h-4 w-4" /> Regulă nouă
            </Button>
          ) : undefined
        }
      />

      <Tabs defaultValue="rules">
        <TabsList>
          <TabsTrigger value="rules">Reguli ({rules.length})</TabsTrigger>
          <TabsTrigger value="aging">
            Vehicule vechi ({agingVehicles.length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="rules" className="mt-4">
          {isLoading ? (
            <div className="text-sm text-muted-foreground">Se incarcă...</div>
          ) : rules.length === 0 ? (
            <EmptyState
              icon={<Zap className="h-10 w-10" />}
              title="Nicio regulă de preț"
              description="Creează prima regulă de ajustare automată a prețurilor"
            />
          ) : (
            <div className="space-y-3">
              {rules.map((rule) => (
                <RuleCard
                  key={rule.id}
                  rule={rule}
                  canEdit={canEdit}
                  onEdit={() => openEditRule(rule)}
                  onDelete={() => deleteMutation.mutate(rule.id)}
                  onSimulate={() => executeMutation.mutate({ id: rule.id, dryRun: true })}
                  onExecute={() => executeMutation.mutate({ id: rule.id, dryRun: false })}
                  onManageVehicles={() => {
                    setVehicleDialogRuleId(rule.id)
                    setVehicleDialogRuleName(rule.name)
                  }}
                  isExecuting={executeMutation.isPending}
                />
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="aging" className="mt-4">
          {agingVehicles.length === 0 ? (
            <EmptyState
              icon={<Clock className="h-10 w-10" />}
              title="Niciun vehicul vechi"
              description="Toate vehiculele sunt sub pragul de alertă"
            />
          ) : (
            <div className="space-y-2">
              {agingVehicles.map((v) => (
                <AgingCard key={v.vehicle_id} vehicle={v} />
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Rule Create/Edit Dialog */}
      <Dialog open={ruleDialogOpen} onOpenChange={setRuleDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editingRule?.id ? 'Editare regulă' : 'Regulă nouă'}</DialogTitle>
            <DialogDescription>Definește condițiile și acțiunea regulii de preț</DialogDescription>
          </DialogHeader>

          {editingRule && (
            <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-2">
              <div>
                <Label>Nume *</Label>
                <Input
                  value={editingRule.name ?? ''}
                  onChange={(e) => setEditingRule({ ...editingRule, name: e.target.value })}
                  placeholder="ex: Reducere 30 zile"
                />
              </div>

              <div>
                <Label>Descriere</Label>
                <Textarea
                  value={editingRule.description ?? ''}
                  onChange={(e) => setEditingRule({ ...editingRule, description: e.target.value })}
                  rows={2}
                />
              </div>

              {/* Project selector */}
              <div>
                <Label>Proiect marketing</Label>
                <Select
                  value={editingRule.project_id ? String(editingRule.project_id) : '_none'}
                  onValueChange={(v) => setEditingRule({
                    ...editingRule,
                    project_id: v === '_none' ? null : Number(v),
                  })}
                >
                  <SelectTrigger><SelectValue placeholder="Fără proiect" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="_none">Fără proiect</SelectItem>
                    {projects.map((p) => (
                      <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Target mode */}
              <div>
                <Label>Mod țintire vehicule</Label>
                <Select
                  value={editingRule.target_mode ?? 'criteria'}
                  onValueChange={(v) => setEditingRule({ ...editingRule, target_mode: v as TargetMode })}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(TARGET_MODE_LABELS).map(([k, label]) => (
                      <SelectItem key={k} value={k}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground mt-1">
                  {editingRule.target_mode === 'criteria' && 'Vehiculele sunt selectate automat pe baza criteriilor'}
                  {editingRule.target_mode === 'manual' && 'Doar vehiculele adaugate manual sunt vizate'}
                  {editingRule.target_mode === 'both' && 'Vehiculele din criterii + cele adaugate manual'}
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Tip acțiune *</Label>
                  <Select
                    value={editingRule.action_type ?? 'reduce_percent'}
                    onValueChange={(v) => setEditingRule({ ...editingRule, action_type: v as PricingActionType })}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {Object.entries(ACTION_TYPE_LABELS).map(([k, label]) => (
                        <SelectItem key={k} value={k}>{label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Valoare acțiune</Label>
                  <Input
                    type="number"
                    step="0.01"
                    value={editingRule.action_value ?? ''}
                    onChange={(e) => setEditingRule({ ...editingRule, action_value: e.target.value ? Number(e.target.value) : null })}
                    placeholder={editingRule.action_type === 'reduce_percent' ? '% reducere' : 'sumă'}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Zile min. listat</Label>
                  <Input
                    type="number"
                    value={editingRule.condition_min_days ?? ''}
                    onChange={(e) => setEditingRule({ ...editingRule, condition_min_days: e.target.value ? Number(e.target.value) : null })}
                  />
                </div>
                <div>
                  <Label>Zile max. listat</Label>
                  <Input
                    type="number"
                    value={editingRule.condition_max_days ?? ''}
                    onChange={(e) => setEditingRule({ ...editingRule, condition_max_days: e.target.value ? Number(e.target.value) : null })}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Preț min. condiție</Label>
                  <Input
                    type="number"
                    step="0.01"
                    value={editingRule.condition_min_price ?? ''}
                    onChange={(e) => setEditingRule({ ...editingRule, condition_min_price: e.target.value ? Number(e.target.value) : null })}
                  />
                </div>
                <div>
                  <Label>Preț max. condiție</Label>
                  <Input
                    type="number"
                    step="0.01"
                    value={editingRule.condition_max_price ?? ''}
                    onChange={(e) => setEditingRule({ ...editingRule, condition_max_price: e.target.value ? Number(e.target.value) : null })}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Prioritate</Label>
                  <Input
                    type="number"
                    value={editingRule.priority ?? 0}
                    onChange={(e) => setEditingRule({ ...editingRule, priority: Number(e.target.value) })}
                  />
                </div>
                <div className="flex items-center gap-2 pt-6">
                  <Switch
                    checked={editingRule.is_active ?? true}
                    onCheckedChange={(v) => setEditingRule({ ...editingRule, is_active: v })}
                  />
                  <Label>Activă</Label>
                </div>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setRuleDialogOpen(false)}>Anulează</Button>
            <Button onClick={saveRule} disabled={isSaving || !editingRule?.name || !editingRule?.action_type}>
              {isSaving ? 'Se salvează...' : 'Salvează'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Execution Result Dialog */}
      <Dialog open={execDialogOpen} onOpenChange={setExecDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {execResult?.dry_run ? 'Simulare' : 'Executare'}: {execResult?.rule_name}
            </DialogTitle>
            <DialogDescription>
              {execResult?.dry_run ? 'Previzualizare fără aplicare' : 'Rezultatul execuției'}
            </DialogDescription>
          </DialogHeader>

          {execResult && (
            <div className="space-y-4 max-h-[60vh] overflow-y-auto">
              <div className="grid grid-cols-4 gap-3">
                <Card className="p-3 text-center">
                  <div className="text-2xl font-bold">{execResult.total_matched}</div>
                  <div className="text-xs text-muted-foreground">Vehicule potrivite</div>
                </Card>
                <Card className="p-3 text-center">
                  <div className="text-2xl font-bold text-green-600">{execResult.applied_count}</div>
                  <div className="text-xs text-muted-foreground">Aplicate</div>
                </Card>
                <Card className="p-3 text-center">
                  <div className="text-2xl font-bold text-amber-600">{execResult.pending_approval_count}</div>
                  <div className="text-xs text-muted-foreground">Necesită aprobare</div>
                </Card>
                <Card className="p-3 text-center">
                  <div className="text-2xl font-bold text-red-600">{execResult.alert_count}</div>
                  <div className="text-xs text-muted-foreground">Alerte</div>
                </Card>
              </div>

              {execResult.applied.length > 0 && (
                <div>
                  <h4 className="font-medium text-sm mb-2">Modificări preț</h4>
                  <div className="rounded border divide-y text-sm">
                    {execResult.applied.map((item) => (
                      <div key={item.vehicle_id} className="flex items-center justify-between px-3 py-2">
                        <div>
                          <span className="font-medium">{item.vin}</span>
                          <span className="text-muted-foreground ml-2">{item.brand} {item.model}</span>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="text-muted-foreground line-through">{formatCurrency(item.old_price)}</span>
                          <span className="font-medium">{formatCurrency(item.new_price)}</span>
                          <Badge variant={item.floor_hit ? 'destructive' : 'secondary'} className="text-[10px]">
                            -{formatCurrency(item.reduction)}
                          </Badge>
                          {item.needs_approval && (
                            <Badge variant="outline" className="text-[10px] text-amber-600">Aprobare</Badge>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Approval submission UI */}
              {!execResult.dry_run && execResult.pending_approval_count > 0 && !execResult.approval_request_id && (
                <div className="border rounded-md p-4 bg-amber-50 dark:bg-amber-900/10 space-y-3">
                  <div className="flex items-center gap-2 text-amber-700 dark:text-amber-400">
                    <Users className="h-4 w-4" />
                    <span className="text-sm font-medium">
                      {execResult.pending_approval_count} modificări necesită aprobare
                    </span>
                  </div>
                  <div>
                    <Label>Selectează aprobator</Label>
                    <Select
                      value={approverId ? String(approverId) : ''}
                      onValueChange={(v) => setApproverId(v ? Number(v) : null)}
                    >
                      <SelectTrigger><SelectValue placeholder="Alege un aprobator..." /></SelectTrigger>
                      <SelectContent>
                        {allUsers.map((u) => (
                          <SelectItem key={u.id} value={String(u.id)}>{u.name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <Button
                    size="sm"
                    disabled={!approverId || executeMutation.isPending}
                    onClick={() => {
                      if (approverId && execResult.rule_id) {
                        executeMutation.mutate({
                          id: execResult.rule_id,
                          dryRun: false,
                          approver: approverId,
                        })
                      }
                    }}
                  >
                    Trimite pentru aprobare
                  </Button>
                </div>
              )}

              {execResult.approval_request_id && (
                <div className="border rounded-md p-4 bg-green-50 dark:bg-green-900/10">
                  <div className="text-sm text-green-700 dark:text-green-400 font-medium">
                    Cerere de aprobare trimisă (#{execResult.approval_request_id})
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    Modificările de preț vor fi aplicate automat după aprobare.
                  </p>
                </div>
              )}

              {execResult.alerts.length > 0 && (
                <div>
                  <h4 className="font-medium text-sm mb-2">Alerte</h4>
                  <div className="rounded border divide-y text-sm">
                    {execResult.alerts.map((item) => (
                      <div key={item.vehicle_id} className="flex items-center justify-between px-3 py-2">
                        <div>
                          <span className="font-medium">{item.vin}</span>
                          <span className="text-muted-foreground ml-2">{item.brand} {item.model}</span>
                        </div>
                        <Badge variant="outline">{item.days_listed} zile</Badge>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => { setExecDialogOpen(false); setApproverId(null) }}>Închide</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Vehicle Management Dialog */}
      {vehicleDialogRuleId && (
        <RuleVehicleDialog
          ruleId={vehicleDialogRuleId}
          ruleName={vehicleDialogRuleName}
          onClose={() => setVehicleDialogRuleId(null)}
        />
      )}
    </div>
  )
}

// ── Rule Vehicle Dialog ──────────────────────────────
function RuleVehicleDialog({
  ruleId,
  ruleName,
  onClose,
}: {
  ruleId: number
  ruleName: string
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [searchQuery, setSearchQuery] = useState('')

  const { data: vehiclesData } = useQuery({
    queryKey: ['carpark', 'rule-vehicles', ruleId],
    queryFn: () => carparkApi.getRuleVehicles(ruleId),
  })

  const { data: searchData, isFetching: isSearching } = useQuery({
    queryKey: ['carpark', 'catalog-search', searchQuery],
    queryFn: () => carparkApi.getCatalog({ search: searchQuery }, 1, 20),
    enabled: searchQuery.length >= 2,
  })

  const ruleVehicles = vehiclesData?.vehicles ?? []
  const searchResults = searchData?.items ?? []
  const ruleVehicleIds = new Set(ruleVehicles.map((v) => v.vehicle_id))

  const addMutation = useMutation({
    mutationFn: (vehicleIds: number[]) => carparkApi.addRuleVehicles(ruleId, vehicleIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'rule-vehicles', ruleId] })
      toast.success('Vehicul adăugat')
    },
    onError: () => toast.error('Eroare la adăugare'),
  })

  const removeMutation = useMutation({
    mutationFn: (vehicleId: number) => carparkApi.removeRuleVehicle(ruleId, vehicleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'rule-vehicles', ruleId] })
      toast.success('Vehicul eliminat')
    },
    onError: () => toast.error('Eroare la eliminare'),
  })

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Vehicule în regula: {ruleName}</DialogTitle>
          <DialogDescription>Adaugă sau elimină vehicule din această regulă</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-1">
          {/* Search to add */}
          <div>
            <Label>Adaugă vehicul</Label>
            <div className="flex items-center gap-2 mt-1">
              <Search className="h-4 w-4 text-muted-foreground shrink-0" />
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Caută după VIN, marcă, model..."
              />
            </div>
            {searchQuery.length >= 2 && (
              <div className="mt-2 max-h-40 overflow-y-auto border rounded-md">
                {isSearching ? (
                  <div className="p-3 text-center text-sm text-muted-foreground">Se caută...</div>
                ) : searchResults.length === 0 ? (
                  <div className="p-3 text-center text-sm text-muted-foreground">Niciun rezultat</div>
                ) : (
                  <div className="divide-y">
                    {searchResults.map((v: VehicleCatalogItem) => {
                      const isAdded = ruleVehicleIds.has(v.id)
                      return (
                        <button
                          key={v.id}
                          className="w-full text-left px-3 py-2 hover:bg-accent text-sm disabled:opacity-50 flex items-center justify-between"
                          disabled={isAdded || addMutation.isPending}
                          onClick={() => addMutation.mutate([v.id])}
                        >
                          <div>
                            <span className="font-medium">{v.brand} {v.model}</span>
                            <span className="ml-2 text-muted-foreground text-xs">{v.vin}</span>
                          </div>
                          {isAdded && <span className="text-xs text-muted-foreground">Deja adăugat</span>}
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Current vehicles */}
          <div>
            <Label>Vehicule în regulă ({ruleVehicles.length})</Label>
            {ruleVehicles.length === 0 ? (
              <div className="mt-2 p-4 text-center text-sm text-muted-foreground border rounded-md">
                Niciun vehicul adăugat
              </div>
            ) : (
              <div className="mt-2 space-y-1">
                {ruleVehicles.map((rv) => (
                  <div key={rv.id} className="flex items-center justify-between px-3 py-2 border rounded-md">
                    <div className="flex items-center gap-2 min-w-0">
                      <Car className="h-4 w-4 text-muted-foreground shrink-0" />
                      <span className="text-sm font-medium">{rv.brand} {rv.model}</span>
                      <span className="text-xs text-muted-foreground">{rv.vin}</span>
                      {rv.current_price && (
                        <span className="text-xs text-muted-foreground">{formatCurrency(rv.current_price)} EUR</span>
                      )}
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 px-2 text-red-500 shrink-0"
                      onClick={() => removeMutation.mutate(rv.vehicle_id)}
                      disabled={removeMutation.isPending}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Închide</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Rule Card ──────────────────────────────────────
function RuleCard({
  rule,
  canEdit,
  onEdit,
  onDelete,
  onSimulate,
  onExecute,
  onManageVehicles,
  isExecuting,
}: {
  rule: PricingRule
  canEdit: boolean
  onEdit: () => void
  onDelete: () => void
  onSimulate: () => void
  onExecute: () => void
  onManageVehicles: () => void
  isExecuting: boolean
}) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-medium">{rule.name}</h3>
            <Badge variant={rule.is_active ? 'default' : 'secondary'}>
              {rule.is_active ? 'Activă' : 'Inactivă'}
            </Badge>
            <Badge variant="outline">{ACTION_TYPE_LABELS[rule.action_type]}</Badge>
            {rule.action_value != null && rule.action_type !== 'alert_only' && (
              <Badge variant="outline">
                {rule.action_type === 'reduce_percent' ? `${rule.action_value}%` : formatCurrency(rule.action_value)}
              </Badge>
            )}
            {rule.project_name && (
              <Badge variant="outline" className="text-purple-600 border-purple-300">
                <Link2 className="h-3 w-3 mr-1" />
                {rule.project_name}
              </Badge>
            )}
            {rule.target_mode !== 'criteria' && (
              <Badge variant="outline" className="text-blue-600 border-blue-300">
                {TARGET_MODE_LABELS[rule.target_mode]}
              </Badge>
            )}
          </div>
          {rule.description && (
            <p className="text-sm text-muted-foreground mt-1">{rule.description}</p>
          )}
          <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
            {rule.condition_min_days != null && <span>Min {rule.condition_min_days} zile</span>}
            {rule.condition_max_days != null && <span>Max {rule.condition_max_days} zile</span>}
            {rule.condition_min_price != null && <span>Preț min {formatCurrency(rule.condition_min_price)}</span>}
            {rule.condition_max_price != null && <span>Preț max {formatCurrency(rule.condition_max_price)}</span>}
            <span>Prioritate: {rule.priority}</span>
            {rule.last_executed && <span>Ultima execuție: {formatDate(rule.last_executed)}</span>}
          </div>
        </div>

        {canEdit && (
          <div className="flex items-center gap-1 shrink-0 ml-4">
            {(rule.target_mode === 'manual' || rule.target_mode === 'both') && (
              <Button variant="ghost" size="sm" onClick={onManageVehicles} title="Gestionează vehicule">
                <Car className="h-4 w-4" />
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={onSimulate} disabled={isExecuting} title="Simulare">
              <Play className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="sm" onClick={onExecute} disabled={isExecuting || !rule.is_active} title="Execută">
              <Zap className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="sm" onClick={onEdit}>
              <Pencil className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="sm" onClick={onDelete}>
              <Trash2 className="h-4 w-4 text-destructive" />
            </Button>
          </div>
        )}
      </div>
    </Card>
  )
}

// ── Aging Vehicle Card ──────────────────────────────
function AgingCard({ vehicle: v }: { vehicle: AgingVehicle }) {
  const severityColors = {
    critical: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
    warning: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
    info: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  }

  return (
    <Card className="flex items-center justify-between p-3">
      <div className="flex items-center gap-3">
        <div className={`rounded-full p-1.5 ${severityColors[v.severity]}`}>
          <AlertTriangle className="h-4 w-4" />
        </div>
        <div>
          <div className="text-sm font-medium">{v.brand} {v.model}</div>
          <div className="text-xs text-muted-foreground">{v.vin}</div>
        </div>
      </div>
      <div className="flex items-center gap-4 text-sm">
        <div className="text-right">
          <div className="font-medium">{v.days_listed} zile</div>
          <div className="text-xs text-muted-foreground">{CATEGORY_LABELS[v.category as keyof typeof CATEGORY_LABELS] ?? v.category}</div>
        </div>
        <div className="text-right">
          <div className="font-medium">{formatCurrency(v.current_price)}</div>
          {v.list_price !== v.current_price && (
            <div className="text-xs text-muted-foreground line-through">{formatCurrency(v.list_price)}</div>
          )}
        </div>
        <Badge variant="outline" className={severityColors[v.severity]}>
          {v.severity === 'critical' ? 'Critic' : v.severity === 'warning' ? 'Atenție' : 'Info'}
        </Badge>
      </div>
    </Card>
  )
}
