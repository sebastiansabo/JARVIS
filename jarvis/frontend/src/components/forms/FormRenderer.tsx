import { useState, useRef, lazy, Suspense, useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Check, ChevronsUpDown, Search } from 'lucide-react'
import { cn } from '@/lib/utils'
import { crmApi } from '@/api/crm'
import { organizationApi } from '@/api/organization'
import { vouchersApi } from '@/api/vouchers'
import { foiParcursApi } from '@/api/foiParcurs'
import type { FormField } from '@/types/forms'
import type { ServiceCatalogCompanyItem } from '@/types/vouchers'

const SignatureCanvas = lazy(() => import('@/components/shared/SignatureCanvas'))

interface FormRendererProps {
  schema: FormField[]
  onSubmit: (answers: Record<string, unknown>) => void
  submitting?: boolean
  submitLabel?: string
  defaultValues?: Record<string, unknown>
}

// ── Duration link (config-driven, e.g. a start/end time pair → a duration) ──
// A field may declare `config.duration = { start, end }`: its value is the span
// between the two time fields, formatted time-wise ("2 h 30 min"). It is
// auto-computed and read-only — editing a time recomputes it. Times are
// "HH:MM" strings.
export type DurationLink = { hours: string; start: string; end: string }

function parseHM(v: unknown): number | null {
  if (typeof v !== 'string') return null
  const s = v.trim()
  let h: number, min: number
  const m = s.match(/^(\d{1,2}):(\d{1,2})$/)
  if (m) { h = +m[1]; min = +m[2] }
  else if (/^\d{1,2}$/.test(s)) { h = +s; min = 0 }  // bare hour, e.g. "9" → 09:00
  else return null
  if (h > 23 || min > 59) return null
  return h * 60 + min
}

// Format a whole-minute span time-wise, dropping a zero part:
// "50 min", "2 h", "2 h 30 min".
export function fmtDuration(mins: number): string {
  const total = Math.max(0, Math.round(mins))
  const h = Math.floor(total / 60), m = total % 60
  if (h && m) return `${h} h ${m} min`
  if (h) return `${h} h`
  return `${m} min`
}

// Apply every duration link touched by a change to `fieldId`, mutating `next`.
// The duration field is read-only: a valid start/end interval fills it; an
// invalid or still-incomplete one clears it (so the required check blocks submit).
export function applyDurationLinks(links: DurationLink[], next: Record<string, unknown>, fieldId: string): void {
  for (const link of links) {
    if (fieldId === link.start || fieldId === link.end) {
      const s = parseHM(next[link.start]), e = parseHM(next[link.end])
      next[link.hours] = s !== null && e !== null && e >= s ? fmtDuration(e - s) : ''
    }
  }
}

function isFieldVisible(field: FormField, answers: Record<string, unknown>): boolean {
  const rule = (field.config as Record<string, unknown> | undefined)?.showWhen as
    | { fieldId: string; operator: string; value: string }
    | undefined
  if (!rule || !rule.fieldId) return true
  const actual = answers[rule.fieldId]
  const actualStr = actual === undefined || actual === null ? '' : String(actual)
  switch (rule.operator) {
    case 'equals': return actualStr === rule.value
    case 'not_equals': return actualStr !== rule.value
    case 'contains': return actualStr.toLowerCase().includes((rule.value || '').toLowerCase())
    case 'is_not_empty': return actualStr !== ''
    case 'is_empty': return actualStr === ''
    default: return true
  }
}

