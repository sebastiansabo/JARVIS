import { useState, useCallback, useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'
import { FileSpreadsheet, Download, CheckCircle2, AlertCircle, Upload, FileText, Loader2, Building2, Search } from 'lucide-react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/shared/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

// ── Shared types ──────────────────────────────────────────────

interface Company {
  id: number
  company: string
  vat: string | null
}

interface CrmClient {
  id: number
  display_name: string
  street?: string
  city?: string
  country?: string
  nr_reg?: string
}

// ── Supplier presets ──────────────────────────────────────────

const SUPPLIER_PRESETS: Record<string, { address_lines: string[]; reg_no: string; vat: string; iban: string; bank: string; swift: string }> = {
  'AUTOWORLD INTERNATIONAL SRL': {
    address_lines: ['Calea Floresti nr. 145', 'Cluj-Napoca, jud. Cluj', 'Romania'],
    reg_no: 'J2024002657125', vat: 'RO 50186890',
    iban: 'RO88BACX0000002700968001', bank: 'Unicredit Tiriac Bank Cluj-Napoca', swift: 'BACXROBU',
  },
  'AUTOWORLD PREMIUM SRL': {
    address_lines: ['Calea Floresti nr. 145', 'Cluj-Napoca, jud. Cluj', 'Romania'],
    reg_no: 'J2024002670120', vat: 'RO 50188939',
    iban: 'RO94BACX0000002700266001', bank: 'Unicredit Tiriac Bank Cluj-Napoca', swift: 'BACXROBU',
  },
}

// ── Helpers ───────────────────────────────────────────────────

function fmtNum(n: number): string {
  return new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n)
}

async function apiCall(url: string, formData: FormData) {
  const res = await fetch(url, { method: 'POST', body: formData })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }))
    throw new Error(err.error || 'Request failed')
  }
  return res.json()
}

function handleDownload(url: string, filename: string) {
  fetch(url)
    .then(r => r.blob())
    .then(blob => {
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = filename
      a.click()
      URL.revokeObjectURL(a.href)
    })
    .catch(() => toast.error('Download failed'))
}

// ── Supplier Card (shared) ───────────────────────────────────

