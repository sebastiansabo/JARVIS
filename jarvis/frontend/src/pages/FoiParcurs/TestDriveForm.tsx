import { useState, useEffect, useCallback, lazy, Suspense } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { foiParcursApi } from '@/api/foiParcurs'
import { crmApi, type CrmClient } from '@/api/crm'
import { useAuthStore } from '@/stores/authStore'
import {
  FUEL_LEVEL_OPTIONS,
  type FuelGaugeLevel,
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
import { Textarea } from '@/components/ui/textarea'
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
  MapPin,
  Fuel,
  ShieldCheck,
  PenLine,
  CheckCircle2,
  ArrowLeft,
  Plus,
  ClipboardCheck,
  Loader2,
  X,
  FileText,
} from 'lucide-react'

const SignatureCanvas = lazy(() => import('@/components/shared/SignatureCanvas'))

// ── Helpers ──

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
  const [searchParams] = useSearchParams()
  const _contractId = searchParams.get('contract_id') // reserved for future edit mode
  void _contractId
  const user = useAuthStore((s) => s.user)

  // ── Section 1: Vehicle & Company ──
  const [companyId, setCompanyId] = useState<number | null>(null)
  const [vehicleId, setVehicleId] = useState<number | null>(null)
  const [selectedVehicle, setSelectedVehicle] = useState<FpVehicle | null>(null)

  // ── Section 2: Client ──
  const [clientSearch, setClientSearch] = useState('')
  const debouncedSearch = useDebounce(clientSearch, 300)
  const [selectedClient, setSelectedClient] = useState<CrmClient | null>(null)
  const [showClientDropdown, setShowClientDropdown] = useState(false)

  // ── Section 3: Route ──
  const [departureDatetime, setDepartureDatetime] = useState('')
  const [returnDatetime, setReturnDatetime] = useState('')
  const [odometerStart, setOdometerStart] = useState('')
  const [odometerEnd, setOdometerEnd] = useState('')
  const [estimatedKm, setEstimatedKm] = useState('')
  const [itinerary, setItinerary] = useState('')

  // ── Section 4: Fuel ──
  const [fuelGaugeStart, setFuelGaugeStart] = useState<FuelGaugeLevel | ''>('')
  const [fuelGaugeEnd, setFuelGaugeEnd] = useState<FuelGaugeLevel | ''>('')

  // ── Section 5: Compliance ──
  const [gdprConsent, setGdprConsent] = useState(false)
  const [inspectionAcceptance, setInspectionAcceptance] = useState(false)
  const [advisorName, setAdvisorName] = useState(user?.name ?? '')

  // ── Section 6: Signatures ──
  const [clientSignature, setClientSignature] = useState('')
  const [advisorSignature, setAdvisorSignature] = useState('')

  // ── Success ──
  const [submittedContract, setSubmittedContract] = useState<FoiContract | null>(null)

  // ── Validation errors ──
  const [errors, setErrors] = useState<Record<string, string>>({})

  // Pre-fill advisor name when user loads
  useEffect(() => {
    if (user?.name && !advisorName) setAdvisorName(user.name)
  }, [user?.name]) // eslint-disable-line react-hooks/exhaustive-deps

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
  const filteredVehicles = companyId
    ? allVehicles.filter((v) => v.company_id === companyId)
    : allVehicles

  const { data: inspectionData } = useQuery({
    queryKey: ['fp-inspection', vehicleId],
    queryFn: () => foiParcursApi.getLatestInspection(vehicleId!),
    enabled: !!vehicleId,
  })
  const latestInspection: FpVehicleInspection | null = inspectionData?.inspection ?? null

  const { data: clientSearchData, isFetching: isSearching } = useQuery({
    queryKey: ['crm-client-search', debouncedSearch],
    queryFn: () => crmApi.getClients({ q: debouncedSearch, per_page: '10' }),
    enabled: debouncedSearch.length >= 2 && !selectedClient,
  })
  const clientResults = clientSearchData?.clients ?? []

  // ── Vehicle selection handler ──
  const handleVehicleChange = useCallback(
    (vId: string) => {
      const id = Number(vId)
      setVehicleId(id)
      const v = allVehicles.find((x) => x.id === id) ?? null
      setSelectedVehicle(v)
    },
    [allVehicles],
  )

  // ── Submit mutation ──
  const submitMutation = useMutation({
    mutationFn: (payload: TestDriveFormPayload) => foiParcursApi.submitTestDrive(payload),
    onSuccess: (data) => {
      setSubmittedContract(data.contract)
    },
  })

  // ── Validation ──
  function validate(): boolean {
    const e: Record<string, string> = {}
    if (!companyId) e.company = 'Selectati compania'
    if (!vehicleId || !selectedVehicle) e.vehicle = 'Selectati vehiculul'
    if (!selectedClient) e.client = 'Selectati clientul'
    if (!departureDatetime) e.departure = 'Data si ora plecarii sunt obligatorii'
    if (!odometerStart) e.odometerStart = 'KM plecare obligatoriu'
    if (!estimatedKm) e.estimatedKm = 'KM estimat obligatoriu'
    if (!itinerary.trim()) e.itinerary = 'Traseul este obligatoriu'
    if (!fuelGaugeStart) e.fuelStart = 'Nivel combustibil plecare obligatoriu'
    if (!gdprConsent) e.gdpr = 'Consimtamantul GDPR este obligatoriu'
    if (!inspectionAcceptance) e.inspection = 'Acceptarea inspectiei este obligatorie'
    if (!advisorName.trim()) e.advisor = 'Numele consilierului este obligatoriu'
    if (!clientSignature) e.clientSig = 'Semnatura clientului este obligatorie'
    if (!advisorSignature) e.advisorSig = 'Semnatura consilierului este obligatorie'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  function handleSubmit() {
    if (!validate()) return
    const payload: TestDriveFormPayload = {
      company_id: companyId!,
      vin: selectedVehicle!.vin,
      registration_number: selectedVehicle!.registration_number ?? '',
      client_id: selectedClient!.id,
      odometer_start: Number(odometerStart),
      odometer_end: odometerEnd ? Number(odometerEnd) : undefined,
      estimated_km: Number(estimatedKm),
      fuel_tank_capacity_liters: selectedVehicle!.fuel_tank_capacity_liters,
      fuel_gauge_start_level: fuelGaugeStart as FuelGaugeLevel,
      fuel_gauge_end_level: fuelGaugeEnd ? (fuelGaugeEnd as FuelGaugeLevel) : undefined,
      itinerary,
      departure_datetime: departureDatetime,
      return_datetime: returnDatetime || undefined,
      advisor_name: advisorName,
      advisor_signature: advisorSignature,
      client_signature: clientSignature,
      gdpr_consent: gdprConsent,
      inspection_acceptance: inspectionAcceptance,
      inspection_id: latestInspection?.id,
    }
    submitMutation.mutate(payload)
  }

  function resetForm() {
    setCompanyId(null)
    setVehicleId(null)
    setSelectedVehicle(null)
    setClientSearch('')
    setSelectedClient(null)
    setDepartureDatetime('')
    setReturnDatetime('')
    setOdometerStart('')
    setOdometerEnd('')
    setEstimatedKm('')
    setItinerary('')
    setFuelGaugeStart('')
    setFuelGaugeEnd('')
    setGdprConsent(false)
    setInspectionAcceptance(false)
    setClientSignature('')
    setAdvisorSignature('')
    setSubmittedContract(null)
    setErrors({})
  }

  // ── Success Screen ──
  if (submittedContract) {
    return (
      <div className="max-w-lg mx-auto py-12 space-y-6">
        <Card>
          <CardContent className="pt-6 text-center space-y-4">
            <CheckCircle2 className="mx-auto h-16 w-16 text-green-500" />
            <h2 className="text-xl font-semibold">Test Drive Inregistrat</h2>
            <div className="text-sm text-muted-foreground space-y-1">
              <p>Contract: <span className="font-medium text-foreground">{submittedContract.contract_id}</span></p>
              {submittedContract.vin && (
                <p>VIN: <span className="font-medium text-foreground">{submittedContract.vin}</span></p>
              )}
              {submittedContract.client_name && (
                <p>Client: <span className="font-medium text-foreground">{submittedContract.client_name}</span></p>
              )}
            </div>
            <div className="flex gap-2 justify-center flex-wrap">
              <a href={foiParcursApi.getContractPdfUrl(submittedContract.id, 'legal')} target="_blank" rel="noopener">
                <Button variant="outline" size="sm">
                  <FileText className="mr-1.5 h-3.5 w-3.5" />
                  Download Legal PDF
                </Button>
              </a>
              <a href={foiParcursApi.getContractPdfUrl(submittedContract.id, 'custom')} target="_blank" rel="noopener">
                <Button variant="outline" size="sm">
                  <FileText className="mr-1.5 h-3.5 w-3.5" />
                  Download Custom PDF
                </Button>
              </a>
            </div>
            <div className="flex gap-3 justify-center pt-2">
              <Button variant="outline" onClick={resetForm}>
                <Plus className="h-4 w-4 mr-1" />
                Test Drive Nou
              </Button>
              <Button onClick={() => navigate('/app/foi-parcurs')}>
                <ArrowLeft className="h-4 w-4 mr-1" />
                Inapoi la Foi de Parcurs
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6 pb-12">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate('/app/foi-parcurs')}>
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div>
          <h1 className="text-lg font-semibold">Formular Test Drive</h1>
          <p className="text-sm text-muted-foreground">Completati datele pentru test drive</p>
        </div>
      </div>

      {/* ── Section 1: Vehicle & Company ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Car className="h-4 w-4" />
            Vehicul si Companie
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Companie *</Label>
            <Select
              value={companyId ? String(companyId) : ''}
              onValueChange={(v) => {
                setCompanyId(Number(v))
                setVehicleId(null)
                setSelectedVehicle(null)
              }}
            >
              <SelectTrigger>
                <SelectValue placeholder="Selectati compania" />
              </SelectTrigger>
              <SelectContent>
                {companies.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.company}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.company && <p className="text-xs text-destructive">{errors.company}</p>}
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Vehicul *</Label>
            <Select
              value={vehicleId ? String(vehicleId) : ''}
              onValueChange={handleVehicleChange}
              disabled={!companyId}
            >
              <SelectTrigger>
                <SelectValue placeholder={companyId ? 'Selectati vehiculul' : 'Selectati mai intai compania'} />
              </SelectTrigger>
              <SelectContent>
                {filteredVehicles.map((v) => (
                  <SelectItem key={v.id} value={String(v.id)}>
                    {v.mark} {v.model} — {v.registration_number || v.vin}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.vehicle && <p className="text-xs text-destructive">{errors.vehicle}</p>}
          </div>

          {selectedVehicle && (
            <div className="rounded-md border bg-muted/50 p-3 space-y-1 text-sm">
              <p><span className="text-muted-foreground">Marca/Model:</span> {selectedVehicle.mark} {selectedVehicle.model}</p>
              <p><span className="text-muted-foreground">Nr. inmatriculare:</span> {selectedVehicle.registration_number || '—'}</p>
              <p><span className="text-muted-foreground">Combustibil:</span> {selectedVehicle.fuel_type}</p>
              <p><span className="text-muted-foreground">Capacitate rezervor:</span> {selectedVehicle.fuel_tank_capacity_liters} L</p>
            </div>
          )}

          {latestInspection && (
            <div className="rounded-md border border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950/30 p-3 space-y-1 text-sm">
              <div className="flex items-center gap-1.5 font-medium text-blue-700 dark:text-blue-300 mb-1">
                <ClipboardCheck className="h-4 w-4" />
                Ultima inspectie
              </div>
              <p><span className="text-muted-foreground">Data:</span> {new Date(latestInspection.inspection_date).toLocaleDateString('ro-RO')}</p>
              <p><span className="text-muted-foreground">Inspector:</span> {latestInspection.inspector_name}</p>
              {latestInspection.condition_notes && (
                <p><span className="text-muted-foreground">Note:</span> {latestInspection.condition_notes}</p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Section 2: Client ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Search className="h-4 w-4" />
            Client
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {selectedClient ? (
            <div className="flex items-center gap-2">
              <Badge variant="secondary" className="text-sm py-1 px-3">
                {selectedClient.display_name}
                {selectedClient.phone && ` — ${selectedClient.phone}`}
              </Badge>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setSelectedClient(null)
                  setClientSearch('')
                }}
              >
                <X className="h-4 w-4 mr-1" />
                Schimba
              </Button>
            </div>
          ) : (
            <div className="space-y-1.5 relative">
              <Label className="text-xs">Cauta client CRM *</Label>
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  className="pl-9"
                  placeholder="Nume, telefon sau email..."
                  value={clientSearch}
                  onChange={(e) => {
                    setClientSearch(e.target.value)
                    setShowClientDropdown(true)
                  }}
                  onFocus={() => setShowClientDropdown(true)}
                />
                {isSearching && (
                  <Loader2 className="absolute right-2.5 top-2.5 h-4 w-4 text-muted-foreground animate-spin" />
                )}
              </div>
              {showClientDropdown && clientResults.length > 0 && (
                <div className="absolute z-50 w-full mt-1 bg-popover border rounded-md shadow-md max-h-60 overflow-y-auto">
                  {clientResults.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      className="w-full text-left px-3 py-2 hover:bg-accent text-sm transition-colors"
                      onClick={() => {
                        setSelectedClient(c)
                        setShowClientDropdown(false)
                        setClientSearch('')
                      }}
                    >
                      <p className="font-medium">{c.display_name}</p>
                      <p className="text-xs text-muted-foreground">
                        {[c.phone, c.company_name].filter(Boolean).join(' — ') || 'Fara detalii'}
                      </p>
                    </button>
                  ))}
                </div>
              )}
              {showClientDropdown && debouncedSearch.length >= 2 && !isSearching && clientResults.length === 0 && (
                <div className="absolute z-50 w-full mt-1 bg-popover border rounded-md shadow-md p-3 text-sm text-muted-foreground text-center">
                  Niciun client gasit
                </div>
              )}
            </div>
          )}
          {errors.client && <p className="text-xs text-destructive">{errors.client}</p>}
        </CardContent>
      </Card>

      {/* ── Section 3: Route ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <MapPin className="h-4 w-4" />
            Traseu
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label className="text-xs">Data/Ora plecare *</Label>
              <Input
                type="datetime-local"
                value={departureDatetime}
                onChange={(e) => setDepartureDatetime(e.target.value)}
              />
              {errors.departure && <p className="text-xs text-destructive">{errors.departure}</p>}
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Data/Ora intoarcere</Label>
              <Input
                type="datetime-local"
                value={returnDatetime}
                onChange={(e) => setReturnDatetime(e.target.value)}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="space-y-1.5">
              <Label className="text-xs">KM Plecare *</Label>
              <Input
                type="number"
                min={0}
                placeholder="ex: 12345"
                value={odometerStart}
                onChange={(e) => setOdometerStart(e.target.value)}
              />
              {errors.odometerStart && <p className="text-xs text-destructive">{errors.odometerStart}</p>}
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">KM Sosire</Label>
              <Input
                type="number"
                min={0}
                placeholder="optional"
                value={odometerEnd}
                onChange={(e) => setOdometerEnd(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">KM Estimat *</Label>
              <Input
                type="number"
                min={0}
                placeholder="ex: 25"
                value={estimatedKm}
                onChange={(e) => setEstimatedKm(e.target.value)}
              />
              {errors.estimatedKm && <p className="text-xs text-destructive">{errors.estimatedKm}</p>}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Itinerariu *</Label>
            <Textarea
              rows={3}
              placeholder="Descrieti traseul test drive-ului..."
              value={itinerary}
              onChange={(e) => setItinerary(e.target.value)}
            />
            {errors.itinerary && <p className="text-xs text-destructive">{errors.itinerary}</p>}
          </div>
        </CardContent>
      </Card>

      {/* ── Section 4: Fuel ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Fuel className="h-4 w-4" />
            Combustibil
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label className="text-xs">Nivel combustibil plecare *</Label>
              <Select
                value={fuelGaugeStart}
                onValueChange={(v) => setFuelGaugeStart(v as FuelGaugeLevel)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Selectati nivelul" />
                </SelectTrigger>
                <SelectContent>
                  {FUEL_LEVEL_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {errors.fuelStart && <p className="text-xs text-destructive">{errors.fuelStart}</p>}
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Nivel combustibil sosire</Label>
              <Select
                value={fuelGaugeEnd}
                onValueChange={(v) => setFuelGaugeEnd(v as FuelGaugeLevel)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Selectati nivelul" />
                </SelectTrigger>
                <SelectContent>
                  {FUEL_LEVEL_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Section 5: Compliance ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <ShieldCheck className="h-4 w-4" />
            Conformitate
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-md border bg-muted/50 p-3 text-xs text-muted-foreground leading-relaxed">
            In conformitate cu Regulamentul (UE) 2016/679 (GDPR), datele dumneavoastra personale
            (nume, prenume, telefon, adresa, serie/numar act de identitate, permis de conducere)
            sunt colectate si prelucrate exclusiv in scopul organizarii si documentarii test
            drive-ului solicitat. Datele vor fi stocate pe durata necesara indeplinirii scopului
            mentionat si nu vor fi transmise catre terti, cu exceptia obligatiilor legale.
            Aveti dreptul de acces, rectificare, stergere si portabilitate a datelor, precum si
            dreptul de a va retrage consimtamantul in orice moment.
          </div>

          <div className="flex items-start gap-2">
            <Checkbox
              id="gdpr"
              checked={gdprConsent}
              onCheckedChange={(v) => setGdprConsent(v === true)}
            />
            <Label htmlFor="gdpr" className="text-xs leading-normal cursor-pointer">
              Accept prelucrarea datelor personale conform GDPR *
            </Label>
          </div>
          {errors.gdpr && <p className="text-xs text-destructive">{errors.gdpr}</p>}

          <div className="flex items-start gap-2">
            <Checkbox
              id="inspection"
              checked={inspectionAcceptance}
              onCheckedChange={(v) => setInspectionAcceptance(v === true)}
            />
            <Label htmlFor="inspection" className="text-xs leading-normal cursor-pointer">
              Accept starea tehnica a vehiculului conform ultimei inspectii *
            </Label>
          </div>
          {errors.inspection && <p className="text-xs text-destructive">{errors.inspection}</p>}

          <div className="space-y-1.5">
            <Label className="text-xs">Consilier vanzari *</Label>
            <Input
              value={advisorName}
              onChange={(e) => setAdvisorName(e.target.value)}
              placeholder="Nume consilier"
            />
            {errors.advisor && <p className="text-xs text-destructive">{errors.advisor}</p>}
          </div>
        </CardContent>
      </Card>

      {/* ── Section 6: Signatures ── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <PenLine className="h-4 w-4" />
            Semnaturi
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-1.5">
            <Label className="text-xs">Semnatura client *</Label>
            {clientSignature ? (
              <div className="space-y-2">
                <div className="border rounded-lg p-2 bg-white">
                  <img src={clientSignature} alt="Client signature" className="max-h-[100px] mx-auto" />
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setClientSignature('')}
                >
                  Resemneaza
                </Button>
              </div>
            ) : (
              <Suspense fallback={<Skeleton className="h-[200px] w-full" />}>
                <SignatureCanvas
                  onSave={setClientSignature}
                  onClear={() => setClientSignature('')}
                  width={500}
                  height={200}
                />
              </Suspense>
            )}
            {errors.clientSig && <p className="text-xs text-destructive">{errors.clientSig}</p>}
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Semnatura consilier *</Label>
            {advisorSignature ? (
              <div className="space-y-2">
                <div className="border rounded-lg p-2 bg-white">
                  <img src={advisorSignature} alt="Advisor signature" className="max-h-[100px] mx-auto" />
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setAdvisorSignature('')}
                >
                  Resemneaza
                </Button>
              </div>
            ) : (
              <Suspense fallback={<Skeleton className="h-[200px] w-full" />}>
                <SignatureCanvas
                  onSave={setAdvisorSignature}
                  onClear={() => setAdvisorSignature('')}
                  width={500}
                  height={200}
                />
              </Suspense>
            )}
            {errors.advisorSig && <p className="text-xs text-destructive">{errors.advisorSig}</p>}
          </div>
        </CardContent>
      </Card>

      {/* ── Submit ── */}
      {submitMutation.isError && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          Eroare la trimitere. Va rugam incercati din nou.
        </div>
      )}

      <Button
        className="w-full"
        size="lg"
        onClick={handleSubmit}
        disabled={submitMutation.isPending}
      >
        {submitMutation.isPending ? (
          <>
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            Se trimite...
          </>
        ) : (
          'Trimite Formular Test Drive'
        )}
      </Button>
    </div>
  )
}
