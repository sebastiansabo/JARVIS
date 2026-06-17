import React, { useState, useEffect, useCallback } from 'react'
import { toast } from 'sonner'
import {
  Plus, FileText, Loader2, ChevronRight, ChevronDown, Copy,
  Search, CheckCircle2, Ban,
  Trash2, Download, Archive, FileSpreadsheet,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

// ── Types ───────────────────────────────────────────────────────

interface Company { id: number; company: string; vat: string | null }

interface ContractSummary {
  id: number; contract_ref: string; supplier_id: number; customer_id: number
  supplier_name: string; customer_name: string; contract_date: string | null
  responsible: string | null; anexa_count: number; notes: string | null
  total_value: number; invoiced_total: number
  created_at: string | null
}

interface AnexaSummary {
  id: number; anexa_number: number; line_count: number; total_value: number
  proformas_total: number; invoiced_total: number; pct_proforma: number; pct_invoiced: number
  invoice_count: number; stage: string; status: string; archived: boolean; types: string[]; notes: string | null
  lines_with_proforma: number; lines_invoiced: number; created_at: string | null
}

interface LineCoverage { invoice_id: number; invoice_type: string; sequence_number: number; amount_eur?: number; invoice_number?: number | null }

interface AnexaLine {
  id: number; line_number: number; nr_comanda: string | null; vin: string | null
  model: string; culoare: string | null; list_price_eur: number; selling_price_eur: number; qty: number
  status?: 'NONE' | 'PROFORMA' | 'INVOICED'; covered_by?: LineCoverage[]
  proforma_eur?: number; invoiced_eur?: number
}

interface InvoiceDetail {
  id: number; anexa_id: number; invoice_type: string; invoice_state: string
  sequence_number: number; invoice_number: number | null
  total_amount_eur: number; total_amount_ron: number; kurs_applied: number | null
  intocmit_de: string | null; notes: string | null; line_ids: number[] | null; issued_date: string | null; created_at: string | null
}

interface AnexaDetail {
  anexa_id: number; anexa_number: number; contract_ref: string
  supplier_name: string; customer_name: string
  lines: AnexaLine[]; invoices: InvoiceDetail[]
  next_actions: string[]; unpaired_proformas: { sequence_number: number; total_amount_eur: number; invoice_number: number | null; line_ids: number[] | null }[]
  anexa_total_eur: number; proformas_total_eur: number; remaining_eur: number
  lines_with_proforma: number; lines_invoiced: number; lines_total: number
}

// ── Helpers ─────────────────────────────────────────────────────

function fmtEur(n: number) { return new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n) }

/** Validate VIN (17 chars, ISO 3779 check digit). Returns error message or null. */
function validateVin(vin: string): string | null {
  if (!vin) return null // VIN is optional
  vin = vin.trim().toUpperCase()
  if (vin.length !== 17) return `VIN must be 17 characters (got ${vin.length})`
  if (/[IOQ]/.test(vin)) return 'VIN cannot contain I, O, or Q'
  if (!/^[A-HJ-NPR-Z0-9]{17}$/.test(vin)) return 'VIN contains invalid characters'
  // Check digit (position 9)
  const transliterate: Record<string, number> = { A:1,B:2,C:3,D:4,E:5,F:6,G:7,H:8,J:1,K:2,L:3,M:4,N:5,P:7,R:9,S:2,T:3,U:4,V:5,W:6,X:7,Y:8,Z:9 }
  const weights = [8,7,6,5,4,3,2,10,0,9,8,7,6,5,4,3,2]
  let sum = 0
  for (let i = 0; i < 17; i++) {
    const ch = vin[i]
    const val = /\d/.test(ch) ? parseInt(ch) : (transliterate[ch] || 0)
    sum += val * weights[i]
  }
  const remainder = sum % 11
  const checkChar = remainder === 10 ? 'X' : String(remainder)
  if (vin[8] !== checkChar) return `VIN check digit invalid (position 9: expected ${checkChar}, got ${vin[8]})`
  return null
}

const STAGE_CONFIG: Record<string, { label: string; color: string }> = {
  NEW: { label: 'Nou', color: 'bg-gray-100 text-gray-800' },
  PROFORMA: { label: 'Proforma', color: 'bg-blue-100 text-blue-800' },
  INVOICE: { label: 'Facturat', color: 'bg-amber-100 text-amber-800' },
  STORNO: { label: 'Storno', color: 'bg-red-100 text-red-800' },
  COMPLETE: { label: 'Finalizat', color: 'bg-emerald-100 text-emerald-800' },
}

const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  NEW: { label: 'New', color: 'bg-gray-100 text-gray-800' },
  IN_PROGRESS: { label: 'In Progress', color: 'bg-blue-100 text-blue-800' },
  PAID: { label: 'Paid', color: 'bg-emerald-100 text-emerald-800' },
  PROCESSED: { label: 'Processed', color: 'bg-purple-100 text-purple-800' },
}
const STATUS_KEYS = Object.keys(STATUS_CONFIG)
const TYPE_LABELS: Record<string, string> = { PROFORMA: 'Proforma', INVOICE: 'Factura', STORNO: 'Storno', FINAL: 'Final' }
const TYPE_COLORS: Record<string, string> = {
  PROFORMA: 'bg-blue-100 text-blue-800',
  INVOICE: 'bg-amber-100 text-amber-800',
  STORNO: 'bg-red-100 text-red-800',
  FINAL: 'bg-emerald-100 text-emerald-800',
}

// ── User Search ─────────────────────────────────────────────────

function UserSearchInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [query, setQuery] = useState(value)
  const [results, setResults] = useState<{ id: number; name: string }[]>([])
  const [open, setOpen] = useState(false)
  useEffect(() => { setQuery(value) }, [value])
  const search = (q: string) => {
    setQuery(q)
    if (q.length < 2) { setResults([]); setOpen(false); return }
    fetch(`/facturare/api/users?q=${encodeURIComponent(q)}`)
      .then(r => r.ok ? r.json() : { users: [] })
      .then(data => { setResults(data.users || []); setOpen(data.users?.length > 0) })
      .catch(() => setResults([]))
  }
  return (
    <div className="relative">
      <Input placeholder="Search user..." value={query} onChange={e => search(e.target.value)}
        onFocus={() => { if (results.length > 0) setOpen(true) }}
        onBlur={() => setTimeout(() => setOpen(false), 200)} />
      {open && results.length > 0 && (
        <div className="absolute z-20 top-full mt-1 w-full bg-background border rounded-md shadow-lg max-h-32 overflow-y-auto">
          {results.map(u => (
            <button key={u.id} className="w-full text-left px-3 py-1.5 text-sm hover:bg-muted"
              onMouseDown={() => { onChange(u.name); setQuery(u.name); setOpen(false) }}>{u.name}</button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Create Contract Dialog ──────────────────────────────────────

function CreateContractDialog({ open, onOpenChange, companies, onCreated }: {
  open: boolean; onOpenChange: (v: boolean) => void; companies: Company[]; onCreated: () => void
}) {
  const [ref, setRef] = useState('')
  const [supplierId, setSupplierId] = useState('')
  const [customerId, setCustomerId] = useState('')
  const [customerSearch, setCustomerSearch] = useState('')
  const [customerResults, setCustomerResults] = useState<{ id: number; display_name: string; nr_reg?: string }[]>([])
  const [customerName, setCustomerName] = useState('')
  const [contractDate, setContractDate] = useState('')
  const [responsible, setResponsible] = useState('')
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [searching, setSearching] = useState(false)

  const searchCrm = () => {
    if (!customerSearch.trim()) return
    setSearching(true)
    fetch(`/api/crm/clients?name=${encodeURIComponent(customerSearch)}&limit=5`)
      .then(r => r.ok ? r.json() : { clients: [] })
      .then(data => setCustomerResults(data.clients || []))
      .catch(() => setCustomerResults([]))
      .finally(() => setSearching(false))
  }

  const handleSubmit = async () => {
    if (!ref.trim()) { toast.error('Contract Ref required'); return }
    if (!supplierId) { toast.error('Supplier required'); return }
    if (!customerId) { toast.error('Customer required'); return }
    setSubmitting(true)
    try {
      const res = await fetch('/facturare/api/contracts', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contract_ref: ref.trim(), supplier_id: parseInt(supplierId),
          customer_id: parseInt(customerId),
          contract_date: contractDate || undefined,
          responsible: responsible || undefined, notes: notes || undefined,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Failed')
      toast.success(`Contract ${data.contract.contract_ref} created`)
      onOpenChange(false); onCreated()
      setRef(''); setSupplierId(''); setCustomerId(''); setCustomerName(''); setContractDate(''); setResponsible(''); setNotes('')
    } catch (err: any) { toast.error(err.message) }
    finally { setSubmitting(false) }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>New Contract</DialogTitle>
          <DialogDescription>Create a new contract with a client.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div><Label>Contract Ref *</Label><Input placeholder="CTR-677" value={ref} onChange={e => setRef(e.target.value)} /></div>
            <div>
              <Label>Supplier *</Label>
              <Select value={supplierId} onValueChange={setSupplierId}>
                <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                <SelectContent>{companies.map(c => <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <div>
            <Label>Customer * {customerName && <span className="text-emerald-600 font-medium ml-2">{customerName}</span>}</Label>
            <div className="flex gap-2 mt-1">
              <Input placeholder="Search CRM..." value={customerSearch} onChange={e => setCustomerSearch(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && searchCrm()} className="flex-1" />
              <Button variant="outline" size="icon" onClick={searchCrm} disabled={searching}>
                {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              </Button>
            </div>
            {customerResults.length > 0 && (
              <div className="border rounded-md divide-y text-sm max-h-32 overflow-y-auto mt-1">
                {customerResults.map(c => (
                  <button key={c.id} className="w-full text-left px-3 py-2 hover:bg-muted"
                    onClick={() => { setCustomerId(String(c.id)); setCustomerName(c.display_name); setCustomerResults([]); setCustomerSearch('') }}>
                    <span className="font-medium">{c.display_name}</span>
                    {c.nr_reg && <span className="text-muted-foreground ml-2">{c.nr_reg}</span>}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div><Label>Date</Label><Input type="date" value={contractDate} onChange={e => setContractDate(e.target.value)} /></div>
            <div><Label>Responsible</Label><UserSearchInput value={responsible} onChange={setResponsible} /></div>
          </div>
          <div><Label>Notes</Label><Input placeholder="Optional" value={notes} onChange={e => setNotes(e.target.value)} /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />} Create Contract
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Create Anexa Dialog ─────────────────────────────────────────

interface LineEntry { nr_comanda: string; make: string; model: string; culoare: string; vin: string; price: string }
const EMPTY_LINE: LineEntry = { nr_comanda: '', make: '', model: '', culoare: '', vin: '', price: '' }

function CreateAnexaDialog({ open, onOpenChange, contractId, onCreated }: {
  open: boolean; onOpenChange: (v: boolean) => void; contractId: number; onCreated: () => void
}) {
  const [anexaNumber, setAnexaNumber] = useState('')
  const [lines, setLines] = useState<LineEntry[]>([{ ...EMPTY_LINE }])
  const [notes, setNotes] = useState('')
  const [mode, setMode] = useState<'manual' | 'import'>('manual')
  const [importFile, setImportFile] = useState<File | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const addLine = () => setLines(prev => [...prev, { ...EMPTY_LINE }])
  const removeLine = (idx: number) => { if (lines.length > 1) setLines(prev => prev.filter((_, i) => i !== idx)) }
  const updateLine = (idx: number, field: keyof LineEntry, value: string) => setLines(prev => prev.map((l, i) => i === idx ? { ...l, [field]: value } : l))


  const validLines = lines.filter(l => l.model.trim())

  const handleSubmit = async () => {
    if (!anexaNumber) { toast.error('Anexa number required'); return }

    if (mode === 'import' && importFile) {
      // Submit with file upload — backend parses the Anexa XLSX
      setSubmitting(true)
      try {
        const fd = new FormData()
        fd.append('anexa', importFile)
        fd.append('contract_id', String(contractId))
        fd.append('anexa_number', anexaNumber)
        if (notes) fd.append('notes', notes)

        const res = await fetch(`/facturare/api/contracts/${contractId}/anexas/import`, {
          method: 'POST', body: fd,
        })
        const data = await res.json()
        if (!res.ok) throw new Error(data.error || 'Failed')
        toast.success(`Anexa ${anexaNumber} created — ${data.lines_imported} vehicles imported`)
        onOpenChange(false); onCreated()
        setAnexaNumber(''); setImportFile(null); setNotes('')
      } catch (err: any) { toast.error(err.message) }
      finally { setSubmitting(false) }
      return
    }

    if (validLines.length === 0) { toast.error('At least one vehicle required'); return }
    // Validate VINs
    const vins = validLines.map(l => l.vin).filter(v => v.trim())
    for (const v of vins) {
      const err = validateVin(v.trim().toUpperCase())
      if (err) { toast.error(err); return }
    }
    const vinSet = new Set(vins.map(v => v.trim().toUpperCase()))
    if (vinSet.size !== vins.length) { toast.error('Duplicate VIN detected — each car must have a unique VIN'); return }
    setSubmitting(true)
    try {
      const res = await fetch(`/facturare/api/contracts/${contractId}/anexas`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          anexa_number: parseInt(anexaNumber),
          notes: notes || undefined,
          lines: validLines.map((l) => {
            const baseNr = parseInt(lines[0].nr_comanda) || 0
            const originalIdx = lines.indexOf(l)
            const nr = originalIdx === 0 ? l.nr_comanda : (baseNr ? String(baseNr + originalIdx) : '')
            return {
              nr_comanda: nr || undefined, vin: l.vin || undefined,
              model: [l.make, l.model].filter(Boolean).join(' '),
              culoare: l.culoare || undefined,
              list_price_eur: parseFloat(l.price) || 0,
              selling_price_eur: parseFloat(l.price) || 0,
              qty: 1,
            }
          }),
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Failed')
      toast.success(`Anexa ${anexaNumber} created`)
      onOpenChange(false); onCreated()
      setAnexaNumber(''); setLines([{ ...EMPTY_LINE }]); setNotes('')
    } catch (err: any) { toast.error(err.message) }
    finally { setSubmitting(false) }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="!max-w-[90vw] w-[90vw] max-h-[92vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>New Anexa</DialogTitle>
          <DialogDescription>Add vehicles to the contract — manual entry or import from Excel.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-4">
            <div><Label>Anexa No. *</Label><Input type="number" placeholder="1" min="1" value={anexaNumber} onChange={e => setAnexaNumber(e.target.value)} /></div>
            <div className="col-span-2"><Label>Notes</Label><Input placeholder="Optional" value={notes} onChange={e => setNotes(e.target.value)} /></div>
          </div>

          <div className="flex items-center gap-2">
            <Button variant={mode === 'manual' ? 'default' : 'outline'} size="sm" onClick={() => setMode('manual')}>Manual Entry</Button>
            <Button variant={mode === 'import' ? 'default' : 'outline'} size="sm" onClick={() => setMode('import')}>
              <FileText className="h-4 w-4 mr-1" /> Import Excel
            </Button>
            <span className="text-muted-foreground text-xs mx-1">|</span>
            <a href="/facturare/api/template/anexa" download className="text-xs text-blue-600 hover:underline inline-flex items-center gap-1">
              <Download className="h-3 w-3" /> Download Template
            </a>
          </div>

          <Separator />

          {mode === 'import' ? (
            <div className="space-y-3">
              <div>
                <Input type="file" accept=".xlsx,.xls,.csv" onChange={e => setImportFile(e.target.files?.[0] || null)} />
                {importFile && <p className="text-sm text-muted-foreground mt-1">{importFile.name}</p>}
              </div>
              <div className="text-xs text-muted-foreground">
                Expected columns: Nr. Comanda, Model, Culoare, VIN, List Price, Selling Price, Qty
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {/* Table header matching import format */}
              <div className="grid grid-cols-[90px_100px_1fr_120px_180px_110px_64px] gap-1 text-xs font-medium text-muted-foreground px-1 border-b pb-1">
                <span>Nr. Cmd</span><span>Make</span><span>Model</span><span>Culoare</span>
                <span>VIN</span><span>Unit Price</span><span></span>
              </div>
              {lines.map((line, idx) => {
                // Nr. Comanda: only first line is editable, rest auto-increment
                const baseNr = parseInt(lines[0].nr_comanda) || 0
                const autoNr = idx === 0 ? line.nr_comanda : (baseNr ? String(baseNr + idx) : '')
                return (
                <div key={idx} className="grid grid-cols-[90px_100px_1fr_120px_180px_110px_64px] gap-1 items-center">
                  {idx === 0 ? (
                    <Input className="h-8 text-xs" placeholder="150001" value={line.nr_comanda} onChange={e => updateLine(idx, 'nr_comanda', e.target.value)} />
                  ) : (
                    <Input className="h-8 text-xs bg-muted/50 text-muted-foreground" value={autoNr} disabled />
                  )}
                  <Input className="h-8 text-xs" placeholder="Audi" value={line.make} onChange={e => updateLine(idx, 'make', e.target.value)} />
                  <Input className="h-8 text-xs" placeholder="Q3 Sportback 35 TFSI" value={line.model} onChange={e => updateLine(idx, 'model', e.target.value)} />
                  <Input className="h-8 text-xs" placeholder="Black" value={line.culoare} onChange={e => updateLine(idx, 'culoare', e.target.value)} />
                  <Input className="h-8 text-xs" placeholder="WAUZZZ8V..." value={line.vin} onChange={e => updateLine(idx, 'vin', e.target.value)} />
                  <Input className="h-8 text-xs" type="number" placeholder="38900" value={line.price} onChange={e => updateLine(idx, 'price', e.target.value)} />
                  <div className="flex">
                    <Button variant="ghost" size="icon" className="h-8 w-8" title="Duplicate"
                      onClick={() => setLines(prev => [...prev.slice(0, idx + 1), { ...line, vin: '', nr_comanda: '' }, ...prev.slice(idx + 1)])}>
                      <Copy className="h-3 w-3" />
                    </Button>
                    <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => removeLine(idx)} disabled={lines.length <= 1}><Trash2 className="h-3 w-3" /></Button>
                  </div>
                </div>
                )
              })}
              <Button variant="outline" size="sm" onClick={addLine} className="w-full"><Plus className="h-4 w-4 mr-1" /> Add Vehicle</Button>
              <div className="text-right text-sm text-muted-foreground">
                {validLines.length} vehicle(s) — Total: <span className="font-mono font-medium text-foreground">{fmtEur(validLines.reduce((s, l) => s + (parseFloat(l.price) || 0), 0))} EUR</span>
              </div>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />} Create Anexa
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Editable Anexa Line (inline VIN edit) ───────────────────────

function EditableAnexaLine({ line, canDelete, onUpdated }: { line: AnexaLine; canDelete?: boolean; onUpdated: () => void }) {
  const [editing, setEditing] = useState(false)
  const [vin, setVin] = useState(line.vin || '')

  const saveVin = async () => {
    const trimmed = vin.trim().toUpperCase()
    if (trimmed) {
      const err = validateVin(trimmed)
      if (err) { toast.error(err); return }
    }
    try {
      const res = await fetch(`/facturare/api/anexa-lines/${line.id}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vin: trimmed }),
      })
      if (!res.ok) { const d = await res.json(); throw new Error(d.error || 'Failed') }
      toast.success('VIN updated')
      setEditing(false); onUpdated()
    } catch (err: any) { toast.error(err.message) }
  }

  return (
    <div className="flex justify-between items-center py-0.5 border-b border-dashed last:border-0 gap-2">
      <span className="flex items-center gap-1 min-w-0">
        {line.nr_comanda && <span className="font-mono text-muted-foreground mr-1">{line.nr_comanda}</span>}
        <span className="truncate">{line.model}{line.culoare && ` (${line.culoare})`}</span>
        {editing ? (
          <span className="flex items-center gap-1 ml-1">
            <Input className="h-6 w-40 text-xs" placeholder="WAUZZZ8V..." value={vin}
              onChange={e => setVin(e.target.value)} onKeyDown={e => e.key === 'Enter' && saveVin()} autoFocus />
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={saveVin}><CheckCircle2 className="h-3 w-3 text-emerald-500" /></Button>
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => { setEditing(false); setVin(line.vin || '') }}>
              <span className="text-xs text-muted-foreground">✕</span>
            </Button>
          </span>
        ) : line.vin ? (
          <span className="text-muted-foreground ml-1 cursor-pointer hover:underline" onClick={() => setEditing(true)}>{line.vin}</span>
        ) : (
          <span className="text-amber-500 ml-1 italic cursor-pointer hover:underline" onClick={() => setEditing(true)}>+ add VIN</span>
        )}
      </span>
      {line.status === 'INVOICED' && <Badge className="bg-emerald-100 text-emerald-800 text-[9px] px-1 py-0 shrink-0">Invoiced</Badge>}
      {line.status === 'PROFORMA' && <Badge className="bg-blue-100 text-blue-800 text-[9px] px-1 py-0 shrink-0">Proforma</Badge>}
      <span className="font-mono shrink-0 text-right ml-auto">{fmtEur(line.selling_price_eur)} EUR</span>
      {canDelete && (
        <Button variant="ghost" size="icon" className="h-5 w-5 shrink-0" title="Remove vehicle"
          onClick={async () => {
            if (!confirm(`Remove ${line.model}?`)) return
            try {
              const res = await fetch(`/facturare/api/anexa-lines/${line.id}`, { method: 'DELETE' })
              if (!res.ok) { const d = await res.json(); throw new Error(d.error || 'Failed') }
              toast.success('Vehicle removed'); onUpdated()
            } catch (err: any) { toast.error(err.message) }
          }}>
          <Trash2 className="h-3 w-3 text-muted-foreground hover:text-red-500" />
        </Button>
      )}
    </div>
  )
}

// ── Add Vehicle Inline ──────────────────────────────────────────

function AddVehicleInline({ anexaId, nextLineNumber, nextNrComanda, onAdded }: {
  anexaId: number; nextLineNumber: number; nextNrComanda: string; onAdded: () => void
}) {
  const [adding, setAdding] = useState(false)
  const [make, setMake] = useState('')
  const [model, setModel] = useState('')
  const [culoare, setCuloare] = useState('')
  const [vin, setVin] = useState('')
  const [price, setPrice] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleAdd = async () => {
    const fullModel = [make, model].filter(Boolean).join(' ')
    if (!fullModel.trim()) { toast.error('Model required'); return }
    if (vin.trim()) {
      const err = validateVin(vin.trim().toUpperCase())
      if (err) { toast.error(err); return }
    }
    setSubmitting(true)
    try {
      const res = await fetch(`/facturare/api/anexa-lines`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          anexa_id: anexaId, line_number: nextLineNumber,
          nr_comanda: nextNrComanda || undefined,
          model: fullModel, culoare: culoare || undefined,
          vin: vin.trim().toUpperCase() || undefined,
          list_price_eur: parseFloat(price) || 0,
          selling_price_eur: parseFloat(price) || 0,
        }),
      })
      if (!res.ok) { const d = await res.json(); throw new Error(d.error || 'Failed') }
      toast.success('Vehicle added')
      setAdding(false); setMake(''); setModel(''); setCuloare(''); setVin(''); setPrice(''); onAdded()
    } catch (err: any) { toast.error(err.message) }
    finally { setSubmitting(false) }
  }

  if (!adding) {
    return (
      <button className="flex items-center gap-1 text-xs text-blue-600 hover:underline mt-1" onClick={() => setAdding(true)}>
        <Plus className="h-3 w-3" /> Add vehicle
      </button>
    )
  }

  return (
    <div className="border rounded-md p-2 mt-1 space-y-2 bg-muted/20">
      <div className="grid grid-cols-[80px_80px_1fr_80px_140px_90px] gap-1 items-center">
        <Input className="h-7 text-xs bg-muted/50" value={nextNrComanda} disabled />
        <Input className="h-7 text-xs" placeholder="Audi" value={make} onChange={e => setMake(e.target.value)} />
        <Input className="h-7 text-xs" placeholder="Q3 Sportback 35 TFSI" value={model} onChange={e => setModel(e.target.value)} />
        <Input className="h-7 text-xs" placeholder="Black" value={culoare} onChange={e => setCuloare(e.target.value)} />
        <Input className="h-7 text-xs" placeholder="VIN (optional)" value={vin} onChange={e => setVin(e.target.value)} />
        <Input className="h-7 text-xs" type="number" placeholder="10000" value={price} onChange={e => setPrice(e.target.value)} />
      </div>
      <div className="flex gap-1 justify-end">
        <Button variant="ghost" size="sm" className="h-6 text-xs" onClick={() => setAdding(false)}>Cancel</Button>
        <Button size="sm" className="h-6 text-xs" onClick={handleAdd} disabled={submitting}>
          {submitting && <Loader2 className="h-3 w-3 mr-1 animate-spin" />} Add
        </Button>
      </div>
    </div>
  )
}

// ── Vehicle Table (per-car invoicing overview) ─────────────────

/** Compute per-car next action from its coverage history.
 *  Flow: Proforma N → Factura Avans N → … (repeat) → Storno → Final → Complete
 *  Number of rounds is NOT fixed — depends on amounts. */
type CarNextAction = 'PROFORMA' | 'INVOICE' | 'STORNO' | 'FINAL' | 'COMPLETE'

function getCarNextAction(line: AnexaLine): CarNextAction {
  const cov = line.covered_by || []
  const proformaCount = cov.filter(c => c.invoice_type === 'PROFORMA').length
  const invoiceCount = cov.filter(c => c.invoice_type === 'INVOICE').length
  const hasStorno = cov.some(c => c.invoice_type === 'STORNO')
  const hasFinal = cov.some(c => c.invoice_type === 'FINAL')
  if (hasFinal) return 'COMPLETE'
  if (hasStorno) return 'FINAL'
  // Unmatched proforma → need invoice to confirm it
  if (proformaCount > invoiceCount) return 'INVOICE'
  // All matched — check if fully covered by amount (proforma sum ≈ selling price)
  const proformaEur = line.proforma_eur || 0
  if (proformaCount > 0 && proformaEur >= line.selling_price_eur * 0.999) return 'STORNO'
  // Need more proformas
  return 'PROFORMA'
}

/** Returns a unique stage key including the round number, e.g. "PROFORMA-3", "INVOICE-2" */
function getCarStageKey(line: AnexaLine): string {
  const cov = line.covered_by || []
  const pCount = cov.filter(c => c.invoice_type === 'PROFORMA').length
  const action = getCarNextAction(line)
  if (action === 'PROFORMA') return `PROFORMA-${pCount + 1}`
  if (action === 'INVOICE') return `INVOICE-${pCount}`
  return action
}

const CAR_ACTION_LABELS: Record<CarNextAction, string> = {
  PROFORMA: 'Proforma', INVOICE: 'Factura Avans', STORNO: 'Storno', FINAL: 'Final', COMPLETE: 'Complet',
}
const CAR_ACTION_COLORS: Record<CarNextAction, string> = {
  PROFORMA: 'bg-blue-100 text-blue-800', INVOICE: 'bg-amber-100 text-amber-800',
  STORNO: 'bg-red-100 text-red-800', FINAL: 'bg-emerald-100 text-emerald-800',
  COMPLETE: 'bg-emerald-50 text-emerald-600',
}

function VehicleTable({ detail, defaultIntocmit, onCreated }: {
  detail: AnexaDetail; defaultIntocmit?: string; onCreated: () => void
}) {
  const { lines, invoices: detailInvoices, unpaired_proformas: unpairedProformas } = detail

  // Build lookup: invoice_id → ordered line_ids (for per-car PDF download)
  const invoiceLineIds = new Map<number, number[]>()
  for (const inv of detailInvoices) {
    invoiceLineIds.set(inv.id, inv.line_ids || lines.map(l => l.id))
  }
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [editingVinId, setEditingVinId] = useState<number | null>(null)
  const [editingVinValue, setEditingVinValue] = useState('')
  const saveVinInline = async (lineId: number) => {
    const trimmed = editingVinValue.trim().toUpperCase()
    if (trimmed) {
      const err = validateVin(trimmed)
      if (err) { toast.error(err); return }
    }
    try {
      const res = await fetch(`/facturare/api/anexa-lines/${lineId}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vin: trimmed }),
      })
      if (!res.ok) { const d = await res.json(); throw new Error(d.error || 'Failed') }
      toast.success('VIN updated')
      setEditingVinId(null); onCreated()
    } catch (err: any) { toast.error(err.message) }
  }
  const [proformaOpen, setProformaOpen] = useState(false)
  const [invoiceOpen, setInvoiceOpen] = useState(false)
  const [stornoOpen, setStornoOpen] = useState(false)
  const [finalOpen, setFinalOpen] = useState(false)

  // Per-line next actions
  const lineActions = new Map<number, CarNextAction>()
  for (const l of lines) lineActions.set(l.id, getCarNextAction(l))

  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set())
  const toggleExpand = (id: number) => {
    setExpandedIds(prev => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next })
  }

  const totalSelling = lines.reduce((s, l) => s + l.selling_price_eur, 0)
  const totalProforma = lines.reduce((s, l) => s + (l.proforma_eur || 0), 0)
  const totalInvoiced = lines.reduce((s, l) => s + (l.invoiced_eur || 0), 0)
  const totalRemaining = totalSelling - totalInvoiced

  // Sort coverage entries for expanded rows: P1, F1, P2, F2, ..., Storno, Final
  const sortCoverage = (a: LineCoverage, b: LineCoverage) => {
    const groupOrder: Record<string, number> = { PROFORMA: 0, INVOICE: 0, STORNO: 1, FINAL: 2 }
    const aGroup = groupOrder[a.invoice_type] ?? 0; const bGroup = groupOrder[b.invoice_type] ?? 0
    if (aGroup !== bGroup) return aGroup - bGroup
    if (a.sequence_number !== b.sequence_number) return a.sequence_number - b.sequence_number
    const typeOrder = ['PROFORMA', 'INVOICE', 'STORNO', 'FINAL']
    return typeOrder.indexOf(a.invoice_type) - typeOrder.indexOf(b.invoice_type)
  }
  const carPdfUrl = (invoiceId: number, lineId: number) => {
    const ids = invoiceLineIds.get(invoiceId)
    const idx = ids ? ids.indexOf(lineId) : -1
    if (idx >= 0 && ids && ids.length > 1) return `/facturare/api/invoices/${invoiceId}/pdf?car=${idx}`
    return `/facturare/api/invoices/${invoiceId}/pdf?mode=merged`
  }

  const covLabel = (c: LineCoverage, sellingPrice: number) => {
    const pct = sellingPrice > 0 && c.amount_eur ? Math.round(Math.abs(c.amount_eur) / sellingPrice * 100) : 0
    const pctStr = pct > 0 ? ` (${pct}%)` : ''
    if (c.invoice_type === 'PROFORMA') return `Proforma${pctStr}`
    if (c.invoice_type === 'INVOICE') return `Factura Avans${pctStr}`
    if (c.invoice_type === 'STORNO') return `Storno${pctStr}`
    if (c.invoice_type === 'FINAL') return `Final${pctStr}`
    return c.invoice_type
  }
  const covColor = (c: LineCoverage) => {
    if (c.invoice_type === 'PROFORMA') return 'text-blue-600'
    if (c.invoice_type === 'INVOICE') return 'text-emerald-600'
    if (c.invoice_type === 'STORNO') return 'text-red-600'
    if (c.invoice_type === 'FINAL') return 'text-emerald-700'
    return ''
  }

  // Selection: any non-complete car is selectable
  const selectableLines = lines.filter(l => lineActions.get(l.id) !== 'COMPLETE')
  const allSelectableSelected = selectableLines.length > 0 && selectableLines.every(l => selectedIds.has(l.id))

  const toggleLine = (id: number) => {
    setSelectedIds(prev => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next })
  }
  const toggleAll = () => {
    if (allSelectableSelected) setSelectedIds(new Set())
    else setSelectedIds(new Set(selectableLines.map(l => l.id)))
  }

  // Compute which actions are valid for the current selection
  const selectedLines = lines.filter(l => selectedIds.has(l.id))
  const selectedActions = new Set(selectedLines.map(l => lineActions.get(l.id)))
  const selectedStageKeys = new Set(selectedLines.map(l => getCarStageKey(l)))
  const selectedCount = selectedIds.size
  const selectedTotal = selectedLines.reduce((s, l) => s + l.selling_price_eur, 0)

  // An action button is enabled if ALL selected cars are at the EXACT same stage (action + round)
  const sameStage = selectedCount > 0 && selectedStageKeys.size === 1
  const canProforma = sameStage && selectedActions.has('PROFORMA')
  const canInvoice = sameStage && selectedActions.has('INVOICE')
  const canStorno = sameStage && selectedActions.has('STORNO')
  const canFinal = sameStage && selectedActions.has('FINAL')

  return (
    <>
    <Card>
      <CardContent className="p-0">
        {/* Action bar */}
        <div className="flex items-center justify-between px-3 py-2 border-b bg-muted/30 flex-wrap gap-2">
          <div className="flex items-center gap-3 text-xs">
            <span className="font-medium text-muted-foreground">{lines.length} vehicle(s)</span>
            {selectedCount > 0 && (
              <span className="text-blue-600 font-medium">{selectedCount} selected — {fmtEur(selectedTotal)} EUR</span>
            )}
            {selectedCount > 0 && sameStage && (
              <span className="text-muted-foreground">→ {CAR_ACTION_LABELS[[...selectedActions][0]!]}</span>
            )}
            {selectedCount > 0 && !sameStage && (
              <span className="text-amber-600">Mixed stages — select cars at the same stage</span>
            )}
          </div>
          <div className="flex gap-1.5">
            <Button size="sm" variant="outline" className="h-7 text-xs" disabled={!canProforma}
              onClick={() => setProformaOpen(true)}>
              <Plus className="h-3 w-3 mr-1" /> Proforma
            </Button>
            <Button size="sm" variant="outline" className="h-7 text-xs" disabled={!canInvoice}
              onClick={() => setInvoiceOpen(true)}>
              <FileText className="h-3 w-3 mr-1" /> Factura Avans
            </Button>
            <Button size="sm" variant="outline" className="h-7 text-xs text-red-600" disabled={!canStorno}
              onClick={() => setStornoOpen(true)}>
              <Ban className="h-3 w-3 mr-1" /> Storno
            </Button>
            <Button size="sm" className="h-7 text-xs" disabled={!canFinal}
              onClick={() => setFinalOpen(true)}>
              <CheckCircle2 className="h-3 w-3 mr-1" /> Final
            </Button>
          </div>
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b bg-muted/40">
                <th className="w-8 px-2 py-1.5">
                  <input type="checkbox" checked={allSelectableSelected} onChange={toggleAll} className="rounded" />
                </th>
                <th className="w-6 px-1 py-1.5"></th>
                <th className="text-left px-2 py-1.5 font-medium">Comanda</th>
                <th className="text-left px-2 py-1.5 font-medium">Model</th>
                <th className="text-left px-2 py-1.5 font-medium">Culoare</th>
                <th className="text-left px-2 py-1.5 font-medium">VIN</th>
                <th className="text-right px-2 py-1.5 font-medium">Pret Vanzare</th>
                <th className="text-right px-2 py-1.5 font-medium text-blue-600">Proforma</th>
                <th className="text-right px-2 py-1.5 font-medium text-emerald-600">Facturat</th>
                <th className="text-right px-2 py-1.5 font-medium">Rest</th>
                <th className="text-center px-2 py-1.5 font-medium w-24">Progres</th>
                <th className="text-center px-2 py-1.5 font-medium">Urmatorul Pas</th>
                <th className="text-center px-2 py-1.5 font-medium w-10"></th>
              </tr>
            </thead>
            <tbody>
              {lines.map(l => {
                const proforma = l.proforma_eur || 0
                const invoiced = l.invoiced_eur || 0
                const rest = l.selling_price_eur - invoiced
                const nextAction = lineActions.get(l.id) || 'PROFORMA'
                const isComplete = nextAction === 'COMPLETE'
                const covEntries = [...(l.covered_by || [])].sort(sortCoverage)
                const hasCov = covEntries.length > 0
                const isExpanded = expandedIds.has(l.id)
                return (
                  <React.Fragment key={l.id}>
                  <tr className={`border-b hover:bg-muted/20 ${selectedIds.has(l.id) ? 'bg-blue-50 dark:bg-blue-950/20' : ''} ${isComplete ? 'opacity-50' : ''} ${hasCov ? 'cursor-pointer' : ''}`}
                    onClick={() => hasCov && toggleExpand(l.id)}>
                    <td className="w-8 px-2 py-1.5 text-center" onClick={e => e.stopPropagation()}>
                      <input type="checkbox" checked={selectedIds.has(l.id)} disabled={isComplete}
                        onChange={() => toggleLine(l.id)} className="rounded" />
                    </td>
                    <td className="w-6 px-1 py-1.5 text-center text-muted-foreground">
                      {hasCov && <ChevronRight className={`h-3.5 w-3.5 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />}
                    </td>
                    <td className="px-2 py-1.5 font-mono text-muted-foreground">{l.nr_comanda || '—'}</td>
                    <td className="px-2 py-1.5">{l.model}</td>
                    <td className="px-2 py-1.5 text-muted-foreground">{l.culoare || '—'}</td>
                    <td className="px-2 py-1.5 font-mono text-muted-foreground text-[11px]" onClick={e => e.stopPropagation()}>
                      {editingVinId === l.id ? (
                        <span className="flex items-center gap-1">
                          <Input className="h-6 w-40 text-xs font-mono" placeholder="WAUZZZ8V..." value={editingVinValue}
                            onChange={e => setEditingVinValue(e.target.value)}
                            onKeyDown={e => { if (e.key === 'Enter') saveVinInline(l.id); if (e.key === 'Escape') setEditingVinId(null) }}
                            autoFocus />
                          <Button variant="ghost" size="icon" className="h-5 w-5" onClick={() => saveVinInline(l.id)}>
                            <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-5 w-5" onClick={() => setEditingVinId(null)}>
                            <Ban className="h-3 w-3 text-muted-foreground" />
                          </Button>
                        </span>
                      ) : l.vin ? (
                        <span className="cursor-pointer hover:underline" onClick={() => { setEditingVinId(l.id); setEditingVinValue(l.vin || '') }}>{l.vin}</span>
                      ) : (
                        <span className="text-amber-500 italic cursor-pointer hover:underline" onClick={() => { setEditingVinId(l.id); setEditingVinValue('') }}>+ VIN</span>
                      )}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono">{fmtEur(l.selling_price_eur)}</td>
                    <td className="px-2 py-1.5 text-right font-mono text-blue-600">{proforma > 0 ? fmtEur(proforma) : '—'}</td>
                    <td className="px-2 py-1.5 text-right font-mono text-emerald-600">{invoiced > 0 ? fmtEur(invoiced) : '—'}</td>
                    <td className="px-2 py-1.5 text-right font-mono text-amber-600">{rest > 0 ? fmtEur(rest) : fmtEur(0)}</td>
                    <td className="px-2 py-1.5">
                      {(() => {
                        const pct = l.selling_price_eur > 0 ? Math.round((proforma / l.selling_price_eur) * 100) : 0
                        return (
                          <div className="flex items-center gap-1">
                            <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                              <div className={`h-full rounded-full ${pct >= 100 ? 'bg-emerald-500' : pct > 0 ? 'bg-blue-400' : 'bg-muted'}`}
                                style={{ width: `${Math.min(pct, 100)}%` }} />
                            </div>
                            <span className="text-[10px] font-mono text-muted-foreground w-7 text-right">{pct}%</span>
                          </div>
                        )
                      })()}
                    </td>
                    <td className="px-2 py-1.5 text-center">
                      <Badge className={`text-[9px] px-1.5 py-0 ${CAR_ACTION_COLORS[nextAction]}`}>
                        {CAR_ACTION_LABELS[nextAction]}
                      </Badge>
                    </td>
                    <td className="px-2 py-1.5 text-center" onClick={e => e.stopPropagation()}>
                      {hasCov && (
                        <Download className="h-3.5 w-3.5 text-muted-foreground cursor-pointer hover:text-blue-600 inline"
                          onClick={() => covEntries.forEach(c => window.open(carPdfUrl(c.invoice_id, l.id), '_blank'))} />
                      )}
                    </td>
                  </tr>
                  {isExpanded && (() => {
                    let cumInvoiced = 0
                    const lastIdx = covEntries.length - 1
                    return covEntries.map((c, ci) => {
                    const isProf = c.invoice_type === 'PROFORMA'
                    if (c.invoice_type === 'INVOICE') cumInvoiced += (c.amount_eur || 0)
                    // Rest: after invoice = selling - cumInvoiced, after storno = full (reverses all), after final = 0
                    const restAfter = c.invoice_type === 'INVOICE' ? l.selling_price_eur - cumInvoiced
                      : c.invoice_type === 'STORNO' ? l.selling_price_eur
                      : c.invoice_type === 'FINAL' ? 0
                      : null
                    return (
                    <tr key={`${l.id}-${c.invoice_type}-${c.sequence_number}`} className="bg-blue-50/50 dark:bg-blue-950/10 border-b border-blue-100 dark:border-blue-900/30 last:border-b-2">
                      <td></td>
                      <td></td>
                      <td className="px-2 py-1 font-mono text-[11px] text-muted-foreground">
                        {c.invoice_number != null ? String(c.invoice_number) : ''}
                      </td>
                      <td colSpan={4} className="px-2 py-1">
                        <span className={`text-[11px] font-medium ${covColor(c)}`}>{covLabel(c, l.selling_price_eur)}</span>
                      </td>
                      <td className={`px-2 py-1 text-right font-mono text-[11px] ${isProf ? covColor(c) : ''}`}>
                        {isProf ? fmtEur(c.amount_eur || 0) : ''}
                      </td>
                      <td className={`px-2 py-1 text-right font-mono text-[11px] ${!isProf ? covColor(c) : ''}`}>
                        {!isProf ? fmtEur(c.amount_eur || 0) : ''}
                      </td>
                      <td className="px-2 py-1 text-right font-mono text-[11px] text-amber-600">
                        {restAfter != null ? fmtEur(restAfter) : ''}
                      </td>
                      <td colSpan={2}></td>
                      <td className="px-2 py-1 text-center">
                        <span className="inline-flex gap-1">
                          <Download className="h-3.5 w-3.5 text-muted-foreground cursor-pointer hover:text-blue-600"
                            onClick={() => window.open(carPdfUrl(c.invoice_id, l.id), '_blank')} />
                          {ci === lastIdx && (
                          <Trash2 className="h-3.5 w-3.5 text-muted-foreground cursor-pointer hover:text-red-500"
                            onClick={async () => {
                              if (!confirm(`Delete this ${covLabel(c, l.selling_price_eur)}?`)) return
                              const res = await fetch(`/facturare/api/invoices/${c.invoice_id}`, { method: 'DELETE' })
                              if (res.ok) { toast.success('Deleted'); onCreated() }
                              else { const d = await res.json().catch(() => null); toast.error(d?.error || 'Delete failed') }
                            }} />
                          )}
                        </span>
                      </td>
                    </tr>
                    )
                  })
                  })()}
                  </React.Fragment>
                )
              })}
            </tbody>
            <tfoot>
              <tr className="border-t bg-muted/30 font-medium">
                <td colSpan={2}></td>
                <td className="px-2 py-1.5" colSpan={4}>Total</td>
                <td className="px-2 py-1.5 text-right font-mono">{fmtEur(totalSelling)}</td>
                <td className="px-2 py-1.5 text-right font-mono text-blue-600">{totalProforma > 0 ? fmtEur(totalProforma) : '—'}</td>
                <td className="px-2 py-1.5 text-right font-mono text-emerald-600">{totalInvoiced > 0 ? fmtEur(totalInvoiced) : '—'}</td>
                <td className="px-2 py-1.5 text-right font-mono text-amber-600">{totalRemaining > 0 ? fmtEur(totalRemaining) : '—'}</td>
                <td colSpan={3}></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </CardContent>
    </Card>

    {/* Dialogs */}
    <ProformaDialog open={proformaOpen} onOpenChange={setProformaOpen} anexaId={detail.anexa_id}
      remainingEur={detail.remaining_eur} anexaTotalEur={detail.anexa_total_eur}
      lines={lines} invoices={detail.invoices} defaultIntocmit={defaultIntocmit} onCreated={onCreated}
      preSelectedIds={selectedIds} />
    <InvoiceDialog open={invoiceOpen} onOpenChange={setInvoiceOpen} anexaId={detail.anexa_id}
      unpairedProformas={unpairedProformas} defaultIntocmit={defaultIntocmit} onCreated={onCreated}
      preSelectedLineIds={selectedIds} />
    <ActionDialog open={stornoOpen} onOpenChange={setStornoOpen} anexaId={detail.anexa_id} action="storno"
      defaultIntocmit={defaultIntocmit} onCreated={onCreated} lineIds={[...selectedIds]} lines={lines} />
    <ActionDialog open={finalOpen} onOpenChange={setFinalOpen} anexaId={detail.anexa_id} action="final"
      defaultIntocmit={defaultIntocmit} onCreated={onCreated} lineIds={[...selectedIds]} lines={lines} />
    </>
  )
}

// ── Proforma Dialog (with line selection) ───────────────────────

function ProformaDialog({ open, onOpenChange, anexaId, remainingEur, anexaTotalEur, lines, invoices, defaultIntocmit, onCreated, preSelectedIds }: {
  open: boolean; onOpenChange: (v: boolean) => void; anexaId: number
  remainingEur: number; anexaTotalEur: number; lines: AnexaLine[]; invoices?: InvoiceDetail[]; defaultIntocmit?: string; onCreated: () => void
  preSelectedIds?: Set<number>
}) {
  // A car is "covered" (unselectable) only if its next action is NOT proforma
  const coveredIds = new Set(lines.filter(l => getCarNextAction(l) !== 'PROFORMA').map(l => l.id))
  const uncoveredLines = lines.filter(l => !coveredIds.has(l.id))
  const defaultSelection = preSelectedIds && preSelectedIds.size > 0
    ? new Set([...preSelectedIds].filter(id => !coveredIds.has(id)))
    : new Set(uncoveredLines.map(l => l.id))
  const [selectedIds, setSelectedIds] = useState<Set<number>>(defaultSelection)
  const [amount, setAmount] = useState('')
  const [percent, setPercent] = useState('')
  const [splitMode, setSplitMode] = useState<'equal' | 'proportional'>('proportional')
  const [startNo, setStartNo] = useState('')
  const [issuedDate, setIssuedDate] = useState(new Date().toISOString().split('T')[0])
  const [kurs, setKurs] = useState<string | null>(null)
  const [kursDate, setKursDate] = useState('')
  const [intocmitDe, setIntocmitDe] = useState(defaultIntocmit || '')
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Reset selection and start number when dialog opens
  useEffect(() => {
    if (!open) return
    const covered = new Set(lines.filter(l => getCarNextAction(l) !== 'PROFORMA').map(l => l.id))
    if (preSelectedIds && preSelectedIds.size > 0) {
      setSelectedIds(new Set([...preSelectedIds].filter(id => !covered.has(id))))
    } else {
      setSelectedIds(new Set(lines.filter(l => !covered.has(l.id)).map(l => l.id)))
    }
    // Auto-suggest next invoice number based on existing invoices on this anexa
    const maxNo = (invoices || []).reduce((m, i) => Math.max(m, i.invoice_number || 0), 0)
    setStartNo(maxNo > 0 ? String(maxNo + 1) : '')
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  const selectedLines = lines.filter(l => selectedIds.has(l.id))
  const selectedPrices = selectedLines.map(l => l.selling_price_eur)
  const selectedTotal = selectedPrices.reduce((s, p) => s + p, 0)
  const carCount = selectedLines.length
  const allSelected = uncoveredLines.length > 0 && uncoveredLines.every(l => selectedIds.has(l.id))

  const toggleLine = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }
  const toggleAll = () => {
    if (allSelected) setSelectedIds(new Set())
    else setSelectedIds(new Set(uncoveredLines.map(l => l.id)))
  }

  // Recalculate amount when selection or percent changes
  const recalcAmount = (pct: string, prices: number[], total: number, mode: string) => {
    if (!pct) return
    const p = parseFloat(pct) / 100
    if (mode === 'proportional') setAmount(prices.reduce((s, cp) => s + cp * p, 0).toFixed(2))
    else if (total > 0) setAmount((p * total).toFixed(2))
  }

  useEffect(() => {
    if (percent) recalcAmount(percent, selectedPrices, selectedTotal, splitMode)
  }, [selectedIds.size]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!issuedDate) return
    fetch(`/facturare/api/bnr-rate?date=${issuedDate}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.success) { setKurs(String(data.kurs)); setKursDate(data.kurs_date) } })
      .catch(() => {})
  }, [issuedDate])

  const handleSubmit = async () => {
    if (carCount === 0) { toast.error('Select at least one vehicle'); return }
    if (!amount || parseFloat(amount) <= 0) { toast.error('Amount required'); return }
    if (!startNo) { toast.error('Invoice No. required'); return }
    setSubmitting(true)
    try {
      const res = await fetch('/facturare/api/invoices/proforma', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          anexa_id: anexaId, amount_eur: parseFloat(amount),
          split_mode: splitMode,
          line_ids: Array.from(selectedIds),
          invoice_number: startNo ? parseInt(startNo) : undefined,
          issued_date: issuedDate || undefined, intocmit_de: intocmitDe || undefined, notes: notes || undefined,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Failed')
      toast.success('Proforma created'); onOpenChange(false); onCreated()
    } catch (err: any) { toast.error(err.message) }
    finally { setSubmitting(false) }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] flex flex-col">
        <DialogHeader className="flex-shrink-0">
          <DialogTitle>Issue Proforma</DialogTitle>
          <DialogDescription>
            {carCount === 1 ? (
              <>{selectedLines[0].model} — Remaining: <span className="font-mono font-semibold">{fmtEur(selectedLines.reduce((s, l) => s + l.selling_price_eur - (l.proforma_eur || 0), 0))} EUR</span></>
            ) : carCount > 1 ? (
              <>{carCount} vehicles — Remaining: <span className="font-mono font-semibold">{fmtEur(selectedLines.reduce((s, l) => s + l.selling_price_eur - (l.proforma_eur || 0), 0))} EUR</span></>
            ) : (
              <>Anexa total: {fmtEur(anexaTotalEur)} EUR — Remaining: <span className="font-mono font-semibold">{fmtEur(remainingEur)} EUR</span></>
            )}
          </DialogDescription>
        </DialogHeader>
        <div className="flex-1 overflow-y-auto space-y-3 pr-1">
          {/* Vehicle selection — only show if multiple cars and not pre-selected from VehicleTable */}
          {uncoveredLines.length > 1 && selectedIds.size !== 1 && (
            <div className="border rounded-md">
              <div className="flex items-center gap-2 px-3 py-1.5 bg-muted/40 border-b">
                <input type="checkbox" checked={allSelected} onChange={toggleAll} className="rounded" />
                <span className="text-xs font-medium text-muted-foreground">Select vehicles ({selectedIds.size}/{uncoveredLines.length})</span>
              </div>
              <div className="max-h-[200px] overflow-y-auto">
                {uncoveredLines.map(l => (
                  <label key={l.id} className={`flex items-center gap-2 px-3 py-1 text-xs hover:bg-muted/20 cursor-pointer ${selectedIds.has(l.id) ? '' : 'opacity-50'}`}>
                    <input type="checkbox" checked={selectedIds.has(l.id)} onChange={() => toggleLine(l.id)} className="rounded" />
                    <span className="font-mono text-muted-foreground w-12 shrink-0">{l.nr_comanda || '—'}</span>
                    <span className="flex-1 truncate">{l.model}</span>
                    <span className="font-mono text-muted-foreground">{fmtEur(l.selling_price_eur)}</span>
                  </label>
                ))}
              </div>
            </div>
          )}
          <div className="grid grid-cols-[70px_1fr_1fr_1fr] gap-3">
            <div>
              <Label>%</Label>
              <Input type="number" step="0.1" min="0" max="100" placeholder="10"
                value={percent}
                onChange={e => {
                  const p = e.target.value
                  setPercent(p)
                  recalcAmount(p, selectedPrices, selectedTotal, splitMode)
                }} />
            </div>
            <div>
              <Label>Total EUR *</Label>
              <Input type="number" step="0.01" placeholder="20130"
                value={amount}
                onChange={e => {
                  const a = e.target.value
                  setAmount(a)
                  if (a && selectedTotal > 0) {
                    setPercent(((parseFloat(a) / selectedTotal) * 100).toFixed(1))
                  }
                }} />
            </div>
            <div><Label>Start No.</Label><Input type="number" placeholder="9102842" value={startNo} onChange={e => setStartNo(e.target.value)} /></div>
            <div><Label>Date</Label><Input type="date" value={issuedDate} onChange={e => setIssuedDate(e.target.value)} /></div>
          </div>
          {/* Split mode + per-car breakdown */}
          {carCount > 0 && (
            <div className="text-xs bg-muted/30 rounded-md px-3 py-2 space-y-1">
              <div className="flex items-center gap-3">
                <span className="text-muted-foreground">Split:</span>
                <button className={`px-2 py-0.5 rounded ${splitMode === 'equal' ? 'bg-foreground text-background' : 'bg-muted'}`}
                  onClick={() => {
                    setSplitMode('equal')
                    if (percent) setAmount(((parseFloat(percent) / 100) * selectedTotal).toFixed(2))
                  }}>Equal per car</button>
                <button className={`px-2 py-0.5 rounded ${splitMode === 'proportional' ? 'bg-foreground text-background' : 'bg-muted'}`}
                  onClick={() => {
                    setSplitMode('proportional')
                    if (percent) setAmount(selectedPrices.reduce((s, cp) => s + cp * (parseFloat(percent) / 100), 0).toFixed(2))
                  }}>% of each car price</button>
              </div>
              {amount && (
                <div className="text-muted-foreground pt-1 space-y-0.5">
                  <div className="flex justify-between">
                    {splitMode === 'equal' ? (
                      <span>{carCount} vehicle(s) × <span className="font-mono">{fmtEur(parseFloat(amount) / carCount)}</span> EUR each</span>
                    ) : (
                      <span>{carCount} vehicle(s) × <span className="font-mono">{percent || '?'}%</span> of unit price</span>
                    )}
                    {startNo && <span className="font-mono">No: {startNo}–{parseInt(startNo) + carCount - 1}</span>}
                  </div>
                  {splitMode === 'proportional' && percent && selectedPrices.some((p, i) => i > 0 && p !== selectedPrices[0]) && (
                    <div className="text-[10px] text-muted-foreground/70">
                      {selectedPrices.map((cp, i) => (
                        <span key={i} className="mr-2">{fmtEur(cp * parseFloat(percent) / 100)}</span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
          {kurs && (
            <div className="text-sm bg-muted/50 rounded-md px-3 py-2">
              BNR Kurs ({kursDate}): <span className="font-mono font-medium">{kurs}</span>
              {amount && <span className="ml-2 text-muted-foreground">= {fmtEur(parseFloat(amount) * parseFloat(kurs))} RON</span>}
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Intocmit de</Label><UserSearchInput value={intocmitDe} onChange={setIntocmitDe} /></div>
            <div><Label>Notes</Label><Input placeholder="10% advance" value={notes} onChange={e => setNotes(e.target.value)} /></div>
          </div>
        </div>
        <DialogFooter className="flex-shrink-0">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={submitting}>{submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />} Issue Proforma</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Invoice Dialog ──────────────────────────────────────────────

function InvoiceDialog({ open, onOpenChange, anexaId, unpairedProformas, defaultIntocmit, onCreated, preSelectedLineIds }: {
  open: boolean; onOpenChange: (v: boolean) => void; anexaId: number
  unpairedProformas: { sequence_number: number; total_amount_eur: number; invoice_number: number | null; line_ids: number[] | null }[]
  defaultIntocmit?: string; onCreated: () => void; preSelectedLineIds?: Set<number>
}) {
  const [selectedSeq, setSelectedSeq] = useState('')
  const [invoiceNumber, setInvoiceNumber] = useState('')
  const [issuedDate, setIssuedDate] = useState(new Date().toISOString().split('T')[0])
  const [intocmitDe, setIntocmitDe] = useState(defaultIntocmit || '')
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Auto-select the proforma matching the selected cars when dialog opens
  useEffect(() => {
    if (!open) return
    if (preSelectedLineIds && preSelectedLineIds.size > 0) {
      const match = unpairedProformas.find(p => {
        if (!p.line_ids) return true // null = all lines
        return p.line_ids.some(id => preSelectedLineIds.has(id))
      })
      if (match) { setSelectedSeq(String(match.sequence_number)); return }
    }
    if (unpairedProformas.length > 0) setSelectedSeq(String(unpairedProformas[0].sequence_number))
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleSubmit = async () => {
    if (!selectedSeq) { toast.error('Select a proforma'); return }
    if (!invoiceNumber) { toast.error('Invoice No. required'); return }
    setSubmitting(true)
    try {
      const res = await fetch('/facturare/api/invoices/invoice', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          anexa_id: anexaId, sequence_number: parseInt(selectedSeq),
          invoice_number: invoiceNumber ? parseInt(invoiceNumber) : undefined,
          issued_date: issuedDate || undefined, intocmit_de: intocmitDe || undefined,
          notes: notes || undefined,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Failed')
      toast.success(`Invoice issued`); onOpenChange(false); onCreated()
    } catch (err: any) { toast.error(err.message) }
    finally { setSubmitting(false) }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>Issue Invoice</DialogTitle><DialogDescription>Confirm payment of a proforma</DialogDescription></DialogHeader>
        <div className="space-y-4">
          <div>
            <Label>Proforma to confirm *</Label>
            <Select value={selectedSeq} onValueChange={setSelectedSeq}>
              <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
              <SelectContent>
                {unpairedProformas.map(p => (
                  <SelectItem key={p.sequence_number} value={String(p.sequence_number)}>
                    Proforma #{p.sequence_number} — {fmtEur(p.total_amount_eur)} EUR ({p.line_ids?.length || 'all'} cars)
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div><Label>Invoice No.</Label><Input type="number" placeholder="9102842" value={invoiceNumber} onChange={e => setInvoiceNumber(e.target.value)} /></div>
            <div><Label>Date</Label><Input type="date" value={issuedDate} onChange={e => setIssuedDate(e.target.value)} /></div>
            <div><Label>Intocmit de</Label><UserSearchInput value={intocmitDe} onChange={setIntocmitDe} /></div>
          </div>
          <div><Label>Notes</Label><Input placeholder="Optional" value={notes} onChange={e => setNotes(e.target.value)} /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={submitting}>{submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />} Issue Invoice</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Action Dialog (Storno / Final) ──────────────────────────────

function ActionDialog({ open, onOpenChange, anexaId, action, defaultIntocmit, onCreated, lineIds, lines }: {
  open: boolean; onOpenChange: (v: boolean) => void; anexaId: number; action: 'storno' | 'final'
  defaultIntocmit?: string; onCreated: () => void; lineIds?: number[]; lines?: AnexaLine[]
}) {
  const [invoiceNumber, setInvoiceNumber] = useState('')
  const [issuedDate, setIssuedDate] = useState(new Date().toISOString().split('T')[0])
  const [intocmitDe, setIntocmitDe] = useState(defaultIntocmit || '')
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const selectedLines = (lines || []).filter(l => lineIds?.includes(l.id))
  const selectedTotal = selectedLines.reduce((s, l) => s + l.selling_price_eur, 0)

  const handleSubmit = async () => {
    if (!invoiceNumber) { toast.error('Invoice No. required'); return }
    setSubmitting(true)
    try {
      const res = await fetch(`/facturare/api/invoices/${action}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          anexa_id: anexaId,
          invoice_number: invoiceNumber ? parseInt(invoiceNumber) : undefined,
          issued_date: issuedDate || undefined, intocmit_de: intocmitDe || undefined,
          notes: notes || undefined,
          line_ids: lineIds && lineIds.length > 0 ? lineIds : undefined,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Failed')
      toast.success(`${action === 'storno' ? 'Storno' : 'Final'} issued`); onOpenChange(false); onCreated()
    } catch (err: any) { toast.error(err.message) }
    finally { setSubmitting(false) }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Issue {action === 'storno' ? 'Storno' : 'Final'}</DialogTitle>
          {selectedLines.length === 1 && (
            <DialogDescription>{selectedLines[0].model} — {fmtEur(selectedTotal)} EUR</DialogDescription>
          )}
        </DialogHeader>
        <div className="space-y-4">
          {selectedLines.length > 1 && (
            <div className="rounded border bg-muted/30 p-2 text-xs space-y-1">
              <div className="font-medium text-muted-foreground">{selectedLines.length} vehicles — {fmtEur(selectedTotal)} EUR</div>
              {selectedLines.map(l => (
                <div key={l.id} className="flex gap-2">
                  <span className="font-mono text-muted-foreground w-12">{l.nr_comanda || '—'}</span>
                  <span className="flex-1 truncate">{l.model}</span>
                  <span className="font-mono">{fmtEur(l.selling_price_eur)}</span>
                </div>
              ))}
            </div>
          )}
          <div className="grid grid-cols-3 gap-3">
            <div><Label>Invoice No.</Label><Input type="number" placeholder="9102842" value={invoiceNumber} onChange={e => setInvoiceNumber(e.target.value)} /></div>
            <div><Label>Date</Label><Input type="date" value={issuedDate} onChange={e => setIssuedDate(e.target.value)} /></div>
            <div><Label>Intocmit de</Label><UserSearchInput value={intocmitDe} onChange={setIntocmitDe} /></div>
          </div>
          <div><Label>Notes</Label><Input placeholder="Optional" value={notes} onChange={e => setNotes(e.target.value)} /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={submitting} variant={action === 'storno' ? 'destructive' : 'default'}>
            {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />} Issue {action === 'storno' ? 'Storno' : 'Final'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Anexa Detail Panel ──────────────────────────────────────────

function AnexaDetailPanel({ anexaId, onAction, onDetailLoaded }: {
  anexaId: number; onAction: () => void;
  onDetailLoaded?: (detail: AnexaDetail | null) => void
}) {
  const [detail, setDetail] = useState<AnexaDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [linesExpanded, setLinesExpanded] = useState(false)
  const [collapsedCycles, setCollapsedCycles] = useState<Set<string>>(new Set())
  const toggleCycle = (key: string) => setCollapsedCycles(prev => {
    const next = new Set(prev); next.has(key) ? next.delete(key) : next.add(key); return next
  })

  const load = useCallback(() => {
    setLoading(true)
    fetch(`/facturare/api/anexas/${anexaId}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { setDetail(d); onDetailLoaded?.(d) })
      .catch(() => { setDetail(null); onDetailLoaded?.(null) })
      .finally(() => setLoading(false))
  }, [anexaId]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load() }, [load])

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin" /></div>
  if (!detail) return <div className="text-center py-8 text-muted-foreground">Not found</div>

  const handleCreated = () => { load(); onAction() }

  return (
    <div className="bg-blue-50/30 dark:bg-blue-950/10 border-t border-blue-100 dark:border-blue-900/30">
      {/* Vehicle lines (edit only when no invoices) */}
      {detail.invoices.length === 0 && (
        <div className="px-3 py-2 border-b border-blue-100 dark:border-blue-900/30">
          <button className="flex items-center justify-between text-xs text-muted-foreground hover:text-foreground w-full"
            onClick={() => setLinesExpanded(!linesExpanded)}>
            <span className="flex items-center gap-1">
              {linesExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              {detail.lines.length} vehicle(s) — edit lines
            </span>
          </button>
          {linesExpanded && (
            <div className="text-xs space-y-1 mt-2">
              {detail.lines.map(l => (
                <EditableAnexaLine key={l.id} line={l} canDelete={detail.invoices.length === 0} onUpdated={load} />
              ))}
              <AddVehicleInline anexaId={anexaId} nextLineNumber={detail.lines.length + 1}
                nextNrComanda={detail.lines.length > 0 ? String((parseInt(detail.lines[detail.lines.length - 1].nr_comanda || '0') || 0) + 1) : ''}
                onAdded={load} />
            </div>
          )}
        </div>
      )}

      {/* Invoice table — grouped by date, collapsible */}
      {detail.invoices.length > 0 && (() => {
        const typeOrder: Record<string, number> = { PROFORMA: 0, INVOICE: 1, STORNO: 2, FINAL: 3 }
        // Group by issued_date
        const dateMap = new Map<string, InvoiceDetail[]>()
        for (const inv of detail.invoices) {
          const key = inv.issued_date || 'no-date'
          if (!dateMap.has(key)) dateMap.set(key, [])
          dateMap.get(key)!.push(inv)
        }
        const groups: { key: string; label: string; invoices: InvoiceDetail[]; totalEur: number }[] = []
        for (const [key, invs] of dateMap) {
          const label = key !== 'no-date'
            ? new Date(key).toLocaleDateString('ro-RO', { day: '2-digit', month: '2-digit', year: 'numeric', weekday: 'short' })
            : 'No date'
          invs.sort((a, b) => (typeOrder[a.invoice_type] ?? 9) - (typeOrder[b.invoice_type] ?? 9) || a.sequence_number - b.sequence_number)
          const totalEur = invs.reduce((s, i) => s + i.total_amount_eur, 0)
          groups.push({ key, label, invoices: invs, totalEur })
        }
        groups.sort((a, b) => a.key.localeCompare(b.key))
        return (
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b bg-blue-50/50 dark:bg-blue-950/20">
                <th className="text-left px-3 py-1 font-medium">Type</th>
                <th className="text-left px-2 py-1 font-medium">No.</th>
                <th className="text-center px-2 py-1 font-medium">Cars</th>
                <th className="text-left px-2 py-1 font-medium">By</th>
                <th className="text-right px-2 py-1 font-medium">EUR</th>
                <th className="text-right px-2 py-1 font-medium">RON</th>
                <th className="w-16"></th>
              </tr>
            </thead>
            <tbody>
              {groups.map(group => {
                const isCollapsed = collapsedCycles.has(group.key)
                return (
                  <React.Fragment key={group.key}>
                    <tr className="bg-muted/30 cursor-pointer hover:bg-muted/50"
                      onClick={() => toggleCycle(group.key)}>
                      <td colSpan={4} className="px-3 py-1.5 text-[11px]">
                        <span className="flex items-center gap-1.5">
                          {isCollapsed ? <ChevronRight className="h-3 w-3 shrink-0" /> : <ChevronDown className="h-3 w-3 shrink-0" />}
                          <span className="font-medium">{group.label}</span>
                          <span className="text-muted-foreground/60 shrink-0">{group.invoices.length} docs</span>
                        </span>
                      </td>
                      <td className="px-2 py-1.5 text-right font-mono text-[11px] text-muted-foreground">{fmtEur(group.totalEur)}</td>
                      <td></td>
                      <td></td>
                    </tr>
                    {!isCollapsed && group.invoices.map((inv, idx) => (
                      <tr key={inv.id} className="border-b border-blue-100 dark:border-blue-900/30 last:border-0 hover:bg-blue-50/50">
                        <td className="px-3 py-1.5 pl-8">
                          <Badge className={`text-xs ${TYPE_COLORS[inv.invoice_type] || ''}`}>
                            {TYPE_LABELS[inv.invoice_type]}
                          </Badge>
                        </td>
                        <td className="px-2 py-1.5 font-mono text-muted-foreground">
                          {inv.invoice_number || '—'}
                        </td>
                        <td className="px-2 py-1.5 text-muted-foreground">
                          {inv.line_ids?.length || detail.lines.length}/{detail.lines.length} cars
                        </td>
                        <td className="px-2 py-1.5 text-muted-foreground max-w-[80px] truncate">{inv.intocmit_de || '—'}</td>
                        <td className="px-2 py-1.5 text-right font-mono">{fmtEur(inv.total_amount_eur)}</td>
                        <td className="px-2 py-1.5 text-right font-mono text-muted-foreground">
                          {inv.total_amount_ron !== 0 ? fmtEur(inv.total_amount_ron) : '—'}
                        </td>
                        <td className="px-2 py-1.5 text-right">
                          <div className="flex items-center justify-end gap-0.5">
                            <Button variant="ghost" size="icon" className="h-5 w-5" title="Download merged PDF"
                              onClick={(e) => { e.stopPropagation(); window.open(`/facturare/api/invoices/${inv.id}/pdf?mode=merged`, '_blank') }}>
                              <Download className="h-3 w-3 text-red-500" />
                            </Button>
                            {(inv.line_ids?.length || detail.lines.length) > 1 && (
                              <Button variant="ghost" size="icon" className="h-5 w-5" title="Download individual PDFs (ZIP)"
                                onClick={(e) => { e.stopPropagation(); window.open(`/facturare/api/invoices/${inv.id}/pdf?mode=individual`, '_blank') }}>
                                <Archive className="h-3 w-3 text-amber-500" />
                              </Button>
                            )}
                            {inv.invoice_type !== 'PROFORMA' && (
                              <Button variant="ghost" size="icon" className="h-5 w-5" title="Download EuroFib XLSX"
                                onClick={(e) => { e.stopPropagation(); window.open(`/facturare/api/invoices/${inv.id}/eurofib`, '_blank') }}>
                                <FileSpreadsheet className="h-3 w-3 text-emerald-500" />
                              </Button>
                            )}
                            {idx === group.invoices.length - 1 && (
                              <Button variant="ghost" size="icon" className="h-5 w-5" title="Delete"
                                onClick={async (e) => {
                                  e.stopPropagation()
                                  if (!confirm(`Delete ${TYPE_LABELS[inv.invoice_type]} #${inv.sequence_number}?`)) return
                                  try {
                                    const res = await fetch(`/facturare/api/invoices/${inv.id}`, { method: 'DELETE' })
                                    const data = await res.json()
                                    if (!res.ok) throw new Error(data.error || 'Failed')
                                    toast.success('Deleted'); handleCreated()
                                  } catch (err: any) { toast.error(err.message) }
                                }}><Trash2 className="h-3 w-3 text-muted-foreground hover:text-red-500" /></Button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </React.Fragment>
                )
              })}
            </tbody>
          </table>
        )
      })()}

      {/* Dialogs removed — handled by VehicleTable */}
    </div>
  )
}

// ── Main ComenziTab ─────────────────────────────────────────────

export default function ComenziTab({ companies }: { companies: Company[] }) {
  const [contracts, setContracts] = useState<ContractSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [createContractOpen, setCreateContractOpen] = useState(false)
  const [currentUserName, setCurrentUserName] = useState('')

  // Fetch current logged-in user name once
  useEffect(() => {
    fetch('/api/auth/current-user')
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.user?.name) setCurrentUserName(data.user.name) })
      .catch(() => {})
  }, [])

  // Drill-down into a contract
  const initialContractId = React.useRef(new URLSearchParams(window.location.search).get('ccontract'))
  const [drillContract, setDrillContract] = useState<ContractSummary | null>(null)
  const [anexas, setAnexas] = useState<AnexaSummary[]>([])
  const [anexasLoading, setAnexasLoading] = useState(false)
  const [createAnexaOpen, setCreateAnexaOpen] = useState(false)

  // Detail panel for an anexa (persisted in URL)
  const [selectedAnexaId, setSelectedAnexaId] = useState<number | null>(() => {
    const v = new URLSearchParams(window.location.search).get('canexa')
    return v ? parseInt(v) : null
  })
  const [anexaDetail, setAnexaDetail] = useState<AnexaDetail | null>(null)

  // Filters (persisted in URL)
  const [searchQuery, setSearchQuery] = useState(() => new URLSearchParams(window.location.search).get('cq') || '')
  const [filterCompany, setFilterCompany] = useState(() => new URLSearchParams(window.location.search).get('ccompany') || 'all')
  const [filterClient, setFilterClient] = useState(() => new URLSearchParams(window.location.search).get('cclient') || 'all')

  const [datePeriod, setDatePeriod] = useState(() => new URLSearchParams(window.location.search).get('cperiod') || 'all')
  const [dateFrom, setDateFrom] = useState(() => new URLSearchParams(window.location.search).get('cfrom') || '')
  const [dateTo, setDateTo] = useState(() => new URLSearchParams(window.location.search).get('cto') || '')

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

  useEffect(() => {
    const url = new URL(window.location.href)
    searchQuery ? url.searchParams.set('cq', searchQuery) : url.searchParams.delete('cq')
    filterCompany !== 'all' ? url.searchParams.set('ccompany', filterCompany) : url.searchParams.delete('ccompany')
    filterClient !== 'all' ? url.searchParams.set('cclient', filterClient) : url.searchParams.delete('cclient')
    datePeriod !== 'all' ? url.searchParams.set('cperiod', datePeriod) : url.searchParams.delete('cperiod')
    dateFrom ? url.searchParams.set('cfrom', dateFrom) : url.searchParams.delete('cfrom')
    dateTo ? url.searchParams.set('cto', dateTo) : url.searchParams.delete('cto')
    selectedAnexaId ? url.searchParams.set('canexa', String(selectedAnexaId)) : url.searchParams.delete('canexa')
    // Preserve ccontract during initial restore (before contracts load)
    if (drillContract) {
      url.searchParams.set('ccontract', String(drillContract.id))
      initialContractId.current = null // restore complete
    } else if (!initialContractId.current) {
      url.searchParams.delete('ccontract')
    }
    window.history.replaceState({}, '', url.toString())
  }, [searchQuery, filterCompany, filterClient, datePeriod, dateFrom, dateTo, selectedAnexaId, drillContract])

  const loadContracts = useCallback(() => {
    setLoading(true)
    fetch('/facturare/api/contracts')
      .then(r => r.ok ? r.json() : { contracts: [] })
      .then(data => setContracts(data.contracts || []))
      .catch(() => setContracts([]))
      .finally(() => setLoading(false))
  }, [])
  useEffect(() => { loadContracts() }, [loadContracts])

  // Restore drill-down from URL on initial load
  useEffect(() => {
    if (contracts.length === 0 || drillContract) return
    const contractId = initialContractId.current
    if (!contractId) return
    const c = contracts.find(x => x.id === parseInt(contractId))
    if (c) {
      setDrillContract(c); setAnexasLoading(true)
      fetch(`/facturare/api/contracts/${c.id}/anexas`)
        .then(r => r.ok ? r.json() : { anexas: [] })
        .then(data => setAnexas(data.anexas || []))
        .catch(() => setAnexas([]))
        .finally(() => setAnexasLoading(false))
    }
  }, [contracts]) // eslint-disable-line react-hooks/exhaustive-deps

  const loadAnexas = (contract: ContractSummary) => {
    setDrillContract(contract); setSelectedAnexaId(null); setAnexasLoading(true)
    fetch(`/facturare/api/contracts/${contract.id}/anexas`)
      .then(r => r.ok ? r.json() : { anexas: [] })
      .then(data => setAnexas(data.anexas || []))
      .catch(() => setAnexas([]))
      .finally(() => setAnexasLoading(false))
  }

  // Refresh anexa list without resetting selection
  const refreshAnexas = () => {
    if (!drillContract) return
    fetch(`/facturare/api/contracts/${drillContract.id}/anexas`)
      .then(r => r.ok ? r.json() : { anexas: [] })
      .then(data => setAnexas(data.anexas || []))
      .catch(() => {})
  }

  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set())
  const toggleGroup = (key: string) => setExpandedGroups(prev => {
    const next = new Set(prev)
    next.has(key) ? next.delete(key) : next.add(key)
    return next
  })

  const uniqueCompanies = [...new Set(contracts.map(c => c.supplier_name))].sort()
  const uniqueClients = [...new Set(contracts.map(c => c.customer_name))].sort()

  const filtered = contracts.filter(c => {
    if (filterCompany !== 'all' && c.supplier_name !== filterCompany) return false
    if (filterClient !== 'all' && c.customer_name !== filterClient) return false
    if (dateFrom && (!c.contract_date || c.contract_date < dateFrom)) return false
    if (dateTo && (!c.contract_date || c.contract_date > dateTo)) return false
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      if (!c.contract_ref.toLowerCase().includes(q) && !c.customer_name.toLowerCase().includes(q) && !c.supplier_name.toLowerCase().includes(q)) return false
    }
    return true
  })

  // Group by Company + Client
  const grouped = filtered.reduce<Record<string, { supplier: string; client: string; contracts: ContractSummary[] }>>((acc, c) => {
    const key = `${c.supplier_name}|||${c.customer_name}`
    if (!acc[key]) acc[key] = { supplier: c.supplier_name, client: c.customer_name, contracts: [] }
    acc[key].contracts.push(c)
    return acc
  }, {})
  const groups = Object.entries(grouped).sort(([, a], [, b]) => {
    const latestA = Math.max(...a.contracts.map(c => c.created_at ? new Date(c.created_at).getTime() : 0))
    const latestB = Math.max(...b.contracts.map(c => c.created_at ? new Date(c.created_at).getTime() : 0))
    return latestB - latestA
  })

  return (
    <>
    <div className="space-y-3">
      <div className="space-y-3">

        {drillContract ? (
          /* ── Drill-down: Anexas for a contract ── */
          <>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Button variant="outline" size="sm" onClick={() => { setDrillContract(null); setSelectedAnexaId(null) }}>← Back</Button>
                <div>
                  <h3 className="font-semibold text-sm">{drillContract.contract_ref}</h3>
                  <p className="text-xs text-muted-foreground">{drillContract.customer_name} — {drillContract.supplier_name}</p>
                </div>
              </div>
              {!selectedAnexaId && <Button size="sm" onClick={() => setCreateAnexaOpen(true)}><Plus className="h-4 w-4 mr-1" /> New Anexa</Button>}
            </div>

            <Card>
              <CardContent className="p-0 overflow-x-auto">
                <table className="w-full text-sm min-w-[400px]">
                  <thead>
                    <tr className="border-b bg-muted/50">
                      <th className="text-left px-3 py-2.5 font-medium">Anexa</th>
                      <th className="text-center px-3 py-2.5 font-medium">Cars</th>
                      <th className="text-left px-3 py-2.5 font-medium">Stage</th>
                      <th className="text-left px-3 py-2.5 font-medium">Status</th>
                      <th className="text-right px-3 py-2.5 font-medium">Value EUR</th>
                      <th className="text-right px-3 py-2.5 font-medium">Invoiced</th>
                      <th className="text-center px-3 py-2.5 font-medium">%</th>
                      <th className="w-10"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {anexasLoading && <tr><td colSpan={8} className="text-center py-8"><Loader2 className="h-5 w-5 animate-spin inline" /></td></tr>}
                    {!anexasLoading && anexas.length === 0 && <tr><td colSpan={8} className="text-center py-8 text-muted-foreground">No anexas yet</td></tr>}
                    {anexas.map(a => {
                      const cfg = STAGE_CONFIG[a.stage] || STAGE_CONFIG.NEW
                      const isSelected = selectedAnexaId === a.id
                      return (
                        <React.Fragment key={a.id}>
                        <tr className={`border-b hover:bg-muted/30 cursor-pointer ${isSelected ? 'bg-primary/5' : ''}`}
                          onClick={() => setSelectedAnexaId(isSelected ? null : a.id)}>
                          <td className="px-3 py-2.5 font-medium">
                            <span className="flex items-center gap-1">
                              <ChevronRight className={`h-3.5 w-3.5 transition-transform text-muted-foreground ${isSelected ? 'rotate-90' : ''}`} />
                              Anexa {a.anexa_number}
                            </span>
                          </td>
                          <td className="px-3 py-2.5 text-center"><Badge variant="outline" className="text-xs">{a.line_count}</Badge></td>
                          <td className="px-3 py-2.5"><Badge className={`${cfg.color} text-xs`}>{cfg.label}</Badge></td>
                          <td className="px-3 py-1" onClick={e => e.stopPropagation()}>
                            <Select value={a.status} onValueChange={async (v) => {
                              try {
                                const res = await fetch(`/facturare/api/anexas/${a.id}/status`, {
                                  method: 'PATCH', headers: { 'Content-Type': 'application/json' },
                                  body: JSON.stringify({ status: v }),
                                })
                                if (!res.ok) throw new Error('Failed')
                                refreshAnexas()
                              } catch { toast.error('Failed to update status') }
                            }}>
                              <SelectTrigger className="h-7 w-[130px] text-xs">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {STATUS_KEYS.map(s => (
                                  <SelectItem key={s} value={s}>
                                    <span className={`inline-block px-1 py-0.5 rounded text-xs ${STATUS_CONFIG[s].color}`}>{STATUS_CONFIG[s].label}</span>
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </td>
                          <td className="px-3 py-2.5 text-right font-mono">{fmtEur(a.total_value)}</td>
                          <td className="px-3 py-2.5 text-right font-mono text-xs">{a.invoiced_total > 0 ? fmtEur(a.invoiced_total) : '—'}</td>
                          <td className="px-3 py-2.5 text-center">
                            <div className="flex items-center gap-1 justify-center" title={`Proforma: ${a.pct_proforma}% | Invoiced: ${a.pct_invoiced}%`}>
                              <div className="w-16 h-2 bg-muted rounded-full overflow-hidden">
                                <div className={`h-full rounded-full ${a.pct_invoiced >= 100 ? 'bg-emerald-500' : a.pct_invoiced >= 50 ? 'bg-amber-400' : 'bg-blue-400'}`} style={{ width: `${Math.min(a.pct_invoiced, 100)}%` }} />
                              </div>
                              <span className="text-xs text-muted-foreground">{a.pct_invoiced}%</span>
                            </div>
                          </td>
                          <td className="px-3 py-2.5 text-right">
                            {a.stage === 'NEW' && (
                              <Button variant="ghost" size="icon" className="h-7 w-7" title="Delete anexa (no invoices yet)"
                                onClick={async (e) => {
                                  e.stopPropagation()
                                  if (!confirm(`Delete Anexa ${a.anexa_number} and all its vehicles?`)) return
                                  try {
                                    const res = await fetch(`/facturare/api/anexas/${a.id}`, { method: 'DELETE' })
                                    const data = await res.json()
                                    if (!res.ok) throw new Error(data.error || 'Failed')
                                    toast.success('Anexa deleted')
                                    if (selectedAnexaId === a.id) setSelectedAnexaId(null)
                                    if (drillContract) loadAnexas(drillContract)
                                  } catch (err: any) { toast.error(err.message) }
                                }}>
                                <Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-red-500" />
                              </Button>
                            )}
                          </td>
                        </tr>
                        {isSelected && (
                          <tr>
                            <td colSpan={8} className="p-0">
                              <AnexaDetailPanel key={a.id} anexaId={a.id}
                                onAction={refreshAnexas}
                                onDetailLoaded={setAnexaDetail} />
                            </td>
                          </tr>
                        )}
                        </React.Fragment>
                      )
                    })}
                  </tbody>
                </table>
              </CardContent>
            </Card>

            {/* Statistics card removed */}

            <CreateAnexaDialog open={createAnexaOpen} onOpenChange={setCreateAnexaOpen} contractId={drillContract.id}
              onCreated={() => loadAnexas(drillContract)} />
          </>
        ) : (
          /* ── Main: Contract list ── */
          <>
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
              </div>
              <Button onClick={() => setCreateContractOpen(true)}><Plus className="h-4 w-4 mr-1" /> New Contract</Button>
            </div>

            <Card>
              <CardContent className="p-0 overflow-x-auto">
                <table className="w-full text-sm min-w-[900px]">
                  <thead>
                    <tr className="border-b bg-muted/50">
                      <th className="w-8"></th>
                      <th className="text-left px-3 py-2.5 font-medium">Company</th>
                      <th className="text-left px-3 py-2.5 font-medium">Client</th>
                      <th className="text-left px-3 py-2.5 font-medium">Contracts</th>
                      <th className="text-center px-3 py-2.5 font-medium">Anexe</th>
                      <th className="text-right px-3 py-2.5 font-medium whitespace-nowrap">Total EUR</th>
                      <th className="text-right px-3 py-2.5 font-medium whitespace-nowrap">Invoiced</th>
                      <th className="text-right px-3 py-2.5 font-medium whitespace-nowrap">Remaining</th>
                      <th className="text-center px-3 py-2.5 font-medium w-24">%</th>
                      <th className="w-8"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading && <tr><td colSpan={10} className="text-center py-8"><Loader2 className="h-5 w-5 animate-spin inline" /></td></tr>}
                    {!loading && groups.length === 0 && <tr><td colSpan={10} className="text-center py-8 text-muted-foreground">No contracts yet</td></tr>}
                    {groups.map(([key, g]) => {
                      const expanded = expandedGroups.has(key)
                      const totalVal = g.contracts.reduce((s, c) => s + c.total_value, 0)
                      const totalInv = g.contracts.reduce((s, c) => s + c.invoiced_total, 0)
                      const totalAnexe = g.contracts.reduce((s, c) => s + c.anexa_count, 0)
                      const remaining = totalVal - totalInv
                      return (
                        <React.Fragment key={key}>
                          {/* Group header row */}
                          <tr className="border-b hover:bg-muted/30 cursor-pointer" onClick={() => toggleGroup(key)}>
                            <td className="px-2 py-2.5 text-center">
                              {expanded ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                            </td>
                            <td className="px-3 py-2.5 text-xs text-muted-foreground max-w-[160px] truncate">{g.supplier}</td>
                            <td className="px-3 py-2.5 font-medium max-w-[180px] truncate">{g.client}</td>
                            <td className="px-3 py-2.5">
                              <Badge variant="outline" className="text-xs">{g.contracts.length}</Badge>
                            </td>
                            <td className="px-3 py-2.5 text-center"><Badge variant="outline" className="text-xs">{totalAnexe}</Badge></td>
                            <td className="px-3 py-2.5 text-right font-mono text-xs">{fmtEur(totalVal)}</td>
                            <td className="px-3 py-2.5 text-right font-mono text-xs text-emerald-600">{totalInv > 0 ? fmtEur(totalInv) : '—'}</td>
                            <td className="px-3 py-2.5 text-right font-mono text-xs">
                              {remaining > 0
                                ? <span className="text-amber-600">{fmtEur(remaining)}</span>
                                : <span className="text-emerald-600">0,00</span>}
                            </td>
                            <td className="px-3 py-2.5 text-center">
                              {totalVal > 0 && (
                                <div className="flex items-center gap-1 justify-center">
                                  <div className="w-12 h-2 bg-muted rounded-full overflow-hidden">
                                    <div className={`h-full rounded-full ${totalInv >= totalVal ? 'bg-emerald-500' : totalInv >= totalVal * 0.5 ? 'bg-amber-400' : 'bg-blue-400'}`}
                                      style={{ width: `${Math.min(Math.round(totalInv / totalVal * 100), 100)}%` }} />
                                  </div>
                                  <span className="text-xs text-muted-foreground">{Math.round(totalInv / totalVal * 100)}%</span>
                                </div>
                              )}
                            </td>
                            <td></td>
                          </tr>
                          {/* Expanded contract rows */}
                          {expanded && g.contracts.map(c => (
                            <tr key={c.id} className="border-b hover:bg-primary/5 cursor-pointer bg-muted/40" onClick={() => loadAnexas(c)}>
                              <td></td>
                              <td className="px-3 py-2 text-xs text-muted-foreground" colSpan={3}>
                                <span className="font-medium text-foreground">{c.contract_ref}</span>
                                <span className="ml-2 text-muted-foreground">{c.contract_date ? new Date(c.contract_date).toLocaleDateString('ro-RO') : ''}</span>
                                {c.responsible && <span className="ml-2 text-muted-foreground">· {c.responsible}</span>}
                              </td>
                              <td className="px-3 py-2 text-center"><Badge variant="outline" className="text-xs">{c.anexa_count}</Badge></td>
                              <td className="px-3 py-2 text-right font-mono text-xs">{fmtEur(c.total_value)}</td>
                              <td className="px-3 py-2 text-right font-mono text-xs text-emerald-600">{c.invoiced_total > 0 ? fmtEur(c.invoiced_total) : '—'}</td>
                              <td className="px-3 py-2 text-right font-mono text-xs">
                                {c.total_value - c.invoiced_total > 0
                                  ? <span className="text-amber-600">{fmtEur(c.total_value - c.invoiced_total)}</span>
                                  : <span className="text-emerald-600">0,00</span>}
                              </td>
                              <td className="px-3 py-2 text-center text-xs text-muted-foreground">
                                {c.total_value > 0 ? `${Math.round(c.invoiced_total / c.total_value * 100)}%` : '—'}
                              </td>
                              <td className="px-1 py-2" onClick={e => e.stopPropagation()}>
                                {c.anexa_count === 0 && (
                                  <Button variant="ghost" size="icon" className="h-6 w-6" title="Delete contract"
                                    onClick={async () => {
                                      if (!confirm(`Delete contract ${c.contract_ref}?`)) return
                                      try {
                                        const res = await fetch(`/facturare/api/contracts/${c.id}`, { method: 'DELETE' })
                                        if (!res.ok) { const d = await res.json(); throw new Error(d.error || 'Failed') }
                                        toast.success('Contract deleted'); loadContracts()
                                      } catch (err: any) { toast.error(err.message) }
                                    }}>
                                    <Trash2 className="h-3 w-3 text-muted-foreground hover:text-red-500" />
                                  </Button>
                                )}
                              </td>
                            </tr>
                          ))}
                        </React.Fragment>
                      )
                    })}
                  </tbody>
                </table>
              </CardContent>
            </Card>

            <CreateContractDialog open={createContractOpen} onOpenChange={setCreateContractOpen} companies={companies} onCreated={loadContracts} />
          </>
        )}
      </div>

      {/* Detail panel integrated inline in anexa table rows */}
    </div>

    {/* Vehicle table — full width below the grid */}
    {anexaDetail && selectedAnexaId && (
      <div className="mt-4">
        <VehicleTable detail={anexaDetail} defaultIntocmit={currentUserName}
          onCreated={() => {
            refreshAnexas()
            // Reload detail
            fetch(`/facturare/api/anexas/${selectedAnexaId}`)
              .then(r => r.ok ? r.json() : null).then(d => setAnexaDetail(d)).catch(() => {})
          }} />
      </div>
    )}
    </>
  )
}
