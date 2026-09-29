import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import {
  ArrowLeft,
  Car,
  Euro,
  FileText,
  IdCard,
  ImagePlus,
  Loader2,
  Search,
  Tag,
  User,
  X,
} from 'lucide-react'
import { buybackApi } from '@/api/buyback'
import type { BuybackRecord } from '@/types/buyback'
import { useAuth } from '@/hooks/useAuth'
import { cn, useDebounce } from '@/lib/utils'
import { fileToCompressedDataUrl } from '@/lib/imageCompress'
import { AUTOVIT_EQUIPMENT, AUTOVIT_BRANDS, AUTOVIT_MODELS } from '@/data/autovitData'
import { Autocomplete, norm } from '@/components/shared/Autocomplete'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

// ── VIN validation — mirrors buyback/routes/_shared.py::VIN_RE exactly
//    (17 chars, no I/O/Q). ──
const VIN_RE = /^[A-HJ-NPR-Z0-9]{17}$/

// Stable empty option list — avoids allocating a fresh `[]` on every render for
// brands that have no known models yet.
const EMPTY_STRINGS: string[] = []

// Map a parsed value to a known option's exact casing (so a CIV/talon "NISSAN"
// becomes "Nissan"); returns the value unchanged when there's no match — the
// Marca/Model autocompletes then offer "➕ Adaugă «value»". Uses Autocomplete's
// shared case/diacritic-insensitive `norm`.
function canonicalOption(value: string, options: readonly string[]): string {
  const n = norm(value)
  return options.find((o) => norm(o) === n) ?? value
}

// ── A lean CRM-client shape (only the fields this form reads/writes) — the
//    API returns `any[]` since crm client serialization is shared/generic. ──
interface LookupCrmClient {
  id: number | string
  display_name?: string | null
  name?: string | null
  phone?: string | null
  email?: string | null
  cui?: string | null
  client_type?: string | null
}

interface LookupCarparkVehicle {
  id: number
  brand?: string | null
  model?: string | null
  vin?: string | null
  nr_stoc?: string | null
  registration_number?: string | null
}

// ── Form state ──────────────────────────────────────────────────────────
// Numeric fields are kept as strings (raw <Input> values) so the field can
// genuinely be blank; buildCreatePayload below coerces them to numbers and
// drops anything empty. Mirrors the shape buildCreatePayload's unit test
// exercises directly (some numeric fields there arrive pre-coerced too —
// `Number(x)` handles both).
export interface BuyBackFormState {
  // Header
  advisor_id?: number | null
  advisor_name?: string
  acquisition_type?: string
  is_trade_in?: boolean
  client_type?: string
  vat_status?: string
  // Seller
  client_id?: number | null
  seller_name?: string
  seller_email?: string
  seller_phone?: string
  seller_cui?: string
  // Vehicle
  brand: string
  brand_id?: number | null
  model: string
  variant?: string
  equipment?: string
  vin: string
  mileage_km?: string | number
  engine_capacity_cm3?: string | number
  fuel_type?: string
  transmission?: string
  gearbox?: string
  manufacture_date?: string
  first_registration_date?: string
  service_history_uptodate?: boolean
  extra_wheels?: boolean
  keys_count?: string | number
  has_damage?: boolean
  damage_details?: string
  general_condition?: string | number
  images?: string[]
  // Trade-in
  target_vehicle_text?: string
  target_carpark_vehicle_id?: number | null
  crm_deal_id?: number | null
  // Client expectations
  client_asking_price_eur?: string | number
  client_source?: string
  other_details?: string
  drive_folder_link?: string
}

const emptyForm: BuyBackFormState = {
  advisor_id: null,
  advisor_name: '',
  acquisition_type: 'buyback',
  is_trade_in: false,
  client_type: 'person',
  vat_status: '',
  client_id: null,
  seller_name: '',
  seller_email: '',
  seller_phone: '',
  seller_cui: '',
  brand: '',
  model: '',
  variant: '',
  equipment: '',
  vin: '',
  mileage_km: '',
  engine_capacity_cm3: '',
  fuel_type: '',
  transmission: '',
  gearbox: '',
  manufacture_date: '',
  first_registration_date: '',
  service_history_uptodate: false,
  extra_wheels: false,
  keys_count: '',
  has_damage: false,
  damage_details: '',
  general_condition: '',
  images: [],
  target_vehicle_text: '',
  target_carpark_vehicle_id: null,
  crm_deal_id: null,
  client_asking_price_eur: '',
  client_source: '',
  other_details: '',
  drive_folder_link: '',
}

