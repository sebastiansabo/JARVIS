import { useState, useCallback, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  MapPin, LogIn, LogOut, Loader2, CheckCircle2, XCircle,
  Navigation, Clock, Smartphone, Zap, Wifi, QrCode, Camera,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { useAuth } from '@/hooks/useAuth'
import { checkinApi } from '@/api/checkin'
import type { CheckinStatus, PunchResult, CheckinLocation } from '@/types/checkin'

// ── Haversine (client-side, for display only — server validates) ──

function haversine(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6_371_000
  const p1 = (lat1 * Math.PI) / 180
  const p2 = (lat2 * Math.PI) / 180
  const dp = ((lat2 - lat1) * Math.PI) / 180
  const dl = ((lon2 - lon1) * Math.PI) / 180
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

// ── GPS hook ──

function useGPS() {
  const [position, setPosition] = useState<{ lat: number; lng: number } | null>(null)
  const [accuracy, setAccuracy] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const requestPosition = useCallback(() => {
    if (!navigator.geolocation) {
      setError('Geolocation not supported by this browser.')
      return
    }
    setLoading(true)
    setError(null)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setPosition({ lat: pos.coords.latitude, lng: pos.coords.longitude })
        setAccuracy(pos.coords.accuracy)
        setLoading(false)
      },
      (err) => {
        const messages: Record<number, string> = {
          1: 'Location access denied. Enable GPS in your phone settings.',
          2: 'Location unavailable. Make sure GPS is on.',
          3: 'Location request timed out. Try again.',
        }
        setError(messages[err.code] || 'Unknown GPS error.')
        setLoading(false)
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    )
  }, [])

  return { position, accuracy, error, loading, requestPosition }
}

// ── QR Scanner hook (uses native camera + BarcodeDetector or manual input) ──

function useQRScanner(onScan: (token: string) => void) {
  const [scanning, setScanning] = useState(false)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopScanning = useCallback(() => {
    if (intervalRef.current) clearInterval(intervalRef.current)
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
    setScanning(false)
  }, [])

  const startScanning = useCallback(async () => {
    // Check if BarcodeDetector is available (Chrome Android, Safari 16.4+)
    if (!('BarcodeDetector' in window)) {
      // Fallback: prompt for manual QR code input
      const token = prompt('Enter the check-in code from the QR (e.g. checkin:1):')
      if (token) onScan(token)
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
      })
      streamRef.current = stream
      setScanning(true)

      // Wait for video element to be ready
      requestAnimationFrame(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          videoRef.current.play()
        }

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const detector = new (window as any).BarcodeDetector({ formats: ['qr_code'] })
        intervalRef.current = setInterval(async () => {
          if (!videoRef.current || videoRef.current.readyState < 2) return
          try {
            const barcodes = await detector.detect(videoRef.current)
            if (barcodes.length > 0) {
              const value = barcodes[0].rawValue
              if (value && value.startsWith('checkin:')) {
                stopScanning()
                onScan(value)
              }
            }
          } catch {
            // detection frame error, ignore
          }
        }, 500)
      })
    } catch {
      // Camera denied or unavailable
      const token = prompt('Camera unavailable. Enter the check-in code manually (e.g. checkin:1):')
      if (token) onScan(token)
    }
  }, [onScan, stopScanning])

  // Cleanup on unmount
  useEffect(() => () => stopScanning(), [stopScanning])

  return { scanning, videoRef, startScanning, stopScanning }
}

// ── Desktop message ──

function DesktopMessage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6 text-center px-4">
      <Smartphone className="h-16 w-16 text-muted-foreground" />
      <div>
        <h2 className="text-2xl font-semibold mb-2">Mobile Only</h2>
        <p className="text-muted-foreground max-w-sm">
          GPS Check-in is only available on your phone. Open this page on your mobile device to punch in or out.
        </p>
      </div>
      <div className="text-sm text-muted-foreground bg-muted rounded-lg px-4 py-3 font-mono">
        /app/mobile-checkin
      </div>
    </div>
  )
}

// ── Method label ──

function methodLabel(method?: string) {
  switch (method) {
    case 'gps_mobile': return 'GPS'
    case 'ip_wifi': return 'WiFi'
    case 'qr_code': return 'QR'
    default: return method || ''
  }
}

// ── Main component ──

