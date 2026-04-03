import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { hrApi } from '@/api/hr'
import { StatCard } from '@/components/shared/StatCard'
import { EmptyState } from '@/components/shared/EmptyState'
import { MobileCardList, type MobileCardField } from '@/components/shared/MobileCardList'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Users, Building2, ArrowUpDown, Briefcase,
} from 'lucide-react'
import type { HrEmployee, StructureCompany } from '@/types/hr'

interface Props {
  search: string
}

type SortField = 'name' | 'company' | 'department'
type SortDir = 'asc' | 'desc'

export default function EmployeesTab({ search }: Props) {
  const navigate = useNavigate()
  const isMobile = useIsMobile()
  const [companyFilter, setCompanyFilter] = useState<string>('all')
  const [sortField, setSortField] = useState<SortField>('name')
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  const { data: employeesData, isLoading: loadingEmployees } = useQuery({
    queryKey: ['hr', 'employees', 'all'],
    queryFn: () => hrApi.getEmployees(true),
  })

  const { data: companiesData } = useQuery({
    queryKey: ['hr', 'companies-full'],
    queryFn: () => hrApi.getCompaniesFull(),
  })

  const employees: HrEmployee[] = employeesData ?? []
  const companies: StructureCompany[] = companiesData ?? []

  // Filter + search + sort
  const filtered = useMemo(() => {
    let rows = employees
    if (companyFilter !== 'all') {
      rows = rows.filter((e) => e.company === companyFilter)
    }
    if (search) {
      const q = search.toLowerCase()
      rows = rows.filter(
        (e) =>
          e.name.toLowerCase().includes(q) ||
          (e.email ?? '').toLowerCase().includes(q) ||
          (e.departments ?? '').toLowerCase().includes(q) ||
          (e.company ?? '').toLowerCase().includes(q),
      )
    }
    rows = [...rows].sort((a, b) => {
      const dir = sortDir === 'asc' ? 1 : -1
      if (sortField === 'name') return a.name.localeCompare(b.name) * dir
      if (sortField === 'company') return (a.company ?? '').localeCompare(b.company ?? '') * dir
      return (a.departments ?? '').localeCompare(b.departments ?? '') * dir
    })
    return rows
  }, [employees, companyFilter, search, sortField, sortDir])

  // Stats
  const stats = useMemo(() => {
    const byCompany = new Map<string, number>()
    employees.forEach((e) => {
      const c = e.company || 'Unknown'
      byCompany.set(c, (byCompany.get(c) ?? 0) + 1)
    })
    return {
      total: employees.length,
      companies: byCompany.size,
      filtered: filtered.length,
    }
  }, [employees, filtered])

  function toggleSort(field: SortField) {
    if (sortField === field) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else {
      setSortField(field)
      setSortDir('asc')
    }
  }

  const mobileFields: MobileCardField<HrEmployee>[] = useMemo(
    () => [
      { key: 'name', label: 'Name', render: (r) => <span className="font-medium">{r.name}</span>, isPrimary: true },
      {
        key: 'company',
        label: 'Company',
        render: (r) => <span className="text-xs text-muted-foreground">{r.company ?? '-'}</span>,
        isSecondary: true,
      },
      { key: 'departments', label: 'Department', render: (r) => <span className="text-xs">{r.departments ?? '-'}</span> },
      { key: 'brand', label: 'Brand', render: (r) => <span className="text-xs">{r.brand ?? '-'}</span> },
      {
        key: 'email',
        label: 'Email',
        render: (r) => <span className="text-xs text-muted-foreground">{r.email ?? '-'}</span>,
        expandOnly: true,
      },
      {
        key: 'phone',
        label: 'Phone',
        render: (r) => <span className="text-xs text-muted-foreground">{r.phone ?? '-'}</span>,
        expandOnly: true,
      },
    ],
    [],
  )

  if (loadingEmployees) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
        <Skeleton className="h-96 w-full" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Company filter */}
      <div className="flex items-center gap-2">
        <Select value={companyFilter} onValueChange={setCompanyFilter}>
          <SelectTrigger className="h-8 w-56 text-xs">
            <SelectValue placeholder="All Companies" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Companies</SelectItem>
            {companies.map((c) => (
              <SelectItem key={c.id} value={c.company}>
                {c.company}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-xs text-muted-foreground">
          {filtered.length} of {stats.total} employees
        </span>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <StatCard title="Total Employees" value={stats.total} icon={<Users className="h-4 w-4" />} />
        <StatCard title="Companies" value={stats.companies} icon={<Building2 className="h-4 w-4" />} />
        <StatCard
          title={companyFilter !== 'all' ? companyFilter : 'Showing'}
          value={filtered.length}
          icon={<Briefcase className="h-4 w-4" />}
        />
      </div>

      {/* Data */}
      {employees.length === 0 ? (
        <EmptyState icon={<Users className="h-10 w-10" />} title="No Employees" description="No employees found." />
      ) : isMobile ? (
        <MobileCardList
          data={filtered}
          fields={mobileFields}
          getRowId={(r) => r.id}
          onRowClick={(r) => navigate(`/app/hr/employees/${r.id}`)}
        />
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="cursor-pointer select-none" onClick={() => toggleSort('name')}>
                      <span className="flex items-center gap-1">
                        Name <ArrowUpDown className="h-3 w-3" />
                      </span>
                    </TableHead>
                    <TableHead className="cursor-pointer select-none" onClick={() => toggleSort('company')}>
                      <span className="flex items-center gap-1">
                        Company <ArrowUpDown className="h-3 w-3" />
                      </span>
                    </TableHead>
                    <TableHead className="cursor-pointer select-none" onClick={() => toggleSort('department')}>
                      <span className="flex items-center gap-1">
                        Department <ArrowUpDown className="h-3 w-3" />
                      </span>
                    </TableHead>
                    <TableHead>Brand</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Phone</TableHead>
                    <TableHead className="text-center">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((e) => (
                    <TableRow
                      key={e.id}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => navigate(`/app/hr/employees/${e.id}`)}
                    >
                      <TableCell className="font-medium">{e.name}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{e.company ?? '-'}</TableCell>
                      <TableCell className="text-xs">{e.departments ?? '-'}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{e.brand ?? '-'}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{e.email ?? '-'}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{e.phone ?? '-'}</TableCell>
                      <TableCell className="text-center">
                        <Badge variant={e.is_active ? 'default' : 'secondary'} className="text-xs">
                          {e.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