// Map a fetched record → editable form state (Corectează flow). Nulls become ''
// so inputs stay controlled; numeric fields pass through (the <Input>s coerce).
function recordToForm(r: BuybackRecord): BuyBackFormState {
  const s = (v: string | null | undefined) => v ?? ''
  const n = (v: number | null | undefined): string | number => v ?? ''
  return {
    advisor_id: r.advisor_id ?? null,
    advisor_name: s(r.advisor_name),
    acquisition_type: s(r.acquisition_type),
    is_trade_in: !!r.is_trade_in,
    client_type: s(r.client_type),
    vat_status: s(r.vat_status),
    client_id: r.client_id ?? null,
    seller_name: s(r.seller_name),
    seller_email: s(r.seller_email),
    seller_phone: s(r.seller_phone),
    seller_cui: s(r.seller_cui),
    brand: s(r.brand),
    brand_id: null,
    model: s(r.model),
    variant: s(r.variant),
    equipment: s(r.equipment),
    vin: s(r.vin),
    mileage_km: n(r.mileage_km),
    engine_capacity_cm3: n(r.engine_capacity_cm3),
    fuel_type: s(r.fuel_type),
    transmission: s(r.transmission),
    gearbox: s(r.gearbox),
    manufacture_date: s(r.manufacture_date),
    first_registration_date: s(r.first_registration_date),
    service_history_uptodate: !!r.service_history_uptodate,
    extra_wheels: !!r.extra_wheels,
    keys_count: n(r.keys_count),
    has_damage: !!r.has_damage,
    damage_details: s(r.damage_details),
    general_condition: n(r.general_condition),
    images: [],
    target_vehicle_text: s(r.target_vehicle_text),
    target_carpark_vehicle_id: r.target_carpark_vehicle_id ?? null,
    crm_deal_id: r.crm_deal_id ?? null,
    client_asking_price_eur: n(r.client_asking_price_eur),
    client_source: s(r.client_source),
    other_details: s(r.other_details),
    drive_folder_link: s(r.drive_folder_link),
  }
}

// ── The backend's `_CREATE_FIELDS` whitelist (buyback/routes/records.py) —
//    `vin`/`brand`/`model` are handled separately below (always required,
//    never omitted); every other field here is optional. ──
export interface CreatePayload {
  brand: string
  model: string
  vin: string
  brand_id?: number
  acquisition_type?: string
  is_trade_in?: boolean
  advisor_id?: number
  advisor_name?: string
  client_type?: string
  vat_status?: string
  client_id?: number
  seller_name?: string
  seller_email?: string
  seller_phone?: string
  seller_cui?: string
  variant?: string
  equipment?: string
  mileage_km?: number
  engine_capacity_cm3?: number
  fuel_type?: string
  transmission?: string
  gearbox?: string
  manufacture_date?: string
  first_registration_date?: string
  service_history_uptodate?: boolean
  extra_wheels?: boolean
  keys_count?: number
  has_damage?: boolean
  damage_details?: string
  general_condition?: number
  client_asking_price_eur?: number
  client_source?: string
  other_details?: string
  drive_folder_link?: string
  target_vehicle_text?: string
  target_carpark_vehicle_id?: number
  crm_deal_id?: number
  images?: string[]
}

// Optional string fields copied as-is (dates included — sent as the
// "YYYY-MM-DD" strings the date <Input>s already produce).
const STRING_FIELDS = [
  'acquisition_type', 'advisor_name', 'client_type', 'vat_status',
  'seller_name', 'seller_email', 'seller_phone', 'seller_cui',
  'variant', 'equipment', 'fuel_type', 'transmission', 'gearbox',
  'manufacture_date', 'first_registration_date', 'damage_details',
  'client_source', 'other_details', 'drive_folder_link', 'target_vehicle_text',
] as const satisfies readonly (keyof BuyBackFormState)[]

// Optional fields coerced to a number (integers in practice, but Number()
// suffices — the backend re-validates/coerces server-side too).
const NUMBER_FIELDS = [
  'mileage_km', 'engine_capacity_cm3', 'keys_count', 'general_condition',
] as const satisfies readonly (keyof BuyBackFormState)[]

// Optional id-reference fields — same numeric coercion as NUMBER_FIELDS,
// kept as a separate list only for readability at the call site below.
const ID_FIELDS = [
  'brand_id', 'advisor_id', 'client_id', 'target_carpark_vehicle_id', 'crm_deal_id',
] as const satisfies readonly (keyof BuyBackFormState)[]

// Optional boolean fields — emitted only when explicitly true/false (never
// for undefined, which would otherwise serialize as a bogus payload key).
const BOOLEAN_FIELDS = [
  'is_trade_in', 'service_history_uptodate', 'extra_wheels', 'has_damage',
] as const satisfies readonly (keyof BuyBackFormState)[]

/**
 * Pure mapping: form state → the exact `_CREATE_FIELDS` whitelist the
 * backend accepts for POST /api/buyback/records (buyback/routes/records.py).
 * Coerces numeric-looking fields to real numbers, keeps booleans as
 * booleans, keeps dates as plain "YYYY-MM-DD" strings, and OMITS any
 * optional field whose value is '' / undefined / null. Required
 * brand/model/vin are always present (even if blank — client-side submit
 * gating, not this function, is what blocks an incomplete record).
 */
