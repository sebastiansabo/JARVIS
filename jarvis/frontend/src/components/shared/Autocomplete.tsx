import { useMemo, useRef, useState } from 'react'
import { Plus } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Input } from '@/components/ui/input'

/** Diacritic- and case-insensitive normalizer for fuzzy matching (ș→s, ț→t, …). */
function norm(s: string): string {
  return s
    .replace(/ş/g, 's').replace(/ţ/g, 't').replace(/Ş/g, 'S').replace(/Ţ/g, 'T')
    .normalize('NFKD').replace(/[̀-ͯ]/g, '')
    .toLowerCase().trim()
}

/** Type-and-suggest text input over a fixed option list. Free typing is allowed
 *  (value updates on every keystroke); clicking a suggestion calls `onSelect`.
 *  Diacritic-insensitive matching so "iasi" finds "Iași". Ported from the
 *  mobile app so client-registration forms stay consistent across platforms. */
export function Autocomplete({
  value,
  onChange,
  onSelect,
  options,
  placeholder,
  invalid,
  disabled,
  max = 8,
  allowCreate = false,
  canonicalize = false,
}: {
  value: string
  onChange: (v: string) => void
  onSelect: (v: string) => void
  options: string[]
  placeholder?: string
  invalid?: boolean
  disabled?: boolean
  max?: number
  /** When true, a custom (non-matching) value shows an "Adaugă «…»" row that
   *  commits the typed text via onSelect. Off by default so existing pickers
   *  that must stay within their option list are unchanged. */
  allowCreate?: boolean
  /** When true, on blur a value that case/diacritic-insensitively matches an
   *  option snaps to that option's exact casing (typed "NISSAN" → "Nissan").
   *  Off by default. */
  canonicalize?: boolean
}) {
  const [open, setOpen] = useState(false)
  const blurTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const matches = useMemo(() => {
    const q = norm(value)
    const pool = q
      ? options.filter((o) => norm(o).includes(q) && norm(o) !== q)
      : options
    return pool.slice(0, max)
  }, [value, options, max])

  // Offer to add the typed value when it's non-empty and not already an exact option.
  const trimmed = value.trim()
  const showCreate =
    allowCreate && trimmed !== '' && !options.some((o) => norm(o) === norm(trimmed))

  const showList = open && !disabled && (matches.length > 0 || showCreate)

  return (
    <div className="relative">
      <Input
        type="text"
        value={value}
        disabled={disabled}
        onChange={(e) => {
          onChange(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          // delay so a suggestion click registers before the list unmounts
          blurTimer.current = setTimeout(() => {
            setOpen(false)
            if (canonicalize && value.trim() !== '') {
              const hit = options.find((o) => norm(o) === norm(value))
              if (hit && hit !== value) onSelect(hit)
            }
          }, 120)
        }}
        placeholder={placeholder}
        className={cn(invalid && 'ring-2 ring-destructive')}
      />
      {showList && (
        <ul className="absolute z-50 mt-1 w-full max-h-56 overflow-auto rounded-md border bg-popover shadow-md">
          {matches.map((opt) => (
            <li key={opt}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  if (blurTimer.current) clearTimeout(blurTimer.current)
                  onSelect(opt)
                  setOpen(false)
                }}
                className="w-full px-3 py-2 text-left text-sm hover:bg-accent transition-colors"
              >
                {opt}
              </button>
            </li>
          ))}
          {showCreate && (
            <li className={cn(matches.length > 0 && 'border-t')}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  if (blurTimer.current) clearTimeout(blurTimer.current)
                  onSelect(trimmed)
                  setOpen(false)
                }}
                className="flex w-full items-center gap-1.5 px-3 py-2 text-left text-sm text-primary hover:bg-accent transition-colors"
              >
                <Plus className="h-3.5 w-3.5" />
                Adaugă „{trimmed}"
              </button>
            </li>
          )}
        </ul>
      )}
    </div>
  )
}
