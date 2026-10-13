import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { AlertTriangle } from 'lucide-react'
import { buybackApi } from '@/api/buyback'
import type { BuybackRecord } from '@/types/buyback'
import { recordStatus, STATUS_FILTER_OPTIONS } from './recordStatus'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

function errMsg(e: unknown, fallback: string): string {
  const data = (e as { data?: { error?: string } } | undefined)?.data
  if (data?.error) return data.error
  if (e instanceof Error && e.message) return e.message
  return fallback
}

/**
 * Admin/Manager status override — set a buyback record to ANY status, bypassing
 * the lifecycle state machine. Shared by the detail page (ActionPanel) and the
 * list's inline row menu; owns its own mutation + cache invalidation so both
 * call sites just render it and toggle `open`.
 *
 * This NEVER touches the linked CarPark vehicle or offers (mirrors the backend
 * force_status contract) — the warning text spells that out. A record is the
 * minimal shape both call sites can supply (list rows carry the full record).
 */
export default function StatusChangeDialog({
  record,
  open,
  onOpenChange,
}: {
  record: Pick<BuybackRecord, 'id' | 'status' | 'record_code' | 'brand' | 'model'>
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const [target, setTarget] = useState('')
  const [note, setNote] = useState('')

  // Reset the form each time the dialog opens (or the record changes) so a
  // previous pick never leaks into the next record's override.
  useEffect(() => {
    if (open) {
      setTarget('')
      setNote('')
    }
  }, [open, record.id])

  const mutation = useMutation({
    mutationFn: () => buybackApi.setStatus(record.id, { status: target, note: note || undefined }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['buyback-record', record.id] })
      queryClient.invalidateQueries({ queryKey: ['buyback-records'] })
      toast.success('Statusul a fost schimbat')
      onOpenChange(false)
    },
    onError: (e) => toast.error(errMsg(e, 'Schimbarea statusului a eșuat')),
  })

  const current = recordStatus(record.status)
  // All statuses except the record's current one (a no-op is rejected backend-side anyway).
  const options = STATUS_FILTER_OPTIONS.filter((o) => o.value !== record.status)
  const targetIsBought = target === 'BOUGHT'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Schimbă statusul</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">
              <span className="font-mono text-xs">{record.record_code}</span> · {record.brand} {record.model}
            </span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Status curent:</span>
            <Badge className={current.badgeClass}>{current.label}</Badge>
          </div>

          <div className="space-y-1">
            <Label className="text-xs">Status nou</Label>
            <Select value={target} onValueChange={setTarget}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Alege statusul" />
              </SelectTrigger>
              <SelectContent>
                {options.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label className="text-xs">Motiv / notă (opțional)</Label>
            <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
          </div>

          <div className="flex gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2.5 text-xs text-amber-700 dark:text-amber-400">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div className="space-y-1">
              <p>
                Suprascrie fluxul normal de lucru. Nu creează, nu șterge și nu modifică vehiculul din
                CarPark și nu schimbă ofertele — doar statusul solicitării.
              </p>
              {targetIsBought && (
                <p>
                  „Achiziționat” prin suprascriere <strong>nu</strong> creează vehiculul în CarPark —
                  folosește apoi „Finalizează → CarPark” pentru transfer.
                </p>
              )}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Renunță
          </Button>
          <Button disabled={!target || mutation.isPending} onClick={() => mutation.mutate()}>
            Schimbă statusul
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