export function FormRenderer({ schema, onSubmit, submitting, submitLabel = 'Submit', defaultValues }: FormRendererProps) {
  const [answers, setAnswers] = useState<Record<string, unknown>>(() => {
    const init: Record<string, unknown> = { ...(defaultValues || {}) }
    // Time fields with config.defaultNow prefill the current HH:MM.
    for (const f of schema) {
      if (f.type === 'time' && (f.config as Record<string, unknown> | undefined)?.defaultNow && !init[f.id]) {
        const d = new Date()
        init[f.id] = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
      }
    }
    return init
  })
  const [errors, setErrors] = useState<Record<string, string>>({})

  const durationLinks = useMemo<DurationLink[]>(() => {
    const out: DurationLink[] = []
    for (const f of schema) {
      const d = (f.config as Record<string, unknown> | undefined)?.duration as { start?: string; end?: string } | undefined
      if (d?.start && d?.end) out.push({ hours: f.id, start: d.start, end: d.end })
    }
    return out
  }, [schema])

  const setValue = (fieldId: string, value: unknown) => {
    setAnswers((prev) => {
      const next = { ...prev, [fieldId]: value }
      if (durationLinks.length) applyDurationLinks(durationLinks, next, fieldId)
      return next
    })
    if (errors[fieldId]) {
      setErrors((prev) => { const copy = { ...prev }; delete copy[fieldId]; return copy })
    }
  }

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {}
    for (const field of schema) {
      if (field.type === 'heading' || field.type === 'paragraph') continue
      if (!isFieldVisible(field, answers)) continue
      if (field.required) {
        const val = answers[field.id]
        if (val === undefined || val === null || val === '' || (Array.isArray(val) && val.length === 0)) {
          newErrors[field.id] = `${field.label || 'This field'} is required`
        }
      }
      // Email validation
      if (field.type === 'email' && answers[field.id]) {
        if (!String(answers[field.id]).includes('@')) {
          newErrors[field.id] = 'Please enter a valid email'
        }
      }
    }
    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (validate()) onSubmit(answers)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5 form-mobile-friendly">
      <style>{`
        .form-mobile-friendly input:not([type="checkbox"]):not([type="radio"]),
        .form-mobile-friendly textarea,
        .form-mobile-friendly [role="combobox"],
        .form-mobile-friendly select { min-height: 44px; font-size: 16px; }
        .form-mobile-friendly [role="radiogroup"] label { min-height: 44px; display: flex; align-items: center; }
        .form-mobile-friendly .space-y-1 { gap: 0.375rem; }
      `}</style>
      {schema.map((field) => {
        if (!isFieldVisible(field, answers)) return null
        return (
          <FieldComponent
            key={field.id}
            field={field}
            value={answers[field.id]}
            error={errors[field.id]}
            onChange={(val) => setValue(field.id, val)}
            onSetField={setValue}
            allAnswers={answers}
          />
        )
      })}
      <Button type="submit" className="w-full h-12 text-base font-semibold" disabled={submitting}>
        {submitting ? 'Submitting...' : submitLabel}
      </Button>
    </form>
  )
}

interface FieldProps {
  field: FormField
  value: unknown
  error?: string
  onChange: (value: unknown) => void
  onSetField?: (fieldId: string, value: unknown) => void
  allAnswers?: Record<string, unknown>
}

