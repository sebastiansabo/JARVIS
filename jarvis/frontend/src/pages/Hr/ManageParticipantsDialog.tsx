import { useState, useEffect, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Search, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { DateField } from '@/components/ui/date-field'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { hrApi } from '@/api/hr'
import { marketingApi } from '@/api/marketing'
import { toast } from 'sonner'
import type { HrEvent, HrEmployee } from '@/types/hr'
import { participantToRow, diffParticipantRows, type ParticipantRow } from './manageParticipants'

interface Props {
  open: boolean
  eventId: number
  event: HrEvent
  canAddBonus: boolean
  canDeleteBonus: boolean
  canViewAmounts: boolean
  onClose: () => void
}

function errorMessage(e: unknown): string {
  const data = (e as { data?: { error?: unknown } } | null)?.data
  if (data && typeof data.error === 'string') return data.error
  if (e instanceof Error) return e.message
  return 'Failed to save participants'
}

export default function ManageParticipantsDialog({
  open, eventId, event, canAddBonus, canDeleteBonus, canViewAmounts, onClose,
}: Props) {
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['event-participants', eventId],
    queryFn: () => marketingApi.getEventParticipants(eventId),
    enabled: open,
  })
  const original = useMemo(() => data?.participants ?? [], [data])

  const { data: bonusTypes = [] } = useQuery({
    queryKey: ['hr-bonus-types-active'],
    queryFn: () => hrApi.getBonusTypes(true),
    staleTime: 5 * 60_000,
    enabled: open,
  })

  const [rows, setRows] = useState<ParticipantRow[]>([])
  useEffect(() => {
    if (data?.participants) setRows(data.participants.map(participantToRow))
  }, [data])

  // Defaults for newly added rows, derived from the event's start date.
  const [defYear, defMonth] = useMemo(() => {
    const d = event.start_date ? new Date(event.start_date) : null
    if (d && !isNaN(d.getTime())) return [d.getFullYear(), d.getMonth() + 1]
    const now = new Date()
    return [now.getFullYear(), now.getMonth() + 1]
  }, [event.start_date])

  // Employee search (adding participants)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<HrEmployee[]>([])
  const [searching, setSearching] = useState(false)

  const handleSearch = async (q: string) => {
    setSearchQuery(q)
    if (q.length < 2) { setSearchResults([]); return }
    setSearching(true)
    try {
      const results = await hrApi.searchEmployees(q)
      const taken = new Set(rows.map((r) => r.userId))
      setSearchResults(results.filter((e) => !taken.has(e.id)))
    } catch {
      setSearchResults([])
    } finally {
      setSearching(false)
    }
  }

  const addEmployee = (emp: HrEmployee) => {
    const t = bonusTypes[0]
    setRows((prev) => [
      ...prev,
      {
        id: null,
        userId: emp.id,
        userName: emp.name,
        year: defYear,
        month: defMonth,
        partStart: event.start_date ?? '',
        partEnd: event.end_date ?? '',
        bonusDays: '1',
        hoursFree: '6',
        bonusTypeId: t ? String(t.id) : '',
        bonusNet: t ? t.amount / (t.days_per_amount ?? 1) : null,
        details: '',
      },
    ])
    setSearchQuery('')
    setSearchResults([])
  }

  const updateRow = (idx: number, updates: Partial<ParticipantRow>) => {
    setRows((prev) =>
      prev.map((r, i) => {
        if (i !== idx) return r
        const updated = { ...r, ...updates }
        // Recompute amount only when a bonus type is selected (matches AddEventPage);
        // rows without a type keep their stored/manual amount.
        if ('bonusTypeId' in updates || 'bonusDays' in updates) {
          const type = bonusTypes.find((t) => String(t.id) === updated.bonusTypeId)
          const days = parseFloat(updated.bonusDays) || 0
          if (type && days > 0) updated.bonusNet = (type.amount / (type.days_per_amount ?? 1)) * days
        }
        return updated
      }),
    )
  }

  const removeRow = (idx: number) => setRows((prev) => prev.filter((_, i) => i !== idx))

  const saveMutation = useMutation({
    mutationFn: async () => {
      const ops = diffParticipantRows(original, rows, eventId)
      for (const c of ops.creates) await hrApi.createBonus(c)
      for (const u of ops.updates) await hrApi.updateBonus(u.id, u.data)
      for (const id of ops.deletes) await hrApi.deleteBonus(id)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['event-participants', eventId] })
      queryClient.invalidateQueries({ queryKey: ['hr-events'] })
      queryClient.invalidateQueries({ queryKey: ['hr-summary'] })
      toast.success('Participants updated')
      onClose()
    },
    onError: (e) => toast.error(errorMessage(e)),
  })

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Edit participants</DialogTitle>
          <DialogDescription>{event.name}</DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="p-4 text-sm text-muted-foreground">Loading participants…</div>
        ) : (
          <div className="space-y-3">
            <div className="rounded-md border overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Period</TableHead>
                    <TableHead className="text-right">Days</TableHead>
                    <TableHead className="text-right">Free Hours</TableHead>
                    {canViewAmounts && <TableHead className="text-right">Bonus (RON)</TableHead>}
                    {canDeleteBonus && <TableHead className="w-10" />}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-sm text-muted-foreground text-center py-6">
                        No participants. {canAddBonus ? 'Add one below.' : ''}
                      </TableCell>
                    </TableRow>
                  ) : (
                    rows.map((row, idx) => (
                      <TableRow key={row.id ?? `new-${idx}`}>
                        <TableCell className="text-sm font-medium whitespace-nowrap">{row.userName}</TableCell>
                        <TableCell>
                          <Select value={row.bonusTypeId || undefined} onValueChange={(v) => updateRow(idx, { bonusTypeId: v })}>
                            <SelectTrigger className="h-8 w-[130px] text-xs"><SelectValue placeholder="Type" /></SelectTrigger>
                            <SelectContent>
                              {bonusTypes.map((t) => (
                                <SelectItem key={t.id} value={String(t.id)}>{t.name}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-1">
                            <DateField value={row.partStart} onChange={(v) => updateRow(idx, { partStart: v })} className="w-[120px]" />
                            <span className="text-muted-foreground">—</span>
                            <DateField value={row.partEnd} onChange={(v) => updateRow(idx, { partEnd: v })} className="w-[120px]" />
                          </div>
                        </TableCell>
                        <TableCell className="text-right">
                          <Input
                            aria-label={`Bonus days for ${row.userName}`}
                            type="number" min="0" step="0.5"
                            value={row.bonusDays}
                            onChange={(e) => updateRow(idx, { bonusDays: e.target.value })}
                            className="h-8 w-16 text-right tabular-nums ml-auto"
                          />
                        </TableCell>
                        <TableCell className="text-right">
                          <Input
                            aria-label={`Free hours for ${row.userName}`}
                            type="number" min="0" step="1"
                            value={row.hoursFree}
                            onChange={(e) => updateRow(idx, { hoursFree: e.target.value })}
                            className="h-8 w-16 text-right tabular-nums ml-auto"
                          />
                        </TableCell>
                        {canViewAmounts && (
                          <TableCell className="text-right">
                            <Input
                              aria-label={`Bonus amount for ${row.userName}`}
                              type="number" min="0" step="1"
                              value={row.bonusNet ?? ''}
                              onChange={(e) => updateRow(idx, { bonusNet: e.target.value === '' ? null : Number(e.target.value) })}
                              className="h-8 w-24 text-right tabular-nums ml-auto"
                            />
                          </TableCell>
                        )}
                        {canDeleteBonus && (
                          <TableCell>
                            <Button
                              variant="ghost" size="icon" className="h-7 w-7 text-destructive"
                              aria-label={`Remove ${row.userName}`}
                              onClick={() => removeRow(idx)}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </TableCell>
                        )}
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>

            {canAddBonus && (
              <div className="space-y-2">
                <div className="relative">
                  <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    aria-label="Search employees to add"
                    value={searchQuery}
                    onChange={(e) => handleSearch(e.target.value)}
                    placeholder="Search employee to add…"
                    className="pl-8 h-9"
                  />
                  {searching && <Loader2 className="absolute right-2 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-muted-foreground" />}
                </div>
                {searchResults.length > 0 && (
                  <div className="rounded-md border max-h-40 overflow-y-auto">
                    {searchResults.map((emp) => (
                      <button
                        key={emp.id}
                        type="button"
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-muted"
                        onClick={() => addEmployee(emp)}
                      >
                        <Plus className="h-3.5 w-3.5 text-muted-foreground" />
                        <span className="font-medium">{emp.name}</span>
                        {emp.company && <span className="text-xs text-muted-foreground">{emp.company}</span>}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>Save</Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
