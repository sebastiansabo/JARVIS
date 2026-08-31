import { useQuery } from '@tanstack/react-query'
import { foiParcursApi } from '@/api/foiParcurs'

// Block/unblock audit trail for a car — who blocked/unblocked, when, and why.
// Shared by the lock modal ("Blocare parc auto") and the Driving Park
// car-profile expander so both render the same "Istoric blocări" list.
// Read-only; fetches on mount. created_at is a real server timestamptz, so it's
// rendered with new Date() (local tz), not naiveDate.
export function VehicleLockHistory({ vehicleId }: { vehicleId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['fp-lock-events', vehicleId],
    queryFn: () => foiParcursApi.getLockEvents(vehicleId),
  })
  // All reasons (incl. inactive) so an old event's slug still gets a label.
  const { data: reasonsData } = useQuery({
    queryKey: ['fp-lockout-reasons', 'all'],
    queryFn: () => foiParcursApi.getLockoutReasons(false),
    staleTime: 60_000,
  })
  const reasons = reasonsData?.reasons ?? []
  const reasonLabel = (slug?: string | null) => reasons.find((r) => r.slug === slug)?.label || slug || '—'
  const events = data?.events ?? []

  return (
    <div>
      <p className="mb-1.5 text-xs font-medium text-muted-foreground">Istoric blocări</p>
      {isLoading ? (
        <p className="py-1 text-sm text-muted-foreground">Se încarcă…</p>
      ) : events.length === 0 ? (
        <p className="py-1 text-sm text-muted-foreground">Fără istoric înregistrat.</p>
      ) : (
        <ul className="max-h-44 space-y-2 overflow-y-auto pr-1">
          {events.map((ev) => (
            <li key={ev.id} className="flex items-baseline justify-between gap-3 text-sm">
              <span className="flex items-baseline gap-1.5">
                <span aria-hidden>{ev.action === 'lock' ? '🔒' : '🔓'}</span>
                <span className="font-medium">{ev.action === 'lock' ? 'Blocat' : 'Deblocat'}</span>
                {ev.action === 'lock' && (
                  <span className="text-muted-foreground">
                    · {reasonLabel(ev.category)}{ev.note ? ` · ${ev.note}` : ''}
                  </span>
                )}
              </span>
              <span className="whitespace-nowrap text-right text-xs text-muted-foreground">
                {ev.actor_name || 'Sistem'} · {new Date(ev.created_at).toLocaleString('ro-RO')}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
