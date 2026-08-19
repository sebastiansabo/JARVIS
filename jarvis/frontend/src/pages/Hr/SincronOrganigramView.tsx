import { useState, useMemo, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Building2, Users, User, Link2, Unlink, Layers, Crown, UserX } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/shared/EmptyState'
import { cn } from '@/lib/utils'
import { organizationApi, type SincronOrgCompany, type SincronOrgTreeNode, type SincronOrgEmployee } from '@/api/organization'

/** Title-case a company name */
function titleCase(name: string): string {
  return name.replace(/\S+/g, (w) =>
    /^s\.r\.l\.?$/i.test(w) ? 'S.R.L.' : w.charAt(0).toUpperCase() + w.slice(1).toLowerCase(),
  )
}

/* ──── Level colors (mirror the editor) ──── */

const levelColors = [
  'text-amber-600 dark:text-amber-400',
  'text-green-600 dark:text-green-400',
  'text-blue-600 dark:text-blue-400',
  'text-purple-600 dark:text-purple-400',
  'text-pink-600 dark:text-pink-400',
  'text-rose-600 dark:text-rose-400',
]

/* ──── Search helpers ──── */

function employeeMatches(e: SincronOrgEmployee, q: string): boolean {
  return (
    `${e.nume} ${e.prenume}`.toLowerCase().includes(q) ||
    (e.mapped_user_name?.toLowerCase().includes(q) ?? false)
  )
}

/** Filter a node subtree by query; returns null if nothing matches. A node-name
 *  match keeps the whole subtree, otherwise members/children are filtered. */
function filterNode(node: SincronOrgTreeNode, q: string): SincronOrgTreeNode | null {
  if (node.name.toLowerCase().includes(q)) return node
  const responsables = node.responsables.filter((e) => employeeMatches(e, q))
  const members = node.members.filter((e) => employeeMatches(e, q))
  const children = node.children
    .map((c) => filterNode(c, q))
    .filter((c): c is SincronOrgTreeNode => c !== null)
  if (responsables.length || members.length || children.length) {
    return { ...node, responsables, members, children }
  }
  return null
}

/** Collect expand-keys for every node in a subtree (used to open matches on search). */
function collectNodeKeys(nodes: SincronOrgTreeNode[], acc: string[]): void {
  for (const n of nodes) {
    acc.push(`n-${n.id}`)
    collectNodeKeys(n.children, acc)
  }
}

