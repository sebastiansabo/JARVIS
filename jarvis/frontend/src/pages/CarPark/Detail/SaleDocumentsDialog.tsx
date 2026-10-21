// CarPark vehicle Detail — "Documente vânzare" dialog: drives the three
// sale-document renderers (contract / proformă / garanție) added in Tasks
// 2-7 of the CarPark "Documente vanzare" plan. Mirrors the shadcn Dialog
// pattern of ../Dispo/SellDialog.tsx. Price/currency/dates are pre-filled
// from the vehicle but stay editable (design D7) — context.py now prefers
// these form values over the vehicle's own price/currency (see the sibling
// backend fix), so editing them here actually reaches the rendered PDF.
//
// The buyer is NOT re-picked here: it's resolved server-side from the
// vehicle's existing buyer_client_id/buyer_name (a buyer picker in this
// dialog would be a silent no-op, since the backend context ignores any
// form-supplied buyer). The leasing-company picker is the one exception —
// a leasing sale's "Cumparator" party comes from `carpark_leasing_companies`,
// which the vehicle record has no column for, so the form is the only way
// to supply it.
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { carparkSaleDocsApi } from '@/api/carparkSaleDocs'
import { LeasingCompanySelect } from './LeasingCompanySelect'
import type { SaleDocType, SaleDocForm, Vehicle } from '@/types/carpark'
import { apiErrorMessage } from '../Dispo/dispoApiError'

// Mirrors `carpark/services/sale_docs/context.py::LEASING_SALE_TYPES` —
// sale_type values that mean "financed via a leasing company" (Cumparator
// = the leasing company) rather than a cash/direct sale.
const LEASING_SALE_TYPES = ['PLR', 'CREDIT PLR', 'BT LEASING', 'BRD', 'BCR', 'AW NEXT']

const DOC_ROWS: { type: SaleDocType; label: string }[] = [
  { type: 'contract', label: 'Contract' },
  { type: 'proforma', label: 'Proformă' },
  { type: 'garantie', label: 'Garanție' },
]

function todayStr(): string {
  return new Date().toISOString().slice(0, 10)
}

