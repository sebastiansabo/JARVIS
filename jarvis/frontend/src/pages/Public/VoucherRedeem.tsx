import { useState, useRef, useEffect, useCallback, lazy, Suspense } from 'react'
import { useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Camera, CameraOff, Keyboard, CheckCircle2, XCircle, AlertTriangle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { useAuthStore } from '@/stores/authStore'

const SignatureCanvas = lazy(() => import('@/components/shared/SignatureCanvas'))

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-green-100 text-green-800',
  redeemed: 'bg-gray-200 text-gray-600',
  expired: 'bg-red-50 text-red-600',
  pending_approval: 'bg-yellow-100 text-yellow-800',
  rejected: 'bg-red-100 text-red-800',
}

interface VoucherPublic {
  voucher_code: string
  client_name: string
  contract_number: string
  car_vin: string
  voucher_type: string
  value_lei: number | null
  discount_code: string | null
  discount_percentage: number | null
  service_items: string[] | null
  validity_months: number
  status: string
  issued_at: string | null
  expires_at: string | null
  company_name: string | null
  company_vat: string | null
  days_remaining: number | null
}

function benefitDisplay(v: VoucherPublic): string {
  if (v.voucher_type === 'value') return `${v.value_lei} LEI`
  if (v.voucher_type === 'accessory_discount_code') return v.discount_code || ''
  if (v.voucher_type === 'accessory_percentage') return `${v.discount_percentage}%`
  if (v.voucher_type === 'service_items' && Array.isArray(v.service_items)) return v.service_items.join(', ')
  return ''
}

