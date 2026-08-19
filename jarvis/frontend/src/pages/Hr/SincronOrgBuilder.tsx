import { useState, useMemo, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Pencil, ChevronRight, ChevronDown, Users, Sprout, Crown, FolderInput } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { MultiSelectPills } from '@/components/shared/MultiSelectPills'
import { organizationApi } from '@/api/organization'
import { api } from '@/api/client'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import type { SincronOrgNode, SincronOrgMember } from '@/types/organization'

/* ──── Tree helpers ──── */

interface TreeNode extends SincronOrgNode {
  children: TreeNode[]
}

function buildTree(nodes: SincronOrgNode[]): Map<number, TreeNode[]> {
  const byCompany = new Map<number, SincronOrgNode[]>()
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

/* ──── Level colors ──── */

const levelColors = [
  'text-amber-600 dark:text-amber-400',   // L1
  'text-green-600 dark:text-green-400',    // L2
  'text-blue-600 dark:text-blue-400',      // L3
  'text-purple-600 dark:text-purple-400',  // L4
  'text-pink-600 dark:text-pink-400',      // L5
  'text-rose-600 dark:text-rose-400',      // L6
]

const levelBg = [
  'bg-amber-50/50 dark:bg-amber-950/20',
  'bg-green-50/30 dark:bg-green-950/15',
  'bg-blue-50/25 dark:bg-blue-950/10',
  'bg-purple-50/20 dark:bg-purple-950/10',
  'bg-pink-50/15 dark:bg-pink-950/10',
  'bg-rose-50/10 dark:bg-rose-950/10',
]

const nodeTypeLabels: Record<string, string> = {
  department: 'Dept',
  role: 'Role',
  team: 'Team',
  unallocated: 'Nealocat',
}

/* ──── Sincron employee type (from /sincron/api/employees) ──── */

interface SincronEmployee {
  id: number
  sincron_employee_id: string
  company_name: string
  nume: string
  prenume: string
  nr_contract: string | null
  is_active: boolean
  department: string | null
}

/* ──── Main component ──── */

export default function SincronOrgBuilder() {
  const queryClient = useQueryClient()
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  // CRUD state
  const [addNodeParent, setAddNodeParent] = useState<{ companyId: number; parentId?: number; level: number } | null>(null)
  const [editNode, setEditNode] = useState<SincronOrgNode | null>(null)
  const [deleteNodeId, setDeleteNodeId] = useState<number | null>(null)
  const [moveNode, setMoveNode] = useState<TreeNode | null>(null)

  // Data queries — only Sincron companies (not all JARVIS companies)
  const { data: companiesRes } = useQuery({
    queryKey: ['sincron', 'orgCompanies'],
    queryFn: organizationApi.getSincronOrgCompanies,
  })
  const companies = companiesRes?.data ?? []

  const { data: nodesRes } = useQuery({
    queryKey: ['sincron', 'orgNodes'],
    queryFn: () => organizationApi.getSincronOrgNodes(),
  })
  const nodes = nodesRes?.data ?? []

  const { data: membersRes } = useQuery({
    queryKey: ['sincron', 'orgMembers'],
    queryFn: organizationApi.getSincronOrgMembers,
  })
  const members = membersRes?.data ?? []

  const { data: employeesRes } = useQuery({
    queryKey: ['sincron', 'employees'],
    queryFn: () => api.get<{ success: boolean; data: SincronEmployee[] }>('/sincron/api/employees'),
  })
  const allEmployees = employeesRes?.data ?? []

  const treeByCompany = useMemo(() => buildTree(nodes), [nodes])

  // Group members by node
  const membersByNode = useMemo(() => {
    const map = new Map<number, SincronOrgMember[]>()
    for (const m of members) {
      const list = map.get(m.node_id) || []
      list.push(m)
      map.set(m.node_id, list)
    }
    return map
  }, [members])

  // Group employees by company_name for selects
  const employeesByCompany = useMemo(() => {
    const map = new Map<string, SincronEmployee[]>()
    for (const e of allEmployees) {
      const list = map.get(e.company_name) || []
      list.push(e)
      map.set(e.company_name, list)
    }
    return map
  }, [allEmployees])

  const toggleExpand = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  // Auto-expand companies on first load
  useEffect(() => {
    if (companies.length > 0 && expanded.size === 0) {
      setExpanded(new Set(companies.map((c) => `c-${c.company_id}`)))
    }
  }, [companies.length])

  // Mutations
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['sincron', 'orgNodes'] })
    queryClient.invalidateQueries({ queryKey: ['sincron', 'orgMembers'] })
  }

  const createNodeMut = useMutation({
    mutationFn: (data: { company_id: number; parent_id?: number | null; name: string; node_type?: string }) =>
      organizationApi.createSincronOrgNode(data),
    onSuccess: () => { invalidate(); setAddNodeParent(null); toast.success('Node created') },
    onError: () => toast.error('Failed to create node'),
  })

  const updateNodeMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: { name?: string; node_type?: string } }) =>
      organizationApi.updateSincronOrgNode(id, data),
    onSuccess: () => { invalidate(); setEditNode(null); toast.success('Node updated') },
    onError: () => toast.error('Failed to update node'),
  })

  const deleteNodeMut = useMutation({
    mutationFn: (id: number) => organizationApi.deleteSincronOrgNode(id),
    onSuccess: () => { invalidate(); setDeleteNodeId(null); toast.success('Node deleted') },
    onError: () => toast.error('Failed to delete node'),
  })

  const moveNodeMut = useMutation({
    mutationFn: ({ id, parentId }: { id: number; parentId: number | null }) =>
      organizationApi.updateSincronOrgNode(id, { parent_id: parentId }),
    onSuccess: () => { invalidate(); setMoveNode(null); toast.success('Node mutat') },
    onError: (e: any) => toast.error(e?.response?.data?.error || 'Failed to move node'),
  })

  const setMembersMut = useMutation({
    mutationFn: ({ nodeId, role, memberKeys }: { nodeId: number; role: 'responsable' | 'member'; memberKeys: { sincron_employee_id: string; company_name: string }[] }) =>
      organizationApi.setSincronOrgMembers(nodeId, role, memberKeys),
    onSuccess: () => { invalidate(); toast.success('Members updated') },
    onError: () => toast.error('Failed to update members'),
  })

  const seedMut = useMutation({
    mutationFn: (companyId: number) => organizationApi.seedSincronOrgNodes(companyId),
    onSuccess: (data) => {
      invalidate()
      toast.success(`Seeded: ${data.created} created, ${data.assigned} assigned`)
    },
    onError: () => toast.error('Failed to seed nodes'),
  })

  if (!companies.length) {
    return <EmptyState title="No Sincron data" description="No active Sincron employees found." />
  }

  return (
    <div className="space-y-3">
      {companies.map((company) => {
        const companyKey = `c-${company.company_id}`
        const isExpanded = expanded.has(companyKey)
        const companyNodes = treeByCompany.get(company.company_id) || []
        const companyName = company.company_name

        // Get employee options for this company
        const compEmployees = employeesByCompany.get(companyName) || []

        return (
          <Card key={company.company_id} className="overflow-hidden">
            {/* Company header */}
            <button
              onClick={() => toggleExpand(companyKey)}
              className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-muted/50 transition-colors"
            >
              {isExpanded ? (
                <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
              ) : (
                <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
              )}
              <Crown className="h-5 w-5 text-amber-600 shrink-0" />
              <span className="font-semibold text-sm">{companyName}</span>
              <span className="text-[10px] text-muted-foreground">L0</span>
              <div className="ml-auto flex items-center gap-2">
                <Badge variant="outline" className="text-xs">
                  {companyNodes.length} nodes
                </Badge>
              </div>
            </button>

            {isExpanded && (
              <div className="border-t">
                {companyNodes.length === 0 ? (
                  <div className="px-4 py-6 text-center text-sm text-muted-foreground">
                    No org nodes yet.
                  </div>
                ) : (
                  companyNodes.map((node) => (
                    <SincronNodeRow
                      key={node.id}
                      node={node}
                      indent={24}
                      expanded={expanded}
                      toggleExpand={toggleExpand}
                      membersByNode={membersByNode}
                      employees={compEmployees}
                      companyName={companyName}
                      onAdd={(parentId, level) => setAddNodeParent({ companyId: company.company_id, parentId, level })}
                      onEdit={setEditNode}
                      onDelete={setDeleteNodeId}
                      onMove={setMoveNode}
                      onSetMembers={(nodeId, role, keys) => setMembersMut.mutate({ nodeId, role, memberKeys: keys })}
                    />
                  ))
                )}

                {/* Actions row */}
                <div className="flex items-center gap-2 px-4 py-2 border-t bg-muted/10">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs text-muted-foreground hover:text-foreground"
                    onClick={() => setAddNodeParent({ companyId: company.company_id, level: 1 })}
                  >
                    <Plus className="mr-1 h-3 w-3" />
                    Add L1
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs text-muted-foreground hover:text-foreground"
                    onClick={() => seedMut.mutate(company.company_id)}
                    disabled={seedMut.isPending}
                  >
                    <Sprout className="mr-1 h-3 w-3" />
                    {seedMut.isPending ? 'Seeding...' : 'Seed from Departments'}
                  </Button>
                </div>
              </div>
            )}
          </Card>
        )
      })}

      {/* Node create/edit dialog */}
      <NodeFormDialog
        open={!!addNodeParent || !!editNode}
        node={editNode}
        onClose={() => { setAddNodeParent(null); setEditNode(null) }}
        onSave={(name, nodeType) => {
          if (editNode) {
            updateNodeMut.mutate({ id: editNode.id, data: { name, node_type: nodeType } })
          } else if (addNodeParent) {
            createNodeMut.mutate({
              company_id: addNodeParent.companyId,
              parent_id: addNodeParent.parentId || null,
              name,
              node_type: nodeType,
            })
          }
        }}
        isPending={createNodeMut.isPending || updateNodeMut.isPending}
      />

      {/* Delete confirm */}
      <ConfirmDialog
        open={!!deleteNodeId}
        onOpenChange={() => setDeleteNodeId(null)}
        title="Delete Node"
        description="This will remove this node and all its children + member assignments."
        onConfirm={() => deleteNodeId && deleteNodeMut.mutate(deleteNodeId)}
        destructive
      />

      {/* Move-under-parent dialog */}
      <MoveNodeDialog
        node={moveNode}
        allNodes={nodes}
        onClose={() => setMoveNode(null)}
        onMove={(parentId) => moveNode && moveNodeMut.mutate({ id: moveNode.id, parentId })}
        isPending={moveNodeMut.isPending}
      />
    </div>
  )
}

