import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { EmptyState } from '@/components/shared/EmptyState'
import { telemetryApi } from '@/api/telemetry'
import type { TelemetrySession, JourneyStep } from '@/api/telemetry'
import {
  BarChart3,
  Users,
  Eye,
  MousePointerClick,
  Clock,
  FileText,
  Monitor,
  Smartphone,
  ArrowRight,
  ChevronLeft,
} from 'lucide-react'

function formatDuration(seconds: number | null): string {
  if (!seconds || seconds <= 0) return '-'
  if (seconds < 60) return `${seconds}s`
  const min = Math.floor(seconds / 60)
  const sec = seconds % 60
  if (min < 60) return `${min}m ${sec}s`
  const hrs = Math.floor(min / 60)
  return `${hrs}h ${min % 60}m`
}

function formatPagePath(path: string | null): string {
  if (!path) return '-'
  return path.replace('/app/', '').replace(/\//g, ' / ') || 'Home'
}

function StatCard({ label, value, icon: Icon, sub }: { label: string; value: string | number; icon: React.ElementType; sub?: string }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-4">
        <div className="rounded-lg bg-primary/10 p-2.5">
          <Icon className="h-5 w-5 text-primary" />
        </div>
        <div className="min-w-0">
          <p className="text-2xl font-bold tabular-nums">{value}</p>
          <p className="text-xs text-muted-foreground">{label}</p>
          {sub && <p className="text-xs text-muted-foreground/70">{sub}</p>}
        </div>
      </CardContent>
    </Card>
  )
}

function DailyChart({ data }: { data: Array<{ day: string; active_users: number; events: number }> }) {
  if (!data.length) return null
  const maxUsers = Math.max(...data.map(d => d.active_users), 1)
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Daily Active Users</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-end gap-1" style={{ height: 120 }}>
          {data.map((d) => {
            const h = Math.max((d.active_users / maxUsers) * 100, 4)
            return (
              <div key={d.day} className="group relative flex-1 min-w-0">
                <div
                  className="mx-auto w-full max-w-[24px] rounded-t bg-primary/80 transition-colors group-hover:bg-primary"
                  style={{ height: `${h}%` }}
                />
                <div className="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-popover px-2 py-1 text-xs shadow opacity-0 group-hover:opacity-100 transition-opacity z-10">
                  {new Date(d.day).toLocaleDateString('ro-RO', { day: 'numeric', month: 'short' })}: {d.active_users} users, {d.events} events
                </div>
              </div>
            )
          })}
        </div>
        <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
          <span>{data.length > 0 ? new Date(data[0].day).toLocaleDateString('ro-RO', { day: 'numeric', month: 'short' }) : ''}</span>
          <span>{data.length > 0 ? new Date(data[data.length - 1].day).toLocaleDateString('ro-RO', { day: 'numeric', month: 'short' }) : ''}</span>
        </div>
      </CardContent>
    </Card>
  )
}

