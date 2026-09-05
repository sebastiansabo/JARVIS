import { useQuery } from '@tanstack/react-query'

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { organizationApi } from '@/api/organization'
import { useAccountingStore } from '@/stores/accountingStore'
import type { CompanyWithBrands } from '@/types/organization'

const ALL = '__all__'

interface AccountingTenantSelectorProps {
  /** Show the "Toate companiile" option (default true). Pages that require a specific
   * company (e.g. per-company export) can hide it. */
  allowAll?: boolean
  className?: string
}

/**
 * Accounting section tenant switcher — a company dropdown ("Toate companiile" + group
 * companies) bound to the shared accountingStore, so the acting company persists across
 * accounting pages. Company-only (no brand). Mirrors the tenant selector in other sections.
 */
export function AccountingTenantSelector({ allowAll = true, className }: AccountingTenantSelectorProps) {
  const selectedCompanyId = useAccountingStore((s) => s.selectedCompanyId)
  const setSelectedCompanyId = useAccountingStore((s) => s.setSelectedCompanyId)

  const { data: companies = [] } = useQuery<CompanyWithBrands[]>({
    queryKey: ['companies-config'],
    queryFn: () => organizationApi.getCompaniesConfig(),
    staleTime: 10 * 60_000,
  })

  const value = selectedCompanyId == null ? (allowAll ? ALL : '') : String(selectedCompanyId)

  return (
    <Select
      value={value}
      onValueChange={(v) => setSelectedCompanyId(v === ALL ? null : Number(v))}
    >
      <SelectTrigger className={className}>
        <SelectValue placeholder="Selectează compania" />
      </SelectTrigger>
      <SelectContent>
        {allowAll && <SelectItem value={ALL}>Toate companiile</SelectItem>}
        {companies.map((c) => (
          <SelectItem key={c.id} value={String(c.id)}>
            {c.company}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
