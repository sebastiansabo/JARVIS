import { Megaphone, FileCheck, Award, Flag, BarChart3 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useHappyHealth } from '@/api/happyAdmin'

function StatTile({
  icon,
  label,
  value,
  sub,
}: {
  icon: React.ReactNode
  label: string
  value: React.ReactNode
  sub?: string
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {icon}
          {label}
        </div>
        <p className="mt-1 text-2xl font-semibold">{value}</p>
        {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
      </CardContent>
    </Card>
  )
}

export function KpiTab() {
  const { data, isLoading } = useHappyHealth()

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>
    )
  }
  if (!data) return null

  const oldest = data.open_ack_backlog.oldest_deadline
    ? new Date(data.open_ack_backlog.oldest_deadline).toLocaleDateString('ro-RO')
    : '—'

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          icon={<Megaphone className="h-3.5 w-3.5" />}
          label="Campanii live"
          value={data.live_campaigns}
        />
        <StatTile
          icon={<FileCheck className="h-3.5 w-3.5" />}
          label="Confirmări restante"
          value={data.open_ack_backlog.count}
          sub={`Cea mai veche: ${oldest}`}
        />
        <StatTile icon={<Award className="h-3.5 w-3.5" />} label="Aprecieri (7 zile)" value={data.kudos_last_7d} />
        <StatTile icon={<Flag className="h-3.5 w-3.5" />} label="Aprecieri semnalate" value={data.flagged_kudos} />
      </div>

      {data.latest_pulse && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <BarChart3 className="h-4 w-4" />
              Ultimul pulse
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            <p className="text-sm font-medium">{data.latest_pulse.title}</p>
            <p className="text-xs text-muted-foreground">
              {data.latest_pulse.responses}/{data.latest_pulse.invited} răspunsuri · {data.latest_pulse.status}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

export default KpiTab
