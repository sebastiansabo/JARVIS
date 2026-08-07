import { useMemo } from 'react'
import { cn } from '@/lib/utils'

export interface PresenceDayPickerProps {
  /** Event range bounds, inclusive, as 'YYYY-MM-DD'. */
  startDate: string
  endDate: string
  /** Selected days as 'YYYY-MM-DD', in any order. */
  value: string[]
  onChange: (days: string[]) => void
  disabled?: boolean
  /** Non-interactive display: shows attended days highlighted within the range. */
  readOnly?: boolean
}

/** Enumerate every day in [start, end] inclusive as ISO strings (UTC-safe). */
export function enumerateDays(startISO: string, endISO: string): string[] {
  if (!startISO || !endISO) return []
  const [sy, sm, sd] = startISO.split('-').map(Number)
  const [ey, em, ed] = endISO.split('-').map(Number)
  const cur = new Date(Date.UTC(sy, sm - 1, sd))
  const end = new Date(Date.UTC(ey, em - 1, ed))
  const out: string[] = []
  while (cur <= end && out.length < 400) {
    out.push(cur.toISOString().slice(0, 10))
    cur.setUTCDate(cur.getUTCDate() + 1)
  }
  return out
}

interface MonthGroup {
  key: string
  label: string
  shortLabel: string
  days: { iso: string; dayNum: number }[]
}

function groupByMonth(days: string[]): MonthGroup[] {
  const groups: MonthGroup[] = []
  let current: MonthGroup | null = null
  for (const iso of days) {
    const [y, m, d] = iso.split('-').map(Number)
    const key = `${y}-${m}`
    if (!current || current.key !== key) {
      const first = new Date(Date.UTC(y, m - 1, 1))
      const label = first.toLocaleDateString('ro-RO', { month: 'long', year: 'numeric' })
      const shortLabel = first.toLocaleDateString('ro-RO', { month: 'short' })
      current = { key, label, shortLabel, days: [] }
      groups.push(current)
    }
    current.days.push({ iso, dayNum: d })
  }
  return groups
}

/**
 * A compact calendar bounded to an event's date range for choosing the specific
 * (possibly non-contiguous) full days an employee attended. Days are grouped by
 * calendar month so an event spanning a month boundary reads clearly.
 */
export function PresenceDayPicker({
  startDate,
  endDate,
  value,
  onChange,
  disabled,
  readOnly,
}: PresenceDayPickerProps) {
  const months = useMemo(
    () => groupByMonth(enumerateDays(startDate, endDate)),
    [startDate, endDate],
  )
  const selected = useMemo(() => new Set(value), [value])

  const toggle = (iso: string) => {
    const next = new Set(selected)
    if (next.has(iso)) next.delete(iso)
    else next.add(iso)
    onChange([...next].sort())
  }

  if (months.length === 0) {
    return <p className="text-xs text-muted-foreground">Set the event dates first.</p>
  }

  // Compact single-row strip for tables: inline month groups, tiny day chips
  // (attended solid, missed faint), trailing count.
  if (readOnly) {
    return (
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        {months.map((m) => (
          <div key={m.key} className="flex items-center gap-0.5">
            <span className="mr-0.5 text-[10px] font-medium uppercase text-muted-foreground">{m.shortLabel}</span>
            {m.days.map((d) => {
              const isOn = selected.has(d.iso)
              return (
                <span
                  key={d.iso}
                  data-testid="presence-day"
                  data-selected={isOn}
                  aria-label={d.iso}
                  title={d.iso}
                  className={cn(
                    'inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded px-1 text-[10px] tabular-nums',
                    isOn
                      ? 'bg-primary font-semibold text-primary-foreground'
                      : 'bg-muted/40 text-muted-foreground/40',
                  )}
                >
                  {d.dayNum}
                </span>
              )
            })}
          </div>
        ))}
        <span className="whitespace-nowrap text-[10px] text-muted-foreground">· {value.length} zile</span>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {months.map((m) => (
        <div key={m.key} data-testid="presence-month" className="rounded-md border border-border/60 p-2">
          <div className="mb-1 text-xs font-medium capitalize text-muted-foreground">{m.label}</div>
          <div className="flex flex-wrap gap-1">
            {m.days.map((d) => {
              const isOn = selected.has(d.iso)
              return (
                <button
                  key={d.iso}
                  type="button"
                  aria-label={d.iso}
                  aria-pressed={isOn}
                  disabled={disabled}
                  onClick={() => toggle(d.iso)}
                  className={cn(
                    'h-8 w-8 rounded-md text-xs tabular-nums transition-colors',
                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    disabled && 'cursor-not-allowed opacity-50',
                    isOn
                      ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                      : 'bg-muted text-muted-foreground hover:bg-muted/70',
                  )}
                >
                  {d.dayNum}
                </button>
              )
            })}
          </div>
        </div>
      ))}
      <div className="text-xs text-muted-foreground">
        {value.length} {value.length === 1 ? 'zi selectată' : 'zile selectate'}
      </div>
    </div>
  )
}
