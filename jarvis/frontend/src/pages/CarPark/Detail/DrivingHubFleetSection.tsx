// CarPark vehicle Detail (Anunțuri tab) — "Driving Hub" fleet push section.
// Task 4 of the CarPark -> Driving Hub fleet push feature: a thin UI over the
// Task 2-3 backend (carpark/routes/driving_hub.py +
// carpark/services/driving_hub_push_service.py). Three states per the design:
// not in fleet -> "Adaugă în Driving Hub" (opens the prefill dialog); in
// fleet -> badge + link into the hub; archived -> same badge/link, but the
// add button stays visible (disabled) so it's clear re-adding isn't possible
// from here. Mirrors the react-query + dialog idiom of the sibling
// AutoworldPublishRow.tsx.
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Car } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { carparkApi, type DrivingHubPushPayload } from '@/api/carpark'
import { foiParcursApi } from '@/api/foiParcurs'

// Fleet's own (narrower) fuel enum — mirrors the Select in
// FoiParcurs/index.tsx's own vehicle-create form, which fp_vehicles rows are
// validated against (foi_parcurs/services/vehicle_create.py).
const FUEL_TYPES = ['Benzina', 'Diesel', 'Electric', 'Hybrid', 'Plug-in Hybrid'] as const
const TANK_FUELS = new Set<string>(['Benzina', 'Diesel', 'Hybrid', 'Plug-in Hybrid'])
const BATTERY_FUELS = new Set<string>(['Electric', 'Plug-in Hybrid'])

const usesTank = (fuel: string) => TANK_FUELS.has(fuel)
const usesBattery = (fuel: string) => BATTERY_FUELS.has(fuel)

function pushErrorMessage(err: unknown): string {
  const e = err as { data?: { error?: string }; message?: string } | null | undefined
  return e?.data?.error || e?.message || 'Eroare la adăugarea în Driving Hub'
}

// Pick the catalog label that best matches the CarPark make: exact
// (case-insensitive) first, else a catalog entry that starts with or contains
// the make (e.g. make 'MG' -> 'MG Motor', 'Volkswagen' -> 'Volkswagen (PKW)',
// 'MAZDA' -> 'Mazda'). Returns '' when nothing matches, forcing a manual pick.
function bestBrandMatch(catalog: string[], make: string | null | undefined): string {
  if (catalog.length === 0 || !make) return ''
  const m = make.trim().toLowerCase()
  const exact = catalog.find((b) => b.toLowerCase() === m)
  if (exact) return exact
  const partial = catalog.find((b) => {
    const bl = b.toLowerCase()
    return bl.startsWith(m) || bl.includes(m)
  })
  return partial ?? ''
}

