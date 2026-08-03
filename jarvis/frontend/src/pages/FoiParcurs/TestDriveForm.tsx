import { useState, useEffect, useCallback, useMemo, lazy, Suspense } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { foiParcursApi } from '@/api/foiParcurs'
import { useAuthStore } from '@/stores/authStore'
import { cn } from '@/lib/utils'
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
  ChevronDown,
  FileText,
  AlertTriangle,
  CalendarPlus,
  PlayCircle,
  Megaphone,
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

interface TestDriveFormProps {
  embedded?: boolean
  activateId?: number
  initialCompanyId?: number
  onDone?: (contract: FoiContract) => void
  onCancel?: () => void
}

// ── Component ──
export default function TestDriveForm({ embedded, activateId: activateIdProp, initialCompanyId, onDone, onCancel }: TestDriveFormProps = {}) {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)

  // ── Activation mode — reopens this form pre-filled from a PLANNED draft ──
  const [searchParams] = useSearchParams()
  const activateId = activateIdProp ?? (searchParams.get('activate') ? Number(searchParams.get('activate')) : null)
  const isActivating = activateId != null

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

  // Campaign / event (optional marketing project) — type-to-search, like mobile
  const [mktProject, setMktProject] = useState<MktProject | null>(null)
  const [projectSearch, setProjectSearch] = useState('')
  const debouncedProjectSearch = useDebounce(projectSearch, 350)

  // Driver license
  const [driverLicensePhoto, setDriverLicensePhoto] = useState<string | null>(null)
  const [driverLicenseNumber, setDriverLicenseNumber] = useState('')
  const [driverLicenseExpiry, setDriverLicenseExpiry] = useState('')

  // Trip
  const [departureDatetime, setDepartureDatetime] = useState(() => localDatetimeValue(new Date()))
  const [returnDatetime, setReturnDatetime] = useState(() => localDatetimeValue(new Date(Date.now() + 60 * 60 * 1000)))
  const [odometerStart, setOdometerStart] = useState('')
  const [estimatedKm, setEstimatedKm] = useState('')
  const [fuelGaugeStart, setFuelGaugeStart] = useState<FuelGaugeLevel | ''>('')
  const [generalObservation, setGeneralObservation] = useState('')

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
  const [attempted, setAttempted] = useState(false)

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
  const { data: companiesData } = useQuery({
    queryKey: ['fp-companies'],
    queryFn: () => foiParcursApi.getCompanies(),
  })
  const companies = companiesData?.companies ?? []

  // Fetch ALL vehicles (incl. archived + blocked) under a distinct key so we
  // don't collide with the active-only ['fp-vehicles'] cache other views use.
  const { data: vehiclesData } = useQuery({
    queryKey: ['fp-vehicles', 'all'],
    queryFn: () => foiParcursApi.getVehicles(false),
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
    // Keep the currently-selected car in the list even if the toggle would hide
    // it (e.g. a blocked car selected earlier), so the trigger still renders it.
    if (selectedVehicle && !base.some((v) => v.id === selectedVehicle.id)) {
      const sel = vehiclesForCompany.find((v) => v.id === selectedVehicle.id)
      if (sel) return [sel, ...base]
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

  // ── Load + prefill the PLANNED draft being activated ──
  const { data: draftData, isLoading: loadingDraft } = useQuery({
    queryKey: ['fp-test-drive', activateId],
    queryFn: () => foiParcursApi.getTestDrive(activateId!),
    enabled: activateId != null,
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
    if (c.mkt_project_id) setMktProject({ id: c.mkt_project_id, name: c.mkt_project_name ?? null })
  }, [draftData]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const c = draftData?.contract
    if (!c || c.status !== 'PLANNED' || !allVehicles.length) return
    const v = allVehicles.find((x) => x.vin === c.vin)
    if (v) { setVehicleId(v.id); setSelectedVehicle(v) }
  }, [draftData, allVehicles])

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
    queryKey: ['fp-general-conditions', companyId, selectedVehicle?.vin],
    queryFn: () => foiParcursApi.getGeneralConditions(companyId!, selectedVehicle!.vin),
    enabled: !!companyId && !!selectedVehicle?.vin,
    staleTime: 60_000,
  })
  const generalConditions = (gcData?.text ?? '').trim()
  const conditionsRequired = generalConditions.length > 0

  const { data: clientSearchData, isFetching: isSearching } = useQuery({
    queryKey: ['fp-crm-search', debouncedSearch],
    queryFn: () => foiParcursApi.searchCrmClients(debouncedSearch, 20),
    enabled: debouncedSearch.trim().length >= 2 && !selectedClient,
  })
  const clientResults = clientSearchData?.clients ?? []

  // Campaign/event search — type-to-search (>=2 chars), not scoped by company
  // (matches the mobile form). Optional field, nothing gates on it.
  const { data: projectSearchData, isFetching: isSearchingProjects } = useQuery({
    queryKey: ['fp-mkt-project-search', debouncedProjectSearch],
    queryFn: () => foiParcursApi.searchMktProjects(debouncedProjectSearch, undefined, 20),
    enabled: debouncedProjectSearch.trim().length >= 2 && !mktProject,
  })
  const projectResults = projectSearchData?.projects ?? []

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
    license: !driverLicensePhoto,
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
    missing.clientSig || missing.conditions
  )
  const err = (bad: boolean) => attempted && bad

  const damagedZoneCount = toDamagePayload(departureDamage).length

  const submitMutation = useMutation({
    mutationFn: (payload: TestDriveFormPayload) => foiParcursApi.submitTestDrive(payload),
    onSuccess: (data) => { if (embedded) onDone?.(data.contract); else setSubmittedContract(data.contract) },
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
    return {
      company_id: companyId!,
      vin: vehicle.vin,
      registration_number: vehicle.registration_number ?? '',
      client_id: Number(client.id),
      odometer_start: odometerNum,
      estimated_km: estimatedNum,
      fuel_gauge_start_level: fuelGaugeStart as FuelGaugeLevel,
      departure_datetime: departureDatetime,
      advisor_name: advisorName.trim(),
      ...(returnDatetime ? { return_datetime: returnDatetime } : {}),
      ...(capacity != null ? { fuel_tank_capacity_liters: capacity } : {}),
      ...(advisorSignature ? { advisor_signature: advisorSignature } : {}),
      ...(inspectionAcceptance ? { inspection_acceptance: inspectionAcceptance } : {}),
      ...(latestInspection?.id ? { inspection_id: latestInspection.id } : {}),
      ...(damagePayload.length ? { departure_damage: damagePayload } : {}),
      ...(driverLicensePhoto ? { driver_license_photo: driverLicensePhoto } : {}),
      ...(driverLicenseNumber.trim() ? { driver_license_number: driverLicenseNumber.trim() } : {}),
      ...(driverLicenseExpiry.trim() ? { driver_license_expiry: driverLicenseExpiry.trim() } : {}),
      ...(generalObservation.trim() ? { general_observation: generalObservation.trim() } : {}),
      ...(mktProject ? { mkt_project_id: Number(mktProject.id) } : {}),
      ...(vehicle.locked_out || vehicle.blocked_now ? { allow_locked: true } : {}),
    }
  }

  function handleSubmit() {
    if (submitMutation.isPending || planMutation.isPending || checking) return
    if (!formValid || !selectedVehicle?.vin || !selectedClient || !fuelGaugeStart) {
      setAttempted(true)
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
      setAttempted(true)
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
  })

  function handleActivate() {
    if (activateMutation.isPending || checking || activateId == null) return
    if (!activateValid || !selectedVehicle?.vin || !selectedClient || !fuelGaugeStart) {
      setAttempted(true)
      return
    }
    const damagePayload = toDamagePayload(departureDamage)
    const capacity = selectedVehicle.fuel_tank_capacity_liters ?? selectedVehicle.battery_capacity_kwh ?? undefined
    const payload: ActivateTestDrivePayload = {
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
      ...(selectedVehicle.locked_out || selectedVehicle.blocked_now ? { allow_locked: true } : {}),
    }
    withConflictCheck(selectedVehicle.vin, () => activateMutation.mutate(payload), activateId)
  }

  // Back/cancel out of the form — routes to the parent's onCancel callback
  // when embedded (e.g. the Hub panel), else the standalone route's nav.
  const handleBack = () => { if (embedded) onCancel?.(); else navigate('/app/foi-parcurs') }

  function resetForm() {
    setCompanyId(null); setVehicleId(null); setSelectedVehicle(null)
    setClientSearch(''); setSelectedClient(null); setShowManualCreate(false)
    setMktProject(null); setProjectSearch('')
    setDriverLicensePhoto(null); setDriverLicenseNumber(''); setDriverLicenseExpiry('')
    setDepartureDatetime(localDatetimeValue(new Date()))
    setReturnDatetime(localDatetimeValue(new Date(Date.now() + 60 * 60 * 1000)))
    setOdometerStart(''); setEstimatedKm(''); setFuelGaugeStart('')
    setGeneralObservation('')
    setClientSignature('')
    setShowDamage(false); setDepartureDamage(makeEmptyDamageState())
    setGdprConsent(false); setInspectionAcceptance(false)
    setConditionsAccepted(false); setShowConditions(false)
    setSubmittedContract(null); setAttempted(false)
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

  return (
    <div className="max-w-2xl mx-auto space-y-6 pb-12">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" aria-label="Înapoi" onClick={handleBack}>
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div>
          <h1 className="text-lg font-semibold">{isActivating ? 'Activează Test Drive' : 'Test Drive Nou'}</h1>
          <p className="text-sm text-muted-foreground">
            {isActivating ? 'Confirmă/ajustează datele și capturează semnătura clientului' : 'Completați datele pentru test drive'}
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
                {visibleVehicles.map((v) => (
                  <SelectItem key={v.id} value={String(v.id)}>
                    {[v.mark, v.model].filter(Boolean).join(' ') || '—'} — {v.registration_number || v.vin}
                    {v.is_active === false ? ' · 🗄 Arhivat' : ''}
                    {(v.locked_out || v.blocked_now) ? ` · 🔒 Blocat${(v.locked_out ? v.lockout_category : v.active_block_category) ? ` (${reasonLabel(v.locked_out ? v.lockout_category : v.active_block_category)})` : ''}` : ''}
                  </SelectItem>
                ))}
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
          {selectedClient ? (
            <div className="flex items-center gap-2">
              <Badge variant="secondary" className="text-sm py-1 px-3">
                {selectedClient.display_name || selectedClient.name || `Client #${selectedClient.id}`}
                {selectedClient.phone && ` — ${selectedClient.phone}`}
              </Badge>
              <Button variant="ghost" size="sm" onClick={() => { setSelectedClient(null); setClientSearch('') }}>
                <X className="h-4 w-4 mr-1" />Schimbă
              </Button>
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
          {mktProject ? (
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
                  placeholder="Caută campanie sau eveniment (opțional)..."
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
          <DriverLicenseSection
            photo={driverLicensePhoto}
            onPhotoChange={setDriverLicensePhoto}
            invalid={err(missing.license)}
            hasClient={!!selectedClient}
            onSelectClient={setSelectedClient}
            onLicenseNumber={setDriverLicenseNumber}
            onLicenseExpiry={setDriverLicenseExpiry}
          />
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
              <Input type="datetime-local" value={departureDatetime} onChange={(e) => setDepartureDatetime(e.target.value)} className={invalidRing(missing.departure)} />
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
              <Input type="number" min={0} placeholder="Km la plecare" value={odometerStart} onChange={(e) => setOdometerStart(e.target.value)} className={invalidRing(missing.odometer)} />
              {odometerBelowFloor && (
                <p className="text-[11px] leading-tight text-amber-600 dark:text-amber-500">
                  ⚠ Sub kilometrajul actual al mașinii ({mileageFloor!.toLocaleString('ro-RO')} km)
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">KM estimat *</Label>
              <Input type="number" min={0} placeholder="Km estimați" value={estimatedKm} onChange={(e) => setEstimatedKm(e.target.value)} className={invalidRing(missing.estimated)} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Nivel combustibil plecare *</Label>
            <div className={cn('grid grid-cols-4 gap-1 h-11 rounded-lg bg-secondary p-1', err(missing.fuel) && 'ring-2 ring-destructive')}>
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

      {/* ── Consilier & Semnături ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2"><PenLine className="h-4 w-4" />Consilier & Semnături</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-1.5">
            <Label className="text-xs">Nume consilier *</Label>
            <Input value={advisorName} onChange={(e) => setAdvisorName(e.target.value)} placeholder="Numele consilierului" className={invalidRing(missing.advisor)} />
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
            {err(missing.clientSig) && <p className="text-xs text-destructive">Semnătura clientului este obligatorie.</p>}
          </div>

          <AdvisorSignatureField value={advisorSignature} onChange={setAdvisorSignature} />
        </CardContent>
      </Card>

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
          <div className={cn('flex items-start gap-2 rounded-md p-2 -m-2', err(missing.gdpr) && 'ring-2 ring-destructive')}>
            <Checkbox id="gdpr" checked={gdprConsent} onCheckedChange={(v) => setGdprConsent(v === true)} />
            <Label htmlFor="gdpr" className="text-xs leading-normal cursor-pointer">Clientul este de acord cu prelucrarea datelor (GDPR). *</Label>
          </div>
          {conditionsRequired && (
            <div className="space-y-2">
              <div className={cn('flex items-start gap-2 rounded-md p-2 -m-2', err(missing.conditions) && 'ring-2 ring-destructive')}>
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

      {/* ── Submit ── */}
      {(submitMutation.isError || planMutation.isError || activateMutation.isError) && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          Eroare la trimitere. Vă rugăm încercați din nou.
        </div>
      )}
      {isActivating ? (
        <Button className={cn('w-full', attempted && !activateValid && 'bg-destructive hover:bg-destructive/90')} size="lg" onClick={handleActivate} disabled={activateMutation.isPending || checking || loadingDraft}>
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
          <Button className={cn('flex-1', attempted && !formValid && 'bg-destructive hover:bg-destructive/90')} size="lg" onClick={handleSubmit} disabled={submitMutation.isPending || planMutation.isPending || checking}>
            {submitMutation.isPending ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Se trimite...</> : 'Trimite'}
          </Button>
        </div>
      )}
      {attempted && !(isActivating ? activateValid : formValid) && !submitMutation.isPending && !activateMutation.isPending && (
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
              Motiv: <span className="font-medium">{reasonLabel(pendingLockedVehicle.lockout_category) || 'Blocată'}</span>
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
