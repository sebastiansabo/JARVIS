import { useState } from 'react'
import { BarChart3, CheckCircle2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { useCurrentPulse } from '@/api/happy'
import { PulseSheet } from './PulseSheet'

/**
 * Hub card for the current anonymous Pulse:
 * - live + invited + not yet responded → teaser + "Răspunde la pulse"
 * - already responded → a thank-you line
 * - no live pulse (or not invited) → renders null
 */
export function PulseCard() {
  const [open, setOpen] = useState(false)
  const { data } = useCurrentPulse()

  const pulse = data?.pulse ?? null
  if (!pulse) return null

  if (data?.responded) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <BarChart3 className="h-4 w-4" />
            Pulse
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <CheckCircle2 className="h-4 w-4 text-green-600" />
            Mulțumim, ai răspuns.
          </p>
        </CardContent>
      </Card>
    )
  }

  // Only surface an actionable card to invited, not-yet-responded users.
  if (!data?.invited) return null

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <BarChart3 className="h-4 w-4" />
          Pulse
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div>
          <p className="text-sm font-medium">{pulse.title}</p>
          <p className="text-xs text-muted-foreground">
            Câteva întrebări scurte și anonime. Durează sub un minut.
          </p>
        </div>
        <Button size="sm" onClick={() => setOpen(true)}>
          Răspunde la pulse
        </Button>
      </CardContent>

      <PulseSheet
        pulse={pulse}
        questions={data?.questions ?? []}
        anonymityNotice={data?.anonymity_notice ?? ''}
        open={open}
        onOpenChange={setOpen}
      />
    </Card>
  )
}

export default PulseCard
