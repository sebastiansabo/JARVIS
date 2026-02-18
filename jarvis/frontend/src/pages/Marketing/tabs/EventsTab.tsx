import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Plus, Trash2, Search } from 'lucide-react'
import { marketingApi } from '@/api/marketing'
import type { HrEventSearchResult } from '@/types/marketing'
import { fmtDate } from './utils'

export function EventsTab({ projectId }: { projectId: number }) {
  const queryClient = useQueryClient()
  const [showLink, setShowLink] = useState(false)
  const [eventSearch, setEventSearch] = useState('')
  const [eventResults, setEventResults] = useState<HrEventSearchResult[]>([])
  const [isSearching, setIsSearching] = useState(false)

  const { data } = useQuery({
    queryKey: ['mkt-project-events', projectId],
    queryFn: () => marketingApi.getProjectEvents(projectId),
  })
  const events = data?.events ?? []

  const linkMut = useMutation({
    mutationFn: (eventId: number) => marketingApi.linkEvent(projectId, eventId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-project-events', projectId] })
      setShowLink(false)
      setEventSearch('')
      setEventResults([])
    },
  })

  const unlinkMut = useMutation({
    mutationFn: (eventId: number) => marketingApi.unlinkEvent(projectId, eventId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mkt-project-events', projectId] }),
  })

  async function searchEvents(q: string) {
    setEventSearch(q)
    if (q.length < 2) { setEventResults([]); return }
    setIsSearching(true)
    try {
      const res = await marketingApi.searchHrEvents(q)
      setEventResults(res?.events ?? [])
    } catch { setEventResults([]) }
    setIsSearching(false)
  }

  const linkedIds = new Set(events.map((e) => e.event_id))

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => { setShowLink(true); setEventSearch(''); setEventResults([]) }}>
          <Plus className="h-3.5 w-3.5 mr-1.5" /> Link Event
        </Button>
      </div>

      {events.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">No HR events linked.</div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Event</TableHead>
                <TableHead>Company</TableHead>
                <TableHead>Start</TableHead>
                <TableHead>End</TableHead>
                <TableHead>Linked By</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.map((e) => (
                <TableRow key={e.id}>
                  <TableCell>
                    <div>
                      <div className="text-sm font-medium">{e.event_name}</div>
                      {e.event_description && (
                        <div className="text-xs text-muted-foreground truncate max-w-[250px]">{e.event_description}</div>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">{e.event_company ?? '—'}</TableCell>
                  <TableCell className="text-sm">{fmtDate(e.event_start_date)}</TableCell>
                  <TableCell className="text-sm">{fmtDate(e.event_end_date)}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{e.linked_by_name}</TableCell>
                  <TableCell>
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => unlinkMut.mutate(e.event_id)}>
                      <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Link Event Dialog */}
      <Dialog open={showLink} onOpenChange={setShowLink}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Link HR Event</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                className="pl-9"
                placeholder="Search events by name, company..."
                value={eventSearch}
                onChange={(e) => searchEvents(e.target.value)}
                autoFocus
              />
            </div>
            {isSearching && <div className="text-center text-sm text-muted-foreground py-2">Searching...</div>}
            {eventResults.length > 0 && (
              <div className="rounded-md border max-h-64 overflow-y-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Event</TableHead>
                      <TableHead>Company</TableHead>
                      <TableHead>Dates</TableHead>
                      <TableHead className="w-10" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {eventResults.map((ev) => (
                      <TableRow key={ev.id}>
                        <TableCell>
                          <div className="text-sm font-medium">{ev.name}</div>
                          {ev.description && <div className="text-xs text-muted-foreground truncate max-w-[200px]">{ev.description}</div>}
                        </TableCell>
                        <TableCell className="text-sm">{ev.company ?? '—'}</TableCell>
                        <TableCell className="text-sm">{fmtDate(ev.start_date)} — {fmtDate(ev.end_date)}</TableCell>
                        <TableCell>
                          {linkedIds.has(ev.id) ? (
                            <Badge variant="secondary" className="text-xs">Linked</Badge>
                          ) : (
                            <Button size="sm" variant="outline" className="h-7"
                              disabled={linkMut.isPending}
                              onClick={() => linkMut.mutate(ev.id)}>
                              Link
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
            {eventSearch.length >= 2 && !isSearching && eventResults.length === 0 && (
              <div className="text-center text-sm text-muted-foreground py-4">No events found.</div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
