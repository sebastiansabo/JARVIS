import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, ChevronsUpDown, Check, Plus, Loader2, Link2 } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { cn, useDebounce } from '@/lib/utils'
import type { FSClientSearch } from '@/api/fieldSales'
import { carparkDispoApi } from '@/api/carparkDispo'

export interface ClientSearchValue {
  id?: number | null
  name?: string | null
}

export interface ClientSearchSelection {
  id: number | null
  name: string
}

interface ClientSearchSelectProps {
  /** Currently committed selection — a CRM client (id set) or a free-text name (id null/absent). */
  value?: ClientSearchValue
  /** Tenant scope forwarded to the search API; omit to search the caller's full allowed set. */
  companyId?: number
  /** Fired when the user picks a CRM client or confirms free text. */
  onSelect: (client: ClientSearchSelection) => void
  /** Allow committing typed text that doesn't match any CRM client (walk-in buyer). Default true. */
  allowCustom?: boolean
  placeholder?: string
  searchPlaceholder?: string
  disabled?: boolean
  /** Controlled open state (e.g. to auto-open on mount for inline editing). Uncontrolled (internal state) when omitted. */
  open?: boolean
  onOpenChange?: (open: boolean) => void
  className?: string
}

/**
 * Async typeahead over crm_clients (GET /api/carpark/clients/search) — the
 * reusable client picker behind buyer fields in CarPark (Dispo table cell,
 * Sell dialog, Vânzare tab). Uses the carpark-scoped search route (not
 * /api/field-sales/clients/search) so a CarPark editor without field-sales
 * access isn't 403'd by field_sales_required; same response shape, so this
 * is otherwise unchanged. Picking a result commits `{ id, name }`; when
 * allowCustom is on, the typed text can also be committed as-is with a null
 * id so a walk-in buyer not in the CRM can still be recorded.
 *
 * Mirrors SearchSelect.tsx's controlled/uncontrolled `open` pattern so it
 * slots into EditableCell's "opens immediately in edit mode, commits on
 * pick" flow the same way SearchSelect does for the 'user' cell type.
 */
export function ClientSearchSelect({
  value,
  companyId,
  onSelect,
  allowCustom = true,
  placeholder = 'Caută client...',
  searchPlaceholder = 'Nume, companie, CUI, nr. reg...',
  disabled = false,
  open: openProp,
  onOpenChange,
  className,
}: ClientSearchSelectProps) {
  const [internalOpen, setInternalOpen] = useState(false)
  const open = openProp ?? internalOpen
  const setOpen = (v: boolean) => {
    if (openProp === undefined) setInternalOpen(v)
    onOpenChange?.(v)
  }
  const [search, setSearch] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const debouncedSearch = useDebounce(search, 300)
  const trimmedQuery = debouncedSearch.trim()
  const trimmedTyped = search.trim()

  // enabled/queryFn both gate on the 2-char floor the backend itself
  // enforces (a shorter query 400s) — never fire a doomed request.
  const { data, isFetching, isError } = useQuery({
    queryKey: ['client-search', trimmedQuery, companyId ?? null],
    queryFn: () => carparkDispoApi.searchClients(trimmedQuery, companyId),
    enabled: open && trimmedQuery.length >= 2,
    staleTime: 30_000,
    retry: false,
  })

  const results: FSClientSearch[] = data?.success ? (data.clients ?? []) : []

  const displayName = value?.name?.trim() || (value?.id != null ? `Client #${value.id}` : '')
  const isLinked = value?.id != null

  useEffect(() => {
    if (open) {
      setSearch('')
      setTimeout(() => inputRef.current?.focus(), 0)
    }
  }, [open])

  function selectClient(c: FSClientSearch) {
    onSelect({ id: c.id, name: c.display_name })
    setOpen(false)
  }

  function useCustomText() {
    if (!trimmedTyped) return
    onSelect({ id: null, name: trimmedTyped })
    setOpen(false)
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault()
      if (results.length > 0) {
        selectClient(results[0])
      } else if (allowCustom && trimmedTyped) {
        useCustomText()
      }
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setOpen(false)
    }
  }

  const showCustomOption =
    allowCustom && trimmedTyped !== '' && !results.some((r) => r.display_name.toLowerCase() === trimmedTyped.toLowerCase())

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className={cn('w-full justify-between font-normal h-9 px-3', className)}
          disabled={disabled}
        >
          <span className={cn('flex min-w-0 items-center gap-1.5 truncate', !displayName && 'text-muted-foreground')}>
            {isLinked && <Link2 className="h-3 w-3 shrink-0 text-muted-foreground" />}
            <span className="truncate">{displayName || placeholder}</span>
          </span>
          <ChevronsUpDown className="ml-1 h-3.5 w-3.5 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start" collisionPadding={8}>
        <div className="flex items-center gap-1.5 border-b px-2">
          <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <Input
            ref={inputRef}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={searchPlaceholder}
            className="h-8 flex-1 border-0 shadow-none focus-visible:ring-0 text-sm"
          />
          {isFetching && <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" />}
        </div>
        <div className="max-h-64 overflow-y-auto overscroll-contain">
          {showCustomOption && (
            <div className="border-b p-1">
              <button
                type="button"
                className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm text-primary hover:bg-accent"
                onClick={useCustomText}
              >
                <Plus className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">Folosește „{trimmedTyped}" (fără CRM)</span>
              </button>
            </div>
          )}
          {trimmedQuery.length < 2 ? (
            <div className="px-3 py-4 text-center text-sm text-muted-foreground">
              {trimmedQuery.length === 0 ? 'Scrie pentru a căuta...' : 'Minim 2 caractere'}
            </div>
          ) : isError ? (
            <div className="px-3 py-4 text-center text-sm text-muted-foreground">
              Eroare la căutare — poți folosi textul liber de mai sus.
            </div>
          ) : results.length === 0 ? (
            <div className="px-3 py-4 text-center text-sm text-muted-foreground">
              {isFetching ? 'Se caută...' : 'Niciun rezultat'}
            </div>
          ) : (
            <div className="p-1">
              {results.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className={cn(
                    'flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent',
                    value?.id === c.id && 'bg-accent',
                  )}
                  onClick={() => selectClient(c)}
                >
                  <Check className={cn('h-3.5 w-3.5 shrink-0', value?.id === c.id ? 'opacity-100' : 'opacity-0')} />
                  <div className="min-w-0">
                    <div className="truncate">{c.display_name}</div>
                    {(c.company_name || c.nr_reg || c.city) && (
                      <div className="truncate text-xs text-muted-foreground">
                        {[c.company_name, c.nr_reg, c.city].filter(Boolean).join(' · ')}
                      </div>
                    )}
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
