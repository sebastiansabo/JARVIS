import { useQuery } from '@tanstack/react-query'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { foiParcursApi } from '@/api/foiParcurs'
import type { FoiContract } from '@/types/foiParcurs'
import { sessionActionLabel } from './sessionActions'

// "Istoric" — a session's audit trail (who did what, when). Fetched on open;
// events come back newest-first. created_at is a real server timestamp, so it's
// rendered with new Date() (like the "Created" field), not naiveDate.
export default function SessionHistoryModal({ session, onClose }: {
  session: FoiContract
  onClose: () => void
}) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['fp-session-history', session.id],
    queryFn: () => foiParcursApi.getSessionHistory(session.id),
  })
  const events = data?.events ?? []

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>Istoric sesiune</DialogTitle></DialogHeader>
        <p className="text-xs text-muted-foreground">
          {session.client_name || session.advisor_name || '—'} · {session.vin}
        </p>

        {isLoading ? (
          <p className="py-6 text-sm text-muted-foreground">Se încarcă…</p>
        ) : isError ? (
          <p className="py-6 text-sm text-red-600 dark:text-red-400">Istoricul nu a putut fi încărcat.</p>
        ) : events.length === 0 ? (
          <div className="py-4 space-y-1 text-sm text-muted-foreground">
            <p>Fără istoric înregistrat pentru această sesiune.</p>
            {session.created_at && <p>Creat: {new Date(session.created_at).toLocaleString('ro-RO')}</p>}
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {events.map((ev) => (
              <li key={ev.id} className="flex items-baseline justify-between gap-3 py-2 text-sm">
                <span className="font-medium">{sessionActionLabel(ev.action)}</span>
                <span className="text-right text-xs text-muted-foreground">
                  {new Date(ev.created_at).toLocaleString('ro-RO')}
                  {ev.actor ? ` · ${ev.actor}` : ''}
                </span>
              </li>
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  )
}
