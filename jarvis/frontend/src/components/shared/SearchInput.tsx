import { useState, useEffect, useRef } from 'react'
import { Search, X } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface SearchInputProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  debounceMs?: number
  className?: string
  /** When true, renders as a search icon button that expands to input on click */
  collapsible?: boolean
  autoFocus?: boolean
}

export function SearchInput({
  value,
  onChange,
  placeholder = 'Search...',
  debounceMs = 300,
  className,
  collapsible = false,
  autoFocus = false,
}: SearchInputProps) {
  const [localValue, setLocalValue] = useState(value)
  const [expanded, setExpanded] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setLocalValue(value)
  }, [value])

  useEffect(() => {
    if (expanded && inputRef.current) {
      inputRef.current.focus()
    }
  }, [expanded])

  const handleChange = (newValue: string) => {
    setLocalValue(newValue)
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => onChange(newValue), debounceMs)
  }

  const clear = () => {
    setLocalValue('')
    onChange('')
  }

  const collapse = () => {
    setExpanded(false)
    clear()
  }

  if (collapsible && !expanded) {
    return (
      <Button
        variant="ghost"
        size="icon"
        onClick={() => setExpanded(true)}
        title="Search"
        className={cn(value ? 'text-primary' : '', className)}
      >
        <Search className="h-4 w-4" />
      </Button>
    )
  }

  return (
    <div className={cn('relative flex items-center', collapsible ? 'gap-1' : '', className)}>
      <div className="relative">
        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input
          ref={inputRef}
          value={localValue}
          onChange={(e) => handleChange(e.target.value)}
          placeholder={placeholder}
          className={cn('pl-8 pr-8', collapsible ? 'w-36' : '')}
          autoFocus={autoFocus}
        />
        {localValue && (
          <button onClick={clear} aria-label="Clear search" className="absolute right-2.5 top-2.5 text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
      {collapsible && (
        <Button variant="ghost" size="icon" onClick={collapse} title="Close search">
          <X className="h-4 w-4" />
        </Button>
      )}
    </div>
  )
}
