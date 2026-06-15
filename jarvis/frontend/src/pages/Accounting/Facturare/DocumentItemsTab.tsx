import { useState, useEffect, useCallback } from 'react'
import { toast } from 'sonner'
import { Loader2, Download, FileSpreadsheet, ArrowUp, ArrowDown, ArrowUpDown } from 'lucide-react'

import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { ColumnToggle, useColumnState, type ColumnDef } from '@/components/shared/ColumnToggle'

interface DocItem {
  invoice_id: number
  invoice_type: string
  sequence_number: number
  doc_number: number | null
  car_index: number
  issued_date: string | null
  kurs_applied: number | null
  intocmit_de: string | null
  contract_ref: string
  anexa_number: number
  supplier_name: string
  customer_name: string
  nr_comanda: string | null
  model: string
  culoare: string | null
  vin: string | null
  unit_price: number
  doc_amount: number
  notes: string | null
  payment_status: string
}

function fmtEur(n: number) {
  return new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n)
}

type SortField = 'doc_number' | 'date' | 'customer' | 'contract' | 'model' | 'amount'
type SortDir = 'asc' | 'desc'

function getParam(key: string, fallback: string) {
  return new URLSearchParams(window.location.search).get(key) || fallback
}
function setParam(key: string, value: string) {
  const url = new URL(window.location.href)
  if (value && value !== 'all' && value !== '') url.searchParams.set(key, value)
  else url.searchParams.delete(key)
  window.history.replaceState({}, '', url.toString())
}

// ── Column definitions ──────────────────────────────────────────

const TYPE_BADGES: Record<string, { label: string; color: string }> = {
  PROFORMA: { label: 'Proforma', color: 'bg-blue-100 text-blue-800' },
  INVOICE: { label: 'Factura', color: 'bg-amber-100 text-amber-800' },
  STORNO: { label: 'Storno', color: 'bg-red-100 text-red-800' },
  FINAL: { label: 'Final', color: 'bg-emerald-100 text-emerald-800' },
}

