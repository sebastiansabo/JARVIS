import { useState, useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Building2, User, FileText, Plus, Search } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useDebounce } from '@/lib/utils'
import { dmsApi } from '@/api/dms'
import type { PartySuggestion } from '@/types/dms'

interface PartyPickerProps {
  value: string
  onSelect: (s: PartySuggestion) => void
  onChange: (name: string) => void
  onCreateNew?: () => void
  placeholder?: string
  parentId?: number
}

const SOURCE_CONFIG: Record<string, { label: string; color: string; icon: typeof Building2 }> = {
  parent: { label: 'Parent', color: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400', icon: FileText },
  company: { label: 'Company', color: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400', icon: Building2 },
  supplier: { label: 'Supplier', color: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400', icon: Building2 },
  invoice: { label: 'Invoice', color: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400', icon: FileText },
}

export default function PartyPicker({ value, onSelect, onChange, onCreateNew, placeholder, parentId }: PartyPickerProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState(value)
  const inputRef = useRef<HTMLInputElement>(null)
  const debouncedSearch = useDebounce(search, 300)

  // Sync external value changes
  useEffect(() => { setSearch(value) }, [value])

  const { data, isFetching } = useQuery({
    queryKey: ['dms-party-suggest', debouncedSearch, parentId],
    queryFn: () => dmsApi.suggestParties(debouncedSearch, parentId),
    enabled: (debouncedSearch.length >= 2 || !!parentId) && open,
  })
  const suggestions: PartySuggestion[] = data?.suggestions || []

  const handleInputChange = (val: string) => {
    setSearch(val)
    onChange(val)
    if ((val.length >= 2 || parentId) && !open) setOpen(true)
    if (val.length < 2 && !parentId && open) setOpen(false)
  }

  const handleSelect = (s: PartySuggestion) => {
    setSearch(s.name)
    onSelect(s)
    setOpen(false)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground pointer-events-none" />
          <Input
            ref={inputRef}
            value={search}
            onChange={(e) => handleInputChange(e.target.value)}
            onFocus={() => { if (search.length >= 2 || parentId) setOpen(true) }}
            placeholder={placeholder || 'Search company, supplier...'}
            className="pl-8"
          />
        </div>
      </PopoverTrigger>
      <PopoverContent
        className="p-0 w-[var(--radix-popover-trigger-width)]"
        align="start"
        sideOffset={4}
        onOpenAutoFocus={(e) => e.preventDefault()}
      >
        <div className="max-h-[240px] overflow-y-auto">
          {isFetching && suggestions.length === 0 ? (
            <p className="text-sm text-muted-foreground px-3 py-2">Searching...</p>
          ) : suggestions.length === 0 && debouncedSearch.length >= 2 ? (
            <p className="text-sm text-muted-foreground px-3 py-2">No results found</p>
          ) : (
            suggestions.map((s, i) => {
              const cfg = SOURCE_CONFIG[s.source] || SOURCE_CONFIG.supplier
              const Icon = s.entity_type === 'person' ? User : cfg.icon
              return (
                <button
                  key={`${s.source}-${s.id ?? i}`}
                  className="flex items-center gap-2 w-full px-3 py-2 text-left hover:bg-accent text-sm transition-colors"
                  onClick={() => handleSelect(s)}
                >
                  <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span className="flex-1 truncate font-medium">{s.name}</span>
                  {s.cui && <span className="text-xs text-muted-foreground shrink-0">{s.cui}</span>}
                  <Badge variant="outline" className={`text-[10px] px-1.5 py-0 shrink-0 ${cfg.color}`}>
                    {cfg.label}
                  </Badge>
                </button>
              )
            })
          )}
        </div>
        {onCreateNew && (
          <div className="border-t px-2 py-1.5">
            <Button
              variant="ghost"
              size="sm"
              className="w-full justify-start text-sm"
              onClick={() => { setOpen(false); onCreateNew() }}
            >
              <Plus className="h-4 w-4 mr-1.5" />
              New Supplier
            </Button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  )
}
