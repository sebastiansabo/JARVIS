import { useState } from 'react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'

/** JARVIS-styled cancel dialog for a Bilet de Învoire, replacing the native
 *  window.confirm. A motive is required for both a pending self-withdraw and an
 *  approved-leave cancellation request (the manager sees the motive on the latter). */
export function CancelLeaveDialog({
  open, approved, pending, onOpenChange, onConfirm,
}: {
  open: boolean
  /** true = cancelling an APPROVED leave (needs manager approval). */
  approved: boolean
  pending: boolean
  onOpenChange: (v: boolean) => void
  onConfirm: (reason: string) => void
}) {
  const [reason, setReason] = useState('')
  const close = (v: boolean) => { if (!v) setReason(''); onOpenChange(v) }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{approved ? 'Cere anularea învoirii' : 'Anulează cererea de învoire'}</DialogTitle>
          <DialogDescription>
            {approved
              ? 'Cererea de anulare va fi trimisă managerului spre aprobare.'
              : 'Cererea ta de învoire va fi anulată.'}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label>Motiv<span className="ml-0.5 text-destructive">*</span></Label>
          <Textarea
            autoFocus rows={3} value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Motivul anulării"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => close(false)} disabled={pending}>Renunță</Button>
          <Button
            variant="destructive"
            disabled={pending || !reason.trim()}
            onClick={() => onConfirm(reason.trim())}
          >
            {pending ? 'Se trimite…' : approved ? 'Trimite cererea' : 'Anulează învoirea'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
