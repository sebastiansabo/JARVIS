import { useState, useMemo, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Pencil, Building2, Layers, GitBranch, BarChart3, Crown, ChevronRight, ChevronDown, Users } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { SearchInput } from '@/components/shared/SearchInput'
import { StatCard } from '@/components/shared/StatCard'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { organizationApi } from '@/api/organization'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import type { CompanyWithBrands, StructureNode } from '@/types/organization'

/* ──── Company tree helpers ──── */

interface CompanyTreeNode extends CompanyWithBrands {
  children: CompanyTreeNode[]
  depth: number
}

function buildCompanyTree(companies: CompanyWithBrands[]): CompanyTreeNode[] {
  const map = new Map<number, CompanyTreeNode>()
  const roots: CompanyTreeNode[] = []
  for (const c of companies) map.set(c.id, { ...c, children: [], depth: 0 })
  for (const node of map.values()) {
    if (node.parent_company_id && map.has(node.parent_company_id)) {
      map.get(node.parent_company_id)!.children.push(node)
    } else {
      roots.push(node)
    }
  }
  function setDepth(nodes: CompanyTreeNode[], depth: number) {
    for (const n of nodes) { n.depth = depth; setDepth(n.children, depth + 1) }
  }
  setDepth(roots, 0)
  return roots
}

function flattenTree(nodes: CompanyTreeNode[]): CompanyTreeNode[] {
  const result: CompanyTreeNode[] = []
  function walk(list: CompanyTreeNode[]) {
    for (const n of list) { result.push(n); walk(n.children) }
  }
  walk(nodes)
  return result
}

/* ──── Structure node tree helpers ──── */

interface TreeNode extends StructureNode {
  children: TreeNode[]
}

function buildNodeTree(nodes: StructureNode[]): Map<number, TreeNode[]> {
  const byCompany = new Map<number, StructureNode[]>()
  for (const n of nodes) {
    const list = byCompany.get(n.company_id) || []
    list.push(n)
    byCompany.set(n.company_id, list)
  }

  const result = new Map<number, TreeNode[]>()
  for (const [companyId, companyNodes] of byCompany) {
    const nodeMap = new Map<number, TreeNode>()
    for (const n of companyNodes) nodeMap.set(n.id, { ...n, children: [] })
    const roots: TreeNode[] = []
    for (const node of nodeMap.values()) {
      if (node.parent_id && nodeMap.has(node.parent_id)) {
        nodeMap.get(node.parent_id)!.children.push(node)
      } else {
        roots.push(node)
      }
    }
    const sortNodes = (list: TreeNode[]) => {
      list.sort((a, b) => a.display_order - b.display_order || a.name.localeCompare(b.name))
      for (const n of list) sortNodes(n.children)
    }
    sortNodes(roots)
    result.set(companyId, roots)
  }
  return result
}

function countAllDescendants(nodes: TreeNode[]): number {
  let count = nodes.length
  for (const n of nodes) count += countAllDescendants(n.children)
  return count
}

/* ──── Level colors ──── */

const levelColors = [
  'text-amber-600 dark:text-amber-400',   // L1
  'text-green-600 dark:text-green-400',    // L2
  'text-blue-600 dark:text-blue-400',      // L3
  'text-purple-600 dark:text-purple-400',  // L4
  'text-pink-600 dark:text-pink-400',      // L5
]

const levelBg = [
  'bg-amber-50/50 dark:bg-amber-950/20',
  'bg-green-50/30 dark:bg-green-950/15',
  'bg-blue-50/25 dark:bg-blue-950/10',
  'bg-purple-50/20 dark:bg-purple-950/10',
  'bg-pink-50/15 dark:bg-pink-950/10',
]

/* ──── Main component ──── */

export default function StructureTab() {
  const [showStats, setShowStats] = useState(false)

  const { data: companies = [] } = useQuery({
    queryKey: ['settings', 'companiesConfig'],
    queryFn: organizationApi.getCompaniesConfig,
  })

  const { data: structureNodes = [] } = useQuery({
    queryKey: ['settings', 'structureNodes'],
    queryFn: organizationApi.getStructureNodes,
  })

  return (
    <div className="space-y-6">
      <div className={`grid grid-cols-1 gap-4 sm:grid-cols-3 ${showStats ? '' : 'hidden md:grid'}`}>
        <StatCard title="Companies" value={companies.length} icon={<Building2 className="h-4 w-4" />} />
        <StatCard title="Structure Nodes" value={structureNodes.length} icon={<Layers className="h-4 w-4" />} />
        <StatCard title="Max Depth" value={Math.max(0, ...structureNodes.map(n => n.level))} icon={<GitBranch className="h-4 w-4" />} />
      </div>
      <div className="flex items-center gap-2 md:hidden">
        <Button variant="ghost" size="icon" onClick={() => setShowStats(s => !s)}>
          <BarChart3 className="h-4 w-4" />
        </Button>
      </div>
      <CompaniesSection companies={companies} structureNodes={structureNodes} />
    </div>
  )
}

