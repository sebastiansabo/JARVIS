/**
 * BrandFilter — inline quick-filter widget with brand/company logos.
 *
 * Renders a compact row of clickable logo pills. Each page decides how to
 * map clicks to its own filter mechanism via the `onSelect` callback.
 *
 * Usage modes:
 *   mode="brand"   → shows brand logos (Toyota, Mazda, VW, Audi, Volvo, MG)
 *   mode="company"  → shows company logos (loaded from API, matched to known logos)
 *   mode="both"     → shows company pills grouped by brand
 *
 * The widget auto-fetches company/brand data from the organization API.
 */
import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { organizationApi } from '@/api/organization'
import { cn } from '@/lib/utils'
import { X } from 'lucide-react'
import type { CompanyWithBrands } from '@/types/organization'

/* ── Logo mapping ─────────────────────────────────────────── */

const BRAND_LOGOS: Record<string, string> = {
  toyota: '/static/img/brands/toyota.png',
  mazda: '/static/img/brands/mazda.png',
  volkswagen: '/static/img/brands/vw.png',
  vw: '/static/img/brands/vw.png',
  audi: '/static/img/brands/audi.png',
  volvo: '/static/img/brands/volvo.png',
  mg: '/static/img/brands/mg.png',
  autoworld: '/static/img/brands/autoworld_holding.png',
}

function logoFor(name: string): string | null {
  const key = name.toLowerCase().replace(/\s+/g, '')
  for (const [k, v] of Object.entries(BRAND_LOGOS)) {
    if (key.includes(k)) return v
  }
  return null
}

/* ── Types ────────────────────────────────────────────────── */

export interface BrandFilterItem {
  /** Unique key for selection state */
  key: string
  /** Display label (shown on hover / when no logo) */
  label: string
  /** Logo URL (resolved automatically from name) */
  logo: string | null
  /** Company id (for pages that filter by numeric id) */
  companyId?: number
  /** Brand id (for pages that filter by numeric id) */
  brandId?: number
  /** Raw company name (for pages that filter by string) */
  companyName?: string
  /** Raw brand name (for pages that filter by string) */
  brandName?: string
}

interface BrandFilterProps {
  /** Which dimension to show pills for */
  mode?: 'company' | 'brand'
  /** Currently selected key (null = all) */
  value: string | null
  /** Called when a pill is clicked. key=null means "All" */
  onSelect: (item: BrandFilterItem | null) => void
  /** Optional: hide the "All" reset pill */
  hideAll?: boolean
  /** Optional: extra className on the container */
  className?: string
}

/* ── Component ────────────────────────────────────────────── */

export function BrandFilter({
  mode = 'company',
  value,
  onSelect,
  hideAll,
  className,
}: BrandFilterProps) {
  const { data: companies = [] } = useQuery<CompanyWithBrands[]>({
    queryKey: ['companies-config'],
    queryFn: organizationApi.getCompaniesConfig,
    staleTime: 5 * 60_000,
  })

  const items = useMemo(() => {
    if (mode === 'brand') {
      // Deduplicate brands across all companies
      const seen = new Map<string, BrandFilterItem>()
      for (const c of companies) {
        for (const b of c.brands_list ?? []) {
          const bKey = b.brand.toLowerCase()
          if (!seen.has(bKey)) {
            seen.set(bKey, {
              key: `brand:${b.brand_id}`,
              label: b.brand,
              logo: logoFor(b.brand),
              brandId: b.brand_id,
              brandName: b.brand,
            })
          }
        }
      }
      return Array.from(seen.values())
    }

    // mode === 'company'
    return companies
      .sort((a, b) => (a.display_order ?? 0) - (b.display_order ?? 0))
      .map((c): BrandFilterItem => {
        // Try to find a brand logo for the company
        const primaryBrand = c.brands_list?.[0]?.brand
        const logo = logoFor(c.company) ?? (primaryBrand ? logoFor(primaryBrand) : null)
        return {
          key: `company:${c.id}`,
          label: c.company,
          logo,
          companyId: c.id,
          companyName: c.company,
          brandName: primaryBrand ?? undefined,
        }
      })
  }, [companies, mode])

  if (items.length === 0) return null

  return (
    <div className={cn('flex items-center gap-1', className)}>
      {/* "All" reset pill */}
      {!hideAll && (
        <button
          onClick={() => onSelect(null)}
          className={cn(
            'inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-all',
            value === null
              ? 'border-primary bg-primary/10 text-primary shadow-sm'
              : 'border-transparent text-muted-foreground hover:border-border hover:text-foreground',
          )}
        >
          All
        </button>
      )}

      {items.map((item) => {
        const isActive = value === item.key
        return (
          <button
            key={item.key}
            onClick={() => onSelect(isActive ? null : item)}
            title={item.label}
            className={cn(
              'group relative inline-flex items-center gap-1.5 rounded-full border px-2 py-1 transition-all',
              isActive
                ? 'border-primary bg-primary/10 shadow-sm ring-1 ring-primary/20'
                : 'border-transparent hover:border-border hover:bg-accent/50',
            )}
          >
            {item.logo ? (
              <img
                src={item.logo}
                alt={item.label}
                className={cn(
                  'h-4 w-4 object-contain transition-opacity dark:invert',
                  isActive ? 'opacity-100' : 'opacity-60 group-hover:opacity-100',
                )}
              />
            ) : (
              <span
                className={cn(
                  'flex h-4 w-4 items-center justify-center rounded-full bg-muted text-[9px] font-bold leading-none',
                  isActive ? 'bg-primary/20 text-primary' : 'text-muted-foreground',
                )}
              >
                {item.label.charAt(0)}
              </span>
            )}
            <span
              className={cn(
                'text-xs font-medium whitespace-nowrap',
                isActive ? 'text-primary' : 'text-muted-foreground group-hover:text-foreground',
              )}
            >
              {item.label}
            </span>
            {isActive && (
              <X className="h-3 w-3 text-primary/60" />
            )}
          </button>
        )
      })}
    </div>
  )
}
