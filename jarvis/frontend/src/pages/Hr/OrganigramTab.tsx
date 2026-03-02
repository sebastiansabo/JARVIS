import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Search,
  ChevronDown,
  ChevronRight,
  Building2,
  FolderTree,
  Crown,
  User,
  Users,
  Mail,
  Phone,
} from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/shared/EmptyState'
import { hrApi } from '@/api/hr'
import { cn } from '@/lib/utils'
import type { HrEmployee, DepartmentStructure } from '@/types/hr'

interface OrgNode {
  company: string
  departments: DeptNode[]
  employeeCount: number
}

interface DeptNode {
  department: string
  subdepartment: string | null
  managers: HrEmployee[]
  employees: HrEmployee[]
  structureId: number | null
}

function buildTree(employees: HrEmployee[], structures: DepartmentStructure[]): OrgNode[] {
  // Build a set of manager IDs from all structures
  const managerIdSet = new Set<number>()
  const structureMap = new Map<string, DepartmentStructure>()

  for (const s of structures) {
    const key = `${s.company}|||${s.department}|||${s.subdepartment || ''}`
    structureMap.set(key, s)
    if (s.manager_ids) {
      const ids = typeof s.manager_ids === 'string'
        ? s.manager_ids.replace(/[{}]/g, '').split(',').map(Number).filter(Boolean)
        : Array.isArray(s.manager_ids) ? s.manager_ids : []
      ids.forEach((id) => managerIdSet.add(id))
    }
  }

  // Group employees by company → department
  const companyMap = new Map<string, Map<string, HrEmployee[]>>()
  for (const emp of employees) {
    const company = emp.company || 'Unassigned'
    const dept = emp.departments || 'Unassigned'
    if (!companyMap.has(company)) companyMap.set(company, new Map())
    const deptMap = companyMap.get(company)!
    const deptKey = `${dept}|||${emp.subdepartment || ''}`
    if (!deptMap.has(deptKey)) deptMap.set(deptKey, [])
    deptMap.get(deptKey)!.push(emp)
  }

  // Build tree nodes
  const tree: OrgNode[] = []

  for (const [company, deptMap] of [...companyMap.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
    const departments: DeptNode[] = []
    let companyTotal = 0

    for (const [deptKey, emps] of [...deptMap.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
      const [department, subdepartment] = deptKey.split('|||')
      const structKey = `${company}|||${department}|||${subdepartment}`
      const structure = structureMap.get(structKey)

      // Parse manager IDs from structure
      let mgrIds: number[] = []
      if (structure?.manager_ids) {
        mgrIds = typeof structure.manager_ids === 'string'
          ? structure.manager_ids.replace(/[{}]/g, '').split(',').map(Number).filter(Boolean)
          : Array.isArray(structure.manager_ids) ? structure.manager_ids : []
      }
      const mgrSet = new Set(mgrIds)

      const managers = emps.filter((e) => mgrSet.has(e.id))
      const nonManagers = emps.filter((e) => !mgrSet.has(e.id))

      departments.push({
        department,
        subdepartment: subdepartment || null,
        managers,
        employees: nonManagers,
        structureId: structure?.id ?? null,
      })
      companyTotal += emps.length
    }

    tree.push({ company, departments, employeeCount: companyTotal })
  }

  return tree
}

export default function OrganigramTab() {
  const [search, setSearch] = useState('')
  const [expandedCompanies, setExpandedCompanies] = useState<Set<string>>(new Set())
  const [expandedDepts, setExpandedDepts] = useState<Set<string>>(new Set())

  const { data, isLoading } = useQuery({
    queryKey: ['hr-organigram'],
    queryFn: () => hrApi.getOrganigram(),
    staleTime: 2 * 60 * 1000,
  })

  const tree = useMemo(() => {
    if (!data) return []
    return buildTree(data.employees, data.structures)
  }, [data])

  // Auto-expand all on first load
  useMemo(() => {
    if (tree.length > 0 && expandedCompanies.size === 0) {
      setExpandedCompanies(new Set(tree.map((n) => n.company)))
      const allDepts = new Set<string>()
      tree.forEach((c) => c.departments.forEach((d) => allDepts.add(`${c.company}|||${d.department}|||${d.subdepartment || ''}`)))
      setExpandedDepts(allDepts)
    }
  }, [tree])

  const filtered = useMemo(() => {
    if (!search.trim()) return tree
    const q = search.toLowerCase()

    return tree
      .map((company) => {
        const filteredDepts = company.departments
          .map((dept) => {
            const matchedManagers = dept.managers.filter(
              (e) => e.name.toLowerCase().includes(q) || (e.email?.toLowerCase().includes(q))
            )
            const matchedEmployees = dept.employees.filter(
              (e) => e.name.toLowerCase().includes(q) || (e.email?.toLowerCase().includes(q))
            )
            const deptMatch = dept.department.toLowerCase().includes(q)

            if (deptMatch || matchedManagers.length || matchedEmployees.length) {
              return {
                ...dept,
                managers: deptMatch ? dept.managers : matchedManagers,
                employees: deptMatch ? dept.employees : matchedEmployees,
              }
            }
            return null
          })
          .filter(Boolean) as DeptNode[]

        if (filteredDepts.length > 0 || company.company.toLowerCase().includes(q)) {
          return { ...company, departments: filteredDepts.length > 0 ? filteredDepts : company.departments }
        }
        return null
      })
      .filter(Boolean) as OrgNode[]
  }, [tree, search])

  const toggleCompany = (company: string) => {
    setExpandedCompanies((prev) => {
      const next = new Set(prev)
      if (next.has(company)) next.delete(company)
      else next.add(company)
      return next
    })
  }

  const toggleDept = (key: string) => {
    setExpandedDepts((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

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
          placeholder="Search by name, email, department..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-9"
        />
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          icon={<Users className="h-10 w-10" />}
          title="No results"
          description={search ? 'Try a different search term' : 'No organizational data found. Set up departments and assign employees first.'}
        />
      ) : (
        <div className="space-y-3">
          {filtered.map((company) => {
            const isExpanded = expandedCompanies.has(company.company)
            return (
              <Card key={company.company} className="overflow-hidden">
                {/* Company header */}
                <button
                  onClick={() => toggleCompany(company.company)}
                  className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-muted/50 transition-colors"
                >
                  {isExpanded ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
                  <Building2 className="h-5 w-5 shrink-0 text-primary" />
                  <span className="font-semibold text-sm">{company.company}</span>
                  <Badge variant="secondary" className="ml-auto text-xs">
                    {company.employeeCount} {company.employeeCount === 1 ? 'employee' : 'employees'}
                  </Badge>
                </button>

                {isExpanded && (
                  <div className="border-t">
                    {company.departments.map((dept) => {
                      const deptKey = `${company.company}|||${dept.department}|||${dept.subdepartment || ''}`
                      const isDeptExpanded = expandedDepts.has(deptKey)
                      const totalInDept = dept.managers.length + dept.employees.length

                      return (
                        <div key={deptKey} className="border-b last:border-b-0">
                          {/* Department header */}
                          <button
                            onClick={() => toggleDept(deptKey)}
                            className="flex w-full items-center gap-3 py-2.5 pl-10 pr-4 text-left hover:bg-muted/30 transition-colors"
                          >
                            {isDeptExpanded ? <ChevronDown className="h-3.5 w-3.5 shrink-0" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0" />}
                            <FolderTree className="h-4 w-4 shrink-0 text-orange-500" />
                            <span className="text-sm font-medium">{dept.department}</span>
                            {dept.subdepartment && (
                              <span className="text-xs text-muted-foreground">/ {dept.subdepartment}</span>
                            )}
                            <Badge variant="outline" className="ml-auto text-xs">
                              {totalInDept}
                            </Badge>
                          </button>

                          {isDeptExpanded && (
                            <div className="pb-2 pl-16 pr-4 space-y-0.5">
                              {/* Managers first */}
                              {dept.managers.map((mgr) => (
                                <EmployeeRow key={mgr.id} employee={mgr} isManager />
                              ))}
                              {/* Regular employees */}
                              {dept.employees.map((emp) => (
                                <EmployeeRow key={emp.id} employee={emp} />
                              ))}
                              {totalInDept === 0 && (
                                <p className="py-2 text-xs text-muted-foreground italic">No employees assigned</p>
                              )}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
              </Card>
            )
          })}
        </div>
      )}

      {/* Summary stats */}
      {data && (
        <div className="flex gap-4 text-xs text-muted-foreground pt-2">
          <span>{data.employees.length} total employees</span>
          <span>{tree.length} companies</span>
          <span>{tree.reduce((sum, c) => sum + c.departments.length, 0)} departments</span>
        </div>
      )}
    </div>
  )
}

function EmployeeRow({ employee, isManager = false }: { employee: HrEmployee; isManager?: boolean }) {
  return (
    <div
      className={cn(
        'flex items-center gap-2.5 rounded-md px-3 py-1.5 text-sm transition-colors hover:bg-muted/40',
        isManager && 'bg-amber-50 dark:bg-amber-950/20'
      )}
    >
      {isManager ? (
        <Crown className="h-3.5 w-3.5 shrink-0 text-amber-500" />
      ) : (
        <User className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      )}
      <span className={cn('font-medium', isManager && 'text-amber-700 dark:text-amber-400')}>
        {employee.name}
      </span>
      {isManager && (
        <Badge variant="outline" className="text-[10px] px-1.5 py-0 border-amber-300 text-amber-600 dark:border-amber-700 dark:text-amber-400">
          Manager
        </Badge>
      )}
      {employee.email && (
        <span className="ml-auto hidden md:flex items-center gap-1 text-xs text-muted-foreground">
          <Mail className="h-3 w-3" />
          {employee.email}
        </span>
      )}
      {employee.phone && (
        <span className="hidden lg:flex items-center gap-1 text-xs text-muted-foreground">
          <Phone className="h-3 w-3" />
          {employee.phone}
        </span>
      )}
    </div>
  )
}
