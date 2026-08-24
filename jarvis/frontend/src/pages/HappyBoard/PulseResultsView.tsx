import { EyeOff } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { PulseResults, PulseBlock, PulseQuestionScore } from '@/api/happyAdmin'

/** True when a block is below the anonymity threshold — its numbers stay hidden. */
export function isSuppressed(block: PulseBlock): boolean {
  return (block as { suppressed?: boolean }).suppressed === true
}

/** Human label for an opaque cohort key (`node:12`, `company:16`, `all`). */
export function cohortLabel(key: string): string {
  if (key === 'all') return 'Toți angajații'
  if (key.startsWith('company:')) return `Companie ${key.slice('company:'.length)}`
  if (key.startsWith('node:')) return `Departament ${key.slice('node:'.length)}`
  return key
}

/** The per-question score entries of a non-suppressed block. */
function questionScores(block: PulseBlock): [string, PulseQuestionScore][] {
  return Object.entries(block).filter(
    ([, v]) => v != null && typeof v === 'object' && 'type' in v,
  ) as [string, PulseQuestionScore][]
}

/** One question's score as a badge — eNPS gets its own label, others show the average. */
function ScoreBadge({ score }: { score: PulseQuestionScore }) {
  if (score.type === 'enps') {
    return <Badge variant="outline">eNPS {score.nps}</Badge>
  }
  return (
    <Badge variant="outline">
      {score.driver ?? 'scor'} {score.avg}
    </Badge>
  )
}

/**
 * Threshold-enforced pulse results. Suppressed blocks render a fixed hidden label
 * and NEVER their response counts or scores (spec §7.5 / §10). The data shape
 * mirrors the backend `PulseRepository.get_results` contract: `overall` is a
 * block, `cohorts` is a dict keyed by cohort_key.
 */
export function PulseResultsView({ results }: { results: PulseResults }) {
  const { participation, overall, cohorts } = results
  const noResponsesYet = participation.responses === 0
  const cohortEntries = Object.entries(cohorts ?? {})

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

      {/* Overall */}
      <div className="space-y-1">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">General</p>
        {noResponsesYet ? (
          <p className="text-sm text-muted-foreground">Încă fără răspunsuri.</p>
        ) : isSuppressed(overall) ? (
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <EyeOff className="h-3.5 w-3.5" />
            Ascuns (sub pragul de anonimat)
          </span>
        ) : (
          <div className="flex flex-wrap gap-2">
            {questionScores(overall).map(([qk, score]) => (
              <ScoreBadge key={qk} score={score} />
            ))}
          </div>
        )}
      </div>

      {/* Cohorts */}
      <div className="space-y-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Pe cohorte</p>
        {cohortEntries.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nu există cohorte de afișat.</p>
        ) : (
          cohortEntries.map(([key, block]) => (
            <div key={key} className="flex items-center justify-between rounded-md border p-3">
              <span className="text-sm font-medium">{cohortLabel(key)}</span>
              {isSuppressed(block) ? (
                <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <EyeOff className="h-3.5 w-3.5" />
                  Ascuns (sub pragul de anonimat)
                </span>
              ) : (
                <span className="flex flex-wrap items-center justify-end gap-2 text-sm">
                  {questionScores(block).map(([qk, score]) => (
                    <ScoreBadge key={qk} score={score} />
                  ))}
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
