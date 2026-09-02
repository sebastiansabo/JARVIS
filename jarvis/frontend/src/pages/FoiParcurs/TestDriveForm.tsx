import { useState, useEffect, useCallback, useMemo, useRef, lazy, Suspense } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { foiParcursApi } from '@/api/foiParcurs'
import { crmApi, type ClientContact } from '@/api/crm'
import { toast } from 'sonner'
import { useAuthStore } from '@/stores/authStore'
import { cn } from '@/lib/utils'
import { fileToCompressedDataUrl } from '@/lib/imageCompress'
import { useVehicleConflicts } from '@/hooks/useVehicleConflicts'
import {
  usesFuelTank,
  usesBattery,
  LOCKOUT_LABELS,
  type FuelGaugeLevel,
  type CrmClient,
  type FpVehicle,
  type FpVehicleInspection,
  type TestDriveFormPayload,
  type PlanTestDrivePayload,
  type ActivateTestDrivePayload,
  type VehicleConflict,
  type FoiContract,
  type MktProject,
} from '@/types/foiParcurs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Car,
  Search,
  IdCard,
  Fuel,
  ShieldCheck,
  PenLine,
  CheckCircle2,
  ArrowLeft,
  Plus,
  ClipboardCheck,
  Loader2,
  X,
  UserPlus,
  Trash2,
  ImagePlus,
  ChevronDown,
  FileText,
  AlertTriangle,
  CalendarPlus,
  PlayCircle,
  Megaphone,
  Pencil,
  Save,
  Wallet,
} from 'lucide-react'
import { CreateClientPanel, DriverLicenseSection } from './CreateClientPanel'
import {
  DamageReport,
  makeEmptyDamageState,
  toDamagePayload,
  fromDamagePayload,
  type DamageState,
} from './testDriveDamage'
import { ConflictDialog } from './ConflictDialog'
import { isCompanyClientLike } from './companyClient'
import { contextFromSearch, type DocType } from './documentType'

const SignatureCanvas = lazy(() => import('@/components/shared/SignatureCanvas'))

const ADVISOR_SIG_KEY = 'fp_advisor_signature'

const FUEL_START_OPTIONS: { label: string; value: FuelGaugeLevel }[] = [
  { label: 'Plin (1)', value: '1' },
  { label: '2/3', value: '2/3' },
  { label: '1/2', value: '1/2' },
  { label: '1/4', value: '1/4' },
]

// ── datetime-local helpers (local time, no tz suffix) ──
function localDatetimeValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function useDebounce(value: string, delay: number) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

/** Join a client's address parts (street, city, region) into a display string. */
function clientAddress(c: CrmClient | null): string {
  if (!c) return ''
  return [c.street, c.city, c.region].map((x) => (x || '').trim()).filter(Boolean).join(', ')
}

interface TestDriveFormProps {
  embedded?: boolean
  activateId?: number
  /** Edit a PLANNED draft in place (Corectează on a not-started session) —
   *  loads + prefills like activation but saves via PUT /plan without starting. */
  editId?: number
  initialCompanyId?: number
  /** Seed the departure datetime ("YYYY-MM-DDTHH:MM"), e.g. from a calendar
   *  slot the user dragged/clicked. Return defaults to +1h. Ignored in
   *  activation mode, which prefills from the loaded draft instead. */
  initialDeparture?: string
  /** Seed the return datetime ("YYYY-MM-DDTHH:MM") — set for multi-day drags so
   *  a 2–3 day session prefills the arrival on a later day. */
  initialReturn?: string
  onDone?: (contract: FoiContract) => void
  onCancel?: () => void
  /** Seed the document context when the form is mounted without a URL to carry
   *  `?context=service` (e.g. the Hub courtesy overlay). The standalone route
   *  keeps using `?context=`; this prop is the equivalent for inline mounts.
   *  Activation still prefers the loaded draft's own frozen document_type. */
  initialDocumentType?: DocType
}

