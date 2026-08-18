import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { foiParcursApi } from '@/api/foiParcurs'
import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { cn } from '@/lib/utils'
import type { FoiContract, InternalSessionPayload } from '@/types/foiParcurs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Car, ArrowLeft, CalendarPlus, Loader2, CheckCircle2, Plus } from 'lucide-react'

// ── datetime-local helper (local time, no tz suffix) — mirrors TestDriveForm ──
function localDatetimeValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export interface QuickSessionForm {
  vin: string
  driver: string
  departure: string
  ret: string
  kmStart: string
}

/** Pure validation for the internal driving-log form — ported verbatim from
 *  the mobile QuickSession form (jarvis-mobile-2 src/pages/Sales/TestDrive/
 *  QuickSession.tsx). Vehicle + driver + departure + km start are required;
 *  the return (when set) can't precede departure. Exported so it's
 *  unit-testable independently of the component. */
export function quickSessionError(f: QuickSessionForm):
  'vehicle_required' | 'driver_required' | 'departure_required' | 'km_required' | 'return_before_departure' | null {
  if (!f.vin) return 'vehicle_required'
  if (!f.driver) return 'driver_required'
  if (!f.departure) return 'departure_required'
  if (!f.kmStart) return 'km_required'
  if (f.ret && f.ret < f.departure) return 'return_before_departure'
  return null
}

const MESSAGES: Record<string, string> = {
  vehicle_required: 'Alege mașina.',
  driver_required: 'Alege șoferul.',
  departure_required: 'Alege data plecării.',
  km_required: 'Introdu km la plecare.',
  return_before_departure: 'Data sosirii nu poate fi înainte de plecare.',
}

interface InternalSessionFormProps {
  embedded?: boolean
  initialCompanyId?: number
  /** Seed the departure datetime ("YYYY-MM-DDTHH:MM"), e.g. from a calendar
   *  slot the user dragged/clicked. Return defaults to +1h. */
  initialDeparture?: string
  /** Seed the return datetime ("YYYY-MM-DDTHH:MM"). */
  initialReturn?: string
  onDone?: (contract: FoiContract) => void
  onCancel?: () => void
}

/** Slim internal driving-log form (Client/Intern chooser → "Intern") — a web
 *  port of the mobile QuickSession screen. Creates a normal FILLED test drive
 *  tagged is_internal (no client/signature/GDPR/fuel/damage), reusing the
 *  standard TestDriveReturn flow. Company is auto-derived from the chosen
 *  car; km plecare pre-fills from the car's live odometer. */
