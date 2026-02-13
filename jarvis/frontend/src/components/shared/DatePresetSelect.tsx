import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

type DateRange = { start: string; end: string }

const fmt = (d: Date) => d.toISOString().slice(0, 10)

function getPresetRange(key: string): DateRange {
  const now = new Date()
  const y = now.getFullYear()
  const m = now.getMonth()

  switch (key) {
    case 'this_month':
      return { start: fmt(new Date(y, m, 1)), end: fmt(now) }
    case 'last_month':
      return { start: fmt(new Date(y, m - 1, 1)), end: fmt(new Date(y, m, 0)) }
    case 'this_quarter': {
      const q = Math.floor(m / 3) * 3
      return { start: fmt(new Date(y, q, 1)), end: fmt(now) }
    }
    case 'last_quarter': {
      const q = Math.floor(m / 3) * 3
      return { start: fmt(new Date(y, q - 3, 1)), end: fmt(new Date(y, q, 0)) }
    }
    case 'ytd':
      return { start: fmt(new Date(y, 0, 1)), end: fmt(now) }
    default:
      return { start: '', end: '' }
  }
}

const presets = [
  { value: 'this_month', label: 'This Month' },
  { value: 'last_month', label: 'Last Month' },
  { value: 'this_quarter', label: 'This Quarter' },
  { value: 'last_quarter', label: 'Last Quarter' },
  { value: 'ytd', label: 'YTD' },
]

function detectPreset(start: string, end: string): string {
  if (!start && !end) return '__none__'
  for (const p of presets) {
    const r = getPresetRange(p.value)
    if (r.start === start && r.end === end) return p.value
  }
  return 'custom'
}

interface DatePresetSelectProps {
  startDate: string
  endDate: string
  onChange: (start: string, end: string) => void
}

export function DatePresetSelect({ startDate, endDate, onChange }: DatePresetSelectProps) {
  const current = detectPreset(startDate, endDate)

  const handleChange = (v: string) => {
    if (v === '__none__') {
      onChange('', '')
    } else {
      const r = getPresetRange(v)
      onChange(r.start, r.end)
    }
  }

  return (
    <Select value={current} onValueChange={handleChange}>
      <SelectTrigger className="h-8 w-auto min-w-[130px] gap-1 text-xs">
        <span className="text-muted-foreground">Period:</span>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="__none__">All Time</SelectItem>
        {presets.map((p) => (
          <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
        ))}
        {current === 'custom' && <SelectItem value="custom" disabled>Custom</SelectItem>}
      </SelectContent>
    </Select>
  )
}
