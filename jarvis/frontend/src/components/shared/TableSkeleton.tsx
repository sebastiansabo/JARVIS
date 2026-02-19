import { Skeleton } from '@/components/ui/skeleton'

interface TableSkeletonProps {
  /** Number of skeleton rows (default 5) */
  rows?: number
  /** Number of columns (default 5) */
  columns?: number
  /** Show header row (default true) */
  showHeader?: boolean
  /** Show checkbox column (default false) */
  showCheckbox?: boolean
}

/**
 * Skeleton placeholder for data tables.
 * Renders a header row + N data rows with realistic column widths.
 */
export function TableSkeleton({
  rows = 5,
  columns = 5,
  showHeader = true,
  showCheckbox = false,
}: TableSkeletonProps) {
  const colWidths = ['w-32', 'w-24', 'w-20', 'w-28', 'w-16', 'w-24', 'w-20']

  return (
    <div className="space-y-0">
      {showHeader && (
        <div className="flex items-center gap-4 border-b px-4 py-3">
          {showCheckbox && <Skeleton className="h-4 w-4 rounded" />}
          {Array.from({ length: columns }).map((_, i) => (
            <Skeleton
              key={i}
              className={`h-3 ${colWidths[i % colWidths.length]}`}
            />
          ))}
        </div>
      )}
      {Array.from({ length: rows }).map((_, rowIdx) => (
        <div
          key={rowIdx}
          className="flex items-center gap-4 border-b last:border-0 px-4 py-3"
        >
          {showCheckbox && <Skeleton className="h-4 w-4 rounded" />}
          {Array.from({ length: columns }).map((_, colIdx) => (
            <Skeleton
              key={colIdx}
              className={`h-4 ${colWidths[colIdx % colWidths.length]}`}
            />
          ))}
        </div>
      ))}
    </div>
  )
}