export default function SincronOrganigramView({ search = '' }: { search?: string }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const { data, isLoading } = useQuery({
    queryKey: ['organigram', 'sincron'],
    queryFn: organizationApi.getSincronOrganigram,
  })

  const companies = data?.data ?? []

  // Auto-expand companies on first load
  useEffect(() => {
    if (companies.length > 0 && expanded.size === 0) {
      setExpanded(new Set(companies.map((c) => `c-${c.company_name}`)))
    }
  }, [companies.length])

  const q = search.trim().toLowerCase()

  const filtered = useMemo(() => {
    if (!q) return companies
    return companies
      .map((company) => {
        if (company.company_name.toLowerCase().includes(q)) return company
        const nodes = company.nodes
          .map((n) => filterNode(n, q))
          .filter((n): n is SincronOrgTreeNode => n !== null)
        const unassigned = company.unassigned.filter((e) => employeeMatches(e, q))
        if (nodes.length || unassigned.length) return { ...company, nodes, unassigned }
        return null
      })
      .filter((c): c is SincronOrgCompany => c !== null)
  }, [companies, q])

  // While searching, force-open every matching company + node so hits are visible.
  const effectiveExpanded = useMemo(() => {
    if (!q) return expanded
    const keys: string[] = []
    for (const c of filtered) {
      keys.push(`c-${c.company_name}`, `u-${c.company_name}`)
      collectNodeKeys(c.nodes, keys)
    }
    return new Set(keys)
  }, [q, filtered, expanded])

  const toggle = (key: string) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  if (isLoading) return <Skeleton className="h-64 w-full" />

  if (!companies.length) {
    return <EmptyState title="No Sincron data" description="No active Sincron employees found." />
  }

  const totalEmps = data?.total_employees ?? 0
  const totalComps = data?.total_companies ?? 0

  return (
    <div className="space-y-3">
      {filtered.map((company) => {
        const companyKey = `c-${company.company_name}`
        const isCompanyExpanded = effectiveExpanded.has(companyKey)

        return (
          <Card key={company.company_name} className="overflow-hidden">
            {/* Company header */}
            <button
              onClick={() => toggle(companyKey)}
              className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-muted/50 transition-colors"
            >
              {isCompanyExpanded ? (
                <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
              ) : (
                <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
              )}
              <Building2 className="h-5 w-5 text-amber-600 shrink-0" />
              <span className="font-semibold text-sm">{titleCase(company.company_name)}</span>
              <span className="text-[10px] text-muted-foreground">L0</span>
              <div className="ml-auto flex items-center gap-2">
                <Badge variant="outline" className="text-xs">
                  {company.mapped_count}/{company.count} mapped
                </Badge>
                <Badge variant="secondary" className="text-xs">
                  {company.count}
                </Badge>
              </div>
            </button>

            {/* Node tree + Neatribuit bucket */}
            {isCompanyExpanded && (
              <div className="border-t">
                {company.nodes.length === 0 && company.unassigned.length === 0 ? (
                  <div className="px-4 py-6 text-center text-sm text-muted-foreground">
                    No org structure yet — build it in edit mode.
                  </div>
                ) : (
                  <>
                    {company.nodes.map((node) => (
                      <NodeRow
                        key={node.id}
                        node={node}
                        depth={0}
                        expanded={effectiveExpanded}
                        toggle={toggle}
                      />
                    ))}
                    {company.unassigned.length > 0 && (
                      <UnassignedRow
                        companyName={company.company_name}
                        employees={company.unassigned}
                        expanded={effectiveExpanded}
                        toggle={toggle}
                      />
                    )}
                  </>
                )}
              </div>
            )}
          </Card>
        )
      })}

      <p className="text-xs text-muted-foreground pt-1">
        {totalComps} companies, {totalEmps} employees
      </p>
    </div>
  )
}

/* ──── Recursive node row (read-only) ──── */

function NodeRow({
  node,
  depth,
  expanded,
  toggle,
}: {
  node: SincronOrgTreeNode
  depth: number
  expanded: Set<string>
  toggle: (key: string) => void
}) {
  const nodeKey = `n-${node.id}`
  const isExpanded = expanded.has(nodeKey)
  const levelIdx = Math.min(node.level - 1, 5)
  const indent = 24 + depth * 20
  const hasContent = node.children.length > 0 || node.responsables.length > 0 || node.members.length > 0

  return (
    <>
      <button
        onClick={() => hasContent && toggle(nodeKey)}
        className={cn(
          'flex w-full items-center gap-1.5 py-2 pr-4 text-left border-b border-muted/20 transition-colors',
          hasContent && 'hover:bg-muted/30',
        )}
        style={{ paddingLeft: `${indent}px` }}
      >
        {hasContent ? (
          isExpanded ? (
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          )
        ) : (
          <span className="h-3.5 w-3.5 shrink-0" />
        )}
        <Layers className={cn('h-3.5 w-3.5 shrink-0', levelColors[levelIdx])} />
        <span className={cn('text-sm font-medium', levelColors[levelIdx])}>{node.name}</span>
        <span className="text-[10px] text-muted-foreground">L{node.level}</span>
        {node.node_type === 'unallocated' && (
          <Badge
            variant="outline"
            className="text-[10px] px-1 py-0 h-4 border-amber-400 bg-amber-50 text-amber-700 dark:border-amber-500/50 dark:bg-amber-950/40 dark:text-amber-300"
            title="Nealocat — fără responsabil sau loc în ierarhie"
          >
            Nealocat
          </Badge>
        )}

        {!isExpanded && node.responsables.length > 0 && (
          <span className="inline-flex items-center gap-0.5 text-[10px] text-amber-600 dark:text-amber-400 ml-1">
            <Crown className="h-3 w-3" />
            {node.responsables.map((r) => `${titleCase(r.nume)} ${titleCase(r.prenume)}`).join(', ')}
          </span>
        )}
        {node.members.length > 0 && (
          <Badge variant="secondary" className="text-[10px] px-1 py-0 h-4 ml-auto">
            <Users className="h-2.5 w-2.5 mr-0.5" />
            {node.members.length}
          </Badge>
        )}
      </button>

      {isExpanded && (
        <>
          {node.responsables.map((e) => (
            <EmployeeRow key={`r-${e.sincron_employee_id}`} emp={e} indent={indent + 24} responsable />
          ))}
          {node.members.map((e) => (
            <EmployeeRow key={`m-${e.sincron_employee_id}`} emp={e} indent={indent + 24} />
          ))}
          {node.children.map((child) => (
            <NodeRow key={child.id} node={child} depth={depth + 1} expanded={expanded} toggle={toggle} />
          ))}
        </>
      )}
    </>
  )
}

