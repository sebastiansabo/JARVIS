import type { CampaignFunnel } from '@/api/happyAdmin'

interface Step {
  key: keyof CampaignFunnel
  label: string
}

const STEPS: Step[] = [
  { key: 'targeted', label: 'Vizați' },
  { key: 'reached', label: 'Ajunși' },
  { key: 'read_8s', label: 'Citit (≥8s)' },
  { key: 'clicked', label: 'Click' },
  { key: 'acknowledged', label: 'Confirmat' },
]

/** Reach funnel: absolute numbers + % of the targeted base. No per-person data. */
export function ReachFunnel({ funnel }: { funnel: CampaignFunnel }) {
  const base = funnel.targeted || 0
  const pct = (n: number) => (base > 0 ? Math.round((n / base) * 100) : 0)

  return (
    <div className="space-y-2">
      {STEPS.map((s) => {
        const n = funnel[s.key] ?? 0
        const p = pct(n)
        return (
          <div key={s.key} className="space-y-1">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">{s.label}</span>
              <span className="font-medium">
                {n} <span className="text-muted-foreground">({p}%)</span>
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(p, 100)}%` }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default ReachFunnel
