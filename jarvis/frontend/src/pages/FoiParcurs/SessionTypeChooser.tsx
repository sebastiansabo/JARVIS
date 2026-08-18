import { Car, UserRound } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'

export type SessionType = 'client' | 'internal'

interface SessionTypeChooserProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onPick: (type: SessionType) => void
}

/** First step of "+ Sesiune nouă" — lets the advisor pick between a
 *  client-facing test drive (contract + signatures, unchanged) and a slim
 *  internal driving log (no client/signature). Reused by the Hub Driving
 *  panel, the standalone Foi de Parcurs page and the Calendar's slot-add. */
export default function SessionTypeChooser({ open, onOpenChange, onPick }: SessionTypeChooserProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Sesiune nouă</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <button
            type="button"
            onClick={() => onPick('client')}
            className="flex flex-col items-start gap-2 rounded-xl border p-4 text-left transition-colors hover:border-primary hover:bg-accent"
          >
            <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <UserRound className="h-5 w-5" />
            </span>
            <span className="text-sm font-semibold">Sesiune cu client</span>
            <span className="text-xs text-muted-foreground">Test drive cu contract și semnături</span>
          </button>
          <button
            type="button"
            onClick={() => onPick('internal')}
            className="flex flex-col items-start gap-2 rounded-xl border p-4 text-left transition-colors hover:border-primary hover:bg-accent"
          >
            <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Car className="h-5 w-5" />
            </span>
            <span className="text-sm font-semibold">Sesiune internă</span>
            <span className="text-xs text-muted-foreground">Jurnal de conducere, fără client/semnătură</span>
          </button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
