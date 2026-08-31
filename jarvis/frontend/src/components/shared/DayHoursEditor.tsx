import { useState } from 'react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Clock } from 'lucide-react'
import { eventHoursFromDayHours, type DayHours } from '@/lib/eventHours'

interface DayHoursEditorProps {
  /** Selected attended days as 'YYYY-MM-DD', sorted. */
  days: string[]
  value: DayHours
  onChange: (next: DayHours) => void
}

/** UTC-safe 'YYYY-MM-DD' → e.g. "29 aug." */
function dayLabel(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('ro-RO', {
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  })
}

/** '' → null; otherwise the whole hour clamped to 0..24. */
function parseHour(raw: string): number | null {
  if (raw === '') return null
  const n = Math.round(Number(raw))
  if (Number.isNaN(n)) return null
  return Math.min(24, Math.max(0, n))
}

/**
 * Per-day whole-hour interval editor. Each selected day gets a start/end hour;
 * a participant's "Event Hours" = sum of (end − start). Includes an "apply to
 * all days" shortcut so a uniform shift needn't be typed per day.
 */
export function DayHoursEditor({ days, value, onChange }: DayHoursEditorProps) {
  const [bulkStart, setBulkStart] = useState('')
  const [bulkEnd, setBulkEnd] = useState('')

  if (days.length === 0) return null

  const total = eventHoursFromDayHours(value)

  const setDay = (iso: string, patch: Partial<{ start: number | null; end: number | null }>) => {
    const cur = value[iso] ?? { start: null, end: null }
    onChange({ ...value, [iso]: { ...cur, ...patch } })
  }

  const applyToAll = () => {
    const start = parseHour(bulkStart)
    const end = parseHour(bulkEnd)
    if (start == null || end == null || end <= start) return
    const next: DayHours = { ...value }
    for (const iso of days) next[iso] = { start, end }
    onChange(next)
  }

  const bulkValid = (() => {
    const s = parseHour(bulkStart)
    const e = parseHour(bulkEnd)
    return s != null && e != null && e > s
  })()

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
          <Clock className="h-3 w-3" /> Interval orar / zi
        </span>
        <span className="text-[11px] font-medium tabular-nums">
          Ore eveniment: {total}
        </span>
      </div>

      {/* Apply-to-all shortcut */}
      <div className="flex items-center gap-1">
        <span className="w-14 shrink-0 text-[10px] text-muted-foreground">Toate zilele</span>
        <Input
          type="number" min={0} max={24} placeholder="de la"
          className="h-6 w-14 px-1 text-center text-xs"
          value={bulkStart} onChange={(e) => setBulkStart(e.target.value)}
        />
        <span className="text-muted-foreground">–</span>
        <Input
          type="number" min={0} max={24} placeholder="până"
          className="h-6 w-14 px-1 text-center text-xs"
          value={bulkEnd} onChange={(e) => setBulkEnd(e.target.value)}
        />
        <Button
          type="button" variant="outline" size="sm" className="h-6 px-2 text-[11px]"
          disabled={!bulkValid} onClick={applyToAll}
        >
          Aplică
        </Button>
      </div>

      {/* Per-day intervals */}
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {days.map((iso) => {
          const iv = value[iso] ?? { start: null, end: null }
          const invalid = iv.start != null && iv.end != null && iv.end <= iv.start
          return (
            <div key={iso} className="flex items-center gap-1">
              <span className="w-12 shrink-0 text-right text-[10px] tabular-nums text-muted-foreground">
                {dayLabel(iso)}
              </span>
              <Input
                type="number" min={0} max={24} aria-label={`${iso} start`}
                className={`h-6 w-12 px-1 text-center text-xs ${invalid ? 'border-destructive' : ''}`}
                value={iv.start ?? ''}
                onChange={(e) => setDay(iso, { start: parseHour(e.target.value) })}
              />
              <span className="text-muted-foreground">–</span>
              <Input
                type="number" min={0} max={24} aria-label={`${iso} end`}
                className={`h-6 w-12 px-1 text-center text-xs ${invalid ? 'border-destructive' : ''}`}
                value={iv.end ?? ''}
                onChange={(e) => setDay(iso, { end: parseHour(e.target.value) })}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}
