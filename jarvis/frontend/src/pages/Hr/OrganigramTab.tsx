import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Search,
  ChevronDown,
  ChevronRight,
  Building2,
  Crown,
  Users,
  Layers,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/shared/EmptyState'
import { MultiSelectPills } from '@/components/shared/MultiSelectPills'
import { organizationApi } from '@/api/organization'
import { usersApi } from '@/api/users'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import type { CompanyWithBrands, StructureNode, StructureNodeMember } from '@/types/organization'

/* ──── Tree helpers ──── */

interface TreeNode extends StructureNode {
  children: TreeNode[]
}

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

function flattenCompanyTree(nodes: CompanyTreeNode[]): CompanyTreeNode[] {
  const result: CompanyTreeNode[] = []
  function walk(list: CompanyTreeNode[]) {
    for (const n of list) { result.push(n); walk(n.children) }
  }
  walk(nodes)
  return result
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

/* ──── Level colors ──── */

const levelColors = [
  'text-amber-600 dark:text-amber-400',
  'text-green-600 dark:text-green-400',
  'text-blue-600 dark:text-blue-400',
  'text-purple-600 dark:text-purple-400',
  'text-pink-600 dark:text-pink-400',
]

const levelBg = [
  'bg-amber-50/40 dark:bg-amber-950/15',
  'bg-green-50/30 dark:bg-green-950/10',
  'bg-blue-50/25 dark:bg-blue-950/10',
  'bg-purple-50/20 dark:bg-purple-950/10',
  'bg-pink-50/15 dark:bg-pink-950/10',
]

/* ──── Main component ──── */

export default function OrganigramTab() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set())

  const { data: companies = [], isLoading: loadingCompanies } = useQuery({
    queryKey: ['settings', 'companiesConfig'],
    queryFn: organizationApi.getCompaniesConfig,
  })

  const { data: structureNodes = [], isLoading: loadingNodes } = useQuery({
    queryKey: ['settings', 'structureNodes'],
    queryFn: organizationApi.getStructureNodes,
  })

  const { data: allMembers = [], isLoading: loadingMembers } = useQuery({
    queryKey: ['settings', 'nodeMembers'],
    queryFn: organizationApi.getNodeMembers,
  })

  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: usersApi.getUsers,
  })

  const isLoading = loadingCompanies || loadingNodes || loadingMembers

  // Build lookup maps
  const companyTree = useMemo(() => buildCompanyTree(companies), [companies])
  const flatCompanies = useMemo(() => flattenCompanyTree(companyTree), [companyTree])
  const nodeTreeByCompany = useMemo(() => buildNodeTree(structureNodes), [structureNodes])

  const membersByNode = useMemo(() => {
    const map = new Map<number, { responsables: StructureNodeMember[]; team: StructureNodeMember[] }>()
    for (const m of allMembers) {
      if (!map.has(m.node_id)) map.set(m.node_id, { responsables: [], team: [] })
      const entry = map.get(m.node_id)!
      if (m.role === 'responsable') entry.responsables.push(m)
      else entry.team.push(m)
    }
    return map
  }, [allMembers])

  const userOptions = useMemo(
    () => users.filter(u => u.is_active).map(u => ({ value: u.id, label: u.name })),
    [users],
  )

  // Mutations
  const setMembersMut = useMutation({
    mutationFn: ({ nodeId, role, userIds }: { nodeId: number; role: 'responsable' | 'team'; userIds: number[] }) =>
      organizationApi.setNodeMembers(nodeId, role, userIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'nodeMembers'] })
    },
    onError: () => toast.error('Failed to update members'),
  })

  const toggleTeamMut = useMutation({
    mutationFn: ({ nodeId, hasTeam }: { nodeId: number; hasTeam: boolean }) =>
      organizationApi.updateStructureNode(nodeId, { has_team: hasTeam }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'structureNodes'] })
    },
    onError: () => toast.error('Failed to toggle team'),
  })

  const handleSetMembers = (nodeId: number, role: 'responsable' | 'team', userIds: number[]) => {
    setMembersMut.mutate({ nodeId, role, userIds })
  }

  const handleToggleTeam = (nodeId: number, hasTeam: boolean) => {
    toggleTeamMut.mutate({ nodeId, hasTeam })
  }

  // Auto-expand on first load
  useMemo(() => {
    if (flatCompanies.length > 0 && expandedNodes.size === 0) {
      const keys = new Set<string>()
      for (const c of flatCompanies) keys.add(`c-${c.id}`)
      function collectNodeKeys(nodes: TreeNode[]) {
        for (const n of nodes) {
          keys.add(`n-${n.id}`)
          collectNodeKeys(n.children)
        }
      }
      for (const [, nodes] of nodeTreeByCompany) collectNodeKeys(nodes)
      setExpandedNodes(keys)
    }
  }, [flatCompanies, nodeTreeByCompany])

  const toggleExpand = (key: string) => {
    setExpandedNodes(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  // Count all members (recursively) for a node tree
  function countNodeMembers(nodes: TreeNode[]): number {
    let count = 0
    for (const n of nodes) {
      const m = membersByNode.get(n.id)
      if (m) count += m.responsables.length + m.team.length
      count += countNodeMembers(n.children)
    }
    return count
  }

  // Search filter
  const filteredCompanies = useMemo(() => {
    if (!search.trim()) return flatCompanies
    const q = search.toLowerCase()

    // Find matching node IDs + their ancestor companies
    const matchingCompanyIds = new Set<number>()

    for (const c of flatCompanies) {
      if (c.company.toLowerCase().includes(q)) {
        matchingCompanyIds.add(c.id)
        continue
      }
      // Check nodes under this company
      const nodes = nodeTreeByCompany.get(c.id) || []
      function checkNodes(list: TreeNode[]): boolean {
        for (const n of list) {
          if (n.name.toLowerCase().includes(q)) return true
          const m = membersByNode.get(n.id)
          if (m) {
            const allM = [...m.responsables, ...m.team]
            if (allM.some(mem => mem.user_name.toLowerCase().includes(q))) return true
          }
          if (checkNodes(n.children)) return true
        }
        return false
      }
      if (checkNodes(nodes)) matchingCompanyIds.add(c.id)
    }

    return flatCompanies.filter(c => matchingCompanyIds.has(c.id))
  }, [flatCompanies, search, nodeTreeByCompany, membersByNode])

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-10 w-full max-w-sm" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Search */}
      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search by name, node, company..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-9"
        />
      </div>

      {filteredCompanies.length === 0 ? (
        <EmptyState
          icon={<Users className="h-10 w-10" />}
          title="No results"
          description={search ? 'Try a different search term' : 'No organizational structure found. Set up the structure in Settings first.'}
        />
      ) : (
        <div className="space-y-3">
          {filteredCompanies.map((company) => {
            const companyKey = `c-${company.id}`
            const isExpanded = expandedNodes.has(companyKey)
            const companyNodes = nodeTreeByCompany.get(company.id) || []
            const totalMembers = countNodeMembers(companyNodes)

            return (
              <Card key={company.id} className="overflow-hidden">
                {/* Company header */}
                <button
                  onClick={() => toggleExpand(companyKey)}
                  className={cn(
                    'flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-muted/50 transition-colors',
                    company.depth > 0 && 'pl-8',
                  )}
                >
                  {isExpanded
                    ? <ChevronDown className="h-4 w-4 shrink-0" />
                    : <ChevronRight className="h-4 w-4 shrink-0" />
                  }
                  <Building2 className="h-5 w-5 shrink-0 text-primary" />
                  <span className="font-semibold text-sm">{company.company}</span>
                  <span className="text-[10px] text-muted-foreground">L0</span>
                  {company.children?.length > 0 && (
                    <Badge className="text-[10px] px-1.5 py-0">Holding</Badge>
                  )}
                  <Badge variant="secondary" className="ml-auto text-xs">
                    {totalMembers} {totalMembers === 1 ? 'person' : 'people'}
                  </Badge>
                </button>

                {/* Structure nodes */}
                {isExpanded && (
                  <div className="border-t">
                    {companyNodes.length === 0 ? (
                      <p className="px-6 py-4 text-sm text-muted-foreground italic">
                        No structure defined. Add levels in Settings &rarr; Structure.
                      </p>
                    ) : (
                      companyNodes.map(node => (
                        <NodeRow
                          key={node.id}
                          node={node}
                          depth={0}
                          expandedNodes={expandedNodes}
                          toggleExpand={toggleExpand}
                          membersByNode={membersByNode}
                          userOptions={userOptions}
                          onSetMembers={handleSetMembers}
                          onToggleTeam={handleToggleTeam}
                        />
                      ))
                    )}
                  </div>
                )}
              </Card>
            )
          })}
        </div>
      )}

      {/* Summary */}
      <div className="flex gap-4 text-xs text-muted-foreground pt-2">
        <span>{companies.length} companies</span>
        <span>{structureNodes.length} nodes</span>
        <span>{allMembers.length} assignments</span>
      </div>
    </div>
  )
}

