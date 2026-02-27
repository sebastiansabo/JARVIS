import { useState, useMemo, useRef, useEffect, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Search,
  Link2,
  Unlink,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  ArrowUpDown,
  ChevronsUpDown,
  Wand2,
  X,
  Trash2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { EmptyState } from '@/components/shared/EmptyState'
import { biostarApi } from '@/api/biostar'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import type { BioStarEmployee, JarvisUser } from '@/types/biostar'

type SortField = 'name' | 'group' | 'status'
type SortDir = 'asc' | 'desc'

export default function PontajeTab() {
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [showAll, setShowAll] = useState(false)
  const [filter, setFilter] = useState<'all' | 'mapped' | 'unmapped'>('all')
  const [sortField, setSortField] = useState<SortField>('name')
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  const { data: status } = useQuery({
    queryKey: ['biostar', 'status'],
    queryFn: biostarApi.getStatus,
  })

  const { data: employees = [], isLoading } = useQuery({
    queryKey: ['biostar', 'employees'],
    queryFn: () => biostarApi.getEmployees(true),
    enabled: !!status?.connected,
  })

  const { data: jarvisUsers = [] } = useQuery({
    queryKey: ['biostar', 'jarvisUsers'],
    queryFn: biostarApi.getJarvisUsers,
    enabled: !!status?.connected,
  })

  const mapMut = useMutation({
    mutationFn: ({ biostarUserId, jarvisUserId }: { biostarUserId: string; jarvisUserId: number }) =>
      biostarApi.updateMapping(biostarUserId, jarvisUserId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['biostar', 'employees'] })
      qc.invalidateQueries({ queryKey: ['biostar', 'status'] })
      toast.success('Mapping updated')
    },
    onError: () => toast.error('Failed to update mapping'),
  })

  const unmapMut = useMutation({
    mutationFn: (biostarUserId: string) => biostarApi.removeMapping(biostarUserId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['biostar', 'employees'] })
      qc.invalidateQueries({ queryKey: ['biostar', 'status'] })
      toast.success('Mapping removed')
    },
    onError: () => toast.error('Failed to remove mapping'),
  })

  const scheduleMut = useMutation({
    mutationFn: ({ biostarUserId, data }: { biostarUserId: string; data: { lunch_break_minutes: number; working_hours: number; schedule_start?: string; schedule_end?: string } }) =>
      biostarApi.updateSchedule(biostarUserId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['biostar', 'employees'] })
      toast.success('Schedule updated')
    },
    onError: () => toast.error('Failed to update schedule'),
  })

  // ── Selection + Bulk Edit ──
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkLunch, setBulkLunch] = useState<string>('')
  const [bulkHours, setBulkHours] = useState<string>('')
  const [bulkFrom, setBulkFrom] = useState<string>('')
  const [bulkTo, setBulkTo] = useState<string>('')

  const toggleSelect = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const toggleSelectAll = useCallback((allIds: string[]) => {
    setSelected((prev) => {
      const allSelected = allIds.length > 0 && allIds.every((id) => prev.has(id))
      if (allSelected) return new Set()
      return new Set(allIds)
    })
  }, [])

  const clearSelection = useCallback(() => {
    setSelected(new Set())
    setBulkLunch('')
    setBulkHours('')
    setBulkFrom('')
    setBulkTo('')
  }, [])

  const bulkMut = useMutation({
    mutationFn: (data: Parameters<typeof biostarApi.bulkUpdateSchedule>[0]) =>
      biostarApi.bulkUpdateSchedule(data),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['biostar', 'employees'] })
      toast.success(`Updated ${res.data?.updated ?? selected.size} employees`)
      clearSelection()
    },
    onError: () => toast.error('Bulk update failed'),
  })

  const applyBulk = () => {
    if (selected.size === 0) return
    const payload: Parameters<typeof biostarApi.bulkUpdateSchedule>[0] = {
      biostar_user_ids: Array.from(selected),
    }
    if (bulkLunch) payload.lunch_break_minutes = Number(bulkLunch)
    if (bulkHours) payload.working_hours = Number(bulkHours)
    if (bulkFrom) payload.schedule_start = bulkFrom
    if (bulkTo) payload.schedule_end = bulkTo
    if (!payload.lunch_break_minutes && !payload.working_hours && !payload.schedule_start && !payload.schedule_end) {
      toast.error('Select at least one field to update')
      return
    }
    bulkMut.mutate(payload)
  }

  const deactivateMut = useMutation({
    mutationFn: () => biostarApi.bulkDeactivate(Array.from(selected)),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['biostar', 'employees'] })
      qc.invalidateQueries({ queryKey: ['biostar', 'status'] })
      toast.success(`Deactivated ${res.data?.deactivated ?? selected.size} employees`)
      clearSelection()
    },
    onError: () => toast.error('Deactivate failed'),
  })

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDir('asc')
    }
  }

  const processed = useMemo(() => {
    let list = [...employees]

    // Filter
    if (filter === 'mapped') list = list.filter((e) => e.mapped_jarvis_user_id)
    if (filter === 'unmapped') list = list.filter((e) => !e.mapped_jarvis_user_id)

    // Search
    if (search) {
      const s = search.toLowerCase()
      list = list.filter(
        (e) =>
          e.name.toLowerCase().includes(s) ||
          (e.email || '').toLowerCase().includes(s) ||
          (e.user_group_name || '').toLowerCase().includes(s) ||
          (e.mapped_jarvis_user_name || '').toLowerCase().includes(s),
      )
    }

    // Sort
    list.sort((a, b) => {
      let cmp = 0
      if (sortField === 'name') cmp = a.name.localeCompare(b.name)
      else if (sortField === 'group') cmp = (a.user_group_name || '').localeCompare(b.user_group_name || '')
      else if (sortField === 'status') {
        const aVal = a.mapped_jarvis_user_id ? 1 : 0
        const bVal = b.mapped_jarvis_user_id ? 1 : 0
        cmp = aVal - bVal
      }
      return sortDir === 'asc' ? cmp : -cmp
    })

    return list
  }, [employees, filter, search, sortField, sortDir])

  const displayed = showAll ? processed : processed.slice(0, 50)

  if (!status?.connected) {
    return (
      <Card>
        <CardContent className="py-8">
          <EmptyState
            title="BioStar not connected"
            description="Configure the BioStar 2 connection in Settings → Connectors first."
          />
        </CardContent>
      </Card>
    )
  }

  const mappedCount = employees.filter((e) => e.mapped_jarvis_user_id).length
  const unmappedCount = employees.filter((e) => !e.mapped_jarvis_user_id).length

  const SortIcon = ({ field }: { field: SortField }) => (
    <ArrowUpDown className={cn('ml-1 h-3 w-3 inline', sortField === field ? 'opacity-100' : 'opacity-40')} />
  )

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Link2 className="h-5 w-5" />
              Pontaje — Employee Mapping
            </CardTitle>
            <CardDescription>
              Map BioStar employees to JARVIS users.
              {' '}<span className="text-green-600">{mappedCount} mapped</span>, <span className="text-orange-600">{unmappedCount} unmapped</span> of {employees.length} active.
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              className="pl-9"
              placeholder="Search by name, email, group, or JARVIS user..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <Select value={filter} onValueChange={(v) => setFilter(v as typeof filter)}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All ({employees.length})</SelectItem>
              <SelectItem value="mapped">Mapped ({mappedCount})</SelectItem>
              <SelectItem value="unmapped">Unmapped ({unmappedCount})</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : processed.length === 0 ? (
          <EmptyState title="No employees found" description={search ? 'Try a different search term.' : 'Sync users from BioStar first.'} />
        ) : (
          <>
            {/* Bulk action bar */}
            {selected.size > 0 && (
              <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border bg-muted/50 px-4 py-2.5">
                <span className="text-sm font-medium mr-1">{selected.size} selected</span>
                <Select value={bulkLunch} onValueChange={setBulkLunch}>
                  <SelectTrigger className="h-7 w-28 text-xs">
                    <SelectValue placeholder="Lunch" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="0">None</SelectItem>
                    <SelectItem value="15">15 min</SelectItem>
                    <SelectItem value="30">30 min</SelectItem>
                    <SelectItem value="45">45 min</SelectItem>
                    <SelectItem value="60">60 min</SelectItem>
                    <SelectItem value="90">90 min</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={bulkHours} onValueChange={setBulkHours}>
                  <SelectTrigger className="h-7 w-28 text-xs">
                    <SelectValue placeholder="Hours/Day" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="4">4h</SelectItem>
                    <SelectItem value="6">6h</SelectItem>
                    <SelectItem value="7">7h</SelectItem>
                    <SelectItem value="7.5">7.5h</SelectItem>
                    <SelectItem value="8">8h</SelectItem>
                    <SelectItem value="8.5">8.5h</SelectItem>
                    <SelectItem value="9">9h</SelectItem>
                    <SelectItem value="10">10h</SelectItem>
                    <SelectItem value="12">12h</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={bulkFrom} onValueChange={setBulkFrom}>
                  <SelectTrigger className="h-7 w-24 text-xs">
                    <SelectValue placeholder="From" />
                  </SelectTrigger>
                  <SelectContent>
                    {['05:00','05:30','06:00','06:30','07:00','07:30','08:00','08:30','09:00','09:30','10:00'].map((t) => (
                      <SelectItem key={t} value={t}>{t}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={bulkTo} onValueChange={setBulkTo}>
                  <SelectTrigger className="h-7 w-24 text-xs">
                    <SelectValue placeholder="To" />
                  </SelectTrigger>
                  <SelectContent>
                    {['14:00','14:30','15:00','15:30','16:00','16:30','17:00','17:30','18:00','18:30','19:00','20:00','22:00'].map((t) => (
                      <SelectItem key={t} value={t}>{t}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button size="sm" className="h-7 text-xs" onClick={applyBulk} disabled={bulkMut.isPending}>
                  <Wand2 className="mr-1 h-3 w-3" />
                  {bulkMut.isPending ? 'Applying...' : 'Apply'}
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  className="h-7 text-xs"
                  onClick={() => {
                    if (confirm(`Deactivate ${selected.size} employee(s)? They will be hidden from the list.`)) {
                      deactivateMut.mutate()
                    }
                  }}
                  disabled={deactivateMut.isPending}
                >
                  <Trash2 className="mr-1 h-3 w-3" />
                  {deactivateMut.isPending ? 'Deleting...' : 'Delete'}
                </Button>
                <Button size="sm" variant="ghost" className="h-7 w-7 p-0 ml-auto" onClick={clearSelection} title="Clear selection">
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
            )}

            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-10">
                      <Checkbox
                        checked={
                          processed.length > 0 && processed.every((e) => selected.has(e.biostar_user_id))
                            ? true
                            : selected.size > 0
                              ? 'indeterminate'
                              : false
                        }
                        onCheckedChange={() => toggleSelectAll(processed.map((e) => e.biostar_user_id))}
                      />
                    </TableHead>
                    <TableHead className="cursor-pointer select-none" onClick={() => handleSort('name')}>
                      BioStar Employee <SortIcon field="name" />
                    </TableHead>
                    <TableHead className="hidden md:table-cell cursor-pointer select-none" onClick={() => handleSort('group')}>
                      Group <SortIcon field="group" />
                    </TableHead>
                    <TableHead className="cursor-pointer select-none" onClick={() => handleSort('status')}>
                      JARVIS User <SortIcon field="status" />
                    </TableHead>
                    <TableHead className="hidden sm:table-cell">Method</TableHead>
                    <TableHead className="hidden lg:table-cell text-center w-28">Lunch</TableHead>
                    <TableHead className="hidden lg:table-cell text-center w-28">Hours/Day</TableHead>
                    <TableHead className="hidden xl:table-cell text-center w-24">From</TableHead>
                    <TableHead className="hidden xl:table-cell text-center w-24">To</TableHead>
                    <TableHead className="w-12" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {displayed.map((emp) => (
                    <EmployeeRow
                      key={emp.id}
                      employee={emp}
                      jarvisUsers={jarvisUsers}
                      selected={selected.has(emp.biostar_user_id)}
                      onToggleSelect={() => toggleSelect(emp.biostar_user_id)}
                      onMap={(jarvisUserId) =>
                        mapMut.mutate({ biostarUserId: emp.biostar_user_id, jarvisUserId })
                      }
                      onUnmap={() => unmapMut.mutate(emp.biostar_user_id)}
                      onSchedule={(data) =>
                        scheduleMut.mutate({ biostarUserId: emp.biostar_user_id, data })
                      }
                    />
                  ))}
                </TableBody>
              </Table>
            </div>
            <div className="mt-2 flex items-center justify-between text-sm text-muted-foreground">
              <span>Showing {displayed.length} of {processed.length}</span>
              {processed.length > 50 && (
                <Button variant="ghost" size="sm" onClick={() => setShowAll(!showAll)}>
                  {showAll ? (
                    <><ChevronUp className="mr-1 h-4 w-4" /> Show Less</>
                  ) : (
                    <><ChevronDown className="mr-1 h-4 w-4" /> Show All ({processed.length})</>
                  )}
                </Button>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}

// ── Searchable User Picker (Combobox) ──

function UserCombobox({
  jarvisUsers,
  biostarName,
  biostarEmail,
  onSelect,
}: {
  jarvisUsers: JarvisUser[]
  biostarName: string
  biostarEmail: string | null
  onSelect: (userId: number) => void
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 0)
    } else {
      setQuery('')
    }
  }, [open])

  // Sort users: best match first (email > name), then alphabetical
  const sorted = useMemo(() => {
    const bioLower = biostarName.toLowerCase().trim()
    const bioParts = bioLower.split(/\s+/)
    const bioEmail = (biostarEmail || '').toLowerCase().trim()

    const scored = jarvisUsers.map((u) => {
      const uLower = u.name.toLowerCase()
      const uParts = uLower.split(/\s+/)
      const uEmail = (u.email || '').toLowerCase()
      let score = 0

      // Email match — highest priority
      if (bioEmail && uEmail && bioEmail === uEmail) score = 100
      // Email prefix match (before @)
      else if (bioEmail && uEmail && bioEmail.split('@')[0] === uEmail.split('@')[0]) score = 95
      // Exact name match
      else if (uLower === bioLower) score = 90
      // All parts of one name appear in the other
      else if (bioParts.every((p) => uLower.includes(p))) score = 75
      else if (uParts.every((p) => bioLower.includes(p))) score = 75
      // Partial word overlap
      else {
        const overlap = bioParts.filter((p) => uParts.some((up) => up.includes(p) || p.includes(up)))
        score = overlap.length * 25
      }

      return { user: u, score }
    })

    scored.sort((a, b) => b.score - a.score || a.user.name.localeCompare(b.user.name))
    return scored
  }, [jarvisUsers, biostarName, biostarEmail])

  const filtered = useMemo(() => {
    if (!query) return sorted
    const q = query.toLowerCase()
    return sorted.filter(
      ({ user }) =>
        user.name.toLowerCase().includes(q) ||
        (user.email || '').toLowerCase().includes(q) ||
        (user.department || '').toLowerCase().includes(q),
    )
  }, [sorted, query])

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-8 w-52 justify-between text-xs font-normal text-muted-foreground">
          Select user...
          <ChevronsUpDown className="ml-1 h-3 w-3 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-0" align="start">
        <div className="p-2 border-b">
          <Input
            ref={inputRef}
            placeholder="Search users..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="h-8 text-sm"
          />
        </div>
        <div className="max-h-56 overflow-y-auto">
          {filtered.length === 0 ? (
            <p className="p-3 text-center text-sm text-muted-foreground">No users found</p>
          ) : (
            filtered.map(({ user, score }) => (
              <button
                key={user.id}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent transition-colors"
                onClick={() => {
                  onSelect(user.id)
                  setOpen(false)
                }}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate font-medium">{user.name}</span>
                    {score >= 80 && (
                      <span className="shrink-0 rounded bg-green-100 px-1 py-0.5 text-[10px] font-medium text-green-700 dark:bg-green-900 dark:text-green-300">
                        match
                      </span>
                    )}
                  </div>
                  {user.email && (
                    <p className="truncate text-xs text-muted-foreground">{user.email}</p>
                  )}
                </div>
              </button>
            ))
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}

// ── Employee Row ──

function EmployeeRow({
  employee,
  jarvisUsers,
  selected,
  onToggleSelect,
  onMap,
  onUnmap,
  onSchedule,
}: {
  employee: BioStarEmployee
  jarvisUsers: JarvisUser[]
  selected: boolean
  onToggleSelect: () => void
  onMap: (jarvisUserId: number) => void
  onUnmap: () => void
  onSchedule: (data: { lunch_break_minutes: number; working_hours: number; schedule_start?: string; schedule_end?: string }) => void
}) {
  const fmtTime = (t: string | null) => {
    if (!t) return '08:00'
    // DB returns "08:00:00", trim to "HH:MM"
    return t.slice(0, 5)
  }
  return (
    <TableRow className={selected ? 'bg-muted/40' : undefined}>
      <TableCell>
        <Checkbox checked={selected} onCheckedChange={onToggleSelect} />
      </TableCell>
      <TableCell>
        <div>
          <span className="font-medium">{employee.name}</span>
          {employee.email && <p className="text-xs text-muted-foreground">{employee.email}</p>}
        </div>
      </TableCell>
      <TableCell className="hidden md:table-cell text-sm text-muted-foreground">
        {employee.user_group_name || '-'}
      </TableCell>
      <TableCell>
        {employee.mapped_jarvis_user_id ? (
          <span className="flex items-center gap-1.5 text-sm">
            <CheckCircle className="h-3.5 w-3.5 text-green-600 shrink-0" />
            {employee.mapped_jarvis_user_name}
          </span>
        ) : (
          <UserCombobox
            jarvisUsers={jarvisUsers}
            biostarName={employee.name}
            biostarEmail={employee.email}
            onSelect={onMap}
          />
        )}
      </TableCell>
      <TableCell className="hidden sm:table-cell text-xs text-muted-foreground">
        {employee.mapping_method
          ? `${employee.mapping_method.replace('auto_', '')} (${employee.mapping_confidence}%)`
          : '-'}
      </TableCell>
      <TableCell className="hidden lg:table-cell">
        <Select
          value={String(employee.lunch_break_minutes ?? 60)}
          onValueChange={(v) => onSchedule({ lunch_break_minutes: Number(v), working_hours: employee.working_hours ?? 8 })}
        >
          <SelectTrigger className="h-7 w-24 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="0">None</SelectItem>
            <SelectItem value="15">15 min</SelectItem>
            <SelectItem value="30">30 min</SelectItem>
            <SelectItem value="45">45 min</SelectItem>
            <SelectItem value="60">60 min</SelectItem>
            <SelectItem value="90">90 min</SelectItem>
          </SelectContent>
        </Select>
      </TableCell>
      <TableCell className="hidden lg:table-cell">
        <Select
          value={String(Number(employee.working_hours ?? 8))}
          onValueChange={(v) => onSchedule({ lunch_break_minutes: employee.lunch_break_minutes ?? 60, working_hours: Number(v) })}
        >
          <SelectTrigger className="h-7 w-24 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="4">4h</SelectItem>
            <SelectItem value="6">6h</SelectItem>
            <SelectItem value="7">7h</SelectItem>
            <SelectItem value="7.5">7.5h</SelectItem>
            <SelectItem value="8">8h</SelectItem>
            <SelectItem value="8.5">8.5h</SelectItem>
            <SelectItem value="9">9h</SelectItem>
            <SelectItem value="10">10h</SelectItem>
            <SelectItem value="12">12h</SelectItem>
          </SelectContent>
        </Select>
      </TableCell>
      <TableCell className="hidden xl:table-cell">
        <Select
          value={fmtTime(employee.schedule_start)}
          onValueChange={(v) => onSchedule({ lunch_break_minutes: employee.lunch_break_minutes ?? 60, working_hours: employee.working_hours ?? 8, schedule_start: v })}
        >
          <SelectTrigger className="h-7 w-[5.5rem] text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {['05:00','05:30','06:00','06:30','07:00','07:30','08:00','08:30','09:00','09:30','10:00'].map((t) => (
              <SelectItem key={t} value={t}>{t}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </TableCell>
      <TableCell className="hidden xl:table-cell">
        <Select
          value={fmtTime(employee.schedule_end)}
          onValueChange={(v) => onSchedule({ lunch_break_minutes: employee.lunch_break_minutes ?? 60, working_hours: employee.working_hours ?? 8, schedule_end: v })}
        >
          <SelectTrigger className="h-7 w-[5.5rem] text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {['14:00','14:30','15:00','15:30','16:00','16:30','17:00','17:30','18:00','18:30','19:00','20:00','22:00'].map((t) => (
              <SelectItem key={t} value={t}>{t}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </TableCell>
      <TableCell>
        {employee.mapped_jarvis_user_id && (
          <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={onUnmap} title="Remove mapping">
            <Unlink className="h-3.5 w-3.5 text-muted-foreground" />
          </Button>
        )}
      </TableCell>
    </TableRow>
  )
}
