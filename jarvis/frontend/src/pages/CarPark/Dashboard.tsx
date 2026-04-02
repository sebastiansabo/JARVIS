import { useQuery } from '@tanstack/react-query'
import {
  Car, TrendingUp, TrendingDown, Clock, AlertTriangle,
  Package, Eye, MessageSquare, DollarSign, Activity,
  BarChart3, ArrowRight,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { PageHeader } from '@/components/shared/PageHeader'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { carparkApi } from '@/api/carpark'
import type {
  DashboardData,
  AgingBucket,
  BrandBreakdown,
  MonthlySales,
  CostOverviewItem,
  RecentActivity,
} from '@/types/carpark'
import { STATUS_LABELS } from '@/types/carpark'

function fmt(val: number | null | undefined): string {
  if (val == null) return '0'
  return new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(val)
}

function fmtDec(val: number | null | undefined, decimals = 1): string {
  if (val == null) return '0'
  return new Intl.NumberFormat('ro-RO', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(val)
}

function fmtCurrency(val: number | null | undefined): string {
  if (val == null) return '0 €'
  return `${fmt(val)} €`
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h`
  const days = Math.floor(hrs / 24)
  return `${days}z`
}

export default function CarParkDashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ['carpark', 'dashboard'],
    queryFn: () => carparkApi.getDashboard(90),
    refetchInterval: 60000,
  })

  if (isLoading || !data) {
    return (
      <div className="space-y-6">
        <PageHeader title="Dashboard Parc Auto" description="Se încarcă..." />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <Card key={i} className="p-4 animate-pulse">
              <div className="h-4 w-20 bg-muted rounded mb-2" />
              <div className="h-8 w-16 bg-muted rounded" />
            </Card>
          ))}
        </div>
      </div>
    )
  }

  const { summary, kpis, aging_distribution, profitability, brand_breakdown, monthly_sales, publishing, cost_overview, recent_activity } = data

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard Parc Auto"
        description="KPI-uri, stoc și performanță"
      />

      {/* ── KPI Cards Row 1: Inventory ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard
          icon={<Car className="h-4 w-4" />}
          label="Vehicule în stoc"
          value={fmt(summary.in_stock)}
          sub={`din ${fmt(summary.total_vehicles)} total`}
        />
        <KpiCard
          icon={<DollarSign className="h-4 w-4" />}
          label="Valoare stoc"
          value={fmtCurrency(summary.total_stock_value)}
          sub={`achiziție: ${fmtCurrency(summary.total_acquisition_value)}`}
        />
        <KpiCard
          icon={<TrendingUp className="h-4 w-4" />}
          label="Vândute (30 zile)"
          value={fmt(kpis.sold_last_30d)}
          sub={`${fmt(kpis.sold_last_365d)} / an`}
          accent
        />
        <KpiCard
          icon={<Clock className="h-4 w-4" />}
          label="Zile medii pe stoc"
          value={fmt(kpis.avg_days_on_lot)}
          sub="obiectiv: < 45 zile"
          warn={kpis.avg_days_on_lot > 45}
        />
      </div>

      {/* ── KPI Cards Row 2: Performance ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard
          icon={<Activity className="h-4 w-4" />}
          label="Rotație inventar"
          value={`${fmtDec(kpis.inventory_turn_rate)}x`}
          sub="obiectiv: 12x / an"
          warn={kpis.inventory_turn_rate < 8}
        />
        <KpiCard
          icon={<AlertTriangle className="h-4 w-4" />}
          label="Stoc vechi (>60 zile)"
          value={`${fmtDec(kpis.aged_percent)}%`}
          sub={`${fmt(kpis.aged_count)} vehicule`}
          warn={kpis.aged_percent > 15}
        />
        <KpiCard
          icon={<TrendingUp className="h-4 w-4" />}
          label="GROI"
          value={`${fmtDec(kpis.groi, 2)}%`}
          sub="obiectiv: > 100%"
          warn={kpis.groi < 100}
        />
        <KpiCard
          icon={<BarChart3 className="h-4 w-4" />}
          label="Eficiență stocking"
          value={`${fmtDec(kpis.stocking_efficiency)}%`}
          sub="vândute < 30 zile"
          accent={kpis.stocking_efficiency >= 60}
        />
      </div>

      {/* ── Main content grid ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column: charts & breakdowns */}
        <div className="lg:col-span-2 space-y-6">
          {/* Profitability summary */}
          <ProfitabilitySection profitability={profitability} />

          {/* Monthly sales trend */}
          {monthly_sales.length > 0 && (
            <MonthlySalesChart data={monthly_sales} />
          )}

          {/* Aging distribution */}
          {aging_distribution.length > 0 && (
            <AgingChart data={aging_distribution} />
          )}

          {/* Brand breakdown */}
          {brand_breakdown.length > 0 && (
            <BrandTable data={brand_breakdown} />
          )}

          {/* Cost overview */}
          {cost_overview.length > 0 && (
            <CostTable data={cost_overview} />
          )}
        </div>

        {/* Right column: sidebar widgets */}
        <div className="space-y-6">
          {/* Quick status */}
          <StatusWidget summary={summary} />

          {/* Publishing */}
          <PublishingWidget stats={publishing} />

          {/* Recent activity */}
          {recent_activity.length > 0 && (
            <ActivityFeed data={recent_activity} />
          )}
        </div>
      </div>
    </div>
  )
}

// ── KPI Card ────────────────────────────────────────

function KpiCard({ icon, label, value, sub, warn, accent }: {
  icon: React.ReactNode
  label: string
  value: string
  sub?: string
  warn?: boolean
  accent?: boolean
}) {
  return (
    <Card className={`p-4 ${warn ? 'border-amber-500/50 bg-amber-500/5' : ''}`}>
      <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
        {icon}
        <span className="truncate">{label}</span>
      </div>
      <div className={`text-2xl font-bold tabular-nums ${accent ? 'text-emerald-600' : ''} ${warn ? 'text-amber-600' : ''}`}>
        {value}
      </div>
      {sub && <div className="text-xs text-muted-foreground mt-1">{sub}</div>}
    </Card>
  )
}

// ── Profitability Section ───────────────────────────

function ProfitabilitySection({ profitability }: { profitability: DashboardData['profitability'] }) {
  if (!profitability.vehicles_sold) {
    return (
      <Card className="p-5">
        <h3 className="text-sm font-semibold mb-2">Profitabilitate (ultimele 90 zile)</h3>
        <p className="text-sm text-muted-foreground">Nicio vânzare în perioada selectată</p>
      </Card>
    )
  }

  const marginColor = profitability.avg_margin_percent >= 10
    ? 'text-emerald-600' : profitability.avg_margin_percent >= 5
    ? 'text-amber-600' : 'text-red-600'

  return (
    <Card className="p-5">
      <h3 className="text-sm font-semibold mb-4">Profitabilitate (ultimele 90 zile)</h3>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div>
          <div className="text-xs text-muted-foreground">Vehicule vândute</div>
          <div className="text-lg font-bold">{profitability.vehicles_sold}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Venituri totale</div>
          <div className="text-lg font-bold">{fmtCurrency(profitability.total_revenue)}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Profit brut total</div>
          <div className={`text-lg font-bold ${profitability.total_gross_profit >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
            {fmtCurrency(profitability.total_gross_profit)}
          </div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Marjă medie</div>
          <div className={`text-lg font-bold ${marginColor}`}>
            {fmtDec(profitability.avg_margin_percent)}%
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-3 pt-3 border-t">
        <div>
          <div className="text-xs text-muted-foreground">Profit / vehicul</div>
          <div className="text-sm font-medium">{fmtCurrency(profitability.avg_profit_per_unit)}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Zile medii până la vânzare</div>
          <div className="text-sm font-medium">{profitability.avg_days_to_sell} zile</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Total achiziție</div>
          <div className="text-sm font-medium">{fmtCurrency(profitability.total_acquisition)}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Total costuri</div>
          <div className="text-sm font-medium">{fmtCurrency(profitability.total_costs)}</div>
        </div>
      </div>
    </Card>
  )
}

// ── Monthly Sales Bar Chart (CSS-based) ─────────────

function MonthlySalesChart({ data }: { data: MonthlySales[] }) {
  const maxRevenue = Math.max(...data.map(d => d.revenue), 1)

  return (
    <Card className="p-5">
      <h3 className="text-sm font-semibold mb-4">Vânzări lunare (12 luni)</h3>
      <div className="space-y-2">
        {data.map((m) => (
          <div key={m.month} className="flex items-center gap-3 text-xs">
            <span className="w-14 text-muted-foreground font-mono shrink-0">{m.month}</span>
            <div className="flex-1 flex items-center gap-2">
              <div className="flex-1 h-5 bg-muted rounded-sm overflow-hidden relative">
                <div
                  className="absolute inset-y-0 left-0 bg-blue-500/80 rounded-sm"
                  style={{ width: `${(m.revenue / maxRevenue) * 100}%` }}
                />
                <div
                  className="absolute inset-y-0 left-0 bg-emerald-500/90 rounded-sm"
                  style={{ width: `${(m.gross_profit / maxRevenue) * 100}%` }}
                />
              </div>
              <span className="w-6 text-right font-medium">{m.sold}</span>
            </div>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-4 mt-3 text-[10px] text-muted-foreground">
        <span className="flex items-center gap-1"><span className="w-3 h-2 bg-blue-500/80 rounded-sm inline-block" /> Venituri</span>
        <span className="flex items-center gap-1"><span className="w-3 h-2 bg-emerald-500/90 rounded-sm inline-block" /> Profit brut</span>
        <span className="flex items-center gap-1">Nr = vehicule vândute</span>
      </div>
    </Card>
  )
}

// ── Aging Distribution ──────────────────────────────

function AgingChart({ data }: { data: AgingBucket[] }) {
  const maxCount = Math.max(...data.map(d => d.count), 1)
  const total = data.reduce((s, d) => s + d.count, 0)

  const bucketColors: Record<string, string> = {
    '0-15': 'bg-emerald-500',
    '16-30': 'bg-emerald-400',
    '31-45': 'bg-amber-400',
    '46-60': 'bg-amber-500',
    '61-90': 'bg-orange-500',
    '90+': 'bg-red-500',
  }

  return (
    <Card className="p-5">
      <h3 className="text-sm font-semibold mb-4">Distribuție vechime stoc</h3>
      <div className="space-y-2">
        {data.map((bucket) => (
          <div key={bucket.bucket} className="flex items-center gap-3 text-xs">
            <span className="w-12 text-muted-foreground font-mono shrink-0">{bucket.bucket}z</span>
            <div className="flex-1 h-6 bg-muted rounded-sm overflow-hidden relative">
              <div
                className={`absolute inset-y-0 left-0 rounded-sm ${bucketColors[bucket.bucket] || 'bg-gray-400'}`}
                style={{ width: `${(bucket.count / maxCount) * 100}%` }}
              />
              <span className="absolute inset-y-0 left-2 flex items-center text-[11px] font-medium text-white drop-shadow">
                {bucket.count > 0 ? bucket.count : ''}
              </span>
            </div>
            <span className="w-20 text-right text-muted-foreground">
              {fmtCurrency(bucket.total_value)}
            </span>
            <span className="w-10 text-right text-muted-foreground">
              {total > 0 ? `${Math.round(100 * bucket.count / total)}%` : ''}
            </span>
          </div>
        ))}
      </div>
    </Card>
  )
}

// ── Brand Breakdown Table ───────────────────────────

function BrandTable({ data }: { data: BrandBreakdown[] }) {
  const total = data.reduce((s, b) => s + b.count, 0)

  return (
    <Card className="p-5">
      <h3 className="text-sm font-semibold mb-3">Stoc pe brand</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b text-muted-foreground">
              <th className="text-left py-1.5 font-medium">Brand</th>
              <th className="text-right py-1.5 font-medium">Vehicule</th>
              <th className="text-right py-1.5 font-medium">%</th>
              <th className="text-right py-1.5 font-medium">Valoare</th>
              <th className="text-right py-1.5 font-medium">Zile medii</th>
            </tr>
          </thead>
          <tbody>
            {data.map((b) => (
              <tr key={b.brand} className="border-b border-muted/50">
                <td className="py-1.5 font-medium">{b.brand}</td>
                <td className="text-right py-1.5 tabular-nums">{b.count}</td>
                <td className="text-right py-1.5 tabular-nums text-muted-foreground">
                  {total > 0 ? `${Math.round(100 * b.count / total)}%` : '-'}
                </td>
                <td className="text-right py-1.5 tabular-nums">{fmtCurrency(b.total_value)}</td>
                <td className={`text-right py-1.5 tabular-nums ${b.avg_days > 60 ? 'text-amber-600 font-medium' : ''}`}>
                  {b.avg_days}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

// ── Cost Overview Table ─────────────────────────────

function CostTable({ data }: { data: CostOverviewItem[] }) {
  const totalCost = data.reduce((s, c) => s + c.total_amount, 0)

  return (
    <Card className="p-5">
      <h3 className="text-sm font-semibold mb-3">Costuri pe stoc curent</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b text-muted-foreground">
              <th className="text-left py-1.5 font-medium">Tip cost</th>
              <th className="text-right py-1.5 font-medium">Înreg.</th>
              <th className="text-right py-1.5 font-medium">Vehicule</th>
              <th className="text-right py-1.5 font-medium">Total</th>
              <th className="text-right py-1.5 font-medium">%</th>
            </tr>
          </thead>
          <tbody>
            {data.map((c) => (
              <tr key={c.cost_type} className="border-b border-muted/50">
                <td className="py-1.5 font-medium capitalize">{c.cost_type.replace(/_/g, ' ')}</td>
                <td className="text-right py-1.5 tabular-nums">{c.entries}</td>
                <td className="text-right py-1.5 tabular-nums">{c.vehicles}</td>
                <td className="text-right py-1.5 tabular-nums">{fmtCurrency(c.total_amount)}</td>
                <td className="text-right py-1.5 tabular-nums text-muted-foreground">
                  {totalCost > 0 ? `${Math.round(100 * c.total_amount / totalCost)}%` : '-'}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t font-medium">
              <td className="py-1.5">Total</td>
              <td className="text-right py-1.5" colSpan={2}>{data.reduce((s, c) => s + c.entries, 0)}</td>
              <td className="text-right py-1.5">{fmtCurrency(totalCost)}</td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
    </Card>
  )
}

// ── Status Widget ───────────────────────────────────

function StatusWidget({ summary }: { summary: DashboardData['summary'] }) {
  const items = [
    { label: 'Pregătire', value: summary.in_preparation, color: 'bg-orange-500' },
    { label: 'Gata de vânzare', value: summary.ready_for_sale, color: 'bg-emerald-500' },
    { label: 'Listate', value: summary.listed, color: 'bg-blue-500' },
    { label: 'Rezervate', value: summary.reserved, color: 'bg-purple-500' },
    { label: 'Vândute/Livrate', value: summary.sold_delivered, color: 'bg-gray-400' },
  ]

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold">Status stoc</h3>
        <Link to="/app/carpark" className="text-xs text-primary hover:underline flex items-center gap-1">
          Catalog <ArrowRight className="h-3 w-3" />
        </Link>
      </div>
      <div className="space-y-2.5">
        {items.map((item) => (
          <div key={item.label} className="flex items-center gap-3 text-xs">
            <span className={`w-2 h-2 rounded-full ${item.color} shrink-0`} />
            <span className="flex-1 text-muted-foreground">{item.label}</span>
            <span className="font-medium tabular-nums">{item.value}</span>
          </div>
        ))}
      </div>
    </Card>
  )
}

// ── Publishing Widget ───────────────────────────────

function PublishingWidget({ stats }: { stats: DashboardData['publishing'] }) {
  return (
    <Card className="p-5">
      <h3 className="text-sm font-semibold mb-3">Publishing</h3>
      <div className="space-y-2.5 text-xs">
        <div className="flex items-center gap-2">
          <Package className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="flex-1 text-muted-foreground">Vehicule publicate</span>
          <span className="font-medium tabular-nums">{stats.vehicles_published}</span>
        </div>
        <div className="flex items-center gap-2">
          <Eye className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="flex-1 text-muted-foreground">Vizualizări totale</span>
          <span className="font-medium tabular-nums">{fmt(stats.total_views)}</span>
        </div>
        <div className="flex items-center gap-2">
          <MessageSquare className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="flex-1 text-muted-foreground">Cereri de info</span>
          <span className="font-medium tabular-nums">{fmt(stats.total_inquiries)}</span>
        </div>
        <div className="flex items-center gap-2">
          <TrendingDown className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="flex-1 text-muted-foreground">Rată conversie</span>
          <span className="font-medium tabular-nums">{fmtDec(stats.inquiry_rate)}%</span>
        </div>
      </div>
    </Card>
  )
}

// ── Activity Feed ───────────────────────────────────

function ActivityFeed({ data }: { data: RecentActivity[] }) {
  return (
    <Card className="p-5">
      <h3 className="text-sm font-semibold mb-3">Activitate recentă</h3>
      <div className="space-y-3 max-h-[400px] overflow-y-auto">
        {data.map((a) => (
          <div key={a.id} className="flex gap-2 text-xs">
            <div className="w-1 rounded-full bg-primary/30 shrink-0" />
            <div className="min-w-0">
              <Link
                to={`/app/carpark/${a.vehicle_id}`}
                className="font-medium hover:underline truncate block"
              >
                {a.brand} {a.model}
              </Link>
              <div className="text-muted-foreground">
                {a.old_status ? (
                  <>
                    <span>{STATUS_LABELS[a.old_status as keyof typeof STATUS_LABELS] || a.old_status}</span>
                    <span className="mx-1">→</span>
                  </>
                ) : null}
                <Badge variant="outline" className="text-[10px] py-0">
                  {STATUS_LABELS[a.new_status as keyof typeof STATUS_LABELS] || a.new_status}
                </Badge>
                <span className="ml-2 text-muted-foreground/70">{timeAgo(a.changed_at)}</span>
              </div>
              {a.notes && <p className="text-muted-foreground/70 mt-0.5 truncate">{a.notes}</p>}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}
