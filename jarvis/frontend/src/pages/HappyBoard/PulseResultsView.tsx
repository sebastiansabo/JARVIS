import { useState } from 'react'
import { ChevronRight, EyeOff } from 'lucide-react'
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

/** A revealed block's representative response count (max across its questions) — for sorting. */
function blockResponseCount(block: PulseBlock): number {
  return questionScores(block).reduce((m, [, s]) => Math.max(m, s.n), 0)
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

/** The overall roll-up — the headline number(s) at the top of the report. */
function OverallSummary({ block, noResponsesYet }: { block: PulseBlock; noResponsesYet: boolean }) {
  if (noResponsesYet) {
    return <p className="text-sm text-muted-foreground">Încă fără răspunsuri.</p>
  }
  if (isSuppressed(block)) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <EyeOff className="h-3.5 w-3.5" />
        Ascuns (sub pragul de anonimat)
      </span>
    )
  }
  const scores = questionScores(block)
  return (
    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
      {scores.map(([qk, s]) =>
        s.type === 'enps' ? (
          <div key={qk} className="flex items-baseline gap-1.5">
            <span className="text-2xl font-semibold tabular-nums">{s.nps}</span>
            <span className="text-xs text-muted-foreground">eNPS · {s.n} răsp.</span>
          </div>
        ) : (
          <div key={qk} className="flex items-baseline gap-1.5">
            <span className="text-2xl font-semibold tabular-nums">{s.avg}</span>
            <span className="text-xs text-muted-foreground">{s.driver ?? 'scor'} · {s.n} răsp.</span>
          </div>
        ),
      )}
    </div>
  )
}

/**
 * Threshold-enforced pulse results, summary-first. Overall roll-up headlines the
 * report; revealed cohorts sort by response count; suppressed cohorts collapse
 * into a single count so the list stays readable at 50–100 responses. Suppressed
 * blocks NEVER expose their counts or scores (spec §7.5 / §10). Data shape mirrors
 * the backend `PulseRepository.get_results` contract (`cohorts` is a dict).
 */
export function PulseResultsView({ results }: { results: PulseResults }) {
  const { participation, overall, cohorts } = results
  const [showHidden, setShowHidden] = useState(false)
  const noResponsesYet = participation.responses === 0

  const entries = Object.entries(cohorts ?? {})
  const revealed = entries
    .filter(([, b]) => !isSuppressed(b))
    .sort((a, b) => blockResponseCount(b[1]) - blockResponseCount(a[1])) // most responses first
  const hidden = entries.filter(([, b]) => isSuppressed(b))

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

      {/* Overall — headline */}
      <div className="space-y-1">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">General</p>
        <OverallSummary block={overall} noResponsesYet={noResponsesYet} />
      </div>

      {/* Cohorts */}
      <div className="space-y-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Pe cohorte</p>
        {entries.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nu există cohorte de afișat.</p>
        ) : (
          <>
            {revealed.map(([key, block]) => (
              <div key={key} className="flex items-center justify-between rounded-md border p-3">
                <span className="text-sm font-medium">{cohortLabel(key)}</span>
                <span className="flex flex-wrap items-center justify-end gap-2 text-sm">
                  {questionScores(block).map(([qk, score]) => (
                    <ScoreBadge key={qk} score={score} />
                  ))}
                </span>
              </div>
            ))}

            {hidden.length > 0 && (
              <div className="rounded-md border">
                <button
                  type="button"
                  onClick={() => setShowHidden((v) => !v)}
                  className="flex w-full items-center gap-1.5 p-3 text-left text-xs text-muted-foreground hover:text-foreground"
                >
                  <ChevronRight className={`h-3.5 w-3.5 transition-transform ${showHidden ? 'rotate-90' : ''}`} />
                  <EyeOff className="h-3.5 w-3.5" />
                  {hidden.length === 1
                    ? '1 cohortă ascunsă (sub prag)'
                    : `${hidden.length} cohorte ascunse (sub prag)`}
                </button>
                {showHidden && (
                  <ul className="border-t px-3 py-2 text-xs text-muted-foreground">
                    {hidden.map(([key]) => (
                      <li key={key} className="flex items-center justify-between py-1">
                        <span>{cohortLabel(key)}</span>
                        <span className="flex items-center gap-1.5">
                          <EyeOff className="h-3 w-3" />
                          Ascuns (sub pragul de anonimat)
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {revealed.length === 0 && hidden.length > 0 && (
              <p className="text-xs text-muted-foreground">
                Toate cohortele sunt încă sub pragul de anonimat.
              </p>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default PulseResultsView
