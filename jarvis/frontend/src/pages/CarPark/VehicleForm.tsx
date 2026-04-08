import { useState, useEffect, useMemo } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Save, Loader2, Search, Check, X } from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { SearchSelect } from '@/components/shared/SearchSelect'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
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
import { Separator } from '@/components/ui/separator'
import { carparkApi } from '@/api/carpark'
import { toast } from 'sonner'
import {
  CATEGORY_LABELS,
  type Vehicle,
  type VehicleCategory,
  type VINDecodeResult,
} from '@/types/carpark'
import {
  AUTOVIT_BRANDS,
  AUTOVIT_MODELS,
  AUTOVIT_BODY_TYPES,
  AUTOVIT_FUEL_TYPES,
  AUTOVIT_GEARBOX_TYPES,
  AUTOVIT_DRIVE_TYPES,
  AUTOVIT_COLORS,
  AUTOVIT_INTERIOR_COLORS,
  AUTOVIT_EURO_STANDARDS,
  AUTOVIT_VEHICLE_STATES,
  AUTOVIT_DOORS,
  AUTOVIT_SEATS,
} from '@/data/autovitData'

type FormData = Record<string, string | number | boolean | null>

/** Safely extract a numeric/string value for <Input value=...> (excludes boolean) */
function inputVal(v: string | number | boolean | null | undefined): string | number {
  if (v == null || typeof v === 'boolean') return ''
  return v
}

const CATEGORIES: VehicleCategory[] = ['NEW', 'ORD', 'SH', 'TD', 'CUS', 'SHR', 'DSP', 'CON', 'TI']

// ── Form field components ──────────────────────────────────
function TextField({
  label,
  name,
  value,
  onChange,
  type = 'text',
  placeholder,
  required,
}: {
  label: string
  name: string
  value: string | number | boolean | null
  onChange: (name: string, value: string) => void
  type?: string
  placeholder?: string
  required?: boolean
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={name}>
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </Label>
      <Input
        id={name}
        type={type}
        value={value != null ? String(value) : ''}
        onChange={(e) => onChange(name, e.target.value)}
        placeholder={placeholder}
      />
    </div>
  )
}