function JourneyView({ sessionId, onBack }: { sessionId: string; onBack: () => void }) {
  const { data: steps = [], isLoading } = useQuery({
    queryKey: ['telemetry', 'journey', sessionId],
    queryFn: () => telemetryApi.getUserJourney(sessionId),
  })

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" onClick={onBack} className="h-7 w-7">
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <div>
            <CardTitle className="text-sm">User Journey</CardTitle>
            <CardDescription className="font-mono text-xs">{sessionId}</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-8 animate-pulse rounded bg-muted" />)}</div>
        ) : steps.length === 0 ? (
          <EmptyState title="No journey data" description="No page navigation found for this session." />
        ) : (
          <div className="space-y-1">
            {steps.map((step: JourneyStep, i: number) => (
              <div key={i} className="flex items-center gap-3 rounded px-2 py-1.5 text-sm hover:bg-muted/50">
                <span className="shrink-0 text-xs tabular-nums text-muted-foreground w-16">
                  {new Date(step.client_ts).toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </span>
                {step.event_name === 'Session Started' ? (
                  <Badge variant="outline" className="text-green-600 border-green-200">Start</Badge>
                ) : step.event_name === 'Session Ended' ? (
                  <Badge variant="outline" className="text-red-600 border-red-200">End</Badge>
                ) : (
                  <ArrowRight className="h-3 w-3 text-muted-foreground shrink-0" />
                )}
                <span className="truncate font-medium">{formatPagePath(step.page_path)}</span>
                {step.duration_ms && Number(step.duration_ms) > 0 && (
                  <span className="ml-auto shrink-0 text-xs text-muted-foreground tabular-nums">
                    {formatDuration(Math.round(Number(step.duration_ms) / 1000))}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default function TelemetryTab() {
  const [days, setDays] = useState(30)
  const [view, setView] = useState<'overview' | 'sessions' | 'events'>('overview')
  const [journeySessionId, setJourneySessionId] = useState<string | null>(null)
  const [sessionsOffset, setSessionsOffset] = useState(0)
  const [eventsOffset, setEventsOffset] = useState(0)
  const [eventNameFilter, setEventNameFilter] = useState('')
  const sessionsLimit = 50
  const eventsLimit = 100

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['telemetry', 'dashboard', days],
    queryFn: () => telemetryApi.getDashboard(days),
    staleTime: 30_000,
  })

  const { data: pages = [] } = useQuery({
    queryKey: ['telemetry', 'popular-pages', days],
    queryFn: () => telemetryApi.getPopularPages(days),
    staleTime: 30_000,
  })

  const { data: actions = [] } = useQuery({
    queryKey: ['telemetry', 'popular-actions', days],
    queryFn: () => telemetryApi.getPopularActions(days),
    staleTime: 30_000,
  })

  const { data: sessions = [], isLoading: sessionsLoading } = useQuery({
    queryKey: ['telemetry', 'sessions', { limit: sessionsLimit, offset: sessionsOffset }],
    queryFn: () => telemetryApi.getSessions({ limit: sessionsLimit, offset: sessionsOffset }),
    enabled: view === 'sessions',
  })

  const { data: events = [], isLoading: eventsLoading } = useQuery({
    queryKey: ['telemetry', 'events', { limit: eventsLimit, offset: eventsOffset, event_name: eventNameFilter || undefined }],
    queryFn: () => telemetryApi.getEvents({ limit: eventsLimit, offset: eventsOffset, event_name: eventNameFilter || undefined }),
    enabled: view === 'events',
  })

  const { data: eventNames = [] } = useQuery({
    queryKey: ['telemetry', 'event-names'],
    queryFn: telemetryApi.getEventNames,
    staleTime: 5 * 60_000,
    enabled: view === 'events',
  })

  if (journeySessionId) {
    return <JourneyView sessionId={journeySessionId} onBack={() => setJourneySessionId(null)} />
  }

  return (
    <div className="space-y-4">
      {/* Header + Controls */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex gap-1">
          {(['overview', 'sessions', 'events'] as const).map((v) => (
            <Button key={v} variant={view === v ? 'default' : 'outline'} size="sm" onClick={() => setView(v)} className="capitalize">
              {v}
            </Button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Label className="text-xs">Period</Label>
          <Select value={String(days)} onValueChange={(v) => setDays(Number(v))}>
            <SelectTrigger className="h-8 w-28 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">7 days</SelectItem>
              <SelectItem value="14">14 days</SelectItem>
              <SelectItem value="30">30 days</SelectItem>
              <SelectItem value="90">90 days</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Overview */}
      {view === 'overview' && (
        <>
          {/* Stats Grid */}
          {statsLoading ? (
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
              {Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-20 animate-pulse rounded-lg bg-muted" />)}
            </div>
          ) : stats ? (
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
              <StatCard label="Unique Users" value={stats.unique_users ?? 0} icon={Users} />
              <StatCard label="Sessions" value={stats.total_sessions ?? 0} icon={BarChart3} />
              <StatCard label="Page Views" value={stats.page_views ?? 0} icon={Eye} />
              <StatCard label="Interactions" value={stats.interactions ?? 0} icon={MousePointerClick} />
              <StatCard label="Avg Session" value={formatDuration(stats.avg_session_duration)} icon={Clock} sub={`${stats.avg_pages_per_session ?? 0} pages/session`} />
            </div>
          ) : null}

          {/* Daily Active Users Chart */}
          {stats?.daily_active && <DailyChart data={stats.daily_active} />}

          {/* Two-column: Popular Pages + Popular Actions */}
          <div className="grid gap-4 lg:grid-cols-2">
            {/* Popular Pages */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm font-medium">
                  <FileText className="h-4 w-4" /> Top Pages
                </CardTitle>
              </CardHeader>
              <CardContent>
                {pages.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No page views yet.</p>
                ) : (
                  <div className="space-y-1.5">
                    {pages.slice(0, 15).map((p, i) => {
                      const maxViews = pages[0]?.view_count || 1
                      const pct = (p.view_count / maxViews) * 100
                      return (
                        <div key={p.page_path} className="group relative rounded px-2 py-1.5">
                          <div className="absolute inset-0 rounded bg-primary/5" style={{ width: `${pct}%` }} />
                          <div className="relative flex items-center gap-2 text-sm">
                            <span className="w-5 shrink-0 text-xs text-muted-foreground tabular-nums">{i + 1}</span>
                            <span className="min-w-0 truncate font-medium">{formatPagePath(p.page_path)}</span>
                            <span className="ml-auto shrink-0 tabular-nums text-xs text-muted-foreground">
                              {p.view_count} views &middot; {p.unique_users} users
                            </span>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Popular Actions */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm font-medium">
                  <MousePointerClick className="h-4 w-4" /> Top Interactions
                </CardTitle>
              </CardHeader>
              <CardContent>
                {actions.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No interactions tracked yet.</p>
                ) : (
                  <div className="space-y-1.5">
                    {actions.slice(0, 15).map((a, i) => {
                      const maxClicks = actions[0]?.click_count || 1
                      const pct = (a.click_count / maxClicks) * 100
                      return (
                        <div key={`${a.event_name}-${a.button_id}-${i}`} className="group relative rounded px-2 py-1.5">
                          <div className="absolute inset-0 rounded bg-primary/5" style={{ width: `${pct}%` }} />
                          <div className="relative flex items-center gap-2 text-sm">
                            <span className="w-5 shrink-0 text-xs text-muted-foreground tabular-nums">{i + 1}</span>
                            <span className="min-w-0 truncate font-medium">{a.button_text || a.button_id || a.event_name}</span>
                            <span className="ml-auto shrink-0 tabular-nums text-xs text-muted-foreground">
                              {a.click_count}x &middot; {a.unique_users} users
                            </span>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}

      {/* Sessions View */}
      {view === 'sessions' && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Sessions</CardTitle>
          </CardHeader>
          <CardContent>
            {sessionsLoading ? (
              <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-10 animate-pulse rounded bg-muted" />)}</div>
            ) : sessions.length === 0 ? (
              <EmptyState title="No sessions" description="No sessions recorded yet." />
            ) : (
              <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>User</TableHead>
                      <TableHead>Started</TableHead>
                      <TableHead>Duration</TableHead>
                      <TableHead>Pages</TableHead>
                      <TableHead>Events</TableHead>
                      <TableHead>Device</TableHead>
                      <TableHead>Entry</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sessions.map((s: TelemetrySession) => (
                      <TableRow key={s.id} className="cursor-pointer hover:bg-muted/50" onClick={() => setJourneySessionId(s.session_id)}>
                        <TableCell className="font-medium">{s.user_name || '-'}</TableCell>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                          {new Date(s.started_at).toLocaleString('ro-RO')}
                        </TableCell>
                        <TableCell className="tabular-nums">{formatDuration(s.duration_seconds)}</TableCell>
                        <TableCell className="tabular-nums">{s.page_views}</TableCell>
                        <TableCell className="tabular-nums">{s.event_count}</TableCell>
                        <TableCell>{s.is_mobile ? <Smartphone className="h-4 w-4 text-muted-foreground" /> : <Monitor className="h-4 w-4 text-muted-foreground" />}</TableCell>
                        <TableCell className="max-w-[140px] truncate text-xs text-muted-foreground">{formatPagePath(s.entry_page)}</TableCell>
                        <TableCell>
                          <Button variant="ghost" size="sm" className="h-6 text-xs">Journey</Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <div className="mt-4 flex items-center justify-between">
                  <Button variant="outline" size="sm" disabled={sessionsOffset === 0} onClick={() => setSessionsOffset(Math.max(0, sessionsOffset - sessionsLimit))}>Previous</Button>
                  <span className="text-xs text-muted-foreground">Showing {sessionsOffset + 1}-{sessionsOffset + sessions.length}</span>
                  <Button variant="outline" size="sm" disabled={sessions.length < sessionsLimit} onClick={() => setSessionsOffset(sessionsOffset + sessionsLimit)}>Next</Button>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      )}

      {/* Events View */}
      {view === 'events' && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-medium">Raw Events</CardTitle>
              <div className="flex items-center gap-2">
                <Select value={eventNameFilter || '__all__'} onValueChange={(v) => { setEventNameFilter(v === '__all__' ? '' : v); setEventsOffset(0) }}>
                  <SelectTrigger className="h-8 w-44 text-xs">
                    <SelectValue placeholder="All events" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__all__">All events</SelectItem>
                    {eventNames.map((n) => <SelectItem key={n} value={n}>{n}</SelectItem>)}
                  </SelectContent>
                </Select>
                {eventNameFilter && <Button variant="ghost" size="sm" className="h-8" onClick={() => setEventNameFilter('')}>Clear</Button>}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {eventsLoading ? (
              <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-10 animate-pulse rounded bg-muted" />)}</div>
            ) : events.length === 0 ? (
              <EmptyState title="No events" description="No telemetry events recorded yet." />
            ) : (
              <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Time</TableHead>
                      <TableHead>User</TableHead>
                      <TableHead>Event</TableHead>
                      <TableHead>Page</TableHead>
                      <TableHead>Properties</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {events.map((e) => (
                      <TableRow key={e.id}>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground tabular-nums">
                          {new Date(e.server_ts).toLocaleString('ro-RO')}
                        </TableCell>
                        <TableCell className="font-medium">{e.user_name || '-'}</TableCell>
                        <TableCell>
                          <Badge variant={e.event_category === 'navigation' ? 'secondary' : 'default'} className="text-xs font-mono">
                            {e.event_name}
                          </Badge>
                        </TableCell>
                        <TableCell className="max-w-[160px] truncate text-xs text-muted-foreground">{formatPagePath(e.page_path)}</TableCell>
                        <TableCell className="max-w-[200px] truncate text-xs font-mono text-muted-foreground">
                          {Object.keys(e.properties).length > 0 ? JSON.stringify(e.properties) : '-'}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <div className="mt-4 flex items-center justify-between">
                  <Button variant="outline" size="sm" disabled={eventsOffset === 0} onClick={() => setEventsOffset(Math.max(0, eventsOffset - eventsLimit))}>Previous</Button>
                  <span className="text-xs text-muted-foreground">Showing {eventsOffset + 1}-{eventsOffset + events.length}</span>
                  <Button variant="outline" size="sm" disabled={events.length < eventsLimit} onClick={() => setEventsOffset(eventsOffset + eventsLimit)}>Next</Button>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
