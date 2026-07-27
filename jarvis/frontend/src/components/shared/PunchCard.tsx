import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { LogIn, LogOut, Loader2, Wifi, CheckCircle2, XCircle, Clock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { checkinApi } from '@/api/checkin'
import type { CheckinStatus, PunchResult } from '@/types/checkin'

// Promise wrapper around the browser Geolocation API so we can `await` the fix
// on the button click (no permission prompt until the user actually punches).
function getPosition(): Promise<{ lat: number; lng: number } | null> {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(null)
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: 15_000, maximumAge: 0 },
    )
  })
}

/** Compact GPS punch-in/out card. Shares the `checkin-status` query cache with
 *  the mobile check-in page, so a punch here updates both. Server decides the
 *  next direction (IN/OUT) and validates location — we only send coordinates. */
export function PunchCard() {
  const qc = useQueryClient()
  const [locating, setLocating] = useState(false)
  const [result, setResult] = useState<PunchResult | null>(null)

  const { data: status, isLoading } = useQuery<CheckinStatus>({
    queryKey: ['checkin-status'],
    queryFn: checkinApi.getStatus,
    refetchInterval: 30_000,
  })

  const punch = useMutation({
    mutationFn: (data: { lat?: number; lng?: number }) => checkinApi.punch(data),
    onSuccess: (r) => {
      setResult(r)
      qc.invalidateQueries({ queryKey: ['checkin-status'] })
    },
    onError: (err: any) => {
      const d = err?.data || err?.response?.data || {}
      setResult({ success: false, error: d.error || 'Eroare de rețea. Verifică conexiunea.', distance: d.distance, location: d.location, allowed_radius: d.allowed_radius })
    },
  })

  const doPunch = async (gps: boolean) => {
    setResult(null)
    if (!gps) return punch.mutate({})
    setLocating(true)
    const pos = await getPosition()
    setLocating(false)
    punch.mutate(pos ? { lat: pos.lat, lng: pos.lng } : {})
  }

  const busy = locating || punch.isPending

  if (isLoading) {
    return <Card><CardContent className="p-4 h-[68px] flex items-center text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin mr-2" /> Se încarcă pontajul…</CardContent></Card>
  }

  // Account not linked to a BioStar employee — can't punch.
  if (status && !status.mapped) {
    return (
      <Card className="border-dashed">
        <CardContent className="p-4 flex items-center gap-3 text-sm text-muted-foreground">
          <XCircle className="h-4 w-4 shrink-0 text-muted-foreground" />
          Contul tău nu este conectat la pontajul GPS. Contactează HR pentru mapare.
        </CardContent>
      </Card>
    )
  }

  const isCheckIn = (status?.next_direction || 'IN') === 'IN'
  const lastPunch = status?.punches?.[status.punches.length - 1]
  const lastTime = lastPunch
    ? new Date(lastPunch.event_datetime).toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' })
    : null

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <Button
            onClick={() => doPunch(true)}
            disabled={busy}
            className={`gap-2 ${isCheckIn ? 'bg-green-600 hover:bg-green-700' : 'bg-red-600 hover:bg-red-700'} text-white`}
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : isCheckIn ? <LogIn className="h-4 w-4" /> : <LogOut className="h-4 w-4" />}
            {isCheckIn ? 'Pontează intrare' : 'Pontează ieșire'}
          </Button>
          <Button variant="outline" size="sm" onClick={() => doPunch(false)} disabled={busy} className="gap-1.5">
            <Wifi className="h-4 w-4" /> WiFi
          </Button>
          <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
            <Clock className="h-3.5 w-3.5" />
            {lastTime
              ? <span>Ultima pontare: <span className="font-medium text-foreground">{lastTime}</span> ({lastPunch!.direction})</span>
              : <span>Nicio pontare azi</span>}
            {status?.punches != null && status.punches.length > 0 && (
              <Badge variant="secondary" className="text-[10px]">{status.punches.length}</Badge>
            )}
          </div>
        </div>

        {result && (
          <div className={`flex items-start gap-2 rounded-md px-3 py-2 text-sm ${result.success ? 'bg-green-50 text-green-700 dark:bg-green-950/20 dark:text-green-400' : 'bg-red-50 text-red-700 dark:bg-red-950/20 dark:text-red-400'}`}>
            {result.success ? <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" /> : <XCircle className="h-4 w-4 shrink-0 mt-0.5" />}
            {result.success
              ? <span>{result.direction === 'IN' ? 'Intrare' : 'Ieșire'} înregistrată la {result.time} — {result.location}{result.distance != null && result.distance > 0 ? ` (${result.distance}m)` : ''}</span>
              : <span>{result.error}</span>}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
