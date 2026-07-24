import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Check, Search, Lock, Users } from 'lucide-react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { eval360Nomination, RELATIONSHIP_LABEL } from '@/api/evaluation360'

const RECOMMENDED_MAX = 8

/** Peer nomination for one subject. Shared by the HR editor (any subject) and
 *  an employee nominating their own peers. `title` distinguishes the two. */
export default function NominationEditor({
  cycleId, subjectId, subjectName, title, onClose,
}: {
  cycleId: number; subjectId: number; subjectName: string; title?: string; onClose: () => void
}) {
  const qc = useQueryClient()
  const q = useQuery({
    queryKey: ['eval360-nominate', cycleId, subjectId],
    queryFn: () => eval360Nomination.view(cycleId, subjectId),
  })

  const [selected, setSelected] = useState<Set<number> | null>(null)
  const [search, setSearch] = useState('')

  // Rows: current peers first (some locked if already submitted), then candidates.
  const { rows, lockedIds, initial } = useMemo(() => {
    const v = q.data
    if (!v) return { rows: [], lockedIds: new Set<number>(), initial: new Set<number>() }
    const locked = new Set<number>()
    const init = new Set<number>()
    const peerRows = v.peers.map((p) => {
      const id = p.reviewer_id as number
      init.add(id)
      if (p.status === 'submitted') locked.add(id)
      return { id, name: p.reviewer_name ?? `#${id}`, dept: null as string | null, status: p.status }
    })
    const candRows = v.candidates.map((c) => ({ id: c.id, name: c.name, dept: c.department, status: null as string | null }))
    return { rows: [...peerRows, ...candRows], lockedIds: locked, initial: init }
  }, [q.data])

  const sel = selected ?? initial
  const filtered = useMemo(
    () => (search.trim() ? rows.filter((r) => r.name.toLowerCase().includes(search.toLowerCase())) : rows),
    [rows, search],
  )

  const toggle = (id: number) => {
    if (lockedIds.has(id)) return
    setSelected((prev) => {
      const next = new Set(prev ?? initial)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const saveM = useMutation({
    mutationFn: () => eval360Nomination.setPeers(cycleId, subjectId, [...sel]),
    onSuccess: ({ result }) => {
      toast.success(`Colegi actualizați · ${result.added.length} adăugați, ${result.removed.length} eliminați`)
      qc.invalidateQueries({ queryKey: ['eval360-nominate', cycleId, subjectId] })
      qc.invalidateQueries({ queryKey: ['eval360-nomination-participants', cycleId] })
      qc.invalidateQueries({ queryKey: ['eval360-my-nominations'] })
      onClose()
    },
    onError: () => toast.error('Nu s-au putut salva colegii'),
  })

  const others = q.data?.others ?? []

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{title ?? 'Nominalizează colegi'}</DialogTitle>
        </DialogHeader>

        <p className="text-sm text-muted-foreground -mt-1">
          Pentru <span className="font-medium text-foreground">{subjectName}</span> · alege colegii care oferă feedback.
        </p>

        {q.isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : (
          <>
            {others.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {others.map((o) => (
                  <Badge key={o.id} variant="secondary" className="text-[11px]">
                    {RELATIONSHIP_LABEL[o.relationship] ?? o.relationship}: {o.reviewer_name}
                  </Badge>
                ))}
              </div>
            )}

            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-sm font-medium">
                <Users className="h-4 w-4" />{sel.size} colegi selectați
              </span>
              {sel.size > RECOMMENDED_MAX && (
                <span className="text-xs text-amber-600">peste recomandarea de {RECOMMENDED_MAX}</span>
              )}
            </div>

            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input className="pl-8" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Caută un nume…" />
            </div>

            <div className="max-h-72 overflow-y-auto rounded-lg border divide-y">
              {filtered.length === 0 ? (
                <p className="p-4 text-center text-sm text-muted-foreground">Niciun coleg disponibil.</p>
              ) : filtered.map((r) => {
                const on = sel.has(r.id)
                const locked = lockedIds.has(r.id)
                return (
                  <button
                    key={r.id}
                    type="button"
                    disabled={locked}
                    onClick={() => toggle(r.id)}
                    className={cn(
                      'flex w-full items-center justify-between px-3 py-2 text-left text-sm transition-colors',
                      locked ? 'cursor-not-allowed bg-muted/40' : 'hover:bg-muted/50',
                    )}
                  >
                    <span className="min-w-0 truncate">
                      {r.name}
                      {r.dept && <span className="ml-2 text-xs text-muted-foreground">{r.dept}</span>}
                    </span>
                    {locked ? (
                      <span className="flex items-center gap-1 text-xs text-muted-foreground"><Lock className="h-3 w-3" />trimis</span>
                    ) : (
                      <span className={cn('flex h-5 w-5 items-center justify-center rounded-md border',
                        on ? 'border-primary bg-primary text-primary-foreground' : 'border-muted-foreground/30')}>
                        {on && <Check className="h-3.5 w-3.5" />}
                      </span>
                    )}
                  </button>
                )
              })}
            </div>

            <div className="flex items-center justify-end gap-2">
              <Button variant="outline" size="sm" onClick={onClose}>Anulează</Button>
              <Button size="sm" disabled={saveM.isPending} onClick={() => saveM.mutate()}>Salvează colegii</Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
