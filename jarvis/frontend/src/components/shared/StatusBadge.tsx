import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

const statusColors: Record<string, string> = {
  active: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
  pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
  resolved: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  ignored: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200',
  merged: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
  deleted: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
  archived: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200',
  coming_soon: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200',
  paid: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
  unpaid: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
  not_paid: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
  partial: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
  new: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  processed: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
  incomplete: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
  eronata: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
  nebugetata: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
  bugetata: 'bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-200',
  approved: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200',
}

interface StatusBadgeProps {
  status: string | undefined | null
  className?: string
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  if (!status) return null
  const colorClass = statusColors[status.toLowerCase()] ?? statusColors.pending
  return (
    <Badge variant="secondary" className={cn('font-normal', colorClass, className)}>
      {status}
    </Badge>
  )
}
