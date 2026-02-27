import { useRef, useState } from 'react'
import { X, Search, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

export interface MultiSelectOption {
  value: number | string
  label: string
}

interface MultiSelectPillsProps {
  options: MultiSelectOption[]
  selected: (number | string)[]
  onChange: (selected: (number | string)[]) => void
  placeholder?: string
  className?: string
}

export function MultiSelectPills({
  options,
  selected,
  onChange,
  placeholder = 'Search...',
  className,
}: MultiSelectPillsProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const filtered = options.filter(
    (o) =>
      !selected.includes(o.value) &&
      o.label.toLowerCase().includes(search.toLowerCase()),
  )

  const selectedOptions = options.filter((o) => selected.includes(o.value))

  const toggle = (value: number | string) => {
    if (selected.includes(value)) {
      onChange(selected.filter((v) => v !== value))
    } else {
      onChange([...selected, value])
      setSearch('')
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            'flex min-h-[2rem] w-full flex-wrap items-center gap-1 rounded-md border border-input bg-background px-2 py-1 text-sm ring-offset-background',
            'hover:border-ring focus-within:ring-1 focus-within:ring-ring transition-colors',
            className,
          )}
          onClick={() => {
            setOpen(true)
            setTimeout(() => inputRef.current?.focus(), 0)
          }}
        >
          {selectedOptions.length === 0 && (
            <span className="text-muted-foreground text-xs py-0.5">{placeholder}</span>
          )}
          {selectedOptions.map((o) => (
            <Badge
              key={o.value}
              variant="secondary"
              className="gap-0.5 pr-0.5 text-xs font-normal"
            >
              {o.label}
              <span
                role="button"
                tabIndex={0}
                className="ml-0.5 rounded-sm p-0.5 hover:bg-muted-foreground/20 cursor-pointer"
                onClick={(e) => {
                  e.stopPropagation()
                  toggle(o.value)
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') { e.stopPropagation(); toggle(o.value) }
                }}
              >
                <X className="h-3 w-3" />
              </span>
            </Badge>
          ))}
          <ChevronDown className="ml-auto h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        className="w-[var(--radix-popover-trigger-width)] p-0"
        align="start"
        onOpenAutoFocus={(e) => e.preventDefault()}
      >
        <div className="flex items-center gap-1.5 border-b px-2 py-1.5">
          <Search className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          <input
            ref={inputRef}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={placeholder}
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        </div>
        <div className="max-h-44 overflow-y-auto p-1">
          {filtered.length === 0 && (
            <p className="py-2 text-center text-xs text-muted-foreground">No results</p>
          )}
          {filtered.map((o) => (
            <button
              key={o.value}
              type="button"
              className="flex w-full items-center rounded-sm px-2 py-1.5 text-sm hover:bg-accent hover:text-accent-foreground cursor-pointer"
              onClick={() => toggle(o.value)}
            >
              {o.label}
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}