export function SaleDocumentsDialog({ vehicle, onClose }: { vehicle: Vehicle; onClose: () => void }) {
  const queryClient = useQueryClient()

  const [contractNumber, setContractNumber] = useState('')
  const [contractDate, setContractDate] = useState(todayStr())
  const [proformaNumber, setProformaNumber] = useState('')
  const [proformaDate, setProformaDate] = useState(todayStr())
  const [price, setPrice] = useState(vehicle.sale_price != null ? String(vehicle.sale_price) : vehicle.current_price != null ? String(vehicle.current_price) : '')
  const [currency, setCurrency] = useState(vehicle.price_currency || 'RON')
  const [deliveryTermDays, setDeliveryTermDays] = useState('')
  const [deliveryPlace, setDeliveryPlace] = useState('')
  const [deliveryDate, setDeliveryDate] = useState(vehicle.sale_date || todayStr())
  const [leasingCompanyId, setLeasingCompanyId] = useState<number | null>(null)
  const [autonomy, setAutonomy] = useState('')

  const isLeasing = !!vehicle.sale_type && LEASING_SALE_TYPES.includes(vehicle.sale_type)
  const isEV = (vehicle.fuel_type || '').toLowerCase().includes('electric')

  function buildForm(): SaleDocForm {
    const form: SaleDocForm = {}
    if (contractNumber !== '') form.contract_number = contractNumber
    if (contractDate !== '') form.contract_date = contractDate
    if (proformaNumber !== '') form.proforma_number = Number(proformaNumber)
    if (proformaDate !== '') form.proforma_date = proformaDate
    if (price !== '') form.price = Number(price)
    if (currency !== '') form.currency = currency
    if (deliveryTermDays !== '') form.delivery_term_days = Number(deliveryTermDays)
    if (deliveryPlace !== '') form.delivery_place = deliveryPlace
    if (deliveryDate !== '') form.delivery_date = deliveryDate
    if (isLeasing && leasingCompanyId != null) form.leasing_company_id = leasingCompanyId
    if (isEV && autonomy !== '') form.autonomy = autonomy
    return form
  }

  const generateMutation = useMutation({
    mutationFn: (docType: SaleDocType) =>
      carparkSaleDocsApi.generate(vehicle.id, { doc_type: docType, form: buildForm() }),
    onSuccess: (blob) => {
      // Best-effort preview: open the rendered PDF in a new tab. Nothing is
      // persisted server-side by `generate` — that's what "Salvează" is for.
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank')
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Eroare la generarea documentului')),
  })

  const saveMutation = useMutation({
    mutationFn: (docType: SaleDocType) =>
      carparkSaleDocsApi.save(vehicle.id, { doc_type: docType, form: buildForm() }),
    onSuccess: () => {
      toast.success('Document salvat')
      queryClient.invalidateQueries({ queryKey: ['carpark', 'documents', vehicle.id] })
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Eroare la salvare')),
  })

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Documente vânzare — {vehicle.brand} {vehicle.model}</DialogTitle>
          <DialogDescription>VIN {vehicle.vin}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="sd-contract-number">Nr. contract</Label>
              <Input
                id="sd-contract-number"
                value={contractNumber}
                onChange={(e) => setContractNumber(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="sd-contract-date">Data contract</Label>
              <Input
                id="sd-contract-date"
                type="date"
                value={contractDate}
                onChange={(e) => setContractDate(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="sd-proforma-number">Nr. proformă</Label>
              <Input
                id="sd-proforma-number"
                type="number"
                value={proformaNumber}
                onChange={(e) => setProformaNumber(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="sd-proforma-date">Data proformă</Label>
              <Input
                id="sd-proforma-date"
                type="date"
                value={proformaDate}
                onChange={(e) => setProformaDate(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="sd-price">Preț</Label>
              <Input
                id="sd-price"
                type="number"
                step="0.01"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="sd-currency">Valută</Label>
              <Input id="sd-currency" value={currency} onChange={(e) => setCurrency(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="sd-delivery-term-days">Termen livrare (zile)</Label>
              <Input
                id="sd-delivery-term-days"
                type="number"
                value={deliveryTermDays}
                onChange={(e) => setDeliveryTermDays(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="sd-delivery-place">Loc livrare</Label>
              <Input
                id="sd-delivery-place"
                value={deliveryPlace}
                onChange={(e) => setDeliveryPlace(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="sd-delivery-date">Data livrare</Label>
              <Input
                id="sd-delivery-date"
                type="date"
                value={deliveryDate}
                onChange={(e) => setDeliveryDate(e.target.value)}
              />
            </div>
            {isEV && (
              <div>
                <Label htmlFor="sd-autonomy">Autonomie (km)</Label>
                <Input id="sd-autonomy" value={autonomy} onChange={(e) => setAutonomy(e.target.value)} />
              </div>
            )}
          </div>

          {isLeasing && (
            <div>
              <Label>Firmă de leasing (Cumpărător)</Label>
              <LeasingCompanySelect value={leasingCompanyId} onSelect={(lc) => setLeasingCompanyId(lc.id)} />
            </div>
          )}

          <div className="space-y-2">
            {DOC_ROWS.map(({ type, label }) => (
              <div key={type} className="flex items-center justify-between rounded-md border p-2">
                <span className="text-sm font-medium">{label}</span>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={generateMutation.isPending}
                    onClick={() => generateMutation.mutate(type)}
                  >
                    Generează
                  </Button>
                  <Button
                    size="sm"
                    disabled={saveMutation.isPending}
                    onClick={() => saveMutation.mutate(type)}
                  >
                    Salvează în Documente
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Anulează</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default SaleDocumentsDialog
