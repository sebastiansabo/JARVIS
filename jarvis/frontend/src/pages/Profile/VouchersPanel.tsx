import { useState, useMemo, lazy, Suspense } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { FileText, ScanLine, ArrowLeft, Plus } from 'lucide-react'
import { useAuthStore } from '@/stores/authStore'
import { FormRenderer } from '@/components/forms/FormRenderer'
import { formsApi } from '@/api/forms'
import { api } from '@/api/client'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { vouchersApi } from '@/api/vouchers'
import type { Voucher } from '@/types/vouchers'

const VoucherRedeem = lazy(() => import('@/pages/Public/VoucherRedeem'))

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
  const user = useAuthStore((s) => s.user)
  const queryClient = useQueryClient()
  const perms = user?.permissions || {}
  const canIssue = !user?.permissions || (perms['vouchers.form.view'] ?? true)
  const canRedeem = !user?.permissions || (perms['vouchers.accounting.redeem'] ?? true)

  const { data: vouchers = [], isLoading } = useQuery({
    queryKey: ['my-vouchers'],
    queryFn: () => vouchersApi.myVouchers(),
  })

  const { data: formData } = useQuery({
    queryKey: ['voucher-form-schema'],
    queryFn: () => vouchersApi.getFormSchema(),
    enabled: showIssue,
    staleTime: 5 * 60_000,
  })

  const { data: sigStatus } = useQuery({
    queryKey: ['voucher-sig-status'],
    queryFn: () => api.get<{ has_signature: boolean }>('/api/vouchers/signature-status'),
    enabled: showIssue,
    staleTime: 60_000,
  })

  const submitMutation = useMutation({
    mutationFn: async (answers: Record<string, unknown>) => {
      if (!formData?.id) throw new Error('Form not loaded')
      if (answers.f_signature && typeof answers.f_signature === 'string') {
        await api.put('/profile/api/signature', { signature: answers.f_signature })
      }
      const { f_signature: _, ...formAnswers } = answers
      return formsApi.submitInternal(formData.id, formAnswers)
    },
    onSuccess: () => {
      toast.success('Voucher submitted for approval!')
      setShowIssue(false)
      queryClient.invalidateQueries({ queryKey: ['my-vouchers'] })
    },
    onError: (err: unknown) => {
      toast.error(err instanceof Error ? err.message : 'Submission failed')
    },
  })

  const issueSchema = useMemo(() => {
    if (!formData?.schema) return null
    const contextFields: typeof formData.schema = [
      { id: 'f_company', type: 'company_select' as any, label: 'Company', required: true, order: -2 },
      { id: 'f_department', type: 'department_select' as any, label: 'Department', required: false, order: -1, config: { companyField: 'f_company' } },
    ]
    const approverField: typeof formData.schema[0] = {
      id: 'f_approver', type: 'user_select' as any, label: 'Send for Approval to', required: false,
      placeholder: 'Leave empty for direct manager', order: 98,
    }
    let schema = [...contextFields, ...formData.schema, approverField]
    if (sigStatus && !sigStatus.has_signature) {
      schema = [...schema, { id: 'f_signature', type: 'signature' as const, label: 'Your Signature', required: true, order: 99 }]
    }
    return schema
  }, [formData?.schema, sigStatus])

  if (showRedeem) {
    return (
      <div className="space-y-3">
        <Button variant="ghost" size="sm" onClick={() => setShowRedeem(false)}>
          <ArrowLeft className="mr-1 h-4 w-4" />Back to My Vouchers
        </Button>
        <Suspense fallback={<div className="py-8 text-center text-muted-foreground">Loading...</div>}>
          <VoucherRedeem />
        </Suspense>
      </div>
    )
  }

  if (showIssue) {
    return (
      <div className="space-y-3">
        <Button variant="ghost" size="sm" onClick={() => setShowIssue(false)}>
          <ArrowLeft className="mr-1 h-4 w-4" />Back to My Vouchers
        </Button>
        <div className="rounded-lg border p-6">
          {issueSchema ? (
            <FormRenderer
              schema={issueSchema}
              onSubmit={(answers) => submitMutation.mutate(answers)}
              submitting={submitMutation.isPending}
              submitLabel="Issue Voucher"
              defaultValues={{ f_company: user?.company || '', f_department: user?.department || '' }}
            />
          ) : (
            <div className="py-8 text-center text-muted-foreground">Loading form...</div>
          )}
        </div>
      </div>
    )
  }

  if (isLoading) return <div className="py-8 text-center text-muted-foreground">Loading...</div>

  return (
    <>
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-muted-foreground">{vouchers.length} voucher{vouchers.length !== 1 ? 's' : ''}</span>
        <div className="flex gap-2">
          {canRedeem && (
            <Button variant="outline" size="sm" onClick={() => setShowRedeem(true)}>
              <ScanLine className="mr-1 h-4 w-4" />Redeem
            </Button>
          )}
          {canIssue && (
            <Button size="sm" onClick={() => setShowIssue(true)}>
              <Plus className="mr-1 h-4 w-4" />Issue
            </Button>
          )}
        </div>
      </div>

      {vouchers.length === 0 ? (
        <div className="py-8 text-center text-muted-foreground">No vouchers issued yet.</div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Code</TableHead>
                <TableHead>Client</TableHead>
                <TableHead>Contract</TableHead>
                <TableHead>VIN</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Benefit</TableHead>
                <TableHead>Issued</TableHead>
                <TableHead>Expires</TableHead>
                <TableHead>Days Left</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {vouchers.map((v) => (
                <TableRow key={v.id} className={`cursor-pointer hover:bg-muted/50 ${expiringClass(v)}`} onClick={() => setSelected(v)}>
                  <TableCell className="font-mono text-xs">{v.voucher_code}</TableCell>
                  <TableCell>{v.client_name}</TableCell>
                  <TableCell>{v.contract_number}</TableCell>
                  <TableCell className="font-mono text-xs">{v.car_vin}</TableCell>
                  <TableCell>{v.voucher_type.replace(/_/g, ' ')}</TableCell>
                  <TableCell>{v.benefit_display}</TableCell>
                  <TableCell>{v.issued_at || '—'}</TableCell>
                  <TableCell>{v.expires_at || '—'}</TableCell>
                  <TableCell>
                    {v.days_remaining !== null && v.days_remaining !== undefined ? (
                      <span className={v.days_remaining <= 30 ? 'text-orange-500 font-medium' : ''}>{v.days_remaining}d</span>
                    ) : '—'}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={STATUS_COLORS[v.status] || ''}>{v.status.replace('_', ' ')}</Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={!!selected} onOpenChange={() => setSelected(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{selected?.voucher_code}</DialogTitle>
          </DialogHeader>
          {selected && (
            <div className="space-y-2 text-sm">
              <div className="grid grid-cols-2 gap-2">
                <div><span className="text-muted-foreground">Client:</span> {selected.client_name}</div>
                <div><span className="text-muted-foreground">Contract:</span> {selected.contract_number}</div>
                <div><span className="text-muted-foreground">VIN:</span> <span className="font-mono">{selected.car_vin}</span></div>
                <div><span className="text-muted-foreground">Type:</span> {selected.voucher_type.replace(/_/g, ' ')}</div>
                <div><span className="text-muted-foreground">Benefit:</span> {selected.benefit_display}</div>
                <div><span className="text-muted-foreground">Validity:</span> {selected.validity_months} months</div>
                <div><span className="text-muted-foreground">Issued:</span> {selected.issued_at || '—'}</div>
                <div><span className="text-muted-foreground">Expires:</span> {selected.expires_at || '—'}</div>
                <div><span className="text-muted-foreground">Status:</span> <Badge variant="outline" className={STATUS_COLORS[selected.status] || ''}>{selected.status.replace('_', ' ')}</Badge></div>
                {selected.approver_name && <div><span className="text-muted-foreground">Approver:</span> {selected.approver_name}</div>}
              </div>
              {selected.notes && <div><span className="text-muted-foreground">Notes:</span> {selected.notes}</div>}
              {selected.redemption_notes && <div><span className="text-muted-foreground">Redemption notes:</span> {selected.redemption_notes}</div>}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" asChild>
              <a href={vouchersApi.pdfUrl(selected?.id ?? 0)} download target="_blank" rel="noopener">
                <FileText className="mr-1 h-4 w-4" />Download PDF
              </a>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
