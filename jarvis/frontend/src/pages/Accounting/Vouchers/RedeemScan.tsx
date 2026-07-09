import { useState, useRef, useEffect, useCallback } from 'react'
import { useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'
import jsQR from 'jsqr'
import { Camera, CameraOff, Keyboard, CheckCircle2, XCircle, AlertTriangle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { api } from '@/api/client'
import type { Voucher } from '@/types/vouchers'

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-green-100 text-green-800',
  redeemed: 'bg-gray-200 text-gray-600',
  expired: 'bg-red-50 text-red-600',
  pending_approval: 'bg-yellow-100 text-yellow-800',
  rejected: 'bg-red-100 text-red-800',
}

export default function RedeemScan() {
  const [mode, setMode] = useState<'scan' | 'manual'>('scan')
  const [manualCode, setManualCode] = useState('')
  const [scannedVoucher, setScannedVoucher] = useState<Voucher | null>(null)
  const [redeemNotes, setRedeemNotes] = useState('')
  const [cameraActive, setCameraActive] = useState(false)
  const [lookupError, setLookupError] = useState('')

  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const scanningRef = useRef(false)

  const stopCamera = useCallback(() => {
    scanningRef.current = false
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
    setCameraActive(false)
  }, [])

  const lookupVoucher = useCallback(async (code: string) => {
    setLookupError('')
    setScannedVoucher(null)
    try {
      const voucher = await api.get<Voucher>(`/api/vouchers/lookup/${encodeURIComponent(code)}`)
      setScannedVoucher(voucher)
      stopCamera()
    } catch {
      setLookupError(`Voucher "${code}" not found`)
    }
  }, [stopCamera])

  const startCamera = useCallback(async () => {
    setScannedVoucher(null)
    setLookupError('')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
      })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
      }
      setCameraActive(true)
      scanningRef.current = true

      // Parse the voucher QR payload — either "voucher:CODE" or a URL
      // ".../app/voucher/CODE" (see accounting/vouchers/pdf_generator.py).
      const extractCode = (raw: string): string => {
        if (!raw) return ''
        if (raw.startsWith('voucher:')) return raw.replace('voucher:', '').trim()
        if (raw.includes('/voucher/')) return (raw.split('/voucher/').pop() || '').split(/[?#/]/)[0].trim()
        return ''
      }
      const onDecoded = (raw: string): boolean => {
        const code = extractCode(raw)
        if (!code) return false
        scanningRef.current = false
        toast.success(`Scanned: ${code}`)
        lookupVoucher(code)
        return true
      }

      if ('BarcodeDetector' in window) {
        const detector = new (window as any).BarcodeDetector({ formats: ['qr_code'] })
        const poll = async () => {
          if (!scanningRef.current || !videoRef.current) return
          try {
            const barcodes = await detector.detect(videoRef.current)
            for (const barcode of barcodes) {
              if (onDecoded(barcode.rawValue || '')) return
            }
          } catch { /* ignore detect errors */ }
          if (scanningRef.current) requestAnimationFrame(poll)
        }
        requestAnimationFrame(poll)
      } else {
        // Fallback for browsers without BarcodeDetector (Safari/iOS, Firefox,
        // iOS WKWebView): decode each frame with jsQR via an offscreen canvas.
        const canvas = document.createElement('canvas')
        const ctx = canvas.getContext('2d', { willReadFrequently: true })
        const poll = () => {
          if (!scanningRef.current || !videoRef.current || !ctx) return
          const v = videoRef.current
          if (v.readyState >= 2 && v.videoWidth > 0) {
            canvas.width = v.videoWidth
            canvas.height = v.videoHeight
            ctx.drawImage(v, 0, 0, canvas.width, canvas.height)
            const { data, width, height } = ctx.getImageData(0, 0, canvas.width, canvas.height)
            const result = jsQR(data, width, height, { inversionAttempts: 'dontInvert' })
            if (result?.data && onDecoded(result.data)) return
          }
          if (scanningRef.current) setTimeout(poll, 250)
        }
        setTimeout(poll, 250)
      }
    } catch (err) {
      toast.error('Camera access denied or unavailable')
    }
  }, [lookupVoucher])

  useEffect(() => {
    return () => { stopCamera() }
  }, [stopCamera])

  const redeemMutation = useMutation({
    mutationFn: (data: { voucher_code: string; redemption_notes?: string }) =>
      api.post<{ success: boolean; voucher: Voucher }>('/api/vouchers/redeem-by-code', data),
    onSuccess: (result) => {
      toast.success(`Voucher ${result.voucher.voucher_code} redeemed!`)
      setScannedVoucher(result.voucher)
      setRedeemNotes('')
    },
    onError: (err: unknown) => {
      toast.error(err instanceof Error ? err.message : 'Failed to redeem')
    },
  })

  const handleManualLookup = () => {
    const code = manualCode.trim().toUpperCase()
    if (!code) return
    lookupVoucher(code)
  }

  const canRedeem = scannedVoucher?.status === 'active'

  return (
    <div className="mx-auto max-w-lg space-y-6 p-6">
      <h1 className="text-2xl font-bold">Redeem Voucher</h1>
      <p className="text-sm text-muted-foreground">Scan a voucher QR code or enter the code manually.</p>

      {/* Mode toggle */}
      <div className="flex gap-2">
        <Button variant={mode === 'scan' ? 'default' : 'outline'} size="sm" onClick={() => { setMode('scan'); setScannedVoucher(null); setLookupError('') }}>
          <Camera className="mr-1 h-4 w-4" />Scan QR
        </Button>
        <Button variant={mode === 'manual' ? 'default' : 'outline'} size="sm" onClick={() => { setMode('manual'); stopCamera(); setScannedVoucher(null); setLookupError('') }}>
          <Keyboard className="mr-1 h-4 w-4" />Enter Code
        </Button>
      </div>

      {/* Scanner */}
      {mode === 'scan' && !scannedVoucher && (
        <div className="space-y-3">
          <div className="relative aspect-square w-full overflow-hidden rounded-lg border bg-black">
            <video ref={videoRef} className="h-full w-full object-cover" playsInline muted />
            {!cameraActive && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
                <CameraOff className="h-12 w-12 text-muted-foreground" />
                <Button onClick={startCamera}>Start Camera</Button>
              </div>
            )}
            {cameraActive && (
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div className="h-48 w-48 border-2 border-white/60 rounded-lg" />
              </div>
            )}
          </div>
          {cameraActive && (
            <Button variant="outline" size="sm" className="w-full" onClick={stopCamera}>
              Stop Camera
            </Button>
          )}
        </div>
      )}

      {/* Manual entry */}
      {mode === 'manual' && !scannedVoucher && (
        <div className="space-y-3">
          <div className="grid gap-1.5">
            <Label>Voucher Code</Label>
            <Input
              value={manualCode}
              onChange={(e) => setManualCode(e.target.value.toUpperCase())}
              placeholder="e.g. VCH-202606-ABC123"
              onKeyDown={(e) => e.key === 'Enter' && handleManualLookup()}
            />
          </div>
          <Button onClick={handleManualLookup} className="w-full">Look Up</Button>
        </div>
      )}

      {/* Lookup error */}
      {lookupError && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <XCircle className="h-5 w-5 shrink-0" />
          {lookupError}
        </div>
      )}

      {/* Voucher detail card */}
      {scannedVoucher && (
        <div className="rounded-lg border p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold font-mono">{scannedVoucher.voucher_code}</h2>
            <Badge variant="outline" className={STATUS_COLORS[scannedVoucher.status] || ''}>
              {scannedVoucher.status.replace('_', ' ')}
            </Badge>
          </div>

          <div className="grid grid-cols-2 gap-2 text-sm">
            <div><span className="text-muted-foreground">Client:</span> {scannedVoucher.client_name}</div>
            <div><span className="text-muted-foreground">Contract:</span> {scannedVoucher.contract_number}</div>
            <div><span className="text-muted-foreground">VIN:</span> <span className="font-mono">{scannedVoucher.car_vin}</span></div>
            <div><span className="text-muted-foreground">Type:</span> {scannedVoucher.voucher_type.replace(/_/g, ' ')}</div>
            <div><span className="text-muted-foreground">Issued:</span> {scannedVoucher.issued_at || '—'}</div>
            <div><span className="text-muted-foreground">Expires:</span> {scannedVoucher.expires_at || '—'}</div>
          </div>

          {scannedVoucher.status === 'redeemed' && (
            <div className="flex items-center gap-2 rounded bg-gray-100 p-3 text-sm">
              <CheckCircle2 className="h-5 w-5 text-gray-500" />
              <span>Already redeemed{scannedVoucher.redeemed_by_name ? ` by ${scannedVoucher.redeemed_by_name}` : ''} on {scannedVoucher.redeemed_at?.slice(0, 10) || '—'}</span>
            </div>
          )}

          {scannedVoucher.status === 'expired' && (
            <div className="flex items-center gap-2 rounded bg-red-50 p-3 text-sm text-red-700">
              <AlertTriangle className="h-5 w-5" />
              <span>This voucher has expired</span>
            </div>
          )}

          {canRedeem && (
            <div className="space-y-3 border-t pt-3">
              <div className="grid gap-1.5">
                <Label>Redemption Notes (optional)</Label>
                <Textarea value={redeemNotes} onChange={(e) => setRedeemNotes(e.target.value)} placeholder="Notes..." />
              </div>
              <Button
                className="w-full"
                onClick={() => redeemMutation.mutate({ voucher_code: scannedVoucher.voucher_code, redemption_notes: redeemNotes || undefined })}
                disabled={redeemMutation.isPending}
              >
                {redeemMutation.isPending ? 'Redeeming...' : 'Confirm Redeem'}
              </Button>
            </div>
          )}

          <Button variant="outline" size="sm" className="w-full" onClick={() => { setScannedVoucher(null); setRedeemNotes(''); setLookupError('') }}>
            Scan Another
          </Button>
        </div>
      )}
    </div>
  )
}
