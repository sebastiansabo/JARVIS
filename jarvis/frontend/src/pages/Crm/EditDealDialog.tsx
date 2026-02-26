import { useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Search, X } from 'lucide-react'
import { toast } from 'sonner'
import { crmApi, type CrmDeal } from '@/api/crm'
import { useDebounce } from '@/lib/utils'

interface Props {
  deal: CrmDeal | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function EditDealDialog({ deal, open, onOpenChange }: Props) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<Record<string, string>>({})
  const [clientSearch, setClientSearch] = useState('')
  const [clientOpen, setClientOpen] = useState(false)
  const [selectedClient, setSelectedClient] = useState<{ id: number; name: string } | null>(null)
  const debouncedClientSearch = useDebounce(clientSearch, 300)

  const { data: dossierData } = useQuery({ queryKey: ['crm-deal-statuses'], queryFn: crmApi.getDealStatuses, enabled: open })
  const { data: orderData } = useQuery({ queryKey: ['crm-order-statuses'], queryFn: crmApi.getOrderStatuses, enabled: open })
  const { data: contractData } = useQuery({ queryKey: ['crm-contract-statuses'], queryFn: crmApi.getContractStatuses, enabled: open })
  const { data: clientsData } = useQuery({
    queryKey: ['crm-clients-search', debouncedClientSearch],
    queryFn: () => crmApi.getClients({ name: debouncedClientSearch, limit: '10' }),
    enabled: open && debouncedClientSearch.length >= 2,
  })

  const dossierOptions = dossierData?.statuses.map(s => s.dossier_status) || []
  const orderOptions = orderData?.statuses || []
  const contractOptions = contractData?.statuses || []

  useEffect(() => {
    if (deal) {
      setForm({
        brand: deal.brand || '',
        model_name: deal.model_name || '',
        buyer_name: deal.buyer_name || '',
        dossier_status: deal.dossier_status || '',
        order_status: deal.order_status || '',
        contract_status: deal.contract_status || '',
        sales_person: deal.sales_person || '',
        sale_price_net: deal.sale_price_net?.toString() || '',
        color: deal.color || '',
        fuel_type: deal.fuel_type || '',
        vehicle_type: deal.vehicle_type || '',
        registration_number: deal.registration_number || '',
        vin: deal.vin || '',
        engine_code: deal.engine_code || '',
        client_id: deal.client_id?.toString() || '',
      })
      setSelectedClient(
        deal.client_id
          ? { id: deal.client_id, name: deal.client_display_name || `Client #${deal.client_id}` }
          : null
      )
      setClientSearch('')
    }
  }, [deal])

  const mutation = useMutation({
    mutationFn: (data: Record<string, string>) => crmApi.updateDeal(deal!.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['crm-deals'] })
      queryClient.invalidateQueries({ queryKey: ['crm-deal-statuses'] })
      queryClient.invalidateQueries({ queryKey: ['crm-order-statuses'] })
      queryClient.invalidateQueries({ queryKey: ['crm-contract-statuses'] })
      toast.success('Deal updated')
      onOpenChange(false)
    },
    onError: () => toast.error('Failed to update deal'),
  })

  const selectFields: Record<string, string[]> = {
    dossier_status: dossierOptions,
    order_status: orderOptions,
    contract_status: contractOptions,
  }

  const fields: { key: string; label: string; type?: string }[] = [
    { key: 'brand', label: 'Brand' },
    { key: 'model_name', label: 'Model' },
    { key: 'buyer_name', label: 'Buyer' },
    { key: 'dossier_status', label: 'Dossier Status' },
    { key: 'order_status', label: 'Order Status' },
    { key: 'contract_status', label: 'Contract Status' },
    { key: 'sales_person', label: 'Sales Person' },
    { key: 'sale_price_net', label: 'Sale Price (Net)', type: 'number' },
    { key: 'color', label: 'Color' },
    { key: 'fuel_type', label: 'Fuel Type' },
    { key: 'vehicle_type', label: 'Vehicle Type' },
    { key: 'registration_number', label: 'Reg. Number' },
    { key: 'vin', label: 'VIN' },
    { key: 'engine_code', label: 'Engine Code' },
  ]

  const clients = clientsData?.clients || []

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit Deal — {deal?.dossier_number || deal?.id}</DialogTitle>
        </DialogHeader>

        {/* Client link */}
        <div className="space-y-1 pb-3 border-b">
          <Label className="text-xs">Linked Client</Label>
          {selectedClient ? (
            <div className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm">
              <span className="flex-1">{selectedClient.name}</span>
              <Button
                variant="ghost" size="icon" className="h-5 w-5 shrink-0"
                onClick={() => {
                  setSelectedClient(null)
                  setForm(prev => ({ ...prev, client_id: '' }))
                }}
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            </div>
          ) : (
            <Popover open={clientOpen} onOpenChange={setClientOpen}>
              <PopoverTrigger asChild>
                <Button variant="outline" className="w-full justify-start text-muted-foreground font-normal">
                  <Search className="h-4 w-4 mr-2" />Search client...
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[350px] p-2" align="start">
                <Input
                  placeholder="Type client name..."
                  value={clientSearch}
                  onChange={e => setClientSearch(e.target.value)}
                  className="mb-2"
                  autoFocus
                />
                <div className="max-h-[200px] overflow-y-auto">
                  {clientSearch.length < 2 ? (
                    <p className="text-xs text-muted-foreground px-2 py-3 text-center">Type at least 2 characters</p>
                  ) : clients.length === 0 ? (
                    <p className="text-xs text-muted-foreground px-2 py-3 text-center">No clients found</p>
                  ) : (
                    clients.map(c => (
                      <button
                        key={c.id}
                        className="w-full text-left px-2 py-1.5 rounded-md text-sm hover:bg-accent cursor-pointer"
                        onClick={() => {
                          setSelectedClient({ id: c.id, name: c.display_name })
                          setForm(prev => ({ ...prev, client_id: String(c.id) }))
                          setClientOpen(false)
                          setClientSearch('')
                        }}
                      >
                        <div>{c.display_name}</div>
                        {c.phone && <div className="text-xs text-muted-foreground">{c.phone}</div>}
                      </button>
                    ))
                  )}
                </div>
              </PopoverContent>
            </Popover>
          )}
        </div>

        <div className="grid grid-cols-2 gap-4 py-4">
          {fields.map(f => (
            <div key={f.key} className="space-y-1">
              <Label className="text-xs">{f.label}</Label>
              {f.key in selectFields ? (
                <Select
                  value={form[f.key] || '_empty'}
                  onValueChange={v => setForm(prev => ({ ...prev, [f.key]: v === '_empty' ? '' : v }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder={`Select ${f.label.toLowerCase()}...`} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="_empty">— None —</SelectItem>
                    {selectFields[f.key].map(opt => (
                      <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Input
                  type={f.type || 'text'}
                  value={form[f.key] || ''}
                  onChange={e => setForm(prev => ({ ...prev, [f.key]: e.target.value }))}
                />
              )}
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={() => mutation.mutate(form)} disabled={mutation.isPending}>
            {mutation.isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
