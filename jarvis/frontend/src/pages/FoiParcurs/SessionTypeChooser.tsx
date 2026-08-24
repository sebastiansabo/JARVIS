import { Car, KeyRound, UserRound } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'

export type SessionType = 'client' | 'internal' | 'rental'

interface SessionTypeChooserProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onPick: (type: SessionType) => void
  /** Show the "Rent-a-car" card — only offered when the selected company has
   *  Service (Mașini de curtoazie) enabled, so it never opens onto a locked pool. */
  showRental?: boolean
}

/** First step of "+ Sesiune nouă" — lets the advisor pick between a
 *  client-facing test drive (contract + signatures, unchanged), a slim
 *  internal driving log (no client/signature), and — when the company has
 *  Service enabled — a Rent-a-car courtesy session (client test-drive form
 *  running the rental pricing + courtesy contract). Reused by the Hub Driving
 *  panel, the standalone Foi de Parcurs page and the Calendar's slot-add. */
export default function SessionTypeChooser({ open, onOpenChange, onPick, showRental }: SessionTypeChooserProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Sesiune nouă</DialogTitle>
        </DialogHeader>
        <div className={cn('grid gap-3', showRental ? 'sm:grid-cols-3' : 'sm:grid-cols-2')}>
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
          {showRental && (
            <button
              type="button"
              onClick={() => onPick('rental')}
              className="flex flex-col items-start gap-2 rounded-xl border p-4 text-left transition-colors hover:border-primary hover:bg-accent"
            >
              <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <KeyRound className="h-5 w-5" />
              </span>
              <span className="text-sm font-semibold">Rent-a-car</span>
              <span className="text-xs text-muted-foreground">Mașină de curtoazie — contract închiriere + tarif</span>
            </button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
