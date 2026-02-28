import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'

interface Breadcrumb {
  label: string
  href?: string
}

interface PageHeaderProps {
  title: React.ReactNode
  description?: React.ReactNode
  breadcrumbs?: Breadcrumb[]
  actions?: React.ReactNode
}

export function PageHeader({ title, description, breadcrumbs, actions }: PageHeaderProps) {
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="min-w-0">
        {breadcrumbs && breadcrumbs.length > 0 ? (
          <h1 className="flex items-center gap-1.5 flex-wrap">
            {breadcrumbs.map((crumb, i) => (
              <span key={i} className="flex items-center gap-1.5">
                {i > 0 && <ChevronRight className="h-4 w-4 text-muted-foreground/50 shrink-0" />}
                {i < breadcrumbs.length - 1 ? (
                  crumb.href ? (
                    <Link to={crumb.href} className="text-muted-foreground hover:text-foreground transition-colors text-lg font-medium">
                      {crumb.label}
                    </Link>
                  ) : (
                    <span className="text-muted-foreground text-lg font-medium">{crumb.label}</span>
                  )
                ) : (
                  <span className="text-2xl font-semibold tracking-tight">{crumb.label}</span>
                )}
              </span>
            ))}
          </h1>
        ) : (
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        )}
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  )
}