export function buildCreatePayload(form: BuyBackFormState): CreatePayload {
  const payload: CreatePayload = {
    brand: form.brand,
    model: form.model,
    vin: form.vin.trim().toUpperCase(),
  }

  for (const field of STRING_FIELDS) {
    const v = form[field]
    if (v !== undefined && v !== null && String(v).trim() !== '') {
      ;(payload as unknown as Record<string, unknown>)[field] = v
    }
  }

  for (const field of [...NUMBER_FIELDS, ...ID_FIELDS]) {
    const v = form[field]
    if (v !== undefined && v !== null && String(v).trim() !== '') {
      const n = Number(v)
      if (!Number.isNaN(n)) (payload as unknown as Record<string, unknown>)[field] = n
    }
  }

  const price = form.client_asking_price_eur
  if (price !== undefined && price !== null && String(price).trim() !== '') {
    const n = Number(price)
    if (!Number.isNaN(n)) payload.client_asking_price_eur = n
  }

  for (const field of BOOLEAN_FIELDS) {
    const v = form[field]
    if (typeof v === 'boolean') (payload as unknown as Record<string, unknown>)[field] = v
  }

  if (Array.isArray(form.images) && form.images.length > 0) {
    payload.images = form.images
  }

  return payload
}

interface BuyBackFormProps {
  embedded?: boolean
  onDone?: (r: BuybackRecord) => void
  onCancel?: () => void
}