function SupplierCard({ companies, supplierName, setSupplierName, supplierVat, setSupplierVat,
  supplierRegNo, setSupplierRegNo, supplierIban, setSupplierIban, supplierBank, setSupplierBank,
  supplierSwift, setSupplierSwift, supplierAddress, setSupplierAddress,
}: {
  companies: Company[]
  supplierName: string; setSupplierName: (v: string) => void
  supplierVat: string; setSupplierVat: (v: string) => void
  supplierRegNo: string; setSupplierRegNo: (v: string) => void
  supplierIban: string; setSupplierIban: (v: string) => void
  supplierBank: string; setSupplierBank: (v: string) => void
  supplierSwift: string; setSupplierSwift: (v: string) => void
  supplierAddress: string; setSupplierAddress: (v: string) => void
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <Building2 className="h-4 w-4" /> Furnizor
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <Label>Company *</Label>
          <Select
            value={supplierName}
            onValueChange={v => {
              setSupplierName(v)
              const company = companies.find(c => c.company === v)
              setSupplierVat(company?.vat || SUPPLIER_PRESETS[v]?.vat || '')
              const preset = SUPPLIER_PRESETS[v]
              setSupplierAddress(preset?.address_lines.join('\n') || '')
              setSupplierRegNo(preset?.reg_no || '')
              setSupplierIban(preset?.iban || '')
              setSupplierBank(preset?.bank || '')
              setSupplierSwift(preset?.swift || '')
            }}
          >
            <SelectTrigger><SelectValue placeholder="Select company" /></SelectTrigger>
            <SelectContent>
              {companies.map(c => (
                <SelectItem key={c.id} value={c.company}>{c.company}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
          <div><Label>VAT</Label><Input value={supplierVat} onChange={e => setSupplierVat(e.target.value)} /></div>
          <div><Label>Reg No (J-nr)</Label><Input value={supplierRegNo} onChange={e => setSupplierRegNo(e.target.value)} /></div>
          <div><Label>IBAN</Label><Input value={supplierIban} onChange={e => setSupplierIban(e.target.value)} /></div>
          <div><Label>Bank</Label><Input value={supplierBank} onChange={e => setSupplierBank(e.target.value)} /></div>
          <div><Label>SWIFT</Label><Input value={supplierSwift} onChange={e => setSupplierSwift(e.target.value)} /></div>
        </div>
        <div>
          <Label>Address</Label>
          <textarea className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm" rows={2}
            value={supplierAddress} onChange={e => setSupplierAddress(e.target.value)} />
        </div>
      </CardContent>
    </Card>
  )
}

// ── Customer Card (shared, with CRM search) ──────────────────

function CustomerCard({ customerName, setCustomerName, customerAddress, setCustomerAddress,
  customerVat, setCustomerVat,
}: {
  customerName: string; setCustomerName: (v: string) => void
  customerAddress: string; setCustomerAddress: (v: string) => void
  customerVat: string; setCustomerVat: (v: string) => void
}) {
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<CrmClient[]>([])
  const [searching, setSearching] = useState(false)

  const searchCrm = () => {
    if (!searchQuery.trim()) return
    setSearching(true)
    fetch(`/api/crm/clients?name=${encodeURIComponent(searchQuery)}&limit=5`)
      .then(r => r.ok ? r.json() : { clients: [] })
      .then(data => setSearchResults(data.clients || []))
      .catch(() => setSearchResults([]))
      .finally(() => setSearching(false))
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Customer</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2">
          <div className="flex-1">
            <Label>Search CRM</Label>
            <div className="flex gap-2">
              <Input placeholder="Search by name..." value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && searchCrm()} />
              <Button variant="outline" size="icon" onClick={searchCrm} disabled={searching}>
                {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              </Button>
            </div>
          </div>
        </div>
        {searchResults.length > 0 && (
          <div className="border rounded-md divide-y text-sm max-h-40 overflow-y-auto">
            {searchResults.map(client => (
              <button key={client.id} className="w-full text-left px-3 py-2 hover:bg-muted transition-colors"
                onClick={() => {
                  setCustomerName(client.display_name)
                  const addrParts = [client.street, client.city, client.country].filter(Boolean)
                  setCustomerAddress(addrParts.join('\n'))
                  setCustomerVat(client.nr_reg || '')
                  setSearchResults([])
                  setSearchQuery('')
                  toast.success(`Loaded: ${client.display_name}`)
                }}>
                <span className="font-medium">{client.display_name}</span>
                {client.nr_reg && <span className="text-muted-foreground ml-2">{client.nr_reg}</span>}
                {client.city && <span className="text-muted-foreground ml-2">— {client.city}</span>}
              </button>
            ))}
          </div>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <Label>Name *</Label>
            <Input placeholder="GENERAL LEASE NV" value={customerName} onChange={e => setCustomerName(e.target.value)} />
          </div>
          <div>
            <Label>Address (one line per row)</Label>
            <textarea className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm" rows={3}
              placeholder={"Overhaamlaan 71\n3700 Tongeren\nBELGIA"}
              value={customerAddress} onChange={e => setCustomerAddress(e.target.value)} />
          </div>
          <div>
            <Label>VAT</Label>
            <Input placeholder="BE0431586751" value={customerVat} onChange={e => setCustomerVat(e.target.value)} />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Results Panel (shared) ───────────────────────────────────

function ResultsPanel({ report, generateResult, jobId, label, showKurs, showXlsx,
  validateError, generateError,
}: {
  report: any; generateResult: any; jobId: string; label: string
  showKurs: boolean; showXlsx: boolean
  validateError: Error | null; generateError: Error | null
}) {
  return (
    <div className="space-y-4">
      {report && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-500" /> Validation Report
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-2 text-sm">
              <span className="text-muted-foreground">{label}:</span>
              <span className="font-medium">{report.row_count}</span>
              <span className="text-muted-foreground">Range:</span>
              <span className="font-medium">{report.invoice_range || report.proforma_range}</span>
              <span className="text-muted-foreground">Total:</span>
              <span className="font-medium">{fmtNum(report.total_advance ?? report.total_amount)} {report.currency}</span>
              {showKurs && report.kurs && (<>
                <span className="text-muted-foreground">Kurs:</span>
                <span className="font-medium">{report.kurs}</span>
              </>)}
            </div>
            <Separator />
            <div className="text-sm">
              <p className="text-muted-foreground mb-1">By model:</p>
              {Object.entries(report.models).map(([model, data]: [string, any]) => (
                <div key={model} className="flex justify-between py-0.5">
                  <span>{model} <Badge variant="secondary" className="text-xs ml-1">{data.count}</Badge></span>
                  <span className="font-mono">{fmtNum(data.total)}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {generateResult?.success && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Download className="h-4 w-4 text-blue-500" /> Downloads
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-2 text-sm">
              <span className="text-muted-foreground">{label}:</span>
              <span className="font-medium">{generateResult.lines_count}</span>
              <span className="text-muted-foreground">Range:</span>
              <span className="font-medium">{generateResult.invoice_range || generateResult.proforma_range}</span>
              <span className="text-muted-foreground">Total:</span>
              <span className="font-medium">{fmtNum(generateResult.total_advance ?? generateResult.total_amount)} EUR</span>
            </div>
            <Separator />
            <div className="flex flex-col gap-2">
              {generateResult.pdf_url && (
                <Button variant="outline" className="w-full justify-start"
                  onClick={() => handleDownload(generateResult.pdf_url!, `${jobId || 'facturare'}_${label.toLowerCase()}.pdf`)}>
                  <FileText className="h-4 w-4 mr-2 text-red-500" />
                  Download {label} PDF
                </Button>
              )}
              {showXlsx && generateResult.xlsx_url && (
                <Button variant="outline" className="w-full justify-start"
                  onClick={() => handleDownload(generateResult.xlsx_url!, `${jobId || 'facturare'}_eurofib.xlsx`)}>
                  <FileSpreadsheet className="h-4 w-4 mr-2 text-emerald-500" />
                  Download EuroFib XLSX
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {(validateError || generateError) && (
        <Card className="border-red-200 dark:border-red-800">
          <CardContent className="pt-4">
            <div className="flex items-start gap-2 text-sm text-red-600 dark:text-red-400">
              <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
              <span>{(validateError || generateError)?.message}</span>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ── Invoice Tab ──────────────────────────────────────────────

const INV_DEFAULTS = {
  supplier: 'AUTOWORLD INTERNATIONAL SRL',
  intocmit: 'Ilona Foszto',
}

function InvoiceTab({ companies }: { companies: Company[] }) {
  const [anexaFile, setAnexaFile] = useState<File | null>(null)
  const [report, setReport] = useState<any>(null)
  const [generateResult, setGenerateResult] = useState<any>(null)

  const [jobId, setJobId] = useState('')
  const [contractRef, setContractRef] = useState('')
  const [anexaRef, setAnexaRef] = useState('')
  const [startNo, setStartNo] = useState('')
  const [invoiceDate, setInvoiceDate] = useState('')
  const [intocmitDe, setIntocmitDe] = useState(INV_DEFAULTS.intocmit)
  const [kurs, setKurs] = useState('')
  const [kursDate, setKursDate] = useState('')
  const [customerName, setCustomerName] = useState('')
  const [customerAddress, setCustomerAddress] = useState('')
  const [customerVat, setCustomerVat] = useState('')
  const [kontoDebit, setKontoDebit] = useState('41214286')
  const [kontoCredit, setKontoCredit] = useState('419968')

  const preset = SUPPLIER_PRESETS[INV_DEFAULTS.supplier]
  const [supplierName, setSupplierName] = useState(INV_DEFAULTS.supplier)
  const [supplierAddress, setSupplierAddress] = useState(preset?.address_lines.join('\n') || '')
  const [supplierVat, setSupplierVat] = useState(preset?.vat || '')
  const [supplierRegNo, setSupplierRegNo] = useState(preset?.reg_no || '')
  const [supplierIban, setSupplierIban] = useState(preset?.iban || '')
  const [supplierBank, setSupplierBank] = useState(preset?.bank || '')
  const [supplierSwift, setSupplierSwift] = useState(preset?.swift || '')

  const buildConfig = useCallback(() => ({
    job_id: jobId || `inv-${Date.now()}`,
    contract: { ref: contractRef, anexa_ref: anexaRef },
    input: { anexa: '', sheet: 'Sheet1' },
    invoice: { kind: 'invoice', start_no: parseInt(startNo) || 0, date: invoiceDate, intocmit_de: intocmitDe, description_prefix: '1. ADVANCE PAYMENT' },
    fx: { currency: 'EUR', kurs: parseFloat(kurs) || 0, kurs_date: kursDate || invoiceDate },
    supplier: { name: supplierName, address_lines: supplierAddress.split('\n').filter(Boolean), reg_no: supplierRegNo, vat: supplierVat, iban: supplierIban, bank: supplierBank, swift: supplierSwift },
    customer: { name: customerName, address_lines: customerAddress.split('\n').filter(Boolean), vat: customerVat },
    eurofib: { klient: 139, konto_debit: parseInt(kontoDebit) || 41214286, konto_credit: parseInt(kontoCredit) || 419968, belegart: 'JVV', steuercode: 'L00', fw_steuercode: 'L00', text_template: 'avans {brand_short} {comanda}', brand_map: {} },
    output: {},
  }), [jobId, contractRef, anexaRef, startNo, invoiceDate, intocmitDe, kurs, kursDate, supplierName, supplierAddress, supplierVat, supplierRegNo, supplierIban, supplierBank, supplierSwift, customerName, customerAddress, customerVat, kontoDebit, kontoCredit])

  const buildFormData = useCallback(() => {
    if (!anexaFile) throw new Error('No Anexa file selected')
    const fd = new FormData()
    fd.append('anexa', anexaFile)
    fd.append('config', JSON.stringify(buildConfig()))
    return fd
  }, [anexaFile, buildConfig])

  const validateMut = useMutation({
    mutationFn: () => apiCall('/facturare/api/validate', buildFormData()),
    onSuccess: (data) => { setReport(data.report); setGenerateResult(null); toast.success(`Validated: ${data.report.row_count} invoices`) },
    onError: (err: Error) => toast.error(err.message),
  })
  const generateMut = useMutation({
    mutationFn: () => apiCall('/facturare/api/generate', buildFormData()),
    onSuccess: (data) => { setGenerateResult(data); toast.success(`Generated ${data.lines_count} invoices`) },
    onError: (err: Error) => toast.error(err.message),
  })

  const validate = () => {
    const missing: string[] = []
    if (!anexaFile) missing.push('Anexa file')
    if (!startNo) missing.push('Start No')
    if (!invoiceDate) missing.push('Invoice Date')
    if (!kurs) missing.push('Kurs')
    if (!customerName) missing.push('Customer Name')
    if (missing.length > 0) { toast.error(`Missing: ${missing.join(', ')}`); return }
    validateMut.mutate()
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 space-y-4">
        {/* Anexa upload */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2"><Upload className="h-4 w-4" /> Anexa File</CardTitle>
          </CardHeader>
          <CardContent>
            <Input type="file" accept=".xlsx,.xls" onChange={e => {
              const file = e.target.files?.[0] || null
              setAnexaFile(file); setReport(null); setGenerateResult(null)
              if (file) {
                const fd = new FormData(); fd.append('anexa', file)
                fetch('/facturare/api/parse-anexa', { method: 'POST', body: fd })
                  .then(r => r.ok ? r.json() : null)
                  .then(data => {
                    if (!data?.metadata) return
                    const m = data.metadata
                    if (m.customer_name) setCustomerName(m.customer_name)
                    if (m.customer_address) setCustomerAddress(m.customer_address)
                    if (m.customer_vat) setCustomerVat(m.customer_vat)
                    if (m.invoice_date) setInvoiceDate(m.invoice_date)
                    if (m.kurs) setKurs(m.kurs)
                    if (m.start_no) setStartNo(m.start_no)
                    if (m.contract_ref) setContractRef(m.contract_ref)
                    if (m.anexa_ref) setAnexaRef(m.anexa_ref)
                    if (m.intocmit_de) setIntocmitDe(m.intocmit_de)
                    if (m.job_id) setJobId(m.job_id)
                    toast.success('Form auto-filled from Anexa metadata')
                  }).catch(() => {})
              }
            }} />
            {anexaFile && <p className="text-sm text-muted-foreground mt-1">{anexaFile.name} ({(anexaFile.size / 1024).toFixed(0)} KB)</p>}
            <a href="/facturare/api/template/invoice" download className="text-sm text-blue-600 hover:underline inline-flex items-center gap-1 mt-2">
              <Download className="h-3 w-3" /> Download template
            </a>
          </CardContent>
        </Card>

        {/* Invoice settings */}
        <Card>
          <CardHeader className="pb-3"><CardTitle className="text-base">Invoice Settings</CardTitle></CardHeader>
          <CardContent className="grid grid-cols-2 sm:grid-cols-3 gap-4">
            <div><Label>Job ID</Label><Input placeholder="ctr677-2026-04" value={jobId} onChange={e => setJobId(e.target.value)} /></div>
            <div><Label>Start No *</Label><Input type="number" placeholder="9102842" value={startNo} onChange={e => setStartNo(e.target.value)} /></div>
            <div><Label>Invoice Date *</Label><Input type="date" value={invoiceDate} onChange={e => setInvoiceDate(e.target.value)} /></div>
            <div><Label>Kurs (EUR/RON) *</Label><Input type="number" step="0.0001" placeholder="5.0924" value={kurs} onChange={e => setKurs(e.target.value)} /></div>
            <div><Label>Kurs Date</Label><Input type="date" value={kursDate} onChange={e => setKursDate(e.target.value)} /></div>
            <div><Label>Contract Ref</Label><Input placeholder="ctr 677/03.04.2026" value={contractRef} onChange={e => setContractRef(e.target.value)} /></div>
            <div><Label>Anexa Ref</Label><Input placeholder="Anexa 1 la CTR.677 din 03.04.2026" value={anexaRef} onChange={e => setAnexaRef(e.target.value)} /></div>
            <div><Label>Intocmit de</Label><Input value={intocmitDe} onChange={e => setIntocmitDe(e.target.value)} /></div>
          </CardContent>
        </Card>

        <SupplierCard companies={companies} supplierName={supplierName} setSupplierName={setSupplierName}
          supplierVat={supplierVat} setSupplierVat={setSupplierVat}
          supplierRegNo={supplierRegNo} setSupplierRegNo={setSupplierRegNo}
          supplierIban={supplierIban} setSupplierIban={setSupplierIban}
          supplierBank={supplierBank} setSupplierBank={setSupplierBank}
          supplierSwift={supplierSwift} setSupplierSwift={setSupplierSwift}
          supplierAddress={supplierAddress} setSupplierAddress={setSupplierAddress} />

        <CustomerCard customerName={customerName} setCustomerName={setCustomerName}
          customerAddress={customerAddress} setCustomerAddress={setCustomerAddress}
          customerVat={customerVat} setCustomerVat={setCustomerVat} />

        {/* EuroFib accounts */}
        <Card>
          <CardHeader className="pb-3"><CardTitle className="text-base">EuroFib Accounts</CardTitle></CardHeader>
          <CardContent className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div><Label>Konto Debit</Label><Input type="number" value={kontoDebit} onChange={e => setKontoDebit(e.target.value)} /></div>
            <div><Label>Konto Credit</Label><Input type="number" value={kontoCredit} onChange={e => setKontoCredit(e.target.value)} /></div>
          </CardContent>
        </Card>

        {/* Actions */}
        <div className="flex gap-3">
          <Button onClick={validate} disabled={validateMut.isPending} variant="outline">
            {validateMut.isPending ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <CheckCircle2 className="h-4 w-4 mr-2" />}
            Validate
          </Button>
          <Button disabled={generateMut.isPending}
            onClick={() => {
              const missing: string[] = []
              if (!anexaFile) missing.push('Anexa file')
              if (!startNo) missing.push('Start No')
              if (!invoiceDate) missing.push('Invoice Date')
              if (!kurs) missing.push('Kurs')
              if (!customerName) missing.push('Customer Name')
              if (missing.length > 0) { toast.error(`Missing: ${missing.join(', ')}`); return }
              generateMut.mutate()
            }}>
            {generateMut.isPending ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <FileText className="h-4 w-4 mr-2" />}
            Generate
          </Button>
        </div>
      </div>

      <ResultsPanel report={report} generateResult={generateResult} jobId={jobId}
        label="Invoices" showKurs showXlsx
        validateError={validateMut.error} generateError={generateMut.error} />
    </div>
  )
}

// ── Proforma Tab ─────────────────────────────────────────────

const PRO_DEFAULTS = {
  supplier: 'AUTOWORLD PREMIUM SRL',
  intocmit: 'Gabriela Oltean',
}

function ProformaTab({ companies }: { companies: Company[] }) {
  const [anexaFile, setAnexaFile] = useState<File | null>(null)
  const [report, setReport] = useState<any>(null)
  const [generateResult, setGenerateResult] = useState<any>(null)

  const [jobId, setJobId] = useState('')
  const [startNo, setStartNo] = useState('')
  const [invoiceDate, setInvoiceDate] = useState('')
  const [intocmitDe, setIntocmitDe] = useState(PRO_DEFAULTS.intocmit)
  const [customerName, setCustomerName] = useState('')
  const [customerAddress, setCustomerAddress] = useState('')
  const [customerVat, setCustomerVat] = useState('')

  const preset = SUPPLIER_PRESETS[PRO_DEFAULTS.supplier]
  const [supplierName, setSupplierName] = useState(PRO_DEFAULTS.supplier)
  const [supplierAddress, setSupplierAddress] = useState(preset?.address_lines.join('\n') || '')
  const [supplierVat, setSupplierVat] = useState(preset?.vat || '')
  const [supplierRegNo, setSupplierRegNo] = useState(preset?.reg_no || '')
  const [supplierIban, setSupplierIban] = useState(preset?.iban || '')
  const [supplierBank, setSupplierBank] = useState(preset?.bank || '')
  const [supplierSwift, setSupplierSwift] = useState(preset?.swift || '')

  const buildConfig = useCallback(() => ({
    job_id: jobId || `pro-${Date.now()}`,
    start_no: parseInt(startNo) || 0,
    invoice_date: invoiceDate,
    intocmit_de: intocmitDe,
    sheet: 'Sheet1',
    supplier: { name: supplierName, address_lines: supplierAddress.split('\n').filter(Boolean), reg_no: supplierRegNo, vat: supplierVat, iban: supplierIban, bank: supplierBank, swift: supplierSwift },
    customer: { name: customerName, address_lines: customerAddress.split('\n').filter(Boolean), vat: customerVat },
  }), [jobId, startNo, invoiceDate, intocmitDe, supplierName, supplierAddress, supplierVat, supplierRegNo, supplierIban, supplierBank, supplierSwift, customerName, customerAddress, customerVat])

  const buildFormData = useCallback(() => {
    if (!anexaFile) throw new Error('No Anexa file selected')
    const fd = new FormData()
    fd.append('anexa', anexaFile)
    fd.append('config', JSON.stringify(buildConfig()))
    return fd
  }, [anexaFile, buildConfig])

  const validateMut = useMutation({
    mutationFn: () => apiCall('/facturare/api/proforma/validate', buildFormData()),
    onSuccess: (data) => { setReport(data.report); setGenerateResult(null); toast.success(`Validated: ${data.report.row_count} proformas`) },
    onError: (err: Error) => toast.error(err.message),
  })
  const generateMut = useMutation({
    mutationFn: () => apiCall('/facturare/api/proforma/generate', buildFormData()),
    onSuccess: (data) => { setGenerateResult(data); toast.success(`Generated ${data.lines_count} proformas`) },
    onError: (err: Error) => toast.error(err.message),
  })

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 space-y-4">
        {/* Anexa upload */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2"><Upload className="h-4 w-4" /> Proforma Anexa File</CardTitle>
          </CardHeader>
          <CardContent>
            <Input type="file" accept=".xlsx,.xls" onChange={e => {
              const file = e.target.files?.[0] || null
              setAnexaFile(file); setReport(null); setGenerateResult(null)
              if (file) {
                const fd = new FormData(); fd.append('anexa', file)
                fetch('/facturare/api/parse-anexa', { method: 'POST', body: fd })
                  .then(r => r.ok ? r.json() : null)
                  .then(data => {
                    if (!data?.metadata) return
                    const m = data.metadata
                    if (m.customer_name) setCustomerName(m.customer_name)
                    if (m.customer_address) setCustomerAddress(m.customer_address)
                    if (m.customer_vat) setCustomerVat(m.customer_vat)
                    if (m.invoice_date) setInvoiceDate(m.invoice_date)
                    if (m.start_no) setStartNo(m.start_no)
                    if (m.intocmit_de) setIntocmitDe(m.intocmit_de)
                    if (m.job_id) setJobId(m.job_id)
                    toast.success('Form auto-filled from Anexa metadata')
                  }).catch(() => {})
              }
            }} />
            {anexaFile && <p className="text-sm text-muted-foreground mt-1">{anexaFile.name} ({(anexaFile.size / 1024).toFixed(0)} KB)</p>}
            <a href="/facturare/api/template/proforma" download className="text-sm text-blue-600 hover:underline inline-flex items-center gap-1 mt-2">
              <Download className="h-3 w-3" /> Download template
            </a>
          </CardContent>
        </Card>

        {/* Proforma settings — simpler */}
        <Card>
          <CardHeader className="pb-3"><CardTitle className="text-base">Proforma Settings</CardTitle></CardHeader>
          <CardContent className="grid grid-cols-2 sm:grid-cols-3 gap-4">
            <div><Label>Job ID</Label><Input placeholder="pro-2026-04" value={jobId} onChange={e => setJobId(e.target.value)} /></div>
            <div><Label>Start No</Label><Input type="number" placeholder="550" value={startNo} onChange={e => setStartNo(e.target.value)} /></div>
            <div><Label>Date</Label><Input type="date" value={invoiceDate} onChange={e => setInvoiceDate(e.target.value)} /></div>
            <div><Label>Intocmit de</Label><Input value={intocmitDe} onChange={e => setIntocmitDe(e.target.value)} /></div>
          </CardContent>
        </Card>

        <SupplierCard companies={companies} supplierName={supplierName} setSupplierName={setSupplierName}
          supplierVat={supplierVat} setSupplierVat={setSupplierVat}
          supplierRegNo={supplierRegNo} setSupplierRegNo={setSupplierRegNo}
          supplierIban={supplierIban} setSupplierIban={setSupplierIban}
          supplierBank={supplierBank} setSupplierBank={setSupplierBank}
          supplierSwift={supplierSwift} setSupplierSwift={setSupplierSwift}
          supplierAddress={supplierAddress} setSupplierAddress={setSupplierAddress} />

        <CustomerCard customerName={customerName} setCustomerName={setCustomerName}
          customerAddress={customerAddress} setCustomerAddress={setCustomerAddress}
          customerVat={customerVat} setCustomerVat={setCustomerVat} />

        {/* Actions */}
        <div className="flex gap-3">
          <Button variant="outline" disabled={validateMut.isPending}
            onClick={() => {
              if (!anexaFile) { toast.error('Missing: Anexa file'); return }
              validateMut.mutate()
            }}>
            {validateMut.isPending ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <CheckCircle2 className="h-4 w-4 mr-2" />}
            Validate
          </Button>
          <Button disabled={generateMut.isPending}
            onClick={() => {
              if (!anexaFile) { toast.error('Missing: Anexa file'); return }
              generateMut.mutate()
            }}>
            {generateMut.isPending ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <FileText className="h-4 w-4 mr-2" />}
            Generate
          </Button>
        </div>
      </div>

      <ResultsPanel report={report} generateResult={generateResult} jobId={jobId}
        label="Proformas" showKurs={false} showXlsx={false}
        validateError={validateMut.error} generateError={generateMut.error} />
    </div>
  )
}

// ── Main Page ────────────────────────────────────────────────

export default function Facturare() {
  const [companies, setCompanies] = useState<Company[]>([])

  useEffect(() => {
    fetch('/api/companies-vat')
      .then(r => r.ok ? r.json() : [])
      .then(data => setCompanies(Array.isArray(data) ? data : []))
      .catch(() => {})
  }, [])

  return (
    <div className="space-y-6">
      <PageHeader
        title="Facturare"
        description="Generate invoice PDFs and EuroFib import files from Anexa data"
      />

      <Tabs defaultValue="invoice" className="w-full">
        <TabsList>
          <TabsTrigger value="invoice">Factura</TabsTrigger>
          <TabsTrigger value="proforma">Proforma</TabsTrigger>
        </TabsList>
        <TabsContent value="invoice" className="mt-4">
          <InvoiceTab companies={companies} />
        </TabsContent>
        <TabsContent value="proforma" className="mt-4">
          <ProformaTab companies={companies} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
