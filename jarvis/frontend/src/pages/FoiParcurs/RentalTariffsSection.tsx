import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Coins } from 'lucide-react'
import { toast } from 'sonner'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { foiParcursApi } from '@/api/foiParcurs'
import type { FpVehicle } from '@/types/foiParcurs'

type TariffFields = {
  svc_tariff_eur_day: string
  svc_tariff_eur_month: string
  svc_km_included_day: string
  svc_extra_km_eur: string
  svc_deposit_eur: string
  svc_franchise_eur: string
}

const EMPTY_TARIFF: TariffFields = {
  svc_tariff_eur_day: '',
  svc_tariff_eur_month: '',
  svc_km_included_day: '',
  svc_extra_km_eur: '',
  svc_deposit_eur: '',
  svc_franchise_eur: '',
}

function toStr(v: number | null | undefined): string {
  return v === null || v === undefined ? '' : String(v)
}

function toNumOrNull(s: string): number | null {
  return s.trim() === '' ? null : Number(s)
}

type CompanyPolicyDefaults = {
  svc_km_included_day: number | null
  svc_extra_km_eur: number | null
  svc_deposit_eur: number | null
  svc_franchise_eur: number | null
} | undefined

/** Discoverable "Tarife" price-list — the source of the day/month rental rate
 *  + km/extra-km/deposit/franchise policy for a company's courtesy
 *  (Service-pool) cars, saved per car via updateVehicle. Mirrors
 *  ContractConfigSection's structure (own company selector; SettingsTab has
 *  none of its own). See docs/superpowers/specs/2026-08-24-foi-parcurs-
 *  service-courtesy-cars-design.md for the "where do I set tariffs" gap this
 *  answers (R3). */
