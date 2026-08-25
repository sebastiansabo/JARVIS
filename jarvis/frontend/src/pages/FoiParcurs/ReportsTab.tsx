import { Suspense, useState } from 'react'
import { createPortal } from 'react-dom'
import { useQuery } from '@tanstack/react-query'
import { cn, usePersistedState } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { foiParcursApi } from '@/api/foiParcurs'

/* Validated categorical palette (CVD-safe order) + reserved status colors.
   Fixed hex reads acceptably on both light and dark grounds; text/grid/axes use
   theme CSS vars so the charts follow the app theme. */
const SERIES = ['#2a78d6', '#1baf7a', '#eda100', '#008300', '#4a3aa7', '#e34948', '#e87ba4', '#eb6834']
const ACCENT = '#2a78d6'
const AQUA = '#1baf7a'
const STATUS_COLORS: Record<string, string> = {
  complete: '#0ca30c', planned: '#2a78d6', driving: '#1baf7a',
  late: '#d98a00', incomplete: '#eb6834', missed: '#d03b3b', pending: '#898781',
}
const STATUS_LABEL: Record<string, string> = {
  complete: 'Finalizate', planned: 'Programate', driving: 'În desfășurare',
  late: 'Întârziate', incomplete: 'Neîncheiate', missed: 'Ratate', pending: 'În așteptare',
}
const TYPE_LABEL: Record<string, string> = {
  test_drive: 'Test drive', comodat: 'Comodat', service: 'Curtoazie service', internal: 'Intern',
}
const SEGMENT_LABEL: Record<string, string> = { client: 'Cu client', internal: 'Intern' }
const CLIENT_TYPE_LABEL: Record<string, string> = { company: 'Firmă', person: 'Persoană fizică' }

const nf = new Intl.NumberFormat('ro-RO')
const eur = new Intl.NumberFormat('ro-RO', { maximumFractionDigits: 0 })

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function rangeForPreset(preset: string, from: string, to: string): { from: string; to: string } {
  const now = new Date()
  if (preset === 'month') return { from: ymd(new Date(now.getFullYear(), now.getMonth(), 1)), to: ymd(now) }
  if (preset === 'year') return { from: ymd(new Date(now.getFullYear(), 0, 1)), to: ymd(now) }
  if (preset === 'custom') return { from, to }
  return { from: ymd(new Date(now.getTime() - 29 * 864e5)), to: ymd(now) } // 30d default
}
const fmtDayTick = (b: string) => (b ? b.slice(8, 10) + '.' + b.slice(5, 7) : b)

/* ── lazy recharts (kept out of the main FoiParcurs bundle) ── */
const LazyRecharts = (() => {
  let mod: typeof import('recharts') | null = null
  let promise: Promise<typeof import('recharts')> | null = null
  return () => {
    if (mod) return mod
    if (!promise) { promise = import('recharts').then((m) => { mod = m; return m }) }
    throw promise
  }
})()

const TT = {
  contentStyle: { background: 'hsl(var(--popover))', border: '1px solid hsl(var(--border))', borderRadius: 8, fontSize: 12, color: 'hsl(var(--foreground))' },
  labelStyle: { color: 'hsl(var(--muted-foreground))' },
  itemStyle: { color: 'hsl(var(--foreground))' },
}

function ChartSkeleton({ h = 240 }: { h?: number }) {
  return <div className="animate-pulse rounded-md bg-muted" style={{ height: h }} />
}

function AreaTrend({ data }: { data: { bucket: string; count: number }[] }) {
  const { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip } = LazyRecharts()
  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -12 }}>
        <defs>
          <linearGradient id="rfArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={ACCENT} stopOpacity={0.25} />
            <stop offset="100%" stopColor={ACCENT} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
        <XAxis dataKey="bucket" tickFormatter={fmtDayTick} minTickGap={24}
               tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} />
        <YAxis allowDecimals={false} width={30} tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} />
        <Tooltip {...TT} formatter={(v) => [nf.format(Number(v)), 'sesiuni']} />
        <Area type="monotone" dataKey="count" stroke={ACCENT} strokeWidth={2} fill="url(#rfArea)" />
      </AreaChart>
    </ResponsiveContainer>
  )
}