export function DrivingHubFleetSection({ vehicleId, canEdit }: { vehicleId: number; canEdit: boolean }) {
  const queryClient = useQueryClient()
  const statusKey = ['driving-hub', 'status', vehicleId]

  const [dialogOpen, setDialogOpen] = useState(false)
  const [mark, setMark] = useState('')
  const [brand, setBrand] = useState('')
  const [model, setModel] = useState('')
  const [registrationNumber, setRegistrationNumber] = useState('')
  const [fuelType, setFuelType] = useState('')
  const [companyId, setCompanyId] = useState<number | null>(null)
  const [odometerKm, setOdometerKm] = useState('')
  const [tankLiters, setTankLiters] = useState('')
  const [batteryKwh, setBatteryKwh] = useState('')

  const { data } = useQuery({
    queryKey: statusKey,
    queryFn: () => carparkApi.getDrivingHubStatus(vehicleId),
    enabled: !!vehicleId && canEdit,
  })

  const suggested = data?.suggested ?? null
  const needsCompanyPick = suggested != null && suggested.company_id == null

  const { data: companiesData } = useQuery({
    queryKey: ['carpark', 'companies'],
    queryFn: () => carparkApi.getCompanies(),
    // Enabled on the read-only path too, so the company NAME resolves for the
    // disabled input instead of falling back to "#<id>".
    enabled: dialogOpen,
    staleTime: 60_000,
  })
  const companies = companiesData?.companies ?? []

  // The fleet brand MUST be an exact company_brands catalog label (the Driving
  // Hub filters its pickers by exact string) — not the free-text CarPark make.
  // The effective company is the car's own, or the one picked in the no-company
  // path; fetch its catalog labels (same source as the TD form's Marcă picker).
  const effectiveCompanyId = suggested?.company_id ?? companyId
  const { data: brandsData } = useQuery({
    queryKey: ['fp-brands', effectiveCompanyId],
    queryFn: () => foiParcursApi.getBrands(effectiveCompanyId as number),
    enabled: dialogOpen && effectiveCompanyId != null,
    staleTime: 60_000,
  })
  const brands = brandsData?.brands ?? []

  // Default-select the catalog label best matching the make when the catalog
  // (re)loads; leave unset if nothing matches so the user must pick. Empty
  // catalog (courtesy/rental-only company) -> no Select, make is used as brand.
  useEffect(() => {
    if (!dialogOpen) return
    const list = brandsData?.brands ?? []
    if (list.length === 0) {
      if (brand !== '') setBrand('')
    } else if (!list.includes(brand)) {
      setBrand(bestBrandMatch(list, suggested?.mark))
    }
  }, [brandsData, dialogOpen, suggested?.mark, brand])

  const invalidateStatus = () => queryClient.invalidateQueries({ queryKey: statusKey })

  const pushMutation = useMutation({
    mutationFn: (payload: DrivingHubPushPayload) => carparkApi.pushToDrivingHub(vehicleId, payload),
    onSuccess: () => {
      invalidateStatus()
      toast.success('Vehicul adăugat în flota Driving Hub')
      setDialogOpen(false)
    },
    onError: (err: unknown) => {
      // A 409 means the car is already in the fleet (e.g. a concurrent push,
      // or the status check was stale) — treat it as success-ish: flip the
      // section to "În flotă" rather than showing a hard error.
      if ((err as { status?: number } | null)?.status === 409) {
        invalidateStatus()
        toast.info('Vehiculul este deja în flota Driving Hub')
        setDialogOpen(false)
        return
      }
      toast.error(pushErrorMessage(err))
    },
  })

  function openDialog() {
    if (!suggested) return
    setMark(suggested.mark ?? '')
    // The brand Select defaults via the catalog-load effect once brands arrive.
    setBrand('')
    setModel(suggested.model ?? '')
    setRegistrationNumber(suggested.registration_number ?? '')
    setFuelType(suggested.fuel_type ?? '')
    setCompanyId(suggested.company_id ?? null)
    setOdometerKm(suggested.odometer_km != null ? String(suggested.odometer_km) : '')
    setTankLiters('')
    setBatteryKwh('')
    setDialogOpen(true)
  }

  const tankRequired = usesTank(fuelType)
  const batteryRequired = usesBattery(fuelType)
  const tankOk = !tankRequired || (tankLiters.trim() !== '' && Number(tankLiters) > 0)
  const batteryOk = !batteryRequired || (batteryKwh.trim() !== '' && Number(batteryKwh) > 0)
  const companyOk = !needsCompanyPick || companyId != null
  // A fleet brand is required whenever the company HAS a sales catalog; an empty
  // catalog (courtesy/rental-only) falls back to the make, so it never blocks.
  const brandOk = brands.length === 0 || brand !== ''
  const canSubmit = fuelType !== '' && tankOk && batteryOk && companyOk && brandOk && !pushMutation.isPending

  function handleConfirm() {
    if (!suggested || !canSubmit) return
    const payload: DrivingHubPushPayload = {
      mark: mark.trim() || null,
      brand: brands.length > 0 ? brand : (mark.trim() || null),
      model: model.trim() || null,
      registration_number: registrationNumber.trim() || null,
      fuel_type: fuelType,
      company_id: (companyId ?? suggested.company_id) as number,
      odometer_km: odometerKm.trim() !== '' ? Number(odometerKm) : null,
      color: suggested.color,
      ...(tankRequired ? { fuel_tank_capacity_liters: Number(tankLiters) } : {}),
      ...(batteryRequired ? { battery_capacity_kwh: Number(batteryKwh) } : {}),
    }
    pushMutation.mutate(payload)
  }

  if (!canEdit) return null

  return (
    <section className="space-y-3">
      <div>
        <h3 className="text-base font-semibold tracking-tight">Driving Hub</h3>
        <p className="text-sm text-muted-foreground">
          Adaugă acest vehicul în flota Driving Hub pentru sesiuni Test Drive și interne.
        </p>
      </div>

      <div className="flex items-center justify-between gap-3 rounded-xl border bg-card p-4 text-card-foreground shadow-sm">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-muted text-muted-foreground">
            <Car className="h-5 w-5" />
          </span>
          <div className="min-w-0 text-sm font-medium">Flotă Driving Hub</div>
        </div>

        {data && (
          <div className="flex items-center gap-3">
            {data.in_fleet && (
              <>
                <Badge
                  variant="secondary"
                  className={
                    data.archived
                      ? 'font-normal text-muted-foreground'
                      : 'font-normal bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                  }
                >
                  {data.archived ? 'În flotă (arhivat)' : 'În flotă ✓'}
                </Badge>
                <a
                  href="/app/foi-parcurs"
                  className="text-sm font-medium text-primary underline-offset-4 hover:underline"
                >
                  Deschide în Driving Hub
                </a>
              </>
            )}
            {(!data.in_fleet || data.archived) && (
              <Button size="sm" onClick={openDialog} disabled={data.archived}>
                Adaugă în Driving Hub
              </Button>
            )}
          </div>
        )}
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Adaugă în Driving Hub</DialogTitle>
            <DialogDescription>
              Completează datele vehiculului înainte de a-l adăuga în flota Driving Hub.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="dh-mark">Marcă</Label>
              <Input id="dh-mark" value={mark} onChange={(e) => setMark(e.target.value)} />
            </div>

            {brands.length > 0 && (
              <div className="space-y-1">
                <Label htmlFor="dh-brand">Marcă (flotă)</Label>
                <Select value={brand || undefined} onValueChange={setBrand}>
                  <SelectTrigger id="dh-brand">
                    <SelectValue placeholder="Selectează marca din flotă" />
                  </SelectTrigger>
                  <SelectContent>
                    {brands.map((b) => (
                      <SelectItem key={b} value={b}>
                        {b}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            <div className="space-y-1">
              <Label htmlFor="dh-model">Model</Label>
              <Input id="dh-model" value={model} onChange={(e) => setModel(e.target.value)} />
            </div>

            <div className="space-y-1">
              <Label htmlFor="dh-reg">Număr înmatriculare</Label>
              <Input
                id="dh-reg"
                value={registrationNumber}
                onChange={(e) => setRegistrationNumber(e.target.value)}
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor="dh-fuel">Combustibil</Label>
              <Select value={fuelType || undefined} onValueChange={setFuelType}>
                <SelectTrigger id="dh-fuel">
                  <SelectValue placeholder="Selectează combustibilul" />
                </SelectTrigger>
                <SelectContent>
                  {FUEL_TYPES.map((f) => (
                    <SelectItem key={f} value={f}>
                      {f}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {tankRequired && (
              <div className="space-y-1">
                <Label htmlFor="dh-tank">Capacitate rezervor (L)</Label>
                <Input
                  id="dh-tank"
                  type="number"
                  min={0}
                  step="any"
                  value={tankLiters}
                  onChange={(e) => setTankLiters(e.target.value)}
                  required
                />
              </div>
            )}

            {batteryRequired && (
              <div className="space-y-1">
                <Label htmlFor="dh-battery">Capacitate baterie (kWh)</Label>
                <Input
                  id="dh-battery"
                  type="number"
                  min={0}
                  step="any"
                  value={batteryKwh}
                  onChange={(e) => setBatteryKwh(e.target.value)}
                  required
                />
              </div>
            )}

            <div className="space-y-1">
              <Label htmlFor="dh-company">Companie</Label>
              {needsCompanyPick ? (
                <Select
                  value={companyId != null ? String(companyId) : undefined}
                  onValueChange={(v) => setCompanyId(Number(v))}
                >
                  <SelectTrigger id="dh-company">
                    <SelectValue placeholder="Selectează compania" />
                  </SelectTrigger>
                  <SelectContent>
                    {companies.map((c) => (
                      <SelectItem key={c.id} value={String(c.id)}>
                        {c.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Input
                  id="dh-company"
                  readOnly
                  disabled
                  value={companies.find((c) => c.id === suggested?.company_id)?.name ?? `Compania vehiculului (#${suggested?.company_id ?? ''})`}
                />
              )}
            </div>

            <div className="space-y-1">
              <Label htmlFor="dh-km">Km</Label>
              <Input
                id="dh-km"
                type="number"
                min={0}
                value={odometerKm}
                onChange={(e) => setOdometerKm(e.target.value)}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              Anulează
            </Button>
            <Button onClick={handleConfirm} disabled={!canSubmit}>
              {pushMutation.isPending ? 'Se adaugă...' : 'Adaugă în flotă'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  )
}

export default DrivingHubFleetSection
