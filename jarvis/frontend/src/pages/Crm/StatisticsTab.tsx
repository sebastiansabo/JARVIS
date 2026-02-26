import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import {
  Car, DollarSign, Users, Building2, TrendingUp, BarChart3, Filter, X, Check, ChevronsUpDown,
  MapPin, UserCheck, Link2, Phone, Mail, AlertTriangle, GitMerge, Tag,
} from 'lucide-react'
import { crmApi } from '@/api/crm'

function fmt(n: number) {
  return Number(n).toLocaleString('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

function pct(part: number, total: number) {
  if (!total) return '0%'
  return `${((part / total) * 100).toFixed(1)}%`
}

/* ── Inline MultiSelect ── */
function MultiSelect({ label, options, selected, onChange }: {
  label: string
  options: string[]
  selected: string[]
  onChange: (v: string[]) => void
}) {
  const [open, setOpen] = useState(false)
  const toggle = (val: string) => {
    onChange(selected.includes(val) ? selected.filter(v => v !== val) : [...selected, val])
  }
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-9 min-w-[150px] justify-between font-normal">
          {selected.length === 0
            ? <span className="text-muted-foreground">{label}</span>
            : <span className="truncate max-w-[120px]">{selected.length} selected</span>}
          <ChevronsUpDown className="h-3.5 w-3.5 ml-1 opacity-50 shrink-0" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[220px] p-0" align="start">
        <div className="max-h-[260px] overflow-y-auto p-1">
          {options.length === 0 && (
            <p className="text-xs text-muted-foreground p-2">No options</p>
          )}
          {options.map(opt => {
            const active = selected.includes(opt)
            return (
              <button
                key={opt}
                onClick={() => toggle(opt)}
                className="flex items-center gap-2 w-full rounded px-2 py-1.5 text-sm hover:bg-accent text-left"
              >
                <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border ${active ? 'bg-primary border-primary text-primary-foreground' : 'border-muted-foreground/30'}`}>
                  {active && <Check className="h-3 w-3" />}
                </span>
                <span className="truncate">{opt}</span>
              </button>
            )
          })}
        </div>
        {selected.length > 0 && (
          <div className="border-t p-1">
            <button
              onClick={() => onChange([])}
              className="w-full rounded px-2 py-1.5 text-xs text-muted-foreground hover:bg-accent text-center"
            >
              Clear selection
            </button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  )
}

export default function StatisticsTab() {
  const [showFilters, setShowFilters] = useState(false)
  const [dealers, setDealers] = useState<string[]>([])
  const [brands, setBrands] = useState<string[]>([])
  const [statuses, setStatuses] = useState<string[]>([])
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const activeFilterCount = [dealers.length > 0, brands.length > 0, statuses.length > 0, !!dateFrom, !!dateTo].filter(Boolean).length
  const hasFilters = activeFilterCount > 0

  const filterParams: Record<string, string> = {}
  if (dealers.length) filterParams.dealers = dealers.join(',')
  if (brands.length) filterParams.brands = brands.join(',')
  if (statuses.length) filterParams.statuses = statuses.join(',')
  if (dateFrom) filterParams.date_from = dateFrom
  if (dateTo) filterParams.date_to = dateTo

  const { data, isLoading } = useQuery({
    queryKey: ['crm-detailed-stats', filterParams],
    queryFn: () => crmApi.getDetailedStats(filterParams),
  })
  const { data: dealersData } = useQuery({ queryKey: ['crm-dealers'], queryFn: crmApi.getDealers })
  const { data: brandsData } = useQuery({ queryKey: ['crm-brands'], queryFn: crmApi.getBrands })
  const { data: statusesData } = useQuery({ queryKey: ['crm-deal-statuses'], queryFn: crmApi.getDealStatuses })
  const { data: clientStats } = useQuery({ queryKey: ['crm-client-detailed-stats'], queryFn: crmApi.getClientDetailedStats })

  return (
    <div className="space-y-4">
      {/* Filter toggle button */}
      <div className="flex items-center gap-2 flex-wrap">
        <Button
          variant={hasFilters ? 'default' : 'outline'}
          size="sm"
          onClick={() => setShowFilters(!showFilters)}
        >
          <Filter className="h-4 w-4 mr-1" />
          Filters{hasFilters ? ` (${activeFilterCount})` : ''}
        </Button>
        {hasFilters && (
          <Button variant="ghost" size="sm" onClick={() => { setDealers([]); setBrands([]); setStatuses([]); setDateFrom(''); setDateTo('') }}>
            <X className="h-4 w-4 mr-1" />Clear all
          </Button>
        )}
        {dealers.map(d => (
          <Badge key={`d-${d}`} variant="secondary" className="gap-1 cursor-pointer" onClick={() => setDealers(dealers.filter(x => x !== d))}>
            {d} <X className="h-3 w-3" />
          </Badge>
        ))}
        {brands.map(b => (
          <Badge key={`b-${b}`} variant="secondary" className="gap-1 cursor-pointer" onClick={() => setBrands(brands.filter(x => x !== b))}>
            {b} <X className="h-3 w-3" />
          </Badge>
        ))}
        {statuses.map(s => (
          <Badge key={`s-${s}`} variant="secondary" className="gap-1 cursor-pointer" onClick={() => setStatuses(statuses.filter(x => x !== s))}>
            {s} <X className="h-3 w-3" />
          </Badge>
        ))}
      </div>

      {/* Collapsible filter panel */}
      {showFilters && (
        <Card>
          <CardContent className="p-3">
            <div className="flex flex-wrap gap-2 items-center">
              <MultiSelect label="Dealers" options={dealersData?.dealers ?? []} selected={dealers} onChange={setDealers} />
              <MultiSelect label="Brands" options={brandsData?.brands ?? []} selected={brands} onChange={setBrands} />
              <MultiSelect label="Statuses" options={statusesData?.statuses.map(s => s.dossier_status) ?? []} selected={statuses} onChange={setStatuses} />
              <Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className="w-[140px] h-9" title="From date" />
              <Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} className="w-[140px] h-9" title="To date" />
            </div>
          </CardContent>
        </Card>
      )}

      {/* ═══════════ DEAL STATISTICS ═══════════ */}
      <h2 className="text-lg font-semibold">Deal Statistics</h2>

      {isLoading || !data ? (
        <div className="flex items-center justify-center py-12 text-muted-foreground">Loading statistics...</div>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <SummaryCard icon={Car} label="Total Deals" value={fmt(data.totals.total_deals)} color="text-primary" bg="bg-primary/10" />
            <SummaryCard icon={DollarSign} label="Total Revenue" value={fmt(data.totals.total_revenue)} color="text-green-500" bg="bg-green-500/10" />
            <SummaryCard icon={TrendingUp} label="Avg Price" value={fmt(data.totals.avg_price)} color="text-blue-500" bg="bg-blue-500/10" />
            <SummaryCard icon={BarChart3} label="Brands" value={String(data.totals.brand_count)} color="text-violet-500" bg="bg-violet-500/10" />
            <SummaryCard icon={Building2} label="Dealers" value={String(data.totals.dealer_count)} color="text-orange-500" bg="bg-orange-500/10" />
            <SummaryCard icon={Users} label="Sales People" value={String(data.totals.sales_person_count)} color="text-pink-500" bg="bg-pink-500/10" />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <DealStatsTable title="By Brand" rows={data.by_brand} nameKey="brand" showRevenue />
            <DealStatsTable title="By Dealer" rows={data.by_dealer} nameKey="dealer_name" showRevenue />
            <DealStatsTable title="By Sales Person" rows={data.by_sales_person} nameKey="sales_person" showRevenue />
            <DealStatsTable title="By Status" rows={data.by_status} nameKey="dossier_status" />
          </div>

          {/* Monthly trend */}
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Monthly Trend (Deals)</CardTitle></CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Month</TableHead>
                      <TableHead className="text-right">Deals</TableHead>
                      <TableHead className="text-right">Revenue</TableHead>
                      <TableHead className="w-[40%]">Volume</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(() => {
                      const maxCount = Math.max(...data.by_month.map(m => m.count), 1)
                      return data.by_month.map(r => (
                        <TableRow key={r.month}>
                          <TableCell className="font-mono text-sm">{r.month}</TableCell>
                          <TableCell className="text-right">{fmt(r.count)}</TableCell>
                          <TableCell className="text-right font-mono text-xs">{fmt(r.revenue)}</TableCell>
                          <TableCell>
                            <div className="h-4 rounded bg-primary/20">
                              <div className="h-full rounded bg-primary" style={{ width: `${(r.count / maxCount) * 100}%` }} />
                            </div>
                          </TableCell>
                        </TableRow>
                      ))
                    })()}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </>
      )}

      {/* ═══════════ CLIENT STATISTICS ═══════════ */}
      {clientStats && (() => {
        const total = clientStats.total
        const cov = clientStats.contact_coverage
        const qual = clientStats.data_quality
        return (
          <>
            <h2 className="text-lg font-semibold pt-4">Client Statistics</h2>

            {/* Summary cards */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
              <SummaryCard icon={Users} label="Total Clients" value={fmt(total)} color="text-primary" bg="bg-primary/10" />
              <SummaryCard icon={Link2} label="With Deals" value={fmt(clientStats.clients_with_deals)} sub={pct(clientStats.clients_with_deals, total)} color="text-green-500" bg="bg-green-500/10" />
              <SummaryCard icon={UserCheck} label="Linked Deals" value={fmt(clientStats.total_deals_linked)} color="text-blue-500" bg="bg-blue-500/10" />
              <SummaryCard icon={MapPin} label="Regions" value={String(clientStats.by_region.length)} color="text-orange-500" bg="bg-orange-500/10" />
              <SummaryCard icon={Building2} label="Cities" value={String(clientStats.by_city.length)} color="text-violet-500" bg="bg-violet-500/10" />
              <SummaryCard icon={GitMerge} label="Merged" value={fmt(qual.merged_clients)} color="text-pink-500" bg="bg-pink-500/10" />
            </div>

            {/* Contact Coverage */}
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Contact Info Coverage</CardTitle></CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 sm:grid-cols-5 gap-3">
                  <CoverageBar icon={Phone} label="Phone" have={cov.with_phone} total={total} />
                  <CoverageBar icon={Mail} label="Email" have={cov.with_email} total={total} />
                  <CoverageBar icon={MapPin} label="Region" have={cov.with_region} total={total} />
                  <CoverageBar icon={Building2} label="City" have={cov.with_city} total={total} />
                  <CoverageBar icon={MapPin} label="Street" have={cov.with_street} total={total} />
                </div>
              </CardContent>
            </Card>

            {/* Data Quality */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-1.5">
                  <AlertTriangle className="h-4 w-4 text-amber-500" />Data Quality
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <QualityCard label="Missing Phone" value={qual.missing_phone} total={total} severity={qual.missing_phone / total} />
                  <QualityCard label="Missing Email" value={qual.missing_email} total={total} severity={qual.missing_email / total} />
                  <QualityCard label="Missing Region" value={qual.missing_region} total={total} severity={qual.missing_region / total} />
                  <QualityCard label="No Responsible" value={qual.missing_responsible} total={total} severity={qual.missing_responsible / total} />
                </div>
              </CardContent>
            </Card>

            {/* Monthly Growth */}
            {clientStats.by_month.length > 0 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-1.5">
                    <TrendingUp className="h-4 w-4" />Monthly Growth (Last 12 Months)
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  <div className="overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Month</TableHead>
                          <TableHead className="text-right">New Clients</TableHead>
                          <TableHead className="w-[40%]">Volume</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {(() => {
                          const maxCount = Math.max(...clientStats.by_month.map(m => m.count), 1)
                          return clientStats.by_month.map(r => (
                            <TableRow key={r.month}>
                              <TableCell className="font-mono text-sm">{r.month}</TableCell>
                              <TableCell className="text-right">{fmt(r.count)}</TableCell>
                              <TableCell>
                                <div className="h-4 rounded bg-primary/20">
                                  <div className="h-full rounded bg-primary" style={{ width: `${(r.count / maxCount) * 100}%` }} />
                                </div>
                              </TableCell>
                            </TableRow>
                          ))
                        })()}
                      </TableBody>
                    </Table>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Breakdown tables */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <ClientStatsTable title="By Type" rows={clientStats.by_type} nameKey="client_type" total={total} />
              <ClientStatsTable title="By Region" rows={clientStats.by_region} nameKey="region" total={total} />
              <ClientStatsTable title="By City" rows={clientStats.by_city} nameKey="city" total={total} />
              <ClientStatsTable title="By Responsible" rows={clientStats.by_responsible} nameKey="responsible" total={total} />
            </div>

            {/* Source Flags */}
            {clientStats.source_flags.length > 0 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-1.5">
                    <Tag className="h-4 w-4" />Data Sources
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex flex-wrap gap-2">
                    {clientStats.source_flags.map(s => (
                      <Badge key={s.source} variant="secondary" className="text-sm py-1 px-3">
                        {s.source} <span className="ml-1.5 font-bold">{fmt(s.count)}</span>
                      </Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </>
        )
      })()}
    </div>
  )
}

/* ── Shared components ── */

function SummaryCard({ icon: Icon, label, value, sub, color, bg }: {
  icon: React.ElementType; label: string; value: string; sub?: string; color: string; bg: string
}) {
  return (
    <Card>
      <CardContent className="p-3 flex items-center gap-2.5">
        <div className={`rounded-md ${bg} p-1.5`}><Icon className={`h-4 w-4 ${color}`} /></div>
        <div>
          <p className="text-lg font-bold leading-none">{value}</p>
          <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
          {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
        </div>
      </CardContent>
    </Card>
  )
}

function CoverageBar({ icon: Icon, label, have, total }: {
  icon: React.ElementType; label: string; have: number; total: number
}) {
  const percent = total ? (have / total) * 100 : 0
  const color = percent >= 80 ? 'bg-green-500' : percent >= 50 ? 'bg-amber-500' : 'bg-red-500'
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="flex items-center gap-1.5 text-muted-foreground"><Icon className="h-3.5 w-3.5" />{label}</span>
        <span className="font-medium">{percent.toFixed(1)}%</span>
      </div>
      <div className="h-2 rounded-full bg-muted">
        <div className={`h-full rounded-full ${color} transition-all`} style={{ width: `${percent}%` }} />
      </div>
      <p className="text-xs text-muted-foreground">{fmt(have)} / {fmt(total)}</p>
    </div>
  )
}

function QualityCard({ label, value, total, severity }: {
  label: string; value: number; total: number; severity: number
}) {
  const color = severity >= 0.5 ? 'text-red-500' : severity >= 0.2 ? 'text-amber-500' : 'text-green-500'
  return (
    <div className="rounded-lg border p-3">
      <p className={`text-xl font-bold ${color}`}>{fmt(value)}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-xs text-muted-foreground">{pct(value, total)} of total</p>
    </div>
  )
}

function DealStatsTable({ title, rows, nameKey, showRevenue }: { title: string; rows: Record<string, unknown>[]; nameKey: string; showRevenue?: boolean }) {
  const filtered = rows.filter(r => r[nameKey] != null && r[nameKey] !== '' && (r.count as number) > 0)
  if (filtered.length === 0) return null
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-sm">{title}</CardTitle></CardHeader>
      <CardContent className="p-0">
        <div className="max-h-[350px] overflow-y-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead className="text-right">Count</TableHead>
                {showRevenue && <TableHead className="text-right">Revenue</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((r, i) => (
                <TableRow key={i}>
                  <TableCell className="font-medium text-sm">{String(r[nameKey])}</TableCell>
                  <TableCell className="text-right">{fmt(r.count as number)}</TableCell>
                  {showRevenue && <TableCell className="text-right font-mono text-xs">{fmt(r.revenue as number)}</TableCell>}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}

function ClientStatsTable({ title, rows, nameKey, total }: {
  title: string; rows: Record<string, unknown>[]; nameKey: string; total: number
}) {
  const filtered = rows.filter(r => r[nameKey] != null && r[nameKey] !== '' && (r.count as number) > 0)
  if (filtered.length === 0) return null
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-sm">{title}</CardTitle></CardHeader>
      <CardContent className="p-0">
        <div className="max-h-[350px] overflow-y-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead className="text-right">Count</TableHead>
                <TableHead className="text-right">%</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((r, i) => (
                <TableRow key={i}>
                  <TableCell className="font-medium text-sm">{String(r[nameKey])}</TableCell>
                  <TableCell className="text-right">{fmt(r.count as number)}</TableCell>
                  <TableCell className="text-right text-muted-foreground text-xs">{pct(r.count as number, total)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}
