import { useState, useMemo, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, Plus, Pencil, Trash2, Building2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { MultiSelectPills } from '@/components/shared/MultiSelectPills'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

/* ──── Types (mirror the /api/divisions contract) ──── */

interface DivisionResponsable { id: number; name: string }
interface DivisionDepartment { node_id: number; name: string; company_id: number; company: string }
interface Division {
  id: number
  name: string
  responsables: DivisionResponsable[]
  departments: DivisionDepartment[]
}
interface AvailableDepartment {
  node_id: number
  name: string
  level: number
  node_type: string
  company_id: number
  company: string
  taken_by_division_id: number | null
}
interface EmployeeOption { id: number; name: string }

/* ──── Fetch helpers (credentials:'include', unwrap {success,data}) ──── */

/** Error carrying the backend status + message so callers can react to 409 etc. */
class DivisionApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'DivisionApiError'
  }
}

async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    credentials: 'include',
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  })
  let body: unknown = null
  try { body = await res.json() } catch { /* empty body */ }
  const envelope = (body ?? {}) as { success?: boolean; data?: unknown; error?: string }
  if (!res.ok || envelope.success === false) {
    throw new DivisionApiError(res.status, envelope.error || `Eroare server (${res.status})`)
  }
  return (envelope.data as T)
}

function errMsg(e: unknown, fallback: string): string {
  if (e instanceof Error && e.message) return e.message
  return fallback
}

/* ──── Main component ──── */

