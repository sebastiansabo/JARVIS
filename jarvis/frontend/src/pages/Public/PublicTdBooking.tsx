import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'
import { tdApi, type TdSlot, type TdCar } from '@/api/td'
import { composePhone, COUNTRY_DIAL_CODES } from '@/pages/FoiParcurs/phoneFormat'
import { ApiError } from '@/api/client'
import { RichTextDisplay } from '@/components/shared/RichTextEditor'
import { sanitizeRichHtml, isEmptyRichHtml } from '@/lib/richText'
import { Toaster } from '@/components/ui/sonner'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'

// Day pills/captions read as "Vin 25 sep." and chips as clock times, so the
// picker never shows a long machine datetime.
const dayFmt = new Intl.DateTimeFormat('ro-RO', { weekday: 'short', day: '2-digit', month: 'short' })
const timeFmt = new Intl.DateTimeFormat('ro-RO', { hour: '2-digit', minute: '2-digit' })
// opens_at/closes_at are true instants → format in the viewer's local zone.
const regFmt = new Intl.DateTimeFormat('ro-RO', { day: '2-digit', month: 'long', hour: '2-digit', minute: '2-digit' })

const EMAIL_RE = /.+@.+\..+/

// Driving-licence photo: read client-side into a plain base64 data URL and
// ship it inline in the submit payload -- same no-object-storage pattern as
// the staff TestDriveForm (driver_license_photo TEXT column) and the event
// logo upload on TdBookingAdmin. This public route renders with no Layout
// (see App.tsx), so there's no ambient <Toaster/> to surface toast.error() --
// this page mounts its own below.
const MAX_PHOTO_BYTES = 2.5 * 1024 * 1024 // 2.5MB

// Fallback texts for the "Citește" consent popups when the tenant/page hasn't
// configured its own (page.gdpr_text / page.conditions_text). Kept short and
// in Romanian so a customer always has something sensible to read.
const DEFAULT_GDPR_TEXT =
  'Prin trimiterea acestei programări ești de acord ca datele tale personale ' +
  '(nume, telefon, email, seria și numărul permisului de conducere și, opțional, ' +
  'poza permisului) să fie prelucrate în scopul organizării și confirmării ' +
  'test drive-ului. Datele sunt folosite exclusiv pentru gestionarea programării ' +
  'și nu sunt transmise către terți fără acordul tău. Ai dreptul de acces, ' +
  'rectificare și ștergere a datelor, conform Regulamentului (UE) 2016/679 (GDPR). ' +
  'Pentru orice solicitare privind datele tale, contactează organizatorul evenimentului.'

const DEFAULT_CONDITIONS_TEXT =
  'Condiții de test drive:\n\n' +
  '1. Șoferul trebuie să dețină un permis de conducere valid, corespunzător ' +
  'categoriei vehiculului testat.\n' +
  '2. Șoferul este responsabil pentru vehicul pe toată durata test drive-ului ' +
  'și se obligă să respecte legislația rutieră în vigoare.\n' +
  '3. Test drive-ul se desfășoară pe un traseu stabilit împreună cu ' +
  'reprezentantul organizatorului și, de regulă, în prezența acestuia.\n' +
  '4. Este interzisă conducerea sub influența alcoolului, a substanțelor interzise ' +
  'sau a medicamentelor care afectează capacitatea de a conduce.\n' +
  '5. Orice daună produsă din culpa șoferului pe durata test drive-ului poate fi ' +
  'imputată acestuia, conform legii.\n' +
  '6. Organizatorul își rezervă dreptul de a întrerupe sau anula test drive-ul ' +
  'în cazul nerespectării acestor condiții.'

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('read failed'))
    reader.onload = () => resolve(reader.result as string)
    reader.readAsDataURL(file)
  })
}

/** Local-calendar-day key for a slot (year-month-date), used both to build the
 *  distinct-day list and to filter each car's slots to the selected day. */
function dayKeyOf(startsAt: string): string {
  const d = new Date(startsAt)
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
}

// A booking is ONE global ranked list: the 1st pick (any car) is the real
// booking (it holds the slot); the 2nd/3rd/4th are ranked preferences that
// reserve nothing and may be shifted by the team.
const MAX_PICKS = 4
const CHOICE_LABELS = ['Prima opțiune', 'A doua opțiune', 'A treia opțiune', 'A patra opțiune']