/* ──── Recursive node row ──── */

function NodeRow({
  node,
  depth,
  expandedNodes,
  toggleExpand,
  membersByNode,
  userOptions,
  onSetMembers,
  onToggleTeam,
}: {
  node: TreeNode
  depth: number
  expandedNodes: Set<string>
  toggleExpand: (key: string) => void
  membersByNode: Map<number, { responsables: StructureNodeMember[]; team: StructureNodeMember[] }>
  userOptions: { value: number; label: string }[]
  onSetMembers: (nodeId: number, role: 'responsable' | 'team', userIds: number[]) => void
  onToggleTeam: (nodeId: number, hasTeam: boolean) => void
}) {
  const nodeKey = `n-${node.id}`
  const isExpanded = expandedNodes.has(nodeKey)
  const levelIdx = Math.min(node.level - 1, 4)
  const indent = 24 + depth * 20
  const members = membersByNode.get(node.id) || { responsables: [], team: [] }
  const memberCount = members.responsables.length + members.team.length

  return (
    <>
      {/* Node header row */}
      <button
        onClick={() => toggleExpand(nodeKey)}
        className={cn(
          'flex w-full items-center gap-2 py-2.5 pr-4 text-left hover:bg-muted/30 transition-colors border-t border-muted/30',
          levelBg[levelIdx],
        )}
        style={{ paddingLeft: `${indent}px` }}
      >
        {isExpanded
          ? <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          : <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        }
        <Layers className={cn('h-3.5 w-3.5 shrink-0', levelColors[levelIdx])} />
        <span className={cn('text-sm font-medium', levelColors[levelIdx])}>{node.name}</span>
        <span className="text-[10px] text-muted-foreground">L{node.level}</span>

        {/* Collapsed member counts */}
        {!isExpanded && members.responsables.length > 0 && (
          <span className="inline-flex items-center gap-0.5 text-[10px] text-amber-600 dark:text-amber-400">
            <Crown className="h-3 w-3" />
            {members.responsables.length}
          </span>
        )}
        {!isExpanded && members.team.length > 0 && (
          <span className="inline-flex items-center gap-0.5 text-[10px] text-blue-600 dark:text-blue-400">
            <Users className="h-3 w-3" />
            {members.team.length}
          </span>
        )}

        <Badge variant="outline" className="ml-auto text-[10px]">{memberCount}</Badge>
      </button>

      {/* Expanded: member management */}
      {isExpanded && (
        <div
          className={cn('border-t border-muted/20 py-3 pr-4 space-y-3', levelBg[levelIdx])}
          style={{ paddingLeft: `${indent + 24}px` }}
          onClick={e => e.stopPropagation()}
        >
          {/* Responsables */}
          <div className="space-y-1">
            <div className="flex items-center gap-1.5">
              <Crown className="h-3.5 w-3.5 text-amber-500" />
              <span className="text-xs font-medium text-muted-foreground">Responsables</span>
            </div>
            <MultiSelectPills
              options={userOptions}
              selected={members.responsables.map(m => m.user_id)}
              onChange={(ids) => onSetMembers(node.id, 'responsable', ids as number[])}
              placeholder="Add responsables..."
              className="max-w-md"
            />
          </div>

          {/* Has team toggle */}
          <div className="flex items-center gap-2">
            <Switch
              size="sm"
              checked={node.has_team}
              onCheckedChange={(checked) => onToggleTeam(node.id, checked)}
            />
            <span className="text-xs text-muted-foreground">Has team</span>
          </div>

          {/* Team members (only if has_team) */}
          {node.has_team && (
            <div className="space-y-1">
              <div className="flex items-center gap-1.5">
                <Users className="h-3.5 w-3.5 text-blue-500" />
                <span className="text-xs font-medium text-muted-foreground">Team</span>
              </div>
              <MultiSelectPills
                options={userOptions}
                selected={members.team.map(m => m.user_id)}
                onChange={(ids) => onSetMembers(node.id, 'team', ids as number[])}
                placeholder="Add team members..."
                className="max-w-md"
              />
            </div>
          )}
        </div>
      )}

      {/* Recursive children */}
      {isExpanded && node.children.map(child => (
        <NodeRow
          key={child.id}
          node={child}
          depth={depth + 1}
          expandedNodes={expandedNodes}
          toggleExpand={toggleExpand}
          membersByNode={membersByNode}
          userOptions={userOptions}
          onSetMembers={onSetMembers}
          onToggleTeam={onToggleTeam}
        />
      ))}
    </>
  )
}
