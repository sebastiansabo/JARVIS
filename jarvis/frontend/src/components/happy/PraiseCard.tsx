import { useState } from 'react'
import { Award, Gift, Plus, Wallet } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useWallet } from '@/api/happy'
import { PraiseComposer } from './PraiseComposer'
import { PraiseFeed } from './PraiseFeed'
import { MyPraiseStreak } from './MyPraiseStreak'

/** Whole days until the giveable balance expires, or null if unknown/past. */
function daysUntil(iso: string | null): number | null {
  if (!iso) return null
  const diff = new Date(iso).getTime() - Date.now()
  if (diff <= 0) return 0
  return Math.ceil(diff / 86_400_000)
}

/**
 * Hub card for Praise: wallet balances (giveable + expiry countdown, redeemable),
 * a "Trimite apreciere" button that opens the composer, the personal streak/trend,
 * and the latest received kudos.
 */
export function PraiseCard() {
  const [composerOpen, setComposerOpen] = useState(false)
  const { data: wallet, isLoading } = useWallet()

  const expiresIn = daysUntil(wallet?.giveable_expires_at ?? null)

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <Award className="h-4 w-4" />
            Aprecieri
          </CardTitle>
          <Button size="sm" onClick={() => setComposerOpen(true)}>
            <Plus className="h-3.5 w-3.5" />
            Trimite apreciere
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Wallet */}
        {isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : (
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border p-3">
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Wallet className="h-3.5 w-3.5" />
                De oferit
              </p>
              <p className="text-xl font-semibold">{wallet?.giveable_balance ?? 0}</p>
              {expiresIn !== null && (
                <p className="text-xs text-muted-foreground">
                  {expiresIn === 0 ? 'expiră azi' : `expiră în ${expiresIn} ${expiresIn === 1 ? 'zi' : 'zile'}`}
                </p>
              )}
            </div>
            <div className="rounded-lg border p-3">
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Gift className="h-3.5 w-3.5" />
                Primite
              </p>
              <p className="text-xl font-semibold">{wallet?.redeemable_balance ?? 0}</p>
              <p className="text-xs text-muted-foreground">nu expiră</p>
            </div>
          </div>
        )}

        {/* Personal streak + trend (no ranking) */}
        <MyPraiseStreak />

        {/* Latest received */}
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Ultimele primite
          </p>
          <PraiseFeed limit={3} />
        </div>
      </CardContent>

      <PraiseComposer open={composerOpen} onOpenChange={setComposerOpen} />
    </Card>
  )
}

export default PraiseCard
