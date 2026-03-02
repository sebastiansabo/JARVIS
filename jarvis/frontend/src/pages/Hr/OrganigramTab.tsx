import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Search,
  ChevronDown,
  ChevronRight,
  Building2,
  FolderTree,
  Crown,
  User,
  Users,
  UserPlus,
  Mail,
  Phone,
  Pencil,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { hrApi } from '@/api/hr'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
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

function parseManagerIds(raw: string | number[] | null): number[] {
  if (!raw) return []
  if (Array.isArray(raw)) return raw
  return raw.replace(/[{}]/g, '').split(',').map(Number).filter(Boolean)
}

function buildTree(employees: HrEmployee[], structures: DepartmentStructure[]): OrgNode[] {
  const structureMap = new Map<string, DepartmentStructure>()

  for (const s of structures) {
    const key = `${s.company}|||${s.department}|||${s.subdepartment || ''}`
    structureMap.set(key, s)
  }

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

  const tree: OrgNode[] = []

  for (const [company, deptMap] of [...companyMap.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
    const departments: DeptNode[] = []
    let companyTotal = 0

    for (const [deptKey, emps] of [...deptMap.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
      const [department, subdepartment] = deptKey.split('|||')
      const structKey = `${company}|||${department}|||${subdepartment}`
      const structure = structureMap.get(structKey)

      const mgrSet = new Set(parseManagerIds(structure?.manager_ids ?? null))

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
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [expandedCompanies, setExpandedCompanies] = useState<Set<string>>(new Set())
  const [expandedDepts, setExpandedDepts] = useState<Set<string>>(new Set())
  const [assignDialog, setAssignDialog] = useState<{ company: string; department: string; subdepartment: string | null } | null>(null)
  const [editDialog, setEditDialog] = useState<HrEmployee | null>(null)

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

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['hr-organigram'] })
    queryClient.invalidateQueries({ queryKey: ['hr-employees'] })
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
                          <div className="flex items-center">
                            <button
                              onClick={() => toggleDept(deptKey)}
                              className="flex flex-1 items-center gap-3 py-2.5 pl-10 pr-2 text-left hover:bg-muted/30 transition-colors"
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
                            <Button
                              variant="ghost"
                              size="icon"
                              className="mr-2 h-7 w-7 shrink-0"
                              title="Add employee to this department"
                              onClick={(e) => {
                                e.stopPropagation()
                                setAssignDialog({ company: company.company, department: dept.department, subdepartment: dept.subdepartment })
                              }}
                            >
                              <UserPlus className="h-3.5 w-3.5" />
                            </Button>
                          </div>

                          {isDeptExpanded && (
                            <div className="pb-2 pl-16 pr-4 space-y-0.5">
                              {dept.managers.map((mgr) => (
                                <EmployeeRow key={mgr.id} employee={mgr} isManager onEdit={() => setEditDialog(mgr)} />
                              ))}
                              {dept.employees.map((emp) => (
                                <EmployeeRow key={emp.id} employee={emp} onEdit={() => setEditDialog(emp)} />
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

      {/* Assign Employee Dialog */}
      {assignDialog && data && (
        <AssignEmployeeDialog
          open
          onClose={() => setAssignDialog(null)}
          target={assignDialog}
          allEmployees={data.employees}
          onSuccess={invalidate}
        />
      )}

      {/* Edit Employee Assignment Dialog */}
      {editDialog && data && (
        <EditAssignmentDialog
          open
          onClose={() => setEditDialog(null)}
          employee={editDialog}
          structures={data.structures}
          onSuccess={invalidate}
        />
      )}
    </div>
  )
}

function EmployeeRow({ employee, isManager = false, onEdit }: { employee: HrEmployee; isManager?: boolean; onEdit: () => void }) {
  return (
    <div
      className={cn(
        'group flex items-center gap-2.5 rounded-md px-3 py-1.5 text-sm transition-colors hover:bg-muted/40',
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
      <button
        onClick={onEdit}
        className="ml-1 opacity-0 group-hover:opacity-100 transition-opacity"
        title="Edit assignment"
      >
        <Pencil className="h-3 w-3 text-muted-foreground hover:text-foreground" />
      </button>
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

/* ──── Assign Employee to Department Dialog ──── */

function AssignEmployeeDialog({
  open,
  onClose,
  target,
  allEmployees,
  onSuccess,
}: {
  open: boolean
  onClose: () => void
  target: { company: string; department: string; subdepartment: string | null }
  allEmployees: HrEmployee[]
  onSuccess: () => void
}) {
  const [selectedId, setSelectedId] = useState<string>('')
  const [empSearch, setEmpSearch] = useState('')

  const updateMutation = useMutation({
    mutationFn: (emp: HrEmployee) =>
      hrApi.updateEmployee(emp.id, {
        ...emp,
        company: target.company,
        departments: target.department,
        subdepartment: target.subdepartment,
      }),
    onSuccess: () => {
      toast.success('Employee assigned')
      onSuccess()
      onClose()
    },
    onError: () => toast.error('Failed to assign employee'),
  })

  const filteredEmployees = useMemo(() => {
    if (!empSearch.trim()) return allEmployees
    const q = empSearch.toLowerCase()
    return allEmployees.filter(
      (e) => e.name.toLowerCase().includes(q) || (e.email?.toLowerCase().includes(q))
    )
  }, [allEmployees, empSearch])

  const handleAssign = () => {
    const emp = allEmployees.find((e) => String(e.id) === selectedId)
    if (emp) updateMutation.mutate(emp)
  }

  return (
    <Dialog open={open} onOpenChange={() => onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Add Employee to {target.department}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 pt-2">
          <p className="text-xs text-muted-foreground">
            Assign to: <strong>{target.company}</strong> / <strong>{target.department}</strong>
            {target.subdepartment && <> / {target.subdepartment}</>}
          </p>
          <div>
            <Label className="text-xs">Search employee</Label>
            <Input
              placeholder="Type name or email..."
              value={empSearch}
              onChange={(e) => setEmpSearch(e.target.value)}
              className="mt-1"
            />
          </div>
          <div>
            <Label className="text-xs">Select employee</Label>
            <Select value={selectedId} onValueChange={setSelectedId}>
              <SelectTrigger className="mt-1">
                <SelectValue placeholder="Choose employee..." />
              </SelectTrigger>
              <SelectContent className="max-h-60">
                {filteredEmployees.map((e) => (
                  <SelectItem key={e.id} value={String(e.id)}>
                    {e.name} {e.company && e.departments ? `(${e.company} / ${e.departments})` : e.company ? `(${e.company})` : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
            <Button size="sm" disabled={!selectedId || updateMutation.isPending} onClick={handleAssign}>
              {updateMutation.isPending ? 'Assigning...' : 'Assign'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

/* ──── Edit Employee Assignment Dialog ──── */

function EditAssignmentDialog({
  open,
  onClose,
  employee,
  structures,
  onSuccess,
}: {
  open: boolean
  onClose: () => void
  employee: HrEmployee
  structures: DepartmentStructure[]
  onSuccess: () => void
}) {
  const [company, setCompany] = useState(employee.company || '')
  const [department, setDepartment] = useState(employee.departments || '')
  const [subdepartment, setSubdepartment] = useState(employee.subdepartment || '')

  const companies = useMemo(() => [...new Set(structures.map((s) => s.company))].sort(), [structures])
  const departments = useMemo(() =>
    [...new Set(structures.filter((s) => s.company === company).map((s) => s.department))].sort(),
    [structures, company]
  )
  const subdepartments = useMemo(() =>
    [...new Set(structures.filter((s) => s.company === company && s.department === department && s.subdepartment).map((s) => s.subdepartment))].sort(),
    [structures, company, department]
  )

  const updateMutation = useMutation({
    mutationFn: () =>
      hrApi.updateEmployee(employee.id, {
        ...employee,
        company: company || null,
        departments: department || null,
        subdepartment: subdepartment || null,
      }),
    onSuccess: () => {
      toast.success('Assignment updated')
      onSuccess()
      onClose()
    },
    onError: () => toast.error('Failed to update'),
  })

  return (
    <Dialog open={open} onOpenChange={() => onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Edit Assignment — {employee.name}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 pt-2">
          <div>
            <Label className="text-xs">Company</Label>
            <Select value={company} onValueChange={(v) => { setCompany(v); setDepartment(''); setSubdepartment('') }}>
              <SelectTrigger className="mt-1"><SelectValue placeholder="Select company" /></SelectTrigger>
              <SelectContent>
                {companies.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs">Department</Label>
            <Select value={department} onValueChange={(v) => { setDepartment(v); setSubdepartment('') }}>
              <SelectTrigger className="mt-1"><SelectValue placeholder="Select department" /></SelectTrigger>
              <SelectContent>
                {departments.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          {subdepartments.length > 0 && (
            <div>
              <Label className="text-xs">Subdepartment</Label>
              <Select value={subdepartment} onValueChange={setSubdepartment}>
                <SelectTrigger className="mt-1"><SelectValue placeholder="None" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="">None</SelectItem>
                  {subdepartments.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
            <Button size="sm" disabled={updateMutation.isPending} onClick={() => updateMutation.mutate()}>
              {updateMutation.isPending ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
