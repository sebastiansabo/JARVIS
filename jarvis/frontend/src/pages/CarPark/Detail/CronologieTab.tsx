// CarPark vehicle Detail — "Cronologie" tab: a merged, chronological
// timeline of everything that happened to a vehicle (status changes,
// lifecycle dates, document uploads). Pure read view — the merge/sort
// happens server-side in DispoRepository.timeline(); see
// carpark/routes/documents.py's vehicle_timeline route.
import { useQuery } from '@tanstack/react-query'
import { ArrowRightLeft, Calendar, FileText, Clock, ExternalLink } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/shared/EmptyState'
import { carparkDispoApi } from '@/api/carparkDispo'
import { safeHref } from './DocumenteTab'
import {
  STATUS_LABELS,
  DOCUMENT_TYPE_LABELS,
  type VehicleStatus,
  type DocumentType,
  type TimelineEvent,
} from '@/types/carpark'

function formatDate(d: string | null): string {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('ro-RO')
}

function statusLabel(status?: string | null): string {
  if (!status) return '-'
  return STATUS_LABELS[status as VehicleStatus] ?? status
}

function documentTypeLabel(docType?: string | null): string {
  if (!docType) return '-'
  return DOCUMENT_TYPE_LABELS[docType as DocumentType] ?? docType
}

// Sort defensively client-side too, even though the backend pre-sorts —
// null/missing dates sink to the bottom instead of throwing off the order.
function sortEvents(events: TimelineEvent[]): TimelineEvent[] {
  return [...events].sort((a, b) => {
    if (!a.date && !b.date) return 0
    if (!a.date) return 1
    if (!b.date) return -1
    return new Date(a.date).getTime() - new Date(b.date).getTime()
  })
}

function EventIcon({ type }: { type: TimelineEvent['type'] }) {
  const cls = 'h-4 w-4'
  switch (type) {
    case 'status_change':
      return <ArrowRightLeft className={cls} />
    case 'vehicle_date':
      return <Calendar className={cls} />
    case 'document':
      return <FileText className={cls} />
    default:
      return <Clock className={cls} />
  }
}

function EventBody({ event }: { event: TimelineEvent }) {
  if (event.type === 'status_change') {
    const { old_status, new_status, notes } = event.meta ?? {}
    return (
      <div>
        <div className="flex items-center gap-2 text-sm font-medium">
          {old_status ? (
            <>
              <span>{statusLabel(old_status)}</span>
              <span className="text-muted-foreground">&rarr;</span>
              <span>{statusLabel(new_status)}</span>
            </>
          ) : (
            <span>{statusLabel(new_status)}</span>
          )}
        </div>
        {notes && <p className="mt-1 text-sm text-muted-foreground">{notes}</p>}
      </div>
    )
  }

  if (event.type === 'document') {
    const { document_type, title } = event.meta ?? {}
    // The backend's document event meta doesn't currently include
    // file_url (see DispoRepository.timeline) — guard for it anyway in
    // case that changes, and never render a raw href.
    const fileUrl = (event.meta as { file_url?: string | null } | undefined)?.file_url
    const href = safeHref(fileUrl)
    return (
      <div>
        <div className="text-sm font-medium">
          {documentTypeLabel(document_type)}
          {title && <span className="text-muted-foreground"> — {title}</span>}
        </div>
        {fileUrl && (
          href ? (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1 inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline"
            >
              Deschide <ExternalLink className="h-3 w-3" />
            </a>
          ) : (
            <span className="mt-1 block text-xs text-muted-foreground">Link invalid</span>
          )
        )}
      </div>
    )
  }

  // vehicle_date
  return <div className="text-sm font-medium">{event.label}</div>
}

export function CronologieTab({ vehicleId }: { vehicleId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['carpark', 'timeline', vehicleId],
    queryFn: () => carparkDispoApi.getTimeline(vehicleId),
    enabled: !!vehicleId,
  })

  // Response shape is `{ timeline: TimelineEvent[] }` (see
  // carpark/routes/documents.py's vehicle_timeline route), but stay
  // defensive against a bare-array response too rather than ever calling
  // .map on undefined.
  const raw = (data as { timeline?: TimelineEvent[] } | TimelineEvent[] | undefined) ?? []
  const events = sortEvents(Array.isArray(raw) ? raw : raw.timeline ?? [])

  if (isLoading) {
    return (
      <Card className="p-4 space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex items-start gap-3">
            <Skeleton className="h-8 w-8 rounded-full shrink-0" />
            <div className="flex-1 space-y-2 pt-1">
              <Skeleton className="h-4 w-1/3" />
              <Skeleton className="h-3 w-1/2" />
            </div>
          </div>
        ))}
      </Card>
    )
  }

  if (events.length === 0) {
    return (
      <Card className="p-4">
        <EmptyState icon={<Clock className="h-8 w-8" />} title="Nicio activitate înregistrată" />
      </Card>
    )
  }

  return (
    <Card className="p-4">
      <h3 className="text-sm font-semibold mb-4">Cronologie ({events.length})</h3>
      <ol className="relative border-l border-border ml-3.5">
        {events.map((event, i) => (
          <li key={i} className="relative mb-6 last:mb-0 pl-6">
            <span className="absolute -left-[13px] top-0.5 flex h-6 w-6 items-center justify-center rounded-full bg-muted text-muted-foreground ring-4 ring-background">
              <EventIcon type={event.type} />
            </span>
            <div className="flex items-start justify-between gap-3">
              <EventBody event={event} />
              <span className="shrink-0 text-xs text-muted-foreground whitespace-nowrap">
                {formatDate(event.date)}
              </span>
            </div>
          </li>
        ))}
      </ol>
    </Card>
  )
}

export default CronologieTab
