import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { MobileCardList, type MobileCardField } from '@/components/shared/MobileCardList'
import {
  Plus,
  Pencil,
  Trash2,
  Search,
  FlaskConical,
  Loader2,
  LinkIcon,
  Check,
  X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { statementsApi } from '@/api/statements'
import { toast } from 'sonner'
import type { VendorMapping } from '@/types/statements'

function formatDate(d: string) {
  return new Date(d).toLocaleDateString('ro-RO')
}

const mappingsMobileFields: MobileCardField<VendorMapping>[] = [
  { key: 'supplier', label: 'Supplier', isPrimary: true, render: (m) => m.supplier_name },
  { key: 'pattern', label: 'Pattern', isSecondary: true, render: (m) => <code className="font-mono text-xs">{m.pattern}</code> },
  { key: 'status', label: 'Status', render: (m) => <Badge variant={m.is_active ? 'default' : 'secondary'} className="text-xs">{m.is_active ? 'Active' : 'Inactive'}</Badge> },
  { key: 'vat', label: 'VAT', render: (m) => <span className="text-xs">{m.supplier_vat ?? '—'}</span> },
  { key: 'created', label: 'Created', expandOnly: true, render: (m) => <span className="text-xs">{formatDate(m.created_at)}</span> },
]

export default function MappingsTab() {
  const queryClient = useQueryClient()
  const isMobile = useIsMobile()
  const [search, setSearch] = useState('')
  const [showInactive, setShowInactive] = useState(false)
  const [editMapping, setEditMapping] = useState<VendorMapping | null>(null)
  const [addOpen, setAddOpen] = useState(false)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [testOpen, setTestOpen] = useState<VendorMapping | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['statements-mappings', showInactive],
    queryFn: () => statementsApi.getMappings(!showInactive),
  })

  const mappings = useMemo(() => {
    const list = data ?? []
    if (!search) return list
    const q = search.toLowerCase()
    return list.filter(
      (m) =>
        m.pattern.toLowerCase().includes(q) ||
        m.supplier_name.toLowerCase().includes(q) ||
        (m.supplier_vat?.toLowerCase().includes(q) ?? false),
    )
  }, [data, search])

  const deleteMutation = useMutation({
    mutationFn: (id: number) => statementsApi.deleteMapping(id),
    onSuccess: () => {
      toast.success('Mapping deleted')
      queryClient.invalidateQueries({ queryKey: ['statements-mappings'] })
    },
    onError: () => toast.error('Delete failed'),
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      statementsApi.updateMapping(id, { is_active }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['statements-mappings'] })
    },
    onError: () => toast.error('Toggle failed'),
  })

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-0 max-w-xs">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input className="pl-8" placeholder="Search mappings..." value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <div className="hidden sm:flex items-center gap-1.5 text-sm text-muted-foreground">
          <Switch checked={showInactive} onCheckedChange={setShowInactive} id="show-inactive" />
          <Label htmlFor="show-inactive" className="cursor-pointer text-xs">Show inactive</Label>
        </div>
        <span className="hidden sm:inline text-xs text-muted-foreground">{mappings.length} mappings</span>
        <Button size="icon" className="ml-auto md:size-auto md:px-3" onClick={() => setAddOpen(true)}>
          <Plus className="h-4 w-4 md:mr-1" />
          <span className="hidden md:inline">Add Mapping</span>
        </Button>
      </div>

      {isLoading ? (
        <Card className="p-6">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-10 animate-pulse rounded bg-muted mb-2" />
          ))}
        </Card>
      ) : mappings.length === 0 ? (
        <EmptyState
          icon={<LinkIcon className="h-8 w-8" />}
          title="No vendor mappings"
          description="Create mappings to automatically match transaction descriptions to suppliers."
          action={
            <Button onClick={() => setAddOpen(true)}>
              <Plus className="mr-1.5 h-4 w-4" />
              Add Mapping
            </Button>
          }
        />
      ) : isMobile ? (
        <MobileCardList
          data={mappings}
          fields={mappingsMobileFields}
          getRowId={(m) => m.id}
          actions={(m) => (
            <>
              <Button variant="ghost" size="icon" className="h-7 w-7" title="Test pattern" onClick={() => setTestOpen(m)}>
                <FlaskConical className="h-3.5 w-3.5" />
              </Button>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setEditMapping(m)}>
                <Pencil className="h-3.5 w-3.5" />
              </Button>
              <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => setDeleteId(m.id)}>
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </>
          )}
        />
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Pattern</TableHead>
                  <TableHead>Supplier Name</TableHead>
                  <TableHead>VAT</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="w-28">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {mappings.map((m) => (
                  <TableRow key={m.id} className={!m.is_active ? 'opacity-50' : undefined}>
                    <TableCell className="font-mono text-xs max-w-[250px] truncate">{m.pattern}</TableCell>
                    <TableCell className="text-sm font-medium">{m.supplier_name}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{m.supplier_vat ?? '—'}</TableCell>
                    <TableCell>
                      <Badge
                        variant={m.is_active ? 'default' : 'secondary'}
                        className="cursor-pointer text-xs"
                        onClick={() => toggleMutation.mutate({ id: m.id, is_active: !m.is_active })}
                      >
                        {m.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">{formatDate(m.created_at)}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Button variant="ghost" size="icon" className="h-7 w-7" title="Test pattern" onClick={() => setTestOpen(m)}>
                          <FlaskConical className="h-3.5 w-3.5" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setEditMapping(m)}>
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => setDeleteId(m.id)}>
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </Card>
      )}

      {/* Add / Edit dialog */}
      <MappingFormDialog
        open={addOpen || editMapping !== null}
        mapping={editMapping}
        onClose={() => { setAddOpen(false); setEditMapping(null) }}
      />

      {/* Test pattern dialog */}
      {testOpen && (
        <TestPatternDialog
          mapping={testOpen}
          open
          onClose={() => setTestOpen(null)}
        />
      )}

      {/* Delete confirm */}
      <ConfirmDialog
        open={deleteId !== null}
        title="Delete Mapping"
        description="This vendor mapping will be permanently deleted."
        onOpenChange={() => setDeleteId(null)}
        onConfirm={() => deleteId !== null && deleteMutation.mutate(deleteId)}
        destructive
      />
    </div>
  )
}

