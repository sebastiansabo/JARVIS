import { useState, useRef, useEffect } from 'react'
import { Search, ChevronsUpDown, Check, Plus } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface SearchSelectProps {
  value: string
  onValueChange: (value: string) => void
  options: { value: string; label: string; sublabel?: string }[]
  placeholder?: string
  searchPlaceholder?: string
  emptyMessage?: string
  /** Allow typing a custom value not in the list */
  allowCustom?: boolean
  disabled?: boolean
}

export function SearchSelect({
  value,
  onValueChange,
  options,
  placeholder = 'Select...',
  searchPlaceholder = 'Search...',
  emptyMessage = 'No results.',
  allowCustom = false,
  disabled = false,
}: SearchSelectProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const selected = options.find((o) => o.value === value)
  // If allowCustom and value is set but not in options, show the raw value
  const displayLabel = selected?.label ?? (allowCustom && value ? value : undefined)

  const filtered = search
    ? options.filter((o) =>
        o.label.toLowerCase().includes(search.toLowerCase()) ||
        (o.sublabel?.toLowerCase().includes(search.toLowerCase()) ?? false),
      )
    : options

  // Show "use custom" option when allowCustom is on, search has text, and no exact match
  const showCustomOption =
    allowCustom && search.trim() !== '' && !options.some((o) => o.label.toLowerCase() === search.trim().toLowerCase())

  useEffect(() => {
    if (open) {
      setSearch('')
      setTimeout(() => inputRef.current?.focus(), 0)
    }
  }, [open])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && allowCustom && search.trim()) {
      e.preventDefault()
      // Pick the first filtered option, or use the custom text
      if (filtered.length > 0 && !showCustomOption) {
        onValueChange(filtered[0].value)
      } else {
        onValueChange(search.trim())
      }
      setOpen(false)
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between font-normal h-9 px-3"
          disabled={disabled}
        >
          <span className={cn('truncate', !displayLabel && 'text-muted-foreground')}>
            {displayLabel ?? placeholder}
          </span>
          <ChevronsUpDown className="ml-1 h-3.5 w-3.5 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
        <div className="flex items-center border-b px-2">
          <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <Input
            ref={inputRef}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={searchPlaceholder}
            className="h-8 border-0 shadow-none focus-visible:ring-0 text-sm"
          />
        </div>
        <div className="max-h-48 overflow-y-auto overscroll-contain">
          {showCustomOption && (
            <div className="p-1 border-b">
              <button
                className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent text-primary"
                onClick={() => {
                  onValueChange(search.trim())
                  setOpen(false)
                }}
              >
                <Plus className="h-3.5 w-3.5 shrink-0" />
                <span>"{search.trim()}"</span>
              </button>
            </div>
          )}
          {filtered.length === 0 && !showCustomOption ? (
            <div className="px-3 py-4 text-center text-sm text-muted-foreground">{emptyMessage}</div>
          ) : (
            <div className="p-1">
              {filtered.map((o) => (
                <button
                  key={o.value}
                  className={cn(
                    'flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent',
                    o.value === value && 'bg-accent',
                  )}
                  onClick={() => {
                    onValueChange(o.value)
                    setOpen(false)
                  }}
                >
                  <Check className={cn('h-3.5 w-3.5 shrink-0', o.value === value ? 'opacity-100' : 'opacity-0')} />
                  <div className="min-w-0">
                    <div className="truncate">{o.label}</div>
                    {o.sublabel && <div className="truncate text-xs text-muted-foreground">{o.sublabel}</div>}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
