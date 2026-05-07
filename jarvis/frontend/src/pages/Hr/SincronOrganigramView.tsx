import { useState, useMemo, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Building2, Users, User, Link2, Unlink } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/shared/EmptyState'
import { organizationApi, type SincronOrgCompany } from '@/api/organization'

/** Title-case a company name */
function titleCase(name: string): string {
  return name.replace(/\S+/g, (w) =>
    /^s\.r\.l\.?$/i.test(w) ? 'S.R.L.' : w.charAt(0).toUpperCase() + w.slice(1).toLowerCase(),
  )
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
      setExpanded(new Set(companies.map((c) => c.company_name)))
    }
  }, [companies.length])

  const toggle = (key: string) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  const filtered = useMemo(() => {
    if (!search.trim()) return companies
    const q = search.toLowerCase()
    return companies
      .map((company) => {
        if (company.company_name.toLowerCase().includes(q)) return company
        // Filter departments + employees matching search
        const filteredDepts = company.departments
          .map((dept) => {
            if (dept.name.toLowerCase().includes(q)) return dept
            const matchEmps = dept.employees.filter(
              (e) =>
                `${e.nume} ${e.prenume}`.toLowerCase().includes(q) ||
                e.mapped_user_name?.toLowerCase().includes(q),
            )
            if (matchEmps.length > 0) return { ...dept, employees: matchEmps, count: matchEmps.length }
            return null
          })
          .filter(Boolean) as typeof company.departments
        if (filteredDepts.length > 0) {
          const matchEmps = filteredDepts.flatMap((d) => d.employees)
          return { ...company, departments: filteredDepts, employees: matchEmps, count: matchEmps.length }
        }
        return null
      })
      .filter(Boolean) as SincronOrgCompany[]
  }, [companies, search])

  if (isLoading) return <Skeleton className="h-64 w-full" />

  if (!companies.length) {
    return <EmptyState title="No Sincron data" description="No active Sincron employees found." />
  }

  const totalEmps = data?.total_employees ?? 0
  const totalComps = data?.total_companies ?? 0

  return (
    <div className="space-y-3">
      {filtered.map((company) => {
        const isCompanyExpanded = expanded.has(company.company_name)
        const mappedCount = company.employees.filter((e) => e.mapped_jarvis_user_id).length

        return (
          <Card key={company.company_name} className="overflow-hidden">
            {/* Company header */}
            <button
              onClick={() => toggle(company.company_name)}
              className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-muted/50 transition-colors"
            >
              {isCompanyExpanded ? (
                <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
              ) : (
                <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
              )}
              <Building2 className="h-5 w-5 text-amber-600 shrink-0" />
              <span className="font-semibold text-sm">{titleCase(company.company_name)}</span>
              <div className="ml-auto flex items-center gap-2">
                <Badge variant="outline" className="text-xs">
                  {mappedCount}/{company.count} mapped
                </Badge>
                <Badge variant="secondary" className="text-xs">
                  {company.count}
                </Badge>
              </div>
            </button>

            {/* Departments within company */}
            {isCompanyExpanded && (
              <div className="border-t">
                {company.departments.map((dept) => {
                  const deptKey = `${company.company_name}::${dept.name}`
                  const isDeptExpanded = expanded.has(deptKey)
                  const deptMapped = dept.employees.filter((e) => e.mapped_jarvis_user_id).length

                  return (
                    <div key={deptKey}>
                      {/* Department header */}
                      <button
                        onClick={() => toggle(deptKey)}
                        className="flex w-full items-center gap-3 pl-8 pr-4 py-2 text-left hover:bg-muted/40 transition-colors border-b border-muted/20"
                      >
                        {isDeptExpanded ? (
                          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        ) : (
                          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        )}
                        <Users className="h-4 w-4 text-blue-600 shrink-0" />
                        <span className="text-sm font-medium text-foreground/80">{dept.name}</span>
                        <div className="ml-auto flex items-center gap-2">
                          <span className="text-xs text-muted-foreground">
                            {deptMapped}/{dept.count}
                          </span>
                          <Badge variant="outline" className="text-xs">
                            {dept.count}
                          </Badge>
                        </div>
                      </button>

                      {/* Employees within department */}
                      {isDeptExpanded && (
                        <div className="divide-y divide-muted/20">
                          {dept.employees.map((emp) => (
                            <div
                              key={`${emp.sincron_employee_id}-${company.company_name}`}
                              className="flex items-center gap-3 pl-16 pr-4 py-2 text-sm hover:bg-muted/30 transition-colors"
                            >
                              <User className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                              <span className="font-medium">
                                {titleCase(emp.nume)} {titleCase(emp.prenume)}
                              </span>
                              {emp.norma_lucru && (
                                <span className="text-xs text-muted-foreground">{emp.norma_lucru}h</span>
                              )}
                              {emp.nr_contract && (
                                <span className="text-xs text-muted-foreground">#{emp.nr_contract}</span>
                              )}
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
                          ))}
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

      <p className="text-xs text-muted-foreground pt-1">
        {totalComps} companies, {totalEmps} employees
      </p>
    </div>
  )
}
