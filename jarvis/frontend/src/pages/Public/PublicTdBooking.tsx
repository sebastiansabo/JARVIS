import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { tdApi, type TdSlot } from '@/api/td'
import { composePhone, COUNTRY_DIAL_CODES } from '@/pages/FoiParcurs/phoneFormat'
import { ApiError } from '@/api/client'

export default function PublicTdBooking() {
  const { slug } = useParams<{ slug: string }>()
  const [selected, setSelected] = useState<TdSlot | null>(null)
  const [name, setName] = useState('')
  const [dialCode, setDialCode] = useState('+40')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [done, setDone] = useState(false)

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

  const submit = useMutation({
    mutationFn: () => tdApi.submitBooking(slug!, {
      slot_id: selected!.id, name, phone: phoneFull, email,
    }),
    onSuccess: () => setDone(true),
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409) { refetch(); setSelected(null) }
    },
  })

  if (isLoading) return <CenteredMessage title="Se încarcă…" />
  if (isError || !data) return <CenteredMessage title="Pagina nu este disponibilă" />
  if (done) return <CenteredMessage title="Verifică emailul"
    body={data.page.thank_you || 'Ți-am trimis un link de confirmare pe email.'} />

  const canSubmit = !!selected && name.trim() && phoneValid && /.+@.+\..+/.test(email) && !submit.isPending

  return (
    <div className="min-h-screen bg-gray-50 p-4">
      <div className="max-w-2xl mx-auto space-y-6">
        <header>
          <h1 className="text-2xl font-bold">{data.page.title || 'Programează un test drive'}</h1>
          {data.page.intro && <p className="text-muted-foreground">{data.page.intro}</p>}
        </header>

        {data.cars.map(car => (
          <section key={car.id} className="rounded-lg border bg-white p-4">
            <h2 className="font-semibold mb-2">{car.vin}</h2>
            <div className="flex flex-wrap gap-2">
              {(slotsByCar[car.id] || []).map(s => (
                <button key={s.id}
                  onClick={() => setSelected(s)}
                  className={`px-3 py-1 rounded border text-sm ${selected?.id === s.id ? 'bg-black text-white' : 'bg-white'}`}>
                  {new Date(s.starts_at).toLocaleString('ro-RO', { dateStyle: 'short', timeStyle: 'short' })}
                </button>
              ))}
              {!(slotsByCar[car.id] || []).length && <span className="text-sm text-muted-foreground">Niciun interval liber</span>}
            </div>
          </section>
        ))}

        <section className="rounded-lg border bg-white p-4 space-y-3">
          <input className="w-full border rounded px-3 py-2" placeholder="Nume complet"
                 value={name} onChange={e => setName(e.target.value)} />
          <div className="flex gap-2">
            <select className="border rounded px-2" value={dialCode} onChange={e => setDialCode(e.target.value)}>
              {COUNTRY_DIAL_CODES.map(c => <option key={c.code} value={c.code}>{c.flag} {c.code}</option>)}
            </select>
            <input className="flex-1 border rounded px-3 py-2" placeholder="Telefon"
                   value={phone} onChange={e => setPhone(e.target.value)} />
          </div>
          <input className="w-full border rounded px-3 py-2" placeholder="Email" type="email"
                 value={email} onChange={e => setEmail(e.target.value)} />
          {submit.isError && <p className="text-sm text-red-600">{errText(submit.error)}</p>}
          <button disabled={!canSubmit} onClick={() => submit.mutate()}
                  className="w-full bg-black text-white rounded py-2 disabled:opacity-40">
            {selected ? 'Trimite programarea' : 'Alege un interval'}
          </button>
        </section>
      </div>
    </div>
  )
}

function CenteredMessage({ title, body }: { title: string; body?: string }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4 text-center">
      <div><h1 className="text-2xl font-bold">{title}</h1>{body && <p className="text-muted-foreground mt-2">{body}</p>}</div>
    </div>
  )
}

function errText(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 429) return 'Ai atins limita de programări. Încearcă mai târziu.'
    if (e.status === 403) return 'Programările sunt închise.'
    if (e.status === 409) return 'Intervalul tocmai a fost ocupat. Alege altul.'
  }
  return 'A apărut o eroare. Încearcă din nou.'
}
