import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { tdApi, type TdSlot, type TdCar } from '@/api/td'
import { composePhone, COUNTRY_DIAL_CODES } from '@/pages/FoiParcurs/phoneFormat'
import { ApiError } from '@/api/client'

// Day headers read as "mie., 01 oct." and chips as clock times, so the picker
// never shows a long machine datetime.
const dayFmt = new Intl.DateTimeFormat('ro-RO', { weekday: 'short', day: '2-digit', month: 'short' })
const timeFmt = new Intl.DateTimeFormat('ro-RO', { hour: '2-digit', minute: '2-digit' })

const EMAIL_RE = /.+@.+\..+/

/** Group a car's slots into ordered day buckets (slots already arrive
 *  time-sorted from the API), keyed by local calendar day. */
function groupByDay(slots: TdSlot[]): { key: string; label: string; slots: TdSlot[] }[] {
  const order: string[] = []
  const buckets: Record<string, { label: string; slots: TdSlot[] }> = {}
  for (const s of slots) {
    const d = new Date(s.starts_at)
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
    if (!buckets[key]) {
      buckets[key] = { label: dayFmt.format(d), slots: [] }
      order.push(key)
    }
    buckets[key].slots.push(s)
  }
  return order.map((key) => ({ key, ...buckets[key] }))
}

// A customer can pick up to this many (car+interval) slots in one group; beyond
// it, the unpicked chips go quiet and a gentle hint appears.
const MAX_SLOTS = 5

