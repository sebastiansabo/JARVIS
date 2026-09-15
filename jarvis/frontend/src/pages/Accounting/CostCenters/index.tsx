import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, Plus, Pencil, Trash2, Wand2, Landmark } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import { PageHeader } from '@/components/shared/PageHeader'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { ApiError } from '@/api/client'
import { costCentersApi } from '@/api/costCenters'
import type { CostCenter } from '@/types/costCenters'

/** Sentinel select value for "no structure node mapped" — Radix Select rejects "". */
const UNMAPPED = '__none__'

/** Backend routes (accounting/cost_centers/routes.py) always surface errors as
 *  { success: false, error: "<mesaj RO>" } via safe_error_response — pull that
 *  string out of the ApiError thrown by api/client.ts (same pattern as
 *  pages/CarPark/Dispo/dispoApiError.ts's apiErrorMessage). */
function errMsg(e: unknown, fallback: string): string {
  if (e instanceof ApiError) {
    const data = e.data as { error?: unknown } | null
    if (data && typeof data.error === 'string' && data.error) return data.error
  }
  if (e instanceof Error && e.message) return e.message
  return fallback
}

/* ──── Main component ──── */

export default function CostCenters() {
  const qc = useQueryClient()
  const [companyId, setCompanyId] = useState<number | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<CostCenter | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<CostCenter | null>(null)

  const { data: companies = [], isLoading: companiesLoading } = useQuery({
    queryKey: ['cost-centers-companies'],
    queryFn: async () => (await costCentersApi.companies()).data,
  })

  // Default to the first company once the list arrives.
  useEffect(() => {
    if (companyId == null && companies.length > 0) setCompanyId(companies[0].company_id)
  }, [companies, companyId])

  const { data: rows = [], isLoading: rowsLoading } = useQuery({
    queryKey: ['cost-centers', companyId],
    queryFn: async () => (await costCentersApi.list(companyId as number)).data,
    enabled: companyId != null,
  })

  const { data: structureNodes = [] } = useQuery({
    queryKey: ['cc-structure-nodes', companyId],
    queryFn: async () => (await costCentersApi.structureNodes(companyId as number)).data,
    enabled: companyId != null,
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['cost-centers', companyId] })

  const createMut = useMutation({
    mutationFn: (payload: { code: string; name: string }) =>
      costCentersApi.create({ company_id: companyId as number, code: payload.code, name: payload.name }),
    onSuccess: () => { invalidate(); setCreateOpen(false); toast.success('Centru de cost creat') },
    onError: (e) => toast.error(errMsg(e, 'Crearea centrului de cost a eșuat')),
  })

  const updateMut = useMutation({
    mutationFn: (payload: { id: number; code: string; name: string }) =>
      costCentersApi.update(payload.id, { code: payload.code, name: payload.name }),
    onSuccess: () => { invalidate(); setEditing(null); toast.success('Centru de cost salvat') },
    onError: (e) => toast.error(errMsg(e, 'Salvarea a eșuat')),
  })

  const toggleActiveMut = useMutation({
    mutationFn: (payload: { id: number; active: boolean }) =>
      costCentersApi.update(payload.id, { active: payload.active }),
    onSuccess: () => invalidate(),
    onError: (e) => toast.error(errMsg(e, 'Actualizarea stării a eșuat')),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => costCentersApi.remove(id),
    onSuccess: () => { invalidate(); setDeleteTarget(null); toast.success('Centru de cost șters') },
    onError: (e) => toast.error(errMsg(e, 'Ștergerea a eșuat')),
  })

  const mapMut = useMutation({
    mutationFn: (payload: { id: number; nodeId: number | null }) =>
      costCentersApi.setMap(payload.id, payload.nodeId),
    onSuccess: () => invalidate(),
    onError: (e) => toast.error(errMsg(e, 'Maparea a eșuat')),
  })

  const seedMut = useMutation({
    mutationFn: () => costCentersApi.seedMapExact(companyId as number),
    onSuccess: (res) => {
      invalidate()
      toast.success(`${res.data.inserted} centre mapate`)
    },
    onError: (e) => toast.error(errMsg(e, 'Auto-maparea a eșuat')),
  })

  const loading = companiesLoading || rowsLoading

  return (
    <div className="space-y-4">
      <PageHeader
        title="Centre de cost"
        breadcrumbs={[
          { label: 'Accounting', href: '/app/accounting' },
          { label: 'Centre de cost' },
        ]}
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              disabled={companyId == null || seedMut.isPending}
              onClick={() => seedMut.mutate()}
            >
              {seedMut.isPending
                ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                : <Wand2 className="mr-1.5 h-4 w-4" />}
              Auto-mapează (nume identice)
            </Button>
            <Button size="sm" disabled={companyId == null} onClick={() => setCreateOpen(true)}>
              <Plus className="mr-1.5 h-4 w-4" />
              Adaugă centru de cost
            </Button>
          </>
        }
      />

      {/* Company selector */}
      <div className="flex flex-wrap items-center gap-3">
        <Select
          value={companyId != null ? String(companyId) : undefined}
          onValueChange={(v) => setCompanyId(Number(v))}
        >
          <SelectTrigger className="w-64">
            <SelectValue placeholder="Selectează compania" />
          </SelectTrigger>
          <SelectContent>
            {companies.map((c) => (
              <SelectItem key={c.company_id} value={String(c.company_id)}>
                {c.company} ({c.count})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Se încarcă…
        </div>
      ) : rows.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-40 gap-2 text-muted-foreground text-sm">
          <Landmark className="h-8 w-8 opacity-40" />
          Nu există centre de cost pentru această companie.
        </div>
      ) : (
        <div className="rounded-md border overflow-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Cod</TableHead>
                <TableHead>Denumire</TableHead>
                <TableHead>Nod structură (mapare)</TableHead>
                <TableHead>Activ</TableHead>
                <TableHead className="w-20 text-right">Acțiuni</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((cc) => (
                <TableRow key={cc.id} className="hover:bg-muted/20">
                  <TableCell className="font-mono text-xs whitespace-nowrap">{cc.code}</TableCell>
                  <TableCell className="font-medium">{cc.name}</TableCell>
                  <TableCell>
                    <Select
                      value={cc.structure_node_id != null ? String(cc.structure_node_id) : UNMAPPED}
                      onValueChange={(v) => mapMut.mutate({ id: cc.id, nodeId: v === UNMAPPED ? null : Number(v) })}
                    >
                      <SelectTrigger className="w-56">
                        <SelectValue placeholder="— Nemapat —" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={UNMAPPED}>— Nemapat —</SelectItem>
                        {structureNodes.map((n) => (
                          <SelectItem key={n.id} value={String(n.id)}>{n.name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell>
                    <Switch
                      checked={cc.active}
                      disabled={toggleActiveMut.isPending}
                      onCheckedChange={(checked) => toggleActiveMut.mutate({ id: cc.id, active: checked })}
                    />
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      title="Editează"
                      onClick={() => setEditing(cc)}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-destructive"
                      title="Șterge"
                      onClick={() => setDeleteTarget(cc)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Create */}
      <CreateCostCenterDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreate={(payload) => createMut.mutate(payload)}
        saving={createMut.isPending}
      />

      {/* Edit */}
      <EditCostCenterDialog
        costCenter={editing}
        onClose={() => setEditing(null)}
        onSave={(payload) => updateMut.mutate(payload)}
        saving={updateMut.isPending}
      />

      {/* Delete confirm */}
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(o) => { if (!o) setDeleteTarget(null) }}
        title="Șterge centrul de cost"
        description={deleteTarget
          ? `Centrul de cost „${deleteTarget.code} — ${deleteTarget.name}" va fi șters definitiv.`
          : ''}
        confirmLabel="Șterge"
        cancelLabel="Anulează"
        destructive
        onConfirm={() => deleteTarget && deleteMut.mutate(deleteTarget.id)}
      />
    </div>
  )
}

/* ──── Create dialog ──── */

function CreateCostCenterDialog({
  open, onClose, onCreate, saving,
}: {
  open: boolean
  onClose: () => void
  onCreate: (payload: { code: string; name: string }) => void
  saving: boolean
}) {
  const [code, setCode] = useState('')
  const [name, setName] = useState('')

  useEffect(() => { if (open) { setCode(''); setName('') } }, [open])

  const submit = () => {
    if (code.trim() && name.trim()) onCreate({ code: code.trim(), name: name.trim() })
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle>Adaugă centru de cost</DialogTitle>
          <DialogDescription>
            Centrul de cost este specific companiei selectate.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-1">
          <div className="space-y-1.5">
            <Label htmlFor="cc-code" className="text-xs">Cod</Label>
            <Input
              id="cc-code"
              autoFocus
              value={code}
              onChange={(e) => setCode(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
              placeholder="ex. CC-001"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="cc-name" className="text-xs">Denumire</Label>
            <Input
              id="cc-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
              placeholder="ex. Vânzări Auto"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={saving}>Anulează</Button>
          <Button disabled={!code.trim() || !name.trim() || saving} onClick={submit}>
            {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
            Salvează
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/* ──── Edit dialog (Cod + Denumire) ──── */

function EditCostCenterDialog({
  costCenter, onClose, onSave, saving,
}: {
  costCenter: CostCenter | null
  onClose: () => void
  onSave: (payload: { id: number; code: string; name: string }) => void
  saving: boolean
}) {
  const [code, setCode] = useState('')
  const [name, setName] = useState('')

  useEffect(() => {
    if (!costCenter) return
    setCode(costCenter.code)
    setName(costCenter.name)
  }, [costCenter])

  if (!costCenter) return null

  return (
    <Dialog open={!!costCenter} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle>Editează centrul de cost</DialogTitle>
          <DialogDescription>Modifică codul și denumirea.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-1">
          <div className="space-y-1.5">
            <Label htmlFor="edit-cc-code" className="text-xs">Cod</Label>
            <Input id="edit-cc-code" value={code} onChange={(e) => setCode(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="edit-cc-name" className="text-xs">Denumire</Label>
            <Input id="edit-cc-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={saving}>Anulează</Button>
          <Button
            disabled={saving || !code.trim() || !name.trim()}
            onClick={() => onSave({ id: costCenter.id, code: code.trim(), name: name.trim() })}
          >
            {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
            Salvează
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