export default function VoucherRedeem() {
  const { code: urlCode } = useParams<{ code?: string }>()
  const user = useAuthStore((s) => s.user)
  const [mode, setMode] = useState<'scan' | 'manual'>(urlCode ? 'manual' : 'scan')
  const [manualCode, setManualCode] = useState(urlCode || '')
  const [voucher, setVoucher] = useState<VoucherPublic | null>(null)
  const [redeemed, setRedeemed] = useState(false)
  const [lookupError, setLookupError] = useState('')
  const [loading, setLoading] = useState(false)
  const [redeemSignature, setRedeemSignature] = useState('')

  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const scanningRef = useRef(false)
  const [cameraActive, setCameraActive] = useState(false)

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
    setVoucher(null)
    setRedeemed(false)
    setLoading(true)
    try {
      const resp = await fetch(`/api/public/vouchers/lookup/${encodeURIComponent(code)}`)
      if (!resp.ok) {
        setLookupError(`Voucher "${code}" not found`)
        return
      }
      const data: VoucherPublic = await resp.json()
      setVoucher(data)
      stopCamera()
    } catch {
      setLookupError('Network error')
    } finally {
      setLoading(false)
    }
  }, [stopCamera])

  // Auto-lookup if code in URL
  useEffect(() => {
    if (urlCode) lookupVoucher(urlCode)
  }, [urlCode, lookupVoucher])

  const startCamera = useCallback(async () => {
    setVoucher(null)
    setLookupError('')
    setRedeemed(false)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
      }
      setCameraActive(true)
      scanningRef.current = true

      if ('BarcodeDetector' in window) {
        const detector = new (window as any).BarcodeDetector({ formats: ['qr_code'] })
        const poll = async () => {
          if (!scanningRef.current || !videoRef.current) return
          try {
            const barcodes = await detector.detect(videoRef.current)
            for (const barcode of barcodes) {
              const raw = barcode.rawValue || ''
              // Support both "voucher:CODE" and "https://.../voucher/CODE" formats
              let voucherCode = ''
              if (raw.startsWith('voucher:')) {
                voucherCode = raw.replace('voucher:', '')
              } else if (raw.includes('/voucher/')) {
                voucherCode = raw.split('/voucher/').pop() || ''
              }
              if (voucherCode) {
                scanningRef.current = false
                toast.success(`Scanned: ${voucherCode}`)
                lookupVoucher(voucherCode)
                return
              }
            }
          } catch { /* ignore */ }
          if (scanningRef.current) requestAnimationFrame(poll)
        }
        requestAnimationFrame(poll)
      }
    } catch {
      toast.error('Camera access denied or unavailable')
    }
  }, [lookupVoucher])

  useEffect(() => () => stopCamera(), [stopCamera])

  const effectiveName = user?.name || ''

  const handleRedeem = async () => {
    if (!voucher || !effectiveName) return
    if (!redeemSignature) { toast.error('Signature is required'); return }
    setLoading(true)
    try {
      const resp = await fetch('/api/public/vouchers/redeem', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voucher_code: voucher.voucher_code, redeemer_name: effectiveName, signature: redeemSignature }),
      })
      const data = await resp.json()
      if (data.success) {
        toast.success('Voucher redeemed!')
        setRedeemed(true)
        setVoucher({ ...voucher, status: 'redeemed' })
      } else {
        toast.error(data.error || 'Failed to redeem')
      }
    } catch {
      toast.error('Network error')
    } finally {
      setLoading(false)
    }
  }

  const canRedeem = voucher?.status === 'active' && !redeemed

  return (
    <div className="min-h-screen bg-gray-50 flex items-start justify-center p-4 pt-12">
      <div className="w-full max-w-md space-y-6">
        {/* Header */}
        <div className="text-center">
          <h1 className="text-2xl font-bold">Voucher Redemption</h1>
          <p className="text-sm text-gray-500 mt-1">Scan the QR code on your voucher or enter the code manually</p>
        </div>

        {/* Mode toggle */}
        {!voucher && (
          <div className="flex gap-2 justify-center">
            <Button variant={mode === 'scan' ? 'default' : 'outline'} size="sm" onClick={() => { setMode('scan'); setLookupError('') }}>
              <Camera className="mr-1 h-4 w-4" />Scan QR
            </Button>
            <Button variant={mode === 'manual' ? 'default' : 'outline'} size="sm" onClick={() => { setMode('manual'); stopCamera(); setLookupError('') }}>
              <Keyboard className="mr-1 h-4 w-4" />Enter Code
            </Button>
          </div>
        )}

        {/* Scanner */}
        {mode === 'scan' && !voucher && (
          <div className="space-y-3">
            <div className="relative aspect-square w-full overflow-hidden rounded-lg border bg-black">
              <video ref={videoRef} className="h-full w-full object-cover" playsInline muted />
              {!cameraActive && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
                  <CameraOff className="h-12 w-12 text-gray-400" />
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
              <Button variant="outline" size="sm" className="w-full" onClick={stopCamera}>Stop Camera</Button>
            )}
          </div>
        )}

        {/* Manual entry */}
        {mode === 'manual' && !voucher && (
          <div className="space-y-3 bg-white rounded-lg border p-4">
            <div className="grid gap-1.5">
              <Label>Voucher Code</Label>
              <Input
                value={manualCode}
                onChange={(e) => setManualCode(e.target.value.toUpperCase())}
                placeholder="VCH-202606-XXXXXX"
                onKeyDown={(e) => e.key === 'Enter' && lookupVoucher(manualCode.trim())}
              />
            </div>
            <Button onClick={() => lookupVoucher(manualCode.trim())} className="w-full" disabled={loading || !manualCode.trim()}>
              {loading ? 'Looking up...' : 'Look Up Voucher'}
            </Button>
          </div>
        )}

        {/* Error */}
        {lookupError && (
          <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            <XCircle className="h-5 w-5 shrink-0" />
            {lookupError}
          </div>
        )}

        {/* Voucher card */}
        {voucher && (
          <div className="bg-white rounded-lg border shadow-sm overflow-hidden">
            {/* Card header */}
            <div className="bg-slate-800 text-white p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-300">VOUCHER</p>
                  <p className="text-lg font-bold font-mono">{voucher.voucher_code}</p>
                </div>
                <Badge variant="outline" className={`${STATUS_COLORS[voucher.status] || ''} border-0`}>
                  {voucher.status.replace('_', ' ').toUpperCase()}
                </Badge>
              </div>
              {voucher.company_name && (
                <p className="text-xs text-slate-300 mt-2">{voucher.company_name}{voucher.company_vat ? ` \u2022 ${voucher.company_vat}` : ''}</p>
              )}
            </div>

            {/* Card body */}
            <div className="p-4 space-y-3">
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div><span className="text-gray-500">Client:</span> <strong>{voucher.client_name}</strong></div>
                <div><span className="text-gray-500">Contract:</span> {voucher.contract_number}</div>
                <div><span className="text-gray-500">VIN:</span> <span className="font-mono text-xs">{voucher.car_vin}</span></div>
                <div><span className="text-gray-500">Type:</span> {voucher.voucher_type.replace(/_/g, ' ')}</div>
              </div>

              <div className="rounded-lg bg-green-50 border border-green-200 p-3 text-center">
                <p className="text-xs text-green-600 font-medium">BENEFIT</p>
                <p className="text-lg font-bold text-green-800">{benefitDisplay(voucher)}</p>
              </div>

              <div className="grid grid-cols-2 gap-2 text-sm">
                <div><span className="text-gray-500">Issued:</span> {voucher.issued_at || '—'}</div>
                <div><span className="text-gray-500">Expires:</span> {voucher.expires_at || '—'}</div>
              </div>

              {voucher.days_remaining !== null && voucher.days_remaining !== undefined && voucher.status === 'active' && voucher.days_remaining <= 30 && (
                <div className="flex items-center gap-2 rounded bg-orange-50 border border-orange-200 p-2 text-sm text-orange-700">
                  <AlertTriangle className="h-4 w-4" />
                  Expires in {voucher.days_remaining} day{voucher.days_remaining !== 1 ? 's' : ''}
                </div>
              )}

              {voucher.status === 'redeemed' && (
                <div className="flex items-center gap-2 rounded bg-gray-100 p-3 text-sm text-gray-600">
                  <CheckCircle2 className="h-5 w-5" />
                  {redeemed ? 'Voucher redeemed successfully!' : 'This voucher has already been redeemed'}
                </div>
              )}

              {voucher.status === 'expired' && (
                <div className="flex items-center gap-2 rounded bg-red-50 p-3 text-sm text-red-700">
                  <AlertTriangle className="h-5 w-5" />
                  This voucher has expired
                </div>
              )}

              {canRedeem && (
                <div className="space-y-3 border-t pt-3">
                  <p className="text-sm text-muted-foreground">Redeeming as: <strong>{user?.name}</strong></p>
                  <div className="grid gap-1.5">
                    <Label>Signature (required)</Label>
                    {redeemSignature ? (
                      <div className="space-y-2">
                        <img src={redeemSignature} alt="Signature" className="max-h-16 border rounded bg-white p-1" />
                        <Button type="button" variant="outline" size="sm" onClick={() => setRedeemSignature('')}>Clear & Re-sign</Button>
                      </div>
                    ) : (
                      <Suspense fallback={<div className="h-[120px] border rounded animate-pulse bg-muted" />}>
                        <SignatureCanvas height={120} onSave={(base64) => setRedeemSignature(base64)} onClear={() => setRedeemSignature('')} />
                      </Suspense>
                    )}
                  </div>
                  <Button className="w-full" onClick={handleRedeem} disabled={loading || !effectiveName || !redeemSignature}>
                    {loading ? 'Redeeming...' : 'Redeem Voucher'}
                  </Button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Scan another */}
        {voucher && (
          <Button variant="outline" className="w-full" onClick={() => { setVoucher(null); setRedeemed(false); setRedeemSignature(''); setManualCode(''); setLookupError('') }}>
            Scan Another Voucher
          </Button>
        )}

        <p className="text-center text-xs text-gray-400">Powered by JARVIS</p>
      </div>
    </div>
  )
}
