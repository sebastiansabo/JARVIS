import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

interface RatioCardProps {
  label: string
  value: number | null
  suffix?: string
  thresholds?: { good: number; warning: number }
  description?: string
}

function getColor(value: number | null, thresholds?: { good: number; warning: number }): string {
  if (value == null || !thresholds) return 'text-muted-foreground'
  if (value >= thresholds.good) return 'text-emerald-600 dark:text-emerald-400'
  if (value >= thresholds.warning) return 'text-amber-600 dark:text-amber-400'
  return 'text-red-600 dark:text-red-400'
}

function getBorder(value: number | null, thresholds?: { good: number; warning: number }): string {
  if (value == null || !thresholds) return ''
  if (value >= thresholds.good) return 'border-l-emerald-500'
  if (value >= thresholds.warning) return 'border-l-amber-500'
  return 'border-l-red-500'
}

export function RatioCard({ label, value, suffix = '', thresholds, description }: RatioCardProps) {
  const color = getColor(value, thresholds)
  const border = getBorder(value, thresholds)

  return (
    <Card className={cn('gap-0 border-l-4 py-0', border || 'border-l-muted')}>
      <CardContent className="px-4 py-3">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        <p className={cn('text-xl font-bold', color)}>
          {value != null ? `${value.toFixed(2)}${suffix}` : 'N/A'}
        </p>
        {description && <p className="mt-0.5 text-[11px] text-muted-foreground">{description}</p>}
      </CardContent>
    </Card>
  )
}