function SelectField({
  label,
  name,
  value,
  options,
  onChange,
  required,
}: {
  label: string
  name: string
  value: string | null
  options: { value: string; label: string }[]
  onChange: (name: string, value: string) => void
  required?: boolean
}) {
  return (
    <div className="space-y-1.5">
      <Label>
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </Label>
      <Select value={value ?? ''} onValueChange={(v) => onChange(name, v)}>
        <SelectTrigger>
          <SelectValue placeholder={`Select ${label.toLowerCase()}`} />
        </SelectTrigger>
        <SelectContent>
          {options.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

function SearchSelectField({
  label,
  name,
  value,
  options,
  onChange,
  required,
  placeholder,
  searchPlaceholder,
  allowCustom,
  disabled,
}: {
  label: string
  name: string
  value: string | null
  options: { value: string; label: string }[]
  onChange: (name: string, value: string) => void
  required?: boolean
  placeholder?: string
  searchPlaceholder?: string
  allowCustom?: boolean
  disabled?: boolean
}) {
  return (
    <div className="space-y-1.5">
      <Label>
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </Label>
      <SearchSelect
        value={value ?? ''}
        onValueChange={(v) => onChange(name, v)}
        options={options}
        placeholder={placeholder ?? `Select ${label.toLowerCase()}`}
        searchPlaceholder={searchPlaceholder ?? `Search ${label.toLowerCase()}...`}
        allowCustom={allowCustom}
        disabled={disabled}
      />
    </div>
  )
}

function CheckboxField({
  label,
  name,
  checked,
  onChange,
}: {
  label: string
  name: string
  checked: boolean
  onChange: (name: string, value: boolean) => void
}) {
  return (
    <div className="flex items-center gap-2">
      <Checkbox
        id={name}
        checked={checked}
        onCheckedChange={(v) => onChange(name, !!v)}
      />
      <Label htmlFor={name} className="text-sm font-normal cursor-pointer">
        {label}
      </Label>
    </div>
  )
}

// ── Build options ──────────────────────────────────────────
const brandOptions = AUTOVIT_BRANDS.map((b) => ({ value: b, label: b }))

// ── Main Form ──────────────────────────────────────────────
export default function VehicleForm() {
  const { vehicleId } = useParams<{ vehicleId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const isEdit = vehicleId && vehicleId !== 'new'
  const id = isEdit ? Number(vehicleId) : null

  // Load existing vehicle for edit
  const { data: existingData, isLoading: isLoadingVehicle } = useQuery({
    queryKey: ['carpark', 'vehicle', id],
    queryFn: () => carparkApi.getVehicle(id!),
    enabled: !!id,
  })

  // Load locations for dropdown
  const { data: locationsData } = useQuery({
    queryKey: ['carpark', 'locations'],
    queryFn: () => carparkApi.getLocations(),
    staleTime: 5 * 60_000,
  })

  const [form, setForm] = useState<FormData>({
    vin: '',
    nr_stoc: '',
    brand: '',
    model: '',
    variant: '',
    generation: '',
    equipment_level: '',
    category: 'SH',
    state: 'Rulat',
    year_of_manufacture: null,
    fuel_type: '',
    transmission: '',
    body_type: '',
    mileage_km: 0,
    engine_power_hp: null,
    engine_displacement_cc: null,
    drive_type: '',
    color_exterior: '',
    color_interior: '',
    doors: null,
    seats: null,
    euro_standard: '',
    co2_emissions: null,
    current_price: null,
    list_price: null,
    minimum_price: null,
    price_currency: 'EUR',
    price_includes_vat: true,
    is_negotiable: true,
    margin_scheme: false,
    eligible_for_financing: true,
    purchase_price_net: null,
    purchase_price_currency: 'EUR',
    acquisition_value: null,
    acquisition_currency: 'EUR',
    reconditioning_cost: null,
    transport_cost: null,
    registration_cost: null,
    other_costs: null,
    location_id: null,
    parking_spot: '',
    source: '',
    supplier_name: '',
    supplier_cif: '',
    has_manufacturer_warranty: false,
    manufacturer_warranty_date: '',
    has_dealer_warranty: false,
    dealer_warranty_months: null,
    is_first_owner: false,
    has_accident_history: false,
    has_service_book: false,
    has_tuning: false,
    is_registered: false,
    first_registration_date: '',
    notes: '',
    internal_notes: '',
    listing_title: '',
    listing_description: '',
  })

  // Populate form when editing
  useEffect(() => {
    if (existingData?.vehicle) {
      const v = existingData.vehicle
      const populated: FormData = {}
      for (const key of Object.keys(form)) {
        if (key in v) {
          populated[key] = (v as unknown as Record<string, string | number | boolean | null>)[key]
        }
      }
      setForm((prev) => ({ ...prev, ...populated }))
    }
    // Only run when existingData changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existingData])

  // Model options based on selected brand
  const modelOptions = useMemo(() => {
    const brand = form.brand as string
    if (!brand) return []
    const models = AUTOVIT_MODELS[brand] ?? []
    return models.map((m) => ({ value: m, label: m }))
  }, [form.brand])

  // VIN decoder
  const [isDecoding, setIsDecoding] = useState(false)
  const [decodeResult, setDecodeResult] = useState<VINDecodeResult | null>(null)

  const handleDecodeVIN = async () => {
    const vin = (form.vin as string)?.trim().toUpperCase()
    if (!vin || vin.length !== 17) {
      toast.error('Enter a valid 17-character VIN to decode')
      return
    }
    setIsDecoding(true)
    try {
      const result = await carparkApi.decodeVIN(vin)
      if (result.success && result.data) {
        setDecodeResult(result.data)
        toast.success(
          `VIN decoded via ${result.data.provider} (${Math.round(result.data.confidence * 100)}% confidence)`,
        )
      } else {
        toast.error((result as any).error || 'Could not decode VIN')
      }
    } catch (err: any) {
      const msg = err?.data?.error || 'VIN decode failed'
      toast.error(msg)
    } finally {
      setIsDecoding(false)
    }
  }

  const applyDecodedFields = () => {
    if (!decodeResult?.vehicle_fields) return
    // Filter to only simple values compatible with FormData type
    const fields: FormData = {}
    for (const [k, v] of Object.entries(decodeResult.vehicle_fields)) {
      if (v === null || typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') {
        fields[k] = v
      }
    }
    setForm((prev) => ({ ...prev, ...fields }))
    setDecodeResult(null)
    toast.success('Vehicle specs applied from VIN decode')
  }

  // VIN duplicate check
  const [vinError, setVinError] = useState<string | null>(null)
  const checkVinDuplicate = async (vin: string) => {
    if (vin.length < 5) {
      setVinError(null)
      return
    }
    try {
      const result = await carparkApi.checkVin(vin)
      if (result.exists && result.vehicle_id !== id) {
        setVinError(`VIN already exists (Vehicle #${result.vehicle_id})`)
      } else {
        setVinError(null)
      }
    } catch {
      // ignore
    }
  }

  const handleChange = (name: string, value: string | number | boolean) => {
    setForm((prev) => {
      const next = { ...prev, [name]: value }
      // Clear model when brand changes
      if (name === 'brand' && prev.brand !== value) {
        next.model = ''
      }
      return next
    })
    if (name === 'vin') {
      checkVinDuplicate(value as string)
    }
  }

  const handleNumericChange = (name: string, value: string) => {
    const num = value === '' ? null : Number(value)
    setForm((prev) => ({ ...prev, [name]: num }))
  }

  // Submit
  const createMutation = useMutation({
    mutationFn: (data: Partial<Vehicle>) => carparkApi.createVehicle(data),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['carpark'] })
      toast.success('Vehicle created')
      navigate(`/app/carpark/${result.vehicle.id}`)
    },
    onError: (err: Error & { data?: { error?: string } }) => {
      toast.error((err as any).data?.error || 'Failed to create vehicle')
    },
  })

  const updateMutation = useMutation({
    mutationFn: (data: Partial<Vehicle>) => carparkApi.updateVehicle(id!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark'] })
      toast.success('Vehicle updated')
      navigate(`/app/carpark/${id}`)
    },
    onError: (err: Error & { data?: { error?: string } }) => {
      toast.error((err as any).data?.error || 'Failed to update vehicle')
    },
  })

  const isPending = createMutation.isPending || updateMutation.isPending

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    // Validation
    if (!form.vin || (form.vin as string).length < 5) {
      toast.error('VIN is required (min 5 characters)')
      return
    }
    if (!form.brand) {
      toast.error('Brand is required')
      return
    }
    if (!form.model) {
      toast.error('Model is required')
      return
    }
    if (vinError) {
      toast.error('Please resolve the VIN duplicate error')
      return
    }

    // Clean empty strings -> null
    const payload: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(form)) {
      if (v === '') {
        payload[k] = null
      } else {
        payload[k] = v
      }
    }

    if (isEdit) {
      updateMutation.mutate(payload as Partial<Vehicle>)
    } else {
      createMutation.mutate(payload as Partial<Vehicle>)
    }
  }

  if (isEdit && isLoadingVehicle) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const locationOptions = (locationsData?.locations ?? []).map((l) => ({
    value: String(l.id),
    label: `${l.name} (${l.code})`,
  }))

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <PageHeader
        title={isEdit ? 'Edit Vehicle' : 'New Vehicle'}
        breadcrumbs={[
          { label: 'CarPark', href: '/app/carpark' },
          ...(isEdit && existingData?.vehicle
            ? [{ label: `${existingData.vehicle.brand} ${existingData.vehicle.model}`, href: `/app/carpark/${id}` }]
            : []),
          { label: isEdit ? 'Edit' : 'New Vehicle' },
        ]}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" type="button" asChild>
              <Link to={isEdit ? `/app/carpark/${id}` : '/app/carpark'}>
                Cancel
              </Link>
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              ) : (
                <Save className="mr-1 h-4 w-4" />
              )}
              {isEdit ? 'Save Changes' : 'Create Vehicle'}
            </Button>
          </div>
        }
      />

      {/* Identification */}
      <Card className="p-4 space-y-4">
        <h3 className="text-sm font-semibold">Identification</h3>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor="vin">
              VIN <span className="text-red-500">*</span>
            </Label>
            <div className="flex gap-2">
              <Input
                id="vin"
                value={(form.vin as string) ?? ''}
                onChange={(e) => handleChange('vin', e.target.value.toUpperCase())}
                placeholder="e.g. WBAPH5C55BA123456"
                className={vinError ? 'border-red-500' : ''}
              />
              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={handleDecodeVIN}
                disabled={isDecoding || !form.vin || (form.vin as string).length !== 17}
                title="Decode VIN"
              >
                {isDecoding ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Search className="h-4 w-4" />
                )}
              </Button>
            </div>
            {vinError && <p className="text-xs text-red-500">{vinError}</p>}
            {decodeResult && (
              <div className="mt-2 rounded-md border border-blue-200 bg-blue-50 p-3 dark:border-blue-800 dark:bg-blue-950">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium">
                    {decodeResult.specs.brand} {decodeResult.specs.model}
                    {decodeResult.specs.model_year ? ` (${decodeResult.specs.model_year})` : ''}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {decodeResult.provider} &middot; {Math.round(decodeResult.confidence * 100)}%
                  </span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-1 text-xs text-muted-foreground mb-2">
                  {decodeResult.specs.fuel_type && <span>Fuel: {decodeResult.specs.fuel_type}</span>}
                  {decodeResult.specs.engine_power_hp > 0 && <span>Power: {decodeResult.specs.engine_power_hp} HP</span>}
                  {decodeResult.specs.engine_displacement_cc > 0 && <span>Engine: {decodeResult.specs.engine_displacement_cc} cc</span>}
                  {decodeResult.specs.transmission && <span>Trans: {decodeResult.specs.transmission}</span>}
                  {decodeResult.specs.body_type && <span>Body: {decodeResult.specs.body_type}</span>}
                  {decodeResult.specs.drive_type && <span>Drive: {decodeResult.specs.drive_type}</span>}
                </div>
                <div className="flex gap-2">
                  <Button type="button" size="sm" onClick={applyDecodedFields}>
                    <Check className="mr-1 h-3 w-3" />
                    Apply to Vehicle
                  </Button>
                  <Button type="button" size="sm" variant="ghost" onClick={() => setDecodeResult(null)}>
                    <X className="mr-1 h-3 w-3" />
                    Dismiss
                  </Button>
                </div>
              </div>
            )}
          </div>
          <TextField label="Stock Number" name="nr_stoc" value={form.nr_stoc as string} onChange={handleChange} />
          <SelectField
            label="Category"
            name="category"
            value={form.category as string}
            options={CATEGORIES.map((c) => ({ value: c, label: CATEGORY_LABELS[c] }))}
            onChange={handleChange}
            required
          />
        </div>
        <div className="grid gap-4 md:grid-cols-4">
          <SearchSelectField
            label="Brand"
            name="brand"
            value={form.brand as string}
            options={brandOptions}
            onChange={handleChange}
            required
            placeholder="Select brand"
            searchPlaceholder="Search brand..."
            allowCustom
          />
          <SearchSelectField
            label="Model"
            name="model"
            value={form.model as string}
            options={modelOptions}
            onChange={handleChange}
            required
            placeholder={form.brand ? 'Select model' : 'Select brand first'}
            searchPlaceholder="Search model..."
            allowCustom
            disabled={!form.brand}
          />
          <TextField label="Variant" name="variant" value={form.variant as string} onChange={handleChange} placeholder="e.g. xDrive40i" />
          <SelectField
            label="State"
            name="state"
            value={form.state as string}
            options={[...AUTOVIT_VEHICLE_STATES]}
            onChange={handleChange}
          />
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <TextField label="Generation" name="generation" value={form.generation as string} onChange={handleChange} placeholder="e.g. G05 (LCI)" />
          <TextField label="Equipment Level" name="equipment_level" value={form.equipment_level as string} onChange={handleChange} placeholder="e.g. M Sport, Inscription" />
          <TextField label="First Registration" name="first_registration_date" value={form.first_registration_date as string} onChange={handleChange} type="date" />
        </div>
      </Card>

      {/* Technical */}
      <Card className="p-4 space-y-4">
        <h3 className="text-sm font-semibold">Technical Specs</h3>
        <div className="grid gap-4 md:grid-cols-4">
          <div className="space-y-1.5">
            <Label>Year</Label>
            <Input
              type="number"
              value={inputVal(form.year_of_manufacture)}
              onChange={(e) => handleNumericChange('year_of_manufacture', e.target.value)}
              placeholder="2024"
            />
          </div>
          <SearchSelectField
            label="Fuel Type"
            name="fuel_type"
            value={form.fuel_type as string}
            options={[...AUTOVIT_FUEL_TYPES]}
            onChange={handleChange}
            searchPlaceholder="Search fuel type..."
          />
          <SearchSelectField
            label="Transmission"
            name="transmission"
            value={form.transmission as string}
            options={[...AUTOVIT_GEARBOX_TYPES]}
            onChange={handleChange}
            searchPlaceholder="Search gearbox..."
          />
          <SearchSelectField
            label="Body Type"
            name="body_type"
            value={form.body_type as string}
            options={[...AUTOVIT_BODY_TYPES]}
            onChange={handleChange}
            searchPlaceholder="Search body type..."
          />
        </div>
        <div className="grid gap-4 md:grid-cols-4">
          <div className="space-y-1.5">
            <Label>Mileage (km)</Label>
            <Input
              type="number"
              value={inputVal(form.mileage_km)}
              onChange={(e) => handleNumericChange('mileage_km', e.target.value)}
              placeholder="0"
            />
          </div>
          <div className="space-y-1.5">
            <Label>Power (HP)</Label>
            <Input
              type="number"
              value={inputVal(form.engine_power_hp)}
              onChange={(e) => handleNumericChange('engine_power_hp', e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Engine (cc)</Label>
            <Input
              type="number"
              value={inputVal(form.engine_displacement_cc)}
              onChange={(e) => handleNumericChange('engine_displacement_cc', e.target.value)}
            />
          </div>
          <SearchSelectField
            label="Drive Type"
            name="drive_type"
            value={form.drive_type as string}
            options={[...AUTOVIT_DRIVE_TYPES]}
            onChange={handleChange}
            searchPlaceholder="Search drive type..."
          />
        </div>
        <div className="grid gap-4 md:grid-cols-4">
          <SearchSelectField
            label="Exterior Color"
            name="color_exterior"
            value={form.color_exterior as string}
            options={[...AUTOVIT_COLORS]}
            onChange={handleChange}
            searchPlaceholder="Search color..."
          />
          <SearchSelectField
            label="Interior Color"
            name="color_interior"
            value={form.color_interior as string}
            options={[...AUTOVIT_INTERIOR_COLORS]}
            onChange={handleChange}
            searchPlaceholder="Search color..."
          />
          <SelectField
            label="Doors"
            name="doors"
            value={form.doors != null ? String(form.doors) : ''}
            options={[...AUTOVIT_DOORS]}
            onChange={(n, v) => handleNumericChange(n, v)}
          />
          <SelectField
            label="Seats"
            name="seats"
            value={form.seats != null ? String(form.seats) : ''}
            options={[...AUTOVIT_SEATS]}
            onChange={(n, v) => handleNumericChange(n, v)}
          />
        </div>
        <div className="grid gap-4 md:grid-cols-4">
          <SearchSelectField
            label="Euro Standard"
            name="euro_standard"
            value={form.euro_standard as string}
            options={[...AUTOVIT_EURO_STANDARDS]}
            onChange={handleChange}
            searchPlaceholder="Search euro..."
          />
          <div className="space-y-1.5">
            <Label>CO2 Emissions (g/km)</Label>
            <Input
              type="number"
              value={inputVal(form.co2_emissions)}
              onChange={(e) => handleNumericChange('co2_emissions', e.target.value)}
            />
          </div>
        </div>
      </Card>

      {/* Pricing */}
      <Card className="p-4 space-y-4">
        <h3 className="text-sm font-semibold">Pricing</h3>
        <div className="grid gap-4 md:grid-cols-4">
          <div className="space-y-1.5">
            <Label>Current Price</Label>
            <Input
              type="number"
              step="0.01"
              value={inputVal(form.current_price)}
              onChange={(e) => handleNumericChange('current_price', e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label>List Price</Label>
            <Input
              type="number"
              step="0.01"
              value={inputVal(form.list_price)}
              onChange={(e) => handleNumericChange('list_price', e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Minimum Price</Label>
            <Input
              type="number"
              step="0.01"
              value={inputVal(form.minimum_price)}
              onChange={(e) => handleNumericChange('minimum_price', e.target.value)}
            />
          </div>
          <SelectField
            label="Currency"
            name="price_currency"
            value={form.price_currency as string}
            options={[
              { value: 'EUR', label: 'EUR' },
              { value: 'RON', label: 'RON' },
              { value: 'USD', label: 'USD' },
            ]}
            onChange={handleChange}
          />
        </div>
        <div className="flex flex-wrap gap-6">
          <CheckboxField label="Price includes VAT" name="price_includes_vat" checked={!!form.price_includes_vat} onChange={handleChange} />
          <CheckboxField label="Negotiable" name="is_negotiable" checked={!!form.is_negotiable} onChange={handleChange} />
          <CheckboxField label="Margin scheme" name="margin_scheme" checked={!!form.margin_scheme} onChange={handleChange} />
          <CheckboxField label="Eligible for financing" name="eligible_for_financing" checked={!!form.eligible_for_financing} onChange={handleChange} />
        </div>

        <Separator />
        <h4 className="text-xs font-medium text-muted-foreground">Acquisition Costs</h4>
        <div className="grid gap-4 md:grid-cols-4">
          <div className="space-y-1.5">
            <Label>Purchase Price (net)</Label>
            <Input
              type="number"
              step="0.01"
              value={inputVal(form.purchase_price_net)}
              onChange={(e) => handleNumericChange('purchase_price_net', e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Reconditioning</Label>
            <Input
              type="number"
              step="0.01"
              value={inputVal(form.reconditioning_cost)}
              onChange={(e) => handleNumericChange('reconditioning_cost', e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Transport</Label>
            <Input
              type="number"
              step="0.01"
              value={inputVal(form.transport_cost)}
              onChange={(e) => handleNumericChange('transport_cost', e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Other Costs</Label>
            <Input
              type="number"
              step="0.01"
              value={inputVal(form.other_costs)}
              onChange={(e) => handleNumericChange('other_costs', e.target.value)}
            />
          </div>
        </div>
      </Card>

      {/* Location & Source */}
      <Card className="p-4 space-y-4">
        <h3 className="text-sm font-semibold">Location & Source</h3>
        <div className="grid gap-4 md:grid-cols-3">
          <SelectField
            label="Location"
            name="location_id"
            value={form.location_id != null ? String(form.location_id) : ''}
            options={locationOptions}
            onChange={(name, value) => handleNumericChange(name, value)}
          />
          <TextField label="Parking Spot" name="parking_spot" value={form.parking_spot as string} onChange={handleChange} placeholder="e.g. A-15" />
          <TextField label="Source" name="source" value={form.source as string} onChange={handleChange} placeholder="e.g. Trade-in, Auction" />
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <TextField label="Supplier Name" name="supplier_name" value={form.supplier_name as string} onChange={handleChange} />
          <TextField label="Supplier CIF" name="supplier_cif" value={form.supplier_cif as string} onChange={handleChange} />
        </div>
      </Card>

      {/* Condition & Warranty */}
      <Card className="p-4 space-y-4">
        <h3 className="text-sm font-semibold">Condition & Warranty</h3>
        <div className="flex flex-wrap gap-6">
          <CheckboxField label="First owner" name="is_first_owner" checked={!!form.is_first_owner} onChange={handleChange} />
          <CheckboxField label="Accident history" name="has_accident_history" checked={!!form.has_accident_history} onChange={handleChange} />
          <CheckboxField label="Service book" name="has_service_book" checked={!!form.has_service_book} onChange={handleChange} />
          <CheckboxField label="Has tuning" name="has_tuning" checked={!!form.has_tuning} onChange={handleChange} />
          <CheckboxField label="Registered" name="is_registered" checked={!!form.is_registered} onChange={handleChange} />
        </div>
        <Separator />
        <div className="grid gap-4 md:grid-cols-3">
          <CheckboxField label="Manufacturer warranty" name="has_manufacturer_warranty" checked={!!form.has_manufacturer_warranty} onChange={handleChange} />
          {form.has_manufacturer_warranty && (
            <TextField label="Warranty Until" name="manufacturer_warranty_date" value={form.manufacturer_warranty_date as string} onChange={handleChange} type="date" />
          )}
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <CheckboxField label="Dealer warranty" name="has_dealer_warranty" checked={!!form.has_dealer_warranty} onChange={handleChange} />
          {form.has_dealer_warranty && (
            <div className="space-y-1.5">
              <Label>Warranty Months</Label>
              <Input
                type="number"
                value={inputVal(form.dealer_warranty_months)}
                onChange={(e) => handleNumericChange('dealer_warranty_months', e.target.value)}
              />
            </div>
          )}
        </div>
      </Card>

      {/* Listing */}
      <Card className="p-4 space-y-4">
        <h3 className="text-sm font-semibold">Listing & Notes</h3>
        <TextField label="Listing Title" name="listing_title" value={form.listing_title as string} onChange={handleChange} placeholder="Custom title for online listings" />
        <div className="space-y-1.5">
          <Label>Listing Description</Label>
          <Textarea
            value={(form.listing_description as string) ?? ''}
            onChange={(e) => handleChange('listing_description', e.target.value)}
            placeholder="Description for online platforms..."
            rows={4}
          />
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-1.5">
            <Label>Notes</Label>
            <Textarea
              value={(form.notes as string) ?? ''}
              onChange={(e) => handleChange('notes', e.target.value)}
              rows={3}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Internal Notes</Label>
            <Textarea
              value={(form.internal_notes as string) ?? ''}
              onChange={(e) => handleChange('internal_notes', e.target.value)}
              rows={3}
            />
          </div>
        </div>
      </Card>

      {/* Submit bar */}
      <div className="flex justify-end gap-2 sticky bottom-4">
        <Button variant="outline" type="button" asChild>
          <Link to={isEdit ? `/app/carpark/${id}` : '/app/carpark'}>Cancel</Link>
        </Button>
        <Button type="submit" disabled={isPending} size="lg">
          {isPending ? (
            <Loader2 className="mr-1 h-4 w-4 animate-spin" />
          ) : (
            <Save className="mr-1 h-4 w-4" />
          )}
          {isEdit ? 'Save Changes' : 'Create Vehicle'}
        </Button>
      </div>
    </form>
  )
}