/* ──── Mapping Form Dialog ──── */

function MappingFormDialog({
  open,
  mapping,
  onClose,
}: {
  open: boolean
  mapping: VendorMapping | null
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const isEdit = mapping !== null

  const [pattern, setPattern] = useState('')
  const [supplierName, setSupplierName] = useState('')
  const [supplierVat, setSupplierVat] = useState('')
  const [patternError, setPatternError] = useState('')

  // Reset form when dialog opens
  const handleOpenChange = (v: boolean) => {
    if (v) {
      setPattern(mapping?.pattern ?? '')
      setSupplierName(mapping?.supplier_name ?? '')
      setSupplierVat(mapping?.supplier_vat ?? '')
      setPatternError('')
    } else {
      onClose()
    }
  }

  const validatePattern = (p: string) => {
    if (!p) { setPatternError(''); return true }
    try {
      new RegExp(p, 'i')
      setPatternError('')
      return true
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Invalid regex'
      setPatternError(msg)
      return false
    }
  }

  const createMutation = useMutation({
    mutationFn: (data: { pattern: string; supplier_name: string; supplier_vat?: string }) =>
      statementsApi.createMapping(data),
    onSuccess: () => {
      toast.success('Mapping created')
      queryClient.invalidateQueries({ queryKey: ['statements-mappings'] })
      onClose()
    },
    onError: () => toast.error('Create failed'),
  })

  const updateMutation = useMutation({
    mutationFn: (data: Partial<VendorMapping>) =>
      statementsApi.updateMapping(mapping!.id, data),
    onSuccess: () => {
      toast.success('Mapping updated')
      queryClient.invalidateQueries({ queryKey: ['statements-mappings'] })
      onClose()
    },
    onError: () => toast.error('Update failed'),
  })

  const handleSubmit = () => {
    if (!pattern.trim() || !supplierName.trim()) return
    if (!validatePattern(pattern)) return

    if (isEdit) {
      updateMutation.mutate({
        pattern,
        supplier_name: supplierName,
        supplier_vat: supplierVat || undefined,
      } as Partial<VendorMapping>)
    } else {
      createMutation.mutate({
        pattern,
        supplier_name: supplierName,
        supplier_vat: supplierVat || undefined,
      })
    }
  }

  const isPending = createMutation.isPending || updateMutation.isPending

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit Mapping' : 'Add Mapping'}</DialogTitle>
          <DialogDescription>
            {isEdit ? 'Update the vendor mapping pattern and supplier info.' : 'Map a regex pattern to a supplier for automatic transaction matching.'}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="pattern">Regex Pattern</Label>
            <Input
              id="pattern"
              className="font-mono text-sm"
              placeholder="e.g. AUTOWORLD.*SRL"
              value={pattern}
              onChange={(e) => { setPattern(e.target.value); validatePattern(e.target.value) }}
            />
            {patternError && <p className="text-xs text-destructive">{patternError}</p>}
            <p className="text-xs text-muted-foreground">Case-insensitive regex matched against transaction descriptions</p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="supplier-name">Supplier Name</Label>
            <Input
              id="supplier-name"
              placeholder="e.g. AUTOWORLD SRL"
              value={supplierName}
              onChange={(e) => setSupplierName(e.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="supplier-vat">Supplier VAT (optional)</Label>
            <Input
              id="supplier-vat"
              placeholder="e.g. RO12345678"
              value={supplierVat}
              onChange={(e) => setSupplierVat(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            onClick={handleSubmit}
            disabled={!pattern.trim() || !supplierName.trim() || !!patternError || isPending}
          >
            {isPending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
            {isEdit ? 'Save Changes' : 'Create Mapping'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/* ──── Test Pattern Dialog ──── */

function TestPatternDialog({
  mapping,
  open,
  onClose,
}: {
  mapping: VendorMapping
  open: boolean
  onClose: () => void
}) {
  const [testInput, setTestInput] = useState('')
  const [result, setResult] = useState<{ matched: boolean; match?: string } | null>(null)

  const runTest = () => {
    if (!testInput.trim()) return
    try {
      const re = new RegExp(mapping.pattern, 'i')
      const m = re.exec(testInput)
      setResult(m ? { matched: true, match: m[0] } : { matched: false })
    } catch {
      setResult({ matched: false })
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Test Pattern</DialogTitle>
          <DialogDescription>
            Test <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">{mapping.pattern}</code> against sample text.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Supplier</Label>
            <p className="text-sm font-medium">{mapping.supplier_name}</p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="test-text">Test String</Label>
            <Input
              id="test-text"
              placeholder="Paste a transaction description..."
              value={testInput}
              onChange={(e) => { setTestInput(e.target.value); setResult(null) }}
              onKeyDown={(e) => e.key === 'Enter' && runTest()}
            />
          </div>
          <Button size="sm" onClick={runTest} disabled={!testInput.trim()}>
            <FlaskConical className="mr-1.5 h-3.5 w-3.5" />
            Test
          </Button>

          {result && (
            <div className={`flex items-center gap-2 rounded-md border p-3 text-sm ${result.matched ? 'border-green-500/30 bg-green-500/5' : 'border-destructive/30 bg-destructive/5'}`}>
              {result.matched ? (
                <>
                  <Check className="h-4 w-4 text-green-500" />
                  <span>Match: <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">{result.match}</code></span>
                </>
              ) : (
                <>
                  <X className="h-4 w-4 text-destructive" />
                  <span>No match</span>
                </>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
