import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Pencil, Tag, Calendar, Car, X, Search } from 'lucide-react'
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
import { carparkApi } from '@/api/carpark'
import { useAuthStore } from '@/stores/authStore'
import { toast } from 'sonner'
import {
  PROMO_TYPE_LABELS,
  TARGET_TYPE_LABELS,
  type Promotion,
  type PromotionTargetType,
  type PromotionType,
  type DiscountType,
  type VehicleCatalogItem,
} from '@/types/carpark'

function formatDate(d: string | null): string {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('ro-RO')
}

function formatCurrency(val: number): string {
  return new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(val)
}

const EMPTY_PROMO: Partial<Promotion> = {
  name: '',
  description: '',
  target_type: 'all',
  promo_type: 'discount',
  discount_type: 'percent',
  discount_value: 0,
  start_date: new Date().toISOString().split('T')[0],
  end_date: '',
  is_active: true,
  push_to_platforms: false,
}

export default function PromotionsPage() {
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const canEdit = user?.can_edit_carpark ?? false

  const [promoDialogOpen, setPromoDialogOpen] = useState(false)
  const [editingPromo, setEditingPromo] = useState<Partial<Promotion> | null>(null)
  const [vehicleDialogPromoId, setVehicleDialogPromoId] = useState<number | null>(null)

  const { data: promosData, isLoading } = useQuery({
    queryKey: ['carpark', 'promotions'],
    queryFn: () => carparkApi.getPromotions(),
  })

  const promotions = promosData?.promotions ?? []

  const createMutation = useMutation({
    mutationFn: (data: Partial<Promotion>) => carparkApi.createPromotion(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'promotions'] })
      toast.success('Promoție creată')
      setPromoDialogOpen(false)
      setEditingPromo(null)
    },
    onError: () => toast.error('Eroare la crearea promoției'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Promotion> }) =>
      carparkApi.updatePromotion(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'promotions'] })
      toast.success('Promoție actualizată')
      setPromoDialogOpen(false)
      setEditingPromo(null)
    },
    onError: () => toast.error('Eroare la actualizare'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => carparkApi.deletePromotion(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'promotions'] })
      toast.success('Promoție ștearsă')
    },
    onError: () => toast.error('Eroare la ștergere'),
  })

  function openNewPromo() {
    setEditingPromo({ ...EMPTY_PROMO })
    setPromoDialogOpen(true)
  }

  function openEditPromo(promo: Promotion) {
    setEditingPromo({ ...promo })
    setPromoDialogOpen(true)
  }

  function savePromo() {
    if (!editingPromo) return
    if (editingPromo.id) {
      updateMutation.mutate({ id: editingPromo.id, data: editingPromo })
    } else {
      createMutation.mutate(editingPromo)
    }
  }

  const isSaving = createMutation.isPending || updateMutation.isPending

  const activePromos = promotions.filter((p) => p.is_active && new Date(p.end_date) >= new Date())
  const pastPromos = promotions.filter((p) => !p.is_active || new Date(p.end_date) < new Date())

  return (
    <div className="space-y-6">
      <PageHeader
        title="Promoții"
        description="Gestionează promoțiile și ofertele speciale pentru vehicule"
        actions={
          canEdit ? (
            <Button onClick={openNewPromo}>
              <Plus className="mr-2 h-4 w-4" /> Promoție nouă
            </Button>
          ) : undefined
        }
      />

      {isLoading ? (
        <div className="text-sm text-muted-foreground">Se incarcă...</div>
      ) : promotions.length === 0 ? (
        <EmptyState
          icon={<Tag className="h-10 w-10" />}
          title="Nicio promoție"
          description="Creează prima promoție pentru vehiculele din parc"
        />
      ) : (
        <div className="space-y-6">
          {activePromos.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">
                Active ({activePromos.length})
              </h3>
              <div className="space-y-3">
                {activePromos.map((promo) => (
                  <PromoCard
                    key={promo.id}
                    promo={promo}
                    canEdit={canEdit}
                    onEdit={() => openEditPromo(promo)}
                    onDelete={() => deleteMutation.mutate(promo.id)}
                    onManageVehicles={() => setVehicleDialogPromoId(promo.id)}
                  />
                ))}
              </div>
            </div>
          )}

          {pastPromos.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">
                Expirate / Inactive ({pastPromos.length})
              </h3>
              <div className="space-y-3">
                {pastPromos.map((promo) => (
                  <PromoCard
                    key={promo.id}
                    promo={promo}
                    canEdit={canEdit}
                    onEdit={() => openEditPromo(promo)}
                    onDelete={() => deleteMutation.mutate(promo.id)}
                    onManageVehicles={() => setVehicleDialogPromoId(promo.id)}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Promo Create/Edit Dialog */}
      <Dialog open={promoDialogOpen} onOpenChange={setPromoDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editingPromo?.id ? 'Editare promoție' : 'Promoție nouă'}</DialogTitle>
            <DialogDescription>Definește detaliile promoției</DialogDescription>
          </DialogHeader>

          {editingPromo && (
            <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-2">
              <div>
                <Label>Nume *</Label>
                <Input
                  value={editingPromo.name ?? ''}
                  onChange={(e) => setEditingPromo({ ...editingPromo, name: e.target.value })}
                  placeholder="ex: Black Friday 2026"
                />
              </div>

              <div>
                <Label>Descriere</Label>
                <Textarea
                  value={editingPromo.description ?? ''}
                  onChange={(e) => setEditingPromo({ ...editingPromo, description: e.target.value })}
                  rows={2}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Tip target *</Label>
                  <Select
                    value={editingPromo.target_type ?? 'all'}
                    onValueChange={(v) => setEditingPromo({ ...editingPromo, target_type: v as PromotionTargetType })}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {Object.entries(TARGET_TYPE_LABELS).map(([k, label]) => (
                        <SelectItem key={k} value={k}>{label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Tip promoție *</Label>
                  <Select
                    value={editingPromo.promo_type ?? 'discount'}
                    onValueChange={(v) => setEditingPromo({ ...editingPromo, promo_type: v as PromotionType })}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {Object.entries(PROMO_TYPE_LABELS).map(([k, label]) => (
                        <SelectItem key={k} value={k}>{label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {editingPromo.promo_type === 'discount' && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label>Tip discount</Label>
                    <Select
                      value={editingPromo.discount_type ?? 'percent'}
                      onValueChange={(v) => setEditingPromo({ ...editingPromo, discount_type: v as DiscountType })}
                    >
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="percent">Procent (%)</SelectItem>
                        <SelectItem value="fixed">Sumă fixă</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Valoare discount</Label>
                    <Input
                      type="number"
                      step="0.01"
                      value={editingPromo.discount_value ?? ''}
                      onChange={(e) => setEditingPromo({ ...editingPromo, discount_value: e.target.value ? Number(e.target.value) : null })}
                    />
                  </div>
                </div>
              )}

              {editingPromo.promo_type === 'special_financing' && (
                <div>
                  <Label>Rată finanțare specială (%)</Label>
                  <Input
                    type="number"
                    step="0.01"
                    value={editingPromo.special_financing_rate ?? ''}
                    onChange={(e) => setEditingPromo({ ...editingPromo, special_financing_rate: e.target.value ? Number(e.target.value) : null })}
                  />
                </div>
              )}

              {editingPromo.promo_type === 'gift' && (
                <div>
                  <Label>Descriere cadou</Label>
                  <Input
                    value={editingPromo.gift_description ?? ''}
                    onChange={(e) => setEditingPromo({ ...editingPromo, gift_description: e.target.value })}
                    placeholder="ex: Set anvelope iarnă"
                  />
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Data început *</Label>
                  <Input
                    type="date"
                    value={editingPromo.start_date ?? ''}
                    onChange={(e) => setEditingPromo({ ...editingPromo, start_date: e.target.value })}
                  />
                </div>
                <div>
                  <Label>Data sfârșit *</Label>
                  <Input
                    type="date"
                    value={editingPromo.end_date ?? ''}
                    onChange={(e) => setEditingPromo({ ...editingPromo, end_date: e.target.value })}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Buget (opțional)</Label>
                  <Input
                    type="number"
                    step="0.01"
                    value={editingPromo.budget ?? ''}
                    onChange={(e) => setEditingPromo({ ...editingPromo, budget: e.target.value ? Number(e.target.value) : null })}
                  />
                </div>
                <div>
                  <Label>Badge platforme</Label>
                  <Input
                    value={editingPromo.platform_badge ?? ''}
                    onChange={(e) => setEditingPromo({ ...editingPromo, platform_badge: e.target.value })}
                    placeholder="ex: PROMO"
                  />
                </div>
              </div>

              <div className="flex items-center gap-6">
                <div className="flex items-center gap-2">
                  <Switch
                    checked={editingPromo.is_active ?? true}
                    onCheckedChange={(v) => setEditingPromo({ ...editingPromo, is_active: v })}
                  />
                  <Label>Activă</Label>
                </div>
                <div className="flex items-center gap-2">
                  <Switch
                    checked={editingPromo.push_to_platforms ?? false}
                    onCheckedChange={(v) => setEditingPromo({ ...editingPromo, push_to_platforms: v })}
                  />
                  <Label>Publică pe platforme</Label>
                </div>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setPromoDialogOpen(false)}>Anulează</Button>
            <Button
              onClick={savePromo}
              disabled={isSaving || !editingPromo?.name || !editingPromo?.start_date || !editingPromo?.end_date}
            >
              {isSaving ? 'Se salvează...' : 'Salvează'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Vehicle Management Dialog */}
      {vehicleDialogPromoId && (
        <VehicleManagementDialog
          promoId={vehicleDialogPromoId}
          promoName={promotions.find((p) => p.id === vehicleDialogPromoId)?.name ?? ''}
          onClose={() => setVehicleDialogPromoId(null)}
        />
      )}
    </div>
  )
}

// ── Vehicle Management Dialog ─────────────────
function VehicleManagementDialog({
  promoId,
  promoName,
  onClose,
}: {
  promoId: number
  promoName: string
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [searchQuery, setSearchQuery] = useState('')

  const { data: vehiclesData } = useQuery({
    queryKey: ['carpark', 'promotion-vehicles', promoId],
    queryFn: () => carparkApi.getPromotionVehicles(promoId),
  })

  const { data: searchData, isFetching: isSearching } = useQuery({
    queryKey: ['carpark', 'catalog-search', searchQuery],
    queryFn: () => carparkApi.getCatalog({ search: searchQuery }, 1, 20),
    enabled: searchQuery.length >= 2,
  })

  const promoVehicles = vehiclesData?.vehicles ?? []
  const searchResults = searchData?.items ?? []
  const promoVehicleIds = new Set(promoVehicles.map((v) => v.vehicle_id))

  const addMutation = useMutation({
    mutationFn: (vehicleIds: number[]) => carparkApi.addPromotionVehicles(promoId, vehicleIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'promotion-vehicles', promoId] })
      toast.success('Vehicul adaugat')
    },
    onError: () => toast.error('Eroare la adaugare'),
  })

  const removeMutation = useMutation({
    mutationFn: (vehicleId: number) => carparkApi.removePromotionVehicle(promoId, vehicleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'promotion-vehicles', promoId] })
      toast.success('Vehicul eliminat')
    },
    onError: () => toast.error('Eroare la eliminare'),
  })

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Vehicule in promotia: {promoName}</DialogTitle>
          <DialogDescription>Adauga sau elimina vehicule din aceasta promotie</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-1">
          {/* Search to add */}
          <div>
            <Label>Adauga vehicul</Label>
            <div className="flex items-center gap-2 mt-1">
              <Search className="h-4 w-4 text-muted-foreground shrink-0" />
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Cauta dupa VIN, marca, model..."
              />
            </div>
            {searchQuery.length >= 2 && (
              <div className="mt-2 max-h-40 overflow-y-auto border rounded-md">
                {isSearching ? (
                  <div className="p-3 text-center text-sm text-muted-foreground">Se cauta...</div>
                ) : searchResults.length === 0 ? (
                  <div className="p-3 text-center text-sm text-muted-foreground">Niciun rezultat</div>
                ) : (
                  <div className="divide-y">
                    {searchResults.map((v: VehicleCatalogItem) => {
                      const isAdded = promoVehicleIds.has(v.id)
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
                          {isAdded && <span className="text-xs text-muted-foreground">Deja adaugat</span>}
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
            <Label>Vehicule in promotie ({promoVehicles.length})</Label>
            {promoVehicles.length === 0 ? (
              <div className="mt-2 p-4 text-center text-sm text-muted-foreground border rounded-md">
                Niciun vehicul adaugat
              </div>
            ) : (
              <div className="mt-2 space-y-1">
                {promoVehicles.map((pv) => (
                  <div key={pv.id} className="flex items-center justify-between px-3 py-2 border rounded-md">
                    <div className="flex items-center gap-2 min-w-0">
                      <Car className="h-4 w-4 text-muted-foreground shrink-0" />
                      <span className="text-sm font-medium">{pv.brand} {pv.model}</span>
                      <span className="text-xs text-muted-foreground">{pv.vin}</span>
                      {pv.current_price && (
                        <span className="text-xs text-muted-foreground">{formatCurrency(pv.current_price)} EUR</span>
                      )}
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 px-2 text-red-500 shrink-0"
                      onClick={() => removeMutation.mutate(pv.vehicle_id)}
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
          <Button variant="outline" onClick={onClose}>Inchide</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Promo Card ────────────────────────────────
function PromoCard({
  promo,
  canEdit,
  onEdit,
  onDelete,
  onManageVehicles,
}: {
  promo: Promotion
  canEdit: boolean
  onEdit: () => void
  onDelete: () => void
  onManageVehicles: () => void
}) {
  const isExpired = new Date(promo.end_date) < new Date()
  const isActive = promo.is_active && !isExpired

  return (
    <Card className={`p-4 ${!isActive ? 'opacity-60' : ''}`}>
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-medium">{promo.name}</h3>
            <Badge variant={isActive ? 'default' : 'secondary'}>
              {isActive ? 'Activa' : isExpired ? 'Expirata' : 'Inactiva'}
            </Badge>
            <Badge variant="outline">{PROMO_TYPE_LABELS[promo.promo_type]}</Badge>
            <Badge variant="outline">{TARGET_TYPE_LABELS[promo.target_type]}</Badge>
          </div>
          {promo.description && (
            <p className="text-sm text-muted-foreground mt-1">{promo.description}</p>
          )}
          <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground flex-wrap">
            <span className="flex items-center gap-1">
              <Calendar className="h-3 w-3" />
              {formatDate(promo.start_date)} — {formatDate(promo.end_date)}
            </span>
            {promo.discount_value != null && promo.promo_type === 'discount' && (
              <span>
                Discount: {promo.discount_type === 'percent' ? `${promo.discount_value}%` : formatCurrency(promo.discount_value)}
              </span>
            )}
            {promo.budget != null && (
              <span>Buget: {formatCurrency(promo.budget)} (cheltuit: {formatCurrency(promo.spent ?? 0)})</span>
            )}
            {(promo.vehicles_sold ?? 0) > 0 && (
              <span>Vandute: {promo.vehicles_sold}</span>
            )}
            {promo.push_to_platforms && promo.platform_badge && (
              <Badge variant="outline" className="text-[10px]">{promo.platform_badge}</Badge>
            )}
          </div>
        </div>

        {canEdit && (
          <div className="flex items-center gap-1 shrink-0 ml-4">
            <Button variant="ghost" size="sm" onClick={onManageVehicles} title="Gestioneaza vehicule">
              <Car className="h-4 w-4" />
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
