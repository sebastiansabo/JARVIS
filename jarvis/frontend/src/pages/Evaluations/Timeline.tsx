import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface TimelineNode {
  label: string
  state: 'done' | 'current' | 'todo'
  /** Small value shown under a done node (e.g. the given score, or "N/O"). */
  badge?: string
}

/** A horizontal step rail — one node per step, with a connector line, a dot
 *  (✓ when done, else its number), a label, and an optional mini badge. Used by
 *  the evaluation capture stepper (clickable) and the admin cycle-stage header
 *  (read-only). On narrow screens pass `compact` to drop the labels to dots. */
export function Timeline({ nodes, current, onSelect, compact }: {
  nodes: TimelineNode[]
  /** Index of the current node (for the aria-current marker). */
  current?: number
  onSelect?: (i: number) => void
  compact?: boolean
}) {
  return (
    <div className="flex items-start" role="list">
      {nodes.map((n, i) => {
        const clickable = !!onSelect && n.state !== 'todo'
        return (
          <button
            key={i}
            type="button"
            role="listitem"
            aria-current={i === current ? 'step' : undefined}
            disabled={!clickable}
            onClick={() => clickable && onSelect!(i)}
            className={cn('group relative flex flex-1 flex-col items-center text-center', clickable ? 'cursor-pointer' : 'cursor-default')}
          >
            {/* connector back to the previous node */}
            {i > 0 && (
              <span className={cn('absolute top-3.5 right-1/2 z-0 h-0.5 w-full', n.state === 'todo' ? 'bg-border' : 'bg-primary')} />
            )}
            <span className={cn(
              'relative z-10 flex h-7 w-7 items-center justify-center rounded-full border-2 text-xs font-bold transition-all',
              n.state === 'done' ? 'border-primary bg-primary text-primary-foreground'
                : n.state === 'current' ? 'scale-110 border-primary bg-background text-primary ring-4 ring-primary/15'
                  : 'border-border bg-background text-muted-foreground',
            )}>
              {n.state === 'done' ? <Check className="h-3.5 w-3.5" /> : i + 1}
            </span>
            {!compact && (
              <span className={cn('mt-2 max-w-[9ch] truncate text-[11px] font-medium leading-tight',
                n.state === 'current' ? 'text-primary' : n.state === 'done' ? 'text-foreground' : 'text-muted-foreground')}>
                {n.label}
              </span>
            )}
            {n.badge && n.state === 'done' && <span className="text-[10px] font-bold text-green-600">{n.badge}</span>}
          </button>
        )
      })}
    </div>
  )
}