export default function RentalTariffsSection() {
  const qc = useQueryClient()
  const [selectedCompany, setSelectedCompany] = useState<string>('')
  const companyId = selectedCompany ? Number(selectedCompany) : null

  const { data: companiesData } = useQuery({
    queryKey: ['fp-companies'],
    queryFn: () => foiParcursApi.getCompanies(),
    staleTime: 60_000,
  })
  const companies = companiesData?.companies ?? []

  // Service-pool cars across ALL companies (documentType='service', per
  // R1/S6a) — filtered client-side to the selected company below.
  const { data: vehiclesData, isLoading } = useQuery({
    queryKey: ['fp-vehicles', 'all', 'service'],
    queryFn: () => foiParcursApi.getVehicles(true, 'service'),
    enabled: !!companyId,
    staleTime: 30_000,
  })
  const cars = (vehiclesData?.vehicles ?? []).filter((v) => v.company_id === companyId)

  const { data: configData } = useQuery({
    queryKey: ['fp-company-config', companyId],
    queryFn: () => foiParcursApi.getCompanyConfig(companyId!),
    enabled: !!companyId,
    staleTime: 30_000,
  })
  const defaults: CompanyPolicyDefaults = configData?.config

  const saveMut = useMutation({
    mutationFn: ({ id, values }: { id: number; values: TariffFields }) =>
      foiParcursApi.updateVehicle(id, {
        svc_tariff_eur_day: toNumOrNull(values.svc_tariff_eur_day),
        svc_tariff_eur_month: toNumOrNull(values.svc_tariff_eur_month),
        svc_km_included_day: toNumOrNull(values.svc_km_included_day),
        svc_extra_km_eur: toNumOrNull(values.svc_extra_km_eur),
        svc_deposit_eur: toNumOrNull(values.svc_deposit_eur),
        svc_franchise_eur: toNumOrNull(values.svc_franchise_eur),
      }),
    onSuccess: (_data, vars) => {
      toast.success('Tarif salvat')
      qc.invalidateQueries({ queryKey: ['fp-vehicles', 'all', 'service'] })
      qc.invalidateQueries({ queryKey: ['fp-vehicle', vars.id] })
    },
    onError: (err: any) => {
      toast.error(err?.status === 403 ? 'Nu ai permisiuni pentru a salva tariful.' : 'Salvarea tarifului a eșuat')
    },
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Coins className="h-5 w-5 text-muted-foreground" />
        <h3 className="text-lg font-semibold">Tarife mașini de curtoazie</h3>
      </div>
      <p className="text-sm text-muted-foreground">
        Tarif €/zi, Tarif €/lună și politica (km incluși, extra km, garanție, franșiză) per mașină
        de curtoazie. Un câmp lăsat gol moștenește valoarea implicită a companiei, setată mai jos
        la "Politică implicită mașini de curtoazie".
      </p>

      <div className="max-w-sm space-y-1.5">
        <Label>Company</Label>
        <Select value={selectedCompany} onValueChange={setSelectedCompany}>
          <SelectTrigger>
            <SelectValue placeholder="Selectează o companie..." />
          </SelectTrigger>
          <SelectContent>
            {companies.map((c) => (
              <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {!companyId ? null : isLoading ? (
        <p className="py-4 text-sm text-muted-foreground">Se încarcă…</p>
      ) : !cars.length ? (
        <p className="py-4 text-sm text-muted-foreground">Nicio mașină de curtoazie pentru această companie.</p>
      ) : (
        <div className="space-y-3">
          {cars.map((car) => (
            <TariffRow
              key={car.id}
              car={car}
              defaults={defaults}
              isSaving={saveMut.isPending}
              onSave={(values) => saveMut.mutate({ id: car.id, values })}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function TariffRow({ car, defaults, onSave, isSaving }: {
  car: FpVehicle
  defaults: CompanyPolicyDefaults
  onSave: (values: TariffFields) => void
  isSaving: boolean
}) {
  // The Driving-Park lean list (getVehicles) only carries svc_tariff_eur_day/
  // _month (see vehicle_repository._LIST_SELECT); the other 4 policy columns
  // only come back on the full row. Fetch it per-row so a save that only
  // touches the rate never silently nulls out an already-set policy value.
  const { data: fullData } = useQuery({
    queryKey: ['fp-vehicle', car.id],
    queryFn: () => foiParcursApi.getVehicle(car.id),
    staleTime: 30_000,
  })
  const full = fullData?.vehicle

  const [draft, setDraft] = useState<TariffFields>(EMPTY_TARIFF)

  // Re-sync when the underlying data changes (initial load, full-row arrival,
  // or after a successful save invalidates + refetches) — mirrors
  // ContractConfigSection's ContractBrandRow.
  useEffect(() => {
    const source = full ?? car
    setDraft({
      svc_tariff_eur_day: toStr(source.svc_tariff_eur_day),
      svc_tariff_eur_month: toStr(source.svc_tariff_eur_month),
      svc_km_included_day: toStr(full?.svc_km_included_day),
      svc_extra_km_eur: toStr(full?.svc_extra_km_eur),
      svc_deposit_eur: toStr(full?.svc_deposit_eur),
      svc_franchise_eur: toStr(full?.svc_franchise_eur),
    })
  }, [full, car])

  const set = <K extends keyof TariffFields>(k: K, v: TariffFields[K]) => setDraft((p) => ({ ...p, [k]: v }))

  const label = [car.mark, car.model].filter(Boolean).join(' ') || car.brand || car.vin
  const subLabel = [car.registration_number, car.brand].filter(Boolean).join(' · ')

  return (
    <Card className="space-y-3 p-4">
      <div>
        <div className="text-sm font-medium">{label}</div>
        {subLabel && <div className="text-xs text-muted-foreground">{subLabel}</div>}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <div className="space-y-1.5">
          <Label className="text-xs">Tarif €/zi</Label>
          <Input
            type="number"
            step="0.01"
            value={draft.svc_tariff_eur_day}
            onChange={(e) => set('svc_tariff_eur_day', e.target.value)}
            placeholder="implicit"
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Tarif €/lună</Label>
          <Input
            type="number"
            step="0.01"
            value={draft.svc_tariff_eur_month}
            onChange={(e) => set('svc_tariff_eur_month', e.target.value)}
            placeholder="implicit"
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Km incluși/zi</Label>
          <Input
            type="number"
            step="1"
            value={draft.svc_km_included_day}
            onChange={(e) => set('svc_km_included_day', e.target.value)}
            placeholder={defaults?.svc_km_included_day != null ? String(defaults.svc_km_included_day) : 'implicit companie'}
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Extra km €</Label>
          <Input
            type="number"
            step="0.01"
            value={draft.svc_extra_km_eur}
            onChange={(e) => set('svc_extra_km_eur', e.target.value)}
            placeholder={defaults?.svc_extra_km_eur != null ? String(defaults.svc_extra_km_eur) : 'implicit companie'}
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Garanție €</Label>
          <Input
            type="number"
            step="0.01"
            value={draft.svc_deposit_eur}
            onChange={(e) => set('svc_deposit_eur', e.target.value)}
            placeholder={defaults?.svc_deposit_eur != null ? String(defaults.svc_deposit_eur) : 'implicit companie'}
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Franșiză €</Label>
          <Input
            type="number"
            step="0.01"
            value={draft.svc_franchise_eur}
            onChange={(e) => set('svc_franchise_eur', e.target.value)}
            placeholder={defaults?.svc_franchise_eur != null ? String(defaults.svc_franchise_eur) : 'implicit companie'}
          />
        </div>
      </div>

      <Button size="sm" onClick={() => onSave(draft)} disabled={isSaving}>
        {isSaving ? 'Se salvează...' : 'Salvează'}
      </Button>
    </Card>
  )
}
