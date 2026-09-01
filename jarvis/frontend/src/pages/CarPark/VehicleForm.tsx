import { useState, useEffect, useMemo, useRef } from 'react'
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Save, Loader2, Search, Check, X, RefreshCw, Sparkles, Plus, ArrowLeft } from 'lucide-react'
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
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { carparkApi } from '@/api/carpark'
import { useAuthStore } from '@/stores/authStore'
import { useCarParkStore } from '@/stores/carParkStore'
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
  AUTOVIT_INTERIOR_MATERIALS,
  AUTOVIT_COLOR_FINISHES,
  AUTOVIT_EQUIPMENT,
  AUTOVIT_EURO_STANDARDS,
  AUTOVIT_VEHICLE_STATES,
  AUTOVIT_DOORS,
  AUTOVIT_SEATS,
  VEHICLE_SOURCES,
  CARPARK_COST_TYPES,
} from '@/data/autovitData'

type FormData = Record<string, string | number | boolean | null | string[]>
type CostLine = {
  type: string
  description: string
  date: string
  lei: number | null
  kurs: number | null
  eur: number | null
}

/** Safely extract a numeric/string value for <Input value=...> (excludes boolean) */
function inputVal(v: string | number | boolean | string[] | null | undefined): string | number {
  if (v == null || typeof v === 'boolean' || Array.isArray(v)) return ''
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

// "Date of fabrication" = Month + Year dropdowns (native <input type="month">
// renders inconsistently across browsers). Stored as manufacture_date = YYYY-MM-01.
const MONTH_OPTIONS = [
  ['01', 'January'], ['02', 'February'], ['03', 'March'], ['04', 'April'],
  ['05', 'May'], ['06', 'June'], ['07', 'July'], ['08', 'August'],
  ['09', 'September'], ['10', 'October'], ['11', 'November'], ['12', 'December'],
].map(([value, label]) => ({ value, label }))
const _fabCurrentYear = new Date().getFullYear()
const YEAR_OPTIONS = Array.from({ length: 41 }, (_, i) =>
  String(_fabCurrentYear + 1 - i),
).map((y) => ({ value: y, label: y }))

// Fuel-type → which capacity/norm fields apply (mirrors Drive Park's
// usesFuelTank / usesBattery, mapped to CarPark's AUTOVIT_FUEL_TYPES values).
const FUEL_USES_TANK = new Set(['petrol', 'diesel', 'hybrid', 'plugin-hybrid', 'mild-hybrid-petrol', 'mild-hybrid-diesel', 'petrol-lpg', 'petrol-cng', 'hydrogen'])
// Mild hybrids deliberately excluded — no battery capacity / kWh norm.
const FUEL_USES_BATTERY = new Set(['electric', 'hybrid', 'plugin-hybrid'])
const usesFuelTank = (ft?: string | null) => FUEL_USES_TANK.has(ft ?? '')
const usesBattery = (ft?: string | null) => FUEL_USES_BATTERY.has(ft ?? '')

// Compose the "Titlu anunț" from the vehicle's spec fields, e.g.
// "Dacia Duster 1.5 Blue dCi Prestige III 1.5l Diesel Manuala Fata (FWD)".
function buildListingTitle(f: FormData): string {
  const label = (opts: readonly { value: string; label: string }[], v: unknown) =>
    opts.find((o) => o.value === v)?.label ?? ''
  const cc = f.engine_displacement_cc
  const liters = typeof cc === 'number' && cc > 0 ? `${(cc / 1000).toFixed(1)}l` : ''
  return [
    f.brand, f.model, f.variant, f.generation, f.equipment_level,
    liters,
    label(AUTOVIT_FUEL_TYPES, f.fuel_type),
    label(AUTOVIT_GEARBOX_TYPES, f.transmission),
    label(AUTOVIT_DRIVE_TYPES, f.drive_type),
  ]
    .map((p) => (p == null ? '' : String(p)).trim())
    .filter(Boolean)
    .join(' ')
}

// ── Main Form ──────────────────────────────────────────────
export default function VehicleForm() {
  const { vehicleId } = useParams<{ vehicleId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const isEdit = vehicleId && vehicleId !== 'new'

  // Active tab persisted in the URL (?tab=…) so it survives a page refresh
  // and is shareable/bookmarkable.
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = searchParams.get('tab') ?? 'vehicul'
  const handleTabChange = (v: string) => {
    const next = new URLSearchParams(searchParams)
    next.set('tab', v)
    setSearchParams(next, { replace: true })
  }
  const id = isEdit ? Number(vehicleId) : null

  // Tenant switcher: new cars are created into the selected (acting) company,
  // defaulting to the user's own company. Never applied on edit.
  const user = useAuthStore((s) => s.user)
  const selectedCompanyId = useCarParkStore((s) => s.selectedCompanyId)
  const effectiveCompanyId = selectedCompanyId ?? user?.company_id ?? null

  // Load existing vehicle for edit
  const { data: existingData, isLoading: isLoadingVehicle } = useQuery({
    queryKey: ['carpark', 'vehicle', id],
    queryFn: () => carparkApi.getVehicle(id!),
    enabled: !!id,
  })
  const { data: pricingHistoryData } = useQuery({
    queryKey: ['carpark', 'pricing-history', id],
    queryFn: () => carparkApi.getPricingHistory(id!),
    enabled: !!id,
  })
  const pricingHistory = pricingHistoryData?.history ?? []

  // Load locations for dropdown (scoped to the acting company)
  const { data: locationsData } = useQuery({
    queryKey: ['carpark', 'locations', effectiveCompanyId],
    queryFn: () => carparkApi.getLocations(effectiveCompanyId),
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
    manufacture_date: '',
    fuel_type: '',
    fuel_tank_capacity_liters: null,
    battery_capacity_kwh: null,
    norma_combustibil: null,
    norma_energie: null,
    transmission: '',
    body_type: '',
    mileage_km: 0,
    engine_power_hp: null,
    engine_displacement_cc: null,
    drive_type: '',
    color_exterior: '',
    color_interior: '',
    interior_material: '',
    doors: null,
    seats: null,
    euro_standard: '',
    co2_emissions: null,
    max_weight_kg: null,
    payload_kg: null,
    cargo_volume_m3: null,
    cargo_length_mm: null,
    cargo_width_mm: null,
    cargo_height_mm: null,
    euro_pallets: null,
    current_price: null,
    list_price: null,
    promotional_price: null,
    minimum_price: null,
    price_currency: 'EUR',
    price_includes_vat: true,
    is_negotiable: true,
    margin_scheme: false,
    eligible_for_financing: true,
    purchase_price_net: null,
    purchase_price_currency: 'EUR',
    acquisition_value: null,
    acquisition_currency: 'RON',
    acquisition_price: null,
    acquisition_date: '',
    acquisition_exchange_rate: null,
    reconditioning_cost: null,
    transport_cost: null,
    registration_cost: null,
    other_costs: null,
    location_id: null,
    parking_spot: '',
    source: '',
    supplier_name: '',
    supplier_cif: '',
    acquisition_document_number: '',
    has_manufacturer_warranty: false,
    manufacturer_warranty_date: '',
    has_dealer_warranty: false,
    dealer_warranty_months: null,
    is_first_owner: false,
    has_accident_history: false,
    has_service_book: false,
    has_tuning: false,
    is_registered: false,
    is_right_hand_drive: false,
    has_particle_filter: false,
    is_vintage: false,
    is_damaged: false,
    certified_mileage: false,
    color_finish: '',
    consum_urban: null,
    consum_extraurban: null,
    consum_mixt: null,
    electric_range_km: null,
    previous_owners: null,
    country_of_origin: '',
    equipment_options: [],
    first_registration_date: '',
    notes: '',
    internal_notes: '',
    listing_title: '',
    listing_description: '',
  })

  // "Titlu anunț" auto-composes from the specs until the user edits it manually
  // (then titleTouched stays true and we stop overwriting their text).
  const titleTouched = useRef(false)

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
      // Keep an existing custom title — don't auto-overwrite it.
      if (v.listing_title) titleTouched.current = true
      // Cost lines: parse the stored JSON, else migrate the old fixed columns.
      const vAny = v as unknown as Record<string, unknown>
      let lines: CostLine[] = []
      if (typeof vAny.cost_lines === 'string' && vAny.cost_lines) {
        try {
          const parsed = JSON.parse(vAny.cost_lines as string) as Array<Record<string, unknown>>
          lines = parsed.map((l) => ({
            type: String(l.type ?? l.label ?? ''),
            description: String(l.description ?? ''),
            date: String(l.date ?? ''),
            lei: l.lei == null ? null : Number(l.lei),
            kurs: l.kurs == null ? null : Number(l.kurs),
            eur: l.eur != null ? Number(l.eur) : l.amount != null ? Number(l.amount) : null,
          }))
        } catch {
          lines = []
        }
      } else {
        lines = (
          [
            ['Recondiționare', vAny.reconditioning_cost],
            ['Transport', vAny.transport_cost],
            ['Alte costuri', vAny.other_costs],
          ] as [string, unknown][]
        )
          .filter(([, a]) => a != null && a !== 0)
          .map(([type, a]) => ({ type, description: '', date: '', lei: null, kurs: null, eur: Number(a) }))
      }
      setCostLines(lines)
    }
    // Only run when existingData changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existingData])

  // Auto-composed listing title, refreshed as the specs change (unless edited).
  const autoTitle = useMemo(() => buildListingTitle(form), [
    form.brand, form.model, form.variant, form.generation, form.equipment_level,
    form.engine_displacement_cc, form.fuel_type, form.transmission, form.drive_type,
  ])
  useEffect(() => {
    if (!titleTouched.current) {
      setForm((prev) => (prev.listing_title === autoTitle ? prev : { ...prev, listing_title: autoTitle }))
    }
  }, [autoTitle])
  const regenerateTitle = () => {
    titleTouched.current = false
    setForm((prev) => ({ ...prev, listing_title: buildListingTitle(prev) }))
  }

  // AI-generated listing description from the vehicle's specs + dotări.
  const [genDesc, setGenDesc] = useState(false)
  const generateDescription = async () => {
    const lbl = (opts: readonly { value: string; label: string }[], v: unknown) =>
      opts.find((o) => o.value === v)?.label ?? (v == null ? '' : String(v))
    const eqLabels = ((form.equipment_options as string[]) ?? []).map((val) => {
      for (const g of AUTOVIT_EQUIPMENT) {
        const o = g.options.find((x) => x.value === val)
        if (o) return o.label
      }
      return val
    })
    const warranty = [
      form.has_manufacturer_warranty
        ? `Garanție producător${form.manufacturer_warranty_date ? ' până la ' + form.manufacturer_warranty_date : ''}`
        : '',
      form.has_dealer_warranty
        ? `Garanție dealer${form.dealer_warranty_months ? ' ' + form.dealer_warranty_months + ' luni' : ''}`
        : '',
    ]
      .filter(Boolean)
      .join('; ')
    const RO_MONTHS = ['ianuarie', 'februarie', 'martie', 'aprilie', 'mai', 'iunie', 'iulie', 'august', 'septembrie', 'octombrie', 'noiembrie', 'decembrie']
    const md = (form.manufacture_date as string | null) ?? ''
    const anFab = md
      ? (() => {
          const [y, m] = md.slice(0, 7).split('-')
          const name = RO_MONTHS[Number(m) - 1]
          return name ? `${name} ${y}` : md.slice(0, 7)
        })()
      : (form.year_of_manufacture ?? '')
    const specs: Record<string, unknown> = {
      Marcă: form.brand,
      Model: form.model,
      Versiune: form.variant,
      Generație: form.generation,
      'Nivel echipare': form.equipment_level,
      'An fabricație': anFab,
      Caroserie: lbl(AUTOVIT_BODY_TYPES, form.body_type),
      Combustibil: lbl(AUTOVIT_FUEL_TYPES, form.fuel_type),
      'Cutie de viteze': lbl(AUTOVIT_GEARBOX_TYPES, form.transmission),
      Tracțiune: lbl(AUTOVIT_DRIVE_TYPES, form.drive_type),
      'Capacitate cilindrică (cmc)': form.engine_displacement_cc,
      'Putere (CP)': form.engine_power_hp,
      'Rulaj (km)': form.mileage_km,
      'Culoare exterioară': lbl(AUTOVIT_COLORS, form.color_exterior),
      Tapițerie: lbl(AUTOVIT_INTERIOR_MATERIALS, form.interior_material),
      'Normă de poluare': lbl(AUTOVIT_EURO_STANDARDS, form.euro_standard),
      Portiere: form.doors,
      Locuri: form.seats,
      'Culoare interior': lbl(AUTOVIT_INTERIOR_COLORS, form.color_interior),
      'Prima înmatriculare': form.first_registration_date,
      'Primul proprietar': form.is_first_owner ? 'Da' : '',
      'Carte service': form.has_service_book ? 'Da' : '',
      'Nr. proprietari anteriori': form.previous_owners,
      'Nr. stoc': form.nr_stoc,
      Sursă: lbl(VEHICLE_SOURCES, form.source),
      Garanție: warranty,
    }
    setGenDesc(true)
    try {
      const description = await carparkApi.generateDescription({ specs, equipment: eqLabels })
      setForm((prev) => ({ ...prev, listing_description: description }))
      toast.success('Descriere generată')
    } catch {
      toast.error('Generarea descrierii a eșuat')
    } finally {
      setGenDesc(false)
    }
  }

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

  // "Date of fabrication" = Month + Year dropdowns. Both drive manufacture_date
  // (DATE column, stored as the 1st of the chosen month) and keep
  // year_of_manufacture in sync for the fleet year-range filters. Picking one
  // half defaults the other (current year / January) so a full date always forms.
  const fabMonth = (form.manufacture_date as string | null)?.slice(5, 7) ?? ''
  const fabYear = (form.manufacture_date as string | null)?.slice(0, 4) ?? ''
  const handleFabMonth = (month: string) => {
    const year = fabYear || String(_fabCurrentYear)
    setForm((prev) => ({
      ...prev,
      manufacture_date: `${year}-${month}-01`,
      year_of_manufacture: Number(year),
    }))
  }
  const handleFabYear = (year: string) => {
    const month = fabMonth || '01'
    setForm((prev) => ({
      ...prev,
      manufacture_date: `${year}-${month}-01`,
      year_of_manufacture: Number(year),
    }))
  }

  // Dotări equipment: toggle a value in the equipment_options string[].
  const toggleEquipment = (value: string) => {
    setForm((prev) => {
      const cur = Array.isArray(prev.equipment_options) ? (prev.equipment_options as string[]) : []
      const next = cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value]
      return { ...prev, equipment_options: next }
    })
  }

  // Local draft: save partial progress (from any tab, no required fields) to the
  // browser and restore it on return. Cleared once the vehicle is really saved.
  const draftKey = `carpark-draft-${vehicleId ?? 'new'}`
  const [pendingDraft, setPendingDraft] = useState<FormData | null>(null)
  useEffect(() => {
    const raw = localStorage.getItem(draftKey)
    if (raw) {
      try {
        setPendingDraft(JSON.parse(raw) as FormData)
      } catch {
        /* ignore a corrupt draft */
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const saveDraft = () => {
    localStorage.setItem(draftKey, JSON.stringify(form))
    setPendingDraft(null)
    toast.success('Ciornă salvată (local, în acest browser)')
  }
  const restoreDraft = () => {
    if (pendingDraft) setForm((prev) => ({ ...prev, ...pendingDraft }))
    setPendingDraft(null)
  }
  const discardDraft = () => {
    localStorage.removeItem(draftKey)
    setPendingDraft(null)
  }

  // Freeform acquisition cost lines — each entered in LEI on a date, converted
  // to EUR via BNR for that date. Sum of EUR feeds the cost total.
  const [costLines, setCostLines] = useState<CostLine[]>([])
  const fetchBnrRate = async (date: string): Promise<number | null> => {
    if (!date) return null
    try {
      const r = await carparkApi.getBnrRate(date)
      return r.kurs ?? null
    } catch {
      toast.error('Cursul BNR nu a putut fi preluat')
      return null
    }
  }
  const addCostLine = () =>
    setCostLines((p) => [...p, { type: '', description: '', date: '', lei: null, kurs: null, eur: null }])
  const removeCostLine = (i: number) => setCostLines((p) => p.filter((_, idx) => idx !== i))
  const patchLine = (i: number, patch: Partial<CostLine>) =>
    setCostLines((p) => p.map((l, idx) => (idx === i ? { ...l, ...patch } : l)))
  const lineEur = (lei: number | null, kurs: number | null) =>
    lei != null && kurs != null && kurs > 0 ? Math.round((lei / kurs) * 100) / 100 : null
  const handleLineDate = async (i: number, date: string) => {
    patchLine(i, { date })
    const kurs = await fetchBnrRate(date)
    if (kurs) {
      setCostLines((p) => p.map((l, idx) => (idx === i ? { ...l, kurs, eur: lineEur(l.lei, kurs) ?? l.eur } : l)))
    }
  }
  const handleLineLei = (i: number, v: string) => {
    const lei = v === '' ? null : Number(v)
    setCostLines((p) => p.map((l, idx) => (idx === i ? { ...l, lei, eur: lineEur(lei, l.kurs) ?? l.eur } : l)))
  }
  const handleLineEur = (i: number, v: string) => {
    const eur = v === '' ? null : Number(v)
    setCostLines((p) =>
      p.map((l, idx) => {
        if (idx !== i) return l
        const lei = eur != null && l.kurs != null && l.kurs > 0 ? Math.round(eur * l.kurs * 100) / 100 : l.lei
        return { ...l, eur, lei }
      }),
    )
  }
  const _num = (v: unknown) => (typeof v === 'number' ? v : 0)
  const costLinesTotal = costLines.reduce((s, l) => s + (l.eur ?? 0), 0)
  const totalCost = _num(form.purchase_price_net) + costLinesTotal

  // Today's BNR EUR/RON rate — to also show the selling prices in lei.
  const [eurRonRate, setEurRonRate] = useState<number | null>(null)
  useEffect(() => {
    fetchBnrRate(new Date().toISOString().slice(0, 10)).then(setEurRonRate)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const priceAlt = (price: unknown) => {
    const p = typeof price === 'number' ? price : null
    if (p == null || !eurRonRate) return null
    const cur = (form.price_currency as string) || 'EUR'
    if (cur === 'EUR') return `${Math.round(p * eurRonRate).toLocaleString('ro-RO')} lei`
    if (cur === 'RON') return `${Math.round(p / eurRonRate).toLocaleString('ro-RO')} EUR`
    return null
  }
  // Switching the Monedă converts the existing prices to the new currency.
  const handleCurrencyChange = (_name: string, next: string) => {
    const prevCur = (form.price_currency as string) || 'EUR'
    if (prevCur === next || !eurRonRate) {
      setForm((f) => ({ ...f, price_currency: next }))
      return
    }
    const conv = (v: unknown): number | null => {
      const p = typeof v === 'number' ? v : null
      if (p == null) return p
      if (prevCur === 'EUR' && next === 'RON') return Math.round(p * eurRonRate * 100) / 100
      if (prevCur === 'RON' && next === 'EUR') return Math.round((p / eurRonRate) * 100) / 100
      return p
    }
    setForm((f) => ({
      ...f,
      price_currency: next,
      list_price: conv(f.list_price),
      promotional_price: conv(f.promotional_price),
      minimum_price: conv(f.minimum_price),
      current_price: conv(f.current_price),
    }))
  }
  const marginInfo = (price: unknown) => {
    let p = typeof price === 'number' ? price : null
    // Margin is always computed in EUR (acquisition cost total is EUR).
    if (p != null && (form.price_currency as string) === 'RON' && eurRonRate) p = p / eurRonRate
    if (p == null || totalCost <= 0) return null
    const val = p - totalCost
    const pct = (val / totalCost) * 100
    return {
      text: `Marjă: ${Math.round(val).toLocaleString('ro-RO')} EUR · ${pct.toFixed(1)}%`,
      positive: val >= 0,
    }
  }
  const listMargin = marginInfo(form.list_price)
  const minMargin = marginInfo(form.minimum_price)

  // Acquisition price is entered in LEI (RON) and converted to EUR using the BNR
  // rate for the invoice date. The EUR value (purchase_price_net) stays editable.
  const [bnrLoading, setBnrLoading] = useState(false)
  const eurFromLei = (lei: unknown, kurs: unknown) => {
    const l = _num(lei)
    const k = _num(kurs)
    return l > 0 && k > 0 ? Math.round((l / k) * 100) / 100 : null
  }
  const fetchBnr = async (date: string) => {
    if (!date) return
    setBnrLoading(true)
    try {
      const r = await carparkApi.getBnrRate(date)
      if (r.kurs) {
        setForm((prev) => ({
          ...prev,
          acquisition_exchange_rate: r.kurs,
          purchase_price_net: eurFromLei(prev.acquisition_price, r.kurs) ?? prev.purchase_price_net,
        }))
        toast.success(`Curs BNR ${r.kurs} (${r.kurs_date})`)
      }
    } catch {
      toast.error('Cursul BNR nu a putut fi preluat')
    } finally {
      setBnrLoading(false)
    }
  }
  const handleAcqDate = (date: string) => {
    setForm((prev) => ({ ...prev, acquisition_date: date }))
    fetchBnr(date)
  }
  const handleAcqLei = (v: string) => {
    const lei = v === '' ? null : Number(v)
    setForm((prev) => ({
      ...prev,
      acquisition_price: lei,
      acquisition_currency: 'RON',
      purchase_price_net: eurFromLei(lei, prev.acquisition_exchange_rate) ?? prev.purchase_price_net,
    }))
  }
  const handleKurs = (v: string) => {
    const kurs = v === '' ? null : Number(v)
    setForm((prev) => ({
      ...prev,
      acquisition_exchange_rate: kurs,
      purchase_price_net: eurFromLei(prev.acquisition_price, kurs) ?? prev.purchase_price_net,
    }))
  }
  const handleAcqEur = (v: string) => {
    const eur = v === '' ? null : Number(v)
    setForm((prev) => {
      const kurs = _num(prev.acquisition_exchange_rate)
      const lei = eur != null && kurs > 0 ? Math.round(eur * kurs * 100) / 100 : prev.acquisition_price
      return { ...prev, purchase_price_net: eur, acquisition_price: lei }
    })
  }

  // Submit
  const createMutation = useMutation({
    mutationFn: (data: Partial<Vehicle>) => carparkApi.createVehicle(data, effectiveCompanyId),
    onSuccess: (result) => {
      localStorage.removeItem(draftKey)
      queryClient.invalidateQueries({ queryKey: ['carpark'] })
      toast.success('Mașină adăugată')
      navigate(`/app/carpark/${result.vehicle.id}/edit`)
    },
    onError: (err: Error & { data?: { error?: string } }) => {
      toast.error((err as any).data?.error || 'Failed to create vehicle')
    },
  })

  const updateMutation = useMutation({
    mutationFn: (data: Partial<Vehicle>) => carparkApi.updateVehicle(id!, data),
    onSuccess: () => {
      localStorage.removeItem(draftKey)
      // Refresh the list + this vehicle, but stay on the edit page.
      queryClient.invalidateQueries({ queryKey: ['carpark'] })
      toast.success('Modificări salvate')
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

    // Mirror Drive Park: persist only the capacity/norm fields relevant to the
    // selected fuel type (null the rest so an EV keeps no stale fuel-tank value).
    const ft = form.fuel_type as string
    if (!usesFuelTank(ft)) {
      payload.fuel_tank_capacity_liters = null
      payload.norma_combustibil = null
      payload.consum_urban = null
      payload.consum_extraurban = null
      payload.consum_mixt = null
    }
    if (!usesBattery(ft)) {
      payload.battery_capacity_kwh = null
      payload.norma_energie = null
      payload.electric_range_km = null
    }
    // Cargo details only apply to vans — null them for other body types so a
    // car switched away from Van / Utilitara keeps no stale cargo values.
    if (form.body_type !== 'van') {
      payload.payload_kg = null
      payload.cargo_volume_m3 = null
      payload.cargo_length_mm = null
      payload.cargo_width_mm = null
      payload.cargo_height_mm = null
      payload.euro_pallets = null
    }
    // Empty equipment array → null (avoids empty-array SQL adaptation).
    if (Array.isArray(payload.equipment_options) && (payload.equipment_options as string[]).length === 0) {
      payload.equipment_options = null
    }
    // Cost lines (JSON) replace the old fixed cost columns.
    payload.cost_lines = costLines.length ? JSON.stringify(costLines) : null
    payload.reconditioning_cost = null
    payload.transport_cost = null
    payload.other_costs = null

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
            {isEdit && (
              <Button variant="ghost" type="button" asChild>
                <Link to={`/app/carpark/${id}`}>
                  <ArrowLeft className="mr-1 h-4 w-4" />
                  Înapoi la profil
                </Link>
              </Button>
            )}
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

      {pendingDraft && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm dark:border-amber-800 dark:bg-amber-950">
          <span>Există o ciornă salvată pentru această mașină.</span>
          <div className="flex gap-2">
            <Button type="button" size="sm" variant="outline" onClick={restoreDraft}>
              Restaurează ciorna
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={discardDraft}>
              Șterge
            </Button>
          </div>
        </div>
      )}
      <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
        <TabsList className="grid w-full grid-cols-5">
          <TabsTrigger value="vehicul">Vehicul</TabsTrigger>
          <TabsTrigger value="specificatii">Specificații</TabsTrigger>
          <TabsTrigger value="dotari">Dotări</TabsTrigger>
          <TabsTrigger value="anunt">Anunț</TabsTrigger>
          <TabsTrigger value="comercial">Comercial</TabsTrigger>
        </TabsList>
        <TabsContent value="vehicul" className="space-y-4 pt-4">
      {/* Identification */}
      <Card className="p-4 space-y-3">
        <h3 className="text-sm font-semibold">Identificare</h3>
        <div className="grid gap-4 md:grid-cols-4">
          <SearchSelectField
            label="Marcă"
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
          <TextField label="Versiune" name="variant" value={form.variant as string} onChange={handleChange} placeholder="e.g. xDrive40i" />
          <SelectField
            label="Stare"
            name="state"
            value={form.state as string}
            options={[...AUTOVIT_VEHICLE_STATES]}
            onChange={handleChange}
          />
        </div>
        <div className="grid gap-4 md:grid-cols-4">
          <TextField label="Generație" name="generation" value={form.generation as string} onChange={handleChange} placeholder="e.g. G05 (LCI)" />
          <TextField label="Nivel echipare" name="equipment_level" value={form.equipment_level as string} onChange={handleChange} placeholder="e.g. M Sport, Inscription" />
          <div className="space-y-1.5">
            <Label>Data fabricației</Label>
            <div className="flex gap-2">
              <div className="flex-1 min-w-0">
                <SearchSelect
                  value={fabMonth}
                  onValueChange={handleFabMonth}
                  options={MONTH_OPTIONS}
                  placeholder="Month"
                  searchPlaceholder="Month..."
                />
              </div>
              <div className="w-28 shrink-0">
                <SearchSelect
                  value={fabYear}
                  onValueChange={handleFabYear}
                  options={YEAR_OPTIONS}
                  placeholder="Year"
                  searchPlaceholder="Year..."
                />
              </div>
            </div>
          </div>
          <TextField label="Prima înmatriculare" name="first_registration_date" value={form.first_registration_date as string} onChange={handleChange} type="date" />
        </div>
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
          <TextField label="Nr. stoc" name="nr_stoc" value={form.nr_stoc as string} onChange={handleChange} />
          <SelectField
            label="Categorie"
            name="category"
            value={form.category as string}
            options={CATEGORIES.map((c) => ({ value: c, label: CATEGORY_LABELS[c] }))}
            onChange={handleChange}
            required
          />
        </div>
      </Card>
      {/* Condition & Warranty */}
      <Card className="p-4 space-y-3">
        <h3 className="text-sm font-semibold">Stare & Garanție</h3>
        <div className="flex flex-wrap gap-6">
          <CheckboxField label="Primul proprietar" name="is_first_owner" checked={!!form.is_first_owner} onChange={handleChange} />
          <CheckboxField label="Istoric accidente" name="has_accident_history" checked={!!form.has_accident_history} onChange={handleChange} />
          <CheckboxField label="Carte service" name="has_service_book" checked={!!form.has_service_book} onChange={handleChange} />
          <CheckboxField label="Tuning" name="has_tuning" checked={!!form.has_tuning} onChange={handleChange} />
          <CheckboxField label="Înmatriculat" name="is_registered" checked={!!form.is_registered} onChange={handleChange} />
          <CheckboxField label="Volan pe dreapta" name="is_right_hand_drive" checked={!!form.is_right_hand_drive} onChange={handleChange} />
          <CheckboxField label="Filtru de particule" name="has_particle_filter" checked={!!form.has_particle_filter} onChange={handleChange} />
          <CheckboxField label="Vehicul de epocă" name="is_vintage" checked={!!form.is_vintage} onChange={handleChange} />
          <CheckboxField label="Autovehicul avariat" name="is_damaged" checked={!!form.is_damaged} onChange={handleChange} />
          <CheckboxField label="Rulaj certificat" name="certified_mileage" checked={!!form.certified_mileage} onChange={handleChange} />
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="space-y-1.5">
            <Label>Nr. proprietari anteriori</Label>
            <Input type="number" min={0} value={inputVal(form.previous_owners)} onChange={(e) => handleNumericChange('previous_owners', e.target.value)} placeholder="ex. 1" />
          </div>
          <TextField label="Țara de origine" name="country_of_origin" value={form.country_of_origin as string} onChange={handleChange} placeholder="ex. Germania" />
        </div>
        <Separator />
        <div className="grid gap-4 md:grid-cols-3">
          <CheckboxField label="Garanție producător" name="has_manufacturer_warranty" checked={!!form.has_manufacturer_warranty} onChange={handleChange} />
          {form.has_manufacturer_warranty && (
            <TextField label="Garanție până la" name="manufacturer_warranty_date" value={form.manufacturer_warranty_date as string} onChange={handleChange} type="date" />
          )}
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <CheckboxField label="Garanție dealer" name="has_dealer_warranty" checked={!!form.has_dealer_warranty} onChange={handleChange} />
          {form.has_dealer_warranty && (
            <div className="space-y-1.5">
              <Label>Luni garanție</Label>
              <Input
                type="number"
                value={inputVal(form.dealer_warranty_months)}
                onChange={(e) => handleNumericChange('dealer_warranty_months', e.target.value)}
              />
            </div>
          )}
        </div>
      </Card>
        </TabsContent>
        <TabsContent value="specificatii" className="space-y-4 pt-4">
      {/* Technical */}
      <Card className="p-4 space-y-3">
        <h3 className="text-sm font-semibold">Specificații tehnice</h3>
        <div className="grid gap-4 md:grid-cols-3">
          <SearchSelectField
            label="Combustibil"
            name="fuel_type"
            value={form.fuel_type as string}
            options={[...AUTOVIT_FUEL_TYPES]}
            onChange={handleChange}
            searchPlaceholder="Search fuel type..."
          />
          <SearchSelectField
            label="Cutie de viteze"
            name="transmission"
            value={form.transmission as string}
            options={[...AUTOVIT_GEARBOX_TYPES]}
            onChange={handleChange}
            searchPlaceholder="Search gearbox..."
          />
          <SearchSelectField
            label="Caroserie"
            name="body_type"
            value={form.body_type as string}
            options={[...AUTOVIT_BODY_TYPES]}
            onChange={handleChange}
            searchPlaceholder="Search body type..."
          />
        </div>
        {(usesFuelTank(form.fuel_type as string) || usesBattery(form.fuel_type as string)) && (
          <div className="grid gap-4 md:grid-cols-4">
            {usesFuelTank(form.fuel_type as string) && (
              <div className="space-y-1.5">
                <Label>Capacitate rezervor (L)</Label>
                <Input
                  type="number"
                  min={0}
                  step="any"
                  value={inputVal(form.fuel_tank_capacity_liters)}
                  onChange={(e) => handleNumericChange('fuel_tank_capacity_liters', e.target.value)}
                  placeholder="e.g. 50"
                />
              </div>
            )}
            {usesBattery(form.fuel_type as string) && (
              <div className="space-y-1.5">
                <Label>Capacitate baterie (kWh)</Label>
                <Input
                  type="number"
                  min={0}
                  step="any"
                  value={inputVal(form.battery_capacity_kwh)}
                  onChange={(e) => handleNumericChange('battery_capacity_kwh', e.target.value)}
                  placeholder="e.g. 64"
                />
              </div>
            )}
            {usesFuelTank(form.fuel_type as string) && (
              <div className="space-y-1.5">
                <Label>Normă consum (l/100 km)</Label>
                <Input
                  type="number"
                  min={0}
                  step="0.1"
                  value={inputVal(form.norma_combustibil)}
                  onChange={(e) => handleNumericChange('norma_combustibil', e.target.value)}
                  placeholder="ex. 6.5"
                />
              </div>
            )}
            {usesFuelTank(form.fuel_type as string) && (
              <div className="space-y-1.5">
                <Label>Consum urban (l/100 km)</Label>
                <Input type="number" min={0} step="0.1" value={inputVal(form.consum_urban)} onChange={(e) => handleNumericChange('consum_urban', e.target.value)} placeholder="ex. 7.5" />
              </div>
            )}
            {usesFuelTank(form.fuel_type as string) && (
              <div className="space-y-1.5">
                <Label>Consum extraurban (l/100 km)</Label>
                <Input type="number" min={0} step="0.1" value={inputVal(form.consum_extraurban)} onChange={(e) => handleNumericChange('consum_extraurban', e.target.value)} placeholder="ex. 5.0" />
              </div>
            )}
            {usesFuelTank(form.fuel_type as string) && (
              <div className="space-y-1.5">
                <Label>Consum mixt (l/100 km)</Label>
                <Input type="number" min={0} step="0.1" value={inputVal(form.consum_mixt)} onChange={(e) => handleNumericChange('consum_mixt', e.target.value)} placeholder="ex. 6.0" />
              </div>
            )}
            {usesBattery(form.fuel_type as string) && (
              <div className="space-y-1.5">
                <Label>Normă energie (kWh/100 km)</Label>
                <Input
                  type="number"
                  min={0}
                  step="0.1"
                  value={inputVal(form.norma_energie)}
                  onChange={(e) => handleNumericChange('norma_energie', e.target.value)}
                  placeholder="ex. 17.5"
                />
              </div>
            )}
            {usesBattery(form.fuel_type as string) && (
              <div className="space-y-1.5">
                <Label>Autonomie electrică (km)</Label>
                <Input type="number" min={0} value={inputVal(form.electric_range_km)} onChange={(e) => handleNumericChange('electric_range_km', e.target.value)} placeholder="ex. 450" />
              </div>
            )}
          </div>
        )}
        <div className="grid gap-4 md:grid-cols-4">
          <div className="space-y-1.5">
            <Label>Rulaj (km)</Label>
            <Input
              type="number"
              value={inputVal(form.mileage_km)}
              onChange={(e) => handleNumericChange('mileage_km', e.target.value)}
              placeholder="0"
            />
          </div>
          <div className="space-y-1.5">
            <Label>Putere (CP)</Label>
            <Input
              type="number"
              value={inputVal(form.engine_power_hp)}
              onChange={(e) => handleNumericChange('engine_power_hp', e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Capacitate cilindrică (cmc)</Label>
            <Input
              type="number"
              value={inputVal(form.engine_displacement_cc)}
              onChange={(e) => handleNumericChange('engine_displacement_cc', e.target.value)}
            />
          </div>
          <SearchSelectField
            label="Tracțiune"
            name="drive_type"
            value={form.drive_type as string}
            options={[...AUTOVIT_DRIVE_TYPES]}
            onChange={handleChange}
            searchPlaceholder="Search drive type..."
          />
        </div>
        <div className="grid gap-4 md:grid-cols-4">
          <SearchSelectField
            label="Culoare exterioară"
            name="color_exterior"
            value={form.color_exterior as string}
            options={[...AUTOVIT_COLORS]}
            onChange={handleChange}
            searchPlaceholder="Search color..."
          />
          <SearchSelectField
            label="Tip culoare"
            name="color_finish"
            value={form.color_finish as string}
            options={[...AUTOVIT_COLOR_FINISHES]}
            onChange={handleChange}
            searchPlaceholder="Search finish..."
          />
          <SearchSelectField
            label="Culoare interior"
            name="color_interior"
            value={form.color_interior as string}
            options={[...AUTOVIT_INTERIOR_COLORS]}
            onChange={handleChange}
            searchPlaceholder="Search color..."
          />
          <SearchSelectField
            label="Tapițerie"
            name="interior_material"
            value={form.interior_material as string}
            options={[...AUTOVIT_INTERIOR_MATERIALS]}
            onChange={handleChange}
            searchPlaceholder="Search material..."
          />
          <SelectField
            label="Nr. portiere"
            name="doors"
            value={form.doors != null ? String(form.doors) : ''}
            options={[...AUTOVIT_DOORS]}
            onChange={(n, v) => handleNumericChange(n, v)}
          />
          <SelectField
            label="Nr. locuri"
            name="seats"
            value={form.seats != null ? String(form.seats) : ''}
            options={[...AUTOVIT_SEATS]}
            onChange={(n, v) => handleNumericChange(n, v)}
          />
        </div>
        <div className="grid gap-4 md:grid-cols-4">
          <SearchSelectField
            label="Normă de poluare"
            name="euro_standard"
            value={form.euro_standard as string}
            options={[...AUTOVIT_EURO_STANDARDS]}
            onChange={handleChange}
            searchPlaceholder="Search euro..."
          />
          <div className="space-y-1.5">
            <Label>Emisii CO2 (g/km)</Label>
            <Input
              type="number"
              value={inputVal(form.co2_emissions)}
              onChange={(e) => handleNumericChange('co2_emissions', e.target.value)}
            />
          </div>
        </div>
        {form.body_type === 'van' && (
          <div className="space-y-4 rounded-md border border-dashed p-3">
            <h4 className="text-xs font-semibold text-muted-foreground">Cargo (Utilitară)</h4>
            <div className="grid gap-4 md:grid-cols-4">
              <div className="space-y-1.5">
                <Label>Masă maximă autorizată (kg)</Label>
                <Input type="number" min={0} value={inputVal(form.max_weight_kg)} onChange={(e) => handleNumericChange('max_weight_kg', e.target.value)} placeholder="e.g. 3500" />
              </div>
              <div className="space-y-1.5">
                <Label>Sarcină utilă (kg)</Label>
                <Input type="number" min={0} value={inputVal(form.payload_kg)} onChange={(e) => handleNumericChange('payload_kg', e.target.value)} placeholder="e.g. 1200" />
              </div>
              <div className="space-y-1.5">
                <Label>Volum util (m³)</Label>
                <Input type="number" min={0} step="0.1" value={inputVal(form.cargo_volume_m3)} onChange={(e) => handleNumericChange('cargo_volume_m3', e.target.value)} placeholder="e.g. 11.5" />
              </div>
              <div className="space-y-1.5">
                <Label>Europaleți</Label>
                <Input type="number" min={0} value={inputVal(form.euro_pallets)} onChange={(e) => handleNumericChange('euro_pallets', e.target.value)} placeholder="e.g. 3" />
              </div>
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              <div className="space-y-1.5">
                <Label>Lungime cală (mm)</Label>
                <Input type="number" min={0} value={inputVal(form.cargo_length_mm)} onChange={(e) => handleNumericChange('cargo_length_mm', e.target.value)} placeholder="e.g. 3200" />
              </div>
              <div className="space-y-1.5">
                <Label>Lățime cală (mm)</Label>
                <Input type="number" min={0} value={inputVal(form.cargo_width_mm)} onChange={(e) => handleNumericChange('cargo_width_mm', e.target.value)} placeholder="e.g. 1700" />
              </div>
              <div className="space-y-1.5">
                <Label>Înălțime cală (mm)</Label>
                <Input type="number" min={0} value={inputVal(form.cargo_height_mm)} onChange={(e) => handleNumericChange('cargo_height_mm', e.target.value)} placeholder="e.g. 1900" />
              </div>
            </div>
          </div>
        )}
      </Card>
        </TabsContent>
        <TabsContent value="dotari" className="space-y-4 pt-4">
      {/* Dotări (Equipment) */}
      <Card className="p-4 space-y-3">
        <h3 className="text-sm font-semibold">Dotări</h3>
        {AUTOVIT_EQUIPMENT.map((group) => (
          <div key={group.category} className="space-y-2">
            <h4 className="text-xs font-semibold text-muted-foreground">{group.category}</h4>
            <div className="flex flex-wrap gap-x-6 gap-y-2">
              {group.options.map((opt) => {
                const selected =
                  Array.isArray(form.equipment_options) &&
                  (form.equipment_options as string[]).includes(opt.value)
                return (
                  <div key={opt.value} className="flex items-center gap-2">
                    <Checkbox
                      id={`eq-${opt.value}`}
                      checked={selected}
                      onCheckedChange={() => toggleEquipment(opt.value)}
                    />
                    <Label htmlFor={`eq-${opt.value}`} className="text-sm font-normal cursor-pointer">
                      {opt.label}
                    </Label>
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </Card>
        </TabsContent>
        <TabsContent value="anunt" className="space-y-4 pt-4">
      {/* Listing */}
      <Card className="p-4 space-y-3">
        <h3 className="text-sm font-semibold">Anunț & Note</h3>
        <div className="space-y-1.5">
          <div className="flex items-center justify-between gap-2">
            <Label htmlFor="listing_title">Titlu anunț</Label>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-xs text-muted-foreground"
              onClick={regenerateTitle}
              title="Recompune titlul din specificații"
            >
              <RefreshCw className="mr-1 h-3 w-3" />
              Din specificații
            </Button>
          </div>
          <Input
            id="listing_title"
            value={(form.listing_title as string) ?? ''}
            onChange={(e) => {
              titleTouched.current = true
              handleChange('listing_title', e.target.value)
            }}
            placeholder="Se completează automat din specificații"
          />
        </div>
        <div className="space-y-1.5">
          <div className="flex items-center justify-between gap-2">
            <Label htmlFor="listing_description">Descriere anunț</Label>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-xs text-muted-foreground"
              onClick={generateDescription}
              disabled={genDesc}
              title="Generează descrierea cu AI din specificații și dotări"
            >
              {genDesc ? (
                <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              ) : (
                <Sparkles className="mr-1 h-3 w-3" />
              )}
              Generează cu AI
            </Button>
          </div>
          <Textarea
            id="listing_description"
            value={(form.listing_description as string) ?? ''}
            onChange={(e) => handleChange('listing_description', e.target.value)}
            placeholder="Se poate genera cu AI din specificații și dotări."
            rows={4}
          />
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-1.5">
            <Label>Note</Label>
            <Textarea
              value={(form.notes as string) ?? ''}
              onChange={(e) => handleChange('notes', e.target.value)}
              rows={3}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Note interne</Label>
            <Textarea
              value={(form.internal_notes as string) ?? ''}
              onChange={(e) => handleChange('internal_notes', e.target.value)}
              rows={3}
            />
          </div>
        </div>
      </Card>
        </TabsContent>
        <TabsContent value="comercial" className="space-y-4 pt-4">
      {/* Location & Source */}
      <Card className="p-4 space-y-3">
        <h3 className="text-sm font-semibold">Locație & Sursă</h3>
        <div className="grid gap-4 md:grid-cols-3">
          <SelectField
            label="Locație"
            name="location_id"
            value={form.location_id != null ? String(form.location_id) : ''}
            options={locationOptions}
            onChange={(name, value) => handleNumericChange(name, value)}
          />
          <TextField label="Loc parcare" name="parking_spot" value={form.parking_spot as string} onChange={handleChange} placeholder="e.g. A-15" />
          <SearchSelectField
            label="Sursă"
            name="source"
            value={form.source as string}
            options={[...VEHICLE_SOURCES]}
            onChange={handleChange}
            allowCustom
            searchPlaceholder="Caută sursă..."
          />
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <TextField label="Nume furnizor" name="supplier_name" value={form.supplier_name as string} onChange={handleChange} />
          <TextField label="CIF furnizor" name="supplier_cif" value={form.supplier_cif as string} onChange={handleChange} />
          <TextField label="Nr. factură intrare" name="acquisition_document_number" value={form.acquisition_document_number as string} onChange={handleChange} />
        </div>
      </Card>
      {/* Pricing */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* Achiziție */}
        <Card className="p-4 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">Achiziție</h3>
            {totalCost > 0 && (
              <span className="text-xs font-medium">Cost total: {totalCost.toLocaleString('ro-RO')} EUR</span>
            )}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Preț achiziție (LEI)</Label>
              <Input type="number" step="0.01" value={inputVal(form.acquisition_price)} onChange={(e) => handleAcqLei(e.target.value)} placeholder="RON" />
            </div>
            <div className="space-y-1.5">
              <Label>Data factură</Label>
              <Input type="date" value={(form.acquisition_date as string) ?? ''} onChange={(e) => handleAcqDate(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Curs BNR (RON/EUR)</Label>
              <Input type="number" step="0.0001" value={inputVal(form.acquisition_exchange_rate)} onChange={(e) => handleKurs(e.target.value)} placeholder={bnrLoading ? 'Se preia…' : 'auto la data facturii'} />
            </div>
            <div className="space-y-1.5">
              <Label>Preț achiziție (EUR)</Label>
              <Input type="number" step="0.01" value={inputVal(form.purchase_price_net)} onChange={(e) => handleAcqEur(e.target.value)} />
            </div>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs text-muted-foreground">Costuri suplimentare (EUR)</Label>
              <Button type="button" size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={addCostLine}>
                <Plus className="mr-1 h-3 w-3" /> Adaugă linie
              </Button>
            </div>
            {costLines.length === 0 && (
              <p className="text-xs text-muted-foreground">Nicio linie. Adaugă recondiționare, transport etc.</p>
            )}
            {costLines.map((line, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2 rounded-md border p-2">
                <div className="w-36 shrink-0">
                  <SearchSelect
                    value={line.type}
                    onValueChange={(v) => patchLine(i, { type: v })}
                    options={[...CARPARK_COST_TYPES]}
                    placeholder="Tip cost"
                    searchPlaceholder="Caută/adaugă..."
                    allowCustom
                  />
                </div>
                <Input placeholder="Descriere" className="min-w-[7rem] flex-1" value={line.description} onChange={(e) => patchLine(i, { description: e.target.value })} />
                <Input type="date" className="w-36 shrink-0" value={line.date} onChange={(e) => handleLineDate(i, e.target.value)} />
                <Input type="number" step="0.01" placeholder="LEI" className="w-24 shrink-0" value={line.lei ?? ''} onChange={(e) => handleLineLei(i, e.target.value)} title={line.kurs ? `Curs BNR ${line.kurs}` : ''} />
                <Input type="number" step="0.01" placeholder="EUR" className="w-24 shrink-0" value={line.eur ?? ''} onChange={(e) => handleLineEur(i, e.target.value)} />
                <Button type="button" size="icon" variant="ghost" className="shrink-0" onClick={() => removeCostLine(i)}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>
        </Card>
        {/* Vânzare */}
        <Card className="p-4 space-y-3">
          <h3 className="text-sm font-semibold">Vânzare</h3>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Preț</Label>
              <Input type="number" step="0.01" value={inputVal(form.list_price)} onChange={(e) => handleNumericChange('list_price', e.target.value)} />
              {priceAlt(form.list_price) && (
                <p className="text-[10px] text-muted-foreground">≈ {priceAlt(form.list_price)}</p>
              )}
              {listMargin && (
                <p className={`text-xs ${listMargin.positive ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>{listMargin.text}</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label>Preț promoțional</Label>
              <Input type="number" step="0.01" value={inputVal(form.promotional_price)} onChange={(e) => handleNumericChange('promotional_price', e.target.value)} />
              {priceAlt(form.promotional_price) && (
                <p className="text-[10px] text-muted-foreground">≈ {priceAlt(form.promotional_price)}</p>
              )}
            </div>
            <SelectField
              label="Monedă"
              name="price_currency"
              value={form.price_currency as string}
              options={[
                { value: 'EUR', label: 'EUR' },
                { value: 'RON', label: 'RON' },
                { value: 'USD', label: 'USD' },
              ]}
              onChange={handleCurrencyChange}
            />
            <div className="space-y-1.5">
              <Label>Preț minim</Label>
              <Input type="number" step="0.01" value={inputVal(form.minimum_price)} onChange={(e) => handleNumericChange('minimum_price', e.target.value)} />
              {priceAlt(form.minimum_price) && (
                <p className="text-[10px] text-muted-foreground">≈ {priceAlt(form.minimum_price)}</p>
              )}
              <p className="text-[10px] text-muted-foreground">Doar pentru alerte & statistici</p>
              {minMargin && (
                <p className={`text-xs ${minMargin.positive ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>{minMargin.text}</p>
              )}
            </div>
          </div>
          <div className="flex flex-wrap gap-4">
            <CheckboxField label="Preț cu TVA" name="price_includes_vat" checked={!!form.price_includes_vat} onChange={handleChange} />
            <CheckboxField label="Negociabil" name="is_negotiable" checked={!!form.is_negotiable} onChange={handleChange} />
            <CheckboxField label="Regim marjă" name="margin_scheme" checked={!!form.margin_scheme} onChange={handleChange} />
            <CheckboxField label="Eligibil finanțare" name="eligible_for_financing" checked={!!form.eligible_for_financing} onChange={handleChange} />
          </div>
          {isEdit && pricingHistory.length > 0 && (
            <>
              <Separator />
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Istoric preț</Label>
                <ul className="max-h-32 space-y-0.5 overflow-y-auto text-xs text-muted-foreground">
                  {pricingHistory.map((h, i) => {
                    const d = new Date(h.created_at).toLocaleDateString('ro-RO')
                    const cur = (form.price_currency as string) || 'EUR'
                    const reasons: Record<string, string> = {
                      manual_update: 'modificare manuală',
                      rule: 'regulă de preț',
                      promotion: 'promoție',
                      initial: 'preț inițial',
                    }
                    const reason = h.change_reason ? reasons[h.change_reason] ?? h.change_reason : ''
                    const changed = h.old_price != null && h.old_price !== h.new_price
                    const price = changed
                      ? `${(h.old_price ?? 0).toLocaleString('ro-RO')} → ${(h.new_price ?? 0).toLocaleString('ro-RO')} ${cur}`
                      : `${(h.new_price ?? 0).toLocaleString('ro-RO')} ${cur}`
                    return (
                      <li key={i}>
                        {d} — {price}
                        {reason ? ` · ${reason}` : ''}
                      </li>
                    )
                  })}
                </ul>
              </div>
            </>
          )}
        </Card>
      </div>
        </TabsContent>
      </Tabs>

      {/* Submit bar */}
      <div className="flex justify-end gap-2 sticky bottom-4">
        <Button variant="secondary" type="button" onClick={saveDraft} className="mr-auto">
          Salvează ciornă
        </Button>
        {isEdit && (
          <Button variant="ghost" type="button" asChild>
            <Link to={`/app/carpark/${id}`}>
              <ArrowLeft className="mr-1 h-4 w-4" />
              Înapoi la profil
            </Link>
          </Button>
        )}
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
