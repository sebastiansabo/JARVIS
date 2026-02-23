import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

interface StructureItem {
  name: string
  value: number
  percent: number
}

interface StructureChartProps {
  title: string
  items: StructureItem[]
  colorScheme?: 'blue' | 'amber'
}

const COLORS = {
  blue: [
    'bg-blue-500', 'bg-blue-400', 'bg-blue-300', 'bg-sky-500', 'bg-sky-400',
    'bg-indigo-500', 'bg-indigo-400', 'bg-cyan-500',
  ],
  amber: [
    'bg-amber-500', 'bg-amber-400', 'bg-orange-500', 'bg-orange-400',
    'bg-yellow-500', 'bg-red-400', 'bg-rose-500', 'bg-rose-400',
  ],
}

function fmtValue(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return new Intl.NumberFormat('ro-RO').format(n)
}

export function StructureChart({ title, items, colorScheme = 'blue' }: StructureChartProps) {
  const colors = COLORS[colorScheme]
  const total = items.reduce((s, i) => s + Math.abs(i.value), 0)

  if (items.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">{title}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">No data</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Stacked bar */}
        <div className="flex h-6 overflow-hidden rounded-full">
          {items.map((item, i) => {
            const pct = total > 0 ? (Math.abs(item.value) / total) * 100 : 0
            if (pct < 0.5) return null
            return (
              <div
                key={i}
                className={cn('transition-all', colors[i % colors.length])}
                style={{ width: `${pct}%` }}
                title={`${item.name}: ${item.percent.toFixed(1)}%`}
              />
            )
          })}
        </div>

        {/* Legend */}
        <div className="space-y-1.5">
          {items.map((item, i) => (
            <div key={i} className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <div className={cn('h-2.5 w-2.5 rounded-sm', colors[i % colors.length])} />
                <span className="text-muted-foreground">{item.name}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="font-medium">{fmtValue(item.value)}</span>
                <span className="w-12 text-right text-muted-foreground">{item.percent.toFixed(1)}%</span>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
