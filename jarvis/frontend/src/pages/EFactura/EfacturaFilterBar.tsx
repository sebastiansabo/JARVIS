import type { ReactNode } from 'react'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { DateField } from '@/components/ui/date-field'

export interface CompanyOption {
  id: number
  name: string
}

/**
 * Shared, always-visible filter row for the e-Factura invoice lists
 * (Unallocated and Bin). Renders Company + Direction + Date-range + Clear.
 * Extra list-specific controls can be appended via `children`.
 */
export function EfacturaFilterBar({
  companies,
  companyId,
  direction,
  startDate,
  endDate,
  onCompanyChange,
  onDirectionChange,
  onDateRangeChange,
  onClear,
  children,
}: {
  companies: CompanyOption[]
  companyId?: number
  direction?: string
  startDate?: string
  endDate?: string
  onCompanyChange: (v: number | undefined) => void
  onDirectionChange: (v: string | undefined) => void
  onDateRangeChange: (start: string | undefined, end: string | undefined) => void
  onClear: () => void
  children?: ReactNode
}) {
  const isMobile = useIsMobile()
  const hasActive =
    companyId != null || direction != null || !!startDate || !!endDate

  return (
    <div className="flex flex-wrap items-center gap-2">
      {companies.length > 0 && (
        <Select
          value={companyId?.toString() ?? 'all'}
          onValueChange={(v) => onCompanyChange(v === 'all' ? undefined : Number(v))}
        >
          <SelectTrigger className={isMobile ? 'w-full' : 'w-[200px]'}>
            <SelectValue placeholder="All companies" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All companies</SelectItem>
            {companies.map((c) => (
              <SelectItem key={c.id} value={c.id.toString()}>
                {c.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      <Select
        value={direction ?? 'all'}
        onValueChange={(v) => onDirectionChange(v === 'all' ? undefined : v)}
      >
        <SelectTrigger className={isMobile ? 'w-full' : 'w-[130px]'}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All</SelectItem>
          <SelectItem value="received">Received</SelectItem>
          <SelectItem value="sent">Sent</SelectItem>
        </SelectContent>
      </Select>

      <DateField
        mode="range"
        startDate={startDate ?? ''}
        endDate={endDate ?? ''}
        onRangeChange={(s, e) => onDateRangeChange(s || undefined, e || undefined)}
      />

      {hasActive && (
        <Button variant="ghost" size="sm" onClick={onClear}>
          Clear
        </Button>
      )}

      {children}
    </div>
  )
}