// ── Component ──
export default function TestDriveForm({ embedded, activateId: activateIdProp, editId: editIdProp, initialCompanyId, initialDeparture, initialReturn, onDone, onCancel, initialDocumentType }: TestDriveFormProps = {}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const isAdmin = ['admin', 'superadmin'].includes((user?.role_name ?? '').toLowerCase())
  const [openBlock, setOpenBlock] = useState<{ message: string; retry: () => void } | null>(null)

  // ── Activation mode — reopens this form pre-filled from a PLANNED draft ──
  const [searchParams] = useSearchParams()
  const activateId = activateIdProp ?? (searchParams.get('activate') ? Number(searchParams.get('activate')) : null)
  const isActivating = activateId != null
  // ── Edit mode — reopens this form pre-filled from a PLANNED draft, saving in
  //    place (PUT /plan) without starting it. Loads/prefills exactly like
  //    activation (via draftLoadId); only the save action + button differ. ──
  const editId = editIdProp ?? (searchParams.get('edit') ? Number(searchParams.get('edit')) : null)
  const isEditing = editId != null
  const draftLoadId = activateId ?? editId

  // Service context (Task 13) — the standalone route deep-links with
  // `?context=service` (Task 12); anything else defaults to 'sales'. The
  // `?activate=` deep link (and the activateId prop) carry NO context param,
  // so during activation the URL alone always reads 'sales'. But the PLANNED
  // draft being activated already stores its own document_type server-side
  // (frozen at plan time), so once the draft row loads we prefer THAT — this
  // is what makes Service activations render the "Sumar închiriere" card,
  // send the svc_* pricing snapshot, and relabel the form (Task 13). Falls
  // back to the URL context on a fresh create or before the draft loads.
  // Base (pre-activation) context: an explicit prop wins (inline mounts like the
  // Hub courtesy overlay that can't carry a URL param), else the URL `?context=`.
  const urlDocumentType: DocType = initialDocumentType ?? contextFromSearch(searchParams.toString() ? `?${searchParams.toString()}` : window.location.search)
  const [serviceOrderRef, setServiceOrderRef] = useState('')

  // Company & vehicle
  const [companyId, setCompanyId] = useState<number | null>(null)
  const [vehicleId, setVehicleId] = useState<number | null>(null)
  const [selectedVehicle, setSelectedVehicle] = useState<FpVehicle | null>(null)

  // Embedded mode may seed the company from the caller (e.g. Hub panel) — only
  // when not already set by the user/route, and only once a value is provided.
  useEffect(() => { if (initialCompanyId && companyId == null) setCompanyId(initialCompanyId) }, [initialCompanyId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Client (CRM)
  const [clientSearch, setClientSearch] = useState('')
  const debouncedSearch = useDebounce(clientSearch, 350)
  const [selectedClient, setSelectedClient] = useState<CrmClient | null>(null)
  const [showManualCreate, setShowManualCreate] = useState(false)

  // Company-client driver gate (Task 11): a company client never drives
  // itself — the backend hard-blocks a live FILLED submit and an activation
  // of a company session without a gate-valid driver_contact_id (see the
  // contacts query + gate below). Not required for a PLANNED draft.
  const [driverContact, setDriverContact] = useState<ClientContact | null>(null)
  const [showAddContact, setShowAddContact] = useState(false)
  // Edit the selected contact person in place (name/email/phone + licence) —
  // reuses ContactForm in edit mode so a company's driver with incomplete data
  // can be completed without deleting and recreating the contact.
  const [editingContact, setEditingContact] = useState(false)

  // Campaign / event (optional marketing project) — type-to-search, like mobile
  const [mktProject, setMktProject] = useState<MktProject | null>(null)
  const [projectSearch, setProjectSearch] = useState('')
  const debouncedProjectSearch = useDebounce(projectSearch, 350)

  // HR event (Task 15) — mutually exclusive with the campaign/mktProject
  // above; the "Este eveniment" checkbox switches the card between the two.
  const [isEvent, setIsEvent] = useState(false)
  const [eventId, setEventId] = useState<number | null>(null)
  const [eventName, setEventName] = useState('')
  const [eventSearch, setEventSearch] = useState('')
  const debouncedEventSearch = useDebounce(eventSearch, 350)
  const [showAddEvent, setShowAddEvent] = useState(false)

  // Driver license
  const [driverLicensePhoto, setDriverLicensePhoto] = useState<string | null>(null)
  const [driverLicenseNumber, setDriverLicenseNumber] = useState('')
  const [driverLicenseExpiry, setDriverLicenseExpiry] = useState('')

  // Trip
  // Seed the departure slot from the prop (Hub overlay) or the ?departure=
  // search param (desktop calendar route) — both are "YYYY-MM-DDTHH:MM".
  const seedDeparture = initialDeparture ?? searchParams.get('departure') ?? undefined
  const seedReturn = initialReturn ?? searchParams.get('return') ?? undefined
  const [departureDatetime, setDepartureDatetime] = useState(() => seedDeparture ?? localDatetimeValue(new Date()))
  const [returnDatetime, setReturnDatetime] = useState(() => {
    if (seedReturn) return seedReturn
    const base = seedDeparture ? new Date(seedDeparture) : new Date()
    return localDatetimeValue(new Date(base.getTime() + 60 * 60 * 1000))
  })
  const [odometerStart, setOdometerStart] = useState('')
  const [estimatedKm, setEstimatedKm] = useState('')
  const [fuelGaugeStart, setFuelGaugeStart] = useState<FuelGaugeLevel | ''>('')
  const [generalObservation, setGeneralObservation] = useState('')

  // Service (Mașini de curtoazie) rental-pricing snapshot (S6b) — auto-filled
  // by the /service-pricing preview once a vehicle + both dates are chosen;
  // the advisor may override any field before submit/plan. Strings so the
  // inputs can be genuinely blank; re-synced (overwritten) whenever a fresh
  // preview arrives for the current vehicle/dates (see the effect below).
  const [svcRateBasis, setSvcRateBasis] = useState<'day' | 'month' | ''>('')
  const [svcTariffEur, setSvcTariffEur] = useState('')
  const [svcUnits, setSvcUnits] = useState('')
  const [svcTotalEur, setSvcTotalEur] = useState('')
  const [svcKmIncludedDay, setSvcKmIncludedDay] = useState('')
  const [svcExtraKmEur, setSvcExtraKmEur] = useState('')
  const [svcGarantieEur, setSvcGarantieEur] = useState('')
  const [svcFransizaEur, setSvcFransizaEur] = useState('')
  // Latches true once the draft-prefill effect below restores a saved pricing
  // snapshot from an activated draft's contract (draftData.contract) — the
  // advisor's quoted/frozen price at planning time. Prevents the auto-preview
  // effect further down from silently clobbering that snapshot with a fresh
  // recompute (see C1: activation must not overwrite a frozen/overridden
  // rental price). Stays false — so the preview auto-applies as before — for
  // a fresh (non-activation) create, or when the draft never had a snapshot.
  const svcPrefilledFromDraftRef = useRef(false)

  // Advisor & signatures
  const [advisorName, setAdvisorName] = useState(user?.name ?? '')
  const [clientSignature, setClientSignature] = useState('')
  const [advisorSignature, setAdvisorSignature] = useState('')

  // Damage (departure)
  const [showDamage, setShowDamage] = useState(false)
  const [departureDamage, setDepartureDamage] = useState<DamageState>(makeEmptyDamageState)

  // Compliance
  const [gdprConsent, setGdprConsent] = useState(false)
  const [inspectionAcceptance, setInspectionAcceptance] = useState(false)
  const [conditionsAccepted, setConditionsAccepted] = useState(false)
  const [showConditions, setShowConditions] = useState(false)

  const [submittedContract, setSubmittedContract] = useState<FoiContract | null>(null)
  // Which action was attempted, so red-flagging is scoped to what that action
  // actually requires: 'plan' flags only the minimal draft fields
  // (car/client/dates), while 'submit'/'activate' flag the full activation set.
  // Mirrors the mobile app — planning a draft never demands KM/fuel/signature/
  // license/GDPR.
  const [attemptedAction, setAttemptedAction] = useState<null | 'plan' | 'submit' | 'activate'>(null)
  const attempted = attemptedAction !== null
  const submitAttempt = attemptedAction === 'submit' || attemptedAction === 'activate'

  useEffect(() => {
    if (user?.name && !advisorName) setAdvisorName(user.name)
  }, [user?.name]) // eslint-disable-line react-hooks/exhaustive-deps

  // Load a persisted advisor signature (reused across submissions, like mobile)
  useEffect(() => {
    try {
      const saved = localStorage.getItem(ADVISOR_SIG_KEY)
      if (saved) setAdvisorSignature(saved)
    } catch { /* ignore */ }
  }, [])

  // ── Queries ──
  // Load the PLANNED draft being activated FIRST — its stored document_type
  // drives `documentType` below (used by the vehicle/pricing queries right
  // after), so it must resolve before them. Only depends on activateId.
  const { data: draftData, isLoading: loadingDraft } = useQuery({
    queryKey: ['fp-test-drive', draftLoadId],
    queryFn: () => foiParcursApi.getTestDrive(draftLoadId!),
    enabled: draftLoadId != null,
  })

  // The effective document context. On a fresh create it's the URL context
  // (Service route deep-links `?context=service`). On an activation the URL
  // carries no context, so we prefer the loaded draft's own frozen
  // document_type — this is what makes a Service activation render the rental
  // card, send the svc_* pricing snapshot on activate, and relabel the form.
  // Before the draft loads it falls back to the URL context ('sales'), then
  // flips to 'service' once draftData arrives (the draft-prefill effect
  // restores the frozen pricing snapshot at that same point).
  const _draftDocType = draftData?.contract?.document_type as DocType | undefined
  const documentType: DocType = ((isActivating || isEditing) && _draftDocType && _draftDocType !== 'sales')
    ? _draftDocType
    : urlDocumentType

  // Whether the current document type is a rental (rent-a-car) type — drives the
  // pricing preview, svc_* payload and the "Predă mașina" labels. Non-rental and
  // sales types show the plain test-drive UI.
  const { data: _docTypesData } = useQuery({
    queryKey: ['fp-document-types', companyId],
    queryFn: () => foiParcursApi.getDocumentTypes(companyId!),
    enabled: !!companyId,
    staleTime: 30_000,
  })
  const isRental = !!_docTypesData?.types.find((t) => t.key === documentType)?.is_rental

  const { data: companiesData } = useQuery({
    queryKey: ['fp-companies'],
    queryFn: () => foiParcursApi.getCompanies(),
  })
  const companies = companiesData?.companies ?? []

  // Fetch ALL vehicles (incl. archived + blocked) under a distinct key so we
  // don't collide with the active-only ['fp-vehicles'] cache other views use.
  const { data: vehiclesData } = useQuery({
    queryKey: ['fp-vehicles', 'all', documentType],
    queryFn: () => foiParcursApi.getVehicles(false, documentType),
  })
  const allVehicles = vehiclesData?.vehicles ?? []
  const vehiclesForCompany = useMemo(
    () => (companyId ? allVehicles.filter((v) => v.company_id === companyId) : []),
    [allVehicles, companyId],
  )
  // Default picker hides archived (is_active=false) + blocked cars; a toggle
  // reveals them (selectable, badged). Blocked cars require a confirm (below).
  const [showAllVehicles, setShowAllVehicles] = useState(false)
  const visibleVehicles = useMemo(() => {
    const base = showAllVehicles
      ? vehiclesForCompany
      : vehiclesForCompany.filter((v) => v.is_active !== false && !v.locked_out && !v.blocked_now)
    // Keep the currently-selected car in the list even if it's hidden by the
    // toggle (a blocked car selected earlier) OR belongs to another company
    // (an activation prefill can resolve a vehicle whose company differs from
    // the contract's) — otherwise the Select has no matching item and renders
    // an empty trigger. Fall back to `selectedVehicle` itself when it isn't in
    // vehiclesForCompany.
    if (selectedVehicle && !base.some((v) => v.id === selectedVehicle.id)) {
      const sel = vehiclesForCompany.find((v) => v.id === selectedVehicle.id) ?? selectedVehicle
      return [sel, ...base]
    }
    return base
  }, [vehiclesForCompany, showAllVehicles, selectedVehicle])
  const hasHiddenVehicles = useMemo(
    () => vehiclesForCompany.some((v) => v.is_active === false || v.locked_out || v.blocked_now),
    [vehiclesForCompany],
  )
  const [pendingLockedVehicle, setPendingLockedVehicle] = useState<FpVehicle | null>(null)

  // Configurable lockout-reason labels (slug → label) for the blocked badge.
  const { data: lockoutReasonsData } = useQuery({
    queryKey: ['fp-lockout-reasons', 'all'],
    queryFn: () => foiParcursApi.getLockoutReasons(false),
    staleTime: 60_000,
  })
  const reasonLabel = useMemo(() => {
    const map: Record<string, string> = { ...LOCKOUT_LABELS }
    for (const r of lockoutReasonsData?.reasons ?? []) map[r.slug] = r.label
    return (slug?: string | null) => (slug ? (map[slug] ?? slug) : '')
  }, [lockoutReasonsData])

  // ── Prefill the PLANNED draft being activated (loaded above, before
  //    documentType, since its document_type feeds that derivation) ──
  // GET /test-drive/{id} denormalizes client_name/client_phone onto the
  // contract but not client_type — needed to tell a company client (which
  // must gate on a driver contact, see below) from a person client while
  // activating a PLANNED draft. Fetched only in activation mode.
  const draftClientId = draftData?.contract?.client_id ?? null
  const { data: draftClientData } = useQuery({
    queryKey: ['fp-draft-client', draftClientId],
    queryFn: () => crmApi.getClient(draftClientId!),
    enabled: (isActivating || isEditing) && draftClientId != null,
  })

  useEffect(() => {
    const c = draftData?.contract
    if (!c || c.status !== 'PLANNED') return
    setCompanyId(c.company_id)
    setDepartureDatetime(c.departure_datetime ? c.departure_datetime.slice(0, 16) : localDatetimeValue(new Date()))
    setReturnDatetime(c.return_datetime ? c.return_datetime.slice(0, 16) : localDatetimeValue(new Date(Date.now() + 60 * 60 * 1000)))
    setOdometerStart(String(c.km_start ?? ''))
    setEstimatedKm(String(c.distance_km ?? ''))
    setFuelGaugeStart((c.fuel_gauge_start_level as FuelGaugeLevel) || '')
    setAdvisorName(c.advisor_name || '')
    setGeneralObservation(c.general_observation ?? '')
    setDepartureDamage(fromDamagePayload(c.departure_damage))
    if (c.client_id && c.client_name) {
      setSelectedClient({ id: c.client_id, display_name: c.client_name, phone: c.client_phone ?? null })
    }
    // Event/campaign are mutually exclusive in the UI (the checkbox handler
    // enforces it), but an event-tagged draft ALSO carries a backend-bridged
    // mkt_project_id (submit auto-links a marketing project when event_id is
    // set). Prefill event-first so reopening such a draft never leaves BOTH
    // eventId and mktProject non-null (which would break the invariant).
    if (c.event_id) {
      setIsEvent(true); setEventId(c.event_id); setEventName(c.event_name ?? '')
    } else if (c.mkt_project_id) {
      setMktProject({ id: c.mkt_project_id, name: c.mkt_project_name ?? null })
    }
    // C1 fix: restore the frozen/overridden Service rental-pricing snapshot
    // from the draft itself. Without this, svc_* state starts blank and the
    // auto-preview effect (below) fills it with a FRESH recompute, silently
    // discarding whatever price the advisor quoted/overrode at planning time
    // once activation persists it. Only restore when the draft actually
    // carries a snapshot (older/blank drafts leave the fields blank, so the
    // preview still auto-fills them as before).
    const hasSvcSnapshot = c.svc_total_eur != null || c.svc_tariff_eur != null || c.svc_rate_basis != null
    if (hasSvcSnapshot) {
      setSvcRateBasis((c.svc_rate_basis as 'day' | 'month' | null) || '')
      setSvcTariffEur(c.svc_tariff_eur != null ? String(c.svc_tariff_eur) : '')
      setSvcUnits(c.svc_units != null ? String(c.svc_units) : '')
      setSvcTotalEur(c.svc_total_eur != null ? String(c.svc_total_eur) : '')
      setSvcKmIncludedDay(c.svc_km_included_day != null ? String(c.svc_km_included_day) : '')
      setSvcExtraKmEur(c.svc_extra_km_eur != null ? String(c.svc_extra_km_eur) : '')
      setSvcGarantieEur(c.svc_garantie_eur != null ? String(c.svc_garantie_eur) : '')
      setSvcFransizaEur(c.svc_fransiza_eur != null ? String(c.svc_fransiza_eur) : '')
      svcPrefilledFromDraftRef.current = true
    }
  }, [draftData]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const c = draftData?.contract
    if (!c || c.status !== 'PLANNED' || !allVehicles.length) return
    const v = allVehicles.find((x) => x.vin === c.vin)
    // Resolve the vehicle by VIN across ALL companies, then align companyId to
    // the vehicle's own company. The scalar effect above seeds companyId from
    // the contract, but a PLANNED session can carry a vehicle registered under
    // a different company; keeping companyId = contract's would filter that car
    // out of the picker and leave the Vehicul Select empty. This runs after
    // allVehicles loads, so its setCompanyId wins.
    if (v) {
      setVehicleId(v.id)
      setSelectedVehicle(v)
      if (v.company_id) setCompanyId(v.company_id)
    }
  }, [draftData, allVehicles])

  // Patch client_type onto the prefilled draft client once the lookup above
  // resolves — only then can isCompanyClient (below) correctly gate the
  // contact picker/gate for an activation of a company-client draft.
  useEffect(() => {
    const c = draftClientData?.client
    if (!c) return
    setSelectedClient((prev) => (prev && String(prev.id) === String(c.id)
      ? { ...prev, client_type: c.client_type, cui: c.cui, nr_reg: c.nr_reg, email: c.email }
      : prev))
  }, [draftClientData])

  const { data: inspectionData } = useQuery({
    queryKey: ['fp-inspection', vehicleId],
    queryFn: () => foiParcursApi.getLatestInspection(vehicleId!),
    enabled: !!vehicleId,
  })
  const latestInspection: FpVehicleInspection | null = inspectionData?.inspection ?? null

  // ── Per company+vehicle-brand general-conditions text ('' when unset ⇒
  //    acceptance not shown/required). Required for live submit + activation,
  //    deferred for a PLANNED draft (mirrors the backend). ──
  const { data: gcData } = useQuery({
    queryKey: ['fp-general-conditions', companyId, selectedVehicle?.vin, documentType],
    queryFn: () => foiParcursApi.getGeneralConditions(companyId!, selectedVehicle!.vin, documentType),
    enabled: !!companyId && !!selectedVehicle?.vin,
    staleTime: 60_000,
  })
  const generalConditions = (gcData?.text ?? '').trim()
  const conditionsRequired = generalConditions.length > 0

  // ── Service (Mașini de curtoazie) rental-pricing preview — Service context
  // only. Debounced so the datetime-local inputs don't refetch on every
  // keystroke; the fetched snapshot pre-fills the editable "Sumar închiriere"
  // card below (see the effect right after this query). ──
  const debouncedSvcDeparture = useDebounce(departureDatetime, 400)
  const debouncedSvcReturn = useDebounce(returnDatetime, 400)
  const svcPricingEnabled = isRental && !!companyId && !!selectedVehicle?.vin
    && !!debouncedSvcDeparture && !!debouncedSvcReturn
  const { data: svcPricingData, isFetching: svcPricingLoading } = useQuery({
    queryKey: ['fp-service-pricing', companyId, selectedVehicle?.vin, debouncedSvcDeparture, debouncedSvcReturn],
    queryFn: () => foiParcursApi.getServicePricing(companyId!, selectedVehicle!.vin, debouncedSvcDeparture, debouncedSvcReturn),
    enabled: svcPricingEnabled,
  })
  // Re-syncs (overwrites) the editable fields whenever a fresh preview
  // arrives — i.e. whenever the vehicle or either date changes. The advisor's
  // edits stick until then, matching how the draft-prefill effect above
  // behaves on reload.
  //
  // C1 fix: when activating a PLANNED draft that already restored a frozen/
  // overridden pricing snapshot (svcPrefilledFromDraftRef, set by the effect
  // above), this auto-apply must NOT run — a fresh recompute here would
  // silently discard the advisor's planning-time price. It only auto-applies
  // on a genuinely fresh create, or when the draft never had a snapshot to
  // restore in the first place.
  useEffect(() => {
    const p = svcPricingData?.pricing
    if (!p) return
    if (svcPrefilledFromDraftRef.current) return
    setSvcRateBasis(p.svc_rate_basis)
    setSvcTariffEur(String(p.svc_tariff_eur))
    setSvcUnits(String(p.svc_units))
    setSvcTotalEur(String(p.svc_total_eur))
    setSvcKmIncludedDay(p.svc_km_included_day != null ? String(p.svc_km_included_day) : '')
    setSvcExtraKmEur(p.svc_extra_km_eur != null ? String(p.svc_extra_km_eur) : '')
    setSvcGarantieEur(p.svc_garantie_eur != null ? String(p.svc_garantie_eur) : '')
    setSvcFransizaEur(p.svc_fransiza_eur != null ? String(p.svc_fransiza_eur) : '')
  }, [svcPricingData])

  // Keep Total = Tarif × Nr. (units) consistent by default: recomputed live
  // from the Tarif/Nr. onChange handlers so a forgotten Total can't silently
  // desync the money-facing snapshot. Total stays editable — an explicit edit
  // afterwards is a legitimate per-key override the backend honors. Non-numeric
  // Tarif/Nr. → Total left as-is.
  const recomputeSvcTotal = (tarifStr: string, unitsStr: string) => {
    const tarif = Number(tarifStr)
    const units = Number(unitsStr)
    if (tarifStr.trim() === '' || unitsStr.trim() === '' || Number.isNaN(tarif) || Number.isNaN(units)) return
    setSvcTotalEur(String(Math.round(tarif * units * 100) / 100))
  }

  // Only sent when documentType is 'service' — the (possibly advisor-
  // overridden) rental snapshot, spread onto the submit/plan/activate
  // payloads. Backend treats any non-null value here as an explicit
  // per-key override of its own compute_service_pricing result.
  const svcPricingPayload = isRental ? {
    ...(svcRateBasis ? { svc_rate_basis: svcRateBasis } : {}),
    ...(svcTariffEur.trim() !== '' ? { svc_tariff_eur: Number(svcTariffEur) } : {}),
    ...(svcUnits.trim() !== '' ? { svc_units: Number(svcUnits) } : {}),
    ...(svcTotalEur.trim() !== '' ? { svc_total_eur: Number(svcTotalEur) } : {}),
    ...(svcKmIncludedDay.trim() !== '' ? { svc_km_included_day: Number(svcKmIncludedDay) } : {}),
    ...(svcExtraKmEur.trim() !== '' ? { svc_extra_km_eur: Number(svcExtraKmEur) } : {}),
    ...(svcGarantieEur.trim() !== '' ? { svc_garantie_eur: Number(svcGarantieEur) } : {}),
    ...(svcFransizaEur.trim() !== '' ? { svc_fransiza_eur: Number(svcFransizaEur) } : {}),
  } : {}

  const { data: clientSearchData, isFetching: isSearching } = useQuery({
    queryKey: ['fp-crm-search', debouncedSearch],
    queryFn: () => foiParcursApi.searchCrmClients(debouncedSearch, 20),
    enabled: debouncedSearch.trim().length >= 2 && !selectedClient,
  })
  const clientResults = clientSearchData?.clients ?? []

  // ── Company-client contact person (Task 11 hard gate) ──
  // A company client (client_type==='company') never drives itself — the
  // backend hard-blocks a live FILLED submit and an activation of a company
  // session without a gate-valid driver_contact_id (crm/repositories/
  // contact_repository.py: contact_gate_valid / GATE_FIELDS). Mirrored here
  // with the SAME six fields so the client-side gate never disagrees with
  // the server. A PLANNED draft is NOT gated (mirrors the server: the gate
  // only applies to a live FILLED submit and to activation).
  const isCompanyClient = isCompanyClientLike(selectedClient)
  // retry:false + error surfaced inline mirrors the HR-event search query
  // below (eventSearchForbidden) — the contacts route is now login-only
  // (see crm/routes/clients.py) but a 403 can still happen for other
  // reasons; silently retrying and landing on an empty list left the gate
  // permanently blocked with no hint to the advisor.
  const { data: contactsData, error: contactsErr } = useQuery({
    queryKey: ['client-contacts', selectedClient?.id],
    queryFn: () => crmApi.listClientContacts(Number(selectedClient!.id)),
    enabled: !!selectedClient && isCompanyClient,
    retry: false,
  })
  const contacts = contactsData?.contacts ?? []
  const contactsForbidden = (contactsErr as any)?.status === 403
  const contactsErrored = !!contactsErr
  // Delete a contact person. The backend blocks (409) a contact who is the
  // driver on an active session; that message is surfaced via toast.
  const deleteContactMutation = useMutation({
    mutationFn: (contactId: number) => crmApi.deleteClientContact(Number(selectedClient!.id), contactId),
    onSuccess: (_r, contactId) => {
      queryClient.invalidateQueries({ queryKey: ['client-contacts', selectedClient?.id] })
      if (driverContact?.id === contactId) setDriverContact(null)
      toast.success('Persoană de contact ștearsă')
    },
    onError: (e: any) => toast.error(e?.data?.error || e?.message || 'Ștergerea a eșuat'),
  })
  // Edit mode: prefill the current driver contact from the draft so the picker
  // shows who's already assigned (activation leaves this choice to the advisor).
  useEffect(() => {
    if (!isEditing) return
    const dcid = draftData?.contract?.driver_contact_id
    if (!dcid || !contacts.length) return
    setDriverContact((prev) => prev ?? contacts.find((x) => x.id === dcid) ?? null)
  }, [isEditing, draftData, contacts])
  // Keep the currently-selected contact in the option list even if the query
  // cache hasn't caught up yet (e.g. a just-created contact whose invalidation
  // refetch is still in flight) — otherwise the Select trigger has no matching
  // item and renders blank. Mirrors the visibleVehicles pattern above.
  const contactOptions = driverContact && !contacts.some((c) => String(c.id) === String(driverContact.id))
    ? [driverContact, ...contacts]
    : contacts
  const contactGateFields = (c: ClientContact | null) =>
    !!c && !!c.full_name && !!c.email && !!c.phone && !!c.driver_license_photo &&
    !!c.driver_license_number
  const contactGateOk = !isCompanyClient || contactGateFields(driverContact)

  // A contact selected for a previous client must never leak into a new
  // selection — reset whenever the selected client changes (including the
  // "Schimbă" → null step before a new pick).
  useEffect(() => {
    setDriverContact(null)
  }, [selectedClient?.id])

  // Auto-select the primary (or first) contact once the list loads.
  useEffect(() => {
    if (isCompanyClient && !driverContact && contacts.length) {
      setDriverContact(contacts.find((c) => c.is_primary) ?? contacts[0])
    }
  }, [isCompanyClient, contacts, driverContact])

  // ── Full client hydration + inline edit (Client card) ──
  // The search row is lean; fetch the full CRM record so the card can show all
  // data (email, address, …) and prefill the edit form. Merge missing fields
  // into selectedClient once, guarded so it never loops.
  const [editingClient, setEditingClient] = useState(false)
  const { data: clientFullData } = useQuery({
    queryKey: ['fp-client-full', selectedClient?.id],
    queryFn: () => crmApi.getClient(Number(selectedClient!.id)),
    enabled: !!selectedClient?.id,
  })
  useEffect(() => {
    const c = clientFullData?.client
    if (!c) return
    setSelectedClient((prev) => {
      if (!prev || String(prev.id) !== String(c.id)) return prev
      // Full record fills in fields the lean search row lacked (email, address…).
      const merged: CrmClient = { ...prev, ...c }
      // Only re-set state if something actually changed (avoids a render loop).
      return JSON.stringify(merged) === JSON.stringify(prev) ? prev : merged
    })
  }, [clientFullData])

  // Campaign search — type-to-search (>=2 chars), not scoped by company
  // (matches the mobile form). Optional field, nothing gates on it. Only
  // active in the non-event branch of the Campanie/Eveniment card (isEvent
  // false); the Eveniment checkbox switches to the HR-event search below.
  const { data: projectSearchData, isFetching: isSearchingProjects } = useQuery({
    queryKey: ['fp-mkt-project-search', debouncedProjectSearch],
    queryFn: () => foiParcursApi.searchMktProjects(debouncedProjectSearch, undefined, 20),
    enabled: !isEvent && debouncedProjectSearch.trim().length >= 2 && !mktProject,
  })
  const projectResults = projectSearchData?.projects ?? []

  // HR-event search (Task 15) — mirrors the campaign search above but hits a
  // separate HR/marketing-gated endpoint that a driving advisor may lack
  // permission for; a 403 is surfaced inline (eventSearchForbidden) rather
  // than crashing the form.
  const {
    data: eventSearchData,
    isFetching: isSearchingEvents,
    error: eventSearchErr,
  } = useQuery({
    queryKey: ['fp-hr-event-search', debouncedEventSearch],
    queryFn: () => foiParcursApi.searchHrEvents(debouncedEventSearch, 20),
    enabled: isEvent && debouncedEventSearch.trim().length >= 2 && eventId == null,
    retry: false,
  })
  const eventResults = eventSearchData?.events ?? []
  // Only allow picking events that haven't finished yet — no past events. Dates
  // are ISO YYYY-MM-DD (DB date column) so a lexicographic compare against
  // today (local) is safe; an event with no dates at all stays selectable.
  const todayISO = (() => {
    const n = new Date()
    return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}-${String(n.getDate()).padStart(2, '0')}`
  })()
  const upcomingEvents = eventResults.filter((e) => {
    const d = e.end_date || e.start_date
    return !d || d >= todayISO
  })
  const eventSearchForbidden = (eventSearchErr as any)?.status === 403
  // Any non-403 search failure (500/network) — distinct from an empty result
  // set, so we don't mislabel a failed search as "no events found".
  const eventSearchFailed = !!eventSearchErr && !eventSearchForbidden

  // Auto-select the logged-in user's company by name (still switchable)
  useEffect(() => {
    if (companyId || !user?.company || !companies.length) return
    const target = user.company.trim().toLowerCase()
    const match = companies.find((c) => c.company.trim().toLowerCase() === target)
    if (match) setCompanyId(match.id)
  }, [companies, user?.company, companyId])

  const commitVehicle = useCallback((v: FpVehicle | null) => {
    setVehicleId(v?.id ?? null)
    setSelectedVehicle(v)
    // Prefill the starting odometer from the car's latest reading across ALL
    // its sessions (mileage_floor), falling back to the stored odometer.
    const floor = v?.mileage_floor ?? v?.odometer_km
    if (floor != null) setOdometerStart(String(floor))
  }, [])
  const handleVehicleChange = useCallback(
    (vId: string) => {
      const v = vehiclesForCompany.find((x) => x.id === Number(vId)) ?? null
      // A blocked car needs an explicit confirmation before it's selected.
      if (v?.locked_out || v?.blocked_now) { setPendingLockedVehicle(v); return }
      commitVehicle(v)
    },
    [vehiclesForCompany, commitVehicle],
  )

  // ── Per-field validity (drives red highlight after a submit attempt) ──
  const odometerNum = odometerStart.trim() === '' ? NaN : Number(odometerStart)
  const estimatedNum = estimatedKm.trim() === '' ? NaN : Number(estimatedKm)
  // Soft, non-blocking guard: warn when KM plecare is below the car's latest
  // known mileage (max of stored odometer + greatest km_end across its sessions).
  const mileageFloor = selectedVehicle?.mileage_floor ?? selectedVehicle?.odometer_km ?? null
  const odometerBelowFloor =
    mileageFloor != null && Number.isFinite(odometerNum) && odometerNum < mileageFloor
  const missing = {
    company: !companyId,
    vehicle: !selectedVehicle?.vin,
    client: !selectedClient,
    // A company client's license comes from its chosen contact (gated below
    // via `contact`), not the standalone photo upload — never double-block on it.
    license: isCompanyClient ? false : !driverLicensePhoto,
    // Person-client completeness gate: the person IS the driver, so a live
    // session needs their phone on file (the license photo is gated by
    // `license` above). A company gets phone from its contact; internal
    // QuickSessions have no client. Only flags once a person is selected —
    // NOT part of draftValid (a PLANNED draft defers this to activation).
    phone: !!selectedClient && !isCompanyClient && !(selectedClient.phone || '').trim(),
    // Company-client hard gate (Task 11): a company never drives itself — a
    // gate-valid contact person is required. Mirrors the backend exactly;
    // NOT part of draftValid (a PLANNED draft defers this to activation).
    contact: !contactGateOk,
    // Company-client CUI hard gate: a company TD requires the fiscal code (CUI)
    // on file. Only flags once a company is selected; deferred for PLANNED drafts.
    cui: !!selectedClient && isCompanyClient && !(selectedClient.cui || '').trim(),
    departure: !departureDatetime,
    odometer: Number.isNaN(odometerNum) || odometerNum < 0,
    estimated: Number.isNaN(estimatedNum) || estimatedNum <= 0,
    fuel: !fuelGaugeStart,
    advisor: advisorName.trim() === '',
    clientSig: !clientSignature,
    gdpr: !gdprConsent,
    conditions: conditionsRequired && !conditionsAccepted,
    // Return can't be before departure (naive "YYYY-MM-DDTHH:MM" → string compare).
    returnInvalid: !!returnDatetime && !!departureDatetime && returnDatetime < departureDatetime,
  }
  const formValid = !Object.values(missing).some(Boolean)
  // A PLANNED draft defers signature/GDPR/license to activation — mirrors the
  // backend's `required` list for status:'PLANNED' (no client_signature/gdpr_consent).
  // Planning a draft only needs the car, the client (name) and the departure
  // date/time — KM/fuel/advisor/signature/GDPR are all deferred to activation.
  const draftValid = !(
    missing.company || missing.vehicle || missing.client || missing.departure || missing.returnInvalid
  )
  // Activating a PLANNED draft only needs the deferred client signature on top of
  // the draft fields — the activate endpoint requires client_signature, defaults
  // gdpr_consent to true, and never reads a driver-license photo (so don't gate on it).
  // Activation (car actually goes out) keeps the operational fields required —
  // only *planning* was relaxed to name + date.
  const activateValid = !(
    missing.company || missing.vehicle || missing.client || missing.departure ||
    missing.odometer || missing.estimated || missing.fuel || missing.advisor || missing.returnInvalid ||
    missing.clientSig || missing.conditions || missing.contact || missing.phone || missing.cui
  )
  const err = (bad: boolean) => attempted && bad          // plan-relevant fields (any attempt)
  const errFull = (bad: boolean) => submitAttempt && bad  // activation-only fields (submit/activate only)

  const damagedZoneCount = toDamagePayload(departureDamage).length

  const submitMutation = useMutation({
    mutationFn: (payload: TestDriveFormPayload) => foiParcursApi.submitTestDrive(payload),
    onSuccess: (data) => { if (embedded) onDone?.(data.contract); else setSubmittedContract(data.contract) },
    onError: (err: any, variables) => {
      if (err?.data?.open_session) {
        setOpenBlock({ message: err.data.error, retry: () => { setOpenBlock(null); submitMutation.mutate({ ...variables, allow_open_session: true }) } })
      }
    },
  })
  const planMutation = useMutation({
    mutationFn: (payload: PlanTestDrivePayload) => foiParcursApi.planTestDrive(payload),
    onSuccess: (data) => { if (embedded) onDone?.(data.contract); else setSubmittedContract(data.contract) },
  })

  // ── VIN-conflict soft-block (shared by Trimite + Planifică) ──
  const { check: checkConflicts, checking } = useVehicleConflicts()
  const [conflictList, setConflictList] = useState<VehicleConflict[]>([])
  const [showConflicts, setShowConflicts] = useState(false)
  const [pendingRun, setPendingRun] = useState<(() => void) | null>(null)

  /** Runs the VIN-conflict check for the chosen window; if clear, calls
   *  `run()` immediately, else stashes it and opens the soft-block dialog. */
  async function withConflictCheck(vin: string, run: () => void, excludeId?: number) {
    const conflicts = await checkConflicts(vin, departureDatetime, returnDatetime || departureDatetime, excludeId)
    if (conflicts.length) {
      setConflictList(conflicts)
      setPendingRun(() => run)
      setShowConflicts(true)
    } else {
      run()
    }
  }

  type BasePayload = Omit<TestDriveFormPayload, 'client_signature' | 'gdpr_consent'>

  function buildBasePayload(vehicle: FpVehicle, client: CrmClient): BasePayload {
    const damagePayload = toDamagePayload(departureDamage)
    const capacity = vehicle.fuel_tank_capacity_liters ?? vehicle.battery_capacity_kwh ?? undefined
    // A company client's driver license lives on the selected contact (the
    // standalone card is hidden for them); a person client uses the standalone
    // fields. Resolve once here so both are fed from the right source.
    const licenseFor = isCompanyClient
      ? {
          photo: driverContact?.driver_license_photo ?? driverLicensePhoto ?? undefined,
          number: (driverContact?.driver_license_number ?? driverLicenseNumber ?? '').trim() || undefined,
        }
      : {
          photo: driverLicensePhoto ?? undefined,
          number: driverLicenseNumber.trim() || undefined,
        }
    return {
      company_id: companyId!,
      // Service context (Task 13) — carried on both the submit and plan
      // payloads (this builder feeds both); the courtesy-car order reference
      // is Service-only.
      document_type: documentType,
      vin: vehicle.vin,
      registration_number: vehicle.registration_number ?? '',
      client_id: Number(client.id),
      odometer_start: odometerNum,
      estimated_km: estimatedNum,
      fuel_gauge_start_level: fuelGaugeStart as FuelGaugeLevel,
      departure_datetime: departureDatetime,
      advisor_name: advisorName.trim(),
      // HR event (Task 15) — mutually exclusive with mkt_project_id below;
      // only sent when the "Este eveniment" checkbox is on and an event has
      // actually been picked/created.
      event_id: isEvent ? (eventId ?? undefined) : undefined,
      ...(isRental && serviceOrderRef.trim() ? { service_order_ref: serviceOrderRef.trim() } : {}),
      // Service rental-pricing snapshot (S6b) — see svcPricingPayload above.
      ...svcPricingPayload,
      ...(returnDatetime ? { return_datetime: returnDatetime } : {}),
      ...(capacity != null ? { fuel_tank_capacity_liters: capacity } : {}),
      ...(advisorSignature ? { advisor_signature: advisorSignature } : {}),
      ...(inspectionAcceptance ? { inspection_acceptance: inspectionAcceptance } : {}),
      ...(latestInspection?.id ? { inspection_id: latestInspection.id } : {}),
      ...(damagePayload.length ? { departure_damage: damagePayload } : {}),
      // License fields: for a company client the standalone license card is
      // hidden (photo/number state stays empty), so the actual driver's
      // license comes from the selected contact — prefer it, falling back to
      // any standalone value. A person client keeps its standalone fields.
      // (Fix round 1: without this a company FILLED submit sent blank
      // photo/number and the legal PDF's permis fields came out empty; the
      // backend now also falls back to the contact defensively.)
      ...(licenseFor.photo ? { driver_license_photo: licenseFor.photo } : {}),
      ...(licenseFor.number ? { driver_license_number: licenseFor.number } : {}),
      ...(driverLicenseExpiry.trim() ? { driver_license_expiry: driverLicenseExpiry.trim() } : {}),
      ...(generalObservation.trim() ? { general_observation: generalObservation.trim() } : {}),
      ...(mktProject ? { mkt_project_id: Number(mktProject.id) } : {}),
      ...(vehicle.locked_out || vehicle.blocked_now ? { allow_locked: true } : {}),
      // Company-client driver gate (Task 11) — the gate-valid contact chosen
      // above (a person client has none). The license number now carries the
      // full serie+number, sent via `licenseFor.number` above.
      ...(driverContact ? { driver_contact_id: driverContact.id } : {}),
    }
  }

  function handleSubmit() {
    if (submitMutation.isPending || planMutation.isPending || checking) return
    if (!formValid || !selectedVehicle?.vin || !selectedClient || !fuelGaugeStart) {
      setAttemptedAction('submit')
      return
    }
    const payload: TestDriveFormPayload = {
      ...buildBasePayload(selectedVehicle, selectedClient),
      client_signature: clientSignature,
      gdpr_consent: gdprConsent,
      ...(conditionsRequired ? { general_conditions_accepted: conditionsAccepted } : {}),
    }
    withConflictCheck(selectedVehicle.vin, () => submitMutation.mutate(payload))
  }

  function handlePlan() {
    if (planMutation.isPending || submitMutation.isPending || checking) return
    // Planning only needs the car + client (name) + departure date.
    if (!draftValid || !selectedVehicle?.vin || !selectedClient) {
      setAttemptedAction('plan')
      return
    }
    const payload: PlanTestDrivePayload = {
      ...buildBasePayload(selectedVehicle, selectedClient),
      status: 'PLANNED',
      ...(clientSignature ? { client_signature: clientSignature } : {}),
      ...(gdprConsent ? { gdpr_consent: gdprConsent } : {}),
    }
    withConflictCheck(selectedVehicle.vin, () => planMutation.mutate(payload))
  }

  const activateMutation = useMutation({
    mutationFn: (payload: ActivateTestDrivePayload) => foiParcursApi.activateTestDrive(activateId!, payload),
    onSuccess: (data) => { if (embedded) onDone?.(data.contract); else setSubmittedContract(data.contract) },
    onError: (err: any, variables) => {
      if (err?.data?.open_session) {
        setOpenBlock({ message: err.data.error, retry: () => { setOpenBlock(null); activateMutation.mutate({ ...variables, allow_open_session: true }) } })
      }
    },
  })

  function handleActivate() {
    if (activateMutation.isPending || checking || activateId == null) return
    if (!activateValid || !selectedVehicle?.vin || !selectedClient || !fuelGaugeStart) {
      setAttemptedAction('activate')
      return
    }
    const damagePayload = toDamagePayload(departureDamage)
    const capacity = selectedVehicle.fuel_tank_capacity_liters ?? selectedVehicle.battery_capacity_kwh ?? undefined
    const payload: ActivateTestDrivePayload = {
      // The client may have been changed/edited at activation ("Schimbă"/
      // "Editează" on the Client card). Send the currently-selected client so
      // the backend validates the contact against it and persists the switch.
      client_id: Number(selectedClient.id),
      client_signature: clientSignature,
      ...(advisorSignature ? { advisor_signature: advisorSignature } : {}),
      gdpr_consent: gdprConsent,
      odometer_start: odometerNum,
      fuel_gauge_start_level: fuelGaugeStart as FuelGaugeLevel,
      ...(capacity != null ? { fuel_tank_capacity_liters: capacity } : {}),
      departure_datetime: departureDatetime,
      ...(returnDatetime ? { return_datetime: returnDatetime } : {}),
      ...(damagePayload.length ? { departure_damage: damagePayload } : {}),
      ...(conditionsRequired ? { general_conditions_accepted: conditionsAccepted } : {}),
      ...(generalObservation.trim() ? { general_observation: generalObservation.trim() } : {}),
      ...(mktProject ? { mkt_project_id: Number(mktProject.id) } : {}),
      ...(isEvent && eventId != null ? { event_id: eventId } : {}),
      ...(selectedVehicle.locked_out || selectedVehicle.blocked_now ? { allow_locked: true } : {}),
      // Company-client driver gate (Task 11) — required server-side for a
      // company client's activation (400s without it); the backend derives
      // driver_license_serie itself from the contact, so it isn't sent here.
      ...(driverContact ? { driver_contact_id: driverContact.id } : {}),
      // Service rental-pricing snapshot (S6b) — see svcPricingPayload above.
      ...svcPricingPayload,
    }
    withConflictCheck(selectedVehicle.vin, () => activateMutation.mutate(payload), activateId)
  }

  // Edit a PLANNED draft in place (Corectează on a not-started session) — saves
  // the full form via PUT /plan without starting it; status stays PLANNED.
  const updatePlanMutation = useMutation({
    mutationFn: (payload: Partial<TestDriveFormPayload>) => foiParcursApi.updatePlan(editId!, payload),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['foi-contracts-all'] })
      if (embedded) onDone?.(data.contract); else setSubmittedContract(data.contract)
    },
    onError: (e: any) => toast.error(e?.data?.error || e?.message || 'Salvarea a eșuat'),
  })

  function handleEditPlan() {
    if (updatePlanMutation.isPending || checking || editId == null) return
    // Same minimal validity as planning: car + client (name) + departure.
    if (!draftValid || !selectedVehicle?.vin || !selectedClient) {
      setAttemptedAction('plan')
      return
    }
    const payload: Partial<TestDriveFormPayload> = buildBasePayload(selectedVehicle, selectedClient)
    withConflictCheck(selectedVehicle.vin, () => updatePlanMutation.mutate(payload), editId)
  }

  // Back/cancel out of the form — routes to the parent's onCancel callback
  // when embedded (e.g. the Hub panel), else the standalone route's nav.
  const handleBack = () => { if (embedded) onCancel?.(); else navigate('/app/foi-parcurs') }

  function resetForm() {
    setCompanyId(null); setVehicleId(null); setSelectedVehicle(null)
    setClientSearch(''); setSelectedClient(null); setShowManualCreate(false)
    setDriverContact(null); setShowAddContact(false)
    setMktProject(null); setProjectSearch('')
    setIsEvent(false); setEventId(null); setEventName(''); setEventSearch(''); setShowAddEvent(false)
    setDriverLicensePhoto(null); setDriverLicenseNumber(''); setDriverLicenseExpiry('')
    setDepartureDatetime(localDatetimeValue(new Date()))
    setReturnDatetime(localDatetimeValue(new Date(Date.now() + 60 * 60 * 1000)))
    setOdometerStart(''); setEstimatedKm(''); setFuelGaugeStart('')
    setGeneralObservation('')
    setClientSignature('')
    setShowDamage(false); setDepartureDamage(makeEmptyDamageState())
    setGdprConsent(false); setInspectionAcceptance(false)
    setConditionsAccepted(false); setShowConditions(false)
    setSubmittedContract(null); setAttemptedAction(null)
    setConflictList([]); setShowConflicts(false); setPendingRun(null)
    if (isActivating) { if (embedded) onCancel?.(); else navigate('/app/foi-parcurs/test-drive', { replace: true }) }
  }

  // ── Success Screen ──
  if (submittedContract) {
    const isPlanned = submittedContract.status === 'PLANNED'
    return (
      <div className="max-w-lg mx-auto py-12 space-y-6">
        <Card>
          <CardContent className="pt-6 text-center space-y-4">
            <CheckCircle2 className="mx-auto h-16 w-16 text-green-500" />
            <h2 className="text-xl font-semibold">{isPlanned ? 'Sesiune Planificată' : 'Test Drive Înregistrat'}</h2>
            <div className="text-sm text-muted-foreground space-y-1">
              <p>Contract: <span className="font-medium text-foreground">{submittedContract.contract_id}</span></p>
              {submittedContract.vin && <p>VIN: <span className="font-medium text-foreground">{submittedContract.vin}</span></p>}
              {submittedContract.client_name && <p>Client: <span className="font-medium text-foreground">{submittedContract.client_name}</span></p>}
            </div>
            {isPlanned ? (
              <p className="text-xs text-muted-foreground">
                Draftul a fost salvat. Activează sesiunea din tab-ul <span className="font-medium">Sesiuni Driving</span> când clientul ajunge.
              </p>
            ) : (
              <div className="flex gap-2 justify-center flex-wrap">
                <a href={foiParcursApi.getContractPdfUrl(submittedContract.id, 'legal')} target="_blank" rel="noopener">
                  <Button variant="outline" size="sm"><FileText className="mr-1.5 h-3.5 w-3.5" />Download Legal PDF</Button>
                </a>
                <a href={foiParcursApi.getContractPdfUrl(submittedContract.id, 'custom')} target="_blank" rel="noopener">
                  <Button variant="outline" size="sm"><FileText className="mr-1.5 h-3.5 w-3.5" />Download Custom PDF</Button>
                </a>
              </div>
            )}
            <div className="flex gap-3 justify-center pt-2">
              <Button variant="outline" onClick={resetForm}><Plus className="h-4 w-4 mr-1" />Test Drive Nou</Button>
              <Button onClick={handleBack}><ArrowLeft className="h-4 w-4 mr-1" />Înapoi la Driving Hub</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  const invalidRing = (bad: boolean) => cn(err(bad) && 'ring-2 ring-destructive')
  const invalidRingFull = (bad: boolean) => cn(errFull(bad) && 'ring-2 ring-destructive')

  return (
    <div className="max-w-2xl mx-auto space-y-6 pb-12">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" aria-label="Înapoi" onClick={handleBack}>
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div>
          <h1 className="text-lg font-semibold">
            {isEditing
              ? 'Corectează sesiunea planificată'
              : isActivating
              ? 'Activează Test Drive'
              : isRental ? 'Predare mașină de curtoazie' : 'Test Drive Nou'}
          </h1>
          <p className="text-sm text-muted-foreground">
            {isEditing
              ? 'Modifică datele sesiunii — se salvează fără a o porni'
              : isActivating
              ? 'Confirmă/ajustează datele și capturează semnătura clientului'
              : isRental ? 'Completați datele pentru predarea mașinii de curtoazie' : 'Completați datele pentru test drive'}
          </p>
        </div>
      </div>

      {/* ── Companie & Vehicul ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2"><Car className="h-4 w-4" />Companie & Vehicul</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Companie *</Label>
            <Select
              value={companyId ? String(companyId) : ''}
              onValueChange={(v) => { setCompanyId(Number(v)); setVehicleId(null); setSelectedVehicle(null) }}
            >
              <SelectTrigger className={invalidRing(missing.company)}><SelectValue placeholder="Selectează compania" /></SelectTrigger>
              <SelectContent>
                {companies.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Vehicul *</Label>
            <Select value={vehicleId ? String(vehicleId) : ''} onValueChange={handleVehicleChange} disabled={!companyId}>
              <SelectTrigger className={invalidRing(missing.vehicle)}>
                <SelectValue placeholder={companyId ? 'Selectează vehiculul' : 'Selectează întâi compania'} />
              </SelectTrigger>
              <SelectContent>
                {visibleVehicles.map((v) => {
                  const blockCategory = v.locked_out ? v.lockout_category : v.active_block_category
                  return (
                    <SelectItem key={v.id} value={String(v.id)}>
                      {[v.mark, v.model].filter(Boolean).join(' ') || '—'} — {v.registration_number || v.vin}
                      {v.is_active === false ? ' · 🗄 Arhivat' : ''}
                      {(v.locked_out || v.blocked_now) ? ` · 🔒 Blocat${blockCategory ? ` (${reasonLabel(blockCategory)})` : ''}` : ''}
                    </SelectItem>
                  )
                })}
              </SelectContent>
            </Select>
            {companyId != null && (hasHiddenVehicles || showAllVehicles) && (
              <label className="flex items-center gap-2 pt-1 text-xs text-muted-foreground cursor-pointer">
                <Checkbox checked={showAllVehicles} onCheckedChange={(c) => setShowAllVehicles(c === true)} />
                Arată și mașini arhivate/blocate
              </label>
            )}
          </div>
          {selectedVehicle && (
            <div className="rounded-md border bg-muted/50 p-3 space-y-1 text-sm">
              <p><span className="text-muted-foreground">Marca/Model:</span> {selectedVehicle.mark} {selectedVehicle.model}</p>
              <p><span className="text-muted-foreground">Nr. înmatriculare:</span> {selectedVehicle.registration_number || '—'}</p>
              <p><span className="text-muted-foreground">VIN:</span> {selectedVehicle.vin || '—'}</p>
              <p><span className="text-muted-foreground">Combustibil:</span> {selectedVehicle.fuel_type}</p>
              <p><span className="text-muted-foreground">Capacitate:</span> {[
                usesFuelTank(selectedVehicle.fuel_type) && selectedVehicle.fuel_tank_capacity_liters ? `${selectedVehicle.fuel_tank_capacity_liters} L` : null,
                usesBattery(selectedVehicle.fuel_type) && selectedVehicle.battery_capacity_kwh ? `${selectedVehicle.battery_capacity_kwh} kWh` : null,
              ].filter(Boolean).join(' + ') || '—'}</p>
            </div>
          )}
          {latestInspection && (
            <div className="rounded-md border border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950/30 p-3 space-y-1 text-sm">
              <div className="flex items-center gap-1.5 font-medium text-blue-700 dark:text-blue-300 mb-1">
                <ClipboardCheck className="h-4 w-4" />Ultima inspecție
              </div>
              <p><span className="text-muted-foreground">Data:</span> {new Date(latestInspection.inspection_date).toLocaleDateString('ro-RO')}</p>
              <p><span className="text-muted-foreground">Inspector:</span> {latestInspection.inspector_name}</p>
              {latestInspection.condition_notes && <p><span className="text-muted-foreground">Note:</span> {latestInspection.condition_notes}</p>}
            </div>
          )}
          <div className="space-y-1.5">
            <Label className="text-xs">Observații generale</Label>
            <Textarea
              value={generalObservation}
              onChange={(e) => setGeneralObservation(e.target.value)}
              placeholder="Observații despre sesiune (stare mașină, mențiuni, etc.)"
              rows={3}
              className="text-sm"
            />
          </div>
        </CardContent>
      </Card>

      {/* ── Client ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2"><Search className="h-4 w-4" />Client</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {isRental && (
            <div className="space-y-1.5">
              <Label className="text-xs">Nr. comandă service</Label>
              <Input
                placeholder="Nr. comandă service"
                value={serviceOrderRef}
                onChange={(e) => setServiceOrderRef(e.target.value)}
              />
            </div>
          )}
          {selectedClient ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge variant="secondary" className="text-sm py-1 px-3">
                  {selectedClient.display_name || selectedClient.name || `Client #${selectedClient.id}`}
                  {selectedClient.phone && ` — ${selectedClient.phone}`}
                </Badge>
                {!editingClient && (
                  <Button variant="ghost" size="sm" onClick={() => setEditingClient(true)}>
                    <Pencil className="h-3.5 w-3.5 mr-1" />Editează
                  </Button>
                )}
                <Button variant="ghost" size="sm" onClick={() => { setSelectedClient(null); setClientSearch(''); setEditingClient(false) }}>
                  <X className="h-4 w-4 mr-1" />Schimbă
                </Button>
              </div>

              {editingClient ? (
                <ClientEditForm
                  client={selectedClient}
                  isCompany={isCompanyClient}
                  onCancel={() => setEditingClient(false)}
                  onSaved={(c) => {
                    setSelectedClient((prev) => (prev ? { ...prev, ...c } : c))
                    setEditingClient(false)
                    queryClient.invalidateQueries({ queryKey: ['fp-client-full', c.id] })
                  }}
                />
              ) : (
                /* Full client data — read-only (name/CUI/nr.reg/tel/email/adresă) */
                <div className="text-xs space-y-0.5">
                  {isCompanyClient && (
                    <>
                      <p className={cn('text-muted-foreground', errFull(missing.cui) && 'text-destructive font-medium')}>
                        CUI: {(selectedClient.cui || '').trim() || 'lipsă'}
                      </p>
                      {(selectedClient.nr_reg || '').trim() && (
                        <p className="text-muted-foreground">Nr. reg.: {selectedClient.nr_reg}</p>
                      )}
                    </>
                  )}
                  <p className={cn('text-muted-foreground', errFull(missing.phone) && 'text-destructive font-medium')}>
                    Tel: {(selectedClient.phone || '').trim() || 'lipsă'}
                  </p>
                  <p className="text-muted-foreground">Email: {(selectedClient.email || '').trim() || '—'}</p>
                  {clientAddress(selectedClient) && (
                    <p className="text-muted-foreground">Adresă: {clientAddress(selectedClient)}</p>
                  )}
                </div>
              )}
              {isCompanyClient && (
                <div className={cn('rounded-md border bg-muted/40 p-3 space-y-2', invalidRingFull(missing.contact))}>
                  <p className="text-xs font-semibold uppercase text-muted-foreground">Persoană de contact *</p>
                  <p className="text-xs text-muted-foreground">
                    Firma nu conduce — alege persoana care preia efectiv vehiculul.
                  </p>
                  {contactsForbidden ? (
                    <p className="text-xs text-destructive">
                      Nu ai acces la persoanele de contact CRM. Contactează un administrator.
                    </p>
                  ) : contactsErrored ? (
                    <p className="text-xs text-destructive">
                      Persoanele de contact nu au putut fi încărcate. Încearcă din nou.
                    </p>
                  ) : (showAddContact || editingContact) ? (
                    <ContactForm
                      clientId={Number(selectedClient.id)}
                      initial={editingContact ? driverContact : null}
                      onSaved={(c) => {
                        // Refresh the picker's option list so the created/edited
                        // contact is current (the Select renders from this
                        // query; without invalidation its trigger can go stale).
                        queryClient.invalidateQueries({ queryKey: ['client-contacts', selectedClient.id] })
                        setDriverContact(c)
                        setShowAddContact(false)
                        setEditingContact(false)
                      }}
                      onCancel={() => { setShowAddContact(false); setEditingContact(false) }}
                    />
                  ) : (
                    <>
                      <Select
                        value={driverContact ? String(driverContact.id) : ''}
                        onValueChange={(v) => setDriverContact(contactOptions.find((c) => String(c.id) === v) ?? null)}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Alege persoana de contact" />
                        </SelectTrigger>
                        <SelectContent>
                          {contactOptions.map((c) => (
                            <SelectItem key={c.id} value={String(c.id)}>
                              {c.full_name}{contactGateFields(c) ? '' : ' ⚠ date incomplete'}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Button type="button" variant="outline" size="sm" className="w-full border-dashed" onClick={() => setShowAddContact(true)}>
                        <UserPlus className="h-3.5 w-3.5 mr-2" />Adaugă persoană de contact
                      </Button>
                      {driverContact && (
                        <div className="flex items-start gap-3 rounded-md border bg-background p-2.5 mt-1">
                          {driverContact.driver_license_photo && (
                            <img
                              src={driverContact.driver_license_photo}
                              alt="Permis de conducere"
                              className="h-14 w-24 shrink-0 rounded object-cover border"
                            />
                          )}
                          <div className="text-xs space-y-0.5 min-w-0">
                            <p className="font-medium">{driverContact.full_name}</p>
                            <p className="text-muted-foreground">Tel: {(driverContact.phone || '').trim() || '—'}</p>
                            <p className="text-muted-foreground truncate">Email: {(driverContact.email || '').trim() || '—'}</p>
                            <p className="text-muted-foreground">
                              Serie permis: {[driverContact.driver_license_serie, driverContact.driver_license_number].filter(Boolean).join(' ') || '—'}
                            </p>
                            {driverContact.driver_license_expiry && (
                              <p className="text-muted-foreground">Valabilitate: {driverContact.driver_license_expiry}</p>
                            )}
                          </div>
                          <div className="ml-auto flex shrink-0 items-start gap-1">
                            <button
                              type="button"
                              aria-label="Editează persoana de contact"
                              title="Editează persoana de contact"
                              onClick={() => { setShowAddContact(false); setEditingContact(true) }}
                              className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                            >
                              <Pencil className="h-4 w-4" />
                            </button>
                            <button
                              type="button"
                              aria-label="Șterge persoana de contact"
                              title="Șterge persoana de contact"
                              disabled={deleteContactMutation.isPending}
                              onClick={() => {
                                if (confirm(`Ștergi persoana de contact „${driverContact.full_name}”?`)) {
                                  deleteContactMutation.mutate(Number(driverContact.id))
                                }
                              }}
                              className="rounded-md p-1.5 text-destructive hover:bg-destructive/10 disabled:opacity-50"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        </div>
                      )}
                    </>
                  )}
                  {errFull(missing.contact) && (
                    <p className="text-xs text-destructive">
                      Firma necesită o persoană de contact cu nume, email, telefon, poză permis, serie și număr complete.
                    </p>
                  )}
                </div>
              )}
              {!isCompanyClient && missing.phone && (
                <div className={cn('rounded-md border bg-muted/40 p-3', errFull(missing.phone) && 'ring-2 ring-destructive')}>
                  <p className="text-xs text-destructive">
                    ⚠ Clientul nu are număr de telefon. Adaugă-l în fișa CRM înainte de a porni cursa.
                  </p>
                </div>
              )}
            </div>
          ) : showManualCreate ? (
            <CreateClientPanel
              prefill={null}
              onCancel={() => setShowManualCreate(false)}
              onCreated={(client, licenseNumber, licenseExpiry) => {
                setSelectedClient(client)
                if (licenseNumber) setDriverLicenseNumber(licenseNumber)
                if (licenseExpiry) setDriverLicenseExpiry(licenseExpiry)
                setShowManualCreate(false)
                setClientSearch('')
              }}
            />
          ) : (
            <div className="space-y-2 relative">
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  className={cn('pl-9', invalidRing(missing.client))}
                  placeholder="Caută client (CRM) după nume sau telefon..."
                  value={clientSearch}
                  onChange={(e) => setClientSearch(e.target.value)}
                />
                {isSearching && <Loader2 className="absolute right-2.5 top-2.5 h-4 w-4 text-muted-foreground animate-spin" />}
              </div>
              {debouncedSearch.trim().length >= 2 && !isSearching && clientResults.length === 0 && (
                <p className="text-xs text-muted-foreground">Niciun client găsit.</p>
              )}
              {clientResults.length > 0 && (
                <div className="border rounded-md divide-y max-h-60 overflow-y-auto">
                  {clientResults.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      className="w-full text-left px-3 py-2 hover:bg-accent text-sm transition-colors flex items-center justify-between gap-2"
                      onClick={() => { setSelectedClient(c); setClientSearch('') }}
                    >
                      <span className="font-medium truncate">{c.display_name || c.name || '—'}</span>
                      {c.phone && <span className="text-xs text-muted-foreground shrink-0">{c.phone}</span>}
                    </button>
                  ))}
                </div>
              )}
              <Button type="button" variant="outline" className="w-full border-dashed" onClick={() => setShowManualCreate(true)}>
                <UserPlus className="h-4 w-4 mr-2" />Adaugă client manual
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Campanie / Eveniment (opțional) ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2"><Megaphone className="h-4 w-4" />Campanie / Eveniment</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-2">
            <Checkbox
              id="is-event"
              checked={isEvent}
              onCheckedChange={(v) => {
                const checked = v === true
                setIsEvent(checked)
                // Event/campaign are mutually exclusive — switching either way
                // clears the other pick so a stray value never reaches the payload.
                setMktProject(null); setProjectSearch('')
                setEventId(null); setEventName(''); setEventSearch(''); setShowAddEvent(false)
              }}
            />
            <Label htmlFor="is-event" className="text-xs cursor-pointer">Este eveniment</Label>
          </div>

          {isEvent ? (
            eventId != null ? (
              <div className="flex items-center gap-2">
                <Badge variant="secondary" className="text-sm py-1 px-3">
                  {eventName || `Eveniment #${eventId}`}
                </Badge>
                <Button variant="ghost" size="sm" onClick={() => { setEventId(null); setEventName(''); setEventSearch('') }}>
                  <X className="h-4 w-4 mr-1" />Schimbă
                </Button>
              </div>
            ) : showAddEvent ? (
              <AddEventForm
                defaultStartDate={departureDatetime.slice(0, 10)}
                defaultEndDate={(returnDatetime || departureDatetime).slice(0, 10)}
                defaultCompany={companies.find((c) => c.id === companyId)?.company}
                defaultBrand={selectedVehicle?.brand ?? undefined}
                onCreated={(id, name) => { setEventId(id); setEventName(name); setShowAddEvent(false); setEventSearch('') }}
                onCancel={() => setShowAddEvent(false)}
              />
            ) : (
              <div className="space-y-2 relative">
                <div className="relative">
                  <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input
                    className="pl-9"
                    placeholder="Caută eveniment (opțional)..."
                    value={eventSearch}
                    onChange={(e) => setEventSearch(e.target.value)}
                  />
                  {isSearchingEvents && <Loader2 className="absolute right-2.5 top-2.5 h-4 w-4 text-muted-foreground animate-spin" />}
                </div>
                {eventSearchForbidden && (
                  <p className="text-xs text-destructive">
                    Nu ai permisiunea de a căuta evenimente HR — poți totuși crea unul nou mai jos.
                  </p>
                )}
                {eventSearchFailed && (
                  <p className="text-xs text-destructive">Căutarea a eșuat.</p>
                )}
                {!eventSearchForbidden && !eventSearchFailed && debouncedEventSearch.trim().length >= 2 && !isSearchingEvents && upcomingEvents.length === 0 && (
                  <p className="text-xs text-muted-foreground">Niciun eveniment viitor găsit.</p>
                )}
                {upcomingEvents.length > 0 && (
                  <div className="border rounded-md divide-y max-h-60 overflow-y-auto">
                    {upcomingEvents.map((e) => (
                      <button
                        key={e.id}
                        type="button"
                        className="w-full text-left px-3 py-2 hover:bg-accent text-sm transition-colors flex items-center justify-between gap-2"
                        onClick={() => { setEventId(e.id); setEventName(e.name || `Eveniment #${e.id}`); setEventSearch('') }}
                      >
                        <span className="font-medium truncate">{e.name || '—'}</span>
                        {e.start_date && <span className="text-xs text-muted-foreground shrink-0">{e.start_date}</span>}
                      </button>
                    ))}
                  </div>
                )}
                <Button type="button" variant="outline" className="w-full border-dashed" onClick={() => setShowAddEvent(true)}>
                  <Plus className="h-4 w-4 mr-2" />Adaugă eveniment nou
                </Button>
              </div>
            )
          ) : mktProject ? (
            <div className="flex items-center gap-2">
              <Badge variant="secondary" className="text-sm py-1 px-3">
                {mktProject.name || `Campanie #${mktProject.id}`}
                {mktProject.status && ` — ${mktProject.status}`}
              </Badge>
              <Button variant="ghost" size="sm" onClick={() => { setMktProject(null); setProjectSearch('') }}>
                <X className="h-4 w-4 mr-1" />Schimbă
              </Button>
            </div>
          ) : (
            <div className="space-y-2 relative">
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  className="pl-9"
                  placeholder="Caută campanie (opțional)..."
                  value={projectSearch}
                  onChange={(e) => setProjectSearch(e.target.value)}
                />
                {isSearchingProjects && <Loader2 className="absolute right-2.5 top-2.5 h-4 w-4 text-muted-foreground animate-spin" />}
              </div>
              {debouncedProjectSearch.trim().length >= 2 && !isSearchingProjects && projectResults.length === 0 && (
                <p className="text-xs text-muted-foreground">Nicio campanie găsită.</p>
              )}
              {projectResults.length > 0 && (
                <div className="border rounded-md divide-y max-h-60 overflow-y-auto">
                  {projectResults.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      className="w-full text-left px-3 py-2 hover:bg-accent text-sm transition-colors flex items-center justify-between gap-2"
                      onClick={() => { setMktProject(p); setProjectSearch('') }}
                    >
                      <span className="font-medium truncate">{p.name || '—'}</span>
                      {p.status && <span className="text-xs text-muted-foreground shrink-0">{p.status}</span>}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Permis de conducere ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2"><IdCard className="h-4 w-4" />Permis de conducere</CardTitle>
        </CardHeader>
        <CardContent>
          {isCompanyClient ? (
            driverContact ? (
              <div className="rounded-md border bg-muted/40 p-3 space-y-2 text-sm">
                <p className="text-xs text-muted-foreground">
                  Preluat din persoana de contact «{driverContact.full_name}» — schimbă persoana de contact mai sus pentru a modifica.
                </p>
                {driverContact.driver_license_photo && (
                  <img src={driverContact.driver_license_photo} alt="Permis de conducere" className="h-20 w-32 rounded-md object-cover border" />
                )}
                <p><span className="text-muted-foreground">Serie/număr:</span> {[driverContact.driver_license_serie, driverContact.driver_license_number].filter(Boolean).join(' ') || '—'}</p>
                <p><span className="text-muted-foreground">Valabilitate:</span> {driverContact.driver_license_expiry || '—'}</p>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">
                Alege sau adaugă mai sus o persoană de contact — permisul se preia automat de acolo.
              </p>
            )
          ) : (
            <DriverLicenseSection
              photo={driverLicensePhoto}
              onPhotoChange={setDriverLicensePhoto}
              invalid={errFull(missing.license)}
              hasClient={!!selectedClient}
              onSelectClient={setSelectedClient}
              onLicenseNumber={setDriverLicenseNumber}
              onLicenseExpiry={setDriverLicenseExpiry}
            />
          )}
        </CardContent>
      </Card>

      {/* ── Detalii plecare ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2"><Fuel className="h-4 w-4" />Detalii plecare</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label className="text-xs">Data plecării *</Label>
              <Input type="datetime-local" data-testid="td-departure" value={departureDatetime} onChange={(e) => setDepartureDatetime(e.target.value)} className={invalidRing(missing.departure)} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Data sosirii (estimată)</Label>
              <Input type="datetime-local" value={returnDatetime} min={departureDatetime || undefined} onChange={(e) => setReturnDatetime(e.target.value)} className={invalidRing(missing.returnInvalid)} />
              {attempted && missing.returnInvalid && <p className="text-xs text-destructive">Data sosirii nu poate fi înainte de plecare.</p>}
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label className="text-xs">KM plecare *</Label>
              <Input type="number" min={0} placeholder="Km la plecare" value={odometerStart} onChange={(e) => setOdometerStart(e.target.value)} className={invalidRingFull(missing.odometer)} />
              {odometerBelowFloor && (
                <p className="text-[11px] leading-tight text-amber-600 dark:text-amber-500">
                  ⚠ Sub kilometrajul actual al mașinii ({mileageFloor!.toLocaleString('ro-RO')} km)
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">KM estimat *</Label>
              <Input type="number" min={0} placeholder="Km estimați" value={estimatedKm} onChange={(e) => setEstimatedKm(e.target.value)} className={invalidRingFull(missing.estimated)} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Nivel combustibil plecare *</Label>
            <div className={cn('grid grid-cols-4 gap-1 h-11 rounded-lg bg-secondary p-1', errFull(missing.fuel) && 'ring-2 ring-destructive')}>
              {FUEL_START_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setFuelGaugeStart(opt.value)}
                  className={cn(
                    'flex items-center justify-center rounded-md text-sm font-medium transition-colors',
                    fuelGaugeStart === opt.value ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground',
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Sumar închiriere (Service — Mașini de curtoazie only) ── */}
      {isRental && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Wallet className="h-4 w-4" />Sumar închiriere
              {svcPricingLoading && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {!selectedVehicle || !departureDatetime || !returnDatetime ? (
              <p className="text-sm text-muted-foreground">
                Selectează mașina și datele de plecare/sosire pentru a calcula prețul.
              </p>
            ) : (
              <>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Bază</Label>
                    <div className="text-sm font-medium h-9 flex items-center">
                      {svcRateBasis === 'month' ? 'Lunar' : svcRateBasis === 'day' ? 'Zilnic' : '—'}
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Tarif (€)</Label>
                    <Input type="number" min={0} step="0.01" value={svcTariffEur} onChange={(e) => { setSvcTariffEur(e.target.value); recomputeSvcTotal(e.target.value, svcUnits) }} />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Nr. {svcRateBasis === 'month' ? 'luni' : 'zile'}</Label>
                    <Input type="number" min={0} value={svcUnits} onChange={(e) => { setSvcUnits(e.target.value); recomputeSvcTotal(svcTariffEur, e.target.value) }} />
                  </div>
                </div>
                <div className="flex items-center justify-between gap-3 rounded-md border bg-muted/50 p-3">
                  <Label className="text-sm font-medium shrink-0">Total</Label>
                  <div className="flex items-center gap-1.5">
                    <Input
                      type="number" min={0} step="0.01"
                      value={svcTotalEur}
                      onChange={(e) => setSvcTotalEur(e.target.value)}
                      className="w-32 text-right font-semibold"
                    />
                    <span className="text-sm text-muted-foreground">€</span>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Garanție (€)</Label>
                    <Input type="number" min={0} step="0.01" value={svcGarantieEur} onChange={(e) => setSvcGarantieEur(e.target.value)} />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Franșiză (€)</Label>
                    <Input type="number" min={0} step="0.01" value={svcFransizaEur} onChange={(e) => setSvcFransizaEur(e.target.value)} />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Km incluși/zi</Label>
                    <Input type="number" min={0} value={svcKmIncludedDay} onChange={(e) => setSvcKmIncludedDay(e.target.value)} />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Extra km (€)</Label>
                    <Input type="number" min={0} step="0.01" value={svcExtraKmEur} onChange={(e) => setSvcExtraKmEur(e.target.value)} />
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Raport Avarii (La Predare) — collapsible ── */}
      <Card>
        <CardHeader className="pb-3">
          <button type="button" className="w-full flex items-center justify-between gap-2" onClick={() => setShowDamage((v) => !v)}>
            <CardTitle className="text-base flex items-center gap-2"><AlertTriangle className="h-4 w-4" />Raport Avarii (La Predare)</CardTitle>
            <span className="flex items-center gap-2">
              {damagedZoneCount > 0 && <span className="text-xs font-medium text-primary">{damagedZoneCount} {damagedZoneCount === 1 ? 'zonă' : 'zone'}</span>}
              <ChevronDown className={cn('h-4 w-4 text-muted-foreground transition-transform', showDamage && 'rotate-180')} />
            </span>
          </button>
        </CardHeader>
        {showDamage && (
          <CardContent className="space-y-3">
            <p className="text-xs text-muted-foreground">Marchează starea vehiculului la momentul predării (opțional).</p>
            <DamageReport value={departureDamage} onChange={setDepartureDamage} />
          </CardContent>
        )}
      </Card>

      {/* ── Conformitate ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2"><ShieldCheck className="h-4 w-4" />Conformitate</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-start gap-2">
            <Checkbox id="inspection" checked={inspectionAcceptance} onCheckedChange={(v) => setInspectionAcceptance(v === true)} />
            <Label htmlFor="inspection" className="text-xs leading-normal cursor-pointer">Clientul a acceptat inspecția vehiculului (opțional).</Label>
          </div>
          <div className={cn('flex items-start gap-2 rounded-md p-2 -m-2', errFull(missing.gdpr) && 'ring-2 ring-destructive')}>
            <Checkbox id="gdpr" checked={gdprConsent} onCheckedChange={(v) => setGdprConsent(v === true)} />
            <Label htmlFor="gdpr" className="text-xs leading-normal cursor-pointer">Clientul este de acord cu prelucrarea datelor (GDPR). *</Label>
          </div>
          {conditionsRequired && (
            <div className="space-y-2">
              <div className={cn('flex items-start gap-2 rounded-md p-2 -m-2', errFull(missing.conditions) && 'ring-2 ring-destructive')}>
                <Checkbox id="conditions" checked={conditionsAccepted} onCheckedChange={(v) => setConditionsAccepted(v === true)} />
                <Label htmlFor="conditions" className="text-xs leading-normal cursor-pointer">Clientul a citit și acceptă condițiile generale. *</Label>
              </div>
              <Button type="button" variant="link" size="sm" className="h-auto p-0 text-xs" onClick={() => setShowConditions((s) => !s)}>
                {showConditions ? 'Ascunde condițiile generale' : 'Citește condițiile generale'}
              </Button>
              {showConditions && (
                <div className="max-h-48 overflow-y-auto whitespace-pre-wrap rounded-md border bg-muted/40 p-3 text-xs leading-relaxed">
                  {generalConditions}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Consilier & Semnături — last, signed after reviewing everything above ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2"><PenLine className="h-4 w-4" />Consilier & Semnături</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-1.5">
            <Label className="text-xs">Nume consilier *</Label>
            <Input value={advisorName} onChange={(e) => setAdvisorName(e.target.value)} placeholder="Numele consilierului" className={invalidRingFull(missing.advisor)} />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Semnătură client *</Label>
            {clientSignature ? (
              <div className="space-y-2">
                <div className="border rounded-lg p-2 bg-white"><img src={clientSignature} alt="Client signature" className="max-h-[100px] mx-auto" /></div>
                <Button type="button" variant="outline" size="sm" onClick={() => setClientSignature('')}>Resemnează</Button>
              </div>
            ) : (
              <Suspense fallback={<Skeleton className="h-[200px] w-full" />}>
                <SignatureCanvas onSave={setClientSignature} onClear={() => setClientSignature('')} width={500} height={200} />
              </Suspense>
            )}
            {errFull(missing.clientSig) && <p className="text-xs text-destructive">Semnătura clientului este obligatorie.</p>}
          </div>

          <AdvisorSignatureField value={advisorSignature} onChange={setAdvisorSignature} />
        </CardContent>
      </Card>

      {/* ── Submit ── */}
      {(submitMutation.isError || planMutation.isError || activateMutation.isError) && !openBlock && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {((activateMutation.error || submitMutation.error || planMutation.error) as { data?: { error?: string } } | null)?.data?.error
            || 'Eroare la trimitere. Vă rugăm încercați din nou.'}
        </div>
      )}
      {isEditing ? (
        <Button className={cn('w-full', attemptedAction === 'plan' && !draftValid && 'bg-destructive hover:bg-destructive/90')} size="lg" onClick={handleEditPlan} disabled={updatePlanMutation.isPending || checking || loadingDraft}>
          {updatePlanMutation.isPending ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Se salvează...</> : <><Save className="h-4 w-4 mr-2" />Salvează modificările</>}
        </Button>
      ) : isActivating ? (
        <Button className={cn('w-full', attemptedAction === 'activate' && !activateValid && 'bg-destructive hover:bg-destructive/90')} size="lg" onClick={handleActivate} disabled={activateMutation.isPending || checking || loadingDraft}>
          {activateMutation.isPending ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Se activează...</> : <><PlayCircle className="h-4 w-4 mr-2" />Începe sesiunea</>}
        </Button>
      ) : (
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            className="flex-1"
            size="lg"
            onClick={handlePlan}
            disabled={planMutation.isPending || submitMutation.isPending || checking}
          >
            {planMutation.isPending ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Se salvează...</> : <><CalendarPlus className="h-4 w-4 mr-2" />Planifică (draft)</>}
          </Button>
          <Button className={cn('flex-1', attemptedAction === 'submit' && !formValid && 'bg-destructive hover:bg-destructive/90')} size="lg" onClick={handleSubmit} disabled={submitMutation.isPending || planMutation.isPending || checking}>
            {submitMutation.isPending ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Se trimite...</> : isRental ? 'Predă mașina' : 'Trimite'}
          </Button>
        </div>
      )}
      {attemptedAction === 'plan' && !draftValid && !planMutation.isPending && (
        <p className="text-xs text-destructive text-center">Pentru a planifica, alege mașina, clientul și data.</p>
      )}
      {submitAttempt && !(isActivating ? activateValid : formValid) && !submitMutation.isPending && !activateMutation.isPending && (
        <p className="text-xs text-destructive text-center">Completează câmpurile marcate cu roșu pentru a trimite.</p>
      )}
      <ConflictDialog
        open={showConflicts}
        conflicts={conflictList}
        onCancel={() => { setShowConflicts(false); setPendingRun(null) }}
        onContinue={() => {
          setShowConflicts(false)
          pendingRun?.()
          setPendingRun(null)
        }}
      />
      {/* Single-open-session block — car already out; admins may force-start. */}
      {openBlock && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4" onClick={() => { setOpenBlock(null); submitMutation.reset(); activateMutation.reset() }}>
          <div className="w-full max-w-sm rounded-2xl bg-background p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400">
              <AlertTriangle className="h-5 w-5" />
              <h3 className="text-base font-semibold">Mașina e deja plecată</h3>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">{openBlock.message}</p>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => { setOpenBlock(null); submitMutation.reset(); activateMutation.reset() }}>Închide</Button>
              {isAdmin && <Button size="sm" onClick={() => openBlock.retry()}>Pornește oricum</Button>}
            </div>
          </div>
        </div>
      )}
      {/* Blocked-car override confirm — the car stays selectable only after this. */}
      {pendingLockedVehicle && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4" onClick={() => setPendingLockedVehicle(null)}>
          <div className="w-full max-w-sm rounded-2xl bg-background p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400">
              <AlertTriangle className="h-5 w-5" />
              <h3 className="text-base font-semibold">Mașină blocată</h3>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              {[pendingLockedVehicle.mark, pendingLockedVehicle.model].filter(Boolean).join(' ')} — {pendingLockedVehicle.registration_number || pendingLockedVehicle.vin}
            </p>
            <p className="mt-1 text-sm">
              Motiv: <span className="font-medium">{reasonLabel(pendingLockedVehicle.locked_out ? pendingLockedVehicle.lockout_category : pendingLockedVehicle.active_block_category) || 'Blocată'}</span>
              {pendingLockedVehicle.lockout_note ? ` — ${pendingLockedVehicle.lockout_note}` : ''}
            </p>
            <p className="mt-2 text-xs text-muted-foreground">
              Poți genera o foaie de parcurs pentru această mașină doar dacă confirmi.
            </p>
            <div className="mt-4 flex gap-2">
              <Button variant="outline" className="flex-1" onClick={() => setPendingLockedVehicle(null)}>Anulează</Button>
              <Button className="flex-1" onClick={() => { commitVehicle(pendingLockedVehicle); setPendingLockedVehicle(null) }}>
                Continuă oricum
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/** Advisor signature — reused across submissions via localStorage. Shows a
 *  collapsed "saved" state once captured, with a "Schimbă semnătura" action. */
function AdvisorSignatureField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [editing, setEditing] = useState(false)
  const saved = !!value && !editing

  const persist = (dataUrl: string) => {
    onChange(dataUrl)
    try { localStorage.setItem(ADVISOR_SIG_KEY, dataUrl) } catch { /* ignore */ }
    setEditing(false)
  }

  return (
    <div className="space-y-1.5">
      <Label className="text-xs">Semnătură consilier (opțional)</Label>
      {saved ? (
        <div className="flex items-center justify-between rounded-md border bg-muted/40 p-2">
          <span className="text-sm text-green-600 flex items-center gap-1.5"><CheckCircle2 className="h-4 w-4" />Semnătură consilier salvată</span>
          <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(true)}>Schimbă semnătura</Button>
        </div>
      ) : (
        <Suspense fallback={<Skeleton className="h-[200px] w-full" />}>
          <SignatureCanvas onSave={persist} onClear={() => onChange('')} width={500} height={200} />
        </Suspense>
      )}
    </div>
  )
}

/** Inline edit of the selected CRM client from the Driving Hub Client card.
 *  Login-gated (any TD user) via foiParcursApi.updateCrmClient — lets a
 *  consilier correct the fiscal identity + address (e.g. a missing CUI that
 *  blocks a company TD) without full CRM access. Company clients get CUI +
 *  Nr. reg fields; persons don't. */
function ClientEditForm({
  client,
  isCompany,
  onCancel,
  onSaved,
}: {
  client: CrmClient
  isCompany: boolean
  onCancel: () => void
  onSaved: (client: CrmClient) => void
}) {
  const [name, setName] = useState(client.display_name || client.name || '')
  const [cui, setCui] = useState(client.cui || '')
  const [nrReg, setNrReg] = useState(client.nr_reg || '')
  const [phone, setPhone] = useState(client.phone || '')
  const [email, setEmail] = useState(client.email || '')
  const [street, setStreet] = useState(client.street || '')
  const [city, setCity] = useState(client.city || '')
  const [region, setRegion] = useState(client.region || '')
  const [error, setError] = useState<string | null>(null)

  const save = useMutation({
    mutationFn: () =>
      foiParcursApi.updateCrmClient(Number(client.id), {
        display_name: name.trim(),
        phone: phone.trim(),
        email: email.trim(),
        street: street.trim(),
        city: city.trim(),
        region: region.trim(),
        ...(isCompany ? { cui: cui.trim(), nr_reg: nrReg.trim() } : {}),
      }),
    onSuccess: (res) => {
      if (res.client) onSaved(res.client)
      else onCancel()
    },
    onError: (e: any) => setError(e?.data?.error || 'Salvarea a eșuat.'),
  })

  const field = (label: string, value: string, setter: (v: string) => void, placeholder = '') => (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <Input value={value} onChange={(e) => setter(e.target.value)} placeholder={placeholder} className="h-8 text-sm" />
    </div>
  )

  return (
    <div className="rounded-md border bg-muted/30 p-3 space-y-2.5">
      {field('Nume', name, setName)}
      {isCompany && (
        <div className="grid grid-cols-2 gap-2">
          {field('CUI', cui, setCui, 'ex. RO1234567')}
          {field('Nr. reg.', nrReg, setNrReg, 'ex. J40/1234/2000')}
        </div>
      )}
      <div className="grid grid-cols-2 gap-2">
        {field('Telefon', phone, setPhone, '+40...')}
        {field('Email', email, setEmail)}
      </div>
      {field('Adresă (stradă)', street, setStreet)}
      <div className="grid grid-cols-2 gap-2">
        {field('Oraș', city, setCity)}
        {field('Județ', region, setRegion)}
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <div className="flex items-center gap-2 pt-0.5">
        <Button type="button" size="sm" onClick={() => { setError(null); save.mutate() }} disabled={save.isPending || !name.trim()}>
          {save.isPending ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Save className="h-3.5 w-3.5 mr-1" />}
          Salvează
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onCancel} disabled={save.isPending}>
          Anulează
        </Button>
      </div>
    </div>
  )
}

/** Inline company-contact form (Task 11) — creates a new contact person, or
 *  (when `initial` is passed) edits the selected one in place. On success it
 *  hands the saved contact back so the picker above can (re)select it. Edit mode
 *  lets a company's driver with incomplete data be completed without deleting
 *  and recreating. Mirrors DriverLicenseSection's photo-upload control (compress
 *  + preview) without its OCR/create-client wiring. */
function ContactForm({
  clientId,
  initial,
  onSaved,
  onCancel,
}: {
  clientId: number
  initial?: ClientContact | null
  onSaved: (contact: ClientContact) => void
  onCancel: () => void
}) {
  const isEdit = !!initial
  const [fullName, setFullName] = useState(initial?.full_name ?? '')
  const [email, setEmail] = useState(initial?.email ?? '')
  const [phone, setPhone] = useState(initial?.phone ?? '')
  const [photo, setPhoto] = useState<string | null>(initial?.driver_license_photo ?? null)
  const [busy, setBusy] = useState(false)
  const [license, setLicense] = useState(initial?.driver_license_number ?? '') // serie+number (one field)
  const [expiry, setExpiry] = useState((initial?.driver_license_expiry ?? '').slice(0, 10))
  const [error, setError] = useState<string | null>(null)

  const save = useMutation({
    mutationFn: (data: Partial<ClientContact>) =>
      isEdit
        ? crmApi.updateClientContact(clientId, Number(initial!.id), data)
        : crmApi.createClientContact(clientId, data),
  })

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setBusy(true)
    const compressed = await fileToCompressedDataUrl(file)
    setBusy(false)
    if (compressed) setPhoto(compressed)
  }

  const canSave = fullName.trim() !== '' && !save.isPending

  const handleSave = () => {
    if (!canSave) return
    setError(null)
    // Edit mode sends the full editable set so a user can also CLEAR a field;
    // create mode keeps omit-empty so we never post blank columns on insert.
    const data: Partial<ClientContact> = isEdit
      ? {
          full_name: fullName.trim(),
          email: email.trim() || null,
          phone: phone.trim() || null,
          driver_license_photo: photo || null,
          driver_license_number: license.trim() || null,
          driver_license_expiry: expiry.trim() || null,
        }
      : {
          full_name: fullName.trim(),
          ...(email.trim() ? { email: email.trim() } : {}),
          ...(phone.trim() ? { phone: phone.trim() } : {}),
          ...(photo ? { driver_license_photo: photo } : {}),
          ...(license.trim() ? { driver_license_number: license.trim() } : {}),
          ...(expiry.trim() ? { driver_license_expiry: expiry.trim() } : {}),
        }
    save.mutate(data, {
      onSuccess: (res) => {
        if (res.contact) onSaved(res.contact)
        else setError(isEdit ? 'Persoana de contact nu a putut fi salvată.' : 'Persoana de contact nu a putut fi creată.')
      },
      onError: (err: any) => {
        setError(err?.data?.error || err?.message
          || (isEdit ? 'Salvarea persoanei de contact a eșuat.' : 'Crearea persoanei de contact a eșuat.'))
      },
    })
  }

  return (
    <div className="space-y-2.5 rounded-md border bg-background p-3">
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
        {isEdit ? 'Editează persoana de contact' : 'Persoană de contact nouă'}
      </p>
      <div className="space-y-1">
        <Label className="text-xs">Nume complet *</Label>
        <Input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Nume și prenume" />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Email *</Label>
        <Input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="email@exemplu.ro"
          inputMode="email"
          autoCapitalize="none"
        />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Telefon *</Label>
        <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="0721 234 567" inputMode="tel" />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Poză permis *</Label>
        {photo ? (
          <div className="flex items-center gap-3">
            <img src={photo} alt="Permis de conducere" className="h-16 w-28 rounded-md object-cover border" />
            <Button type="button" variant="ghost" size="sm" className="text-destructive" onClick={() => setPhoto(null)}>
              <X className="h-3.5 w-3.5 mr-1" /> Șterge
            </Button>
          </div>
        ) : (
          <label className="flex h-16 w-full cursor-pointer flex-col items-center justify-center gap-1 rounded-md border-2 border-dashed text-muted-foreground hover:bg-accent transition-colors">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ImagePlus className="h-4 w-4" />}
            <span className="text-xs font-medium">Adaugă poza permisului</span>
            <input type="file" accept="image/*" className="hidden" onChange={handleFile} />
          </label>
        )}
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Serie/nr permis *</Label>
        <Input value={license} onChange={(e) => setLicense(e.target.value)} placeholder="Serie/număr" />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Valabilitate permis</Label>
        <Input type="date" value={expiry} onChange={(e) => setExpiry(e.target.value)} />
      </div>

      {error && <p className="text-xs text-destructive">{error}</p>}

      <div className="flex gap-2 pt-1">
        <Button type="button" variant="outline" className="flex-1" onClick={onCancel}>Anulează</Button>
        <Button type="button" className="flex-1" onClick={handleSave} disabled={!canSave}>
          {save.isPending
            ? (isEdit ? 'Se salvează...' : 'Se creează...')
            : (isEdit ? 'Salvează persoana de contact' : 'Creează persoana de contact')}
        </Button>
      </div>
    </div>
  )
}

/** Inline "Adaugă eveniment nou" form for the Campanie/Eveniment card (Task
 *  15) — creates an HR event via POST /api/events, then hands the new
 *  {id, name} back so the card can select it. Requires HR/marketing
 *  permissions the current user may lack; a 403 is surfaced inline rather
 *  than crashing the form (mirrors ContactForm's error handling). */
function AddEventForm({
  onCreated,
  onCancel,
  defaultStartDate,
  defaultEndDate,
  defaultCompany,
  defaultBrand,
}: {
  onCreated: (id: number, name: string) => void
  onCancel: () => void
  defaultStartDate?: string
  defaultEndDate?: string
  defaultCompany?: string
  defaultBrand?: string
}) {
  const [name, setName] = useState('')
  const [startDate, setStartDate] = useState(defaultStartDate ?? '')
  const [endDate, setEndDate] = useState(defaultEndDate ?? '')
  const [company, setCompany] = useState(defaultCompany ?? '')
  const [brand, setBrand] = useState(defaultBrand ?? '')
  const [error, setError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: (data: { name: string; start_date: string; end_date: string; company?: string; brand?: string }) =>
      foiParcursApi.createHrEvent(data),
  })

  const canCreate = name.trim() !== '' && startDate !== '' && endDate !== '' && !create.isPending

  const handleCreate = () => {
    if (!canCreate) return
    setError(null)
    const trimmedName = name.trim()
    create.mutate(
      {
        name: trimmedName,
        start_date: startDate,
        end_date: endDate,
        ...(company.trim() ? { company: company.trim() } : {}),
        ...(brand.trim() ? { brand: brand.trim() } : {}),
      },
      {
        onSuccess: (res) => {
          if (res?.success && res.id) onCreated(res.id, trimmedName)
          else setError('Evenimentul nu a putut fi creat.')
        },
        onError: (err: any) => {
          setError(
            err?.status === 403
              ? 'Nu ai permisiunea de a crea evenimente HR.'
              : err?.data?.error || err?.message || 'Crearea evenimentului a eșuat.',
          )
        },
      },
    )
  }

  return (
    <div className="space-y-2.5 rounded-md border bg-background p-3">
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Eveniment nou</p>
      <div className="space-y-1">
        <Label className="text-xs">Denumire *</Label>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Numele evenimentului" />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-xs">Data început *</Label>
          <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Data sfârșit *</Label>
          <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-xs">Companie</Label>
          <Input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Opțional" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Brand</Label>
          <Input value={brand} onChange={(e) => setBrand(e.target.value)} placeholder="Opțional" />
        </div>
      </div>

      {error && <p className="text-xs text-destructive">{error}</p>}

      <div className="flex gap-2 pt-1">
        <Button type="button" variant="outline" className="flex-1" onClick={onCancel}>Anulează</Button>
        <Button type="button" className="flex-1" onClick={handleCreate} disabled={!canCreate}>
          {create.isPending ? 'Se creează...' : 'Creează eveniment'}
        </Button>
      </div>
    </div>
  )
}
