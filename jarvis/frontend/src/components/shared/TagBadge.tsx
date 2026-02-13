import { forwardRef } from 'react'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { EntityTag } from '@/types/tags'

interface TagBadgeProps {
  tag: EntityTag
  onRemove?: () => void
  className?: string
}

/** Hex color → contrasting text color (black or white). */
function contrastText(hex: string | null): string {
  if (!hex) return 'text-foreground'
  const c = hex.replace('#', '')
  const r = parseInt(c.substring(0, 2), 16)
  const g = parseInt(c.substring(2, 4), 16)
  const b = parseInt(c.substring(4, 6), 16)
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return lum > 0.55 ? 'text-gray-900' : 'text-white'
}

export function TagBadge({ tag, onRemove, className }: TagBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-[11px] font-medium leading-none whitespace-nowrap',
        contrastText(tag.color),
        className,
      )}
      style={{ backgroundColor: tag.color ?? '#6c757d' }}
    >
      {tag.name}
      {onRemove && (
        <button
          onClick={(e) => { e.stopPropagation(); onRemove() }}
          className="ml-0.5 rounded-full p-0 hover:opacity-70"
        >
          <X className="h-2.5 w-2.5" />
        </button>
      )}
    </span>
  )
}

interface TagBadgeListProps extends React.HTMLAttributes<HTMLDivElement> {
  tags: EntityTag[]
  maxVisible?: number
}

export const TagBadgeList = forwardRef<HTMLDivElement, TagBadgeListProps>(
  function TagBadgeList({ tags, maxVisible = 3, className, ...rest }, ref) {
    if (tags.length === 0) {
      return (
        <div
          ref={ref}
          className={cn('text-xs text-muted-foreground/50 cursor-pointer hover:text-muted-foreground', className)}
          {...rest}
        >
          +
        </div>
      )
    }

    const visible = tags.slice(0, maxVisible)
    const overflow = tags.length - maxVisible

    return (
      <div ref={ref} className={cn('flex flex-wrap items-center gap-1 cursor-pointer', className)} {...rest}>
        {visible.map((t) => (
          <TagBadge key={t.tag_id} tag={t} />
        ))}
        {overflow > 0 && (
          <span className="text-[11px] text-muted-foreground">+{overflow}</span>
        )}
      </div>
    )
  },
)
