import { useState, useRef } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Search, Check, ChevronsUpDown } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import { vouchersApi } from '@/api/vouchers'
import { usersApi } from '@/api/users'
import { crmApi } from '@/api/crm'
import { organizationApi } from '@/api/organization'
import { useAuthStore } from '@/stores/authStore'
import type { VoucherCreatePayload, ServiceCatalogCompanyItem } from '@/types/vouchers'

const VALIDITY_OPTIONS = [
  { value: '1', label: '1 month' },
  { value: '3', label: '3 months' },
  { value: '6', label: '6 months' },
  { value: '12', label: '12 months' },
  { value: '24', label: '24 months' },
]

const TYPE_OPTIONS = [
  { value: 'value', label: 'Value (LEI)' },
  { value: 'accessory_discount_code', label: 'Discount Code' },
  { value: 'accessory_percentage', label: 'Percentage' },
  { value: 'service_items', label: 'Service Items' },
]

interface SelectedService {
  id: number
  name: string
  price: number
  currency: string
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

interface VoucherIssueFormProps {
  onSuccess?: () => void
}

export default function VoucherIssueForm({ onSuccess }: VoucherIssueFormProps) {
  const user = useAuthStore((s) => s.user)
  const userCompany = user?.company || ''

  // ── Company / Department (informational only — not sent to backend) ──
  const [department, setDepartment] = useState(user?.department || '')
  const { data: departments = [] } = useQuery({
    queryKey: ['departments', userCompany],
    queryFn: () => organizationApi.getDepartments(userCompany),
    enabled: !!userCompany,
    staleTime: 5 * 60_000,
  })

  // ── CRM client search / autofill ──
  const [clientSearch, setClientSearch] = useState('')
  const [activeClientSearch, setActiveClientSearch] = useState('')
  const [showClientResults, setShowClientResults] = useState(false)

  const { data: clientSearchData } = useQuery({
    queryKey: ['crm-clients-search-voucher-issue', activeClientSearch],
    queryFn: () => crmApi.getClients({ q: activeClientSearch, limit: '10' }),
    enabled: activeClientSearch.length >= 2,
    staleTime: 30_000,
  })
  const clientResults = clientSearchData?.clients ?? []

  const triggerClientSearch = () => {
    if (clientSearch.trim().length >= 2) {
      setActiveClientSearch(clientSearch.trim())
      setShowClientResults(true)
    }
  }

  // ── Client / contract fields ──
  const [clientName, setClientName] = useState('')
  const [clientCif, setClientCif] = useState('')
  const [clientEmail, setClientEmail] = useState('')
  const [contractNumber, setContractNumber] = useState('')
  const [carVin, setCarVin] = useState('')

  const selectClient = (id: number, displayName: string, nrReg?: string) => {
    setClientName(displayName)
    if (nrReg) setClientCif(nrReg)
    setClientSearch('')
    setShowClientResults(false)
    crmApi.getClient(id).then((detail) => {
      const profile = detail?.profile
      if (profile?.cui) setClientCif(profile.cui)
      if (detail?.client?.email) setClientEmail(detail.client.email)
      const deals = detail?.deals ?? []
      if (deals.length > 0) {
        const deal = deals[0]
        if (deal.vin) setCarVin(deal.vin)
        if (deal.dossier_number) setContractNumber(deal.dossier_number)
      }
    }).catch(() => {})
  }

  // ── Validity / type / benefit fields ──
  const [validityMonths, setValidityMonths] = useState('12')
  const [voucherType, setVoucherType] = useState('value')
  const [valueLei, setValueLei] = useState('')
  const [discountCode, setDiscountCode] = useState('')
  const [discountPercentage, setDiscountPercentage] = useState('')
  const [selectedServices, setSelectedServices] = useState<SelectedService[]>([])

  const { data: serviceCatalog = [] } = useQuery({
    queryKey: ['voucher-service-catalog-company'],
    queryFn: () => vouchersApi.getServiceCatalogCompany(),
    enabled: voucherType === 'service_items',
    staleTime: 60_000,
  })
  const selectedServiceIds = new Set(selectedServices.map((s) => s.id))
  const servicesTotal = selectedServices.reduce((sum, s) => sum + s.price, 0)

  const toggleService = (svc: ServiceCatalogCompanyItem, checked: boolean) => {
    if (checked) {
      setSelectedServices((prev) => [...prev, { id: svc.id, name: svc.name, price: svc.price, currency: svc.currency }])
    } else {
      setSelectedServices((prev) => prev.filter((s) => s.id !== svc.id))
    }
  }

  // ── Notes / start date ──
  const [notes, setNotes] = useState('')
  const [startDate, setStartDate] = useState(todayIso())

  // ── Approver (searchable) ──
  const [approverUserId, setApproverUserId] = useState('')
  const [approverOpen, setApproverOpen] = useState(false)
  const [approverSearch, setApproverSearch] = useState('')
  const approverInputRef = useRef<HTMLInputElement>(null)

  const { data: users = [] } = useQuery({
    queryKey: ['users-list'],
    queryFn: () => usersApi.getUsers(),
    staleTime: 10 * 60_000,
  })
  const selectedApprover = users.find((u) => String(u.id) === approverUserId)
  const filteredUsers = approverSearch.trim()
    ? users.filter((u) => u.name.toLowerCase().includes(approverSearch.toLowerCase()))
    : users

  const [errors, setErrors] = useState<Record<string, string>>({})

  const resetForm = () => {
    setClientName('')
    setClientCif('')
    setClientEmail('')
    setContractNumber('')
    setCarVin('')
    setValidityMonths('12')
    setVoucherType('value')
    setValueLei('')
    setDiscountCode('')
    setDiscountPercentage('')
    setSelectedServices([])
    setNotes('')
    setStartDate(todayIso())
    setApproverUserId('')
    setApproverSearch('')
    setErrors({})
  }

  const submitMutation = useMutation({
    mutationFn: (payload: VoucherCreatePayload) => vouchersApi.create(payload),
    onSuccess: (result) => {
      toast.success(
        `Voucher ${result.voucher.voucher_code} created — pending approval from ${result.voucher.approver_name}`
      )
      resetForm()
      onSuccess?.()
    },
    onError: (error: unknown) => {
      const msg = error instanceof Error ? error.message : 'Failed to create voucher'
      toast.error(msg)
    },
  })

  const validate = (): boolean => {
    const errs: Record<string, string> = {}
    if (!clientName.trim()) errs.clientName = 'Required'
    if (!contractNumber.trim()) errs.contractNumber = 'Required'
    const vin = carVin.trim().toUpperCase()
    if (!/^[A-Z0-9]{17}$/.test(vin)) errs.carVin = 'VIN must be exactly 17 alphanumeric characters'
    if (clientEmail.trim() && !clientEmail.includes('@')) errs.clientEmail = 'Please enter a valid email'

    if (voucherType === 'value' && (!valueLei || parseFloat(valueLei) <= 0))
      errs.valueLei = 'Value must be greater than 0'
    if (voucherType === 'accessory_discount_code' && !discountCode.trim())
      errs.discountCode = 'Discount code is required'
    if (voucherType === 'accessory_percentage') {
      const pct = parseFloat(discountPercentage)
      if (isNaN(pct) || pct <= 0 || pct > 100)
        errs.discountPercentage = 'Must be between 0 and 100'
    }
    if (voucherType === 'service_items' && selectedServices.length === 0)
      errs.serviceItems = 'At least one service item is required'

    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSubmit = () => {
    if (!validate()) return

    const payload: VoucherCreatePayload = {
      client_name: clientName.trim(),
      contract_number: contractNumber.trim(),
      car_vin: carVin.trim().toUpperCase(),
      validity_months: parseInt(validityMonths),
      voucher_type: voucherType,
    }

    if (voucherType === 'value') payload.value_lei = parseFloat(valueLei)
    if (voucherType === 'accessory_discount_code') payload.discount_code = discountCode.trim()
    if (voucherType === 'accessory_percentage')
      payload.discount_percentage = parseFloat(discountPercentage)
    if (voucherType === 'service_items')
      payload.service_items = selectedServices.map((s) => s.name)

    if (clientCif.trim()) payload.client_cif = clientCif.trim()
    if (clientEmail.trim()) payload.client_email = clientEmail.trim()
    if (startDate) payload.start_date = startDate
    if (approverUserId) payload.approver_user_id = parseInt(approverUserId)
    if (notes.trim()) payload.notes = notes.trim()

    submitMutation.mutate(payload)
  }

  return (
    <div className="space-y-4">
      {/* Company (read-only) */}
      <div className="grid gap-1.5">
        <Label>Company</Label>
        <Input value={userCompany} disabled />
      </div>

      {/* Department (informational) */}
      <div className="grid gap-1.5">
        <Label>Department</Label>
        <Select value={department} onValueChange={setDepartment}>
          <SelectTrigger>
            <SelectValue placeholder="Select department..." />
          </SelectTrigger>
          <SelectContent>
            {departments.map((dept) => (
              <SelectItem key={dept} value={dept}>{dept}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* CRM Client Search */}
      <div className="grid gap-1.5">
        <Label>Search CRM Client</Label>
        <p className="text-xs text-muted-foreground">Search by client name or CIF — autofills the fields below</p>
        <div className="relative">
          <div className="relative">
            <Input
              value={clientSearch}
              onChange={(e) => { setClientSearch(e.target.value); if (!e.target.value) setShowClientResults(false) }}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); triggerClientSearch() } }}
              placeholder="Search by name or CIF..."
              className="pr-10"
            />
            <button
              type="button"
              className="absolute right-0 top-0 h-full px-3 text-muted-foreground hover:text-foreground transition-colors"
              onClick={triggerClientSearch}
              tabIndex={-1}
            >
              <Search className="h-4 w-4" />
            </button>
          </div>
          {showClientResults && activeClientSearch.length >= 2 && clientResults.length > 0 && (
            <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-lg max-h-60 overflow-y-auto">
              {clientResults.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className="flex w-full flex-col px-3 py-2 text-left text-sm hover:bg-accent"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => selectClient(c.id, c.display_name, c.nr_reg)}
                >
                  <span className="font-medium">{c.display_name}</span>
                  <span className="text-xs text-muted-foreground">
                    {[c.nr_reg && `CIF: ${c.nr_reg}`, c.client_type, c.city].filter(Boolean).join(' • ')}
                  </span>
                </button>
              ))}
            </div>
          )}
          {showClientResults && activeClientSearch.length >= 2 && clientResults.length === 0 && (
            <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-lg p-3 text-sm text-muted-foreground">
              No clients found
            </div>
          )}
        </div>
      </div>

      {/* Client Name */}
      <div className="grid gap-1.5">
        <Label htmlFor="clientName">Client Name *</Label>
        <Input
          id="clientName"
          value={clientName}
          onChange={(e) => setClientName(e.target.value)}
          placeholder="Client name"
        />
        {errors.clientName && <p className="text-sm text-red-500">{errors.clientName}</p>}
      </div>

      {/* CIF / CUI */}
      <div className="grid gap-1.5">
        <Label htmlFor="clientCif">CIF / CUI</Label>
        <Input
          id="clientCif"
          value={clientCif}
          onChange={(e) => setClientCif(e.target.value)}
          placeholder="CIF / CUI"
        />
      </div>

      {/* Client Email */}
      <div className="grid gap-1.5">
        <Label htmlFor="clientEmail">Client Email</Label>
        <Input
          id="clientEmail"
          type="email"
          value={clientEmail}
          onChange={(e) => setClientEmail(e.target.value)}
          placeholder="client@email.com"
        />
        {errors.clientEmail && <p className="text-sm text-red-500">{errors.clientEmail}</p>}
      </div>

      {/* Contract Number */}
      <div className="grid gap-1.5">
        <Label htmlFor="contractNumber">Contract Number *</Label>
        <Input
          id="contractNumber"
          value={contractNumber}
          onChange={(e) => setContractNumber(e.target.value)}
          placeholder="Contract number"
        />
        {errors.contractNumber && <p className="text-sm text-red-500">{errors.contractNumber}</p>}
      </div>

      {/* Car VIN */}
      <div className="grid gap-1.5">
        <Label htmlFor="carVin">Car VIN *</Label>
        <Input
          id="carVin"
          value={carVin}
          onChange={(e) => setCarVin(e.target.value.toUpperCase())}
          placeholder="17-character VIN"
          maxLength={17}
        />
        {errors.carVin && <p className="text-sm text-red-500">{errors.carVin}</p>}
      </div>

      {/* Validity */}
      <div className="grid gap-1.5">
        <Label>Validity *</Label>
        <Select value={validityMonths} onValueChange={setValidityMonths}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {VALIDITY_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Voucher Type */}
      <div className="grid gap-1.5">
        <Label>Voucher Type *</Label>
        <RadioGroup
          value={voucherType}
          onValueChange={setVoucherType}
          className="grid grid-cols-2 gap-2"
        >
          {TYPE_OPTIONS.map((o) => (
            <div key={o.value} className="flex items-center space-x-2">
              <RadioGroupItem value={o.value} id={`type-${o.value}`} />
              <Label htmlFor={`type-${o.value}`} className="font-normal">{o.label}</Label>
            </div>
          ))}
        </RadioGroup>
      </div>

      {/* Conditional Fields */}
      {voucherType === 'value' && (
        <div className="grid gap-1.5">
          <Label htmlFor="valueLei">Value (LEI) *</Label>
          <Input
            id="valueLei"
            type="number"
            min="0"
            step="0.01"
            value={valueLei}
            onChange={(e) => setValueLei(e.target.value)}
            placeholder="0.00"
          />
          {errors.valueLei && <p className="text-sm text-red-500">{errors.valueLei}</p>}
        </div>
      )}

      {voucherType === 'accessory_discount_code' && (
        <div className="grid gap-1.5">
          <Label htmlFor="discountCode">Discount Code *</Label>
          <Input
            id="discountCode"
            value={discountCode}
            onChange={(e) => setDiscountCode(e.target.value)}
            placeholder="e.g. SUMMER2026"
          />
          {errors.discountCode && <p className="text-sm text-red-500">{errors.discountCode}</p>}
        </div>
      )}

      {voucherType === 'accessory_percentage' && (
        <div className="grid gap-1.5">
          <Label htmlFor="discountPercentage">Discount Percentage *</Label>
          <Input
            id="discountPercentage"
            type="number"
            min="0"
            max="100"
            step="0.01"
            value={discountPercentage}
            onChange={(e) => setDiscountPercentage(e.target.value)}
            placeholder="0 - 100"
          />
          {errors.discountPercentage && <p className="text-sm text-red-500">{errors.discountPercentage}</p>}
        </div>
      )}

      {voucherType === 'service_items' && (
        <div className="grid gap-1.5">
          <Label>Service Items *</Label>
          <div className="space-y-1 rounded-md border p-3">
            {serviceCatalog.length === 0 && (
              <p className="text-sm text-muted-foreground">No services configured for your company</p>
            )}
            {serviceCatalog.map((svc) => (
              <div key={svc.id} className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <Checkbox
                    id={`svc-${svc.id}`}
                    checked={selectedServiceIds.has(svc.id)}
                    onCheckedChange={(isChecked) => toggleService(svc, !!isChecked)}
                  />
                  <Label htmlFor={`svc-${svc.id}`} className="font-normal">{svc.name}</Label>
                </div>
                <span className="text-sm text-muted-foreground">{svc.price} {svc.currency}</span>
              </div>
            ))}
            {selectedServices.length > 0 && (
              <div className="pt-2 border-t flex justify-between font-medium text-sm">
                <span>Total</span>
                <span>{servicesTotal.toLocaleString('ro-RO')} LEI</span>
              </div>
            )}
          </div>
          {errors.serviceItems && <p className="text-sm text-red-500">{errors.serviceItems}</p>}
        </div>
      )}

      {/* Notes */}
      <div className="grid gap-1.5">
        <Label htmlFor="notes">Notes</Label>
        <Textarea
          id="notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Optional notes"
        />
      </div>

      {/* Starting Date */}
      <div className="grid gap-1.5">
        <Label htmlFor="startDate">Starting Date</Label>
        <Input
          id="startDate"
          type="date"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
        />
      </div>

      {/* Approver (searchable) */}
      <div className="grid gap-1.5">
        <Label>Send for Approval to</Label>
        <Popover open={approverOpen} onOpenChange={(v) => { setApproverOpen(v); if (v) setTimeout(() => approverInputRef.current?.focus(), 0) }}>
          <PopoverTrigger asChild>
            <Button variant="outline" role="combobox" aria-expanded={approverOpen} className="w-full justify-between font-normal">
              {selectedApprover ? selectedApprover.name : 'Direct manager'}
              <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
            <div className="p-2 border-b">
              <Input
                ref={approverInputRef}
                placeholder="Search user..."
                value={approverSearch}
                onChange={(e) => setApproverSearch(e.target.value)}
                className="h-8"
              />
            </div>
            <div className="max-h-60 overflow-y-auto p-1">
              <button
                type="button"
                className={cn(
                  'flex w-full items-center rounded-sm px-2 py-1.5 text-sm hover:bg-accent cursor-pointer',
                  !approverUserId && 'bg-accent',
                )}
                onClick={() => { setApproverUserId(''); setApproverOpen(false); setApproverSearch('') }}
              >
                <Check className={cn('mr-2 h-4 w-4', approverUserId ? 'opacity-0' : 'opacity-100')} />
                Direct manager
              </button>
              {filteredUsers.map((u) => (
                <button
                  type="button"
                  key={u.id}
                  className={cn(
                    'flex w-full items-center rounded-sm px-2 py-1.5 text-sm hover:bg-accent cursor-pointer',
                    approverUserId === String(u.id) && 'bg-accent',
                  )}
                  onClick={() => { setApproverUserId(String(u.id)); setApproverOpen(false); setApproverSearch('') }}
                >
                  <Check className={cn('mr-2 h-4 w-4', approverUserId === String(u.id) ? 'opacity-100' : 'opacity-0')} />
                  {u.name}
                </button>
              ))}
              {filteredUsers.length === 0 && (
                <p className="py-4 text-center text-sm text-muted-foreground">No users found</p>
              )}
            </div>
          </PopoverContent>
        </Popover>
      </div>

      {/* Submit */}
      <Button
        onClick={handleSubmit}
        disabled={submitMutation.isPending}
        className="w-full"
      >
        {submitMutation.isPending ? 'Creating...' : 'Issue Voucher'}
      </Button>
    </div>
  )
}