export default function PublicTdBooking() {
  const { slug } = useParams<{ slug: string }>()
  // Multi-select: an ORDERED list of chosen slot ids (across cars AND days).
  // Kept as ids (not slot objects) so it survives an availability refetch AND a
  // day switch cleanly -- picks made on one day stay selected while browsing
  // another day.
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  // The day currently shown in the car picker (null -> first available day).
  const [selectedDay, setSelectedDay] = useState<string | null>(null)
  // Accordion: which car's hour-slots are expanded (null = all collapsed). Keeps
  // a long multi-car list compact — tap a car to reveal its times.
  const [expandedCar, setExpandedCar] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [dialCode, setDialCode] = useState('+40')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [license, setLicense] = useState('')
  const [licensePhoto, setLicensePhoto] = useState<string | null>(null)
  const [photoBusy, setPhotoBusy] = useState(false)
  const [gdprConsent, setGdprConsent] = useState(false)
  const [conditionsAccepted, setConditionsAccepted] = useState(false)
  const [gdprOpen, setGdprOpen] = useState(false)
  const [conditionsOpen, setConditionsOpen] = useState(false)
  const [done, setDone] = useState(false)
  const [takenNote, setTakenNote] = useState('')
  // Waiting list (always available): preferred car + note; reuses the customer's
  // details entered above.
  const [waitlistCar, setWaitlistCar] = useState('')
  const [waitlistNote, setWaitlistNote] = useState('')
  const [waitlistDone, setWaitlistDone] = useState(false)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['td-page', slug],
    queryFn: () => tdApi.getPage(slug!),
    enabled: !!slug,
  })

  const { full: phoneFull, valid: phoneValid } = composePhone(dialCode, phone)
  const slotsByCar = useMemo(() => {
    const m: Record<number, TdSlot[]> = {}
    for (const s of data?.slots || []) (m[s.car_id] ||= []).push(s)
    return m
  }, [data])

  const carsById = useMemo(() => {
    const m: Record<number, TdCar> = {}
    for (const c of data?.cars || []) m[c.id] = c
    return m
  }, [data])

  const slotsById = useMemo(() => {
    const m: Record<number, TdSlot> = {}
    for (const s of data?.slots || []) m[s.id] = s
    return m
  }, [data])

  // Distinct days across ALL cars' slots, chronologically sorted. Slots arrive
  // ordered by (car_id, starts_at), so iteration order is NOT globally
  // chronological -- sort by the day's timestamp explicitly.
  const days = useMemo(() => {
    const seen: Record<string, { key: string; label: string; ts: number }> = {}
    for (const s of data?.slots || []) {
      const key = dayKeyOf(s.starts_at)
      if (!seen[key]) {
        const d = new Date(s.starts_at)
        const dayStart = new Date(d.getFullYear(), d.getMonth(), d.getDate())
        seen[key] = { key, label: dayFmt.format(d), ts: dayStart.getTime() }
      }
    }
    return Object.values(seen).sort((a, b) => a.ts - b.ts)
  }, [data])

  // Active day: honor the customer's pick when it's still available, else the
  // first day. Derived (no effect) so a background refetch can't strand it.
  const activeDay = (selectedDay && days.some((d) => d.key === selectedDay))
    ? selectedDay
    : (days[0]?.key ?? null)

  // Picks are kept in GLOBAL selection order: index 0 is the real booking
  // (reserved), the rest are ranked preferences. carPicks groups a car's picks
  // for its collapsed accordion badge (each pick's rank is its GLOBAL index).
  const carPicks = (carId: number) => selectedIds.filter((id) => slotsById[id]?.car_id === carId)
  const toggleSlot = (s: TdSlot) => setSelectedIds((prev) => {
    if (prev.includes(s.id)) return prev.filter((x) => x !== s.id)
    if (prev.length >= MAX_PICKS) return prev // 1 booking + up to 3 preferences
    return [...prev, s.id]
  })

  const slotSummary = (s: TdSlot) =>
    `${carsById[s.car_id]?.label ?? ''} · ${dayFmt.format(new Date(s.starts_at))}, ${timeFmt.format(new Date(s.starts_at))}`

  // Licence photo is OPTIONAL: it never gates the CTA (see detailsFilled
  // below), it only rejects an oversized/non-image file client-side.
  const handlePhotoFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (!file.type.startsWith('image/')) {
      toast.error('Fișierul trebuie să fie o imagine')
      return
    }
    if (file.size > MAX_PHOTO_BYTES) {
      toast.error('Poza este prea mare (max 2.5MB)')
      return
    }
    setPhotoBusy(true)
    try {
      setLicensePhoto(await readAsDataUrl(file))
    } catch {
      toast.error('Nu am putut citi fișierul')
    } finally {
      setPhotoBusy(false)
    }
  }

  const submit = useMutation({
    mutationFn: () => {
      // Global ranking: ONLY the 1st pick (selectedIds[0]) is an actual booking;
      // the rest ride along as ranked, human-readable preferences (reserve nothing).
      const primarySlotIds = selectedIds.length ? [selectedIds[0]] : []
      const carOf = (id: number) => data?.cars.find((c) => c.id === slotsById[id]?.car_id)
      const preferred = selectedIds.slice(1).map((id) => {
        const s = slotsById[id]
        const car = carOf(id)
        return {
          car: car?.label ?? '',
          plate: car?.plate ?? null,
          time: s ? `${dayFmt.format(new Date(s.starts_at))}, ${timeFmt.format(new Date(s.starts_at))}` : '',
        }
      }).filter((p) => p.time)
      return tdApi.submitBooking(slug!, {
        slot_ids: primarySlotIds,
        preferred,
        name: name.trim(),
        phone: phoneFull,
        email: email.trim(),
        license: license.trim(),
        license_photo: licensePhoto || null,
        gdpr_consent: gdprConsent,
        conditions_accepted: conditionsAccepted,
      })
    },
    onSuccess: (res) => {
      // Some slots may have been taken between load and submit — surface which.
      const taken = (res?.unavailable || [])
        .map((id) => slotsById[id] && slotSummary(slotsById[id]))
        .filter(Boolean) as string[]
      setTakenNote(taken.length
        ? `Aceste intervale tocmai fuseseră ocupate și nu au fost programate: ${taken.join('; ')}.`
        : '')
      setDone(true)
    },
    onError: (e) => {
      // Every requested slot was lost to other customers: refresh + clear picks.
      if (e instanceof ApiError && e.status === 409) { refetch(); setSelectedIds([]) }
    },
  })

  const waitlist = useMutation({
    mutationFn: () => tdApi.submitWaitlist(slug!, {
      name: name.trim(), phone: phoneFull, email: email.trim(), gdpr_consent: gdprConsent,
      preferred_car_vin: waitlistCar || null, note: waitlistNote.trim() || null,
    }),
    onSuccess: () => setWaitlistDone(true),
  })

  if (isLoading) return <BookingSkeleton />
  if (isError || !data) return <CenteredMessage title="Această pagină nu este disponibilă." />
  if (done) return (
    <ThankYouScreen
      logoUrl={data.page.logo_url}
      thankYouHtml={data.page.thank_you}
      note={takenNote}
    />
  )

  // Registration window (opens_at/closes_at are true instants — compare directly,
  // NOT via naiveDate). Outside the window the form is view-only.
  const nowMs = Date.now()
  const opensAtMs = data.page.opens_at ? new Date(data.page.opens_at).getTime() : null
  const closesAtMs = data.page.closes_at ? new Date(data.page.closes_at).getTime() : null
  const notOpenYet = opensAtMs !== null && nowMs < opensAtMs
  const closed = closesAtMs !== null && nowMs > closesAtMs
  const registrationOpen = !notOpenYet && !closed

  const requirePhoto = !!data.page.require_license_photo
  const detailsFilled = !!name.trim() && phoneValid && EMAIL_RE.test(email.trim())
    && !!license.trim() && gdprConsent && conditionsAccepted
    && (!requirePhoto || !!licensePhoto)
  const canSubmit = selectedIds.length > 0 && detailsFilled && registrationOpen && !submit.isPending
  const ctaHint = !registrationOpen
    ? (notOpenYet ? 'Programările nu sunt încă deschise' : 'Programările s-au închis')
    : !detailsFilled ? 'Completează câmpurile'
    : 'Alege cel puțin un interval'
  // The waiting list needs only contact + GDPR (no slot, no licence photo).
  const waitlistReady = !!name.trim() && phoneValid && EMAIL_RE.test(email.trim()) && gdprConsent

  return (
    <div className="min-h-screen bg-[#F6F7F9] text-[#0E1B2C] dark:bg-[#0B1522] dark:text-slate-100">
      {/* No Layout wraps this public route (see App.tsx), so there's no
          ambient <Toaster/> for the licence-photo upload's toast.error()
          calls -- mount one locally. */}
      <Toaster />
      {/* Full-width event banner — breaks out of the centered content column
          on purpose so the logo/title read as a proper event header, not a
          plain in-column title. */}
      <header className="w-full border-b border-slate-200 bg-white dark:border-slate-700/60 dark:bg-[#14243A]">
        <div className="mx-auto max-w-[640px] px-5 py-6 text-center sm:py-8">
          {data.page.logo_url && (
            <img
              src={data.page.logo_url}
              alt={data.page.title ? `Sigla ${data.page.title}` : 'Sigla evenimentului'}
              className="mx-auto mb-3 h-9 w-auto max-w-[180px] object-contain sm:h-12"
            />
          )}
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
            {data.page.title || 'Programează un test drive'}
          </h1>
          {data.page.company_name && (
            <p className="mt-1 text-sm font-medium text-[#2743E6] dark:text-[#8CA1FF]">{data.page.company_name}</p>
          )}
          {data.page.intro && (
            <p className="mx-auto mt-2.5 max-w-[520px] text-sm leading-relaxed text-slate-600 dark:text-slate-300">
              {data.page.intro}
            </p>
          )}
        </div>
      </header>

      <div className="mx-auto max-w-[520px] px-5 py-8 sm:py-12">
        {!registrationOpen && (
          <div className="mb-6 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-center text-sm
                          text-amber-800 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-300"
               role="status">
            {notOpenYet && opensAtMs !== null
              ? <>Programările se deschid pe <strong>{regFmt.format(new Date(opensAtMs))}</strong>.</>
              : 'Programările pentru acest eveniment s-au închis.'}
          </div>
        )}
        {/* 1) Details first — the customer fills their own data before picking. */}
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm
                            dark:border-slate-700/60 dark:bg-[#14243A]"
                 aria-label="Datele tale">
          <h2 className="mb-4 text-base font-semibold">Datele tale</h2>

          <div className="space-y-4">
            <Field id="td-name" label="Nume complet">
              <input
                id="td-name" value={name} onChange={(e) => setName(e.target.value)}
                autoComplete="name" placeholder="Ex: Andrei Popescu"
                className={inputCls}
              />
            </Field>

            <div>
              <label htmlFor="td-phone" className={labelCls}>Telefon</label>
              <div className="flex gap-2">
                <select
                  aria-label="Prefix telefonic"
                  value={dialCode} onChange={(e) => setDialCode(e.target.value)}
                  className="rounded-lg border border-slate-300 bg-white px-2 text-sm outline-none
                             focus-visible:border-[#2743E6] focus-visible:ring-2 focus-visible:ring-[#2743E6]/40
                             dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                >
                  {COUNTRY_DIAL_CODES.map((c) => (
                    <option key={c.code} value={c.code}>{c.flag} {c.code}</option>
                  ))}
                </select>
                <input
                  id="td-phone" type="tel" inputMode="tel" autoComplete="tel-national"
                  value={phone} onChange={(e) => setPhone(e.target.value)}
                  placeholder="0721 234 567"
                  className={inputCls + ' flex-1'}
                />
              </div>
            </div>

            <Field id="td-email" label="Email">
              <input
                id="td-email" type="email" inputMode="email" autoComplete="email"
                value={email} onChange={(e) => setEmail(e.target.value)}
                placeholder="nume@exemplu.ro"
                className={inputCls}
              />
            </Field>

            <Field id="td-license" label="Serie și număr permis">
              <input
                id="td-license" value={license} onChange={(e) => setLicense(e.target.value)}
                autoComplete="off" placeholder="Ex: AB 123456"
                className={inputCls}
              />
            </Field>

            {/* Licence photo — OPTIONAL, applies once to the whole booking
                group. Never required to submit (see detailsFilled/canSubmit
                below, which don't reference it). */}
            <div>
              <p className={labelCls}>Poză permis {requirePhoto ? '(obligatoriu)' : '(opțional)'}</p>
              {licensePhoto ? (
                <div className="flex items-center gap-3">
                  <img
                    src={licensePhoto}
                    alt="Poză permis"
                    className="h-16 w-28 rounded-lg border border-slate-200 object-cover dark:border-slate-600"
                  />
                  <button
                    type="button"
                    onClick={() => setLicensePhoto(null)}
                    className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600
                               outline-none hover:border-slate-400 focus-visible:ring-2 focus-visible:ring-[#2743E6]
                               dark:border-slate-600 dark:text-slate-300 dark:hover:border-slate-500"
                  >
                    Șterge
                  </button>
                </div>
              ) : (
                <label
                  className="flex h-11 w-full cursor-pointer items-center justify-center gap-2 rounded-lg
                             border border-dashed border-slate-300 text-sm text-slate-500 outline-none
                             hover:border-slate-400 focus-within:ring-2 focus-within:ring-[#2743E6]
                             dark:border-slate-600 dark:text-slate-400 dark:hover:border-slate-500"
                >
                  {photoBusy ? 'Se încarcă…' : 'Adaugă poza permisului'}
                  <input
                    type="file" accept="image/*" className="sr-only"
                    onChange={handlePhotoFile} disabled={photoBusy}
                    aria-label={requirePhoto ? 'Poză permis (obligatoriu)' : 'Poză permis (opțional)'}
                  />
                </label>
              )}
              <p className="mt-1.5 text-xs text-slate-400 dark:text-slate-500">
                {requirePhoto
                  ? 'Obligatorie pentru a trimite programarea.'
                  : 'Opțional — nu este necesară pentru a trimite programarea.'}
              </p>
            </div>
          </div>
        </section>

        {/* 2) Car + time picker — after the customer's details. */}
        <section className="mt-6" aria-label="Alege mașina și intervalul">
          <div className="mb-3">
            <h2 className="text-base font-semibold">Alege mașina și intervalul</h2>
            {days.length > 1 ? (
              // Multi-day: a horizontal row of day pills (wrap on a phone).
              <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Alege ziua">
                {days.map((day) => {
                  const active = day.key === activeDay
                  return (
                    <button
                      key={day.key}
                      type="button"
                      aria-pressed={active}
                      onClick={() => setSelectedDay(day.key)}
                      className={
                        'rounded-full px-3.5 py-1.5 text-sm font-medium capitalize outline-none ' +
                        'motion-safe:transition-colors focus-visible:ring-2 focus-visible:ring-[#2743E6] ' +
                        'focus-visible:ring-offset-2 dark:focus-visible:ring-offset-[#0B1522] ' +
                        (active
                          ? 'bg-[#2743E6] text-white'
                          : 'border border-slate-200 bg-white text-slate-700 hover:border-slate-300 ' +
                            'dark:border-slate-600 dark:bg-transparent dark:text-slate-200 dark:hover:border-slate-500')
                      }
                    >
                      {day.label}
                    </button>
                  )
                })}
              </div>
            ) : days.length === 1 ? (
              // Single day: a quiet caption, no picker.
              <p className="mt-1 text-sm capitalize text-slate-500 dark:text-slate-400">{days[0].label}</p>
            ) : null}
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              Prima oră aleasă (la orice mașină) este cea rezervată. Poți adăuga și alte
              ore preferate (a 2-a, a 3-a, a 4-a) — acestea sunt orientative și pot fi
              ajustate împreună cu echipa.
            </p>
          </div>

          <div className="space-y-4">
            {data.cars.filter((car) => (slotsByCar[car.id] || []).some((s) => dayKeyOf(s.starts_at) === activeDay)).map((car) => {
              const carSlots = (slotsByCar[car.id] || []).filter((s) => dayKeyOf(s.starts_at) === activeDay)
              const picks = carPicks(car.id) // this car's picks; rank = global index in selectedIds
              const expanded = expandedCar === car.id
              return (
                <article key={car.id}
                  className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm
                             dark:border-slate-700/60 dark:bg-[#14243A]">
                  <button
                    type="button"
                    onClick={() => setExpandedCar(expanded ? null : car.id)}
                    aria-expanded={expanded}
                    className="flex w-full items-center gap-2 p-4 text-left outline-none
                               focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#2743E6]"
                  >
                    <h3 className="text-base font-semibold">{car.label}</h3>
                    {car.plate && (
                      <span className="rounded-md border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-xs
                                       font-medium text-slate-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300">
                        {car.plate}
                      </span>
                    )}
                    {/* Collapsed: badge each of this car's picks with its GLOBAL
                        rank (1 = rezervat) so a picked car reads at a glance. */}
                    {!expanded && picks.length > 0 && (
                      <span className="ml-1 flex flex-wrap items-center gap-1">
                        {picks.map((id) => {
                          const s = slotsById[id]
                          if (!s) return null
                          const r = selectedIds.indexOf(id)
                          return (
                            <span key={id} className={
                              'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ' +
                              (r === 0 ? 'bg-[#2743E6] text-white'
                                       : 'bg-[#2743E6]/10 text-[#2743E6] dark:bg-[#2743E6]/25 dark:text-[#C9D4FF]')
                            }>
                              {r + 1} · {timeFmt.format(new Date(s.starts_at))}
                            </span>
                          )
                        })}
                      </span>
                    )}
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                      className={'ml-auto h-4 w-4 shrink-0 text-slate-400 motion-safe:transition-transform '
                        + (expanded ? 'rotate-180' : '')}>
                      <path d="m6 9 6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </button>

                  {expanded && (
                    <div className="flex flex-wrap gap-2 px-4 pb-4">
                    {carSlots.map((s) => {
                        const rank = selectedIds.indexOf(s.id) // GLOBAL: -1 unpicked, 0 rezervat, ≥1 preferință
                        const active = rank >= 0
                        const isPrimary = rank === 0
                        // Unpicked chips go quiet once the full ranked list is set
                        // (1 booking + up to 3 preferences).
                        const disabled = !active && selectedIds.length >= MAX_PICKS
                        return (
                          <button
                            key={s.id}
                            type="button"
                            aria-pressed={active}
                            disabled={disabled}
                            onClick={() => toggleSlot(s)}
                            className={
                              'inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-medium ' +
                              'outline-none motion-safe:transition-colors focus-visible:ring-2 ' +
                              'focus-visible:ring-[#2743E6] focus-visible:ring-offset-2 ' +
                              'dark:focus-visible:ring-offset-[#14243A] ' +
                              (isPrimary
                                ? 'bg-[#2743E6] text-white'
                                : active
                                  ? 'border border-[#2743E6]/40 bg-[#2743E6]/10 text-[#2743E6] ' +
                                    'dark:border-[#8CA1FF]/40 dark:bg-[#2743E6]/25 dark:text-[#C9D4FF]'
                                  : 'border border-slate-200 bg-white text-slate-700 hover:border-slate-300 ' +
                                    'disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-slate-200 ' +
                                    'dark:border-slate-600 dark:bg-transparent dark:text-slate-200 dark:hover:border-slate-500')
                            }
                          >
                            {active && (
                              <span className={
                                'grid h-4 w-4 place-items-center rounded-full text-[10px] font-bold ' +
                                (isPrimary ? 'bg-white/25 text-white' : 'bg-[#2743E6]/20 text-[#2743E6] dark:text-[#C9D4FF]')
                              }>
                                {rank + 1}
                              </span>
                            )}
                            {timeFmt.format(new Date(s.starts_at))}
                          </button>
                        )
                      })}
                    </div>
                  )}
                </article>
              )
            })}
            {data.cars.length === 0 && (
              <p className="text-sm text-slate-400 dark:text-slate-500">Momentan nu sunt mașini disponibile.</p>
            )}
            {data.cars.length > 0
              && !data.cars.some((car) => (slotsByCar[car.id] || []).some((s) => dayKeyOf(s.starts_at) === activeDay)) && (
              <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-5 text-center
                              dark:border-slate-600 dark:bg-[#14243A]">
                <p className="text-sm text-slate-600 dark:text-slate-300">
                  Momentan nu există intervale libere{days.length > 1 ? ' în această zi' : ''}.
                </p>
                {/* Waiting-list request CTA is wired here (see WaitlistPanel). */}
              </div>
            )}
          </div>
        </section>

        {/* 3) "Programările tale" summary + the CTA — at the very bottom. The
            summary lists every pick WITH its day + time so multi-day picks are
            unambiguous. */}
        <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm
                            dark:border-slate-700/60 dark:bg-[#14243A]"
                 aria-label="Programările tale">
          <h2 className="mb-3 text-base font-semibold">
            Programările tale
            {selectedIds.length > 0 && (
              <span className="ml-1 font-normal text-slate-400 dark:text-slate-500">
                ({selectedIds.length})
              </span>
            )}
          </h2>

          {selectedIds.length > 0 ? (
            <ul className="mb-4 space-y-2">
              {selectedIds.map((id, i) => {
                const s = slotsById[id]
                if (!s) return null
                const car = carsById[s.car_id]
                const isPrimary = i === 0
                return (
                  <li key={id}
                    className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-slate-200 p-3
                               text-sm dark:border-slate-700/60">
                    <span className={
                      'grid h-5 w-5 shrink-0 place-items-center rounded-full text-[11px] font-bold ' +
                      (isPrimary ? 'bg-[#2743E6] text-white' : 'bg-[#2743E6]/15 text-[#2743E6] dark:text-[#C9D4FF]')
                    }>
                      {i + 1}
                    </span>
                    <span className="font-medium">{CHOICE_LABELS[i] ?? `Opțiunea ${i + 1}`}</span>
                    <span className="text-slate-600 dark:text-slate-300">
                      {car?.label ?? ''}{car?.plate ? ` (${car.plate})` : ''}
                    </span>
                    <span className="text-slate-500 dark:text-slate-400">
                      {dayFmt.format(new Date(s.starts_at))}, {timeFmt.format(new Date(s.starts_at))}
                    </span>
                    <span className={
                      'ml-auto text-xs ' +
                      (isPrimary ? 'font-medium text-[#2743E6] dark:text-[#8CA1FF]' : 'text-slate-400 dark:text-slate-500')
                    }>
                      {isPrimary ? 'rezervat' : 'preferință'}
                    </span>
                    <button
                      type="button"
                      aria-label={`Elimină ${CHOICE_LABELS[i] ?? 'opțiunea'} — ${car?.label ?? ''}`}
                      onClick={() => toggleSlot(s)}
                      className="shrink-0 rounded-md px-1 text-lg leading-none text-slate-400 outline-none
                                 hover:text-[#2743E6] focus-visible:ring-2 focus-visible:ring-[#2743E6]
                                 dark:hover:text-white"
                    >
                      ×
                    </button>
                  </li>
                )
              })}
            </ul>
          ) : (
            <p className="mb-4 text-sm text-slate-400 dark:text-slate-500">
              Alege cel puțin o oră mai sus — prima aleasă (la orice mașină) este cea rezervată.
            </p>
          )}

          {/* Consents — the final gate before sending. "Citește" opens the full
              text in a popup; both boxes must be checked to enable the CTA. */}
          <div className="mb-4 space-y-3 border-t border-slate-100 pt-4 dark:border-slate-700/60">
            <label className="flex items-start gap-3 text-sm text-slate-700 dark:text-slate-200">
              <input
                type="checkbox" checked={gdprConsent}
                onChange={(e) => setGdprConsent(e.target.checked)}
                className="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-300 text-[#2743E6]
                           accent-[#2743E6] focus-visible:ring-2 focus-visible:ring-[#2743E6]"
              />
              <span>
                Sunt de acord cu prelucrarea datelor personale (GDPR)
                <button
                  type="button"
                  onClick={(e) => { e.preventDefault(); e.stopPropagation(); setGdprOpen(true) }}
                  className="ml-1 text-[#2743E6] underline underline-offset-2 outline-none
                             focus-visible:ring-2 focus-visible:ring-[#2743E6] rounded"
                >
                  Citește
                </button>
              </span>
            </label>

            <label className="flex items-start gap-3 text-sm text-slate-700 dark:text-slate-200">
              <input
                type="checkbox" checked={conditionsAccepted}
                onChange={(e) => setConditionsAccepted(e.target.checked)}
                className="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-300 text-[#2743E6]
                           accent-[#2743E6] focus-visible:ring-2 focus-visible:ring-[#2743E6]"
              />
              <span>
                Accept condițiile de test drive
                <button
                  type="button"
                  onClick={(e) => { e.preventDefault(); e.stopPropagation(); setConditionsOpen(true) }}
                  className="ml-1 text-[#2743E6] underline underline-offset-2 outline-none
                             focus-visible:ring-2 focus-visible:ring-[#2743E6] rounded"
                >
                  Citește
                </button>
              </span>
            </label>
          </div>

          {submit.isError && (
            <p role="alert" className="mb-3 text-sm text-red-600 dark:text-red-400">{errText(submit.error)}</p>
          )}

          <button
            type="button"
            disabled={!canSubmit}
            onClick={() => submit.mutate()}
            className="w-full rounded-xl bg-[#2743E6] py-3 text-sm font-semibold text-white outline-none
                       motion-safe:transition-opacity hover:bg-[#2743E6]/92
                       focus-visible:ring-2 focus-visible:ring-[#2743E6] focus-visible:ring-offset-2
                       disabled:cursor-not-allowed disabled:opacity-40
                       dark:focus-visible:ring-offset-[#14243A]"
          >
            {submit.isPending ? 'Se trimite…' : 'Trimite programările'}
          </button>
          {!canSubmit && !submit.isPending && (
            <p className="mt-2 text-center text-xs text-slate-400 dark:text-slate-500">{ctaHint}</p>
          )}
        </section>

        {/* Waiting list — always available, for people who can't find a slot or
            want a different time/car. Reuses the details entered above. */}
        <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm
                            dark:border-slate-700/60 dark:bg-[#14243A]"
                 aria-label="Listă de așteptare">
          {waitlistDone ? (
            <p className="text-sm text-slate-600 dark:text-slate-300">
              ✅ Ești pe lista de așteptare. Te contactăm dacă se eliberează un loc potrivit.
            </p>
          ) : (
            <>
              <h2 className="text-base font-semibold">Nu găsești un interval potrivit?</h2>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                Înscrie-te pe lista de așteptare și te contactăm dacă apare o oră liberă.
              </p>
              <div className="mt-3 space-y-3">
                <Field id="wl-car" label="Mașina preferată (opțional)">
                  <select id="wl-car" value={waitlistCar} onChange={(e) => setWaitlistCar(e.target.value)} className={inputCls}>
                    <option value="">Orice mașină</option>
                    {data.cars.map((c) => (
                      <option key={c.id} value={c.vin}>{c.label}{c.plate ? ` (${c.plate})` : ''}</option>
                    ))}
                  </select>
                </Field>
                <Field id="wl-note" label="Mesaj (opțional)">
                  <textarea
                    id="wl-note" rows={2} value={waitlistNote} onChange={(e) => setWaitlistNote(e.target.value)}
                    placeholder="Ex: prefer după-amiaza"
                    className={inputCls}
                  />
                </Field>
                {waitlist.isError && (
                  <p role="alert" className="text-sm text-red-600 dark:text-red-400">
                    Nu am putut trimite cererea. Verifică datele și încearcă din nou.
                  </p>
                )}
                <button
                  type="button"
                  disabled={!waitlistReady || waitlist.isPending}
                  onClick={() => waitlist.mutate()}
                  className="w-full rounded-xl border border-[#2743E6] py-2.5 text-sm font-semibold text-[#2743E6]
                             outline-none motion-safe:transition-colors hover:bg-[#2743E6]/5
                             focus-visible:ring-2 focus-visible:ring-[#2743E6] focus-visible:ring-offset-2
                             disabled:cursor-not-allowed disabled:opacity-40
                             dark:text-[#8CA1FF] dark:focus-visible:ring-offset-[#14243A]"
                >
                  {waitlist.isPending ? 'Se trimite…' : 'Înscrie-mă pe lista de așteptare'}
                </button>
                {!waitlistReady && (
                  <p className="text-center text-xs text-slate-400 dark:text-slate-500">
                    Completează numele, telefonul, emailul și bifează acordul GDPR de mai sus.
                  </p>
                )}
              </div>
            </>
          )}
        </section>
      </div>

      {/* Consent "Citește" popups — full text, scrollable; fall back to a
          sensible built-in default when the tenant/page hasn't set its own. */}
      <ReadDialog
        open={gdprOpen}
        onOpenChange={setGdprOpen}
        title="Prelucrarea datelor personale (GDPR)"
        text={data.page.gdpr_text || DEFAULT_GDPR_TEXT}
      />
      <ReadDialog
        open={conditionsOpen}
        onOpenChange={setConditionsOpen}
        title="Condiții de test drive"
        text={data.page.conditions_text || DEFAULT_CONDITIONS_TEXT}
      />
    </div>
  )
}

const labelCls = 'mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-200'
const inputCls =
  'w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-[#0E1B2C] outline-none ' +
  'placeholder:text-slate-400 focus-visible:border-[#2743E6] focus-visible:ring-2 focus-visible:ring-[#2743E6]/40 ' +
  'dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500'

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className={labelCls}>{label}</label>
      {children}
    </div>
  )
}

/** A read-only popup for a consent's full text (GDPR / conditions). Reuses the
 *  app Dialog; the text scrolls inside the dialog on long content. */
function ReadDialog({ open, onOpenChange, title, text }: {
  open: boolean
  onOpenChange: (o: boolean) => void
  title: string
  text: string
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader><DialogTitle>{title}</DialogTitle></DialogHeader>
        <div className="max-h-[60vh] overflow-y-auto whitespace-pre-line text-sm leading-relaxed
                        text-slate-600 dark:text-slate-300">
          {text}
        </div>
      </DialogContent>
    </Dialog>
  )
}

function BookingSkeleton() {
  return (
    <div className="min-h-screen bg-[#F6F7F9] dark:bg-[#0B1522]">
      <div className="w-full border-b border-slate-200 bg-white dark:border-slate-700/60 dark:bg-[#14243A]">
        <div className="mx-auto max-w-[640px] px-5 py-6 text-center sm:py-8">
          <div className="mx-auto space-y-3 motion-safe:animate-pulse">
            <div className="mx-auto h-8 w-2/3 rounded-lg bg-slate-200 dark:bg-slate-700" />
            <div className="mx-auto h-4 w-1/3 rounded bg-slate-200 dark:bg-slate-700" />
          </div>
        </div>
      </div>
      <div className="mx-auto max-w-[520px] px-5 py-8 sm:py-12">
        <div className="space-y-4 motion-safe:animate-pulse">
          {[0, 1].map((i) => (
            <div key={i} className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-700/60 dark:bg-[#14243A]">
              <div className="mb-3 h-5 w-1/2 rounded bg-slate-200 dark:bg-slate-700" />
              <div className="flex flex-wrap gap-2">
                {[0, 1, 2, 3].map((j) => (
                  <div key={j} className="h-8 w-16 rounded-full bg-slate-200 dark:bg-slate-700" />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

/** Post-submit "done" screen: the event logo, the "check your email" heading,
 *  the page's staff-authored rich-text thank-you (or a sensible default), and an
 *  optional note about slots taken between load and submit. */
function ThankYouScreen({ logoUrl, thankYouHtml, note }: {
  logoUrl?: string | null
  thankYouHtml?: string
  note?: string
}) {
  const hasThankYou = !isEmptyRichHtml(thankYouHtml)
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#F6F7F9] p-6 text-center
                    text-[#0E1B2C] dark:bg-[#0B1522] dark:text-slate-100">
      <div className="max-w-[440px]">
        {logoUrl && (
          <img
            src={logoUrl}
            alt="Sigla evenimentului"
            className="mx-auto mb-6 h-11 w-auto max-w-[190px] object-contain"
          />
        )}
        <h1 className="text-2xl font-semibold tracking-tight">Verifică emailul</h1>
        {hasThankYou ? (
          <RichTextDisplay
            content={sanitizeRichHtml(thankYouHtml!)}
            className="mt-3 text-slate-600 dark:text-slate-300 [&_a]:text-[#2743E6] [&_a]:underline"
          />
        ) : (
          <p className="mt-2 text-[15px] leading-relaxed text-slate-500 dark:text-slate-400">
            Confirmă toate programările dintr-un singur link — ți l-am trimis pe email.
          </p>
        )}
        {note && (
          <p className="mt-4 rounded-lg bg-amber-50 px-3 py-2 text-sm leading-relaxed text-amber-700
                        dark:bg-amber-500/10 dark:text-amber-300">{note}</p>
        )}
      </div>
    </div>
  )
}

function CenteredMessage({ title, body, note }: { title: string; body?: string; note?: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#F6F7F9] p-6 text-center
                    text-[#0E1B2C] dark:bg-[#0B1522] dark:text-slate-100">
      <div className="max-w-[420px]">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {body && <p className="mt-2 text-[15px] leading-relaxed text-slate-500 dark:text-slate-400">{body}</p>}
        {note && (
          <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm leading-relaxed text-amber-700
                        dark:bg-amber-500/10 dark:text-amber-300">{note}</p>
        )}
      </div>
    </div>
  )
}

function errText(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 409) return 'Intervalele alese tocmai au fost ocupate. Alege altele.'
    if (e.status === 410) return 'Linkul a expirat. Reîncarcă pagina și încearcă din nou.'
    if (e.status === 429) return 'Ai atins limita de programări. Încearcă mai târziu.'
    if (e.status === 403) return 'Programările sunt închise momentan.'
    if (e.status === 422) {
      const msg = (e.data as { error?: string } | null)?.error
      return msg || 'Verifică datele introduse și încearcă din nou.'
    }
  }
  return 'A apărut o eroare. Încearcă din nou.'
}
