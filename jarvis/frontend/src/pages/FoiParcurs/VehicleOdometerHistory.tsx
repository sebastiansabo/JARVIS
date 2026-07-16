import { useQuery } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import { api } from '@/api/client'

interface OdometerEntry {
  contract_id?: string | null
  route_type?: string | null
  status?: string | null
  km_start?: number | null
  km_end?: number | null
  departure_datetime?: string | null
  return_datetime?: string | null
  client_name?: string | null
  gap_km?: number | null
}

interface OdometerHistoryResp {
  success?: boolean
  vin?: string
  current_odometer?: number | null
  entries?: OdometerEntry[]
}

const nf = (n?: number | null) => (n == null ? '—' : n.toLocaleString('ro-RO'))

function fmt(dt?: string | null) {
  if (!dt) return '—'
  const d = new Date(dt)
  return Number.isNaN(d.getTime())
    ? '—'
    : d.toLocaleString('ro-RO', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

/** Odometer evolution for one car: chronological drives (km_start→km_end) with
 *  KM gaps (unlogged km between logged drives) flagged. Fetched from
 *  /api/foi-parcurs/odometer-history?vin=. Shown inside an expanded Driving Park row. */
export function VehicleOdometerHistory({ vin }: { vin: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['odometer-history', vin],
    queryFn: () => api.get<OdometerHistoryResp>('/api/foi-parcurs/odometer-history', { vin }),
    staleTime: 30_000,
  })

  if (isLoading) return <div className="p-4 text-sm text-muted-foreground">Se încarcă istoricul…</div>

  const entries = data?.entries ?? []
  if (entries.length === 0)
    return <div className="p-4 text-sm text-muted-foreground">Nicio cursă înregistrată pentru acest vehicul.</div>

  const rows = [...entries].reverse() // newest first
  const totalGap = entries.reduce((s, e) => s + (e.gap_km && e.gap_km > 0 ? e.gap_km : 0), 0)

  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h4 className="text-sm font-semibold">Evoluție kilometraj</h4>
        <div className="flex items-center gap-4 text-xs">
          {data?.current_odometer != null && (
            <span className="text-muted-foreground">
              Curent: <span className="font-semibold text-foreground">{nf(data.current_odometer)} km</span>
            </span>
          )}
          {totalGap > 0 && (
            <span className="flex items-center gap-1 text-destructive font-medium">
              <AlertTriangle className="h-3.5 w-3.5" />
              {nf(totalGap)} km neînregistrați
            </span>
          )}
        </div>
      </div>

      <div className="rounded-lg border overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-muted/50 text-muted-foreground">
            <tr>
              <th className="text-left font-medium px-3 py-1.5 whitespace-nowrap">Plecare</th>
              <th className="text-left font-medium px-3 py-1.5 whitespace-nowrap">Întoarcere</th>
              <th className="text-right font-medium px-3 py-1.5">KM start</th>
              <th className="text-right font-medium px-3 py-1.5">KM stop</th>
              <th className="text-right font-medium px-3 py-1.5">Parcurs</th>
              <th className="text-left font-medium px-3 py-1.5">Tip / Client</th>
              <th className="text-right font-medium px-3 py-1.5">Gol</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e, i) => {
              const driven = e.km_start != null && e.km_end != null ? e.km_end - e.km_start : null
              const gap = e.gap_km != null && e.gap_km > 0 ? e.gap_km : null
              return (
                <tr key={e.contract_id ?? i} className="border-t">
                  <td className="px-3 py-1.5 whitespace-nowrap">{fmt(e.departure_datetime)}</td>
                  <td className="px-3 py-1.5 whitespace-nowrap">{e.return_datetime ? fmt(e.return_datetime) : '…'}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{nf(e.km_start)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{e.km_end == null ? '…' : nf(e.km_end)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{driven == null ? '—' : nf(driven)}</td>
                  <td className="px-3 py-1.5 whitespace-nowrap">
                    {e.route_type || '—'}
                    {e.client_name ? ` · ${e.client_name}` : ''}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {gap == null ? '' : <span className="text-destructive font-medium">+{nf(gap)}</span>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
