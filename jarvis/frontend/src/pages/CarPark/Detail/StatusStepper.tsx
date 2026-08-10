// CarPark vehicle Detail — compact horizontal pipeline stepper. Shows the
// main sales pipeline (see DISPO_STAGES in @/types/carpark, which mirrors
// DispoRepository.STAGE_STATUS_MAP exactly) and highlights where the
// vehicle's current `status` sits. IEȘIT (returned/scrapped/transferred/
// insurance claim) is an off-path terminal state, not a rung on the ladder
// — it's rendered as a distinct badge instead of forced into the line.
import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { DISPO_STAGES } from '@/types/carpark'

// Ordered main pipeline — every DISPO_STAGES entry except the 'Toate'
// pseudo-stage and the off-path 'iesit' terminal state.
const MAIN_STAGES = DISPO_STAGES.filter((s) => s.key !== '' && s.key !== 'iesit')

export function StatusStepper({ status }: { status: string }) {
  // Which DISPO_STAGES entry (other than 'Toate') this status belongs to.
  // Defensive: an unmapped status simply yields `undefined` below, and every
  // step renders muted rather than throwing.
  const currentStage = DISPO_STAGES.find(
    (s) => s.key !== '' && (s.statuses as readonly string[]).includes(status),
  )
  const isExited = currentStage?.key === 'iesit'
  const currentIndex =
    currentStage && !isExited ? MAIN_STAGES.findIndex((s) => s.key === currentStage.key) : -1

  return (
    <div className="w-full overflow-x-auto pb-1">
      <ol className="flex min-w-max items-center">
        {MAIN_STAGES.map((stage, i) => {
          const isCompleted = !isExited && currentIndex >= 0 && i < currentIndex
          const isActive = !isExited && i === currentIndex

          return (
            <li key={stage.key} className="flex items-center">
              <div className="flex flex-col items-center gap-1 px-1.5">
                <div
                  className={cn(
                    'flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold transition-colors',
                    isCompleted && 'bg-primary text-primary-foreground',
                    isActive && 'bg-primary text-primary-foreground ring-4 ring-primary/20',
                    !isCompleted && !isActive && 'bg-muted text-muted-foreground',
                  )}
                >
                  {isCompleted ? <Check className="h-3.5 w-3.5" /> : i + 1}
                </div>
                <span
                  className={cn(
                    'whitespace-nowrap text-[11px] font-medium',
                    isActive ? 'text-foreground' : 'text-muted-foreground',
                  )}
                >
                  {stage.label}
                </span>
              </div>
              {i < MAIN_STAGES.length - 1 && (
                <div
                  aria-hidden
                  className={cn(
                    'mb-4 h-0.5 w-6 shrink-0 rounded-full transition-colors sm:w-8',
                    isCompleted ? 'bg-primary' : 'bg-muted',
                  )}
                />
              )}
            </li>
          )
        })}
        {isExited && (
          <li className="ml-2 flex shrink-0 items-center border-l border-border pl-3">
            <Badge variant="destructive" className="text-[11px]">
              Ieșit
            </Badge>
          </li>
        )}
      </ol>
    </div>
  )
}

export default StatusStepper