/* ──── Recursive node row ──── */

function SincronNodeRow({
  node,
  indent,
  expanded,
  toggleExpand,
  membersByNode,
  employees,
  companyName,
  onAdd,
  onEdit,
  onDelete,
  onMove,
  onSetMembers,
}: {
  node: TreeNode
  indent: number
  expanded: Set<string>
  toggleExpand: (key: string) => void
  membersByNode: Map<number, SincronOrgMember[]>
  employees: SincronEmployee[]
  companyName: string
  onAdd: (parentId: number, level: number) => void
  onEdit: (node: SincronOrgNode) => void
  onDelete: (id: number) => void
  onMove: (node: TreeNode) => void
  onSetMembers: (nodeId: number, role: 'responsable' | 'member', keys: { sincron_employee_id: string; company_name: string }[]) => void
}) {
  const nodeKey = `n-${node.id}`
  const isExpanded = expanded.has(nodeKey)
  const hasChildren = node.children.length > 0
  const canAddChild = node.level < 6
  const levelIdx = Math.min(node.level - 1, 5)

  const nodeMembers = membersByNode.get(node.id) || []
  const responsables = nodeMembers.filter((m) => m.role === 'responsable')
  const memberList = nodeMembers.filter((m) => m.role === 'member')

  // Employee options for multi-select (composite key "EMP_ID::COMPANY")
  const employeeOptions = employees.map((e) => ({
    value: `${e.sincron_employee_id}::${e.company_name}`,
    label: `${e.nume} ${e.prenume}${e.nr_contract ? ` #${e.nr_contract}` : ''}`,
  }))

  const selectedResponsables = responsables.map((m) => `${m.sincron_employee_id}::${m.company_name}`)
  const selectedMembers = memberList.map((m) => `${m.sincron_employee_id}::${m.company_name}`)

  const handleMembersChange = (role: 'responsable' | 'member', selected: (string | number)[]) => {
    const keys = (selected as string[]).map((v) => {
      const [sid, cn] = v.split('::')
      return { sincron_employee_id: sid, company_name: cn }
    })
    onSetMembers(node.id, role, keys)
  }

  return (
    <>
      <div
        className={cn(
          'border-b border-muted/20 transition-colors',
          levelBg[levelIdx],
          (hasChildren || nodeMembers.length > 0) && 'cursor-pointer',
        )}
        onClick={() => toggleExpand(nodeKey)}
      >
        {/* Node header */}
        <div className="flex items-center gap-1.5 px-4 py-2" style={{ paddingLeft: `${indent}px` }}>
          {hasChildren || nodeMembers.length > 0 ? (
            isExpanded ? (
              <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            )
          ) : (
            <span className="h-3.5 w-3.5 shrink-0" />
          )}
          <span className={cn('font-medium text-sm', levelColors[levelIdx])}>{node.name}</span>
          <span className="text-[10px] text-muted-foreground">L{node.level}</span>
          <Badge
            variant="outline"
            className={cn(
              'text-[10px] px-1 py-0 h-4',
              node.node_type === 'unallocated' &&
                'border-amber-400 bg-amber-50 text-amber-700 dark:border-amber-500/50 dark:bg-amber-950/40 dark:text-amber-300',
            )}
            title={node.node_type === 'unallocated' ? 'Nealocat — atribuie un responsabil sau mută sub un departament' : undefined}
          >
            {nodeTypeLabels[node.node_type] || node.node_type}
          </Badge>
          {responsables.length > 0 && (
            <span className="text-[10px] text-muted-foreground">
              {responsables.map((r) => `${r.nume} ${r.prenume}`).join(', ')}
            </span>
          )}
          {memberList.length > 0 && (
            <Badge variant="secondary" className="text-[10px] px-1 py-0 h-4 ml-1">
              <Users className="h-2.5 w-2.5 mr-0.5" />
              {memberList.length}
            </Badge>
          )}

          {/* Actions */}
          <div className="ml-auto flex gap-1" onClick={(e) => e.stopPropagation()}>
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
            <Button
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0 text-muted-foreground hover:text-foreground"
              title="Mută sub…"
              onClick={() => onMove(node)}
            >
              <FolderInput className="h-3 w-3" />
            </Button>
            <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => onEdit(node)}>
              <Pencil className="h-3 w-3" />
            </Button>
            <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-destructive" onClick={() => onDelete(node.id)}>
              <Trash2 className="h-3 w-3" />
            </Button>
          </div>
        </div>

        {/* Member assignment (expanded) */}
        {isExpanded && (
          <div className="px-4 pb-2 space-y-2" style={{ paddingLeft: `${indent + 20}px` }} onClick={(e) => e.stopPropagation()}>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              <div>
                <Label className="text-[10px] uppercase text-muted-foreground font-semibold tracking-wider">Responsables</Label>
                <MultiSelectPills
                  options={employeeOptions}
                  selected={selectedResponsables}
                  onChange={(sel) => handleMembersChange('responsable', sel)}
                  placeholder="Assign responsable..."
                  className="mt-0.5"
                />
              </div>
              <div>
                <Label className="text-[10px] uppercase text-muted-foreground font-semibold tracking-wider">Members</Label>
                <MultiSelectPills
                  options={employeeOptions}
                  selected={selectedMembers}
                  onChange={(sel) => handleMembersChange('member', sel)}
                  placeholder="Assign members..."
                  className="mt-0.5"
                />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Recursive children */}
      {isExpanded &&
        node.children.map((child) => (
          <SincronNodeRow
            key={child.id}
            node={child}
            indent={indent + 20}
            expanded={expanded}
            toggleExpand={toggleExpand}
            membersByNode={membersByNode}
            employees={employees}
            companyName={companyName}
            onAdd={onAdd}
            onEdit={onEdit}
            onDelete={onDelete}
            onMove={onMove}
            onSetMembers={onSetMembers}
          />
        ))}
    </>
  )
}

