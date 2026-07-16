import { useState, useEffect, useCallback, useMemo, lazy, Suspense } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { foiParcursApi } from '@/api/foiParcurs'
import { useAuthStore } from '@/stores/authStore'
import { cn } from '@/lib/utils'
import {
  usesFuelTank,
  usesBattery,
  type FuelGaugeLevel,
  type CrmClient,
  type FpVehicle,
  type FpVehicleInspection,
  type TestDriveFormPayload,
  type FoiContract,
} from '@/types/foiParcurs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
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
} from 'lucide-react'
import { CreateClientPanel, DriverLicenseSection } from './CreateClientPanel'
import {
  DamageReport,
  makeEmptyDamageState,
  toDamagePayload,
  type DamageState,
} from './testDriveDamage'

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

// ── Component ──
export default function TestDriveForm() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)

  // Company & vehicle
  const [companyId, setCompanyId] = useState<number | null>(null)
  const [vehicleId, setVehicleId] = useState<number | null>(null)
  const [selectedVehicle, setSelectedVehicle] = useState<FpVehicle | null>(null)

  // Client (CRM)
  const [clientSearch, setClientSearch] = useState('')
  const debouncedSearch = useDebounce(clientSearch, 350)
  const [selectedClient, setSelectedClient] = useState<CrmClient | null>(null)
  const [showManualCreate, setShowManualCreate] = useState(false)

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

  const { data: vehiclesData } = useQuery({
    queryKey: ['fp-vehicles'],
    queryFn: () => foiParcursApi.getVehicles(true),
  })
  const allVehicles = vehiclesData?.vehicles ?? []
  const vehiclesForCompany = useMemo(
    () => (companyId ? allVehicles.filter((v) => v.company_id === companyId) : []),
    [allVehicles, companyId],
  )

  const { data: inspectionData } = useQuery({
    queryKey: ['fp-inspection', vehicleId],
    queryFn: () => foiParcursApi.getLatestInspection(vehicleId!),
    enabled: !!vehicleId,
  })
  const latestInspection: FpVehicleInspection | null = inspectionData?.inspection ?? null

  const { data: clientSearchData, isFetching: isSearching } = useQuery({
    queryKey: ['fp-crm-search', debouncedSearch],
    queryFn: () => foiParcursApi.searchCrmClients(debouncedSearch, 20),
    enabled: debouncedSearch.trim().length >= 2 && !selectedClient,
  })
  const clientResults = clientSearchData?.clients ?? []

  // Auto-select the logged-in user's company by name (still switchable)
  useEffect(() => {
    if (companyId || !user?.company || !companies.length) return
    const target = user.company.trim().toLowerCase()
    const match = companies.find((c) => c.company.trim().toLowerCase() === target)
    if (match) setCompanyId(match.id)
  }, [companies, user?.company, companyId])

  const handleVehicleChange = useCallback(
    (vId: string) => {
      const id = Number(vId)
      setVehicleId(id)
      const v = vehiclesForCompany.find((x) => x.id === id) ?? null
      setSelectedVehicle(v)
      // Prefill the starting odometer from the vehicle's stored reading
      if (v?.odometer_km != null) setOdometerStart(String(v.odometer_km))
    },
    [vehiclesForCompany],
  )

  // ── Per-field validity (drives red highlight after a submit attempt) ──
  const odometerNum = odometerStart.trim() === '' ? NaN : Number(odometerStart)
  const estimatedNum = estimatedKm.trim() === '' ? NaN : Number(estimatedKm)
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
  }
  const formValid = !Object.values(missing).some(Boolean)
  const err = (bad: boolean) => attempted && bad

  const damagedZoneCount = toDamagePayload(departureDamage).length

  const submitMutation = useMutation({
    mutationFn: (payload: TestDriveFormPayload) => foiParcursApi.submitTestDrive(payload),
    onSuccess: (data) => setSubmittedContract(data.contract),
  })

  function handleSubmit() {
    if (submitMutation.isPending) return
    if (!formValid || !selectedVehicle?.vin || !selectedClient || !fuelGaugeStart) {
      setAttempted(true)
      return
    }
    const damagePayload = toDamagePayload(departureDamage)
    const capacity = selectedVehicle.fuel_tank_capacity_liters ?? selectedVehicle.battery_capacity_kwh ?? undefined
    const payload: TestDriveFormPayload = {
      company_id: companyId!,
      vin: selectedVehicle.vin,
      registration_number: selectedVehicle.registration_number ?? '',
      client_id: Number(selectedClient.id),
      odometer_start: odometerNum,
      estimated_km: estimatedNum,
      fuel_gauge_start_level: fuelGaugeStart as FuelGaugeLevel,
      departure_datetime: departureDatetime,
      advisor_name: advisorName.trim(),
      client_signature: clientSignature,
      gdpr_consent: gdprConsent,
      ...(returnDatetime ? { return_datetime: returnDatetime } : {}),
      ...(capacity != null ? { fuel_tank_capacity_liters: capacity } : {}),
      ...(advisorSignature ? { advisor_signature: advisorSignature } : {}),
      ...(inspectionAcceptance ? { inspection_acceptance: inspectionAcceptance } : {}),
      ...(latestInspection?.id ? { inspection_id: latestInspection.id } : {}),
      ...(damagePayload.length ? { departure_damage: damagePayload } : {}),
      ...(driverLicensePhoto ? { driver_license_photo: driverLicensePhoto } : {}),
      ...(driverLicenseNumber.trim() ? { driver_license_number: driverLicenseNumber.trim() } : {}),
      ...(driverLicenseExpiry.trim() ? { driver_license_expiry: driverLicenseExpiry.trim() } : {}),
    }
    submitMutation.mutate(payload)
  }

  function resetForm() {
    setCompanyId(null); setVehicleId(null); setSelectedVehicle(null)
    setClientSearch(''); setSelectedClient(null); setShowManualCreate(false)
    setDriverLicensePhoto(null); setDriverLicenseNumber(''); setDriverLicenseExpiry('')
    setDepartureDatetime(localDatetimeValue(new Date()))
    setReturnDatetime(localDatetimeValue(new Date(Date.now() + 60 * 60 * 1000)))
    setOdometerStart(''); setEstimatedKm(''); setFuelGaugeStart('')
    setClientSignature('')
    setShowDamage(false); setDepartureDamage(makeEmptyDamageState())
    setGdprConsent(false); setInspectionAcceptance(false)
    setSubmittedContract(null); setAttempted(false)
  }

  // ── Success Screen ──
  if (submittedContract) {
    return (
      <div className="max-w-lg mx-auto py-12 space-y-6">
        <Card>
          <CardContent className="pt-6 text-center space-y-4">
            <CheckCircle2 className="mx-auto h-16 w-16 text-green-500" />
            <h2 className="text-xl font-semibold">Test Drive Înregistrat</h2>
            <div className="text-sm text-muted-foreground space-y-1">
              <p>Contract: <span className="font-medium text-foreground">{submittedContract.contract_id}</span></p>
              {submittedContract.vin && <p>VIN: <span className="font-medium text-foreground">{submittedContract.vin}</span></p>}
              {submittedContract.client_name && <p>Client: <span className="font-medium text-foreground">{submittedContract.client_name}</span></p>}
            </div>
            <div className="flex gap-2 justify-center flex-wrap">
              <a href={foiParcursApi.getContractPdfUrl(submittedContract.id, 'legal')} target="_blank" rel="noopener">
                <Button variant="outline" size="sm"><FileText className="mr-1.5 h-3.5 w-3.5" />Download Legal PDF</Button>
              </a>
              <a href={foiParcursApi.getContractPdfUrl(submittedContract.id, 'custom')} target="_blank" rel="noopener">
                <Button variant="outline" size="sm"><FileText className="mr-1.5 h-3.5 w-3.5" />Download Custom PDF</Button>
              </a>
            </div>
            <div className="flex gap-3 justify-center pt-2">
              <Button variant="outline" onClick={resetForm}><Plus className="h-4 w-4 mr-1" />Test Drive Nou</Button>
              <Button onClick={() => navigate('/app/foi-parcurs')}><ArrowLeft className="h-4 w-4 mr-1" />Înapoi la Driving Hub</Button>
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
        <Button variant="ghost" size="icon" onClick={() => navigate('/app/foi-parcurs')}>
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div>
          <h1 className="text-lg font-semibold">Test Drive Nou</h1>
          <p className="text-sm text-muted-foreground">Completați datele pentru test drive</p>
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
                {vehiclesForCompany.map((v) => (
                  <SelectItem key={v.id} value={String(v.id)}>
                    {[v.mark, v.model].filter(Boolean).join(' ') || '—'} — {v.registration_number || v.vin}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {selectedVehicle && (
            <div className="rounded-md border bg-muted/50 p-3 space-y-1 text-sm">
              <p><span className="text-muted-foreground">Marca/Model:</span> {selectedVehicle.mark} {selectedVehicle.model}</p>
              <p><span className="text-muted-foreground">Nr. înmatriculare:</span> {selectedVehicle.registration_number || '—'}</p>
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
              <Input type="datetime-local" value={returnDatetime} onChange={(e) => setReturnDatetime(e.target.value)} />
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label className="text-xs">KM plecare *</Label>
              <Input type="number" min={0} placeholder="Km la plecare" value={odometerStart} onChange={(e) => setOdometerStart(e.target.value)} className={invalidRing(missing.odometer)} />
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
        </CardContent>
      </Card>

      {/* ── Submit ── */}
      {submitMutation.isError && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          Eroare la trimitere. Vă rugăm încercați din nou.
        </div>
      )}
      <Button className={cn('w-full', attempted && !formValid && 'bg-destructive hover:bg-destructive/90')} size="lg" onClick={handleSubmit} disabled={submitMutation.isPending}>
        {submitMutation.isPending ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Se trimite...</> : 'Trimite'}
      </Button>
      {attempted && !formValid && !submitMutation.isPending && (
        <p className="text-xs text-destructive text-center">Completează câmpurile marcate cu roșu pentru a trimite.</p>
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
