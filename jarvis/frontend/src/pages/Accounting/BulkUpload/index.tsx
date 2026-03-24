import { useState, useCallback } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Upload,
  FileText,
  Loader2,
  ArrowLeft,
  X,
  Check,
  AlertCircle,
  Copy,
  ChevronDown,
  ChevronRight,
  Trash2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { PageHeader } from '@/components/shared/PageHeader'
import { invoicesApi } from '@/api/invoices'
import { organizationApi } from '@/api/organization'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import type { SubmitInvoiceInput } from '@/types/invoices'

/* ──── Types ──── */

interface ParsedInvoice {
  id: string
  filename: string
  success: boolean
  error?: string
  duplicate: boolean
  selected: boolean
  // Parsed fields
  supplier: string
  invoice_number: string
  invoice_date: string
  invoice_value: number
  currency: string
  supplier_vat: string
  customer_vat: string
  // Allocation
  company: string
  brand: string
  department: string
  subdepartment: string
  // Extra
  line_items?: unknown[]
  invoice_type?: string
  efactura_match?: Record<string, unknown>
  value_ron?: number | null
  value_eur?: number | null
  exchange_rate?: number | null
  // Status
  saved?: boolean
  save_error?: string
}

type Step = 'upload' | 'review' | 'results'

/* ──── Main Component ──── */

