import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/shared/EmptyState'
import { usersApi } from '@/api/users'
import type { AuditEvent } from '@/types/users'

export default function ActivityTab() {
  const [eventType, setEventType] = useState('')
  const limit = 100
  const [offset, setOffset] = useState(0)

  const { data: events = [], isLoading } = useQuery({
    queryKey: ['settings', 'events', { event_type: eventType || undefined, limit, offset }],
    queryFn: () => usersApi.getEvents({ event_type: eventType || undefined, limit, offset }),
  })

  const { data: eventTypes = [] } = useQuery({
    queryKey: ['settings', 'eventTypes'],
    queryFn: usersApi.getEventTypes,
    staleTime: 10 * 60_000,
  })

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Activity Log</CardTitle>
          <span className="text-sm text-muted-foreground">{events.length} events</span>
        </div>
      </CardHeader>
      <CardContent>
        {/* Filters */}
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <div className="grid gap-1">
            <Label className="text-xs">Event Type</Label>
            <Select value={eventType || '__all__'} onValueChange={(v) => { setEventType(v === '__all__' ? '' : v); setOffset(0) }}>
              <SelectTrigger className="h-8 w-48 text-xs">
                <SelectValue placeholder="All types" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">All types</SelectItem>
                {eventTypes.map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {eventType && (
            <Button variant="ghost" size="sm" onClick={() => setEventType('')}>
              Clear
            </Button>
          )}
        </div>

        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : events.length === 0 ? (
          <EmptyState title="No events" description="No activity recorded yet." />
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Timestamp</TableHead>
                  <TableHead>User</TableHead>
                  <TableHead>Event Type</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead>Entity</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {events.map((event: AuditEvent) => (
                  <TableRow key={event.id}>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {new Date(event.created_at).toLocaleString('ro-RO')}
                    </TableCell>
                    <TableCell className="font-medium">{event.user_name || '-'}</TableCell>
                    <TableCell>
                      <span className="rounded bg-muted px-1.5 py-0.5 text-xs font-mono">{event.event_type}</span>
                    </TableCell>
                    <TableCell className="max-w-xs truncate text-sm">{event.event_description || '-'}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{event.entity_type || '-'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            {/* Pagination */}
            <div className="mt-4 flex items-center justify-between">
              <Button
                variant="outline"
                size="sm"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - limit))}
              >
                Previous
              </Button>
              <span className="text-xs text-muted-foreground">
                Showing {offset + 1}-{offset + events.length}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={events.length < limit}
                onClick={() => setOffset(offset + limit)}
              >
                Next
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