/* ──── Companies + Structure section ──── */

function CompaniesSection({ companies, structureNodes }: { companies: CompanyWithBrands[]; structureNodes: StructureNode[] }) {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [editCompany, setEditCompany] = useState<CompanyWithBrands | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  // Node CRUD state
  const [addNodeParent, setAddNodeParent] = useState<{ companyId: number; parentId?: number; level: number } | null>(null)
  const [editNode, setEditNode] = useState<StructureNode | null>(null)
  const [deleteNodeId, setDeleteNodeId] = useState<number | null>(null)

  const tree = useMemo(() => buildCompanyTree(companies), [companies])
  const flat = useMemo(() => flattenTree(tree), [tree])
  const nodeTreeByCompany = useMemo(() => buildNodeTree(structureNodes), [structureNodes])

  const toggleExpand = (key: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  // Company mutations
  const createMutation = useMutation({
    mutationFn: (data: { company: string; vat?: string; parent_company_id?: number | null }) => organizationApi.createCompanyConfig(data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['settings', 'companiesConfig'] }); setShowAdd(false); toast.success('Company created') },
    onError: () => toast.error('Failed to create company'),
  })
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<CompanyWithBrands> & { parent_company_id?: number | null } }) => organizationApi.updateCompanyConfig(id, data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['settings', 'companiesConfig'] }); setEditCompany(null); toast.success('Company updated') },
    onError: () => toast.error('Failed to update company'),
  })
  const deleteMutation = useMutation({
    mutationFn: (id: number) => organizationApi.deleteCompanyConfig(id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['settings', 'companiesConfig'] }); setDeleteId(null); toast.success('Company deleted') },
    onError: () => toast.error('Failed to delete company'),
  })

  // Structure node mutations
  const createNodeMut = useMutation({
    mutationFn: (data: { company_id: number; parent_id?: number | null; name: string }) => organizationApi.createStructureNode(data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['settings', 'structureNodes'] }); setAddNodeParent(null); toast.success('Node created') },
    onError: () => toast.error('Failed to create node'),
  })
  const updateNodeMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: { name?: string; has_team?: boolean } }) => organizationApi.updateStructureNode(id, data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['settings', 'structureNodes'] }); setEditNode(null); toast.success('Node updated') },
    onError: () => toast.error('Failed to update node'),
  })
  const deleteNodeMut = useMutation({
    mutationFn: (id: number) => organizationApi.deleteStructureNode(id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['settings', 'structureNodes'] }); setDeleteNodeId(null); toast.success('Node deleted') },
    onError: () => toast.error('Failed to delete node'),
  })

  const filtered = flat.filter(c => !search || c.company.toLowerCase().includes(search.toLowerCase()))
  const deleteTarget = companies.find(c => c.id === deleteId)
  const hasChildren = deleteTarget ? companies.some(c => c.parent_company_id === deleteTarget.id) : false

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Companies & Structure</CardTitle>
          <Button size="sm" onClick={() => setShowAdd(true)}>
            <Plus className="mr-1.5 h-4 w-4" />
            Add Company
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <SearchInput value={search} onChange={setSearch} placeholder="Search companies..." className="mb-4" />

        {filtered.length === 0 ? (
          <EmptyState title="No companies found" description={search ? 'Try a different search.' : 'Add your first company.'} />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Company / Structure</TableHead>
                <TableHead>VAT</TableHead>
                <TableHead className="text-center">Nodes</TableHead>
                <TableHead className="w-24">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((c) => {
                const companyKey = `c-${c.id}`
                const isExpanded = expanded.has(companyKey)
                const companyNodes = nodeTreeByCompany.get(c.id) || []
                const totalNodes = countAllDescendants(companyNodes)
                const hasCompanyContent = companyNodes.length > 0 || c.children.length > 0

                return (
                  <>
                    {/* Company row */}
                    <TableRow
                      key={c.id}
                      className={cn('cursor-pointer', isExpanded && 'bg-muted/50')}
                      onClick={() => toggleExpand(companyKey)}
                    >
                      <TableCell>
                        <div className="flex items-center gap-1.5" style={{ paddingLeft: `${c.depth * 24}px` }}>
                          {hasCompanyContent
                            ? isExpanded
                              ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                              : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                            : <span className="h-3.5 w-3.5 shrink-0" />
                          }
                          {c.children.length > 0 && <Crown className="h-3.5 w-3.5 text-amber-500 shrink-0" />}
                          <span className="font-medium">{c.company}</span>
                          <span className="text-[10px] text-muted-foreground">L0</span>
                          {c.children.length > 0 && (
                            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                              Holding
                            </span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="text-muted-foreground font-mono text-xs">{c.vat || '-'}</TableCell>
                      <TableCell className="text-center">
                        {totalNodes > 0 ? (
                          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                            <Users className="h-3 w-3" />
                            {totalNodes}
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">-</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1" onClick={e => e.stopPropagation()}>
                          <Button variant="ghost" size="sm" onClick={() => setEditCompany(c)}>
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setDeleteId(c.id)}>
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>

                    {/* Recursive structure nodes */}
                    {isExpanded && companyNodes.map(node => (
                      <NodeRows
                        key={node.id}
                        node={node}
                        basePad={(c.depth * 24) + 32}
                        expanded={expanded}
                        toggleExpand={toggleExpand}
                        onAdd={(parentId, level) => setAddNodeParent({ companyId: c.id, parentId, level })}
                        onEdit={setEditNode}
                        onDelete={setDeleteNodeId}
                      />
                    ))}

                    {/* Add root-level node button */}
                    {isExpanded && (
                      <TableRow key={`add-${c.id}`} className="bg-muted/10">
                        <TableCell colSpan={4}>
                          <div style={{ paddingLeft: `${(c.depth * 24) + 32}px` }}>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 text-xs text-muted-foreground hover:text-foreground"
                              onClick={() => setAddNodeParent({ companyId: c.id, level: 1 })}
                            >
                              <Plus className="mr-1 h-3 w-3" />
                              Add level 1
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </>
                )
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>

      {/* Company dialogs */}
      <CompanyFormDialog
        open={showAdd || !!editCompany}
        company={editCompany}
        companies={companies}
        onClose={() => { setShowAdd(false); setEditCompany(null) }}
        onSave={(data) => {
          if (editCompany) updateMutation.mutate({ id: editCompany.id, data })
          else createMutation.mutate(data as { company: string; vat?: string; parent_company_id?: number | null })
        }}
        isPending={createMutation.isPending || updateMutation.isPending}
      />

      <ConfirmDialog
        open={!!deleteId}
        onOpenChange={() => setDeleteId(null)}
        title="Delete Company"
        description={hasChildren
          ? 'This will also remove all structure nodes. Subsidiaries will be promoted to root level.'
          : 'This will also remove all structure nodes.'}
        onConfirm={() => deleteId && deleteMutation.mutate(deleteId)}
        destructive
      />

      {/* Node dialogs */}
      <NodeFormDialog
        open={!!addNodeParent || !!editNode}
        node={editNode}
        onClose={() => { setAddNodeParent(null); setEditNode(null) }}
        onSave={(name) => {
          if (editNode) {
            updateNodeMut.mutate({ id: editNode.id, data: { name } })
          } else if (addNodeParent) {
            createNodeMut.mutate({
              company_id: addNodeParent.companyId,
              parent_id: addNodeParent.parentId || null,
              name,
            })
          }
        }}
        isPending={createNodeMut.isPending || updateNodeMut.isPending}
      />

      <ConfirmDialog
        open={!!deleteNodeId}
        onOpenChange={() => setDeleteNodeId(null)}
        title="Delete Node"
        description="This will remove this node and all its children."
        onConfirm={() => deleteNodeId && deleteNodeMut.mutate(deleteNodeId)}
        destructive
      />
    </Card>
  )
}

/* ──── Recursive node rows ──── */

function NodeRows({ node, basePad, expanded, toggleExpand, onAdd, onEdit, onDelete }: {
  node: TreeNode
  basePad: number
  expanded: Set<string>
  toggleExpand: (key: string) => void
  onAdd: (parentId: number, level: number) => void
  onEdit: (node: StructureNode) => void
  onDelete: (id: number) => void
}) {
  const nodeKey = `n-${node.id}`
  const isExpanded = expanded.has(nodeKey)
  const hasChildren = node.children.length > 0
  const canAddChild = node.level < 5
  const levelIdx = Math.min(node.level - 1, 4)
  const indent = basePad + (node.level - 1) * 20

  return (
    <>
      <TableRow
        className={cn(levelBg[levelIdx], hasChildren && 'cursor-pointer')}
        onClick={() => hasChildren && toggleExpand(nodeKey)}
      >
        <TableCell>
          <div className="flex items-center gap-1.5 text-xs" style={{ paddingLeft: `${indent}px` }}>
            {hasChildren
              ? isExpanded
                ? <ChevronDown className="h-3 w-3 text-muted-foreground shrink-0" />
                : <ChevronRight className="h-3 w-3 text-muted-foreground shrink-0" />
              : <span className="h-3 w-3 shrink-0" />
            }
            <span className={cn('font-medium', levelColors[levelIdx])}>{node.name}</span>
            <span className="text-[10px] text-muted-foreground">L{node.level}</span>
            {hasChildren && (
              <span className="text-[10px] text-muted-foreground">
                ({node.children.length})
              </span>
            )}
          </div>
        </TableCell>
        <TableCell />
        <TableCell />
        <TableCell>
          <div className="flex gap-1" onClick={e => e.stopPropagation()}>
            {canAddChild && (
              <Button
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0 text-muted-foreground hover:text-foreground"
                title={`Add child (L${node.level + 1})`}
                onClick={() => onAdd(node.id, node.level + 1)}
              >
                <Plus className="h-3 w-3" />
              </Button>
            )}
            <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => onEdit(node)}>
              <Pencil className="h-3 w-3" />
            </Button>
            <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-destructive" onClick={() => onDelete(node.id)}>
              <Trash2 className="h-3 w-3" />
            </Button>
          </div>
        </TableCell>
      </TableRow>

      {/* Recursive children */}
      {isExpanded && node.children.map(child => (
        <NodeRows
          key={child.id}
          node={child}
          basePad={basePad}
          expanded={expanded}
          toggleExpand={toggleExpand}
          onAdd={onAdd}
          onEdit={onEdit}
          onDelete={onDelete}
        />
      ))}
    </>
  )
}

/* ──── Company form dialog ──── */

function CompanyFormDialog({ open, company, companies, onClose, onSave, isPending }: {
  open: boolean; company: CompanyWithBrands | null; companies: CompanyWithBrands[]; onClose: () => void
  onSave: (data: Partial<CompanyWithBrands> & { parent_company_id?: number | null }) => void; isPending: boolean
}) {
  const [name, setName] = useState('')
  const [vat, setVat] = useState('')
  const [parentId, setParentId] = useState<string>('none')

  const resetForm = () => {
    if (company) {
      setName(company.company); setVat(company.vat || ''); setParentId(company.parent_company_id ? String(company.parent_company_id) : 'none')
    } else {
      setName(''); setVat(''); setParentId('none')
    }
  }

  const parentOptions = companies.filter(c => !company || c.id !== company.id)

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); else resetForm() }}>
      <DialogContent className="sm:max-w-sm" onOpenAutoFocus={resetForm}>
        <DialogHeader>
          <DialogTitle>{company ? 'Edit Company' : 'Add Company'}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Company Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label>VAT Number</Label>
            <Input value={vat} onChange={(e) => setVat(e.target.value)} placeholder="Optional" />
          </div>
          <div className="grid gap-2">
            <Label>Parent Company</Label>
            <Select value={parentId} onValueChange={setParentId}>
              <SelectTrigger><SelectValue placeholder="None (root level)" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None (root level)</SelectItem>
                {parentOptions.map(c => (
                  <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            disabled={!name || isPending}
            onClick={() => onSave({ company: name, vat: vat || undefined, parent_company_id: parentId === 'none' ? null : Number(parentId) })}
          >
            {isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/* ──── Node form dialog (add / rename) ──── */

function NodeFormDialog({ open, node, onClose, onSave, isPending }: {
  open: boolean; node: StructureNode | null; onClose: () => void
  onSave: (name: string) => void; isPending: boolean
}) {
  const [name, setName] = useState('')
  const isEditing = !!node

  useEffect(() => {
    if (!open) return
    setName(node?.name || '')
  }, [open, node])

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Rename' : 'Add Node'}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Name</Label>
            <Input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && name.trim()) onSave(name.trim()) }}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={!name.trim() || isPending} onClick={() => onSave(name.trim())}>
            {isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
