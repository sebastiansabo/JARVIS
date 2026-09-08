import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { foiParcursApi } from '@/api/foiParcurs'
import { useUsersDirectory } from './useUsersDirectory'
import { mergePersonOptions, type PersonSource } from './personOptions'

/** Autocomplete name field backed by the CRM client DB (/clients/search) and
 *  the internal users directory. Free-text: whatever is typed IS the value;
 *  picking a suggestion just fills the name. Used for the Client-extra "Nume
 *  client (șofer)" and the Eveniment "Șofer / consilier" fields. */
export function PersonPicker({
  value, onChange, placeholder, sources = ['clients', 'users'], className,
}: {
  value: string
  onChange: (name: string) => void
  placeholder?: string
  sources?: PersonSource[]
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const q = value.trim()

  const { data: clientRes } = useQuery({
    queryKey: ['fp-clients-search', q],
    queryFn: () => foiParcursApi.searchClients(q, 10),
    enabled: open && sources.includes('clients') && q.length >= 2,
    staleTime: 10_000,
  })
  const { users } = useUsersDirectory()

  const options = useMemo(
    () => mergePersonOptions(value, clientRes?.clients ?? [], users, { sources, limit: 8 }),
    [value, clientRes, users, sources],
  )

  return (
    <div className="relative">
      <Input
        className={className}
        placeholder={placeholder}
        value={value}
        onChange={(e) => { onChange(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        autoComplete="off"
      />
      {open && options.length > 0 && (
        <div className="absolute z-20 mt-1 w-full rounded-md border bg-popover shadow-md max-h-56 overflow-y-auto">
          {options.map((o) => (
            <button
              key={o.key}
              type="button"
              onMouseDown={(e) => { e.preventDefault(); onChange(o.name); setOpen(false) }}
              className="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent"
            >
              <span className="flex min-w-0 items-center gap-2">
                <Badge variant="outline" className="shrink-0 text-[10px]">
                  {o.kind === 'client' ? 'Client' : 'User'}
                </Badge>
                <span className="truncate">{o.name}</span>
              </span>
              {o.detail && <span className="shrink-0 text-xs text-muted-foreground">{o.detail}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
