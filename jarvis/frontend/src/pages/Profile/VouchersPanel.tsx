import { useState, lazy, Suspense } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { FileText, ScanLine, ArrowLeft, Plus } from 'lucide-react'
import { useAuthStore } from '@/stores/authStore'
import VoucherIssueForm from '@/pages/Accounting/Vouchers/VoucherIssueForm'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { vouchersApi } from '@/api/vouchers'
import type { Voucher } from '@/types/vouchers'

const STATUS_COLORS: Record<string, string> = {
  pending_approval: 'bg-yellow-100 text-yellow-800',
  active: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  redeemed: 'bg-gray-200 text-gray-600',
  expired: 'bg-red-50 text-red-600',
}

function expiringClass(v: Voucher): string {
  if (v.status !== 'active') return ''
  if (v.days_remaining !== null && v.days_remaining !== undefined && v.days_remaining <= 30)
    return 'bg-orange-50'
  return ''
}

export default function VouchersPanel() {
  const [selected, setSelected] = useState<Voucher | null>(null)
  const [showRedeem, setShowRedeem] = useState(false)
  const [showIssue, setShowIssue] = useState(false)
  const [redeemCode, setRedeemCode] = useState('')
  const user = useAuthStore((s) => s.user)
  const queryClient = useQueryClient()
  const perms = user?.permissions || {}
  void (!user?.permissions || (perms['vouchers.form.view'] ?? true))
  void (!user?.permissions || (perms['vouchers.accounting.redeem'] ?? true))

  const { data: vouchers = [], isLoading } = useQuery({
    queryKey: ['my-vouchers'],
    queryFn: () => vouchersApi.myVouchers(),
  })

  if (showRedeem && redeemCode) {
    return <InlineRedeem code={redeemCode} userName={user?.name || ''} onBack={() => { setShowRedeem(false); setRedeemCode('') }} onDone={() => { setShowRedeem(false); setRedeemCode(''); queryClient.invalidateQueries({ queryKey: ['my-vouchers'] }) }} />
  }

  if (showIssue) {
    return (
      <div className="space-y-3">
        <Button variant="ghost" size="sm" onClick={() => setShowIssue(false)}>
          <ArrowLeft className="mr-1 h-4 w-4" />Back to My Vouchers
        </Button>
        <div className="rounded-lg border p-6">
          <VoucherIssueForm
            onSuccess={() => {
              setShowIssue(false)
              queryClient.invalidateQueries({ queryKey: ['my-vouchers'] })
            }}
          />
        </div>
      </div>
    )
  }

  if (isLoading) return <div className="py-8 text-center text-muted-foreground">Loading...</div>

  return (
    <>
      <div className="mb-3 flex justify-end">
        <Button size="sm" onClick={() => setShowIssue(true)}>
          <Plus className="mr-1 h-4 w-4" />Issue Voucher
        </Button>
      </div>

      {vouchers.length === 0 ? (
        <div className="py-8 text-center text-muted-foreground">No vouchers issued yet.</div>
      ) : (
        <div className="rounded-md border divide-y">
          {vouchers.map((v) => {
            const isOpen = selected?.id === v.id
            return (
              <div key={v.id}>
                <button
                  type="button"
                  className={`w-full text-left hover:bg-muted/30 transition-colors ${expiringClass(v)}`}
                  onClick={() => setSelected(isOpen ? null : v)}
                >
                  <div className="flex items-center justify-between px-4 py-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{v.client_name}</p>
                      <p className="text-[10px] text-muted-foreground">{v.voucher_code}</p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0 ml-3">
                      <Badge variant="outline" className={`text-[10px] ${STATUS_COLORS[v.status] || ''}`}>{v.status.replace('_', ' ')}</Badge>
                      <span className="text-sm font-semibold tabular-nums">{v.benefit_display}</span>
                    </div>
                  </div>
                </button>
                {isOpen && (
                  <div className="px-4 pb-3 space-y-3">
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
                      <div><span className="text-muted-foreground">Contract:</span> {v.contract_number}</div>
                      <div><span className="text-muted-foreground">VIN:</span> <span className="font-mono">{v.car_vin}</span></div>
                      <div><span className="text-muted-foreground">Issued:</span> {v.issued_at || '—'}</div>
                      <div><span className="text-muted-foreground">Expires:</span> {v.expires_at || '—'}</div>
                      <div><span className="text-muted-foreground">Type:</span> {v.voucher_type.replace(/_/g, ' ')}</div>
                      <div><span className="text-muted-foreground">Days left:</span> {v.days_remaining != null ? <span className={v.days_remaining <= 30 ? 'text-orange-500 font-medium' : ''}>{v.days_remaining}d</span> : '—'}</div>
                      <div><span className="text-muted-foreground">Issuer:</span> {(v as any).issued_by_name || '—'}</div>
                      <div><span className="text-muted-foreground">Approver:</span> {(v as any).approver_name || '—'}</div>
                    </div>
                    {v.notes && <p className="text-xs text-muted-foreground">{v.notes}</p>}
                    <div className="flex gap-2">
                      {v.status === 'approved' && (
                        <Button
                          size="sm"
                          className="h-9 bg-emerald-600 hover:bg-emerald-700 text-white"
                          onClick={(e) => { e.stopPropagation(); setRedeemCode(v.voucher_code); setShowRedeem(true) }}
                        >
                          <ScanLine className="mr-1 h-3.5 w-3.5" />Redeem
                        </Button>
                      )}
                      <Button size="sm" variant="outline" className="h-9" asChild>
                        <a href={vouchersApi.pdfUrl(v.id)} download target="_blank" rel="noopener">
                          <FileText className="mr-1 h-3.5 w-3.5" />PDF
                        </a>
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </>
  )
}

// ─── Inline Redeem (no page navigation) ─────────────────

const SignatureCanvas = lazy(() => import('@/components/shared/SignatureCanvas'))

function InlineRedeem({ code, userName, onBack, onDone }: { code: string; userName: string; onBack: () => void; onDone: () => void }) {
  const [sig, setSig] = useState('')
  const [loading, setLoading] = useState(false)

  const voucher = useQuery({
    queryKey: ['voucher-lookup', code],
    queryFn: () => fetch(`/api/public/vouchers/lookup/${encodeURIComponent(code)}`).then(r => r.ok ? r.json() : null),
  })

  const v = voucher.data

  const handleRedeem = async () => {
    if (!sig) { toast.error('Please sign first'); return }
    setLoading(true)
    try {
      const res = await fetch('/api/public/vouchers/redeem', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voucher_code: code, redeemer_name: userName, signature: sig }),
      })
      const data = await res.json()
      if (data.success) {
        toast.success('Voucher redeemed!')
        onDone()
      } else {
        toast.error(data.error || 'Failed to redeem')
      }
    } catch {
      toast.error('Network error')
    } finally {
      setLoading(false)
    }
  }

  if (voucher.isLoading) return <div className="py-12 text-center text-muted-foreground text-sm">Loading voucher...</div>
  if (!v) return <div className="py-12 text-center text-muted-foreground text-sm">Voucher not found</div>

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold">Redeem Voucher</h3>
        <Button variant="ghost" size="sm" onClick={onBack}>Cancel</Button>
      </div>

      {/* Voucher summary */}
      <div className="rounded-lg border bg-muted/20 p-3 space-y-1">
        <div className="flex items-center justify-between">
          <span className="font-mono text-xs text-muted-foreground">{v.voucher_code}</span>
          <span className="text-sm font-bold text-emerald-600">
            {v.value_lei ? `${v.value_lei} LEI` : v.discount_percentage ? `${v.discount_percentage}%` : v.discount_code || ''}
          </span>
        </div>
        <p className="text-sm font-medium">{v.client_name}</p>
        <p className="text-xs text-muted-foreground">{v.contract_number} &middot; {v.car_vin}</p>
      </div>

      {/* Signature */}
      <div className="space-y-1.5">
        <p className="text-xs text-muted-foreground">Redeeming as <strong>{userName}</strong> — sign to confirm:</p>
        {sig ? (
          <div className="space-y-2">
            <img src={sig} alt="Signature" className="h-16 border rounded bg-white p-1" />
            <Button variant="outline" size="sm" className="h-9" onClick={() => setSig('')}>Re-sign</Button>
          </div>
        ) : (
          <Suspense fallback={<div className="h-[120px] border rounded animate-pulse bg-muted" />}>
            <SignatureCanvas height={120} onSave={setSig} onClear={() => setSig('')} saveLabel="Confirm" />
          </Suspense>
        )}
      </div>

      {/* Redeem button */}
      {sig && (
        <Button
          className="w-full h-12 text-base bg-emerald-600 hover:bg-emerald-700 text-white"
          onClick={handleRedeem}
          disabled={loading}
        >
          {loading ? 'Redeeming...' : 'Redeem Voucher'}
        </Button>
      )}
    </div>
  )
}
