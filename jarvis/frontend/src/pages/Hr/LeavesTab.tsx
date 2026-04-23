import { lazy, Suspense, useMemo, useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload, RefreshCw, CheckCircle2, AlertCircle, UserPlus, Clock, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { StatCard } from '@/components/shared/StatCard'
import { EmptyState } from '@/components/shared/EmptyState'
import { SearchSelect } from '@/components/shared/SearchSelect'
import { hrApi } from '@/api/hr'
import type { CoBalanceUnmatchedRow } from '@/types/hr'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

const CoBalanceImportDialog = lazy(() => import('./CoBalanceImportDialog'))

interface Props {
  search?: string
}

interface MatchedRow {
  id: number
  user_id: number
  year: number
  company_name: string
  cnp: string | null
  nume: string | null
  prenume: string | null
  departament: string | null
  carry_prev_year: number
  carry_two_years_ago: number
  annual_cim: number
  seniority_bonus: number
  manual_adjustment: number
  total_available: number
  used_ytd: number
  current_balance: number
}

function fmtDate(s: string | null | undefined): string {
  if (!s) return '—'
  try {
    return new Date(s).toLocaleString('ro-RO', { timeZone: 'Europe/Bucharest' })
  } catch {
    return s
  }
}

export default function LeavesTab({ search = '' }: Props) {
  const qc = useQueryClient()
  const currentYear = new Date().getFullYear()
  const [year, setYear] = useState<number>(currentYear)
  const [tab, setTab] = useState<'matched' | 'unmatched'>('matched')
  const [assignRow, setAssignRow] = useState<CoBalanceUnmatchedRow | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  const toggleSelect = useCallback((id: number) => {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [])

  const toggleAll = useCallback((rows: MatchedRow[]) => {
    setSelected(prev => {
      const allIds = rows.map(r => r.id)
      const allSelected = allIds.every(id => prev.has(id))
      return allSelected ? new Set<number>() : new Set(allIds)
    })
  }, [])

  // Queries
  const balanceQuery = useQuery({
    queryKey: ['hr', 'co-balance', year],
    queryFn: () => hrApi.getCoBalance(year),
  })
  const unmatchedQuery = useQuery({
    queryKey: ['hr', 'co-balance', 'unmatched', year],
    queryFn: () => hrApi.getCoBalanceUnmatched(year),
  })
  const importsQuery = useQuery({
    queryKey: ['hr', 'co-balance', 'imports'],
    queryFn: () => hrApi.listCoBalanceImports(10),
  })
  const employeesQuery = useQuery({
    queryKey: ['hr', 'employees', 'active'],
    queryFn: () => hrApi.getEmployees(true),
  })

  const matchedRows = useMemo<MatchedRow[]>(() => {
    const data = balanceQuery.data?.data ?? {}
    const rows: MatchedRow[] = []
    for (const [key, r] of Object.entries(data)) {
      const row = r as MatchedRow
      // Ensure id exists — backend key is "userId_dbId"
      if (!row.id) {
        const parts = key.split('_')
        row.id = parseInt(parts[parts.length - 1], 10) || 0
      }
      rows.push(row)
    }
    // Sort by company, then name
    rows.sort((a, b) => {
      const c = (a.company_name || '').localeCompare(b.company_name || '')
      if (c !== 0) return c
      const an = `${a.nume || ''} ${a.prenume || ''}`.trim()
      const bn = `${b.nume || ''} ${b.prenume || ''}`.trim()
      return an.localeCompare(bn)
    })
    return rows
  }, [balanceQuery.data])

  const unmatchedRows = useMemo<CoBalanceUnmatchedRow[]>(() => {
    return unmatchedQuery.data?.data ?? []
  }, [unmatchedQuery.data])

  const filteredMatched = useMemo(() => {
    if (!search) return matchedRows
    const q = search.toLowerCase()
    return matchedRows.filter((r) => {
      const name = `${r.nume || ''} ${r.prenume || ''}`.toLowerCase()
      return (
        name.includes(q) ||
        (r.company_name || '').toLowerCase().includes(q) ||
        (r.departament || '').toLowerCase().includes(q) ||
        (r.cnp || '').includes(q)
      )
    })
  }, [matchedRows, search])

  const filteredUnmatched = useMemo(() => {
    if (!search) return unmatchedRows
    const q = search.toLowerCase()
    return unmatchedRows.filter((r) => {
      const name = `${r.nume || ''} ${r.prenume || ''}`.toLowerCase()
      return (
        name.includes(q) ||
        (r.company_name || '').toLowerCase().includes(q) ||
        (r.departament || '').toLowerCase().includes(q) ||
        (r.cnp || '').includes(q) ||
        (r.nr_contract || '').toLowerCase().includes(q)
      )
    })
  }, [unmatchedRows, search])

  // Stats
  const totalRows = matchedRows.length + unmatchedRows.length
  const matchedCount = matchedRows.length
  const unmatchedCount = unmatchedRows.length
  const matchPct = totalRows > 0 ? Math.round((matchedCount / totalRows) * 100) : 0
  const totalDays = matchedRows.reduce((s, r) => s + (r.total_available || 0), 0)
  const usedDays = matchedRows.reduce((s, r) => s + (r.used_ytd || 0), 0)
  const remainingDays = matchedRows.reduce((s, r) => s + (r.current_balance || 0), 0)
  const lastImport = importsQuery.data?.data?.[0]

  // Assign mutation
  const assignMut = useMutation({
    mutationFn: ({ rowId, userId }: { rowId: number; userId: number }) =>
      hrApi.assignCoBalanceUser(rowId, userId),
    onSuccess: () => {
      toast.success('Employee assigned')
      setAssignRow(null)
      qc.invalidateQueries({ queryKey: ['hr', 'co-balance'] })
      qc.invalidateQueries({ queryKey: ['hr', 'employees', 'work-stats'] })
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : 'Assignment failed'
      toast.error(msg)
    },
  })

  const deleteMut = useMutation({
    mutationFn: (ids: number[]) => hrApi.deleteCoBalanceRows(ids),
    onSuccess: (_, ids) => {
      toast.success(`${ids.length} row(s) deleted`)
      setSelected(new Set())
      setShowDeleteConfirm(false)
      qc.invalidateQueries({ queryKey: ['hr', 'co-balance'] })
    },
    onError: (e: unknown) => {
      toast.error(e instanceof Error ? e.message : 'Delete failed')
    },
  })

  function refetchAll() {
    balanceQuery.refetch()
    unmatchedQuery.refetch()
    importsQuery.refetch()
  }

  const isLoading = balanceQuery.isLoading || unmatchedQuery.isLoading
  const hasData = totalRows > 0

  return (
    <div className="space-y-4">
      {/* Toolbar: year + actions */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Label htmlFor="leaves-year" className="text-sm">Year</Label>
          <Input
            id="leaves-year"
            type="number"
            value={year}
            onChange={(e) => { setYear(parseInt(e.target.value || String(currentYear), 10)); setSelected(new Set()) }}
            min={2000}
            max={2100}
            className="h-9 w-24"
          />
          {lastImport && (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Clock className="h-3.5 w-3.5" />
              Last import: {fmtDate(lastImport.finished_at || lastImport.started_at)}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {selected.size > 0 && (
            <Button variant="destructive" size="sm" onClick={() => setShowDeleteConfirm(true)}>
              <Trash2 className="mr-1.5 h-4 w-4" />
              Delete ({selected.size})
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={refetchAll} disabled={isLoading}>
            <RefreshCw className={cn('mr-1.5 h-4 w-4', isLoading && 'animate-spin')} />
            Refresh
          </Button>
          <Suspense fallback={null}>
            <CoBalanceImportDialog
              defaultYear={year}
              onComplete={refetchAll}
              trigger={
                <Button size="sm">
                  <Upload className="mr-1.5 h-4 w-4" />
                  Import xlsx
                </Button>
              }
            />
          </Suspense>
        </div>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <StatCard
          title="Total Rows"
          value={isLoading ? '—' : totalRows}
          description={hasData ? `${matchedCount} matched · ${unmatchedCount} unmatched` : 'No data imported'}
        />
        <StatCard
          title="Match Rate"
          value={isLoading ? '—' : `${matchPct}%`}
          description={`${matchedCount} of ${totalRows || '—'}`}
          className={cn(!isLoading && unmatchedCount === 0 && totalRows > 0 && 'border-green-500/50')}
        />
        <StatCard
          title="Total CO Days"
          value={isLoading ? '—' : totalDays}
          description={`${usedDays} used · ${remainingDays} remaining`}
        />
        <StatCard
          title="Last Import"
          value={lastImport ? (lastImport.rows_matched + lastImport.rows_unmatched) : '—'}
          description={
            lastImport
              ? `${lastImport.source_file?.slice(0, 30) ?? ''} · ${lastImport.rows_matched}/${lastImport.rows_matched + lastImport.rows_unmatched}`
              : 'Never'
          }
        />
      </div>

      {!hasData && !isLoading ? (
        <Card>
          <CardContent className="py-12">
            <EmptyState
              icon={<Upload className="h-10 w-10" />}
              title={`No CO balance data for ${year}`}
              description="Upload HR's Raport_concedii_contracte_lunar xlsx files to get started."
              action={
                <Suspense fallback={null}>
                  <CoBalanceImportDialog
                    defaultYear={year}
                    onComplete={refetchAll}
                    trigger={
                      <Button>
                        <Upload className="mr-1.5 h-4 w-4" />
                        Import files
                      </Button>
                    }
                  />
                </Suspense>
              }
            />
          </CardContent>
        </Card>
      ) : (
        <Tabs value={tab} onValueChange={(v) => setTab(v as 'matched' | 'unmatched')}>
          <TabsList>
            <TabsTrigger value="matched">
              <CheckCircle2 className="mr-1.5 h-3.5 w-3.5 text-green-600" />
              Matched ({matchedCount})
            </TabsTrigger>
            <TabsTrigger value="unmatched">
              <AlertCircle className={cn('mr-1.5 h-3.5 w-3.5', unmatchedCount > 0 ? 'text-amber-600' : 'text-muted-foreground')} />
              Unmatched ({unmatchedCount})
            </TabsTrigger>
          </TabsList>

          {tab === 'matched' ? (
            <Card className="mt-3">
              <CardContent className="p-0">
                {isLoading ? (
                  <div className="space-y-2 p-4">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <Skeleton key={i} className="h-10 w-full" />
                    ))}
                  </div>
                ) : filteredMatched.length === 0 ? (
                  <div className="py-8 text-center text-sm text-muted-foreground">
                    {search ? 'No matches.' : 'All imported rows are unmatched.'}
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="w-10 px-2">
                            <Checkbox
                              checked={filteredMatched.length > 0 && filteredMatched.every(r => selected.has(r.id))}
                              onCheckedChange={() => toggleAll(filteredMatched)}
                            />
                          </TableHead>
                          <TableHead>Name</TableHead>
                          <TableHead>Company</TableHead>
                          <TableHead>Department</TableHead>
                          <TableHead className="text-right">Carry Prev</TableHead>
                          <TableHead className="text-right">Carry 2y</TableHead>
                          <TableHead className="text-right">CIM</TableHead>
                          <TableHead className="text-right">Vechime</TableHead>
                          <TableHead className="text-right">Adj</TableHead>
                          <TableHead className="text-right font-semibold">Total</TableHead>
                          <TableHead className="text-right text-muted-foreground">Used YTD</TableHead>
                          <TableHead className="text-right font-semibold">Remaining</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {filteredMatched.map((r) => (
                          <TableRow key={`${r.user_id}-${r.company_name}-${r.year}`} className={cn(selected.has(r.id) && 'bg-muted/50')}>
                            <TableCell className="px-2">
                              <Checkbox
                                checked={selected.has(r.id)}
                                onCheckedChange={() => toggleSelect(r.id)}
                              />
                            </TableCell>
                            <TableCell className="font-medium">
                              {[r.nume, r.prenume].filter(Boolean).join(' ') || `user #${r.user_id}`}
                            </TableCell>
                            <TableCell className="text-xs text-muted-foreground">{r.company_name}</TableCell>
                            <TableCell className="text-xs text-muted-foreground">{r.departament || '—'}</TableCell>
                            <TableCell className="text-right tabular-nums">{r.carry_prev_year}</TableCell>
                            <TableCell className="text-right tabular-nums">{r.carry_two_years_ago}</TableCell>
                            <TableCell className="text-right tabular-nums">{r.annual_cim}</TableCell>
                            <TableCell className="text-right tabular-nums">{r.seniority_bonus}</TableCell>
                            <TableCell className="text-right tabular-nums">{r.manual_adjustment}</TableCell>
                            <TableCell className="text-right font-semibold tabular-nums">{r.total_available}</TableCell>
                            <TableCell className="text-right tabular-nums text-muted-foreground">{r.used_ytd}</TableCell>
                            <TableCell
                              className={cn(
                                'text-right font-semibold tabular-nums',
                                r.current_balance < 0 && 'text-red-600',
                              )}
                            >
                              {r.current_balance}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </CardContent>
            </Card>
          ) : (
            <Card className="mt-3">
              <CardContent className="p-0">
                {isLoading ? (
                  <div className="space-y-2 p-4">
                    {Array.from({ length: 3 }).map((_, i) => (
                      <Skeleton key={i} className="h-10 w-full" />
                    ))}
                  </div>
                ) : filteredUnmatched.length === 0 ? (
                  <div className="py-8 text-center text-sm text-muted-foreground">
                    {search ? 'No matches.' : 'All imported rows are matched. '}
                    {!search && <CheckCircle2 className="ml-1 inline h-4 w-4 text-green-600" />}
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Last Name</TableHead>
                          <TableHead>First Name</TableHead>
                          <TableHead>CNP</TableHead>
                          <TableHead>Company</TableHead>
                          <TableHead>Department</TableHead>
                          <TableHead>Contract</TableHead>
                          <TableHead className="text-right">Total</TableHead>
                          <TableHead className="text-right">Action</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {filteredUnmatched.map((r) => (
                          <TableRow key={r.id}>
                            <TableCell className="font-medium">{r.nume || '—'}</TableCell>
                            <TableCell className="font-medium">{r.prenume || '—'}</TableCell>
                            <TableCell className="text-xs font-mono text-muted-foreground">{r.cnp || '—'}</TableCell>
                            <TableCell className="text-xs">{r.company_name}</TableCell>
                            <TableCell className="text-xs text-muted-foreground">{r.departament || '—'}</TableCell>
                            <TableCell className="text-xs text-muted-foreground">{r.nr_contract || '—'}</TableCell>
                            <TableCell className="text-right tabular-nums">{r.total_available}</TableCell>
                            <TableCell className="text-right">
                              <Button size="sm" variant="outline" onClick={() => setAssignRow(r)}>
                                <UserPlus className="mr-1.5 h-3.5 w-3.5" />
                                Assign
                              </Button>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </Tabs>
      )}

      {/* Assign user dialog */}
      <AssignDialog
        row={assignRow}
        employees={employeesQuery.data ?? []}
        onClose={() => setAssignRow(null)}
        onAssign={(userId) => {
          if (assignRow) assignMut.mutate({ rowId: assignRow.id, userId })
        }}
        isPending={assignMut.isPending}
      />

      {/* Delete confirmation dialog */}
      <Dialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete {selected.size} row(s)?</DialogTitle>
            <DialogDescription>
              This will permanently remove the selected CO balance rows. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowDeleteConfirm(false)} disabled={deleteMut.isPending}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteMut.mutate(Array.from(selected))}
              disabled={deleteMut.isPending}
            >
              {deleteMut.isPending ? 'Deleting…' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

interface AssignDialogProps {
  row: CoBalanceUnmatchedRow | null
  employees: { id: number; name: string; email: string | null; company: string | null; departments: string | null }[]
  onClose: () => void
  onAssign: (userId: number) => void
  isPending: boolean
}

function AssignDialog({ row, employees, onClose, onAssign, isPending }: AssignDialogProps) {
  const [selected, setSelected] = useState<string>('')

  const options = useMemo(
    () =>
      employees.map((e) => ({
        value: String(e.id),
        label: e.name,
        sublabel: [e.company, e.departments].filter(Boolean).join(' · ') || e.email || '',
      })),
    [employees],
  )

  return (
    <Dialog
      open={!!row}
      onOpenChange={(next) => {
        if (!next) {
          setSelected('')
          onClose()
        }
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Assign employee</DialogTitle>
          <DialogDescription>
            Map this CO balance row to an existing JARVIS user. Matching is by CNP on re-import;
            manual assignment is saved until the next file is uploaded.
          </DialogDescription>
        </DialogHeader>
        {row && (
          <div className="space-y-3">
            <div className="rounded-md border bg-muted/30 p-3 text-xs">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <span className="text-muted-foreground">Name: </span>
                  <span className="font-medium">{[row.nume, row.prenume].filter(Boolean).join(' ') || '—'}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">CNP: </span>
                  <span className="font-mono">{row.cnp || '—'}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Company: </span>
                  <span>{row.company_name}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Dept: </span>
                  <span>{row.departament || '—'}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Contract: </span>
                  <span>{row.nr_contract || '—'}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Total CO: </span>
                  <span className="font-semibold">{row.total_available}d</span>
                </div>
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">JARVIS employee</Label>
              <SearchSelect
                value={selected}
                onValueChange={setSelected}
                options={options}
                placeholder="Search employee..."
                searchPlaceholder="Type name, company or email..."
              />
            </div>
          </div>
        )}
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={isPending}>Cancel</Button>
          <Button onClick={() => selected && onAssign(Number(selected))} disabled={!selected || isPending}>
            {isPending ? 'Assigning…' : 'Assign'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
