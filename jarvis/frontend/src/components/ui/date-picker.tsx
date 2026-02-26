import { useState, useEffect } from 'react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { ChevronLeft, ChevronRight, CalendarIcon, X } from 'lucide-react'
import { cn } from '@/lib/utils'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const MONTHS_FULL = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

type View = 'days' | 'months' | 'years'

export function DatePicker({
  value,
  onChange,
  placeholder = 'Pick date',
  className,
}: {
  value: string          // ISO date string "YYYY-MM-DD" or ""
  onChange: (v: string) => void
  placeholder?: string
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const today = new Date()
  const parsed = value ? new Date(value + 'T00:00:00') : null

  const [viewDate, setViewDate] = useState(() => parsed ?? today)
  const [view, setView] = useState<View>('days')

  // Sync viewDate when value changes externally
  useEffect(() => {
    if (parsed) setViewDate(parsed)
  }, [value])

  const year = viewDate.getFullYear()
  const month = viewDate.getMonth()

  // --- Day grid ---
  const firstDay = new Date(year, month, 1)
  const startWeekday = (firstDay.getDay() + 6) % 7 // Monday = 0
  const daysInMonth = new Date(year, month + 1, 0).getDate()

  const days: (number | null)[] = []
  for (let i = 0; i < startWeekday; i++) days.push(null)
  for (let d = 1; d <= daysInMonth; d++) days.push(d)

  const selectDay = (d: number) => {
    const m = String(month + 1).padStart(2, '0')
    const dd = String(d).padStart(2, '0')
    onChange(`${year}-${m}-${dd}`)
    setOpen(false)
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

  // Year grid: show 12 years centered on current
  const yearStart = year - 5
  const yearsGrid = Array.from({ length: 12 }, (_, i) => yearStart + i)

  const prevMonth = () => setViewDate(new Date(year, month - 1, 1))
  const nextMonth = () => setViewDate(new Date(year, month + 1, 1))
  const prevYear = () => setViewDate(new Date(year - 1, month, 1))
  const nextYear = () => setViewDate(new Date(year + 1, month, 1))
  const prevYearBlock = () => setViewDate(new Date(year - 12, month, 1))
  const nextYearBlock = () => setViewDate(new Date(year + 12, month, 1))

  const isToday = (d: number) =>
    d === today.getDate() && month === today.getMonth() && year === today.getFullYear()
  const isSelected = (d: number) =>
    parsed && d === parsed.getDate() && month === parsed.getMonth() && year === parsed.getFullYear()

  const displayText = parsed
    ? `${parsed.getDate()} ${MONTHS[parsed.getMonth()]} ${parsed.getFullYear()}`
    : placeholder

  return (
    <Popover open={open} onOpenChange={o => { setOpen(o); if (o) setView('days') }}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          className={cn(
            'justify-start text-left font-normal h-9 px-3',
            !parsed && 'text-muted-foreground',
            className,
          )}
        >
          <CalendarIcon className="h-3.5 w-3.5 mr-1.5 shrink-0" />
          <span className="truncate text-xs">{displayText}</span>
          {parsed && (
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
        {view === 'days' && (
          <>
            <div className="flex items-center justify-between mb-2">
              <button onClick={prevMonth} className="rounded p-1 hover:bg-accent"><ChevronLeft className="h-4 w-4" /></button>
              <button
                onClick={() => setView('months')}
                className="text-sm font-medium hover:bg-accent rounded px-2 py-1"
              >
                {MONTHS_FULL[month]} {year}
              </button>
              <button onClick={nextMonth} className="rounded p-1 hover:bg-accent"><ChevronRight className="h-4 w-4" /></button>
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
                      onClick={() => selectDay(d)}
                      className={cn(
                        'h-7 w-7 rounded-md text-xs hover:bg-accent',
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
                onClick={() => {
                  const m = String(today.getMonth() + 1).padStart(2, '0')
                  const dd = String(today.getDate()).padStart(2, '0')
                  onChange(`${today.getFullYear()}-${m}-${dd}`)
                  setOpen(false)
                }}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                Today
              </button>
              {parsed && (
                <button
                  onClick={() => { onChange(''); setOpen(false) }}
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
              <button onClick={prevYear} className="rounded p-1 hover:bg-accent"><ChevronLeft className="h-4 w-4" /></button>
              <button
                onClick={() => setView('years')}
                className="text-sm font-medium hover:bg-accent rounded px-2 py-1"
              >
                {year}
              </button>
              <button onClick={nextYear} className="rounded p-1 hover:bg-accent"><ChevronRight className="h-4 w-4" /></button>
            </div>
            <div className="grid grid-cols-3 gap-1.5">
              {MONTHS.map((m, i) => (
                <button
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
              <button onClick={prevYearBlock} className="rounded p-1 hover:bg-accent"><ChevronLeft className="h-4 w-4" /></button>
              <span className="text-sm font-medium">{yearStart} – {yearStart + 11}</span>
              <button onClick={nextYearBlock} className="rounded p-1 hover:bg-accent"><ChevronRight className="h-4 w-4" /></button>
            </div>
            <div className="grid grid-cols-3 gap-1.5">
              {yearsGrid.map(y => (
                <button
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
      </PopoverContent>
    </Popover>
  )
}