function CrmClientField({ field, value, error, onChange, onSetField }: FieldProps) {
  const [search, setSearch] = useState('')
  const [activeSearch, setActiveSearch] = useState('')
  const [showResults, setShowResults] = useState(false)

  const triggerSearch = () => { if (search.length >= 2) { setActiveSearch(search); setShowResults(true) } }

  // Search by name, CIF, phone (uses q= for elastic search across all fields)
  const { data: clientData } = useQuery({
    queryKey: ['crm-clients-search', activeSearch],
    queryFn: () => crmApi.getClients({ q: activeSearch, limit: '10' }),
    enabled: activeSearch.length >= 2,
    staleTime: 30_000,
  })

  // Search by VIN
  const isVinLike = /^[A-Z0-9]{5,17}$/i.test(activeSearch.trim())
  const { data: dealData } = useQuery({
    queryKey: ['crm-deals-vin', activeSearch],
    queryFn: () => crmApi.getDeals({ vin: activeSearch.trim(), limit: '10' }),
    enabled: isVinLike && activeSearch.length >= 5,
    staleTime: 30_000,
  })

  const clients = clientData?.clients ?? []
  const vinDeals = dealData?.deals ?? []
  const hasResults = clients.length > 0 || vinDeals.length > 0
  const selectedLabel = typeof value === 'string' && value ? value : ''

  const selectClient = (clientId: number, displayName: string, nr_reg?: string) => {
    onChange(displayName)
    setSearch('')
    setShowResults(false)
    if (onSetField) {
      onSetField('f_client_name', displayName)
      if (nr_reg) onSetField('f_client_cif', nr_reg)
      crmApi.getClient(clientId).then((detail) => {
        const profile = detail?.profile
        if (profile?.cui && onSetField) onSetField('f_client_cif', profile.cui)
        if (detail?.client?.email) onSetField('f_client_email', detail.client.email)
        const deals = detail?.deals ?? []
        if (deals.length > 0) {
          const deal = deals[0]
          if (deal.vin) onSetField('f_car_vin', deal.vin)
          if (deal.dossier_number) onSetField('f_contract_number', deal.dossier_number)
        }
      }).catch(() => {})
    }
  }

  return (
    <div className="space-y-1">
      <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
      <p className="text-xs text-muted-foreground">Search by client name, CIF, or VIN</p>
      <div className="relative">
        <div className="relative">
          <Input
            value={search || selectedLabel}
            onChange={(e) => { setSearch(e.target.value); if (!e.target.value) { onChange(''); setActiveSearch('') } }}
            onFocus={() => { if (selectedLabel) { setSearch(selectedLabel) } }}
            onBlur={() => setTimeout(() => setShowResults(false), 200)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); triggerSearch() } }}
            placeholder={field.placeholder || 'Search by name, CIF, or VIN...'}
            className="pr-10"
          />
          <button
            type="button"
            className="absolute right-0 top-0 h-full px-3 text-muted-foreground hover:text-foreground transition-colors"
            onClick={triggerSearch}
            tabIndex={-1}
          >
            <Search className="h-4 w-4" />
          </button>
        </div>
        {showResults && activeSearch.length >= 2 && hasResults && (
          <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-lg max-h-60 overflow-y-auto">
            {clients.length > 0 && (
              <>
                <div className="px-3 py-1 text-xs font-medium text-muted-foreground bg-muted/50">Clients</div>
                {clients.map((c) => (
                  <button
                    key={`c-${c.id}`}
                    type="button"
                    className="flex w-full flex-col px-3 py-2 text-left text-sm hover:bg-accent"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => selectClient(c.id, c.display_name, c.nr_reg)}
                  >
                    <span className="font-medium">{c.display_name}</span>
                    <span className="text-xs text-muted-foreground">
                      {[c.nr_reg && `CIF: ${c.nr_reg}`, c.client_type, c.city].filter(Boolean).join(' \u2022 ')}
                    </span>
                  </button>
                ))}
              </>
            )}
            {vinDeals.length > 0 && (
              <>
                <div className="px-3 py-1 text-xs font-medium text-muted-foreground bg-muted/50">VIN matches</div>
                {vinDeals.map((d) => (
                  <button
                    key={`d-${d.id}`}
                    type="button"
                    className="flex w-full flex-col px-3 py-2 text-left text-sm hover:bg-accent"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => {
                      onChange(d.client_display_name || '')
                      setSearch('')
                      setShowResults(false)
                      if (onSetField) {
                        if (d.client_display_name) onSetField('f_client_name', d.client_display_name)
                        if (d.vin) onSetField('f_car_vin', d.vin)
                        if (d.dossier_number) onSetField('f_contract_number', d.dossier_number)
                        if (d.client_id) {
                          crmApi.getClient(d.client_id).then((detail) => {
                            const profile = detail?.profile
                            if (profile?.cui) onSetField('f_client_cif', profile.cui)
                            if (detail?.client?.nr_reg) onSetField('f_client_cif', detail.client.nr_reg)
                          }).catch(() => {})
                        }
                      }
                    }}
                  >
                    <span className="font-medium">{d.client_display_name || 'Unknown client'}</span>
                    <span className="text-xs text-muted-foreground">
                      VIN: {d.vin} {d.brand && `\u2022 ${d.brand}`} {d.model_name && d.model_name}
                    </span>
                  </button>
                ))}
              </>
            )}
          </div>
        )}
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}