export default function BulkUpload() {
  const navigate = useNavigate()
  const [step, setStep] = useState<Step>('upload')
  const [files, setFiles] = useState<File[]>([])
  const [invoices, setInvoices] = useState<ParsedInvoice[]>([])
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [isParsing, setIsParsing] = useState(false)

  const { data: companies = [] } = useQuery({
    queryKey: ['companies'],
    queryFn: organizationApi.getCompanies,
    staleTime: 10 * 60_000,
  })

  // ── File handling ──

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const dropped = Array.from(e.dataTransfer.files).filter((f) => {
      const ext = f.name.split('.').pop()?.toLowerCase()
      return ['pdf', 'jpg', 'jpeg', 'png', 'tiff', 'tif'].includes(ext || '')
    })
    setFiles((prev) => [...prev, ...dropped].slice(0, 20))
  }, [])

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles((prev) => [...prev, ...Array.from(e.target.files!)].slice(0, 20))
    }
  }

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }

  // ── Parse all files ──

  const handleParse = async () => {
    if (files.length === 0) return
    setIsParsing(true)
    try {
      const resp = await invoicesApi.bulkParse(files)
      if (!resp.success) {
        toast.error(resp.results?.[0]?.error || 'Parse failed')
        setIsParsing(false)
        return
      }
      const parsed: ParsedInvoice[] = resp.results.map((r, i) => ({
        id: `inv-${i}-${Date.now()}`,
        filename: r.filename,
        success: r.success,
        error: r.error,
        duplicate: r.duplicate ?? false,
        selected: r.success && !r.duplicate,
        supplier: r.data?.supplier as string || '',
        invoice_number: r.data?.invoice_number as string || '',
        invoice_date: r.data?.invoice_date as string || '',
        invoice_value: Number(r.data?.invoice_value) || 0,
        currency: (r.data?.currency as string) || 'RON',
        supplier_vat: (r.data?.supplier_vat as string) || '',
        customer_vat: (r.data?.customer_vat as string) || '',
        company: '',
        brand: '',
        department: '',
        subdepartment: '',
        line_items: r.data?.line_items as unknown[] | undefined,
        invoice_type: r.data?.invoice_type as string | undefined,
        efactura_match: r.data?.efactura_match as Record<string, unknown> | undefined,
        value_ron: r.data?.value_ron as number | null | undefined,
        value_eur: r.data?.value_eur as number | null | undefined,
        exchange_rate: r.data?.exchange_rate as number | null | undefined,
      }))
      setInvoices(parsed)
      setStep('review')
      const ok = parsed.filter((p) => p.success).length
      const fail = parsed.filter((p) => !p.success).length
      const dups = parsed.filter((p) => p.duplicate).length
      toast.success(`Parsed ${ok} invoice${ok !== 1 ? 's' : ''}${fail ? `, ${fail} failed` : ''}${dups ? `, ${dups} duplicate${dups !== 1 ? 's' : ''}` : ''}`)
    } catch (err) {
      toast.error('Failed to parse files')
    }
    setIsParsing(false)
  }

  // ── Update invoice field ──

  const updateInvoice = (id: string, updates: Partial<ParsedInvoice>) => {
    setInvoices((prev) => prev.map((inv) => (inv.id === id ? { ...inv, ...updates } : inv)))
  }

  // ── Submit selected invoices ──

  const submitMutation = useMutation({
    mutationFn: async () => {
      const selected = invoices.filter((inv) => inv.selected && inv.success && !inv.saved)
      if (selected.length === 0) throw new Error('No invoices selected')

      // Validate all selected have at least one level
      const invalid = selected.filter((inv) => !inv.brand && !inv.department && !inv.subdepartment)
      if (invalid.length > 0) {
        throw new Error(`${invalid.length} invoice(s) missing allocation (need at least one level)`)
      }

      const payloads = selected.map((inv) => ({
        supplier: inv.supplier,
        invoice_number: inv.invoice_number,
        invoice_date: inv.invoice_date,
        invoice_value: inv.invoice_value,
        currency: inv.currency,
        payment_status: 'not_paid',
        subtract_vat: false,
        value_ron: inv.value_ron ?? undefined,
        value_eur: inv.value_eur ?? undefined,
        exchange_rate: inv.exchange_rate ?? undefined,
        _line_items: inv.line_items,
        _invoice_type: inv.invoice_type !== 'standard' ? inv.invoice_type : undefined,
        _efactura_match_id: inv.efactura_match?.id as number | undefined,
        distributions: [{
          company: inv.company,
          brand: inv.brand || undefined,
          department: inv.department || '',
          subdepartment: inv.subdepartment || undefined,
          allocation: 1,
          locked: false,
        }],
      } satisfies SubmitInvoiceInput & Record<string, unknown>))

      return invoicesApi.bulkSubmit(payloads)
    },
    onSuccess: (data) => {
      // Mark each invoice with result
      setInvoices((prev) =>
        prev.map((inv) => {
          if (!inv.selected || !inv.success) return inv
          const result = data.results.find((r) => r.invoice_number === inv.invoice_number)
          if (result?.success) return { ...inv, saved: true }
          return { ...inv, save_error: result?.error || 'Unknown error' }
        }),
      )
      setStep('results')
      toast.success(`Saved ${data.saved_count} of ${data.total} invoices`)
    },
    onError: (err: Error) => toast.error(err.message),
  })

  // ── Helpers ──

  const selectedCount = invoices.filter((i) => i.selected && i.success).length
  const toggleAll = (checked: boolean) => {
    setInvoices((prev) => prev.map((inv) => (inv.success ? { ...inv, selected: checked } : inv)))
  }

  // ── Render ──

  return (
    <div className="space-y-4 pb-20">
      <PageHeader
        title="Bulk Upload"
        breadcrumbs={[
          { label: 'Accounting', href: '/app/accounting' },
          { label: 'Bulk Upload' },
        ]}
        actions={
          <Button variant="outline" size="sm" onClick={() => navigate('/app/accounting')}>
            <ArrowLeft className="h-4 w-4 mr-1" /> Back
          </Button>
        }
      />

      {/* ── Step 1: Upload ── */}
      {step === 'upload' && (
        <Card>
          <CardContent className="pt-6 space-y-4">
            <div
              className={cn(
                'border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer',
                'hover:border-primary/50 hover:bg-muted/30',
              )}
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
              onClick={() => document.getElementById('bulk-file-input')?.click()}
            >
              <Upload className="h-10 w-10 mx-auto text-muted-foreground mb-3" />
              <p className="text-sm font-medium">Drop PDF/image files here or click to browse</p>
              <p className="text-xs text-muted-foreground mt-1">Up to 20 files, max 50MB each</p>
              <input
                id="bulk-file-input"
                type="file"
                multiple
                accept=".pdf,.jpg,.jpeg,.png,.tiff,.tif"
                className="hidden"
                onChange={handleFileInput}
              />
            </div>

            {files.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium">{files.length} file{files.length !== 1 ? 's' : ''} selected</p>
                  <Button variant="ghost" size="sm" onClick={() => setFiles([])}>Clear All</Button>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                  {files.map((f, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs border rounded px-2 py-1.5">
                      <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      <span className="truncate flex-1">{f.name}</span>
                      <span className="text-muted-foreground">{(f.size / 1024).toFixed(0)}KB</span>
                      <button onClick={() => removeFile(i)} className="text-muted-foreground hover:text-destructive">
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
                <div className="flex justify-end">
                  <Button onClick={handleParse} disabled={isParsing}>
                    {isParsing ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                    {isParsing ? 'Parsing...' : `Parse ${files.length} File${files.length !== 1 ? 's' : ''}`}
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Step 2: Review ── */}
      {step === 'review' && (
        <>
          <Card>
            <CardContent className="pt-4 space-y-2">
              {/* Header row */}
              <div className="flex items-center gap-3 text-xs font-medium text-muted-foreground border-b pb-2">
                <Checkbox
                  checked={selectedCount === invoices.filter((i) => i.success).length && selectedCount > 0}
                  onCheckedChange={(c) => toggleAll(!!c)}
                  className="mr-1"
                />
                <div className="w-6" />
                <div className="flex-1 min-w-0">File / Supplier</div>
                <div className="w-36">Invoice #</div>
                <div className="w-24">Date</div>
                <div className="w-24 text-right">Value</div>
                <div className="w-16 text-center">Status</div>
                <div className="w-40">Company</div>
                <div className="w-8" />
              </div>

              {/* Invoice rows */}
              {invoices.map((inv) => (
                <InvoiceRow
                  key={inv.id}
                  inv={inv}
                  companies={companies}
                  expanded={expandedId === inv.id}
                  onToggleExpand={() => setExpandedId(expandedId === inv.id ? null : inv.id)}
                  onUpdate={(u) => updateInvoice(inv.id, u)}
                />
              ))}
            </CardContent>
          </Card>

          {/* Sticky bottom bar */}
          <div className="fixed bottom-0 left-0 right-0 bg-background border-t p-3 flex items-center justify-between z-40">
            <div className="flex items-center gap-4">
              <Button variant="outline" size="sm" onClick={() => { setStep('upload'); setInvoices([]) }}>
                <ArrowLeft className="h-4 w-4 mr-1" /> Back to Upload
              </Button>
              <span className="text-sm text-muted-foreground">{selectedCount} invoice{selectedCount !== 1 ? 's' : ''} selected</span>
            </div>
            <Button
              onClick={() => submitMutation.mutate()}
              disabled={selectedCount === 0 || submitMutation.isPending}
            >
              {submitMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Save {selectedCount} Invoice{selectedCount !== 1 ? 's' : ''}
            </Button>
          </div>
        </>
      )}

      {/* ── Step 3: Results ── */}
      {step === 'results' && (
        <Card>
          <CardContent className="pt-6 space-y-4">
            <div className="text-center space-y-2">
              <Check className="h-12 w-12 mx-auto text-green-600" />
              <h2 className="text-lg font-semibold">Bulk Upload Complete</h2>
              <p className="text-sm text-muted-foreground">
                {invoices.filter((i) => i.saved).length} saved,{' '}
                {invoices.filter((i) => i.save_error).length} failed,{' '}
                {invoices.filter((i) => !i.selected || !i.success).length} skipped
              </p>
            </div>

            <div className="space-y-1">
              {invoices.map((inv) => (
                <div key={inv.id} className="flex items-center gap-3 text-sm px-2 py-1.5 rounded hover:bg-muted/50">
                  {inv.saved ? (
                    <Check className="h-4 w-4 text-green-600 shrink-0" />
                  ) : inv.save_error ? (
                    <AlertCircle className="h-4 w-4 text-destructive shrink-0" />
                  ) : (
                    <div className="h-4 w-4 shrink-0" />
                  )}
                  <span className="truncate flex-1">{inv.supplier || inv.filename}</span>
                  <span className="text-muted-foreground">{inv.invoice_number}</span>
                  {inv.saved && <Badge variant="outline" className="text-green-600 border-green-200">Saved</Badge>}
                  {inv.save_error && <Badge variant="destructive">{inv.save_error}</Badge>}
                  {!inv.selected && <Badge variant="secondary">Skipped</Badge>}
                  {!inv.success && <Badge variant="destructive">Parse Error</Badge>}
                </div>
              ))}
            </div>

            <div className="flex justify-center gap-3 pt-4">
              <Button variant="outline" onClick={() => { setStep('upload'); setFiles([]); setInvoices([]) }}>
                Upload More
              </Button>
              <Button onClick={() => navigate('/app/accounting')}>
                Go to Accounting
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

/* ──── Invoice Row Sub-component ──── */

function InvoiceRow({
  inv,
  companies,
  expanded,
  onToggleExpand,
  onUpdate,
}: {
  inv: ParsedInvoice
  companies: string[]
  expanded: boolean
  onToggleExpand: () => void
  onUpdate: (u: Partial<ParsedInvoice>) => void
}) {
  const { data: brands = [] } = useQuery({
    queryKey: ['brands', inv.company],
    queryFn: () => organizationApi.getBrands(inv.company),
    enabled: !!inv.company,
    staleTime: 5 * 60_000,
  })

  const { data: departments = [] } = useQuery({
    queryKey: ['departments', inv.company, inv.brand || null],
    queryFn: () => organizationApi.getDepartments(inv.company, inv.brand || undefined),
    enabled: !!inv.company,
    staleTime: 5 * 60_000,
  })

  const { data: subdepartments = [] } = useQuery({
    queryKey: ['subdepartments', inv.company, inv.department],
    queryFn: () => organizationApi.getSubdepartments(inv.company, inv.department),
    enabled: !!inv.company && !!inv.department,
    staleTime: 5 * 60_000,
  })

  const { data: suggestions = [] } = useQuery({
    queryKey: ['dept-suggest', inv.supplier],
    queryFn: async () => {
      const resp = await invoicesApi.suggestDepartment(inv.supplier)
      return resp.suggestions || []
    },
    enabled: !!inv.supplier && !inv.company,
  })

  // Auto-apply first suggestion when company is empty
  const applySuggestion = (s: { company: string; brand: string | null; department: string; subdepartment: string | null }) => {
    onUpdate({ company: s.company, brand: s.brand || '', department: s.department || '', subdepartment: s.subdepartment || '' })
  }

  return (
    <div className={cn('border rounded-lg', !inv.success && 'opacity-50')}>
      <div className="flex items-center gap-3 px-3 py-2 text-sm">
        <Checkbox
          checked={inv.selected}
          disabled={!inv.success}
          onCheckedChange={(c) => onUpdate({ selected: !!c })}
        />
        <button onClick={onToggleExpand} className="text-muted-foreground">
          {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </button>
        <div className="flex-1 min-w-0">
          <div className="font-medium truncate">{inv.supplier || inv.filename}</div>
          <div className="text-xs text-muted-foreground truncate">{inv.filename}</div>
        </div>
        <div className="w-36 truncate">{inv.invoice_number}</div>
        <div className="w-24">{inv.invoice_date}</div>
        <div className="w-24 text-right font-mono">
          {inv.invoice_value ? inv.invoice_value.toLocaleString('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}
          <span className="text-xs text-muted-foreground ml-1">{inv.currency}</span>
        </div>
        <div className="w-16 text-center">
          {!inv.success ? (
            <Badge variant="destructive" className="text-[10px]">Error</Badge>
          ) : inv.duplicate ? (
            <Badge variant="outline" className="text-amber-600 border-amber-200 text-[10px]">Dup</Badge>
          ) : inv.saved ? (
            <Badge variant="outline" className="text-green-600 border-green-200 text-[10px]">Saved</Badge>
          ) : (
            <Badge variant="secondary" className="text-[10px]">Ready</Badge>
          )}
        </div>
        <div className="w-40">
          <Select value={inv.company || '__none__'} onValueChange={(v) => onUpdate({ company: v === '__none__' ? '' : v, brand: '', department: '', subdepartment: '' })}>
            <SelectTrigger className="h-7 text-xs">
              <SelectValue placeholder="Company..." />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">Select...</SelectItem>
              {companies.filter(Boolean).map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="w-8">
          {!inv.selected && inv.success && (
            <button className="text-muted-foreground hover:text-destructive" onClick={() => onUpdate({ selected: false })}>
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="border-t px-3 py-3 bg-muted/20 space-y-3">
          {inv.error && (
            <div className="text-xs text-destructive bg-destructive/10 rounded px-2 py-1">{inv.error}</div>
          )}

          {/* Suggestions */}
          {suggestions.length > 0 && !inv.company && (
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">Suggested based on previous allocations:</p>
              <div className="flex flex-wrap gap-1.5">
                {suggestions.slice(0, 3).map((s, i) => (
                  <Button
                    key={i}
                    variant="outline"
                    size="sm"
                    className="text-xs h-6"
                    onClick={() => applySuggestion(s)}
                  >
                    {s.company} {s.brand ? `→ ${s.brand}` : ''} {s.department ? `→ ${s.department}` : ''}
                  </Button>
                ))}
              </div>
            </div>
          )}

          {/* Editable fields */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Supplier</label>
              <Input className="h-7 text-xs" value={inv.supplier} onChange={(e) => onUpdate({ supplier: e.target.value })} />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Invoice #</label>
              <Input className="h-7 text-xs" value={inv.invoice_number} onChange={(e) => onUpdate({ invoice_number: e.target.value })} />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Date</label>
              <Input className="h-7 text-xs" value={inv.invoice_date} onChange={(e) => onUpdate({ invoice_date: e.target.value })} />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Value</label>
              <div className="flex gap-1">
                <Input className="h-7 text-xs flex-1" type="number" step="0.01" value={inv.invoice_value} onChange={(e) => onUpdate({ invoice_value: parseFloat(e.target.value) || 0 })} />
                <Select value={inv.currency} onValueChange={(v) => onUpdate({ currency: v })}>
                  <SelectTrigger className="h-7 text-xs w-20">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="RON">RON</SelectItem>
                    <SelectItem value="EUR">EUR</SelectItem>
                    <SelectItem value="USD">USD</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>

          {/* Allocation: Department / Subdivision / Detail */}
          {inv.company && (
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">Allocation</p>
              <div className="grid grid-cols-3 gap-2">
                {brands.length > 0 && (
                  <div className="space-y-0.5">
                    <label className="text-[10px] text-muted-foreground">Department</label>
                    <Select value={inv.brand || '__none__'} onValueChange={(v) => onUpdate({ brand: v === '__none__' ? '' : v, department: '', subdepartment: '' })}>
                      <SelectTrigger className="h-7 text-xs">
                        <SelectValue placeholder="Select..." />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">Select...</SelectItem>
                        {brands.filter(Boolean).map((b) => <SelectItem key={b} value={b}>{b}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                )}
                {departments.length > 0 && (
                  <div className="space-y-0.5">
                    <label className="text-[10px] text-muted-foreground">Subdivision</label>
                    <Select value={inv.department || '__none__'} onValueChange={(v) => onUpdate({ department: v === '__none__' ? '' : v, subdepartment: '' })}>
                      <SelectTrigger className="h-7 text-xs">
                        <SelectValue placeholder="Select..." />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">Select...</SelectItem>
                        {departments.filter(Boolean).map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                )}
                {subdepartments.length > 0 && (
                  <div className="space-y-0.5">
                    <label className="text-[10px] text-muted-foreground">Detail</label>
                    <Select value={inv.subdepartment || '__none__'} onValueChange={(v) => onUpdate({ subdepartment: v === '__none__' ? '' : v })}>
                      <SelectTrigger className="h-7 text-xs">
                        <SelectValue placeholder="Select..." />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">Select...</SelectItem>
                        {subdepartments.filter(Boolean).map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </div>
            </div>
          )}

          {inv.duplicate && (
            <div className="flex items-center gap-2 text-xs text-amber-600 bg-amber-50 dark:bg-amber-950/20 rounded px-2 py-1.5">
              <Copy className="h-3.5 w-3.5" />
              Invoice number already exists in the database. Uncheck to skip, or edit the number.
            </div>
          )}
        </div>
      )}
    </div>
  )
}
