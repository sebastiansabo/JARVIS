import { useState, useMemo, useCallback, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Upload,
  FileText,
  Wand2,
  Plus,
  Loader2,
  ArrowLeft,
  X,
  ChevronDown,
  ChevronRight,
  Link2,
  Lightbulb,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { PageHeader } from '@/components/shared/PageHeader'
import { invoicesApi } from '@/api/invoices'
import { organizationApi } from '@/api/organization'
import { settingsApi } from '@/api/settings'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { useFormValidation } from '@/hooks/useFormValidation'
import { FieldError } from '@/components/shared/FieldError'
import type { ParseResult, SubmitInvoiceInput, DeptSuggestion } from '@/types/invoices'
import { type AllocationRow, newRow, AllocationRowComponent } from '../AllocationEditor'

/* ──── Main Component ──── */

export default function AddInvoice() {
  const navigate = useNavigate()

  // Invoice fields
  const [supplier, setSupplier] = useState('')
  const [invoiceNumber, setInvoiceNumber] = useState('')
  const [invoiceDate, setInvoiceDate] = useState('')
  const [invoiceValue, setInvoiceValue] = useState('')
  const [currency, setCurrency] = useState('RON')
  const [comment, setComment] = useState('')
  const [paymentStatus, setPaymentStatus] = useState('not_paid')
  const [subtractVat, setSubtractVat] = useState(false)
  const [vatRateId, setVatRateId] = useState<string>('')
  const [driveLink, setDriveLink] = useState('')
  const [templateName, setTemplateName] = useState('')

  // Upload modal
  const [uploadOpen, setUploadOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [isDragOver, setIsDragOver] = useState(false)
  const [parseTemplateId, setParseTemplateId] = useState<string>('auto')
  const [isParsing, setIsParsing] = useState(false)

  // Allocations
  const [company, setCompany] = useState('')
  const [rows, setRows] = useState<AllocationRow[]>([newRow()])

  // Currency conversion from parse
  const [valueRon, setValueRon] = useState<number | null>(null)
  const [valueEur, setValueEur] = useState<number | null>(null)
  const [exchangeRate, setExchangeRate] = useState<number | null>(null)

  // AI6: Document Intelligence
  const [lineItems, setLineItems] = useState<{ description: string; quantity: number; unit_price: number; amount: number; vat_rate?: number | null }[]>([])
  const [invoiceType, setInvoiceType] = useState<string>('standard')
  const [efacturaMatch, setEfacturaMatch] = useState<ParseResult['data'] extends undefined ? never : NonNullable<ParseResult['data']>['efactura_match']>(null)
  const [lineItemsOpen, setLineItemsOpen] = useState(false)
  const [deptSuggestions, setDeptSuggestions] = useState<DeptSuggestion[]>([])
  const [parseResult, setParseResult] = useState<Record<string, unknown> | null>(null)

  // Queries
  const { data: companies = [] } = useQuery({
    queryKey: ['companies'],
    queryFn: () => organizationApi.getCompanies(),
  })

  const { data: templates = [] } = useQuery({
    queryKey: ['templates'],
    queryFn: () => invoicesApi.getTemplates(),
  })

  const { data: vatRates = [] } = useQuery({
    queryKey: ['vat-rates'],
    queryFn: () => settingsApi.getVatRates(true),
  })

  const { data: brands = [] } = useQuery({
    queryKey: ['brands', company],
    queryFn: () => organizationApi.getBrands(company),
    enabled: !!company,
  })

  const { data: departments = [] } = useQuery({
    queryKey: ['departments', company],
    queryFn: () => organizationApi.getDepartments(company),
    enabled: !!company,
  })

  const { data: companiesVat = [] } = useQuery({
    queryKey: ['companies-vat'],
    queryFn: () => organizationApi.getCompaniesVat(),
  })

  const { data: paymentOptions = [] } = useQuery({
    queryKey: ['settings', 'dropdowns', 'payment_status'],
    queryFn: () => settingsApi.getDropdownOptions('payment_status'),
  })

  // Fetch department suggestions when supplier changes
  useEffect(() => {
    if (!supplier.trim()) { setDeptSuggestions([]); return }
    const timeout = setTimeout(async () => {
      try {
        const res = await invoicesApi.suggestDepartment(supplier.trim())
        setDeptSuggestions(res.suggestions ?? [])
      } catch { setDeptSuggestions([]) }
    }, 500)
    return () => clearTimeout(timeout)
  }, [supplier])

  // Computed
  const selectedVatRate = useMemo(
    () => vatRates.find((r) => String(r.id) === vatRateId),
    [vatRates, vatRateId],
  )

  const effectiveValue = useMemo(() => {
    const gross = parseFloat(invoiceValue) || 0
    if (subtractVat && selectedVatRate) {
      return gross / (1 + selectedVatRate.rate / 100)
    }
    return gross
  }, [invoiceValue, subtractVat, selectedVatRate])

  const netValue = useMemo(() => {
    if (!subtractVat || !selectedVatRate) return null
    const gross = parseFloat(invoiceValue) || 0
    return gross / (1 + selectedVatRate.rate / 100)
  }, [invoiceValue, subtractVat, selectedVatRate])

  const totalPercent = useMemo(
    () => rows.reduce((sum, r) => sum + r.percent, 0),
    [rows],
  )

  // Inline validation
  const v = useFormValidation(
    { supplier, invoiceNumber, invoiceDate, invoiceValue, company },
    {
      supplier: (val) => (!val.trim() ? 'Supplier is required' : undefined),
      invoiceNumber: (val) => (!val.trim() ? 'Invoice number is required' : undefined),
      invoiceDate: (val) => (!val ? 'Invoice date is required' : undefined),
      invoiceValue: (val) =>
        !val || parseFloat(val) <= 0 ? 'Value must be positive' : undefined,
      company: (val) => (!val ? 'Select a company' : undefined),
    },
  )

  // Handlers
  const handleFileDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
    const f = e.dataTransfer.files[0]
    if (f && /\.(pdf|jpg|jpeg|png)$/i.test(f.name)) {
      setFile(f)
    } else {
      toast.error('Unsupported file type. Use PDF, JPG, or PNG.')
    }
  }, [])

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) setFile(f)
  }, [])

  const handleParse = async () => {
    if (!file) {
      toast.error('Upload a file first')
      return
    }
    setIsParsing(true)
    try {
      const tid = parseTemplateId !== 'auto' ? parseInt(parseTemplateId) : undefined
      const result = (await invoicesApi.parseInvoice(file, tid)) as ParseResult
      if (result.success && result.data) {
        const d = result.data
        setSupplier(d.supplier || '')
        setInvoiceNumber(d.invoice_number || '')
        setInvoiceDate(d.invoice_date || '')
        setInvoiceValue(d.invoice_value != null ? String(d.invoice_value) : '')
        setCurrency(d.currency || 'RON')
        if (d.value_ron != null) setValueRon(d.value_ron)
        if (d.value_eur != null) setValueEur(d.value_eur)
        if (d.exchange_rate != null) setExchangeRate(d.exchange_rate)
        if (d.auto_detected_template) setTemplateName(d.auto_detected_template)
        if (d.line_items?.length) setLineItems(d.line_items)
        else setLineItems([])
        setInvoiceType(d.invoice_type || 'standard')
        setEfacturaMatch(d.efactura_match ?? null)
        setParseResult({ supplier: d.supplier, invoice_number: d.invoice_number, invoice_value: d.invoice_value, invoice_date: d.invoice_date })

        // Match customer VAT to company
        if (d.customer_vat) {
          const normalized = d.customer_vat.replace(/\s/g, '').toUpperCase()
          const match = companiesVat.find(
            (c) => c.vat?.replace(/\s/g, '').toUpperCase() === normalized,
          )
          if (match) {
            setCompany(match.company)
            toast.success(`Parsed & matched to ${match.company}`)
          } else {
            toast.success('Parsed successfully')
          }
        } else {
          toast.success('Parsed successfully')
        }

        // Recalculate allocation values with parsed invoice value
        if (d.invoice_value != null) {
          const gross = d.invoice_value
          const eff = subtractVat && selectedVatRate ? gross / (1 + selectedVatRate.rate / 100) : gross
          setRows((prev) => prev.map((r) => ({ ...r, value: eff * (r.percent / 100) })))
        }

        // Close modal after successful parse
        setUploadOpen(false)
      } else {
        toast.error(result.error || 'Parse failed')
      }
    } catch {
      toast.error('Parse failed')
    } finally {
      setIsParsing(false)
    }
  }

  const updateRow = (id: string, updates: Partial<AllocationRow>) => {
    setRows((prev) =>
      prev.map((r) => {
        if (r.id !== id) return r
        const updated = { ...r, ...updates }
        if ('percent' in updates) {
          updated.value = effectiveValue * (updated.percent / 100)
        }
        if ('value' in updates && effectiveValue > 0) {
          updated.percent = (updated.value / effectiveValue) * 100
        }
        return updated
      }),
    )
  }

  const addRow = () => {
    const unlocked = rows.filter((r) => !r.locked)
    const lockedTotal = rows.filter((r) => r.locked).reduce((s, r) => s + r.percent, 0)
    const remaining = 100 - lockedTotal
    const newCount = unlocked.length + 1
    const perRow = remaining / newCount

    setRows((prev) => {
      const updated = prev.map((r) => {
        if (r.locked) return r
        return { ...r, percent: perRow, value: effectiveValue * (perRow / 100) }
      })
      return [...updated, { ...newRow(), percent: perRow, value: effectiveValue * (perRow / 100) }]
    })
  }

  const removeRow = (id: string) => {
    if (rows.length <= 1) return
    setRows((prev) => {
      const remaining = prev.filter((r) => r.id !== id)
      const lockedTotal = remaining.filter((r) => r.locked).reduce((s, r) => s + r.percent, 0)
      const availablePercent = 100 - lockedTotal
      const unlocked = remaining.filter((r) => !r.locked)
      if (unlocked.length === 0) return remaining
      const perRow = availablePercent / unlocked.length
      return remaining.map((r) => {
        if (r.locked) return r
        return { ...r, percent: perRow, value: effectiveValue * (perRow / 100) }
      })
    })
  }

  const handleValueChange = (val: string) => {
    setInvoiceValue(val)
    const gross = parseFloat(val) || 0
    const eff = subtractVat && selectedVatRate ? gross / (1 + selectedVatRate.rate / 100) : gross
    setRows((prev) =>
      prev.map((r) => ({ ...r, value: eff * (r.percent / 100) })),
    )
  }

  // Submit
  const submitMutation = useMutation({
    mutationFn: (data: SubmitInvoiceInput) => invoicesApi.submitInvoice(data),
    onSuccess: () => {
      toast.success('Invoice saved successfully')
      navigate('/app/accounting')
    },
    onError: () => toast.error('Failed to save invoice'),
  })

  const handleSubmit = async () => {
    v.touchAll()
    if (!v.isValid) return toast.error('Please fix the highlighted fields')
    if (rows.some((r) => !r.department)) return toast.error('All rows need a department')
    if (Math.abs(totalPercent - 100) > 1) return toast.error('Total allocation must be 100%')

    try {
      const check = await invoicesApi.checkInvoiceNumber(invoiceNumber)
      if (check.exists) {
        toast.error('Invoice number already exists')
        return
      }
    } catch {
      // continue if check fails
    }

    const data: SubmitInvoiceInput & Record<string, unknown> = {
      supplier,
      invoice_template: templateName || undefined,
      invoice_number: invoiceNumber,
      invoice_date: invoiceDate,
      invoice_value: parseFloat(invoiceValue),
      currency,
      drive_link: driveLink || undefined,
      comment: comment || undefined,
      payment_status: paymentStatus,
      subtract_vat: subtractVat,
      vat_rate: selectedVatRate?.rate,
      net_value: netValue ?? undefined,
      value_ron: valueRon ?? undefined,
      value_eur: valueEur ?? undefined,
      exchange_rate: exchangeRate ?? undefined,
      _line_items: lineItems.length > 0 ? lineItems : undefined,
      _invoice_type: invoiceType !== 'standard' ? invoiceType : undefined,
      _parse_result: parseResult ?? undefined,
      _efactura_match_id: efacturaMatch?.id ?? undefined,
      distributions: rows.map((r) => ({
        company,
        brand: r.brand || undefined,
        department: r.department,
        subdepartment: r.subdepartment || undefined,
        allocation: r.percent / 100,
        locked: r.locked,
        comment: r.comment || undefined,
        reinvoice_destinations: r.reinvoiceDestinations
          .filter((rd) => rd.company && rd.department)
          .map((rd) => ({
            company: rd.company,
            brand: rd.brand || undefined,
            department: rd.department,
            subdepartment: rd.subdepartment || undefined,
            percent: rd.percentage,
          })),
      })),
    }

    submitMutation.mutate(data)
  }

  const clearForm = () => {
    setSupplier('')
    setInvoiceNumber('')
    setInvoiceDate('')
    setInvoiceValue('')
    setCurrency('RON')
    setComment('')
    setPaymentStatus('not_paid')
    setSubtractVat(false)
    setVatRateId('')
    setDriveLink('')
    setTemplateName('')
    setFile(null)
    setCompany('')
    setRows([newRow()])
    setValueRon(null)
    setValueEur(null)
    setExchangeRate(null)
    setLineItems([])
    setInvoiceType('standard')
    setEfacturaMatch(null)
    setParseResult(null)
  }

  const hasParsedData = !!(supplier || invoiceNumber)

  const onFormSubmit = (e: React.FormEvent) => { e.preventDefault(); handleSubmit() }

  return (
    <form onSubmit={onFormSubmit} className="space-y-4">
      <PageHeader
        title="Add Invoice"
        description="Create a new invoice and distribute costs."
        actions={
          <div className="flex items-center gap-2">
            {invoiceType !== 'standard' && (
              <Badge
                variant="secondary"
                className={cn('gap-1',
                  invoiceType === 'credit_note' && 'border-red-500/50 text-red-600 dark:text-red-400',
                  invoiceType === 'advance_payment' && 'border-blue-500/50 text-blue-600 dark:text-blue-400',
                  invoiceType === 'proforma' && 'border-muted-foreground/50 text-muted-foreground',
                )}
              >
                {invoiceType === 'credit_note' ? 'Credit Note' : invoiceType === 'advance_payment' ? 'Advance' : 'Proforma'}
              </Badge>
            )}
            {templateName && (
              <Badge variant="secondary" className="gap-1">
                <FileText className="h-3 w-3" />
                {templateName}
              </Badge>
            )}
            {file && (
              <Badge variant="outline" className="gap-1">
                <FileText className="h-3 w-3" />
                {file.name}
                <button onClick={() => setFile(null)} className="ml-0.5 hover:text-destructive">
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            )}
            <Button variant="outline" onClick={() => setUploadOpen(true)}>
              <Upload className="mr-1.5 h-4 w-4" />
              {hasParsedData ? 'Re-upload' : 'Upload & Parse'}
            </Button>
            <Button variant="outline" onClick={() => navigate('/app/accounting')}>
              <ArrowLeft className="mr-1.5 h-4 w-4" />
              Back
            </Button>
          </div>
        }
      />

      {/* Upload & Parse Modal */}
      <Dialog open={uploadOpen} onOpenChange={setUploadOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Upload Invoice</DialogTitle>
            <DialogDescription>
              Upload a PDF, JPG, or PNG file and parse it with AI.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            {/* Drop zone */}
            <label
              className={cn(
                'flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors',
                isDragOver
                  ? 'border-primary bg-primary/5'
                  : 'border-muted-foreground/25 hover:border-primary/50',
                file && 'border-green-500/50 bg-green-500/5',
              )}
              onDragOver={(e) => {
                e.preventDefault()
                setIsDragOver(true)
              }}
              onDragLeave={() => setIsDragOver(false)}
              onDrop={handleFileDrop}
            >
              <input
                type="file"
                className="hidden"
                accept=".pdf,.jpg,.jpeg,.png"
                onChange={handleFileSelect}
              />
              {file ? (
                <>
                  <FileText className="mb-2 h-10 w-10 text-green-500" />
                  <span className="text-sm font-medium">{file.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {(file.size / 1024).toFixed(0)} KB — click to replace
                  </span>
                </>
              ) : (
                <>
                  <Upload className="mb-2 h-10 w-10 text-muted-foreground" />
                  <span className="text-sm font-medium">
                    Drag & drop or click to upload
                  </span>
                  <span className="text-xs text-muted-foreground">
                    PDF, JPG, PNG
                  </span>
                </>
              )}
            </label>

            {/* Parse controls */}
            <div className="space-y-1.5">
              <Label className="text-xs">Parse Method</Label>
              <Select value={parseTemplateId} onValueChange={setParseTemplateId}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">Auto-detect (AI fallback)</SelectItem>
                  {templates.map((t) => (
                    <SelectItem key={t.id} value={String(t.id)}>
                      {t.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex gap-2">
              <Button
                className="flex-1"
                onClick={handleParse}
                disabled={!file || isParsing}
              >
                {isParsing ? (
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                ) : (
                  <Wand2 className="mr-1.5 h-4 w-4" />
                )}
                {isParsing ? 'Parsing...' : 'Parse Invoice'}
              </Button>
              <Button
                variant="outline"
                onClick={() => setUploadOpen(false)}
              >
                Cancel
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* e-Factura match banner */}
      {efacturaMatch && !efacturaMatch.jarvis_invoice_id && (
        <div className="flex items-center gap-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-2.5 dark:border-blue-800 dark:bg-blue-950/30">
          <Link2 className="h-4 w-4 shrink-0 text-blue-600 dark:text-blue-400" />
          <div className="flex-1 text-sm">
            <span className="font-medium text-blue-700 dark:text-blue-300">e-Factura match found: </span>
            <span className="text-blue-600 dark:text-blue-400">
              {efacturaMatch.partner_name} — {efacturaMatch.invoice_number}
              {efacturaMatch.total_amount != null && ` — ${new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2 }).format(efacturaMatch.total_amount)} ${efacturaMatch.currency || ''}`}
            </span>
          </div>
          <Badge variant="outline" className="text-blue-600 border-blue-300 dark:text-blue-400 dark:border-blue-700">Will auto-link on save</Badge>
        </div>
      )}

      {/* Line items */}
      {lineItems.length > 0 && (
        <Card>
          <button
            className="flex w-full items-center gap-2 px-4 py-2.5 text-sm font-medium hover:bg-muted/50 transition-colors"
            onClick={() => setLineItemsOpen(!lineItemsOpen)}
          >
            {lineItemsOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            Line Items ({lineItems.length})
          </button>
          {lineItemsOpen && (
            <CardContent className="pt-0 pb-3">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-xs text-muted-foreground">
                      <th className="pb-1.5 text-left font-medium">Description</th>
                      <th className="pb-1.5 text-right font-medium w-16">Qty</th>
                      <th className="pb-1.5 text-right font-medium w-24">Unit Price</th>
                      <th className="pb-1.5 text-right font-medium w-24">Amount</th>
                      <th className="pb-1.5 text-right font-medium w-16">VAT %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lineItems.map((item, i) => (
                      <tr key={i} className="border-b last:border-0">
                        <td className="py-1.5 pr-2">{item.description}</td>
                        <td className="py-1.5 text-right tabular-nums">{item.quantity}</td>
                        <td className="py-1.5 text-right tabular-nums">{new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2 }).format(item.unit_price)}</td>
                        <td className="py-1.5 text-right tabular-nums">{new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2 }).format(item.amount)}</td>
                        <td className="py-1.5 text-right tabular-nums">{item.vat_rate != null ? `${item.vat_rate}%` : '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          )}
        </Card>
      )}

      {/* Department suggestion */}
      {deptSuggestions.length > 0 && !company && (
        <div className="flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 dark:border-amber-800 dark:bg-amber-950/30">
          <Lightbulb className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
          <div className="flex-1 text-sm">
            <span className="font-medium text-amber-700 dark:text-amber-300">Suggested: </span>
            <span className="text-amber-600 dark:text-amber-400">
              {deptSuggestions[0].company} / {deptSuggestions[0].department}
              {deptSuggestions[0].subdepartment ? ` / ${deptSuggestions[0].subdepartment}` : ''}
              {' '}(used {deptSuggestions[0].frequency}×)
            </span>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs border-amber-300 dark:border-amber-700"
            onClick={() => {
              const s = deptSuggestions[0]
              setCompany(s.company)
              setRows([{
                ...newRow(),
                brand: s.brand || '',
                department: s.department,
                subdepartment: s.subdepartment || '',
                percent: 100,
                value: effectiveValue,
              }])
            }}
          >
            Apply
          </Button>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        {/* LEFT: Invoice Details (single card) */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Invoice Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="inv-supplier" className="text-xs">
                  Supplier <span className="text-destructive">*</span>
                </Label>
                <Input id="inv-supplier" value={supplier} onChange={(e) => setSupplier(e.target.value)} onBlur={() => v.touch('supplier')} className={cn(v.error('supplier') && 'border-destructive')} />
                <FieldError message={v.error('supplier')} />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="inv-number" className="text-xs">
                    Invoice Number <span className="text-destructive">*</span>
                  </Label>
                  <Input id="inv-number" value={invoiceNumber} onChange={(e) => setInvoiceNumber(e.target.value)} onBlur={() => v.touch('invoiceNumber')} className={cn(v.error('invoiceNumber') && 'border-destructive')} />
                  <FieldError message={v.error('invoiceNumber')} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="inv-date" className="text-xs">
                    Invoice Date <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="inv-date"
                    type="date"
                    value={invoiceDate}
                    onChange={(e) => setInvoiceDate(e.target.value)}
                    onBlur={() => v.touch('invoiceDate')}
                    className={cn(v.error('invoiceDate') && 'border-destructive')}
                  />
                  <FieldError message={v.error('invoiceDate')} />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="inv-value" className="text-xs">
                    Invoice Value <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="inv-value"
                    type="number"
                    step="0.01"
                    value={invoiceValue}
                    onChange={(e) => handleValueChange(e.target.value)}
                    onBlur={() => v.touch('invoiceValue')}
                    className={cn(v.error('invoiceValue') && 'border-destructive')}
                  />
                  <FieldError message={v.error('invoiceValue')} />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Currency</Label>
                  <Select value={currency} onValueChange={setCurrency}>
                    <SelectTrigger>
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

              {/* VAT */}
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <Switch
                    checked={subtractVat}
                    onCheckedChange={(v) => {
                      setSubtractVat(v)
                      if (v && !vatRateId) {
                        const def = vatRates.find((r) => r.is_default)
                        if (def) setVatRateId(String(def.id))
                      }
                    }}
                    id="subtract-vat"
                  />
                  <Label htmlFor="subtract-vat" className="text-xs">
                    Subtract VAT
                  </Label>
                </div>
                {subtractVat && (
                  <>
                    <div className="space-y-1 flex-1">
                      <Label className="text-xs">VAT Rate</Label>
                      <Select value={vatRateId} onValueChange={setVatRateId}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {vatRates.map((r) => (
                            <SelectItem key={r.id} value={String(r.id)}>
                              {r.name} ({r.rate}%)
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">Net Value</Label>
                      <div className="flex h-9 items-center rounded-md border bg-muted/50 px-3 text-sm">
                        {netValue != null
                          ? new Intl.NumberFormat('ro-RO', {
                              minimumFractionDigits: 2,
                              maximumFractionDigits: 2,
                            }).format(netValue)
                          : '-'}
                      </div>
                    </div>
                  </>
                )}
              </div>

              {/* Payment Status */}
              <div className="space-y-1.5">
                <Label className="text-xs">Payment Status</Label>
                <Select value={paymentStatus} onValueChange={setPaymentStatus}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {paymentOptions.length > 0
                      ? paymentOptions.map((opt) => (
                          <SelectItem key={opt.value} value={opt.value}>
                            {opt.label}
                          </SelectItem>
                        ))
                      : ['not_paid', 'paid'].map((v) => (
                          <SelectItem key={v} value={v}>
                            {v.replace('_', ' ')}
                          </SelectItem>
                        ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="inv-drive-link" className="text-xs">Drive Link</Label>
                <Input
                  id="inv-drive-link"
                  value={driveLink}
                  onChange={(e) => setDriveLink(e.target.value)}
                  placeholder="https://drive.google.com/..."
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="inv-comment" className="text-xs">Comment</Label>
                <Textarea
                  id="inv-comment"
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  rows={2}
                />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* RIGHT: Cost Distribution */}
        <div className="lg:col-span-3">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <CardTitle className="text-sm">Cost Distribution</CardTitle>
              <Button size="sm" variant="outline" onClick={addRow} disabled={!company}>
                <Plus className="mr-1 h-3.5 w-3.5" />
                Add Row
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Company selector */}
              <div className="space-y-1.5">
                <Label className="text-xs">
                  Dedicated To (Company) <span className="text-destructive">*</span>
                </Label>
                <Select
                  value={company}
                  onValueChange={(val) => {
                    setCompany(val)
                    setRows([newRow()])
                  }}
                  onOpenChange={(open) => { if (!open) v.touch('company') }}
                >
                  <SelectTrigger className={cn(v.error('company') && 'border-destructive')}>
                    <SelectValue placeholder="Select company..." />
                  </SelectTrigger>
                  <SelectContent>
                    {(companies as string[]).map((c) => (
                      <SelectItem key={c} value={c}>
                        {c}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldError message={v.error('company')} />
              </div>

              {/* Allocation rows */}
              {company && (
                <div className="space-y-2">
                  {/* Header */}
                  <div className="grid grid-cols-12 gap-2 text-xs font-medium text-muted-foreground px-1">
                    {brands.length > 0 && <div className="col-span-2">Brand</div>}
                    <div className={brands.length > 0 ? 'col-span-3' : 'col-span-4'}>Department</div>
                    <div className="col-span-2">Subdepartment</div>
                    <div className="col-span-1 text-right">%</div>
                    <div className="col-span-2 text-right">
                      Value ({currency})
                    </div>
                    <div className={brands.length > 0 ? 'col-span-2' : 'col-span-3'}></div>
                  </div>

                  {rows.map((row) => (
                    <AllocationRowComponent
                      key={row.id}
                      row={row}
                      company={company}
                      allCompanies={companies as string[]}
                      brands={brands}
                      departments={departments}
                      effectiveValue={effectiveValue}
                      currency={currency}
                      onUpdate={(updates) => updateRow(row.id, updates)}
                      onRemove={() => removeRow(row.id)}
                      canRemove={rows.length > 1}
                    />
                  ))}

                  {/* Total */}
                  <div className="flex items-center justify-end gap-4 border-t pt-2 px-1">
                    <span className="text-sm font-medium">Total Allocation:</span>
                    <span
                      className={cn(
                        'text-sm font-semibold',
                        Math.abs(totalPercent - 100) <= 1
                          ? 'text-green-600'
                          : 'text-destructive',
                      )}
                    >
                      {totalPercent.toFixed(2)}%
                    </span>
                    <span className="text-sm text-muted-foreground">|</span>
                    <span className="text-sm font-medium">
                      {new Intl.NumberFormat('ro-RO', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      }).format(
                        rows.reduce((s, r) => s + r.value, 0),
                      )}{' '}
                      {currency}
                    </span>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Sticky bottom action bar */}
      <div className="sticky bottom-0 -mx-6 -mb-6 z-40 border-t bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div className="flex items-center justify-between gap-3 px-6 py-3">
          <Button variant="outline" onClick={clearForm}>
            Clear Form
          </Button>
          <div className="flex items-center gap-3">
            <Button variant="outline" onClick={() => navigate('/app/accounting')}>
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={submitMutation.isPending}
              className="min-w-[160px]"
            >
              {submitMutation.isPending ? (
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
              ) : null}
              {submitMutation.isPending ? 'Saving...' : 'Save Distribution'}
            </Button>
          </div>
        </div>
      </div>
    </form>
  )
}

