import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ArrowLeft } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { vouchersApi } from '@/api/vouchers'
import { usersApi } from '@/api/users'
import type { VoucherCreatePayload } from '@/types/vouchers'

const VALIDITY_OPTIONS = [
  { value: '1', label: '1 month' },
  { value: '3', label: '3 months' },
  { value: '6', label: '6 months' },
  { value: '12', label: '12 months' },
  { value: '24', label: '24 months' },
]

const TYPE_OPTIONS = [
  { value: 'value', label: 'Value (LEI)' },
  { value: 'accessory_discount_code', label: 'Accessory Discount Code' },
  { value: 'accessory_percentage', label: 'Accessory Percentage' },
  { value: 'service_items', label: 'Service Items' },
]

export default function NewVoucher() {
  const navigate = useNavigate()

  const [clientName, setClientName] = useState('')
  const [contractNumber, setContractNumber] = useState('')
  const [carVin, setCarVin] = useState('')
  const [validityMonths, setValidityMonths] = useState('12')
  const [voucherType, setVoucherType] = useState('value')
  const [valueLei, setValueLei] = useState('')
  const [discountCode, setDiscountCode] = useState('')
  const [discountPercentage, setDiscountPercentage] = useState('')
  const [serviceItems, setServiceItems] = useState('')
  const [approverUserId, setApproverUserId] = useState('__none__')
  const [notes, setNotes] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})

  const { data: users = [] } = useQuery({
    queryKey: ['users-list'],
    queryFn: () => usersApi.getUsers(),
    staleTime: 10 * 60_000,
  })

  const submitMutation = useMutation({
    mutationFn: (payload: VoucherCreatePayload) => vouchersApi.create(payload),
    onSuccess: (result) => {
      toast.success(
        `Voucher ${result.voucher.voucher_code} created — pending approval from ${result.voucher.approver_name}`
      )
      navigate('/app/accounting/vouchers')
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

    if (voucherType === 'value' && (!valueLei || parseFloat(valueLei) <= 0))
      errs.valueLei = 'Value must be greater than 0'
    if (voucherType === 'accessory_discount_code' && !discountCode.trim())
      errs.discountCode = 'Discount code is required'
    if (voucherType === 'accessory_percentage') {
      const pct = parseFloat(discountPercentage)
      if (isNaN(pct) || pct <= 0 || pct > 100)
        errs.discountPercentage = 'Must be between 0 and 100'
    }
    if (voucherType === 'service_items' && !serviceItems.trim())
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
      payload.service_items = serviceItems
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)

    if (approverUserId !== '__none__') payload.approver_user_id = parseInt(approverUserId)
    if (notes.trim()) payload.notes = notes.trim()

    submitMutation.mutate(payload)
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate(-1)}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h1 className="text-2xl font-bold">Issue Voucher</h1>
      </div>

      <div className="space-y-4 rounded-lg border p-6">
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

        {/* Contract Number */}
        <div className="grid gap-1.5">
          <Label htmlFor="contractNumber">Contract Number *</Label>
          <Input
            id="contractNumber"
            value={contractNumber}
            onChange={(e) => setContractNumber(e.target.value)}
            placeholder="Contract number"
          />
          {errors.contractNumber && (
            <p className="text-sm text-red-500">{errors.contractNumber}</p>
          )}
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
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
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
                <Label htmlFor={`type-${o.value}`} className="font-normal">
                  {o.label}
                </Label>
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
            {errors.discountPercentage && (
              <p className="text-sm text-red-500">{errors.discountPercentage}</p>
            )}
          </div>
        )}

        {voucherType === 'service_items' && (
          <div className="grid gap-1.5">
            <Label htmlFor="serviceItems">Service Items * (comma-separated)</Label>
            <Input
              id="serviceItems"
              value={serviceItems}
              onChange={(e) => setServiceItems(e.target.value)}
              placeholder="Oil change, Tire rotation, Brake inspection"
            />
            {errors.serviceItems && <p className="text-sm text-red-500">{errors.serviceItems}</p>}
          </div>
        )}

        {/* Approver Override */}
        <div className="grid gap-1.5">
          <Label>Approver (optional — leave empty for direct manager)</Label>
          <Select value={approverUserId} onValueChange={setApproverUserId}>
            <SelectTrigger>
              <SelectValue placeholder="Direct manager" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">Direct manager</SelectItem>
              {users.map((u) => (
                <SelectItem key={u.id} value={String(u.id)}>
                  {u.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

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

        {/* Submit */}
        <Button
          onClick={handleSubmit}
          disabled={submitMutation.isPending}
          className="w-full"
        >
          {submitMutation.isPending ? 'Creating...' : 'Issue Voucher'}
        </Button>
      </div>
    </div>
  )
}
