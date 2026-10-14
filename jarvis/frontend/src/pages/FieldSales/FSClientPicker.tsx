import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Search, X, UserPlus, Plus } from 'lucide-react'
import { cn } from '@/lib/utils'
import { fieldSalesApi, type FSClientSearch, type CreateFSClientPayload } from '@/api/fieldSales'

const inputClass =
  'h-11 w-full rounded-xl border border-border bg-background px-3 text-base placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-teal-600/40'

/** Tenant-scoped search-or-create client control. Pick-and-forget: calls
 *  onPick({id, display_name}) and resets its own state. Rendered inline so it
 *  can live inside another overlay without sheet-on-sheet. */
export default function FSClientPicker({ companyId, onPick, autoFocus }: {
  companyId: number
  onPick: (client: { id: number; display_name: string }) => void
  autoFocus?: boolean
}) {
  const [mode, setMode] = useState<'search' | 'create'>('search')
  const [query, setQuery] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['fs-client-search', query, companyId],
    queryFn: () => fieldSalesApi.searchClients(query, companyId),
    // Never run unscoped (search endpoint has no ownership clause) or on <2 chars.
    enabled: query.length >= 2 && companyId > 0,
  })
  const results: FSClientSearch[] = data?.clients ?? []

  const pick = (c: { id: number; display_name: string }) => {
    onPick({ id: c.id, display_name: c.display_name })
    setQuery('')
    setMode('search')
  }

  if (mode === 'create') {
    return <ClientCreateForm companyId={companyId} onCancel={() => setMode('search')} onPicked={pick} />
  }

  return (
    <div className="space-y-2">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <input
          autoFocus={autoFocus}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Cauta client dupa nume sau CUI..."
          className={cn(inputClass, 'pl-9 pr-9')}
        />
        {query && (
          <button onClick={() => setQuery('')} className="absolute right-3 top-1/2 -translate-y-1/2">
            <X className="h-4 w-4 text-muted-foreground" />
          </button>
        )}
      </div>

      <button
        onClick={() => setMode('create')}
        className="flex w-full items-center justify-center gap-2 rounded-xl border border-border py-2.5 text-sm font-semibold active:bg-muted"
      >
        <UserPlus className="h-4 w-4" /> Client nou
      </button>

      {query.length >= 2 && (
        <div className="max-h-48 overflow-y-auto rounded-xl border border-border bg-card">
          {isLoading && (
            <div className="flex items-center justify-center py-4">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-foreground" />
            </div>
          )}
          {!isLoading && results.length === 0 && (
            <p className="px-3 py-3 text-xs text-muted-foreground">Niciun client gasit. Creeaza unul nou.</p>
          )}
          {!isLoading && results.map((c) => (
            <button
              key={c.id}
              onClick={() => pick(c)}
              className="w-full border-b border-border/50 px-3 py-2.5 text-left last:border-0 hover:bg-secondary active:bg-secondary"
            >
              <p className="text-sm font-medium">{c.display_name}</p>
              <p className="text-xs text-muted-foreground">
                {c.client_type === 'company' ? 'Firma' : 'Persoana fizica'}{c.city ? ` - ${c.city}` : ''}
              </p>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function ClientCreateForm({ companyId, onCancel, onPicked }: {
  companyId: number
  onCancel: () => void
  onPicked: (c: { id: number; display_name: string }) => void
}) {
  const [displayName, setDisplayName] = useState('')
  const [cui, setCui] = useState('')
  const [phone, setPhone] = useState('')
  const [city, setCity] = useState('')
  const [dup, setDup] = useState<{ id: number; display_name: string } | null>(null)

  const mut = useMutation({
    mutationFn: (data: CreateFSClientPayload) => fieldSalesApi.createClient(data),
    onSuccess: (res) => {
      if (res.duplicate) { setDup({ id: res.client.id, display_name: res.client.display_name }); return }
      onPicked({ id: res.client.id, display_name: res.client.display_name })
    },
  })
  const err = mut.error as { data?: { error?: string } } | null

  const submit = () => {
    if (mut.isPending || displayName.trim().length === 0) return
    mut.mutate({
      display_name: displayName.trim(),
      cui: cui.trim() || undefined,
      phone: phone.trim() || undefined,
      city: city.trim() || undefined,
      client_type: cui.trim() ? 'company' : 'person',
      company_id: companyId,
    })
  }

  if (dup) {
    return (
      <div className="space-y-3">
        <p className="rounded-xl border border-border bg-card p-3 text-sm">
          <span className="font-medium">{dup.display_name}</span>
          <br />
          <span className="text-muted-foreground">Există deja un client cu acest nume — a fost selectat cel existent.</span>
        </p>
        <button
          onClick={() => onPicked(dup)}
          className="h-11 w-full rounded-xl bg-teal-600 text-base font-semibold text-white active:bg-teal-700"
        >
          Continua
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Nume client *" className={inputClass} />
      <input value={cui} onChange={(e) => setCui(e.target.value)} placeholder="CUI (optional)" className={inputClass} />
      <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Telefon (optional)" className={inputClass} />
      <input value={city} onChange={(e) => setCity(e.target.value)} placeholder="Oras (optional)" className={inputClass} />
      {mut.isError && <p className="text-xs text-destructive">{err?.data?.error ?? 'Crearea clientului a esuat'}</p>}
      <div className="grid grid-cols-2 gap-2">
        <button onClick={onCancel} className="h-11 rounded-xl border border-border text-base font-semibold active:bg-muted">Inapoi</button>
        <button
          onClick={submit}
          disabled={mut.isPending || displayName.trim().length === 0}
          className={cn(
            'flex h-11 items-center justify-center gap-2 rounded-xl text-base font-semibold text-white',
            !mut.isPending && displayName.trim().length > 0 ? 'bg-teal-600 active:bg-teal-700' : 'bg-muted-foreground/40 cursor-not-allowed',
          )}
        >
          <Plus className="h-4 w-4" /> {mut.isPending ? 'Se creeaza...' : 'Creeaza'}
        </button>
      </div>
    </div>
  )
}
