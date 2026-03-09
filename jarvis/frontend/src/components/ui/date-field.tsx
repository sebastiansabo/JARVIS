import { useState, useEffect, useCallback } from 'react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { ChevronLeft, ChevronRight, CalendarIcon, X } from 'lucide-react'
import { cn } from '@/lib/utils'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const MONTHS_FULL = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

type CalendarView = 'days' | 'months' | 'years'

const fmt = (d: Date) => {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function todayStr() {
  return fmt(new Date())
}

function shiftDate(dateStr: string, days: number) {
  const d = new Date(dateStr + 'T12:00:00')
  d.setDate(d.getDate() + days)
  return fmt(d)
}

function parseDate(s: string) {
  return s ? new Date(s + 'T00:00:00') : null
}

// ─── Presets for range mode ─────────────────────────────────────────
type DateRange = { start: string; end: string }

const PRESETS = [
  { value: 'this_month', label: 'This Month' },
  { value: 'last_month', label: 'Last Month' },
  { value: 'this_quarter', label: 'This Quarter' },
  { value: 'last_quarter', label: 'Last Quarter' },
  { value: 'ytd', label: 'YTD' },
] as const

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

function detectPreset(start: string, end: string): string | null {
  if (!start && !end) return null
  for (const p of PRESETS) {
    const r = getPresetRange(p.value)
    if (r.start === start && r.end === end) return p.value
  }
  return null
}

// ─── Calendar Grid (shared by all modes) ────────────────────────────
function CalendarGrid({
  value,
  onSelect,
  onClose,
  min,
  max,
}: {
  value: string
  onSelect: (iso: string) => void
  onClose: () => void
  min?: string
  max?: string
}) {
  const today = new Date()
  const parsed = parseDate(value)
  const [viewDate, setViewDate] = useState(() => parsed ?? today)
  const [view, setView] = useState<CalendarView>('days')

  useEffect(() => {
    if (parsed) setViewDate(parsed)
  }, [value])

  const year = viewDate.getFullYear()
  const month = viewDate.getMonth()

  const firstDay = new Date(year, month, 1)
  const startWeekday = (firstDay.getDay() + 6) % 7
  const daysInMonth = new Date(year, month + 1, 0).getDate()

  const days: (number | null)[] = []
  for (let i = 0; i < startWeekday; i++) days.push(null)
  for (let d = 1; d <= daysInMonth; d++) days.push(d)

  const isToday = (d: number) =>
    d === today.getDate() && month === today.getMonth() && year === today.getFullYear()
  const isSelected = (d: number) =>
    parsed && d === parsed.getDate() && month === parsed.getMonth() && year === parsed.getFullYear()

  const isDayDisabled = (d: number) => {
    const iso = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    if (min && iso < min) return true
    if (max && iso > max) return true
    return false
  }

  const selectDay = (d: number) => {
    const m = String(month + 1).padStart(2, '0')
    const dd = String(d).padStart(2, '0')
    onSelect(`${year}-${m}-${dd}`)
    onClose()
    setView('days')
  }

  const selectMonth = (m: number) => {
    setViewDate(new Date(year, m, 1))
    setView('days')
  }

  const selectYear = (y: number) => {
    setViewDate(new Date(y, month, 1))
    setView('months')
  }

  const yearStart = year - 5
  const yearsGrid = Array.from({ length: 12 }, (_, i) => yearStart + i)

  const prevMonth = () => setViewDate(new Date(year, month - 1, 1))
  const nextMonth = () => setViewDate(new Date(year, month + 1, 1))
  const prevYear = () => setViewDate(new Date(year - 1, month, 1))
  const nextYear = () => setViewDate(new Date(year + 1, month, 1))
  const prevYearBlock = () => setViewDate(new Date(year - 12, month, 1))
  const nextYearBlock = () => setViewDate(new Date(year + 12, month, 1))

  return (
    <>
      {view === 'days' && (
        <>
          <div className="flex items-center justify-between mb-2">
            <button type="button" onClick={prevMonth} className="rounded p-1 hover:bg-accent"><ChevronLeft className="h-4 w-4" /></button>
            <button
              type="button"
              onClick={() => setView('months')}
              className="text-sm font-medium hover:bg-accent rounded px-2 py-1"
            >
              {MONTHS_FULL[month]} {year}
            </button>
            <button type="button" onClick={nextMonth} className="rounded p-1 hover:bg-accent"><ChevronRight className="h-4 w-4" /></button>
          </div>
          <div className="grid grid-cols-7 gap-0 text-center text-xs text-muted-foreground mb-1">
            {['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'].map(d => (
              <div key={d} className="py-1">{d}</div>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-0 text-center text-sm">
            {days.map((d, i) => (
              <div key={i} className="aspect-square flex items-center justify-center">
                {d ? (
                  <button
                    type="button"
                    disabled={isDayDisabled(d)}
                    onClick={() => selectDay(d)}
                    className={cn(
                      'h-7 w-7 rounded-md text-xs hover:bg-accent',
                      isDayDisabled(d) && 'opacity-30 cursor-not-allowed hover:bg-transparent',
                      isToday(d) && 'border border-primary/50',
                      isSelected(d) && 'bg-primary text-primary-foreground hover:bg-primary/90',
                    )}
                  >
                    {d}
                  </button>
                ) : null}
              </div>
            ))}
          </div>
          <div className="mt-2 border-t pt-2 flex justify-between">
            <button
              type="button"
              onClick={() => {
                const t = todayStr()
                if ((!min || t >= min) && (!max || t <= max)) {
                  onSelect(t)
                  onClose()
                }
              }}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Today
            </button>
            {parsed && (
              <button
                type="button"
                onClick={() => { onSelect(''); onClose() }}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                Clear
              </button>
            )}
          </div>
        </>
      )}

      {view === 'months' && (
        <>
          <div className="flex items-center justify-between mb-3">
            <button type="button" onClick={prevYear} className="rounded p-1 hover:bg-accent"><ChevronLeft className="h-4 w-4" /></button>
            <button
              type="button"
              onClick={() => setView('years')}
              className="text-sm font-medium hover:bg-accent rounded px-2 py-1"
            >
              {year}
            </button>
            <button type="button" onClick={nextYear} className="rounded p-1 hover:bg-accent"><ChevronRight className="h-4 w-4" /></button>
          </div>
          <div className="grid grid-cols-3 gap-1.5">
            {MONTHS.map((m, i) => (
              <button
                type="button"
                key={m}
                onClick={() => selectMonth(i)}
                className={cn(
                  'rounded-md py-2 text-sm hover:bg-accent',
                  parsed && i === parsed.getMonth() && year === parsed.getFullYear() && 'bg-primary text-primary-foreground hover:bg-primary/90',
                  i === today.getMonth() && year === today.getFullYear() && 'border border-primary/50',
                )}
              >
                {m}
              </button>
            ))}
          </div>
        </>
      )}

      {view === 'years' && (
        <>
          <div className="flex items-center justify-between mb-3">
            <button type="button" onClick={prevYearBlock} className="rounded p-1 hover:bg-accent"><ChevronLeft className="h-4 w-4" /></button>
            <span className="text-sm font-medium">{yearStart} – {yearStart + 11}</span>
            <button type="button" onClick={nextYearBlock} className="rounded p-1 hover:bg-accent"><ChevronRight className="h-4 w-4" /></button>
          </div>
          <div className="grid grid-cols-3 gap-1.5">
            {yearsGrid.map(y => (
              <button
                type="button"
                key={y}
                onClick={() => selectYear(y)}
                className={cn(
                  'rounded-md py-2 text-sm hover:bg-accent',
                  parsed && y === parsed.getFullYear() && 'bg-primary text-primary-foreground hover:bg-primary/90',
                  y === today.getFullYear() && 'border border-primary/50',
                )}
              >
                {y}
              </button>
            ))}
          </div>
        </>
      )}
    </>
  )
}

// ─── Single Mode ────────────────────────────────────────────────────
interface SingleProps {
  mode?: 'single'
  value: string
  onChange: (v: string) => void
  placeholder?: string
  className?: string
  min?: string
  max?: string
  disabled?: boolean
  required?: boolean
}

function SingleDateField({
  value, onChange, placeholder = 'Pick date', className, min, max, disabled,
}: SingleProps) {
  const [open, setOpen] = useState(false)
  const parsed = parseDate(value)
  const displayText = parsed
    ? `${parsed.getDate()} ${MONTHS[parsed.getMonth()]} ${parsed.getFullYear()}`
    : placeholder

  return (
    <Popover open={open} onOpenChange={o => { if (!disabled) setOpen(o) }}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          disabled={disabled}
          className={cn(
            'justify-start text-left font-normal h-9 px-3',
            !parsed && 'text-muted-foreground',
            className,
          )}
        >
          <CalendarIcon className="h-3.5 w-3.5 mr-1.5 shrink-0" />
          <span className="truncate text-xs">{displayText}</span>
          {parsed && !disabled && (
            <span
              className="ml-auto pl-1 shrink-0 text-muted-foreground hover:text-foreground"
              onClick={e => { e.stopPropagation(); onChange('') }}
            >
              <X className="h-3 w-3" />
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[260px] p-3">
        <CalendarGrid
          value={value}
          onSelect={onChange}
          onClose={() => setOpen(false)}
          min={min}
          max={max}
        />
      </PopoverContent>
    </Popover>
  )
}

// ─── Range Mode ─────────────────────────────────────────────────────
interface RangeProps {
  mode: 'range'
  startDate: string
  endDate: string
  onRangeChange: (start: string, end: string) => void
  showPresets?: boolean
  className?: string
  disabled?: boolean
}

function RangeDateField({
  startDate, endDate, onRangeChange, showPresets = true, className, disabled,
}: RangeProps) {
  const [side, setSide] = useState<'start' | 'end'>('start')
  const [open, setOpen] = useState(false)
  const activePreset = detectPreset(startDate, endDate)

  const parsedStart = parseDate(startDate)
  const parsedEnd = parseDate(endDate)
  const startText = parsedStart
    ? `${parsedStart.getDate()} ${MONTHS[parsedStart.getMonth()]} ${parsedStart.getFullYear()}`
    : 'From'
  const endText = parsedEnd
    ? `${parsedEnd.getDate()} ${MONTHS[parsedEnd.getMonth()]} ${parsedEnd.getFullYear()}`
    : 'To'

  const handleSelect = useCallback((iso: string) => {
    if (side === 'start') {
      onRangeChange(iso, endDate && iso > endDate ? iso : endDate)
    } else {
      onRangeChange(startDate && iso < startDate ? iso : startDate, iso)
    }
  }, [side, startDate, endDate, onRangeChange])

  const handlePreset = (key: string) => {
    const r = getPresetRange(key)
    onRangeChange(r.start, r.end)
    setOpen(false)
  }

  const handleClearAll = () => {
    onRangeChange('', '')
    setOpen(false)
  }

  return (
    <div className={cn('flex items-center gap-1', className)}>
      <Popover open={open} onOpenChange={o => { if (!disabled) setOpen(o) }}>
        <div className="flex items-center gap-1">
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              disabled={disabled}
              onClick={() => setSide('start')}
              className={cn(
                'justify-start text-left font-normal h-8 px-2.5 text-xs',
                !parsedStart && 'text-muted-foreground',
                side === 'start' && open && 'ring-1 ring-primary',
              )}
            >
              <CalendarIcon className="h-3 w-3 mr-1 shrink-0" />
              <span className="truncate">{startText}</span>
            </Button>
          </PopoverTrigger>
          <span className="text-xs text-muted-foreground">—</span>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              disabled={disabled}
              onClick={() => setSide('end')}
              className={cn(
                'justify-start text-left font-normal h-8 px-2.5 text-xs',
                !parsedEnd && 'text-muted-foreground',
                side === 'end' && open && 'ring-1 ring-primary',
              )}
            >
              <CalendarIcon className="h-3 w-3 mr-1 shrink-0" />
              <span className="truncate">{endText}</span>
            </Button>
          </PopoverTrigger>
          {(parsedStart || parsedEnd) && !disabled && (
            <button
              type="button"
              onClick={handleClearAll}
              className="shrink-0 text-muted-foreground hover:text-foreground p-0.5"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
        <PopoverContent align="start" className="w-[260px] p-3">
          <div className="text-[10px] text-muted-foreground mb-2 font-medium uppercase tracking-wide">
            {side === 'start' ? 'Select start date' : 'Select end date'}
          </div>
          <CalendarGrid
            value={side === 'start' ? startDate : endDate}
            onSelect={handleSelect}
            onClose={() => setOpen(false)}
            min={side === 'end' ? startDate : undefined}
            max={side === 'start' ? endDate : undefined}
          />
          {showPresets && (
            <div className="mt-2 border-t pt-2 flex flex-wrap gap-1">
              {PRESETS.map(p => (
                <button
                  type="button"
                  key={p.value}
                  onClick={() => handlePreset(p.value)}
                  className={cn(
                    'text-[10px] px-2 py-0.5 rounded-full border hover:bg-accent transition-colors',
                    activePreset === p.value && 'bg-primary text-primary-foreground border-primary hover:bg-primary/90',
                  )}
                >
                  {p.label}
                </button>
              ))}
              <button
                type="button"
                onClick={handleClearAll}
                className="text-[10px] px-2 py-0.5 rounded-full border hover:bg-accent transition-colors"
              >
                All Time
              </button>
            </div>
          )}
        </PopoverContent>
      </Popover>
    </div>
  )
}

// ─── Navigation Mode ────────────────────────────────────────────────
interface NavigationProps {
  mode: 'navigation'
  value: string
  onChange: (v: string) => void
  min?: string
  max?: string
  className?: string
  disabled?: boolean
}

function NavigationDateField({
  value, onChange, min, max, className, disabled,
}: NavigationProps) {
  const [open, setOpen] = useState(false)
  const parsed = parseDate(value)
  const displayText = parsed
    ? `${parsed.getDate()} ${MONTHS[parsed.getMonth()]} ${parsed.getFullYear()}`
    : 'No date'

  const canPrev = !min || (value && shiftDate(value, -1) >= min)
  const canNext = !max || (value && shiftDate(value, 1) <= max)

  const goPrev = () => {
    if (value && canPrev) onChange(shiftDate(value, -1))
  }
  const goNext = () => {
    if (value && canNext) onChange(shiftDate(value, 1))
  }

  return (
    <div className={cn('flex items-center gap-1 shrink-0', className)}>
      <Button
        variant="outline"
        size="icon"
        className="h-8 w-8"
        disabled={disabled || !canPrev}
        onClick={goPrev}
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>
      <Popover open={open} onOpenChange={o => { if (!disabled) setOpen(o) }}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            disabled={disabled}
            className="h-8 px-3 text-sm font-normal min-w-[140px] justify-center"
          >
            <CalendarIcon className="h-3.5 w-3.5 mr-1.5 shrink-0" />
            {displayText}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="center" className="w-[260px] p-3">
          <CalendarGrid
            value={value}
            onSelect={onChange}
            onClose={() => setOpen(false)}
            min={min}
            max={max}
          />
        </PopoverContent>
      </Popover>
      <Button
        variant="outline"
        size="icon"
        className="h-8 w-8"
        disabled={disabled || !canNext}
        onClick={goNext}
      >
        <ChevronRight className="h-4 w-4" />
      </Button>
    </div>
  )
}

// ─── Unified Export ─────────────────────────────────────────────────
type DateFieldProps = SingleProps | RangeProps | NavigationProps

export function DateField(props: DateFieldProps) {
  const mode = props.mode ?? 'single'
  switch (mode) {
    case 'range':
      return <RangeDateField {...(props as RangeProps)} />
    case 'navigation':
      return <NavigationDateField {...(props as NavigationProps)} />
    default:
      return <SingleDateField {...(props as SingleProps)} />
  }
}

// Re-export helpers for consumers that need them
export { todayStr, shiftDate, fmt as formatDate }
