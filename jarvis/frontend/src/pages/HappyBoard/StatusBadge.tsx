import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

/** Romanian display label + tint per pulse/campaign lifecycle status. */
const STATUS_STYLE: Record<string, { label: string; className: string }> = {
  draft: { label: 'draft', className: 'bg-muted text-muted-foreground border-transparent' },
  live: {
    label: 'live',
    className: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  },
  active: {
    label: 'activ',
    className: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  },
  paused: {
    label: 'pauzat',
    className: 'border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400',
  },
  closed: { label: 'închis', className: 'text-muted-foreground border-border' },
}

/** Lifecycle status pill — green when live/active, muted otherwise. */
export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const style = STATUS_STYLE[status] ?? { label: status, className: 'text-muted-foreground border-border' }
  return (
    <Badge variant="outline" className={cn(style.className, className)}>
      {style.label}
    </Badge>
  )
}

export default StatusBadge