const ALL_COLUMNS: ColumnDef<DocItem>[] = [
  { key: 'type', label: 'Type', render: (item) => {
    const b = TYPE_BADGES[item.invoice_type]
    return b ? <span className={`inline-block px-1.5 py-0.5 rounded font-medium ${b.color}`}>{b.label} #{item.sequence_number}</span> : item.invoice_type
  }},
  { key: 'doc_number', label: 'No.', render: (item) => <span className="font-mono">{item.doc_number || '—'}</span> },
  { key: 'date', label: 'Date', render: (item) => (
    <span className="text-muted-foreground">{item.issued_date ? new Date(item.issued_date).toLocaleDateString('ro-RO', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '—'}</span>
  )},
  { key: 'company', label: 'Company', render: (item) => <span className="text-muted-foreground max-w-[120px] truncate block">{item.supplier_name}</span> },
  { key: 'client', label: 'Client', render: (item) => <span className="font-medium max-w-[140px] truncate block">{item.customer_name}</span> },
  { key: 'contract', label: 'Contract', render: (item) => item.contract_ref },
  { key: 'anexa', label: 'Anexa', className: 'text-center', render: (item) => item.anexa_number },
  { key: 'nr_comanda', label: 'Nr. Cmd', render: (item) => <span className="font-mono text-muted-foreground">{item.nr_comanda || '—'}</span> },
  { key: 'vehicle', label: 'Vehicle', render: (item) => (
    <span className="max-w-[180px] truncate block">{item.model}{item.culoare && ` (${item.culoare})`}</span>
  )},
  { key: 'vin', label: 'VIN', render: (item) => (
    <span className="text-muted-foreground max-w-[140px] truncate block">{item.vin || <span className="text-amber-500 italic">no VIN</span>}</span>
  )},
  { key: 'unit_price', label: 'Unit Price', className: 'text-right', render: (item) => <span className="font-mono">{fmtEur(item.unit_price)}</span> },
  { key: 'amount', label: 'Invoice EUR', className: 'text-right', render: (item) => <span className="font-mono font-medium">{fmtEur(item.doc_amount)}</span> },
  { key: 'kurs', label: 'Kurs', render: (item) => <span className="text-muted-foreground">{item.kurs_applied || '—'}</span> },
  { key: 'intocmit', label: 'Intocmit', render: (item) => <span className="text-muted-foreground italic max-w-[100px] truncate block">{item.intocmit_de || '—'}</span> },
  { key: 'payment', label: 'Payment', render: () => null },  // rendered manually with dropdown
]

const PAYMENT_CONFIG: Record<string, { label: string; color: string }> = {
  UNPAID: { label: 'Unpaid', color: 'bg-red-100 text-red-800' },
  PARTIAL: { label: 'Partial', color: 'bg-amber-100 text-amber-800' },
  PAID: { label: 'Paid', color: 'bg-emerald-100 text-emerald-800' },
}

const DEFAULT_VISIBLE = ['type', 'doc_number', 'date', 'client', 'contract', 'nr_comanda', 'vehicle', 'vin', 'amount', 'kurs', 'intocmit', 'payment']
const LOCKED_COLUMNS = new Set(['type', 'amount'])

const SORT_FIELD_MAP: Record<string, SortField> = {
  doc_number: 'doc_number', date: 'date', client: 'customer', contract: 'contract', vehicle: 'model', amount: 'amount',
}

// ── Component ───────────────────────────────────────────────────

export default function DocumentItemsTab({ docType, archived = false }: { docType: string; archived?: boolean }) {
  const [items, setItems] = useState<DocItem[]>([])
  const [loading, setLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState(() => getParam('q', ''))
  const [filterCompany, setFilterCompany] = useState(() => getParam('company', 'all'))
  const [filterClient, setFilterClient] = useState(() => getParam('client', 'all'))
  const [dateFrom, setDateFrom] = useState(() => getParam('from', ''))
  const [dateTo, setDateTo] = useState(() => getParam('to', ''))
  const [datePeriod, setDatePeriod] = useState(() => getParam('period', 'all'))
  const [sortField, setSortField] = useState<SortField>(() => getParam('sort', 'doc_number') as SortField)
  const [sortDir, setSortDir] = useState<SortDir>(() => getParam('dir', 'desc') as SortDir)

  const { visibleColumns, setVisibleColumns, defaultColumns } = useColumnState(
    'facturare-invoices-columns', DEFAULT_VISIBLE, ALL_COLUMNS.map(c => c.key))

  useEffect(() => { setParam('q', searchQuery) }, [searchQuery])
  useEffect(() => { setParam('company', filterCompany) }, [filterCompany])
  useEffect(() => { setParam('client', filterClient) }, [filterClient])
  useEffect(() => { setParam('from', dateFrom) }, [dateFrom])
  useEffect(() => { setParam('to', dateTo) }, [dateTo])
  useEffect(() => { setParam('period', datePeriod) }, [datePeriod])
  useEffect(() => { setParam('sort', sortField) }, [sortField])
  useEffect(() => { setParam('dir', sortDir) }, [sortDir])

  const applyPeriod = (period: string) => {
    setDatePeriod(period)
    if (period === 'all') { setDateFrom(''); setDateTo(''); return }
    const now = new Date()
    const y = now.getFullYear(), m = now.getMonth()
    let from: Date, to: Date
    switch (period) {
      case 'this-month': from = new Date(y, m, 1); to = new Date(y, m + 1, 0); break
      case 'last-month': from = new Date(y, m - 1, 1); to = new Date(y, m, 0); break
      case 'this-quarter': { const q = Math.floor(m / 3) * 3; from = new Date(y, q, 1); to = new Date(y, q + 3, 0); break }
      case 'last-quarter': { const q = Math.floor(m / 3) * 3 - 3; from = new Date(y, q, 1); to = new Date(y, q + 3, 0); break }
      case 'this-year': from = new Date(y, 0, 1); to = new Date(y, 11, 31); break
      case 'last-year': from = new Date(y - 1, 0, 1); to = new Date(y - 1, 11, 31); break
      default: return
    }
    setDateFrom(from.toISOString().split('T')[0])
    setDateTo(to.toISOString().split('T')[0])
  }

  const load = useCallback(() => {
    setLoading(true)
    fetch(`/facturare/api/document-items?type=${docType}${archived ? '&archived=true' : ''}`)
      .then(r => r.ok ? r.json() : { items: [] })
      .then(data => setItems(data.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [docType, archived])

  useEffect(() => { load() }, [load])

  const uniqueCompanies = [...new Set(items.map(i => i.supplier_name))].sort()
  const uniqueClients = [...new Set(items.map(i => i.customer_name))].sort()

  const filtered = items.filter(i => {
    if (filterCompany !== 'all' && i.supplier_name !== filterCompany) return false
    if (filterClient !== 'all' && i.customer_name !== filterClient) return false
    if (dateFrom && (!i.issued_date || i.issued_date < dateFrom)) return false
    if (dateTo && (!i.issued_date || i.issued_date > dateTo)) return false
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      if (
        !(i.contract_ref || '').toLowerCase().includes(q) &&
        !(i.customer_name || '').toLowerCase().includes(q) &&
        !(i.model || '').toLowerCase().includes(q) &&
        !(i.vin || '').toLowerCase().includes(q) &&
        !(i.nr_comanda || '').toLowerCase().includes(q) &&
        !String(i.doc_number || '').includes(q)
      ) return false
    }
    return true
  })

  const sorted = [...filtered].sort((a, b) => {
    let cmp = 0
    switch (sortField) {
      case 'doc_number': cmp = (a.doc_number || 0) - (b.doc_number || 0); break
      case 'date': cmp = (a.issued_date || '').localeCompare(b.issued_date || ''); break
      case 'customer': cmp = a.customer_name.localeCompare(b.customer_name); break
      case 'contract': cmp = a.contract_ref.localeCompare(b.contract_ref); break
      case 'model': cmp = a.model.localeCompare(b.model); break
      case 'amount': cmp = a.doc_amount - b.doc_amount; break
    }
    return sortDir === 'asc' ? cmp : -cmp
  })

  const toggleSort = (colKey: string) => {
    const sf = SORT_FIELD_MAP[colKey]
    if (!sf) return
    if (sortField === sf) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortField(sf); setSortDir('desc') }
  }

  const SortIcon = ({ colKey }: { colKey: string }) => {
    const sf = SORT_FIELD_MAP[colKey]
    if (!sf) return null
    return (
      <span className="inline-flex ml-0.5">{sortField === sf
        ? (sortDir === 'asc' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)
        : <ArrowUpDown className="h-3 w-3 opacity-30" />}</span>
    )
  }

  const totalAmount = sorted.reduce((s, i) => s + i.doc_amount, 0)
  const activeColumns = ALL_COLUMNS.filter(c => visibleColumns.includes(c.key))
  const colCount = activeColumns.length + 1 // +1 for actions column

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <Input placeholder="Search..." value={searchQuery} onChange={e => setSearchQuery(e.target.value)} className="w-48" />
          <Select value={filterCompany} onValueChange={setFilterCompany}>
            <SelectTrigger className="w-44"><SelectValue placeholder="Company" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Companies</SelectItem>
              {uniqueCompanies.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={filterClient} onValueChange={setFilterClient}>
            <SelectTrigger className="w-44"><SelectValue placeholder="Client" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Clients</SelectItem>
              {uniqueClients.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={datePeriod} onValueChange={applyPeriod}>
            <SelectTrigger className="w-40"><SelectValue placeholder="Period" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Time</SelectItem>
              <SelectItem value="this-month">This Month</SelectItem>
              <SelectItem value="last-month">Last Month</SelectItem>
              <SelectItem value="this-quarter">This Quarter</SelectItem>
              <SelectItem value="last-quarter">Last Quarter</SelectItem>
              <SelectItem value="this-year">This Year</SelectItem>
              <SelectItem value="last-year">Last Year</SelectItem>
              {datePeriod === 'custom' && <SelectItem value="custom">Custom</SelectItem>}
            </SelectContent>
          </Select>
          {(filterCompany !== 'all' || filterClient !== 'all' || searchQuery || dateFrom || dateTo) && (
            <Button variant="ghost" size="sm" className="text-xs" onClick={() => { setFilterCompany('all'); setFilterClient('all'); setSearchQuery(''); applyPeriod('all') }}>
              Clear
            </Button>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">{sorted.length} items</span>
          <span className="text-sm font-mono font-medium">{fmtEur(totalAmount)} EUR</span>
          <ColumnToggle
            visibleColumns={visibleColumns}
            defaultColumns={defaultColumns}
            columnDefs={ALL_COLUMNS as ColumnDef<never>[]}
            lockedColumns={LOCKED_COLUMNS}
            onChange={setVisibleColumns}
          />
        </div>
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  {activeColumns.map(col => {
                    const sortable = !!SORT_FIELD_MAP[col.key]
                    return (
                      <th key={col.key}
                        className={`px-3 py-2.5 font-medium text-xs ${col.className || 'text-left'} ${sortable ? 'cursor-pointer select-none hover:bg-muted/80' : ''}`}
                        onClick={sortable ? () => toggleSort(col.key) : undefined}>
                        {col.label} {sortable && <SortIcon colKey={col.key} />}
                      </th>
                    )
                  })}
                  <th className="w-16"></th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr><td colSpan={colCount} className="text-center py-8"><Loader2 className="h-5 w-5 animate-spin inline" /></td></tr>
                )}
                {!loading && sorted.length === 0 && (
                  <tr><td colSpan={colCount} className="text-center py-8 text-muted-foreground">No invoices found</td></tr>
                )}
                {sorted.map((item, idx) => (
                  <tr key={`${item.invoice_id}-${item.nr_comanda}-${idx}`} className="border-b hover:bg-muted/30">
                    {activeColumns.map(col => (
                      <td key={col.key} className={`px-3 py-2 text-xs ${col.className || ''}`}>
                        {col.key === 'payment' ? (() => {
                          if (item.invoice_type === 'PROFORMA') return <span className="text-muted-foreground">—</span>
                          const ps = PAYMENT_CONFIG[item.payment_status] || PAYMENT_CONFIG.UNPAID
                          return (
                            <Select value={item.payment_status || 'UNPAID'} onValueChange={async (v) => {
                              try {
                                const res = await fetch(`/facturare/api/invoices/${item.invoice_id}/payment-status`, {
                                  method: 'PATCH', headers: { 'Content-Type': 'application/json' },
                                  body: JSON.stringify({ payment_status: v }),
                                })
                                if (!res.ok) throw new Error('Failed')
                                load()
                              } catch { toast.error('Failed to update') }
                            }}>
                              <SelectTrigger className="h-6 w-[90px] text-xs border-0 p-0">
                                <span className={`inline-block px-1.5 py-0.5 rounded text-xs ${ps.color}`}>{ps.label}</span>
                              </SelectTrigger>
                              <SelectContent>
                                {Object.entries(PAYMENT_CONFIG).map(([k, v]) => (
                                  <SelectItem key={k} value={k}>
                                    <span className={`inline-block px-1 py-0.5 rounded text-xs ${v.color}`}>{v.label}</span>
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          )
                        })() : col.render(item)}
                      </td>
                    ))}
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-0.5">
                        <Button variant="ghost" size="icon" className="h-6 w-6" title="Download PDF"
                          onClick={() => window.open(`/facturare/api/invoices/${item.invoice_id}/pdf?mode=individual&car=${item.car_index}`, '_blank')}>
                          <Download className="h-3 w-3 text-red-500" />
                        </Button>
                        {item.invoice_type !== 'PROFORMA' && (
                          <Button variant="ghost" size="icon" className="h-6 w-6" title="Download EuroFib XLSX"
                            onClick={() => window.open(`/facturare/api/invoices/${item.invoice_id}/eurofib`, '_blank')}>
                            <FileSpreadsheet className="h-3 w-3 text-emerald-500" />
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
              {sorted.length > 0 && (
                <tfoot>
                  <tr className="border-t bg-muted/30 font-medium">
                    <td colSpan={activeColumns.findIndex(c => c.key === 'amount') + 1} className="px-3 py-2 text-right text-xs">
                      Total ({sorted.length} items):
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-xs">{fmtEur(totalAmount)}</td>
                    <td colSpan={colCount - activeColumns.findIndex(c => c.key === 'amount') - 2}></td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