/* ──── 'Neatribuit' bucket ──── */

function UnassignedRow({
  companyName,
  employees,
  expanded,
  toggle,
}: {
  companyName: string
  employees: SincronOrgEmployee[]
  expanded: Set<string>
  toggle: (key: string) => void
}) {
  const key = `u-${companyName}`
  const isExpanded = expanded.has(key)

  return (
    <>
      <button
        onClick={() => toggle(key)}
        className="flex w-full items-center gap-1.5 py-2 pr-4 pl-6 text-left border-b border-muted/20 bg-orange-50/40 dark:bg-orange-950/10 hover:bg-orange-50/60 dark:hover:bg-orange-950/20 transition-colors"
      >
        {isExpanded ? (
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        )}
        <UserX className="h-3.5 w-3.5 shrink-0 text-orange-500" />
        <span className="text-sm font-medium text-orange-600 dark:text-orange-400">Neatribuit</span>
        <Badge variant="secondary" className="text-[10px] px-1 py-0 h-4 ml-auto">
          {employees.length}
        </Badge>
      </button>
      {isExpanded &&
        employees.map((e) => <EmployeeRow key={`u-${e.sincron_employee_id}`} emp={e} indent={48} />)}
    </>
  )
}

/* ──── Employee leaf row ──── */

function EmployeeRow({
  emp,
  indent,
  responsable = false,
}: {
  emp: SincronOrgEmployee
  indent: number
  responsable?: boolean
}) {
  return (
    <div
      className="flex items-center gap-3 pr-4 py-1.5 text-sm hover:bg-muted/30 transition-colors border-b border-muted/10"
      style={{ paddingLeft: `${indent}px` }}
    >
      {responsable ? (
        <Crown className="h-3.5 w-3.5 text-amber-500 shrink-0" />
      ) : (
        <User className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
      )}
      <span className="font-medium">
        {titleCase(emp.nume)} {titleCase(emp.prenume)}
      </span>
      {emp.norma_lucru != null && (
        <span className="text-xs text-muted-foreground">{emp.norma_lucru}h</span>
      )}
      {emp.nr_contract && <span className="text-xs text-muted-foreground">#{emp.nr_contract}</span>}
      <div className="ml-auto flex items-center gap-1.5">
        {emp.mapped_user_name ? (
          <>
            <Link2 className="h-3 w-3 text-green-600" />
            <span className="text-xs text-muted-foreground">{emp.mapped_user_name}</span>
          </>
        ) : (
          <>
            <Unlink className="h-3 w-3 text-orange-500" />
            <span className="text-xs text-orange-500">Unmapped</span>
          </>
        )}
      </div>
    </div>
  )
}
