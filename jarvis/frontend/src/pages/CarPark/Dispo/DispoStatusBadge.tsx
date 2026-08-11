import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { STATUS_LABELS, type VehicleStatus } from '@/types/carpark'

// Extracted out of index.tsx so StatusEditCell (inline status dropdown) can
// render the exact same badge as the read-only display — kept as its own
// module rather than folded into EditableCell.tsx since status has no
// "text input" edit mode, just this badge plus a dropdown trigger.
export const STATUS_COLORS: Record<string, string> = {
  ACQUIRED: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  INSPECTION: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
  RECONDITIONING: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
  READY_FOR_SALE: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200',
  LISTED: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
  RESERVED: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
  SOLD: 'bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-200',
  DELIVERED: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200',
  PRICE_REDUCED: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
  AUCTION_CANDIDATE: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200',
  IN_TRANSIT: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200',
  AT_BODYSHOP: 'bg-rose-100 text-rose-800 dark:bg-rose-900 dark:text-rose-200',
  INSURANCE_CLAIM: 'bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-200',
  RETURNED: 'bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200',
  SCRAPPED: 'bg-zinc-100 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200',
  TRANSFERRED: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900 dark:text-cyan-200',
}

export function DispoStatusBadge({ status }: { status: VehicleStatus }) {
  return (
    <Badge variant="secondary" className={cn('font-normal text-[11px] whitespace-nowrap', STATUS_COLORS[status] ?? '')}>
      {STATUS_LABELS[status] ?? status}
    </Badge>
  )
}