export default function DivisionsTab({ search }: { search: string }) {
  const qc = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<Division | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Division | null>(null)

  const { data: divisions = [], isLoading } = useQuery({
    queryKey: ['divisions'],
    queryFn: () => apiFetch<Division[]>('/api/divisions'),
  })

  const { data: availableDepartments = [] } = useQuery({
    queryKey: ['divisions', 'available-departments'],
    queryFn: () => apiFetch<AvailableDepartment[]>('/api/divisions/available-departments'),
  })

  // Active JARVIS users for the responsable picker. Uses the dedicated
  // /api/divisions/assignable-users endpoint so each row's id is a real
  // users.id (the bare /api/employees is served by several blueprints with
  // different id semantics).
  const { data: employees = [] } = useQuery({
    queryKey: ['divisions', 'assignable-users'],
    queryFn: async (): Promise<EmployeeOption[]> => {
      const res = await fetch('/api/divisions/assignable-users', { credentials: 'include' })
      const body: unknown = await res.json().catch(() => ({}))
      const raw = (body as { data?: unknown }).data
      const list = Array.isArray(raw) ? raw : []
      return list
        .map((e) => e as { id?: number; name?: string })
        .filter((e) => typeof e.id === 'number')
        .map((e) => ({ id: e.id as number, name: e.name ?? `#${e.id}` }))
    },
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['divisions'] })

  const createMut = useMutation({
    mutationFn: (name: string) =>
      apiFetch<{ id: number }>('/api/divisions', { method: 'POST', body: JSON.stringify({ name }) }),
    onSuccess: () => { invalidate(); setCreateOpen(false); toast.success('Divizie creată') },
    onError: (e) => toast.error(errMsg(e, 'Crearea diviziei a eșuat')),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => apiFetch(`/api/divisions/${id}`, { method: 'DELETE' }),
    onSuccess: () => { invalidate(); setDeleteTarget(null); toast.success('Divizie ștearsă') },
    onError: (e) => toast.error(errMsg(e, 'Ștergerea a eșuat')),
  })

  const saveMut = useMutation({
    mutationFn: async (payload: {
      id: number
      name: string
      nameChanged: boolean
      userIds: number[]
      nodeIds: number[]
    }) => {
      if (payload.nameChanged) {
        await apiFetch(`/api/divisions/${payload.id}`, {
          method: 'PATCH', body: JSON.stringify({ name: payload.name }),
        })
      }
      await apiFetch(`/api/divisions/${payload.id}/responsables`, {
        method: 'PUT', body: JSON.stringify({ user_ids: payload.userIds }),
      })
      await apiFetch(`/api/divisions/${payload.id}/departments`, {
        method: 'PUT', body: JSON.stringify({ node_ids: payload.nodeIds }),
      })
    },
    onSuccess: () => { invalidate(); setEditing(null); toast.success('Divizie salvată') },
    onError: (e) => toast.error(errMsg(e, 'Salvarea a eșuat')),
  })

  const filtered = useMemo(() => {
    if (!search) return divisions
    const q = search.toLowerCase()
    return divisions.filter((d) => d.name.toLowerCase().includes(q))
  }, [divisions, search])

  return (
    <div className="space-y-4">
      {/* Header bar */}
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">
          {filtered.length} {filtered.length === 1 ? 'divizie' : 'divizii'}
        </span>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="mr-1.5 h-4 w-4" />
          Adaugă divizie
        </Button>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Se încarcă…
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-40 gap-2 text-muted-foreground text-sm">
          <Building2 className="h-8 w-8 opacity-40" />
          {search ? 'Nicio divizie găsită.' : 'Nu există divizii încă.'}
        </div>
      ) : (
        <div className="rounded-md border overflow-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Divizie</TableHead>
                <TableHead>Responsabili</TableHead>
                <TableHead>Departamente</TableHead>
                <TableHead className="w-24 text-right">Acțiuni</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((d) => (
                <TableRow key={d.id} className="hover:bg-muted/20">
                  <TableCell className="font-medium whitespace-nowrap">{d.name}</TableCell>
                  <TableCell>
                    {d.responsables.length === 0 ? (
                      <span className="text-xs text-muted-foreground">—</span>
                    ) : (
                      <div className="flex flex-wrap gap-1">
                        {d.responsables.map((r) => (
                          <Badge key={r.id} variant="secondary" className="text-xs font-normal">
                            {r.name}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground whitespace-nowrap">
                    {d.departments.length} {d.departments.length === 1 ? 'departament' : 'departamente'}
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      title="Editează"
                      onClick={() => setEditing(d)}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-destructive"
                      title="Șterge"
                      onClick={() => setDeleteTarget(d)}
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
      <CreateDivisionDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreate={(name) => createMut.mutate(name)}
        saving={createMut.isPending}
      />

      {/* Edit */}
      <EditDivisionDialog
        division={editing}
        employees={employees}
        availableDepartments={availableDepartments}
        onClose={() => setEditing(null)}
        onSave={(payload) => saveMut.mutate(payload)}
        saving={saveMut.isPending}
      />

      {/* Delete confirm */}
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(o) => { if (!o) setDeleteTarget(null) }}
        title="Șterge divizia"
        description={deleteTarget
          ? `Divizia „${deleteTarget.name}" va fi ștearsă, împreună cu responsabilii și departamentele asociate.`
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

function CreateDivisionDialog({
  open, onClose, onCreate, saving,
}: {
  open: boolean
  onClose: () => void
  onCreate: (name: string) => void
  saving: boolean
}) {
  const [name, setName] = useState('')

  useEffect(() => { if (open) setName('') }, [open])

  const submit = () => { if (name.trim()) onCreate(name.trim()) }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle>Adaugă divizie</DialogTitle>
          <DialogDescription>
            O divizie grupează departamente Sincron din mai multe companii.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5 py-1">
          <Label htmlFor="division-name" className="text-xs">Nume</Label>
          <Input
            id="division-name"
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
            placeholder="ex. Vânzări"
          />
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={saving}>Anulează</Button>
          <Button disabled={!name.trim() || saving} onClick={submit}>
            {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
            Salvează
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/* ──── Edit dialog (rename + responsables + departments) ──── */

function EditDivisionDialog({
  division, employees, availableDepartments, onClose, onSave, saving,
}: {
  division: Division | null
  employees: EmployeeOption[]
  availableDepartments: AvailableDepartment[]
  onClose: () => void
  onSave: (payload: { id: number; name: string; nameChanged: boolean; userIds: number[]; nodeIds: number[] }) => void
  saving: boolean
}) {
  const [name, setName] = useState('')
  const [userIds, setUserIds] = useState<number[]>([])
  const [nodeIds, setNodeIds] = useState<number[]>([])

  // Prefill each time a new division is opened for editing.
  useEffect(() => {
    if (!division) return
    setName(division.name)
    setUserIds(division.responsables.map((r) => r.id))
    setNodeIds(division.departments.map((d) => d.node_id))
  }, [division])

  // Departments grouped by company (in the backend's company/level/name order).
  const grouped = useMemo(() => {
    const map = new Map<string, AvailableDepartment[]>()
    for (const dep of availableDepartments) {
      const key = dep.company || 'Fără companie'
      const list = map.get(key) || []
      list.push(dep)
      map.set(key, list)
    }
    return Array.from(map.entries())
  }, [availableDepartments])

  const employeeOptions = useMemo(
    () => employees.map((e) => ({ value: e.id, label: e.name })),
    [employees],
  )

  const toggleNode = (nodeId: number, checked: boolean) => {
    setNodeIds((prev) => (checked ? [...prev, nodeId] : prev.filter((n) => n !== nodeId)))
  }

  if (!division) return null

  const nameChanged = name.trim() !== division.name

  return (
    <Dialog open={!!division} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>Editează divizia</DialogTitle>
          <DialogDescription>
            Redenumește divizia, alege responsabilii și departamentele asociate.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-1">
          {/* Rename */}
          <div className="space-y-1.5">
            <Label htmlFor="edit-division-name" className="text-xs">Nume</Label>
            <Input
              id="edit-division-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          {/* Responsables */}
          <div className="space-y-1.5">
            <Label className="text-xs">Responsabili</Label>
            <MultiSelectPills
              options={employeeOptions}
              selected={userIds}
              onChange={(sel) => setUserIds(sel.map(Number))}
              placeholder="Adaugă responsabil…"
            />
          </div>

          {/* Departments */}
          <div className="space-y-1.5">
            <Label className="text-xs">Departamente</Label>
            <div className="rounded-md border max-h-64 overflow-y-auto">
              {grouped.length === 0 ? (
                <p className="px-3 py-4 text-center text-xs text-muted-foreground">
                  Niciun departament disponibil.
                </p>
              ) : (
                grouped.map(([company, deps]) => (
                  <div key={company}>
                    <div className="sticky top-0 z-10 bg-muted/60 px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                      {company}
                    </div>
                    {deps.map((dep) => {
                      const takenByOther =
                        dep.taken_by_division_id != null && dep.taken_by_division_id !== division.id
                      const checked = nodeIds.includes(dep.node_id)
                      return (
                        <label
                          key={dep.node_id}
                          className={cn(
                            'flex items-center gap-2 border-t border-muted/40 px-2 py-1.5 text-sm',
                            takenByOther
                              ? 'cursor-not-allowed opacity-50'
                              : 'cursor-pointer hover:bg-accent/50',
                          )}
                          style={{ paddingLeft: `${8 + Math.max(0, dep.level - 1) * 14}px` }}
                        >
                          <Checkbox
                            checked={checked}
                            disabled={takenByOther}
                            onCheckedChange={(v) => toggleNode(dep.node_id, v === true)}
                          />
                          <span>{dep.name}</span>
                          {takenByOther && (
                            <span className="text-xs text-muted-foreground">— altă divizie</span>
                          )}
                        </label>
                      )
                    })}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={saving}>Anulează</Button>
          <Button
            disabled={saving || !name.trim()}
            onClick={() => onSave({ id: division.id, name: name.trim(), nameChanged, userIds, nodeIds })}
          >
            {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
            Salvează
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
