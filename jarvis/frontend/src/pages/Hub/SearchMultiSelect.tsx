import { useState } from 'react'
import { ChevronDown, Search, Check, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

export interface MultiOption {
  value: string
  label: string
  /** Lowercase haystack the token search matches against. */
  search: string
}

/**
 * Searchable, multi-select combobox (popover + checkbox list + removable pills).
 * Used for the Driving-Sessions filters (cars, consultants) — the fleet has many
 * near-identical names, so token search across a rich haystack + selected-pills
 * is far easier to scan than a plain <select>. `value` is the set of selected
 * option values; empty = none selected (→ "all").
 */
export default function SearchMultiSelect({ options, value, onChange, allLabel, placeholder, icon: Icon, countNoun }: {
  options: MultiOption[]
  value: string[]
  onChange: (v: string[]) => void
  /** Label for the "none selected" (all) state + the reset row. */
  allLabel: string
  placeholder: string
  icon?: LucideIcon
  /** [singular, plural] noun for the "N selected" trigger label. */
  countNoun?: [string, string]
}) {
  const [q, setQ] = useState('')
  const needle = q.trim().toLowerCase()
  // Each whitespace token must match somewhere in the haystack ("audi 09").
  const filtered = needle ? options.filter((o) => needle.split(/\s+/).every((t) => o.search.includes(t))) : options
  const toggle = (val: string) => onChange(value.includes(val) ? value.filter((v) => v !== val) : [...value, val])
  const noun = countNoun ?? ['selectat', 'selectate']
  const triggerLabel = value.length === 0 ? allLabel : `${value.length} ${value.length === 1 ? noun[0] : noun[1]}`
  const Box = ({ on }: { on: boolean }) => (
    <span className={cn('flex h-4 w-4 shrink-0 items-center justify-center rounded border', on ? 'border-primary bg-primary text-primary-foreground' : 'border-input')}>{on && <Check className="h-3 w-3" />}</span>
  )
  return (
    <div className="space-y-2">
      <Popover>
        <PopoverTrigger asChild>
          <button type="button" aria-label={allLabel} className="flex h-11 w-full items-center gap-2 rounded-lg border border-input bg-background px-3 text-base shadow-sm transition-colors hover:bg-accent">
            {Icon && <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />}
            <span className="min-w-0 flex-1 truncate text-left">{triggerLabel}</span>
            {value.length > 0 && <span className="shrink-0 rounded-full bg-primary px-1.5 py-0.5 text-[11px] font-bold text-primary-foreground">{value.length}</span>}
            <ChevronDown className="h-4 w-4 shrink-0 opacity-50" />
          </button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-[min(20rem,90vw)] p-0">
          <div className="border-b p-2">
            <div className="flex h-9 items-center gap-2 rounded-lg border border-input bg-background px-2">
              <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
              <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder} className="w-full bg-transparent text-sm outline-none" />
            </div>
          </div>
          <div className="max-h-72 overflow-y-auto p-1">
            <button type="button" onClick={() => onChange([])} className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm hover:bg-accent">
              <Box on={value.length === 0} /><span className="font-medium">{allLabel}</span>
            </button>
            {filtered.map((o) => (
              <button key={o.value} type="button" onClick={() => toggle(o.value)} className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm hover:bg-accent">
                <Box on={value.includes(o.value)} /><span className="min-w-0 truncate">{o.label}</span>
              </button>
            ))}
            {filtered.length === 0 && <p className="px-2 py-6 text-center text-sm text-muted-foreground">Niciun rezultat</p>}
          </div>
        </PopoverContent>
      </Popover>

      {/* Selected options as removable pills. */}
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {value.map((val) => {
            const o = options.find((x) => x.value === val)
            return (
              <span key={val} className="inline-flex max-w-full items-center gap-1 rounded-full bg-muted py-1 pl-2.5 pr-1 text-xs font-medium">
                <span className="truncate">{o?.label ?? val}</span>
                <button type="button" aria-label={`Elimină ${o?.label ?? val}`} onClick={() => toggle(val)} className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-foreground/10 hover:text-foreground">
                  <X className="h-3 w-3" />
                </button>
              </span>
            )
          })}
          {value.length > 1 && (
            <button type="button" onClick={() => onChange([])} className="rounded-full px-2 py-1 text-xs font-medium text-muted-foreground underline-offset-2 hover:underline">Șterge tot</button>
          )}
        </div>
      )}
    </div>
  )
}