// ── Component ──────────────────────────────────────────────────────────
export default function BuyBackForm({ embedded, onDone, onCancel }: BuyBackFormProps = {}) {
  const navigate = useNavigate()
  const { id: routeId } = useParams<{ id?: string }>()
  const editId = !embedded && routeId ? Number(routeId) : null
  const isEdit = editId != null
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [form, setForm] = useState<BuyBackFormState>(emptyForm)
  const [attempted, setAttempted] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const set = <K extends keyof BuyBackFormState>(key: K, value: BuyBackFormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  // Edit (Corectează): load the existing record and prefill the form once.
  const { data: editData } = useQuery({
    queryKey: ['buyback-record', editId],
    queryFn: () => buybackApi.getRecord(editId as number),
    enabled: isEdit,
  })
  const prefilledRef = useRef(false)
  useEffect(() => {
    if (isEdit && editData?.record && !prefilledRef.current) {
      prefilledRef.current = true
      setForm(recordToForm(editData.record))
    }
  }, [isEdit, editData])

  // Prefill the advisor from the logged-in user once auth resolves — create only
  // (in edit we keep the record's original advisor).
  useEffect(() => {
    if (!isEdit && user && !form.advisor_id) {
      setForm((f) => ({ ...f, advisor_id: user.id, advisor_name: f.advisor_name || user.name }))
    }
  }, [user, isEdit]) // eslint-disable-line react-hooks/exhaustive-deps

  const { data: opts } = useQuery({
    queryKey: ['buyback-options'],
    queryFn: () => buybackApi.getLookupOptions(),
    staleTime: 5 * 60_000,
  })

  // ── VIN validity (client-side mirror of the backend's VIN_RE) ──
  const vinValue = form.vin.trim().toUpperCase()
  const vinValid = VIN_RE.test(vinValue)
  const vinTouched = attempted || form.vin.length > 0
  const canSubmit = form.brand.trim() !== '' && form.model.trim() !== '' && vinValid

  // ── Echipare (equipment): store selected AUTOVIT values as a comma-joined
  //    string in form.equipment; round-trips cleanly via this Set. ──
  const selectedEquipment = useMemo(
    () => new Set((form.equipment || '').split(',').map((s) => s.trim()).filter(Boolean)),
    [form.equipment],
  )
  const toggleEquipment = (value: string) => {
    const next = new Set(selectedEquipment)
    if (next.has(value)) next.delete(value)
    else next.add(value)
    set('equipment', Array.from(next).join(', '))
  }

  // ── CIV / talon import — AI-vision extraction of a RO vehicle document into
  //    the intake fields (only fills the fields the document actually carries). ──
  const civInputRef = useRef<HTMLInputElement>(null)
  const talonInputRef = useRef<HTMLInputElement>(null)
  const [decoding, setDecoding] = useState<null | 'civ' | 'talon'>(null)

  const DECODE_KEYS = [
    'vin', 'brand', 'model', 'variant',
    'first_registration_date', 'engine_capacity_cm3', 'fuel_type',
  ] as const

  const handleDecodeDocument = async (file: File, docType: 'civ' | 'talon') => {
    if (file.size > 12 * 1024 * 1024) {
      toast.error('Fișierul este prea mare (max 12MB).')
      return
    }
    setDecoding(docType)
    try {
      const res = await buybackApi.decodeDocument(file, docType)
      if (!res.success || !res.data) {
        toast.error(res.error || 'Nu am putut extrage date din document.')
        return
      }
      const fields = res.data.vehicle_fields || {}
      const applied: string[] = []
      setForm((f) => {
        const next = { ...f }
        for (const k of DECODE_KEYS) {
          const v = fields[k]
          if (v === undefined || v === null || v === '') continue
          if (k === 'vin') next.vin = String(v).trim().toUpperCase()
          else if (k === 'engine_capacity_cm3') next.engine_capacity_cm3 = String(v)
          // Canonicalize make/model to the AUTOVIT list casing (NISSAN → Nissan);
          // brand is processed before model so next.brand is already canonical.
          else if (k === 'brand') next.brand = canonicalOption(String(v), AUTOVIT_BRANDS)
          else if (k === 'model') next.model = canonicalOption(String(v), AUTOVIT_MODELS[next.brand] ?? EMPTY_STRINGS)
          else (next as Record<string, unknown>)[k] = String(v)
          applied.push(k)
        }
        return next
      })
      if (applied.length) toast.success(`${docType.toUpperCase()} citit — ${applied.length} câmpuri completate, verifică-le.`)
      else toast.warning(`Nu am găsit date utile în ${docType.toUpperCase()}.`)
    } catch (err) {
      const msg = (err as { data?: { error?: string } })?.data?.error || 'Importul documentului a eșuat.'
      toast.error(msg)
    } finally {
      setDecoding(null)
    }
  }

  // ── Seller (CRM client) search ──
  const [selectedClient, setSelectedClient] = useState<LookupCrmClient | null>(null)
  const [showNewClient, setShowNewClient] = useState(false)
  const [clientQuery, setClientQuery] = useState('')
  const debouncedClientQuery = useDebounce(clientQuery, 350)
  const { data: clientSearchData, isFetching: isSearchingClients } = useQuery({
    queryKey: ['buyback-crm-search', debouncedClientQuery],
    queryFn: () => buybackApi.searchCrmClients(debouncedClientQuery),
    enabled: debouncedClientQuery.trim().length >= 2 && !selectedClient,
  })
  const clientResults: LookupCrmClient[] = clientSearchData?.clients ?? []

  function applyClient(c: LookupCrmClient) {
    setSelectedClient(c)
    set('client_id', Number(c.id))
    set('seller_name', c.display_name || c.name || '')
    set('seller_email', c.email || '')
    set('seller_phone', c.phone || '')
    set('seller_cui', c.cui || '')
    if (c.client_type) set('client_type', c.client_type)
    setClientQuery('')
    setShowNewClient(false)
  }

  function clearClient() {
    setSelectedClient(null)
    set('client_id', null)
  }

  // Inline "client nou" creation
  const [newClientName, setNewClientName] = useState('')
  const [newClientPhone, setNewClientPhone] = useState('')
  const [newClientEmail, setNewClientEmail] = useState('')
  const [newClientCui, setNewClientCui] = useState('')
  const [newClientIsCompany, setNewClientIsCompany] = useState(false)
  const [newClientError, setNewClientError] = useState<string | null>(null)
  const createClientMutation = useMutation({
    mutationFn: () =>
      buybackApi.createCrmClient({
        display_name: newClientName.trim(),
        phone: newClientPhone.trim(),
        email: newClientEmail.trim() || undefined,
        cui: newClientCui.trim() || undefined,
        client_type: newClientIsCompany ? 'company' : 'person',
        is_company: newClientIsCompany,
      }),
    onSuccess: (res) => {
      if (res.client) applyClient(res.client)
      setNewClientName(''); setNewClientPhone(''); setNewClientEmail(''); setNewClientCui('')
      setNewClientIsCompany(false); setNewClientError(null)
    },
    onError: (err: any) => setNewClientError(err?.data?.error || err?.message || 'Crearea clientului a eșuat'),
  })

  // ── Trade-in target — CarPark vehicle search ──
  const [selectedTarget, setSelectedTarget] = useState<LookupCarparkVehicle | null>(null)
  const [targetQuery, setTargetQuery] = useState('')
  const debouncedTargetQuery = useDebounce(targetQuery, 350)
  const { data: targetSearchData, isFetching: isSearchingTargets } = useQuery({
    queryKey: ['buyback-carpark-search', debouncedTargetQuery],
    queryFn: () => buybackApi.searchCarparkVehicles(debouncedTargetQuery),
    enabled: debouncedTargetQuery.trim().length >= 2 && !selectedTarget,
  })
  const targetResults: LookupCarparkVehicle[] = targetSearchData?.vehicles ?? []

  function applyTarget(v: LookupCarparkVehicle) {
    setSelectedTarget(v)
    set('target_carpark_vehicle_id', v.id)
    const label = [v.brand, v.model, v.nr_stoc ? `(${v.nr_stoc})` : ''].filter(Boolean).join(' ')
    if (label) set('target_vehicle_text', label)
    setTargetQuery('')
  }

  function clearTarget() {
    setSelectedTarget(null)
    set('target_carpark_vehicle_id', null)
  }

  // ── Images ──
  const [imageBusy, setImageBusy] = useState(false)
  async function handleImageFiles(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? [])
    e.target.value = ''
    if (!files.length) return
    setImageBusy(true)
    const compressed = await Promise.all(files.map((f) => fileToCompressedDataUrl(f)))
    setImageBusy(false)
    const ok = compressed.filter((x): x is string => !!x)
    if (ok.length) setForm((f) => ({ ...f, images: [...(f.images ?? []), ...ok] }))
  }
  function removeImage(idx: number) {
    setForm((f) => ({ ...f, images: (f.images ?? []).filter((_, i) => i !== idx) }))
  }

  // ── Submit ──
  const createMutation = useMutation({
    mutationFn: () => buybackApi.createRecord(buildCreatePayload(form)),
    onSuccess: (data) => {
      setSubmitError(null)
      queryClient.invalidateQueries({ queryKey: ['buyback-records'] })
      if (embedded) onDone?.(data.record)
      else navigate(`/app/buyback/${data.record.id}`)
    },
    onError: (err: any) => setSubmitError(err?.data?.error || err?.message || 'Salvarea a eșuat'),
  })

  const updateMutation = useMutation({
    mutationFn: () =>
      buybackApi.updateRecord(editId as number, buildCreatePayload(form) as unknown as Partial<BuybackRecord>),
    onSuccess: () => {
      setSubmitError(null)
      queryClient.invalidateQueries({ queryKey: ['buyback-records'] })
      queryClient.invalidateQueries({ queryKey: ['buyback-record', editId] })
      navigate(`/app/buyback/${editId}`)
    },
    onError: (err: any) => setSubmitError(err?.data?.error || err?.message || 'Salvarea a eșuat'),
  })

  const mutation = isEdit ? updateMutation : createMutation

  function handleSubmit() {
    if (mutation.isPending) return
    if (!canSubmit) { setAttempted(true); return }
    mutation.mutate()
  }

  function handleBack() {
    if (embedded) onCancel?.()
    else navigate('/app/buyback')
  }

  const err = (bad: boolean) => attempted && bad

  return (
    <div className={cn('space-y-4', !embedded && 'max-w-3xl mx-auto p-4 md:p-6')}>
      <div className="flex items-center justify-between gap-2">
        <Button variant="ghost" size="sm" onClick={handleBack}>
          <ArrowLeft className="h-4 w-4 mr-1" />Înapoi
        </Button>
        <h1 className="text-lg font-semibold">{isEdit ? 'Corectează solicitarea' : 'Solicitare Preț BuyBack / TradeIn'}</h1>
        <div className="w-16" />
      </div>

      {submitError && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          {submitError}
        </div>
      )}

      {/* ── Header ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2"><Tag className="h-4 w-4" />Detalii Solicitare</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label className="text-xs">Consilier</Label>
            <Input
              value={form.advisor_name}
              readOnly
              disabled
              placeholder="Nume consilier"
              className="disabled:opacity-100 disabled:cursor-default bg-muted/40"
            />
            <p className="text-[11px] text-muted-foreground">Atribuit automat utilizatorului conectat.</p>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Achiziție de tip</Label>
            <Select
              value={form.acquisition_type}
              onValueChange={(v) => {
                set('acquisition_type', v)
                set('is_trade_in', v === 'tradein')
              }}
            >
              <SelectTrigger className="w-full"><SelectValue placeholder="Alege tipul" /></SelectTrigger>
              <SelectContent>
                {(opts?.acquisition_types ?? []).map((o) => (
                  <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Tip Client</Label>
            <Select value={form.client_type} onValueChange={(v) => set('client_type', v)}>
              <SelectTrigger className="w-full"><SelectValue placeholder="Alege tipul de client" /></SelectTrigger>
              <SelectContent>
                {(opts?.client_types ?? []).map((o) => (
                  <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Status TVA</Label>
            <Select value={form.vat_status} onValueChange={(v) => set('vat_status', v)}>
              <SelectTrigger className="w-full"><SelectValue placeholder="Alege statusul TVA" /></SelectTrigger>
              <SelectContent>
                {(opts?.vat_statuses ?? []).map((o) => (
                  <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* ── Vânzător ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2"><User className="h-4 w-4" />Vânzător</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {selectedClient && (
            <div className="rounded-md border bg-muted/30 p-3 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="rounded-md bg-secondary px-2.5 py-1 text-sm font-medium">
                    {selectedClient.display_name || selectedClient.name || `Client #${selectedClient.id}`}
                  </span>
                  <span className="rounded border px-2 py-0.5 text-[11px] text-muted-foreground">
                    {selectedClient.client_type === 'company' ? 'Firmă' : 'Persoană fizică'}
                  </span>
                </div>
                <Button variant="ghost" size="sm" onClick={clearClient}>
                  <X className="h-3.5 w-3.5 mr-1" />Schimbă
                </Button>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-x-4 gap-y-1 text-xs">
                <div><span className="text-muted-foreground">Telefon: </span>{selectedClient.phone || '—'}</div>
                <div><span className="text-muted-foreground">Email: </span>{selectedClient.email || '—'}</div>
                <div><span className="text-muted-foreground">CUI: </span>{selectedClient.cui || '—'}</div>
              </div>
            </div>
          )}

          {!selectedClient && !showNewClient && (
            <div className="space-y-2">
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  className="pl-9"
                  placeholder="Caută client (CRM) după nume sau telefon..."
                  value={clientQuery}
                  onChange={(e) => setClientQuery(e.target.value)}
                />
              </div>
              {isSearchingClients && <p className="text-xs text-muted-foreground">Se caută...</p>}
              {clientResults.length > 0 && (
                <div className="rounded-md border divide-y max-h-56 overflow-y-auto">
                  {clientResults.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      className="w-full text-left px-3 py-2 text-sm hover:bg-accent"
                      onClick={() => applyClient(c)}
                    >
                      <span className="font-medium">{c.display_name || c.name}</span>
                      {c.phone && <span className="text-muted-foreground"> — {c.phone}</span>}
                    </button>
                  ))}
                </div>
              )}
              <Button type="button" variant="outline" size="sm" className="border-dashed" onClick={() => setShowNewClient(true)}>
                Client nou
              </Button>
            </div>
          )}

          {!selectedClient && showNewClient && (
            <div className="space-y-2.5 rounded-md border bg-muted/30 p-3">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold uppercase text-muted-foreground">Client nou</p>
                <Button variant="ghost" size="sm" onClick={() => setShowNewClient(false)}>
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <Input placeholder="Nume complet *" value={newClientName} onChange={(e) => setNewClientName(e.target.value)} />
                <Input placeholder="Telefon * (+40...)" value={newClientPhone} onChange={(e) => setNewClientPhone(e.target.value)} />
                <Input placeholder="Email" value={newClientEmail} onChange={(e) => setNewClientEmail(e.target.value)} />
                {newClientIsCompany && (
                  <Input placeholder="CUI *" value={newClientCui} onChange={(e) => setNewClientCui(e.target.value)} />
                )}
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  checked={newClientIsCompany}
                  onCheckedChange={(v) => {
                    setNewClientIsCompany(v)
                    if (!v) setNewClientCui('')
                  }}
                />
                <Label className="text-xs">Persoană juridică (firmă)</Label>
              </div>
              {newClientError && <p className="text-xs text-destructive">{newClientError}</p>}
              <Button
                type="button"
                size="sm"
                disabled={!newClientName.trim() || !newClientPhone.trim() || (newClientIsCompany && !newClientCui.trim()) || createClientMutation.isPending}
                onClick={() => createClientMutation.mutate()}
              >
                {createClientMutation.isPending && <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />}
                Creează client
              </Button>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
            <div className="space-y-1.5">
              <Label className="text-xs">Nume vânzător</Label>
              <Input value={form.seller_name} onChange={(e) => set('seller_name', e.target.value)} placeholder="Nume și prenume" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Telefon</Label>
              <Input value={form.seller_phone} onChange={(e) => set('seller_phone', e.target.value)} placeholder="0721 234 567" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Email</Label>
              <Input value={form.seller_email} onChange={(e) => set('seller_email', e.target.value)} placeholder="email@exemplu.ro" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">CUI</Label>
              <Input value={form.seller_cui} onChange={(e) => set('seller_cui', e.target.value)} placeholder="CUI (dacă firmă)" />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Specificații Autovehicul ── */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle className="text-base flex items-center gap-2"><Car className="h-4 w-4" />Specificații Autovehicul</CardTitle>
            <div className="flex items-center gap-2">
              <input
                ref={civInputRef}
                type="file"
                accept="image/*,application/pdf"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) handleDecodeDocument(file, 'civ')
                  e.target.value = ''
                }}
              />
              <input
                ref={talonInputRef}
                type="file"
                accept="image/*,application/pdf"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) handleDecodeDocument(file, 'talon')
                  e.target.value = ''
                }}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={decoding !== null}
                onClick={() => civInputRef.current?.click()}
                title="Completează automat din poza/PDF-ul CIV-ului"
              >
                {decoding === 'civ' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <IdCard className="h-3.5 w-3.5" />}
                Importă CIV
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={decoding !== null}
                onClick={() => talonInputRef.current?.click()}
                title="Completează automat din poza/PDF-ul talonului"
              >
                {decoding === 'talon' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileText className="h-3.5 w-3.5" />}
                Importă talon
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Marca *</Label>
              <Autocomplete
                value={form.brand}
                onChange={(v) => set('brand', v)}
                onSelect={(v) => set('brand', v)}
                options={AUTOVIT_BRANDS as unknown as string[]}
                placeholder="BMW"
                allowCreate
                canonicalize
                invalid={err(!form.brand.trim())}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Model *</Label>
              <Autocomplete
                value={form.model}
                onChange={(v) => set('model', v)}
                onSelect={(v) => set('model', v)}
                options={AUTOVIT_MODELS[form.brand] ?? EMPTY_STRINGS}
                placeholder="320d"
                allowCreate
                canonicalize
                invalid={err(!form.model.trim())}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Varianta</Label>
              <Input value={form.variant} onChange={(e) => set('variant', e.target.value)} placeholder="Touring, Sport Line..." />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">VIN *</Label>
              <Input
                className={cn(vinTouched && !vinValid && 'border-destructive')}
                value={form.vin}
                onChange={(e) => set('vin', e.target.value.toUpperCase())}
                placeholder="17 caractere, fără I/O/Q"
                maxLength={17}
              />
              {vinTouched && !vinValid && (
                <p className="text-xs text-destructive">VIN invalid — trebuie să aibă exact 17 caractere (fără I, O, Q).</p>
              )}
            </div>
          </div>

          <div className="space-y-2">
            <Label className="text-xs">
              Echipare{selectedEquipment.size > 0 && <span className="text-muted-foreground"> · {selectedEquipment.size} selectate</span>}
            </Label>
            <div className="rounded-md border bg-muted/20 p-3 space-y-3 max-h-72 overflow-y-auto">
              {AUTOVIT_EQUIPMENT.map((group) => (
                <div key={group.category} className="space-y-2">
                  <h4 className="text-[11px] font-semibold uppercase text-muted-foreground">{group.category}</h4>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5">
                    {group.options.map((opt) => (
                      <div key={opt.value} className="flex items-center gap-2">
                        <Checkbox
                          id={`eq-${opt.value}`}
                          checked={selectedEquipment.has(opt.value)}
                          onCheckedChange={() => toggleEquipment(opt.value)}
                        />
                        <Label htmlFor={`eq-${opt.value}`} className="text-sm font-normal cursor-pointer">
                          {opt.label}
                        </Label>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Rulaj (km)</Label>
              <Input
                type="number"
                inputMode="numeric"
                min={0}
                value={form.mileage_km}
                onChange={(e) => set('mileage_km', e.target.value)}
                placeholder="85000"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Capacitate Cilindrică (cm³)</Label>
              <Input
                type="number"
                inputMode="numeric"
                min={0}
                value={form.engine_capacity_cm3}
                onChange={(e) => set('engine_capacity_cm3', e.target.value)}
                placeholder="1995"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Combustibil</Label>
              <Select value={form.fuel_type} onValueChange={(v) => set('fuel_type', v)}>
                <SelectTrigger className="w-full"><SelectValue placeholder="Alege combustibilul" /></SelectTrigger>
                <SelectContent>
                  {(opts?.fuel_types ?? []).map((o) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Transmisie</Label>
              <Select value={form.transmission} onValueChange={(v) => set('transmission', v)}>
                <SelectTrigger className="w-full"><SelectValue placeholder="Alege transmisia" /></SelectTrigger>
                <SelectContent>
                  {(opts?.transmissions ?? []).map((o) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Cutie de Viteze</Label>
              <Select value={form.gearbox} onValueChange={(v) => set('gearbox', v)}>
                <SelectTrigger className="w-full"><SelectValue placeholder="Alege cutia de viteze" /></SelectTrigger>
                <SelectContent>
                  {(opts?.gearboxes ?? []).map((o) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Nr. Chei</Label>
              <Input
                type="number"
                inputMode="numeric"
                min={0}
                value={form.keys_count}
                onChange={(e) => set('keys_count', e.target.value)}
                placeholder="2"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Data Fabricație</Label>
              <Input type="date" value={form.manufacture_date} onChange={(e) => set('manufacture_date', e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Data Prima Înmatriculare</Label>
              <Input type="date" value={form.first_registration_date} onChange={(e) => set('first_registration_date', e.target.value)} />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
            <div className="flex items-center justify-between rounded-md border p-2.5">
              <Label className="text-xs">Istoric Service la zi</Label>
              <Switch checked={!!form.service_history_uptodate} onCheckedChange={(v) => set('service_history_uptodate', v)} />
            </div>
            <div className="flex items-center justify-between rounded-md border p-2.5">
              <Label className="text-xs">Roți Extra</Label>
              <Switch checked={!!form.extra_wheels} onCheckedChange={(v) => set('extra_wheels', v)} />
            </div>
            <div className="flex items-center justify-between rounded-md border p-2.5">
              <Label className="text-xs">Daune</Label>
              <Switch checked={!!form.has_damage} onCheckedChange={(v) => set('has_damage', v)} />
            </div>
          </div>

          {form.has_damage && (
            <div className="space-y-1.5">
              <Label className="text-xs">Detalii Daune</Label>
              <Textarea value={form.damage_details} onChange={(e) => set('damage_details', e.target.value)} placeholder="Descrie daunele..." rows={2} />
            </div>
          )}

          <div className="space-y-1.5">
            <Label className="text-xs">Condiție Generală (1-5)</Label>
            <div className="flex gap-1.5">
              {[1, 2, 3, 4, 5].map((n) => (
                <Button
                  key={n}
                  type="button"
                  size="sm"
                  variant={String(form.general_condition) === String(n) ? 'default' : 'outline'}
                  onClick={() => set('general_condition', n)}
                >
                  {n}
                </Button>
              ))}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Imagini</Label>
            <div className="flex flex-wrap gap-2">
              {(form.images ?? []).map((src, idx) => (
                <div key={idx} className="relative">
                  <img src={src} alt={`Poză ${idx + 1}`} className="h-20 w-28 rounded-md object-cover border" />
                  <button
                    type="button"
                    aria-label="Șterge poza"
                    onClick={() => removeImage(idx)}
                    className="absolute -top-1.5 -right-1.5 rounded-full bg-destructive text-white p-0.5"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ))}
              <label className="flex h-20 w-28 cursor-pointer flex-col items-center justify-center gap-1 rounded-md border-2 border-dashed text-muted-foreground hover:bg-accent transition-colors">
                {imageBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ImagePlus className="h-4 w-4" />}
                <span className="text-xs font-medium">Adaugă</span>
                <input type="file" accept="image/*" multiple className="hidden" onChange={handleImageFiles} />
              </label>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Trade-in ── */}
      {form.acquisition_type === 'tradein' && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2"><Car className="h-4 w-4" />Vehicul Țintă (Trade-In)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Vehicul dorit (text liber)</Label>
              <Input
                value={form.target_vehicle_text}
                onChange={(e) => set('target_vehicle_text', e.target.value)}
                placeholder="ex: Renault Clio 2022, benzină, automat"
              />
            </div>

            {selectedTarget ? (
              <div className="flex items-center gap-2 flex-wrap">
                <span className="rounded-md bg-secondary px-3 py-1 text-sm">
                  {[selectedTarget.brand, selectedTarget.model, selectedTarget.nr_stoc].filter(Boolean).join(' · ')}
                </span>
                <Button variant="ghost" size="sm" onClick={clearTarget}>
                  <X className="h-3.5 w-3.5 mr-1" />Schimbă
                </Button>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="relative">
                  <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input
                    className="pl-9"
                    placeholder="Caută în stoc CarPark (marcă, model, VIN, nr. stoc)..."
                    value={targetQuery}
                    onChange={(e) => setTargetQuery(e.target.value)}
                  />
                </div>
                {isSearchingTargets && <p className="text-xs text-muted-foreground">Se caută...</p>}
                {targetResults.length > 0 && (
                  <div className="rounded-md border divide-y max-h-56 overflow-y-auto">
                    {targetResults.map((v) => (
                      <button
                        key={v.id}
                        type="button"
                        className="w-full text-left px-3 py-2 text-sm hover:bg-accent"
                        onClick={() => applyTarget(v)}
                      >
                        <span className="font-medium">{v.brand} {v.model}</span>
                        {v.nr_stoc && <span className="text-muted-foreground"> — {v.nr_stoc}</span>}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Așteptări Client ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2"><Euro className="h-4 w-4" />Așteptări Client</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Preț solicitat (€)</Label>
              <Input
                type="number"
                inputMode="numeric"
                min={0}
                value={form.client_asking_price_eur}
                onChange={(e) => set('client_asking_price_eur', e.target.value)}
                placeholder="9500"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Sursă</Label>
              <Select value={form.client_source} onValueChange={(v) => set('client_source', v)}>
                <SelectTrigger className="w-full"><SelectValue placeholder="Alege sursa" /></SelectTrigger>
                <SelectContent>
                  {(opts?.client_sources ?? []).map((o) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Alte Detalii</Label>
            <Textarea value={form.other_details} onChange={(e) => set('other_details', e.target.value)} rows={2} />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Drive Folder Link</Label>
            <Input value={form.drive_folder_link} onChange={(e) => set('drive_folder_link', e.target.value)} placeholder="https://drive.google.com/..." />
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end gap-2 pb-8">
        <Button variant="outline" onClick={handleBack}>Anulează</Button>
        <Button onClick={handleSubmit} disabled={mutation.isPending || !canSubmit}>
          {mutation.isPending && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
          {isEdit ? 'Salvează modificările' : 'Trimite Solicitarea'}
        </Button>
      </div>
    </div>
  )
}
