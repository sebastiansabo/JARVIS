import { DISPO_STAGES, type VehicleStatus } from '@/types/carpark'

// Stages that are no longer "in the pipeline" for aging purposes — a sold,
// delivered, or exited vehicle stops accumulating stock-aging risk.
// Shared by the Dispo table (days_in_stock column, mobile card) and the
// Kanban board (card footer) so both read the exact same aging signal.
export const SOLD_OR_EXITED_STATUSES = new Set<VehicleStatus>(
  DISPO_STAGES.filter((s) => s.key === 'vandut' || s.key === 'livrat' || s.key === 'iesit').flatMap(
    (s) => s.statuses,
  ),
)

export function agingClass(days: number, status: VehicleStatus): string {
  if (SOLD_OR_EXITED_STATUSES.has(status)) return ''
  if (days > 90) return 'text-red-800 dark:text-red-300 font-semibold'
  if (days > 60) return 'text-red-600 dark:text-red-400 font-medium'
  if (days >= 30) return 'text-amber-600 dark:text-amber-500'
  return 'text-green-600 dark:text-green-500'
}