function Donut({ rows, colors, centerCap }: {
  rows: { label: string; value: number; color?: string }[]; colors: string[]; centerCap: string
}) {
  const { ResponsiveContainer, PieChart, Pie, Cell, Tooltip } = LazyRecharts()
  const total = rows.reduce((s, r) => s + r.value, 0)
  if (!total) return <div className="py-8 text-center text-sm text-muted-foreground">Fără date în interval</div>
  return (
    <div className="flex items-center gap-4">
      <div className="relative shrink-0" style={{ width: 150, height: 150 }}>
        <ResponsiveContainer width={150} height={150}>
          <PieChart>
            <Pie data={rows} dataKey="value" nameKey="label" innerRadius={44} outerRadius={68} paddingAngle={2} stroke="none">
              {rows.map((r, i) => <Cell key={i} fill={r.color || colors[i % colors.length]} />)}
            </Pie>
            <Tooltip {...TT} formatter={(v, n) => [nf.format(Number(v)), String(n)]} />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-bold tabular-nums leading-none">{nf.format(total)}</span>
          <span className="mt-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">{centerCap}</span>
        </div>
      </div>
      <ul className="min-w-0 flex-1 space-y-1.5 text-sm">
        {rows.map((r, i) => (
          <li key={i} className="flex items-center justify-between gap-2">
            <span className="flex min-w-0 items-center gap-2">
              <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: r.color || colors[i % colors.length] }} />
              <span className="truncate text-muted-foreground">{r.label}</span>
            </span>
            <span className="font-semibold tabular-nums">{nf.format(r.value)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Bars({ rows, color, unit }: { rows: { label: string; value: number }[]; color?: string; unit?: string }) {
  const max = Math.max(1, ...rows.map((r) => r.value))
  if (!rows.length) return <div className="py-8 text-center text-sm text-muted-foreground">Fără date în interval</div>
  return (
    <div className="space-y-2">
      {rows.map((r, i) => (
        <div key={i} className="grid grid-cols-[minmax(0,7rem)_1fr_auto] items-center gap-3">
          <span className="truncate text-sm text-muted-foreground" title={r.label}>{r.label}</span>
          <div className="h-4 overflow-hidden rounded bg-muted">
            <div className="h-full rounded" style={{ width: `${(r.value / max) * 100}%`, background: color || ACCENT }} />
          </div>
          <span className="w-16 text-right text-sm font-semibold tabular-nums">{nf.format(r.value)}{unit ? ` ${unit}` : ''}</span>
        </div>
      ))}
    </div>
  )
}

type LbRow = { name: string; sub?: string; value: number; id?: string }

function Leaderboard({ rows, renderDetail }: { rows: LbRow[]; renderDetail?: (row: LbRow) => React.ReactNode }) {
  const [open, setOpen] = useState<number | null>(null)
  if (!rows.length) return <div className="py-8 text-center text-sm text-muted-foreground">Fără date în interval</div>
  return (
    <div className="space-y-2">
      {rows.map((r, i) => {
        const expandable = !!renderDetail
        const isOpen = open === i
        return (
          <div key={i}>
            <div
              role={expandable ? 'button' : undefined}
              tabIndex={expandable ? 0 : undefined}
              aria-expanded={expandable ? isOpen : undefined}
              onClick={expandable ? () => setOpen(isOpen ? null : i) : undefined}
              onKeyDown={expandable ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setOpen(isOpen ? null : i) } } : undefined}
              className={cn('grid grid-cols-[1.5rem_1fr_auto] items-center gap-3 rounded-lg border p-2.5',
                i === 0 ? 'border-primary/40 bg-primary/5' : 'bg-muted/40',
                expandable && 'cursor-pointer hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring')}>
              <span className={cn('grid h-6 w-6 place-items-center rounded-full text-xs font-bold tabular-nums',
                i === 0 ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground')}>{i + 1}</span>
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold" title={r.name}>{r.name}</div>
                {r.sub && <div className="truncate text-xs text-muted-foreground">{r.sub}</div>}
              </div>
              <div className="flex items-center gap-1.5">
                <div className="text-right">
                  <div className="text-lg font-bold tabular-nums leading-none">{nf.format(r.value)}</div>
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground">sesiuni</div>
                </div>
                {expandable && (
                  <svg className={cn('h-4 w-4 shrink-0 text-muted-foreground transition-transform', isOpen && 'rotate-180')}
                    viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6 9l6 6 6-6" /></svg>
                )}
              </div>
            </div>
            {expandable && isOpen && <div className="mt-1.5">{renderDetail!(r)}</div>}
          </div>
        )
      })}
    </div>
  )
}

/** Expanded drill-down under a leaderboard row: the sessions for one advisor
 *  (shows client + car) or one car (shows client + consilier). */
function SessionDrill({ kind, id, companyId, from, to, docType }: {
  kind: 'advisor' | 'car'; id: string; companyId: number; from: string; to: string; docType: string
}) {
  const { data, isLoading } = useQuery({
    queryKey: ['fp-report-sessions', kind, id, companyId, from, to, docType],
    queryFn: () => foiParcursApi.getReportSessions({
      company_id: companyId || undefined, date_from: from, date_to: to, document_type: docType,
      ...(kind === 'advisor' ? { advisor: id } : { vin: id }),
    }),
    staleTime: 30_000,
  })
  const rows = data?.sessions ?? []
  if (isLoading) return <div className="px-2 py-3 text-xs text-muted-foreground">Se încarcă sesiunile…</div>
  if (!rows.length) return <div className="px-2 py-3 text-xs text-muted-foreground">Fără sesiuni în interval</div>
  const otherCol = kind === 'advisor' ? 'Mașină' : 'Consilier'
  return (
    <div className="overflow-x-auto rounded-lg border bg-background">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b text-left text-[10px] uppercase tracking-wide text-muted-foreground">
            <th className="px-2 py-1.5 font-medium">Data</th>
            <th className="px-2 py-1.5 font-medium">Client</th>
            <th className="px-2 py-1.5 font-medium">{otherCol}</th>
            <th className="px-2 py-1.5 font-medium">Status</th>
            <th className="px-2 py-1.5 text-right font-medium">Km</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.id} className="border-b last:border-0">
              <td className="whitespace-nowrap px-2 py-1.5 tabular-nums text-muted-foreground">{s.date}</td>
              <td className="px-2 py-1.5">{s.client}</td>
              <td className="px-2 py-1.5 text-muted-foreground">{kind === 'advisor' ? s.model : (s.advisor || '—')}</td>
              <td className="px-2 py-1.5">{STATUS_LABEL[s.td_status] ?? s.td_status}</td>
              <td className="px-2 py-1.5 text-right tabular-nums">{nf.format(s.km)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Seg<T extends string>({ value, onChange, options }: {
  value: T; onChange: (v: T) => void; options: readonly (readonly [T, string])[]
}) {
  return (
    <div className="inline-flex gap-0.5 rounded-lg border bg-muted/50 p-0.5">
      {options.map(([v, label]) => (
        <button key={v} type="button" onClick={() => onChange(v)}
          className={cn('rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
            value === v ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground')}>
          {label}
        </button>
      ))}
    </div>
  )
}

export function ReportsTab({ companyId, toolbarSlot, documentType }: { companyId: number; toolbarSlot?: HTMLElement | null; documentType?: 'sales' | 'service' }) {
  const [preset, setPreset] = usePersistedState<'30d' | 'month' | 'year' | 'custom'>('fp.rep.preset', '30d')
  const [customFrom, setCustomFrom] = usePersistedState<string>('fp.rep.from', ymd(new Date(Date.now() - 29 * 864e5)))
  const [customTo, setCustomTo] = usePersistedState<string>('fp.rep.to', ymd(new Date()))
  // Respect the page header's Sales/Service toggle when it exists (documentType
  // prop); only fall back to an own toggle where the page provides none.
  const [ownDocType, setOwnDocType] = usePersistedState<'sales' | 'service'>('fp.rep.docType', 'sales')
  const docType = documentType ?? ownDocType
  const [odoOrder, setOdoOrder] = usePersistedState<'high' | 'low'>('fp.rep.odo', 'high')

  const { from, to } = rangeForPreset(preset, customFrom, customTo)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['fp-reports', companyId, from, to, docType, odoOrder],
    queryFn: () => foiParcursApi.getReports({
      company_id: companyId || undefined, date_from: from, date_to: to,
      document_type: docType, odo_order: odoOrder, top: 8,
    }),
    staleTime: 30_000,
  })

  const toolbar = (
    <div className="flex flex-wrap items-center gap-2">
      <Seg value={preset} onChange={setPreset} options={[['month', 'Luna curentă'], ['30d', 'Ultimele 30 zile'], ['year', 'Anul curent'], ['custom', 'Interval']] as const} />
      {preset === 'custom' && (
        <div className="flex items-center gap-1.5 text-xs">
          <input type="date" value={customFrom} max={customTo} onChange={(e) => setCustomFrom(e.target.value)}
            className="rounded-md border bg-background px-2 py-1" />
          <span className="text-muted-foreground">–</span>
          <input type="date" value={customTo} min={customFrom} onChange={(e) => setCustomTo(e.target.value)}
            className="rounded-md border bg-background px-2 py-1" />
        </div>
      )}
      {documentType === undefined && (
        <Seg value={ownDocType} onChange={setOwnDocType} options={[['sales', 'Vânzări'], ['service', 'Service']] as const} />
      )}
    </div>
  )

  // Show the per-company card whenever the scope spans >1 company (a single
  // selected company collapses it to one row). Robust regardless of is_group —
  // non-group users are backend-scoped to one company, so it stays hidden.
  const showGroup = (data?.top_companies?.length ?? 0) > 1

  return (
    <div className="mt-4 space-y-4">
      {toolbarSlot && createPortal(toolbar, toolbarSlot)}

      {data && !data.scope.is_group && (
        <p className="text-xs text-muted-foreground">
          Rapoarte limitate la compania dvs. — vizualizarea pe întreg grupul necesită rol de administrator sau board.
        </p>
      )}

      {isError && <Card><CardContent className="py-10 text-center text-sm text-destructive">Nu s-au putut încărca rapoartele.</CardContent></Card>}
      {isLoading && !data && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => <ChartSkeleton key={i} h={84} />)}
        </div>
      )}

      {data && (
        <>
          {/* KPI row */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <Kpi label="Sesiuni total" value={nf.format(data.kpis.total_sessions)} />
            <Kpi label="Km parcurși" value={nf.format(data.kpis.total_km)} unit="km" />
            <Kpi label="Mașini utilizate" value={nf.format(data.kpis.cars_used)} />
            {docType === 'service'
              ? <Kpi label="Venit închiriere" value={eur.format(data.rental?.total_eur ?? 0)} unit="€" />
              : <Kpi label="Test drive-uri" value={nf.format(data.kpis.test_drives)} />}
            <Kpi label="Km / sesiune" value={nf.format(data.kpis.avg_km_per_session)} unit="km" />
            <Kpi label="Rată finalizare" value={nf.format(data.kpis.completion_rate)} unit="%" />
          </div>

          {/* performance leaderboards */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            {showGroup && (
              <ChartCard title="Performanță pe companii" hint="grup · după sesiuni">
                <Leaderboard rows={data.top_companies.map((c) => ({ name: c.company, sub: `${nf.format(c.km)} km`, value: c.sessions }))} />
              </ChartCard>
            )}
            <ChartCard title="Performanță consilieri" hint="după sesiuni · click pentru detalii">
              <Leaderboard
                rows={data.top_advisors.map((a) => ({ name: a.advisor, sub: `${nf.format(a.km)} km · ${a.completion_rate}% finalizare`, value: a.sessions, id: a.advisor }))}
                renderDetail={(row) => <SessionDrill kind="advisor" id={row.id!} companyId={companyId} from={from} to={to} docType={docType} />}
              />
            </ChartCard>
            <ChartCard title="Performanță mașini" hint="după sesiuni · click pentru detalii">
              <Leaderboard
                rows={data.utilization.map((u) => ({ name: u.model, sub: `${u.registration_number} · ${u.days_used}/30 zile`, value: u.sessions, id: u.vin }))}
                renderDetail={(row) => <SessionDrill kind="car" id={row.id!} companyId={companyId} from={from} to={to} docType={docType} />}
              />
            </ChartCard>
          </div>

          {/* charts */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <ChartCard title="Sesiuni în timp" hint="grupare pe zi" className="lg:col-span-2">
              <Suspense fallback={<ChartSkeleton />}><AreaTrend data={data.sessions_over_time} /></Suspense>
            </ChartCard>
            <ChartCard title="Sesiuni după status">
              <Suspense fallback={<ChartSkeleton h={150} />}>
                <Donut centerCap="sesiuni" colors={SERIES}
                  rows={data.by_status.map((s) => ({ label: STATUS_LABEL[s.status] ?? s.status, value: s.count, color: STATUS_COLORS[s.status] }))} />
              </Suspense>
            </ChartCard>

            <ChartCard title="Tip sesiune" hint="intern vs. client · pe tip document">
              <Bars rows={data.by_type.map((t) => ({ label: TYPE_LABEL[t.type] ?? t.type, value: t.count }))} />
            </ChartCard>
            <ChartCard title="Client vs. intern">
              <Bars color={AQUA} rows={data.client_vs_internal.map((s) => ({ label: SEGMENT_LABEL[s.segment] ?? s.segment, value: s.count }))} />
            </ChartCard>
            <ChartCard title="Sesiuni după marcă" hint="număr sesiuni">
              <Bars rows={data.by_brand.map((b) => ({ label: b.brand, value: b.count }))} />
            </ChartCard>

            <ChartCard title="Tip client" hint="sesiuni cu client">
              <Suspense fallback={<ChartSkeleton h={150} />}>
                <Donut centerCap="clienți" colors={[ACCENT, AQUA]}
                  rows={data.client_types.map((c) => ({ label: CLIENT_TYPE_LABEL[c.client_type] ?? c.client_type, value: c.count }))} />
              </Suspense>
            </ChartCard>
            <ChartCard title="Parc după combustibil" hint="nr. mașini active">
              <Suspense fallback={<ChartSkeleton h={150} />}>
                <Donut centerCap="mașini" colors={SERIES}
                  rows={data.fuel_composition.map((f) => ({ label: f.fuel_type, value: f.count }))} />
              </Suspense>
            </ChartCard>
            <ChartCard title="Distanță pe marcă" hint="km parcurși">
              <Bars unit="km" rows={data.distance_by_brand.map((d) => ({ label: d.brand, value: d.km }))} />
            </ChartCard>
          </div>

          {/* fleet + rental */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <ChartCard title="Ocupare flotă" hint="zile utilizate / 30 · cele mai folosite" className={docType === 'service' ? 'lg:col-span-2' : 'lg:col-span-3'}>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                      <th className="py-2 pr-3 font-medium">Mașină</th>
                      <th className="py-2 pr-3 font-medium">Model</th>
                      <th className="py-2 pr-3 text-right font-medium">Zile/30</th>
                      <th className="py-2 pr-3 text-right font-medium">Sesiuni</th>
                      <th className="py-2 pr-3 text-right font-medium">Km</th>
                      <th className="py-2 text-right font-medium">Km/ses.</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.utilization.map((u) => (
                      <tr key={u.vin} className="border-b last:border-0">
                        <td className="py-2 pr-3"><span className="rounded border px-1.5 py-0.5 font-mono text-[11px] font-semibold">{u.registration_number || '—'}</span></td>
                        <td className="py-2 pr-3 text-muted-foreground">{u.model}</td>
                        <td className="py-2 pr-3 text-right">
                          <span className="inline-flex items-center justify-end gap-2">
                            <span className="h-1.5 w-16 overflow-hidden rounded bg-muted">
                              <span className="block h-full rounded bg-primary" style={{ width: `${Math.min(100, (u.days_used / 30) * 100)}%` }} />
                            </span>
                            <span className="tabular-nums">{u.days_used}</span>
                          </span>
                        </td>
                        <td className="py-2 pr-3 text-right tabular-nums">{u.sessions}</td>
                        <td className="py-2 pr-3 text-right tabular-nums">{nf.format(u.km)}</td>
                        <td className="py-2 text-right tabular-nums">{u.sessions ? nf.format(Math.round(u.km / u.sessions)) : '—'}</td>
                      </tr>
                    ))}
                    {!data.utilization.length && <tr><td colSpan={6} className="py-8 text-center text-muted-foreground">Fără date în interval</td></tr>}
                  </tbody>
                </table>
              </div>
            </ChartCard>

            {docType === 'service' && (
              <ChartCard title="Venit închiriere" hint="doar Service · €">
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-bold tabular-nums">{eur.format(data.rental?.total_eur ?? 0)}</span>
                  <span className="text-sm font-semibold text-muted-foreground">€</span>
                </div>
                <p className="mb-3 text-xs text-muted-foreground">{data.rental?.sessions ?? 0} sesiuni curtoazie</p>
                <Bars unit="€" rows={(data.rental?.by_month ?? []).map((m) => ({ label: m.bucket, value: Math.round(m.eur) }))} />
              </ChartCard>
            )}
          </div>

          {/* clients + odometer */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <ChartCard title="Top clienți" hint="după sesiuni">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                      <th className="py-2 pr-3 font-medium">Client</th>
                      <th className="py-2 pr-3 font-medium">Tip</th>
                      <th className="py-2 pr-3 text-right font-medium">Sesiuni</th>
                      <th className="py-2 text-right font-medium">Km</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.top_clients.map((c, i) => (
                      <tr key={i} className="border-b last:border-0">
                        <td className="py-2 pr-3">{c.client}</td>
                        <td className="py-2 pr-3">
                          <span className={cn('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold',
                            c.client_type === 'company' ? 'bg-primary/10 text-primary' : 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400')}>
                            {CLIENT_TYPE_LABEL[c.client_type] ?? c.client_type}
                          </span>
                        </td>
                        <td className="py-2 pr-3 text-right tabular-nums">{c.sessions}</td>
                        <td className="py-2 text-right tabular-nums">{nf.format(c.km)}</td>
                      </tr>
                    ))}
                    {!data.top_clients.length && <tr><td colSpan={4} className="py-8 text-center text-muted-foreground">Fără date în interval</td></tr>}
                  </tbody>
                </table>
              </div>
            </ChartCard>

            <ChartCard title="Mașini după km bord"
              action={<Seg value={odoOrder} onChange={setOdoOrder} options={[['high', 'Cele mai rulate'], ['low', 'Cele mai puțin rulate']] as const} />}>
              <Bars unit="km" color={odoOrder === 'high' ? ACCENT : AQUA}
                rows={data.top_odometer.map((v) => ({ label: v.registration_number || v.model, value: v.odometer_km }))} />
            </ChartCard>
          </div>
        </>
      )}
    </div>
  )
}

function Kpi({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <Card>
      <CardContent className="p-3.5">
        <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
        <div className="mt-1 text-2xl font-bold tabular-nums leading-none">
          {value}{unit && <span className="ml-1 text-sm font-semibold text-muted-foreground">{unit}</span>}
        </div>
      </CardContent>
    </Card>
  )
}

function ChartCard({ title, hint, action, className, children }: {
  title: string; hint?: string; action?: React.ReactNode; className?: string; children: React.ReactNode
}) {
  return (
    <Card className={className}>
      <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0 pb-3">
        <div>
          <CardTitle className="text-sm">{title}</CardTitle>
          {hint && <p className="mt-0.5 text-[11px] text-muted-foreground">{hint}</p>}
        </div>
        {action}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}