function CompanySelectField({ field, value, error, onChange, onSetField }: FieldProps) {
  const { data: companies = [] } = useQuery({
    queryKey: ['companies-config'],
    queryFn: () => organizationApi.getCompaniesConfig(),
    staleTime: 5 * 60_000,
  })
  return (
    <div className="space-y-1">
      <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
      <Select value={(value as string) ?? ''} onValueChange={(v) => { onChange(v); if (onSetField) onSetField('f_department', '') }}>
        <SelectTrigger><SelectValue placeholder="Select company..." /></SelectTrigger>
        <SelectContent>
          {companies.map((c: { id: number; company: string }) => (
            <SelectItem key={c.id} value={c.company}>{c.company}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}

function DepartmentSelectField({ field, value, error, onChange, allAnswers }: FieldProps) {
  const companyFieldId = (field.config as Record<string, unknown> | undefined)?.companyField as string || 'f_company'
  const companyName = (allAnswers?.[companyFieldId] as string) || ''

  const { data: departments = [] } = useQuery({
    queryKey: ['departments', companyName],
    queryFn: () => organizationApi.getDepartments(companyName),
    enabled: !!companyName,
    staleTime: 5 * 60_000,
  })

  return (
    <div className="space-y-1">
      <Label>{field.label}</Label>
      <Select value={(value as string) ?? ''} onValueChange={onChange}>
        <SelectTrigger><SelectValue placeholder={companyName ? 'Select department...' : 'Select company first'} /></SelectTrigger>
        <SelectContent>
          {departments.map((dept: string) => (
            <SelectItem key={dept} value={dept}>{dept}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}

function UserSelectField({ field, value, error, onChange }: FieldProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const { data: users = [] } = useQuery({
    queryKey: ['users-list'],
    queryFn: () => import('@/api/users').then((m) => m.usersApi.getUsers()),
    staleTime: 10 * 60_000,
  })

  const selectedId = (value as string) || ''
  const selectedUser = users.find((u: { id: number; name: string }) => String(u.id) === selectedId)
  const displayLabel = selectedUser ? selectedUser.name : 'Direct manager'

  const filtered = search.trim()
    ? users.filter((u: { id: number; name: string }) =>
        u.name.toLowerCase().includes(search.toLowerCase())
      )
    : users

  return (
    <div className="space-y-1">
      <Label>{field.label}</Label>
      <Popover open={open} onOpenChange={(v) => { setOpen(v); if (v) setTimeout(() => inputRef.current?.focus(), 0) }}>
        <PopoverTrigger asChild>
          <Button variant="outline" role="combobox" aria-expanded={open} className="w-full justify-between font-normal">
            {displayLabel}
            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
          <div className="p-2 border-b">
            <Input
              ref={inputRef}
              placeholder="Search user..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="h-8"
            />
          </div>
          <div className="max-h-60 overflow-y-auto p-1">
            <button
              type="button"
              className={cn(
                'flex w-full items-center rounded-sm px-2 py-1.5 text-sm hover:bg-accent cursor-pointer',
                !selectedId && 'bg-accent',
              )}
              onClick={() => { onChange(''); setOpen(false); setSearch('') }}
            >
              <Check className={cn('mr-2 h-4 w-4', selectedId ? 'opacity-0' : 'opacity-100')} />
              Direct manager
            </button>
            {filtered.map((u: { id: number; name: string }) => (
              <button
                type="button"
                key={u.id}
                className={cn(
                  'flex w-full items-center rounded-sm px-2 py-1.5 text-sm hover:bg-accent cursor-pointer',
                  selectedId === String(u.id) && 'bg-accent',
                )}
                onClick={() => { onChange(String(u.id)); setOpen(false); setSearch('') }}
              >
                <Check className={cn('mr-2 h-4 w-4', selectedId === String(u.id) ? 'opacity-100' : 'opacity-0')} />
                {u.name}
              </button>
            ))}
            {filtered.length === 0 && (
              <p className="py-4 text-center text-sm text-muted-foreground">No users found</p>
            )}
          </div>
        </PopoverContent>
      </Popover>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}

function ServiceCatalogField({ field, value, error, onChange }: FieldProps) {
  const { data: services = [] } = useQuery({
    queryKey: ['voucher-service-catalog-company'],
    queryFn: () => vouchersApi.getServiceCatalogCompany(),
    staleTime: 60_000,
  })

  // value is a JSON array of {id, name, price} objects
  const selected: { id: number; name: string; price: number }[] = Array.isArray(value) ? value : []
  const selectedIds = new Set(selected.map((s) => s.id))

  const toggle = (svc: ServiceCatalogCompanyItem, checked: boolean) => {
    if (checked) {
      onChange([...selected, { id: svc.id, name: svc.name, price: svc.price }])
    } else {
      onChange(selected.filter((s) => s.id !== svc.id))
    }
  }

  const total = selected.reduce((sum, s) => sum + s.price, 0)

  return (
    <div className="space-y-1">
      <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
      <div className="space-y-1">
        {services.map((svc) => (
          <div key={svc.id} className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Checkbox
                id={`${field.id}-svc-${svc.id}`}
                checked={selectedIds.has(svc.id)}
                onCheckedChange={(isChecked) => toggle(svc, !!isChecked)}
              />
              <Label htmlFor={`${field.id}-svc-${svc.id}`} className="font-normal">{svc.name}</Label>
            </div>
            <span className="text-sm text-muted-foreground">{svc.price} {svc.currency}</span>
          </div>
        ))}
      </div>
      {selected.length > 0 && (
        <div className="pt-2 border-t flex justify-between font-medium text-sm">
          <span>Total</span>
          <span>{total.toLocaleString('ro-RO')} LEI</span>
        </div>
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}

function FpVehicleField({ field, value, error, onChange, allAnswers }: FieldProps) {
  const companyFieldId = (field.config as Record<string, unknown> | undefined)?.companyField as string || 'f_company'
  const companyName = (allAnswers?.[companyFieldId] as string) || ''

  const { data: vehicleData } = useQuery({
    queryKey: ['fp-vehicles-active'],
    queryFn: () => foiParcursApi.getVehicles(true),
    staleTime: 60_000,
  })

  const allVehicles = vehicleData?.vehicles ?? []
  const filtered = companyName
    ? allVehicles.filter((v: { company_name?: string }) => v.company_name === companyName)
    : allVehicles

  const selectedId = value ? String(value) : ''
  const selectedVehicle = allVehicles.find((v: { id: number }) => String(v.id) === selectedId) as Record<string, unknown> | undefined

  const { data: inspectionData } = useQuery({
    queryKey: ['fp-inspection', selectedId],
    queryFn: () => foiParcursApi.getLatestInspection(Number(selectedId)),
    enabled: !!selectedId,
  })
  const latestInspection = inspectionData?.inspection ?? null

  return (
    <div className="space-y-2">
      <div className="space-y-1">
        <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
        <Select value={selectedId} onValueChange={onChange}>
          <SelectTrigger>
            <SelectValue placeholder={companyName ? 'Selectati vehiculul...' : 'Selectati compania intai'} />
          </SelectTrigger>
          <SelectContent>
            {filtered.map((v: { id: number; mark: string; model: string; vin: string; registration_number?: string }) => (
              <SelectItem key={v.id} value={String(v.id)}>
                {v.mark} {v.model} — {v.registration_number || v.vin}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>
      {selectedVehicle && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950/30 p-3 text-sm space-y-1">
          <p><span className="text-muted-foreground">VIN:</span> {String(selectedVehicle.vin)}</p>
          <p><span className="text-muted-foreground">Nr. inmatriculare:</span> {String(selectedVehicle.registration_number || '—')}</p>
          <p><span className="text-muted-foreground">Combustibil:</span> {String(selectedVehicle.fuel_type)} — {String(selectedVehicle.fuel_tank_capacity_liters)}L</p>
        </div>
      )}
      {latestInspection && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30 p-3 text-sm">
          <p className="font-medium text-xs text-amber-700 dark:text-amber-400">Ultima inspectie: {latestInspection.inspection_date}</p>
          {latestInspection.condition_notes && (
            <p className="text-muted-foreground mt-1">{latestInspection.condition_notes}</p>
          )}
        </div>
      )}
    </div>
  )
}

function FpClientField({ field, value, error, onChange }: FieldProps) {
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [showDropdown, setShowDropdown] = useState(false)
  const [selectedName, setSelectedName] = useState('')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [])

  const handleSearchChange = (val: string) => {
    setSearch(val)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setDebouncedSearch(val)
      if (val.length >= 2) setShowDropdown(true)
    }, 300)
  }

  const { data: clientData, isFetching } = useQuery({
    queryKey: ['fp-clients-search', debouncedSearch],
    queryFn: () => foiParcursApi.searchClients(debouncedSearch, 10),
    enabled: debouncedSearch.length >= 2 && !value,
    staleTime: 10_000,
  })
  const clients = clientData?.clients ?? []

  const clearSelection = () => {
    onChange('')
    setSelectedName('')
    setSearch('')
    setDebouncedSearch('')
  }

  return (
    <div className="space-y-1">
      <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
      {value && (selectedName || value) ? (
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center rounded-md border px-3 py-1.5 text-sm font-medium">
            {selectedName || `Client #${value}`}
          </span>
          <button type="button" className="text-xs text-muted-foreground hover:text-foreground" onClick={clearSelection}>
            Schimba
          </button>
        </div>
      ) : (
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder="Cauta dupa nume sau telefon..."
            value={search}
            onChange={(e) => handleSearchChange(e.target.value)}
            onFocus={() => { if (debouncedSearch.length >= 2) setShowDropdown(true) }}
          />
          {isFetching && (
            <div className="absolute right-2.5 top-2.5 h-4 w-4 border-2 border-muted-foreground border-t-transparent rounded-full animate-spin" />
          )}
          {showDropdown && debouncedSearch.length >= 2 && (
            <div className="absolute z-50 w-full mt-1 bg-popover border rounded-md shadow-md max-h-48 overflow-y-auto">
              {clients.length === 0 && !isFetching ? (
                <div className="p-3 text-sm text-muted-foreground text-center">Niciun client gasit</div>
              ) : (
                clients.map((c: { id: number; name: string; phone: string }) => (
                  <button
                    key={c.id}
                    type="button"
                    className="w-full text-left px-3 py-2 hover:bg-accent text-sm"
                    onClick={() => {
                      onChange(String(c.id))
                      setSelectedName(c.name)
                      setShowDropdown(false)
                      setSearch('')
                    }}
                  >
                    <span className="font-medium">{c.name}</span>
                    {c.phone && <span className="text-muted-foreground ml-2">{c.phone}</span>}
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}

function FieldComponent({ field, value, error, onChange, onSetField, allAnswers }: FieldProps) {
  const cfg = field.config as Record<string, unknown> | undefined
  // A duration-linked field (config.duration) is auto-computed from its start/end
  // times, so it renders read-only regardless of its declared type.
  if (cfg?.duration) {
    const hint = cfg.hint as string | undefined
    return (
      <div className="space-y-1">
        <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
        <Input
          type="text"
          value={(value as string) ?? ''}
          readOnly
          tabIndex={-1}
          placeholder={field.placeholder}
          className="bg-muted/50 text-muted-foreground cursor-default"
        />
        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>
    )
  }
  switch (field.type) {
    case 'heading':
      return <h2 className="text-lg font-bold pt-2">{field.label}</h2>

    case 'paragraph':
      return <p className="text-sm text-muted-foreground">{field.label}</p>

    case 'hidden':
      return null

    case 'crm_client':
      return <CrmClientField field={field} value={value} error={error} onChange={onChange} onSetField={onSetField} />

    case 'fp_vehicle':
      return <FpVehicleField field={field} value={value} error={error} onChange={onChange} allAnswers={allAnswers} />

    case 'fp_client':
      return <FpClientField field={field} value={value} error={error} onChange={onChange} />

    case 'short_text':
    case 'email':
    case 'phone': {
      const hint = (field.config as Record<string, unknown> | undefined)?.hint as string | undefined
      return (
        <div className="space-y-1">
          <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
          {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
          <Input
            type={field.type === 'email' ? 'email' : field.type === 'phone' ? 'tel' : 'text'}
            value={(value as string) ?? ''}
            onChange={(e) => onChange(e.target.value)}
            placeholder={field.placeholder}
          />
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      )
    }

    case 'number': {
      const hint = (field.config as Record<string, unknown> | undefined)?.hint as string | undefined
      return (
        <div className="space-y-1">
          <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
          {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
          <Input
            type="number"
            value={(value as string) ?? ''}
            onChange={(e) => onChange(e.target.value)}
            placeholder={field.placeholder}
          />
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      )
    }

    case 'long_text':
      return (
        <div className="space-y-1">
          <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
          <Textarea
            value={(value as string) ?? ''}
            onChange={(e) => onChange(e.target.value)}
            placeholder={field.placeholder}
            rows={3}
          />
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      )

    case 'date':
      return (
        <div className="space-y-1">
          <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
          <Input
            type="date"
            value={(value as string) ?? ''}
            onChange={(e) => onChange(e.target.value)}
          />
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      )

    case 'datetime':
      return (
        <div className="space-y-1">
          <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
          <Input
            type="datetime-local"
            value={(value as string) ?? ''}
            onChange={(e) => onChange(e.target.value)}
          />
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      )

    case 'time':
      return (
        <div className="space-y-1">
          <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
          <Input
            type="time"
            value={(value as string) ?? ''}
            onChange={(e) => onChange(e.target.value)}
          />
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      )

    case 'dropdown':
      return (
        <div className="space-y-1">
          <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
          <Select value={(value as string) ?? ''} onValueChange={onChange}>
            <SelectTrigger>
              <SelectValue placeholder={field.placeholder || 'Select...'} />
            </SelectTrigger>
            <SelectContent>
              {(field.options || []).map((opt) => (
                <SelectItem key={opt} value={opt}>{opt}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      )

    case 'radio':
      return (
        <div className="space-y-1">
          <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
          <RadioGroup value={(value as string) ?? ''} onValueChange={onChange}>
            {(field.options || []).map((opt) => (
              <div key={opt} className="flex items-center space-x-2">
                <RadioGroupItem value={opt} id={`${field.id}-${opt}`} />
                <Label htmlFor={`${field.id}-${opt}`} className="font-normal">{opt}</Label>
              </div>
            ))}
          </RadioGroup>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      )

    case 'checkbox':
      return (
        <div className="space-y-1">
          <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
          <div className="space-y-1">
            {(field.options || []).map((opt) => {
              const checked = Array.isArray(value) && value.includes(opt)
              return (
                <div key={opt} className="flex items-center space-x-2">
                  <Checkbox
                    id={`${field.id}-${opt}`}
                    checked={checked}
                    onCheckedChange={(isChecked) => {
                      const current = Array.isArray(value) ? [...value] : []
                      if (isChecked) {
                        current.push(opt)
                      } else {
                        const idx = current.indexOf(opt)
                        if (idx >= 0) current.splice(idx, 1)
                      }
                      onChange(current)
                    }}
                  />
                  <Label htmlFor={`${field.id}-${opt}`} className="font-normal">{opt}</Label>
                </div>
              )
            })}
          </div>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      )

    case 'file_upload':
      return (
        <div className="space-y-1">
          <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
          <Input
            type="file"
            onChange={(e) => {
              const file = e.target.files?.[0]
              onChange(file?.name ?? '')
            }}
          />
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      )

    case 'signature':
      return (
        <div className="space-y-1">
          <Label>{field.label}{field.required && <span className="text-destructive ml-0.5">*</span>}</Label>
          {value ? (
            <div className="space-y-2">
              <img src={value as string} alt="Signature" className="border rounded-lg max-h-24 bg-white" />
              <Button type="button" variant="outline" size="sm" onClick={() => onChange('')}>
                Clear & Re-sign
              </Button>
            </div>
          ) : (
            <Suspense fallback={<div className="h-[200px] border rounded-lg animate-pulse bg-muted" />}>
              <SignatureCanvas
                onSave={(base64) => onChange(base64)}
                onClear={() => onChange('')}
              />
            </Suspense>
          )}
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      )

    case 'service_catalog':
      return <ServiceCatalogField field={field} value={value} error={error} onChange={onChange} />

    case 'company_select':
      return <CompanySelectField field={field} value={value} error={error} onChange={onChange} onSetField={onSetField} />

    case 'department_select':
      return <DepartmentSelectField field={field} value={value} error={error} onChange={onChange} onSetField={onSetField} allAnswers={allAnswers} />

    case 'user_select':
      return <UserSelectField field={field} value={value} error={error} onChange={onChange} />

    default:
      return null
  }
}