export default function InternalSessionForm({
  embedded,
  initialCompanyId,
  initialDeparture,
  initialReturn,
  onDone,
  onCancel,
}: InternalSessionFormProps = {}) {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const [searchParams] = useSearchParams()

  const seedDeparture = initialDeparture ?? searchParams.get('departure') ?? undefined
  const seedReturn = initialReturn ?? searchParams.get('return') ?? undefined

  const [vin, setVin] = useState('')
  const [driver, setDriver] = useState(user?.name ?? '')
  const [departure, setDeparture] = useState(() => seedDeparture ?? localDatetimeValue(new Date()))
  const [ret, setRet] = useState(() => {
    if (seedReturn) return seedReturn
    const base = seedDeparture ? new Date(seedDeparture) : new Date()
    return localDatetimeValue(new Date(base.getTime() + 60 * 60 * 1000))
  })
  const [kmStart, setKmStart] = useState('')
  const [comment, setComment] = useState('')
  const [attempted, setAttempted] = useState(false)
  const [noCompanyError, setNoCompanyError] = useState(false)
  const [submittedContract, setSubmittedContract] = useState<FoiContract | null>(null)

  useEffect(() => {
    if (user?.name && !driver) setDriver(user.name)
  }, [user?.name]) // eslint-disable-line react-hooks/exhaustive-deps

  const { data: vehiclesData } = useQuery({
    queryKey: ['fp-vehicles', 'all'],
    queryFn: () => foiParcursApi.getVehicles(false),
  })
  const allVehicles = vehiclesData?.vehicles ?? []
  // Scope the picker to the calling context's company when one is provided
  // (e.g. the Hub panel's currently-selected company); otherwise show every
  // active/known vehicle, mirroring the mobile QuickSession picker.
  const vehicles = useMemo(
    () => (initialCompanyId ? allVehicles.filter((v) => v.company_id === initialCompanyId) : allVehicles),
    [allVehicles, initialCompanyId],
  )
  const selectedVehicle = useMemo(() => allVehicles.find((v) => v.vin === vin) ?? null, [allVehicles, vin])

  const handleVehicleChange = (nextVin: string) => {
    setVin(nextVin)
    setNoCompanyError(false)
    const v = allVehicles.find((x) => x.vin === nextVin)
    if (v?.odometer_km != null && !kmStart) setKmStart(String(v.odometer_km))
  }

  const validationError = quickSessionError({ vin, driver, departure, ret, kmStart })
  const fieldErr = (key: string) => attempted && validationError === key

  const submitMutation = useMutation({
    mutationFn: (payload: InternalSessionPayload) => foiParcursApi.submitInternalSession(payload),
    onSuccess: (data) => {
      if (embedded) onDone?.(data.contract)
      else setSubmittedContract(data.contract)
    },
  })

  function handleSubmit() {
    if (submitMutation.isPending) return
    if (validationError) {
      setAttempted(true)
      return
    }
    const companyId = selectedVehicle?.company_id
    if (companyId == null) {
      setAttempted(true)
      setNoCompanyError(true)
      return
    }
    setAttempted(false)
    setNoCompanyError(false)
    submitMutation.mutate({
      is_internal: true,
      company_id: Number(companyId),
      vin,
      advisor_name: driver.trim(),
      departure_datetime: departure,
      ...(ret ? { return_datetime: ret } : {}),
      odometer_start: Number(kmStart),
      ...(comment.trim() ? { itinerary: comment.trim() } : {}),
    })
  }

  const handleBack = () => { if (embedded) onCancel?.(); else navigate('/app/foi-parcurs') }

  function resetForm() {
    setVin('')
    setDriver(user?.name ?? '')
    setDeparture(localDatetimeValue(new Date()))
    setRet(localDatetimeValue(new Date(Date.now() + 60 * 60 * 1000)))
    setKmStart('')
    setComment('')
    setAttempted(false)
    setNoCompanyError(false)
    setSubmittedContract(null)
    submitMutation.reset()
  }

  // Surface the backend 409 (locked_out / open-session) — or any other submit
  // error — inline, without the full admin-override retry flow (the internal
  // form is intentionally slim; an advisor blocked this way just picks
  // another car or contacts an admin).
  const apiErrorMessage = submitMutation.isError
    ? ((submitMutation.error instanceof ApiError ? (submitMutation.error.data as { error?: string } | null)?.error : null)
        ?? 'Crearea sesiunii a eșuat. Încearcă din nou.')
    : null

  // ── Success screen — mirrors TestDriveForm's, minus the PDF links (an
  //    internal session has no signature/GDPR, so no legal/custom PDF). ──
  if (submittedContract) {
    return (
      <div className="max-w-lg mx-auto py-12 space-y-6">
        <Card>
          <CardContent className="pt-6 text-center space-y-4">
            <CheckCircle2 className="mx-auto h-16 w-16 text-green-500" />
            <h2 className="text-xl font-semibold">Sesiune Internă Înregistrată</h2>
            <div className="text-sm text-muted-foreground space-y-1">
              <p>Contract: <span className="font-medium text-foreground">{submittedContract.contract_id}</span></p>
              {submittedContract.vin && <p>VIN: <span className="font-medium text-foreground">{submittedContract.vin}</span></p>}
              {submittedContract.advisor_name && <p>Șofer: <span className="font-medium text-foreground">{submittedContract.advisor_name}</span></p>}
            </div>
            <div className="flex gap-3 justify-center pt-2">
              <Button variant="outline" onClick={resetForm}><Plus className="h-4 w-4 mr-1" />Sesiune Internă Nouă</Button>
              <Button onClick={handleBack}><ArrowLeft className="h-4 w-4 mr-1" />Înapoi la Driving Hub</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="max-w-lg mx-auto space-y-6 pb-12">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" aria-label="Înapoi" onClick={handleBack}>
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div>
          <h1 className="text-lg font-semibold">Sesiune Internă Nouă</h1>
          <p className="text-sm text-muted-foreground">Jurnal de conducere intern — fără client sau semnătură</p>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2"><Car className="h-4 w-4" />Detalii sesiune</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Mașină *</Label>
            <Select value={vin} onValueChange={handleVehicleChange}>
              <SelectTrigger data-testid="internal-vehicle" className={cn('w-full', fieldErr('vehicle_required') && 'ring-2 ring-destructive')}>
                <SelectValue placeholder="Selectează mașina" />
              </SelectTrigger>
              <SelectContent>
                {vehicles.filter((v) => v.vin).map((v) => (
                  <SelectItem key={v.id} value={v.vin}>
                    {[v.mark, v.model].filter(Boolean).join(' ') || '—'} — {v.registration_number || v.vin}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {noCompanyError && (
              <p className="text-xs text-destructive">Mașina selectată nu are companie asociată.</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Șofer *</Label>
            <Input
              data-testid="internal-driver"
              className={cn(fieldErr('driver_required') && 'ring-2 ring-destructive')}
              value={driver}
              onChange={(e) => setDriver(e.target.value)}
              placeholder="Numele șoferului"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Data plecării *</Label>
              <Input
                data-testid="internal-departure"
                type="datetime-local"
                className={cn(fieldErr('departure_required') && 'ring-2 ring-destructive')}
                value={departure}
                onChange={(e) => setDeparture(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Data sosirii</Label>
              <Input
                data-testid="internal-return"
                type="datetime-local"
                min={departure || undefined}
                className={cn(fieldErr('return_before_departure') && 'ring-2 ring-destructive')}
                value={ret}
                onChange={(e) => setRet(e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">KM plecare *</Label>
            <Input
              data-testid="internal-km"
              type="number"
              inputMode="numeric"
              className={cn(fieldErr('km_required') && 'ring-2 ring-destructive')}
              value={kmStart}
              onChange={(e) => setKmStart(e.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Comentariu</Label>
            <Input
              data-testid="internal-comment"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Observații (opțional)"
            />
          </div>
        </CardContent>
      </Card>

      {apiErrorMessage && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {apiErrorMessage}
        </div>
      )}
      {attempted && validationError && (
        <p className="text-xs text-destructive text-center">{MESSAGES[validationError]}</p>
      )}

      <Button className="w-full" size="lg" onClick={handleSubmit} disabled={submitMutation.isPending}>
        {submitMutation.isPending
          ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Se creează...</>
          : <><CalendarPlus className="h-4 w-4 mr-2" />Creează sesiunea</>}
      </Button>
    </div>
  )
}
