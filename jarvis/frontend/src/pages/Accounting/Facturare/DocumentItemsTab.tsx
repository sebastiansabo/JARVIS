import { useState, useEffect, useCallback } from 'react'
import { Loader2, Download, ArrowUp, ArrowDown, ArrowUpDown } from 'lucide-react'

import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

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

export default function DocumentItemsTab({ docType }: { docType: string }) {
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
    fetch(`/facturare/api/document-items?type=${docType}`)
      .then(r => r.ok ? r.json() : { items: [] })
      .then(data => setItems(data.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [docType])

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

  const toggleSort = (field: SortField) => {
    if (sortField === field) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortField(field); setSortDir('desc') }
  }

  const SortIcon = ({ field }: { field: SortField }) => (
    <span className="inline-flex ml-0.5">{sortField === field
      ? (sortDir === 'asc' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)
      : <ArrowUpDown className="h-3 w-3 opacity-30" />}</span>
  )

  const totalAmount = sorted.reduce((s, i) => s + i.doc_amount, 0)
  const label = 'Invoice'

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
          {datePeriod === 'custom' && (
            <>
              <Input type="date" className="w-32" value={dateFrom}
                onChange={e => { setDateFrom(e.target.value); setDatePeriod('custom') }} />
              <Input type="date" className="w-32" value={dateTo}
                onChange={e => { setDateTo(e.target.value); setDatePeriod('custom') }} />
            </>
          )}
          {(filterCompany !== 'all' || filterClient !== 'all' || searchQuery || dateFrom || dateTo) && (
            <Button variant="ghost" size="sm" className="text-xs" onClick={() => { setFilterCompany('all'); setFilterClient('all'); setSearchQuery(''); applyPeriod('all') }}>
              Clear
            </Button>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">{sorted.length} items</span>
          <span className="text-sm font-mono font-medium">{fmtEur(totalAmount)} EUR</span>
        </div>
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="text-left px-3 py-2.5 font-medium">Type</th>
                  <th className="text-left px-3 py-2.5 font-medium cursor-pointer select-none hover:bg-muted/80" onClick={() => toggleSort('doc_number')}>
                    No. <SortIcon field="doc_number" />
                  </th>
                  <th className="text-left px-3 py-2.5 font-medium cursor-pointer select-none hover:bg-muted/80" onClick={() => toggleSort('date')}>
                    Date <SortIcon field="date" />
                  </th>
                  <th className="text-left px-3 py-2.5 font-medium">Company</th>
                  <th className="text-left px-3 py-2.5 font-medium cursor-pointer select-none hover:bg-muted/80" onClick={() => toggleSort('customer')}>
                    Client <SortIcon field="customer" />
                  </th>
                  <th className="text-left px-3 py-2.5 font-medium cursor-pointer select-none hover:bg-muted/80" onClick={() => toggleSort('contract')}>
                    Contract <SortIcon field="contract" />
                  </th>
                  <th className="text-center px-3 py-2.5 font-medium">Anexa</th>
                  <th className="text-left px-3 py-2.5 font-medium">Nr. Cmd</th>
                  <th className="text-left px-3 py-2.5 font-medium cursor-pointer select-none hover:bg-muted/80" onClick={() => toggleSort('model')}>
                    Vehicle <SortIcon field="model" />
                  </th>
                  <th className="text-left px-3 py-2.5 font-medium">VIN</th>
                  <th className="text-right px-3 py-2.5 font-medium">Unit Price</th>
                  <th className="text-right px-3 py-2.5 font-medium cursor-pointer select-none hover:bg-muted/80" onClick={() => toggleSort('amount')}>
                    {label} EUR <SortIcon field="amount" />
                  </th>
                  <th className="text-left px-3 py-2.5 font-medium">Kurs</th>
                  <th className="text-left px-3 py-2.5 font-medium">Intocmit</th>
                  <th className="w-10"></th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr><td colSpan={15} className="text-center py-8"><Loader2 className="h-5 w-5 animate-spin inline" /></td></tr>
                )}
                {!loading && sorted.length === 0 && (
                  <tr><td colSpan={15} className="text-center py-8 text-muted-foreground">No {label.toLowerCase()}s found</td></tr>
                )}
                {sorted.map((item, idx) => (
                  <tr key={`${item.invoice_id}-${item.nr_comanda}-${idx}`}
                    className="border-b hover:bg-muted/30">
                    <td className="px-3 py-2 text-xs">
                      {item.invoice_type === 'PROFORMA' && <span className="inline-block px-1.5 py-0.5 rounded bg-blue-100 text-blue-800 font-medium">Proforma #{item.sequence_number}</span>}
                      {item.invoice_type === 'INVOICE' && <span className="inline-block px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 font-medium">Factura #{item.sequence_number}</span>}
                      {item.invoice_type === 'STORNO' && <span className="inline-block px-1.5 py-0.5 rounded bg-red-100 text-red-800 font-medium">Storno #{item.sequence_number}</span>}
                      {item.invoice_type === 'FINAL' && <span className="inline-block px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 font-medium">Final #{item.sequence_number}</span>}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">{item.doc_number || '—'}</td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      {item.issued_date ? new Date(item.issued_date).toLocaleDateString('ro-RO', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '—'}
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground max-w-[120px] truncate">{item.supplier_name}</td>
                    <td className="px-3 py-2 text-xs font-medium max-w-[140px] truncate">{item.customer_name}</td>
                    <td className="px-3 py-2 text-xs">{item.contract_ref}</td>
                    <td className="px-3 py-2 text-xs text-center">{item.anexa_number}</td>
                    <td className="px-3 py-2 font-mono text-xs text-muted-foreground">{item.nr_comanda || '—'}</td>
                    <td className="px-3 py-2 text-xs max-w-[180px] truncate">
                      {item.model}{item.culoare && ` (${item.culoare})`}
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground max-w-[140px] truncate">
                      {item.vin || <span className="text-amber-500 italic">no VIN</span>}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-xs">{fmtEur(item.unit_price)}</td>
                    <td className="px-3 py-2 text-right font-mono text-xs font-medium">{fmtEur(item.doc_amount)}</td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">{item.kurs_applied || '—'}</td>
                    <td className="px-3 py-2 text-xs text-muted-foreground italic max-w-[100px] truncate">{item.intocmit_de || '—'}</td>
                    <td className="px-3 py-2">
                      <Button variant="ghost" size="icon" className="h-6 w-6" title="Download PDF"
                        onClick={() => window.open(`/facturare/api/invoices/${item.invoice_id}/pdf?mode=individual&car=${item.car_index}`, '_blank')}>
                        <Download className="h-3 w-3 text-red-500" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
              {sorted.length > 0 && (
                <tfoot>
                  <tr className="border-t bg-muted/30 font-medium">
                    <td colSpan={10} className="px-3 py-2 text-right text-xs">Total ({sorted.length} items):</td>
                    <td className="px-3 py-2 text-right font-mono text-xs">{fmtEur(totalAmount)}</td>
                    <td colSpan={4}></td>
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