export default function MobileCheckin() {
  const isMobile = useIsMobile()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const gps = useGPS()
  const [lastResult, setLastResult] = useState<PunchResult | null>(null)

  // Fetch status (today's punches + next direction)
  const { data: status, isLoading: statusLoading } = useQuery<CheckinStatus>({
    queryKey: ['checkin-status'],
    queryFn: checkinApi.getStatus,
    refetchInterval: 30_000,
  })

  // Fetch locations (for client-side distance display)
  const { data: locations } = useQuery<CheckinLocation[]>({
    queryKey: ['checkin-locations'],
    queryFn: checkinApi.getLocations,
  })

  // Punch mutation — accepts optional GPS coords or QR token
  const punchMutation = useMutation({
    mutationFn: (data: { lat?: number; lng?: number; qr_token?: string }) =>
      checkinApi.punch(data),
    onSuccess: (result) => {
      setLastResult(result)
      queryClient.invalidateQueries({ queryKey: ['checkin-status'] })
    },
    onError: (err: any) => {
      const errorData = err?.data || err?.response?.data || {}
      setLastResult({
        success: false,
        error: errorData.error || 'Network error. Check your connection.',
        distance: errorData.distance,
        location: errorData.location,
        allowed_radius: errorData.allowed_radius,
      })
    },
  })

  // QR scanner
  const qrScanner = useQRScanner((token) => {
    setLastResult(null)
    setSuggestionDismissed(true)
    punchMutation.mutate({ qr_token: token })
  })

  // Auto-request GPS on mount (mobile only)
  const autoGpsRequested = useRef(false)
  useEffect(() => {
    if (isMobile && !autoGpsRequested.current) {
      autoGpsRequested.current = true
      gps.requestPosition()
    }
  }, [isMobile]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Geofence exit → auto check-out ──
  const autoCheckoutFired = useRef(false)
  useEffect(() => {
    // Only watch when user is checked in (next direction = OUT) and on mobile
    const isCheckedIn = status?.mapped && status.next_direction === 'OUT'
    if (!isMobile || !isCheckedIn || !navigator.geolocation || !locations?.length) {
      autoCheckoutFired.current = false
      return
    }

    const watchId = navigator.geolocation.watchPosition(
      (pos) => {
        if (autoCheckoutFired.current) return
        const { latitude: uLat, longitude: uLng } = pos.coords

        // Check distance to every active location's auto-checkout radius
        const outsideAll = locations.every((loc) => {
          const d = haversine(uLat, uLng, loc.latitude, loc.longitude)
          const threshold = loc.auto_checkout_radius_meters ?? 200
          return d > threshold
        })

        if (outsideAll) {
          autoCheckoutFired.current = true
          // Auto punch OUT
          checkinApi.punch({ lat: uLat, lng: uLng, direction: 'OUT' })
            .then((res: any) => {
              const data = res?.data ?? res
              setLastResult(data?.success ? data : { success: true, direction: 'OUT', time: new Date().toLocaleTimeString('ro-RO'), location: 'Auto-checkout (left area)' })
              queryClient.invalidateQueries({ queryKey: ['checkin-status'] })
              queryClient.invalidateQueries({ queryKey: ['checkin', 'status'] })
            })
            .catch(() => {
              autoCheckoutFired.current = false // allow retry on error
            })
        }
      },
      () => { /* GPS error — ignore, manual checkout still available */ },
      { enableHighAccuracy: true, maximumAge: 10_000 },
    )

    return () => navigator.geolocation.clearWatch(watchId)
  }, [isMobile, status?.mapped, status?.next_direction, locations, queryClient]) // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-suggestion: no punches today + in range = suggest check-in
  const [suggestionDismissed, setSuggestionDismissed] = useState(false)
  const noPunchesToday = status?.mapped && status.punches.length === 0
  const showSuggestion = !suggestionDismissed && !lastResult && noPunchesToday
    && gps.position && !gps.loading && !punchMutation.isPending

  // GPS punch
  const handlePunch = () => {
    setLastResult(null)
    setSuggestionDismissed(true)
    if (gps.position) {
      punchMutation.mutate({ lat: gps.position.lat, lng: gps.position.lng })
    } else {
      // No GPS — try IP-only (send empty body, server checks IP)
      punchMutation.mutate({})
    }
  }

  if (!isMobile) return <DesktopMessage />

  const nextDir = status?.next_direction || 'IN'
  const isCheckIn = nextDir === 'IN'
  const isPending = gps.loading || punchMutation.isPending

  // Client-side distance to nearest location
  let nearestDist: number | null = null
  let nearestName: string | null = null
  if (gps.position && locations?.length) {
    for (const loc of locations) {
      const d = haversine(gps.position.lat, gps.position.lng, loc.latitude, loc.longitude)
      if (nearestDist === null || d < nearestDist) {
        nearestDist = d
        nearestName = loc.name
      }
    }
  }

  return (
    <div className="flex flex-col gap-4 pb-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">GPS Check-in</h1>
          <p className="text-sm text-muted-foreground">{user?.name}</p>
        </div>
        {gps.accuracy !== null && (
          <Badge
            variant={gps.accuracy < 20 ? 'default' : gps.accuracy < 50 ? 'secondary' : 'destructive'}
            className="gap-1"
          >
            <Navigation className="h-3 w-3" />
            {Math.round(gps.accuracy)}m
          </Badge>
        )}
      </div>

      {/* Not mapped warning */}
      {status && !status.mapped && (
        <Card className="border-destructive">
          <CardContent className="pt-4 pb-4">
            <div className="flex items-start gap-3">
              <XCircle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
              <div>
                <p className="font-medium text-destructive">Account Not Linked</p>
                <p className="text-sm text-muted-foreground mt-1">
                  Your account is not linked to a BioStar employee. Contact HR to set up the mapping.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Distance indicator */}
      {nearestDist !== null && (
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="flex items-center gap-3">
              <MapPin className={`h-5 w-5 shrink-0 ${nearestDist <= 50 ? 'text-green-500' : 'text-red-500'}`} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{nearestName}</p>
                <p className={`text-lg font-bold ${nearestDist <= 50 ? 'text-green-600' : 'text-red-600'}`}>
                  {Math.round(nearestDist)}m away
                </p>
              </div>
              {nearestDist <= 50 ? (
                <CheckCircle2 className="h-6 w-6 text-green-500 shrink-0" />
              ) : (
                <XCircle className="h-6 w-6 text-red-500 shrink-0" />
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Auto-suggestion: you're at the office, no punch today */}
      {showSuggestion && nearestDist !== null && nearestDist <= 50 && (
        <Card className="border-green-500 bg-green-50 dark:bg-green-950/20 animate-in fade-in slide-in-from-top-2">
          <CardContent className="pt-4 pb-4">
            <div className="flex items-start gap-3">
              <Zap className="h-5 w-5 text-green-600 shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="font-semibold text-green-700 dark:text-green-400">
                  You're at {nearestName}!
                </p>
                <p className="text-sm text-muted-foreground mt-1">
                  No check-in today yet. Want to punch in?
                </p>
                <div className="flex gap-2 mt-3">
                  <Button
                    size="sm"
                    onClick={handlePunch}
                    className="bg-green-600 hover:bg-green-700 text-white gap-1"
                  >
                    <LogIn className="h-4 w-4" /> Check In Now
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setSuggestionDismissed(true)}
                  >
                    Not now
                  </Button>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* GPS error + fallback options */}
      {gps.error && (
        <Card className="border-amber-500 bg-amber-50 dark:bg-amber-950/20">
          <CardContent className="pt-4 pb-4">
            <div className="flex items-start gap-3">
              <XCircle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm text-amber-700 dark:text-amber-400">{gps.error}</p>
                <p className="text-xs text-muted-foreground mt-2">
                  You can still punch via WiFi or QR code.
                </p>
                <div className="flex gap-2 mt-3">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handlePunch}
                    disabled={punchMutation.isPending}
                    className="gap-1"
                  >
                    <Wifi className="h-4 w-4" /> Use WiFi
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={qrScanner.startScanning}
                    disabled={punchMutation.isPending || qrScanner.scanning}
                    className="gap-1"
                  >
                    <QrCode className="h-4 w-4" /> Scan QR
                  </Button>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* QR Scanner viewfinder */}
      {qrScanner.scanning && (
        <Card className="overflow-hidden">
          <CardContent className="p-0 relative">
            <video
              ref={qrScanner.videoRef}
              className="w-full aspect-square object-cover"
              playsInline
              muted
            />
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="w-48 h-48 border-2 border-white/70 rounded-lg" />
            </div>
            <div className="absolute bottom-0 left-0 right-0 p-3 bg-black/50 flex items-center justify-between">
              <div className="flex items-center gap-2 text-white text-sm">
                <Camera className="h-4 w-4" />
                Point at QR code
              </div>
              <Button
                size="sm"
                variant="secondary"
                onClick={qrScanner.stopScanning}
              >
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Big punch button */}
      <div className="flex justify-center py-6">
        <Button
          size="lg"
          disabled={isPending || statusLoading || (status !== undefined && !status.mapped)}
          onClick={handlePunch}
          className={`
            h-32 w-32 rounded-full text-lg font-bold shadow-lg
            transition-all active:scale-95
            ${isCheckIn
              ? 'bg-green-600 hover:bg-green-700 text-white'
              : 'bg-red-600 hover:bg-red-700 text-white'
            }
          `}
        >
          {isPending ? (
            <Loader2 className="h-8 w-8 animate-spin" />
          ) : isCheckIn ? (
            <div className="flex flex-col items-center gap-1">
              <LogIn className="h-8 w-8" />
              <span>Check In</span>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-1">
              <LogOut className="h-8 w-8" />
              <span>Check Out</span>
            </div>
          )}
        </Button>
      </div>

      {/* Fallback buttons row (always visible) */}
      <div className="flex justify-center gap-3">
        <Button
          variant="outline"
          size="sm"
          onClick={() => { setLastResult(null); gps.requestPosition() }}
          disabled={gps.loading}
          className="gap-1.5"
        >
          {gps.loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Navigation className="h-4 w-4" />}
          GPS
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => { setLastResult(null); punchMutation.mutate({}) }}
          disabled={punchMutation.isPending}
          className="gap-1.5"
        >
          <Wifi className="h-4 w-4" /> WiFi
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => { setLastResult(null); qrScanner.startScanning() }}
          disabled={punchMutation.isPending || qrScanner.scanning}
          className="gap-1.5"
        >
          <QrCode className="h-4 w-4" /> QR
        </Button>
      </div>

      {/* Result feedback */}
      {lastResult && (
        <Card className={lastResult.success ? 'border-green-500 bg-green-50 dark:bg-green-950/20' : 'border-red-500 bg-red-50 dark:bg-red-950/20'}>
          <CardContent className="pt-4 pb-4">
            <div className="flex items-start gap-3">
              {lastResult.success ? (
                <CheckCircle2 className="h-6 w-6 text-green-600 shrink-0 mt-0.5" />
              ) : (
                <XCircle className="h-6 w-6 text-red-600 shrink-0 mt-0.5" />
              )}
              <div>
                {lastResult.success ? (
                  <>
                    <p className="font-semibold text-green-700 dark:text-green-400">
                      {lastResult.direction === 'IN' ? 'Checked In' : 'Checked Out'} at {lastResult.time}
                    </p>
                    <p className="text-sm text-muted-foreground mt-1">
                      {lastResult.location}
                      {lastResult.distance != null && lastResult.distance > 0 ? ` (${lastResult.distance}m away)` : ''}
                      {lastResult.method ? ` via ${methodLabel(lastResult.method)}` : ''}
                    </p>
                  </>
                ) : (
                  <>
                    <p className="font-semibold text-red-700 dark:text-red-400">Punch Failed</p>
                    <p className="text-sm text-muted-foreground mt-1">{lastResult.error}</p>
                  </>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Today's punches */}
      {status?.punches && status.punches.length > 0 && (
        <Card>
          <CardContent className="pt-4 pb-2">
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
              <Clock className="h-4 w-4" />
              Today's Punches
            </h3>
            <div className="space-y-2">
              {status.punches.map((punch) => {
                const time = new Date(punch.event_datetime).toLocaleTimeString('ro-RO', {
                  hour: '2-digit', minute: '2-digit', second: '2-digit',
                })
                const isGPS = punch.device_name === 'GPS Mobile'
                const source = punch.raw_data?.source
                return (
                  <div key={punch.id} className="flex items-center justify-between py-1.5 border-b last:border-0">
                    <div className="flex items-center gap-2">
                      {punch.direction === 'IN' ? (
                        <LogIn className="h-4 w-4 text-green-600" />
                      ) : (
                        <LogOut className="h-4 w-4 text-red-600" />
                      )}
                      <span className="font-mono text-sm">{time}</span>
                      <Badge variant={punch.direction === 'IN' ? 'default' : 'secondary'} className="text-xs">
                        {punch.direction}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      {isGPS && punch.raw_data?.distance_meters != null && punch.raw_data.distance_meters > 0 && (
                        <span>{punch.raw_data.distance_meters}m</span>
                      )}
                      <span>{isGPS ? methodLabel(source) : punch.device_name || 'Terminal'}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Empty state */}
      {status?.punches && status.punches.length === 0 && !statusLoading && (
        <p className="text-center text-sm text-muted-foreground py-4">
          No punches today yet. Tap the button above to check in.
        </p>
      )}
    </div>
  )
}