export default function PublicTdBooking() {
  const { slug } = useParams<{ slug: string }>()
  // Multi-select: an ORDERED list of chosen slot ids (across cars). Kept as ids
  // (not slot objects) so it survives an availability refetch cleanly.
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [name, setName] = useState('')
  const [dialCode, setDialCode] = useState('+40')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [license, setLicense] = useState('')
  const [gdprConsent, setGdprConsent] = useState(false)
  const [conditionsAccepted, setConditionsAccepted] = useState(false)
  const [gdprOpen, setGdprOpen] = useState(false)
  const [done, setDone] = useState(false)
  const [takenNote, setTakenNote] = useState('')

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

  const atCap = selectedIds.length >= MAX_SLOTS
  const toggleSlot = (s: TdSlot) => setSelectedIds((prev) =>
    prev.includes(s.id) ? prev.filter((x) => x !== s.id)
      : prev.length >= MAX_SLOTS ? prev : [...prev, s.id])

  const slotSummary = (s: TdSlot) =>
    `${carsById[s.car_id]?.label ?? ''} · ${dayFmt.format(new Date(s.starts_at))}, ${timeFmt.format(new Date(s.starts_at))}`

  const submit = useMutation({
    mutationFn: () => tdApi.submitBooking(slug!, {
      slot_ids: selectedIds,
      name: name.trim(),
      phone: phoneFull,
      email: email.trim(),
      license: license.trim(),
      gdpr_consent: gdprConsent,
      conditions_accepted: conditionsAccepted,
    }),
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

  if (isLoading) return <BookingSkeleton />
  if (isError || !data) return <CenteredMessage title="Această pagină nu este disponibilă." />
  if (done) return <CenteredMessage
    title="Verifică emailul"
    body={data.page.thank_you || 'Confirmă toate programările dintr-un singur link — ți l-am trimis pe email.'}
    note={takenNote} />

  const selectedSlots = selectedIds.map((id) => slotsById[id]).filter(Boolean) as TdSlot[]
  const detailsFilled = !!name.trim() && phoneValid && EMAIL_RE.test(email.trim())
    && !!license.trim() && gdprConsent && conditionsAccepted
  const canSubmit = selectedIds.length > 0 && detailsFilled && !submit.isPending
  const ctaHint = selectedIds.length === 0 ? 'Alege cel puțin un interval' : 'Completează câmpurile'

  return (
    <div className="min-h-screen bg-[#F6F7F9] text-[#0E1B2C] dark:bg-[#0B1522] dark:text-slate-100">
      {/* Full-width event banner — breaks out of the centered content column
          on purpose so the logo/title read as a proper event header, not a
          plain in-column title. */}
      <header className="w-full border-b border-slate-200 bg-white dark:border-slate-700/60 dark:bg-[#14243A]">
        <div className="mx-auto max-w-[640px] px-5 py-10 text-center sm:py-14">
          {data.page.logo_url && (
            <img
              src={data.page.logo_url}
              alt={data.page.title ? `Sigla ${data.page.title}` : 'Sigla evenimentului'}
              className="mx-auto mb-5 h-12 w-auto max-w-[220px] object-contain sm:h-[72px]"
            />
          )}
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            {data.page.title || 'Programează un test drive'}
          </h1>
          {data.page.company_name && (
            <p className="mt-2 text-sm font-medium text-[#2743E6] dark:text-[#8CA1FF]">{data.page.company_name}</p>
          )}
          {data.page.intro && (
            <p className="mx-auto mt-4 max-w-[520px] text-[15px] leading-relaxed text-slate-600 dark:text-slate-300">
              {data.page.intro}
            </p>
          )}
        </div>
      </header>

      <div className="mx-auto max-w-[520px] px-5 py-8 sm:py-12">
        {/* Car + time picker — the hero */}
        <section className="space-y-4" aria-label="Alege mașina și intervalul">
          {data.cars.map((car) => {
            const days = groupByDay(slotsByCar[car.id] || [])
            return (
              <article key={car.id}
                className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm
                           dark:border-slate-700/60 dark:bg-[#14243A]">
                <div className="mb-3 flex items-center gap-2">
                  <h2 className="text-base font-semibold">{car.label}</h2>
                  {car.plate && (
                    <span className="rounded-md border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-xs
                                     font-medium text-slate-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300">
                      {car.plate}
                    </span>
                  )}
                </div>

                {days.length === 0 ? (
                  <p className="text-sm text-slate-400 dark:text-slate-500">Niciun interval liber</p>
                ) : (
                  <div className="space-y-3">
                    {days.map((day) => (
                      <div key={day.key}>
                        <p className="mb-1.5 text-xs font-medium text-slate-500 dark:text-slate-400">{day.label}</p>
                        <div className="flex flex-wrap gap-2">
                          {day.slots.map((s) => {
                            const active = selectedIds.includes(s.id)
                            // At the cap, unpicked chips go quiet (but stay
                            // visible); picked ones can always be toggled off.
                            const capped = !active && atCap
                            return (
                              <button
                                key={s.id}
                                type="button"
                                aria-pressed={active}
                                disabled={capped}
                                onClick={() => toggleSlot(s)}
                                className={
                                  'rounded-full px-3.5 py-1.5 text-sm font-medium outline-none ' +
                                  'motion-safe:transition-colors focus-visible:ring-2 focus-visible:ring-[#2743E6] ' +
                                  'focus-visible:ring-offset-2 dark:focus-visible:ring-offset-[#14243A] ' +
                                  (active
                                    ? 'bg-[#2743E6] text-white'
                                    : 'border border-slate-200 bg-white text-slate-700 hover:border-slate-300 ' +
                                      'disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-slate-200 ' +
                                      'dark:border-slate-600 dark:bg-transparent dark:text-slate-200 dark:hover:border-slate-500')
                                }
                              >
                                {timeFmt.format(new Date(s.starts_at))}
                              </button>
                            )
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </article>
            )
          })}
          {data.cars.length === 0 && (
            <p className="text-sm text-slate-400 dark:text-slate-500">Momentan nu sunt mașini disponibile.</p>
          )}
          {atCap && (
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Poți alege până la {MAX_SLOTS} intervale. Deselectează unul ca să adaugi altul.
            </p>
          )}
        </section>

        {/* "Programările tale" — a compact, editable summary of every chosen
            (car+interval) so it's clear what will be booked as one group. */}
        {selectedSlots.length > 0 && (
          <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm
                              dark:border-slate-700/60 dark:bg-[#14243A]"
                   aria-label="Programările tale">
            <h2 className="mb-3 text-base font-semibold">
              Programările tale
              <span className="ml-1 font-normal text-slate-400 dark:text-slate-500">
                ({selectedSlots.length})
              </span>
            </h2>
            <ul className="space-y-2">
              {selectedSlots.map((s) => (
                <li key={s.id}
                    className="flex items-center justify-between gap-3 rounded-lg bg-[#2743E6]/8 px-3 py-2
                               text-sm text-[#2743E6] dark:bg-[#2743E6]/15 dark:text-slate-100">
                  <span>{slotSummary(s)}</span>
                  <button
                    type="button"
                    aria-label={`Elimină ${slotSummary(s)}`}
                    onClick={() => toggleSlot(s)}
                    className="shrink-0 rounded-md px-1.5 text-lg leading-none text-[#2743E6]/70 outline-none
                               hover:text-[#2743E6] focus-visible:ring-2 focus-visible:ring-[#2743E6]
                               dark:text-slate-300 dark:hover:text-white"
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Details panel */}
        <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm
                            dark:border-slate-700/60 dark:bg-[#14243A]">
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

            {/* Consent rows */}
            <div className="space-y-3 pt-1">
              <label className="flex items-start gap-3 text-sm text-slate-700 dark:text-slate-200">
                <input
                  type="checkbox" checked={gdprConsent}
                  onChange={(e) => setGdprConsent(e.target.checked)}
                  className="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-300 text-[#2743E6]
                             accent-[#2743E6] focus-visible:ring-2 focus-visible:ring-[#2743E6]"
                />
                <span>
                  Sunt de acord cu prelucrarea datelor personale (GDPR)
                  {data.page.gdpr_text && (
                    <button
                      type="button"
                      aria-expanded={gdprOpen}
                      onClick={(e) => { e.preventDefault(); setGdprOpen((v) => !v) }}
                      className="ml-1 text-[#2743E6] underline underline-offset-2 outline-none
                                 focus-visible:ring-2 focus-visible:ring-[#2743E6] rounded"
                    >
                      {gdprOpen ? 'Ascunde' : 'Detalii'}
                    </button>
                  )}
                </span>
              </label>
              {data.page.gdpr_text && gdprOpen && (
                <p className="whitespace-pre-line rounded-lg bg-slate-50 p-3 text-xs leading-relaxed
                              text-slate-500 dark:bg-slate-800/60 dark:text-slate-300">
                  {data.page.gdpr_text}
                </p>
              )}

              <label className="flex items-start gap-3 text-sm text-slate-700 dark:text-slate-200">
                <input
                  type="checkbox" checked={conditionsAccepted}
                  onChange={(e) => setConditionsAccepted(e.target.checked)}
                  className="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-300 text-[#2743E6]
                             accent-[#2743E6] focus-visible:ring-2 focus-visible:ring-[#2743E6]"
                />
                <span>Accept condițiile de test drive</span>
              </label>
            </div>

            {submit.isError && (
              <p role="alert" className="text-sm text-red-600 dark:text-red-400">{errText(submit.error)}</p>
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
              <p className="text-center text-xs text-slate-400 dark:text-slate-500">{ctaHint}</p>
            )}
          </div>
        </section>
      </div>
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

function BookingSkeleton() {
  return (
    <div className="min-h-screen bg-[#F6F7F9] dark:bg-[#0B1522]">
      <div className="w-full border-b border-slate-200 bg-white dark:border-slate-700/60 dark:bg-[#14243A]">
        <div className="mx-auto max-w-[640px] px-5 py-10 text-center sm:py-14">
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
