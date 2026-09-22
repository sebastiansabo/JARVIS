import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ImagePlus, X, Loader2, ScanLine, Users, UserPlus } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { foiParcursApi } from '@/api/foiParcurs'
import { crmApi } from '@/api/crm'
import { fileToCompressedDataUrl } from '@/lib/imageCompress'
import { RO_COUNTIES, RO_CITIES } from '@/data/roLocalities'
import { Autocomplete } from '@/components/shared/Autocomplete'
import type { CrmClient } from '@/types/foiParcurs'
import { composePhone, COUNTRY_DIAL_CODES } from './phoneFormat'

/** Country options — România default, common others after. */
const COUNTRIES = [
  'România',
  'Republica Moldova',
  'Ungaria',
  'Bulgaria',
  'Germania',
  'Italia',
  'Spania',
  'Franța',
  'Austria',
  'Marea Britanie',
]

/** License a duplicate-suggestion client can hand back: its number, and the
 *  expiry only if it hasn't lapsed (an expired one must be re-captured). */
function reusableLicense(c: CrmClient): { number: string; expiry: string } {
  const number = (c.driver_license_number || '').trim()
  const exp = (c.driver_license_expiry || '').trim()
  const t = Date.parse(exp)
  const valid = exp !== '' && !Number.isNaN(t) && new Date(t) >= new Date(new Date().toDateString())
  return { number, expiry: valid ? exp : '' }
}

/** Required driving-license photo (stored on the contract) plus, when no client
 *  is selected yet, an OCR-assisted "create CRM client from the license" flow.
 *  The uploaded photo doubles as the OCR source and the contract attachment. */
export function DriverLicenseSection({
  photo,
  onPhotoChange,
  invalid,
  hasClient,
  onSelectClient,
  onLicenseNumber,
  onLicenseExpiry,
}: {
  photo: string | null
  onPhotoChange: (value: string | null) => void
  invalid?: boolean
  hasClient: boolean
  onSelectClient: (client: CrmClient) => void
  onLicenseNumber: (value: string) => void
  onLicenseExpiry?: (value: string) => void
}) {
  const [busy, setBusy] = useState(false)
  const [showCreate, setShowCreate] = useState(false)

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setBusy(true)
    const compressed = await fileToCompressedDataUrl(file)
    setBusy(false)
    if (compressed) onPhotoChange(compressed)
  }

  return (
    <div className="space-y-3">
      {photo ? (
        <div className="flex items-center gap-3">
          <img src={photo} alt="Permis de conducere" className="h-20 w-32 rounded-md object-cover border" />
          <Button type="button" variant="ghost" size="sm" className="text-destructive" onClick={() => onPhotoChange(null)}>
            <X className="h-3.5 w-3.5 mr-1" /> Șterge
          </Button>
        </div>
      ) : (
        <label
          className={cn(
            'flex h-20 w-full cursor-pointer flex-col items-center justify-center gap-1 rounded-md border-2 border-dashed text-muted-foreground hover:bg-accent transition-colors',
            invalid && 'border-destructive',
          )}
        >
          {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <ImagePlus className="h-5 w-5" />}
          <span className="text-xs font-medium">Adaugă poza permisului</span>
          <input type="file" accept="image/*" className="hidden" onChange={handleFile} />
        </label>
      )}

      {!photo && (
        <p className={cn('text-xs', invalid ? 'text-destructive' : 'text-muted-foreground')}>
          Poza permisului de conducere este obligatorie.
        </p>
      )}

      {!hasClient && !showCreate && (
        <Button type="button" variant="secondary" className="w-full" onClick={() => setShowCreate(true)}>
          <UserPlus className="h-4 w-4 mr-2" />
          Adaugă client nou
        </Button>
      )}

      {!hasClient && showCreate && (
        <CreateClientPanel
          onCancel={() => setShowCreate(false)}
          onCreated={(client, licenseNumber, licenseExpiry, licensePhoto) => {
            onSelectClient(client)
            if (licenseNumber) onLicenseNumber(licenseNumber)
            if (licenseExpiry) onLicenseExpiry?.(licenseExpiry)
            // The licence photo captured while creating the client doubles as
            // the drive's licence photo, so it's never captured twice.
            if (licensePhoto) onPhotoChange(licensePhoto)
            setShowCreate(false)
          }}
        />
      )}
    </div>
  )
}

