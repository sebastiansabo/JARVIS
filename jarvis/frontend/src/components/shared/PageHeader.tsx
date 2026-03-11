import { useState, useRef, useEffect, useCallback } from 'react'
import { ChevronRight, Search, FileText, X } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { Input } from '@/components/ui/input'

interface Breadcrumb {
  label: string
  shortLabel?: string
  href?: string
}

interface PageHeaderProps {
  title: React.ReactNode
  description?: React.ReactNode
  breadcrumbs?: Breadcrumb[]
  actions?: React.ReactNode
  showSearch?: boolean
}

/* ── Global Search Bar ── */
function HeaderSearchBar({ compact }: { compact?: boolean }) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<{ id: number; invoice_number: string; supplier: string; invoice_value: number; currency: string }[]>([])
  const [open, setOpen] = useState(false)
  const [searching, setSearching] = useState(false)
  const [selectedIdx, setSelectedIdx] = useState(-1)
  const wrapperRef = useRef<HTMLDivElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null)

  const doSearch = useCallback(async (q: string) => {
    if (q.trim().length < 2) { setResults([]); setOpen(false); return }
    setSearching(true)
    try {
      const { invoicesApi } = await import('@/api/invoices')
      const data = await invoicesApi.searchInvoices(q, 10)
      setResults(Array.isArray(data) ? data : [])
      setOpen(true)
    } catch (_) { setResults([]); setOpen(false) }
    finally { setSearching(false) }
  }, [])

  const handleChange = (val: string) => {
    setQuery(val)
    setSelectedIdx(-1)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => doSearch(val), 300)
  }

  const handleSelect = (id: number) => {
    setOpen(false)
    setQuery('')
    setResults([])
    navigate(`/app/accounting?invoice=${id}`)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!open || results.length === 0) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setSelectedIdx(i => Math.min(i + 1, results.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setSelectedIdx(i => Math.max(i - 1, 0)) }
    else if (e.key === 'Enter' && selectedIdx >= 0) { e.preventDefault(); handleSelect(results[selectedIdx].id) }
    else if (e.key === 'Escape') { setOpen(false) }
  }

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div ref={wrapperRef} className={`relative ${compact ? 'w-full' : 'w-56 lg:w-72'}`}>
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
        <Input
          placeholder="Search supplier or invoice..."
          value={query}
          onChange={e => handleChange(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => { if (results.length > 0) setOpen(true) }}
          className={`pl-8 ${compact ? 'h-8 text-sm' : 'h-9 text-sm'} ${query ? 'pr-8' : ''}`}
        />
        {query && (
          <button onClick={() => { setQuery(''); setResults([]); setOpen(false) }} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
      {open && (
        <div className="absolute top-full left-0 right-0 z-50 mt-1 rounded-md border bg-popover shadow-lg overflow-hidden">
          {searching && <div className="px-3 py-2 text-xs text-muted-foreground">Searching...</div>}
          {!searching && results.length === 0 && <div className="px-3 py-2 text-xs text-muted-foreground">No invoices found</div>}
          {results.map((inv, i) => (
            <button
              key={inv.id}
              onClick={() => handleSelect(inv.id)}
              className={`flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm hover:bg-accent transition-colors ${i === selectedIdx ? 'bg-accent' : ''}`}
            >
              <FileText className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="font-medium truncate">{inv.invoice_number}</div>
                <div className="text-xs text-muted-foreground truncate">{inv.supplier}</div>
              </div>
              <span className="text-xs text-muted-foreground whitespace-nowrap">
                {new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2 }).format(inv.invoice_value)} {inv.currency}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export function PageHeader({ title, description, breadcrumbs, actions, showSearch = true }: PageHeaderProps) {
  const isMobile = useIsMobile()

  /* ── Mobile: stacked layout ── */
  if (isMobile && breadcrumbs && breadcrumbs.length > 1) {
    const parentCrumbs = breadcrumbs.slice(0, -1)
    const current = breadcrumbs[breadcrumbs.length - 1]
    return (
      <div className="space-y-3">
        <nav className="flex items-center gap-1.5 text-sm text-muted-foreground">
          {parentCrumbs.map((crumb, i) => (
            <span key={i} className="flex items-center gap-1.5">
              {i > 0 && <ChevronRight className="h-3 w-3 text-muted-foreground/50" />}
              {crumb.href ? (
                <Link to={crumb.href} className="hover:text-foreground transition-colors">
                  {crumb.shortLabel || crumb.label}
                </Link>
              ) : (
                <span>{crumb.shortLabel || crumb.label}</span>
              )}
            </span>
          ))}
        </nav>
        <h1 className="text-xl font-semibold tracking-tight truncate">{current.label}</h1>
        {showSearch && <HeaderSearchBar compact />}
        {description && <div className="text-sm text-muted-foreground">{description}</div>}
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
    )
  }

  /* ── Desktop: inline layout ── */
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="flex items-center gap-4 min-w-0">
        <div className="min-w-0 shrink-0">
          {breadcrumbs && breadcrumbs.length > 0 ? (
            <h1 className="flex items-center gap-1.5 flex-wrap">
              {breadcrumbs.map((crumb, i) => {
                const text = crumb.label
                return (
                <span key={i} className="flex items-center gap-1.5">
                  {i > 0 && <ChevronRight className="h-4 w-4 text-muted-foreground/50 shrink-0" />}
                  {i < breadcrumbs.length - 1 ? (
                    crumb.href ? (
                      <Link to={crumb.href} className="text-muted-foreground hover:text-foreground transition-colors text-base sm:text-lg font-medium">
                        {text}
                      </Link>
                    ) : (
                      <span className="text-muted-foreground text-base sm:text-lg font-medium">{text}</span>
                    )
                  ) : (
                    <span className="text-xl sm:text-2xl font-semibold tracking-tight">{text}</span>
                  )}
                </span>
              )})}
            </h1>
          ) : (
            <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">{title}</h1>
          )}
          {description && <p className="text-sm text-muted-foreground">{description}</p>}
        </div>
        {showSearch && <HeaderSearchBar />}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  )
}
