// "Transferă în cost" dialog — turns an invoice document (factura_achizitie /
// factura_vanzare / factura_transfer) into a VehicleCost. On open it calls
// parse-invoice for a best-effort prefill (see invoice_cost_mapper.py);
// the user reviews/edits the fields, then confirms via transfer-to-cost
// (carpark/routes/documents.py). Modeled on the "Înregistrează cost" dialog
// in Detail.tsx (~line 3651) — same shadcn Dialog/Input/Select layout.
import { useEffect, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { carparkDispoApi } from '@/api/carparkDispo'
import { apiErrorMessage } from '../Dispo/dispoApiError'
import { COST_TYPE_LABELS, type CostType, type DispoDocument } from '@/types/carpark'

function round2(n: number): number {
  return Math.round(n * 100) / 100
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

interface TransferToCostDialogProps {
  vehicleId: number
  doc: DispoDocument | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess: () => void
}

export function TransferToCostDialog({
  vehicleId,
  doc,
  open,
  onOpenChange,
  onSuccess,
}: TransferToCostDialogProps) {
  const [costType, setCostType] = useState<CostType>('other')
  const [amount, setAmount] = useState('')
  const [vatRate, setVatRate] = useState('19')
  const [vatAmount, setVatAmount] = useState('')
  const [invoiceNumber, setInvoiceNumber] = useState('')
  const [date, setDate] = useState(todayIso())
  const [supplierName, setSupplierName] = useState('')
  const [description, setDescription] = useState('')
  const [currency, setCurrency] = useState('RON')
  // Not shown as form fields — kept as the recompute anchor (gross) and
  // round-tripped back to the backend verbatim on confirm.
  const [grossValue, setGrossValue] = useState<number | null>(null)
  const [invoiceDate, setInvoiceDate] = useState<string | null>(null)
  // Default: book the net (VAT-excluded) amount as the cost. Unchecked books
  // the total (net + TVA) and files the VAT into the amount.
  const [transferNet, setTransferNet] = useState(true)

  const docId = doc?.id ?? null

  const { data: parseResult, isLoading } = useQuery({
    queryKey: ['carpark', 'parse-invoice', vehicleId, docId],
    queryFn: () => carparkDispoApi.parseDocumentInvoice(vehicleId, docId as number),
    enabled: open && docId != null,
  })

  // Apply the parse result to the form once it resolves. Re-runs whenever
  // `open` flips true (re-applying the prefill from a fresh open) or when a
  // new parseResult lands (switching documents / a fresh fetch).
  useEffect(() => {
    if (!open || !parseResult) return
    const prefill = parseResult.cost_prefill
    if (prefill) {
      setCostType(prefill.cost_type ?? 'other')
      setAmount(prefill.amount != null ? String(prefill.amount) : '')
      setVatRate(String(prefill.vat_rate ?? 19))
      setVatAmount(prefill.vat_amount != null ? String(prefill.vat_amount) : '')
      setInvoiceNumber(prefill.invoice_number ?? '')
      setDate(prefill.date ?? todayIso())
      setSupplierName(prefill.supplier_name ?? '')
      setDescription(prefill.description ?? '')
      setCurrency(prefill.currency ?? 'RON')
      setGrossValue(prefill.invoice_value ?? null)
      setInvoiceDate(prefill.invoice_date ?? null)
    } else {
      setCostType('other')
      setAmount('')
      setVatRate('19')
      setVatAmount('')
      setInvoiceNumber('')
      setDate(todayIso())
      setSupplierName('')
      setDescription('')
      setCurrency('RON')
      setGrossValue(null)
      setInvoiceDate(null)
      toast.info('Nu am putut citi automat factura — completează manual.')
    }
  }, [parseResult, open])

  // Editing the net amount directly must keep vat_amount/grossValue in sync
  // with it — otherwise grossValue (sent to the backend as invoice_value)
  // stays anchored to whatever the parse-invoice prefill (or a prior TVA%
  // edit) last set it to, and stored gross no longer equals amount+vat_amount.
  // Recompute vat_amount from the current TVA%, and re-anchor grossValue to
  // net+vat_amount so a later TVA%-change recomputes from a gross that still
  // reflects this edit.
  const handleAmountChange = (value: string) => {
    setAmount(value)
    const net = Number(value)
    const rate = Number(vatRate)
    if (value === '' || Number.isNaN(net) || vatRate === '' || Number.isNaN(rate)) return
    const vat = round2((net * rate) / 100)
    setVatAmount(String(vat))
    setGrossValue(round2(net + vat))
  }

  // Changing TVA % recomputes from the stored gross when known (net+VAT
  // from the fixed invoice total); otherwise it recomputes VAT from the
  // currently entered net.
  const handleVatRateChange = (value: string) => {
    setVatRate(value)
    const rate = Number(value)
    if (value === '' || Number.isNaN(rate)) return
    if (grossValue != null) {
      const net = round2(grossValue / (1 + rate / 100))
      setAmount(String(net))
      setVatAmount(String(round2(grossValue - net)))
    } else if (amount) {
      const net = Number(amount)
      if (!Number.isNaN(net)) {
        setVatAmount(String(round2((net * rate) / 100)))
      }
    }
  }

  const transferMut = useMutation({
    mutationFn: () => {
      if (!doc) throw new Error('No document selected')
      const netNum = Number(amount) || 0
      const vatNum = Number(vatAmount) || 0
      const grossNum = grossValue ?? round2(netNum + vatNum)
      return carparkDispoApi.transferDocumentToCost(vehicleId, doc.id, {
        cost_type: costType,
        amount: transferNet ? netNum : grossNum,
        // When booking the gross total, VAT isn't separated — keep rate+amount
        // consistent (both 0) rather than leaving a stale rate on the row.
        vat_rate: transferNet && vatRate ? Number(vatRate) : 0,
        vat_amount: transferNet ? vatNum : 0,
        invoice_number: invoiceNumber || null,
        invoice_date: invoiceDate ?? null,
        invoice_value: grossValue ?? null,
        supplier_name: supplierName || null,
        description: description || null,
        currency,
        date,
      })
    },
    onSuccess: () => {
      toast.success('Transferat în costuri')
      onSuccess()
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Transferul în costuri a eșuat')),
  })

  const grossPreview = grossValue ?? round2((Number(amount) || 0) + (Number(vatAmount) || 0))
  const effectiveAmount = transferNet ? (Number(amount) || 0) : grossPreview

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>Transferă în cost</DialogTitle>
        </DialogHeader>
        {isLoading ? (
          <div className="py-8 text-center text-sm text-muted-foreground">Se citește factura…</div>
        ) : (
          <>
            <div className="grid gap-4 py-2">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Categorie</Label>
                  <Select value={costType} onValueChange={(v) => setCostType(v as CostType)}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {Object.entries(COST_TYPE_LABELS).map(([k, label]) => (
                        <SelectItem key={k} value={k}>{label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Monedă</Label>
                  <Input value={currency} readOnly disabled />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Sumă (net) *</Label>
                  <Input type="number" step="0.01" placeholder="0.00" value={amount} autoFocus
                    onChange={(e) => handleAmountChange(e.target.value)} />
                </div>
                <div>
                  <Label>Dată *</Label>
                  <Input type="date" value={date}
                    onChange={(e) => setDate(e.target.value)} />
                </div>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <Label>TVA %</Label>
                  <Input type="number" step="0.01" value={vatRate}
                    onChange={(e) => handleVatRateChange(e.target.value)} />
                </div>
                <div>
                  <Label>Valoare TVA</Label>
                  <Input type="number" step="0.01" placeholder="0.00" value={vatAmount}
                    onChange={(e) => setVatAmount(e.target.value)} />
                </div>
                <div>
                  <Label>Nr. factură</Label>
                  <Input placeholder="Număr factură" value={invoiceNumber}
                    onChange={(e) => setInvoiceNumber(e.target.value)} />
                </div>
              </div>
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <Checkbox id="cost-transfer-net" checked={transferNet}
                    onCheckedChange={(c) => setTransferNet(c === true)} />
                  <Label htmlFor="cost-transfer-net" className="cursor-pointer text-sm font-normal">
                    Transferă suma netă (fără TVA)
                  </Label>
                </div>
                {!transferNet && (
                  <p className="pl-6 text-xs text-muted-foreground">
                    Se transferă totalul (cu TVA): {grossPreview.toFixed(2)} {currency}
                  </p>
                )}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Furnizor</Label>
                  <Input placeholder="Nume furnizor" value={supplierName}
                    onChange={(e) => setSupplierName(e.target.value)} />
                </div>
                <div>
                  <Label>Descriere</Label>
                  <Input placeholder="Descriere opțională" value={description}
                    onChange={(e) => setDescription(e.target.value)} />
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => onOpenChange(false)}>Anulează</Button>
              <Button
                disabled={effectiveAmount <= 0 || transferMut.isPending}
                onClick={() => transferMut.mutate()}
              >
                {transferMut.isPending ? 'Se transferă...' : 'Transferă'}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

export default TransferToCostDialog
