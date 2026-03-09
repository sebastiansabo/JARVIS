import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useIsMobile } from '@/hooks/useMediaQuery'

interface Breadcrumb {
  label: string
  shortLabel?: string
  href?: string
}

interface PageHeaderProps {
  title: React.ReactNode
  description?: React.ReactNode
  breadcrumbs?: Breadcrumb[]
  actions?: React.ReactNode
}

export function PageHeader({ title, description, breadcrumbs, actions }: PageHeaderProps) {
  const isMobile = useIsMobile()

  /* ── Mobile: stacked layout ── */
  if (isMobile && breadcrumbs && breadcrumbs.length > 1) {
    const parentCrumbs = breadcrumbs.slice(0, -1)
    const current = breadcrumbs[breadcrumbs.length - 1]
    return (
      <div className="space-y-3">
        <nav className="flex items-center gap-1.5 text-sm text-muted-foreground">
          {parentCrumbs.map((crumb, i) => (
            <span key={i} className="flex items-center gap-1.5">
              {i > 0 && <ChevronRight className="h-3 w-3 text-muted-foreground/50" />}
              {crumb.href ? (
                <Link to={crumb.href} className="hover:text-foreground transition-colors">
                  {crumb.shortLabel || crumb.label}
                </Link>
              ) : (
                <span>{crumb.shortLabel || crumb.label}</span>
              )}
            </span>
          ))}
        </nav>
        <h1 className="text-xl font-semibold tracking-tight truncate">{current.label}</h1>
        {description && <div className="text-sm text-muted-foreground">{description}</div>}
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
    )
  }

  /* ── Desktop: inline layout ── */
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="min-w-0">
        {breadcrumbs && breadcrumbs.length > 0 ? (
          <h1 className="flex items-center gap-1.5 flex-wrap">
            {breadcrumbs.map((crumb, i) => {
              const text = crumb.label
              return (
              <span key={i} className="flex items-center gap-1.5">
                {i > 0 && <ChevronRight className="h-4 w-4 text-muted-foreground/50 shrink-0" />}
                {i < breadcrumbs.length - 1 ? (
                  crumb.href ? (
                    <Link to={crumb.href} className="text-muted-foreground hover:text-foreground transition-colors text-base sm:text-lg font-medium">
                      {text}
                    </Link>
                  ) : (
                    <span className="text-muted-foreground text-base sm:text-lg font-medium">{text}</span>
                  )
                ) : (
                  <span className="text-xl sm:text-2xl font-semibold tracking-tight">{text}</span>
                )}
              </span>
            )})}
          </h1>
        ) : (
          <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">{title}</h1>
        )}
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  )
}
