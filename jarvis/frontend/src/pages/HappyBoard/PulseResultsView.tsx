import { EyeOff } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { PulseResults, PulseCohort } from '@/api/happyAdmin'

/** True when a cohort is below the anonymity threshold — its numbers must be hidden. */
export function isSuppressed(cohort: PulseCohort): boolean {
  return cohort.suppressed === true
}

function cohortLabel(cohort: PulseCohort): string {
  return cohort.label ?? cohort.key ?? 'Cohortă'
}

/**
 * Threshold-enforced pulse results. Suppressed cohorts render a fixed hidden
 * label and NEVER their response counts or scores (spec §7.5 / §10).
 */
export function PulseResultsView({ results }: { results: PulseResults }) {
  const { participation, overall, cohorts } = results

  return (
    <div className="space-y-4">
      {/* Participation */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-lg border p-3 text-center">
          <p className="text-xl font-semibold">{participation.responses}</p>
          <p className="text-xs text-muted-foreground">Răspunsuri</p>
        </div>
        <div className="rounded-lg border p-3 text-center">
          <p className="text-xl font-semibold">{participation.invited}</p>
          <p className="text-xs text-muted-foreground">Invitați</p>
        </div>
        <div className="rounded-lg border p-3 text-center">
          <p className="text-xl font-semibold">{Math.round((participation.rate ?? 0) * 100)}%</p>
          <p className="text-xs text-muted-foreground">Participare</p>
        </div>
      </div>

      {/* Overall scores */}
      {overall && Object.keys(overall).length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">General</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(overall).map(([k, v]) => (
              <Badge key={k} variant="secondary">
                {k}: {typeof v === 'number' ? v.toFixed(1) : String(v)}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {/* Cohorts */}
      <div className="space-y-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Pe cohorte</p>
        {cohorts.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nu există cohorte de afișat.</p>
        ) : (
          cohorts.map((c, i) => (
            <div key={c.key ?? i} className="flex items-center justify-between rounded-md border p-3">
              <span className="text-sm font-medium">{cohortLabel(c)}</span>
              {isSuppressed(c) ? (
                <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <EyeOff className="h-3.5 w-3.5" />
                  Ascuns (sub pragul de anonimat)
                </span>
              ) : (
                <span className="flex items-center gap-3 text-sm">
                  <span className="text-muted-foreground">
                    {c.n ?? 0} răsp.
                  </span>
                  {typeof c.enps === 'number' && (
                    <Badge variant="outline">eNPS {c.enps}</Badge>
                  )}
                </span>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export default PulseResultsView