/* ──── Node form dialog ──── */

function NodeFormDialog({
  open,
  node,
  onClose,
  onSave,
  isPending,
}: {
  open: boolean
  node: SincronOrgNode | null
  onClose: () => void
  onSave: (name: string, nodeType: string) => void
  isPending: boolean
}) {
  const [name, setName] = useState('')
  const [nodeType, setNodeType] = useState('department')
  const isEditing = !!node

  useEffect(() => {
    if (!open) return
    setName(node?.name || '')
    setNodeType(node?.node_type || 'department')
  }, [open, node])

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit Node' : 'Add Node'}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Name</Label>
            <Input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && name.trim()) onSave(name.trim(), nodeType) }}
            />
          </div>
          <div className="grid gap-2">
            <Label>Type</Label>
            <Select value={nodeType} onValueChange={setNodeType}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="department">Department</SelectItem>
                <SelectItem value="role">Role</SelectItem>
                <SelectItem value="team">Team</SelectItem>
                {nodeType === 'unallocated' && <SelectItem value="unallocated">Nealocat</SelectItem>}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={!name.trim() || isPending} onClick={() => onSave(name.trim(), nodeType)}>
            {isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/* ──── Move-node dialog (re-parent) ──── */

function MoveNodeDialog({
  node,
  allNodes,
  onClose,
  onMove,
  isPending,
}: {
  node: TreeNode | null
  allNodes: SincronOrgNode[]
  onClose: () => void
  onMove: (parentId: number | null) => void
  isPending: boolean
}) {
  const [parentId, setParentId] = useState<string>('root')

  useEffect(() => {
    if (node) setParentId(node.parent_id != null ? String(node.parent_id) : 'root')
  }, [node])

  // Eligible parents: same company, not the node itself or a descendant, and
  // deep enough to fit the moved subtree within the 6-level cap.
  const eligible = useMemo<SincronOrgNode[]>(() => {
    if (!node) return []
    const companyNodes = allNodes.filter((n) => n.company_id === node.company_id)
    const childrenOf = new Map<number, SincronOrgNode[]>()
    for (const n of companyNodes) {
      if (n.parent_id != null) {
        const list = childrenOf.get(n.parent_id) || []
        list.push(n)
        childrenOf.set(n.parent_id, list)
      }
    }
    const descendants = new Set<number>()
    const collect = (id: number) => {
      for (const k of childrenOf.get(id) || []) { descendants.add(k.id); collect(k.id) }
    }
    collect(node.id)
    const heightOf = (id: number): number => {
      const kids = childrenOf.get(id) || []
      return kids.length ? 1 + Math.max(...kids.map((k) => heightOf(k.id))) : 1
    }
    const height = heightOf(node.id)
    return companyNodes.filter(
      (n) => n.id !== node.id && !descendants.has(n.id) && n.level + height <= 6,
    )
  }, [node, allNodes])

  if (!node) return null

  const nodeById = new Map(allNodes.map((n) => [n.id, n]))
  const pathLabel = (n: SincronOrgNode): string => {
    const parts: string[] = [n.name]
    let cur = n.parent_id != null ? nodeById.get(n.parent_id) : undefined
    while (cur) {
      parts.unshift(cur.name)
      cur = cur.parent_id != null ? nodeById.get(cur.parent_id) : undefined
    }
    return parts.join(' › ')
  }

  const current = node.parent_id != null ? String(node.parent_id) : 'root'

  return (
    <Dialog open={!!node} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Mută „{node.name}" sub…</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3 py-2">
          <Label className="text-xs text-muted-foreground font-normal">
            Alege noul părinte. Mutarea sub un departament curăță marcajul „Nealocat".
          </Label>
          <Select value={parentId} onValueChange={setParentId}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="root">— Rădăcină (L1) —</SelectItem>
              {eligible.map((n) => (
                <SelectItem key={n.id} value={String(n.id)}>
                  {pathLabel(n)} (L{n.level})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Anulează</Button>
          <Button
            disabled={isPending || parentId === current}
            onClick={() => onMove(parentId === 'root' ? null : Number(parentId))}
          >
            {isPending ? 'Se mută…' : 'Mută'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
