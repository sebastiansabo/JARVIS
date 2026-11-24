// "Transferă în venit" dialog — income mirror of TransferToCostDialog. Turns an
// invoice document into a VehicleRevenue (Venituri). Parses once (shared
// react-query cache key with the cost dialog) and uses revenue_prefill, where
// the invoice's customer becomes the client. Confirms via transfer-to-revenue
// (carpark/routes/documents.py).
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
import { REVENUE_TYPE_LABELS, type RevenueType, type DispoDocument } from '@/types/carpark'

function round2(n: number): number {
  return Math.round(n * 100) / 100
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

interface TransferToRevenueDialogProps {
  vehicleId: number
  doc: DispoDocument | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess: () => void
}

export function TransferToRevenueDialog({
  vehicleId,
  doc,
  open,
  onOpenChange,
  onSuccess,
}: TransferToRevenueDialogProps) {
  const [revenueType, setRevenueType] = useState<RevenueType>('sale')
  const [amount, setAmount] = useState('')
  const [vatRate, setVatRate] = useState('19')
  const [vatAmount, setVatAmount] = useState('')
  const [invoiceNumber, setInvoiceNumber] = useState('')
  const [date, setDate] = useState(todayIso())
  const [clientName, setClientName] = useState('')
  const [description, setDescription] = useState('')
  const [currency, setCurrency] = useState('RON')
  // Gross recompute anchor (not persisted on revenues — see the mapper).
  const [grossValue, setGrossValue] = useState<number | null>(null)
  // Default: book the net (VAT-excluded) amount. Unchecked books the total.
  const [transferNet, setTransferNet] = useState(true)

  const docId = doc?.id ?? null

  const { data: parseResult, isLoading } = useQuery({
    queryKey: ['carpark', 'parse-invoice', vehicleId, docId],
    queryFn: () => carparkDispoApi.parseDocumentInvoice(vehicleId, docId as number),
    enabled: open && docId != null,
  })

  useEffect(() => {
    if (!open || !parseResult) return
    const prefill = parseResult.revenue_prefill
    if (prefill) {
      setRevenueType(prefill.revenue_type ?? 'sale')
      setAmount(prefill.amount != null ? String(prefill.amount) : '')
      setVatRate(String(prefill.vat_rate ?? 19))
      setVatAmount(prefill.vat_amount != null ? String(prefill.vat_amount) : '')
      setInvoiceNumber(prefill.invoice_number ?? '')
      setDate(prefill.date ?? todayIso())
      setClientName(prefill.client_name ?? '')
      setDescription(prefill.description ?? '')
      setCurrency(prefill.currency ?? 'RON')
      setGrossValue(prefill.invoice_value ?? null)
    } else {
      setRevenueType('sale')
      setAmount('')
      setVatRate('19')
      setVatAmount('')
      setInvoiceNumber('')
      setDate(todayIso())
      setClientName('')
      setDescription('')
      setCurrency('RON')
      setGrossValue(null)
      toast.info('Nu am putut citi automat factura — completează manual.')
    }
  }, [parseResult, open])

  // Editing net re-anchors gross so a later TVA%-change recomputes correctly
  // (same behavior as the cost dialog).
  const handleAmountChange = (value: string) => {
    setAmount(value)
    const net = Number(value)
    const rate = Number(vatRate)
    if (value === '' || Number.isNaN(net) || vatRate === '' || Number.isNaN(rate)) return
    const vat = round2((net * rate) / 100)
    setVatAmount(String(vat))
    setGrossValue(round2(net + vat))
  }

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
      if (!Number.isNaN(net)) setVatAmount(String(round2((net * rate) / 100)))
    }
  }

  const transferMut = useMutation({
    mutationFn: () => {
      if (!doc) throw new Error('No document selected')
      const netNum = Number(amount) || 0
      const vatNum = Number(vatAmount) || 0
      const grossNum = grossValue ?? round2(netNum + vatNum)
      return carparkDispoApi.transferDocumentToRevenue(vehicleId, doc.id, {
        revenue_type: revenueType,
        amount: transferNet ? netNum : grossNum,
        vat_amount: transferNet ? vatNum : 0,
        invoice_number: invoiceNumber || null,
        client_name: clientName || null,
        description: description || null,
        currency,
        date,
      })
    },
    onSuccess: () => {
      toast.success('Transferat în venituri')
      onSuccess()
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Transferul în venituri a eșuat')),
  })

  const grossPreview = grossValue ?? round2((Number(amount) || 0) + (Number(vatAmount) || 0))
  const effectiveAmount = transferNet ? (Number(amount) || 0) : grossPreview

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>Transferă în venit</DialogTitle>
        </DialogHeader>
        {isLoading ? (
          <div className="py-8 text-center text-sm text-muted-foreground">Se citește factura…</div>
        ) : (
          <>
            <div className="grid gap-4 py-2">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Tip venit</Label>
                  <Select value={revenueType} onValueChange={(v) => setRevenueType(v as RevenueType)}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {Object.entries(REVENUE_TYPE_LABELS).map(([k, label]) => (
                        <SelectItem key={k} value={k}>{label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Monedă</Label>
                  <Input value={currency} readOnly />
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
                  <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
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
                  <Checkbox id="revenue-transfer-net" checked={transferNet}
                    onCheckedChange={(c) => setTransferNet(c === true)} />
                  <Label htmlFor="revenue-transfer-net" className="cursor-pointer text-sm font-normal">
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
                  <Label>Client</Label>
                  <Input placeholder="Nume client" value={clientName}
                    onChange={(e) => setClientName(e.target.value)} />
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

export default TransferToRevenueDialog