/** Inline "new CRM client" form, prefilled from the license OCR where legible.
 *  Name + phone required; the rest optional. Creates in crm_clients. */
export function CreateClientPanel({
  onCancel,
  onCreated,
}: {
  onCancel: () => void
  onCreated: (
    client: CrmClient,
    licenseNumber: string,
    licenseExpiry: string,
    licensePhoto: string | null,
  ) => void
}) {
  const [name, setName] = useState('')
  const [dialCode, setDialCode] = useState('+40')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [isCompany, setIsCompany] = useState(false)
  const [companyName, setCompanyName] = useState('')
  const [cui, setCui] = useState('')
  const [licenseNumber, setLicenseNumber] = useState('')
  const [licenseExpiry, setLicenseExpiry] = useState('')
  const [address, setAddress] = useState('')
  const [country, setCountry] = useState('România')
  const [county, setCounty] = useState('')
  const [city, setCity] = useState('')
  const [licensePhoto, setLicensePhoto] = useState<string | null>(null)
  const [scanBusy, setScanBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const ocr = useMutation({
    mutationFn: (image: string) => foiParcursApi.driverLicenseOcr(image),
  })

  /** Capture the licence photo, OCR it, and prefill the form. The photo is kept
   *  and returned on create so it can become the drive's licence photo too. */
  const handleScanFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setError(null)
    setScanBusy(true)
    const compressed = await fileToCompressedDataUrl(file)
    setScanBusy(false)
    if (!compressed) return
    setLicensePhoto(compressed)
    ocr.mutate(compressed, {
      onSuccess: (res) => {
        const data = res.data ?? {}
        if (data.full_name) setName(data.full_name)
        if (data.license_number) setLicenseNumber(data.license_number)
        if (data.expiry_date) setLicenseExpiry(data.expiry_date)
        if (data.address) setAddress(data.address)
        if (data.county) setCounty(data.county)
        if (data.city) setCity(data.city)
      },
      onError: (err: any) => {
        setError(err?.data?.error || err?.message || 'Scanarea a eșuat. Completează manual.')
      },
    })
  }

  // County first: choosing a județ scopes the city list to that county's towns.
  const cityOptions = useMemo(() => {
    const scoped = county ? RO_CITIES.filter((c) => c.county === county) : RO_CITIES
    return scoped.map((c) => c.name)
  }, [county])

  const create = useMutation({
    mutationFn: (data: Parameters<typeof foiParcursApi.createCrmClient>[0]) =>
      foiParcursApi.createCrmClient(data),
  })

  const { full: phoneFull, valid: phoneValid } = composePhone(dialCode, phone)

  // Duplicate guard: debounce the local number, search CRM, and suggest existing
  // matches so the consilier reuses a client instead of creating a duplicate.
  const phoneDigits = phone.replace(/\D/g, '')
  const [dupTerm, setDupTerm] = useState('')
  useEffect(() => {
    const t = setTimeout(() => setDupTerm(phoneDigits.length >= 6 ? phoneDigits : ''), 400)
    return () => clearTimeout(t)
  }, [phoneDigits])
  const { data: dupData } = useQuery({
    queryKey: ['crm-client-dup-search', dupTerm],
    queryFn: () => foiParcursApi.searchCrmClients(dupTerm, 3),
    enabled: dupTerm.length >= 6,
    staleTime: 15_000,
  })
  const duplicates = (dupData?.clients ?? []).slice(0, 3)

  const emailValid = email.trim() === '' || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())
  const canCreate = name.trim() !== '' && phoneValid && emailValid && !create.isPending

  const handleCreate = () => {
    if (!canCreate) return
    setError(null)
    create.mutate(
      {
        display_name: name.trim(),
        phone: phoneFull,
        ...(email.trim() ? { email: email.trim() } : {}),
        ...(address.trim() ? { address: address.trim() } : {}),
        ...(city.trim() ? { city: city.trim() } : {}),
        ...(county.trim() ? { county: county.trim() } : {}),
        ...(country.trim() ? { country: country.trim() } : {}),
        ...(isCompany
          ? {
              is_company: true,
              ...(companyName.trim() ? { company_name: companyName.trim() } : {}),
              ...(cui.trim() ? { cui: cui.trim() } : {}),
            }
          : {}),
        // Persist the scanned/typed licence on the client (parity with mobile),
        // so it's reusable on that client's next drive. Company drives also keep
        // it on the contact person (created below); this is harmless there.
        ...(licenseNumber.trim() ? { driver_license_number: licenseNumber.trim() } : {}),
        ...(licenseExpiry.trim() ? { driver_license_expiry: licenseExpiry.trim() } : {}),
      },
      {
        onSuccess: async (res) => {
          if (!res.client) {
            setError('Clientul nu a putut fi creat.')
            return
          }
          if (isCompany) {
            try {
              await crmApi.createClientContact(Number(res.client.id), {
                full_name: name.trim(),
                email: email.trim() || null,
                phone: phoneFull || null,
                driver_license_number: licenseNumber.trim() || null,
                driver_license_expiry: licenseExpiry.trim() || null,
                is_primary: true,
              })
            } catch (err: any) {
              setError(err?.data?.error || err?.message || 'Persoana de contact nu a putut fi creată.')
              return
            }
          }
          onCreated(res.client, licenseNumber.trim(), licenseExpiry.trim(), licensePhoto)
        },
        onError: (err: any) => {
          setError(err?.data?.error || err?.message || 'Crearea clientului a eșuat.')
        },
      },
    )
  }

  return (
    <div className="space-y-2.5 rounded-md border bg-muted/40 p-3">
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Client nou</p>
      {/* Scan the driving licence → captures the photo, OCRs it, and prefills the
          fields below. The photo is returned on create to become the drive's
          licence photo too, so it's never captured twice. */}
      {licensePhoto ? (
        <div className="flex items-center gap-3">
          <img src={licensePhoto} alt="Permis de conducere" className="h-16 w-28 rounded-md object-cover border" />
          <Button type="button" variant="ghost" size="sm" className="text-destructive" onClick={() => setLicensePhoto(null)}>
            <X className="h-3.5 w-3.5 mr-1" /> Șterge poza
          </Button>
        </div>
      ) : (
        <label
          className={cn(
            'flex w-full cursor-pointer items-center justify-center gap-2 rounded-md border bg-secondary text-secondary-foreground hover:bg-secondary/80 h-9 px-3 text-sm font-medium transition-colors',
            (scanBusy || ocr.isPending) && 'opacity-60 pointer-events-none',
          )}
        >
          {scanBusy || ocr.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanLine className="h-4 w-4" />}
          {scanBusy ? 'Se procesează...' : ocr.isPending ? 'Se scanează...' : 'Scanează și preia din Permis'}
          <input type="file" accept="image/*" className="hidden" onChange={handleScanFile} />
        </label>
      )}
      <div className="flex items-center gap-2 pt-0.5">
        <Checkbox id="is-company" checked={isCompany} onCheckedChange={(v) => setIsCompany(v === true)} />
        <Label htmlFor="is-company" className="text-xs leading-normal cursor-pointer">Persoană juridică (firmă)</Label>
      </div>
      {isCompany && (
        <>
          <div className="space-y-1">
            <Label className="text-xs">Denumire firmă</Label>
            <Input value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="Denumire firmă" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">CUI</Label>
            <Input value={cui} onChange={(e) => setCui(e.target.value)} placeholder="CUI / CIF" />
          </div>
        </>
      )}
      <div className="space-y-1">
        <Label className="text-xs">Nume complet *</Label>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nume și prenume" />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Telefon *</Label>
        <div className="flex gap-2">
          <Select value={dialCode} onValueChange={setDialCode}>
            <SelectTrigger className="w-[132px] shrink-0"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectLabel>Europa</SelectLabel>
                {COUNTRY_DIAL_CODES.map((c) => (
                  <SelectItem key={c.code} value={c.code}>
                    <span className="mr-1.5">{c.flag}</span>
                    <span className="font-medium">{c.code}</span>
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
          <Input
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="0721 234 567"
            inputMode="tel"
            className={cn('flex-1', phone !== '' && !phoneValid && 'ring-2 ring-destructive')}
          />
        </div>
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Email</Label>
        <Input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="email@exemplu.ro"
          inputMode="email"
          autoCapitalize="none"
          className={cn(email.trim() !== '' && !emailValid && 'ring-2 ring-destructive')}
        />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Serie/nr permis</Label>
        <Input value={licenseNumber} onChange={(e) => setLicenseNumber(e.target.value)} placeholder="Serie/număr" />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Valabilitate permis (4b)</Label>
        <Input type="date" value={licenseExpiry} onChange={(e) => setLicenseExpiry(e.target.value)} />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Adresă</Label>
        <Input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="Strada, număr" />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Țară</Label>
        <Select value={country} onValueChange={setCountry}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            {COUNTRIES.map((c) => (
              <SelectItem key={c} value={c}>{c}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Județ</Label>
        <Autocomplete
          value={county}
          onChange={(v) => { setCounty(v); setCity('') }}
          onSelect={(v) => { setCounty(v); setCity('') }}
          options={RO_COUNTIES}
          placeholder="Caută județul..."
        />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Oraș</Label>
        <Autocomplete
          value={city}
          onChange={setCity}
          onSelect={(name) => {
            setCity(name)
            if (!county) {
              const found = RO_CITIES.find((c) => c.name === name)
              if (found) setCounty(found.county)
            }
          }}
          options={cityOptions}
          placeholder={county ? 'Caută orașul...' : 'Alege întâi județul (sau caută orașul)'}
        />
      </div>

      {duplicates.length > 0 && (
        <div className="space-y-1.5 rounded-md bg-amber-500/10 p-2.5">
          <p className="flex items-center gap-1.5 text-xs font-medium text-amber-700 dark:text-amber-400">
            <Users className="h-3.5 w-3.5" /> Există deja un client cu acest telefon:
          </p>
          {duplicates.map((c) => {
            const lic = reusableLicense(c)
            return (
              <button
                key={c.id}
                type="button"
                onClick={() => onCreated(c, lic.number, lic.expiry, licensePhoto)}
                className="w-full flex items-center justify-between gap-2 rounded-md border bg-background px-2.5 py-2 text-left hover:bg-accent transition-colors"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">{c.display_name || c.name || `Client #${c.id}`}</span>
                  {c.phone && <span className="block text-xs text-muted-foreground">{c.phone}</span>}
                </span>
                <span className="shrink-0 text-xs font-semibold text-primary">Folosește</span>
              </button>
            )
          })}
        </div>
      )}

      {error && <p className="text-xs text-destructive">{error}</p>}

      <div className="flex gap-2 pt-1">
        <Button type="button" variant="outline" className="flex-1" onClick={onCancel}>Anulează</Button>
        <Button type="button" className="flex-1" onClick={handleCreate} disabled={!canCreate}>
          {create.isPending ? 'Se creează...' : 'Creează client'}
        </Button>
      </div>
    </div>
  )
}
