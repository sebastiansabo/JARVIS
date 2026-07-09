import { useState, lazy, Suspense } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus, Download, FileText, ScanLine, Send, ArrowLeft, Pencil, Copy, Trash2, RotateCcw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
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
  DialogDescription,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { ColumnToggle, useColumnState, type ColumnDef } from '@/components/shared/ColumnToggle'
import { FormRenderer } from '@/components/forms/FormRenderer'
import { useVoucherSchema } from '@/hooks/useVoucherSchema'
import { formsApi } from '@/api/forms'
import { api } from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { vouchersApi } from '@/api/vouchers'
import { organizationApi } from '@/api/organization'
import type { Voucher, VoucherSummary } from '@/types/vouchers'

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  pending_approval: 'bg-yellow-100 text-yellow-800',
  approved: 'bg-blue-100 text-blue-800',
  active: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  redeemed: 'bg-gray-200 text-gray-600',
  expired: 'bg-red-50 text-red-600',
  archived: 'bg-gray-100 text-gray-500',
}

function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={STATUS_COLORS[status] || ''}>
      {status.replace('_', ' ')}
    </Badge>
  )
}

function SummaryBar({ summary }: { summary: VoucherSummary }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
      <div className="rounded-lg border p-3 text-center">
        <div className="text-2xl font-bold text-green-600">{summary.active_count}</div>
        <div className="text-xs text-muted-foreground">Active</div>
      </div>
      <div className="rounded-lg border p-3 text-center">
        <div className="text-2xl font-bold text-orange-500">{summary.expiring_soon_count}</div>
        <div className="text-xs text-muted-foreground">Expiring Soon</div>
      </div>
      <div className="rounded-lg border p-3 text-center">
        <div className="text-2xl font-bold text-blue-600">{summary.redeemed_this_month}</div>
        <div className="text-xs text-muted-foreground">Redeemed (month)</div>
      </div>
      <div className="rounded-lg border p-3 text-center">
        <div className="text-2xl font-bold text-red-500">{summary.expired_count}</div>
        <div className="text-xs text-muted-foreground">Expired</div>
      </div>
      <div className="rounded-lg border p-3 text-center">
        <div className="text-2xl font-bold">{Number(summary.total_active_value).toLocaleString()} LEI</div>
        <div className="text-xs text-muted-foreground">Active Value</div>
      </div>
    </div>
  )
}

const RedeemScan = lazy(() => import('./RedeemScan'))

export default function Vouchers() {
  const queryClient = useQueryClient()
  const [view, setView] = useState<'tracking' | 'issue' | 'redeem'>('tracking')
  const [activeTab, setActiveTab] = useState<'active' | 'archive' | 'deleted'>('active')

  const [companyFilter, setCompanyFilter] = useState('__all__')
  const [statusFilter, setStatusFilter] = useState('__all__')
  const [typeFilter, setTypeFilter] = useState('__all__')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const { data: companies = [] } = useQuery({
    queryKey: ['companies-vat'],
    queryFn: () => organizationApi.getCompaniesVat(),
    staleTime: 10 * 60_000,
  })

  const [redeemVoucher, setRedeemVoucher] = useState<Voucher | null>(null)
  const [redeemNotes, setRedeemNotes] = useState('')

  const [detailVoucher, setDetailVoucher] = useState<Voucher | null>(null)
  const [sendEmail, setSendEmail] = useState('')
  const [showSendModal, setShowSendModal] = useState<Voucher | null>(null)

  const deletedView = activeTab === 'deleted'

  const buildParams = () => {
    const p: Record<string, string> = {}
    if (companyFilter !== '__all__') p.company_id = companyFilter
    if (statusFilter !== '__all__') p.status = statusFilter
    if (typeFilter !== '__all__') p.voucher_type = typeFilter
    if (dateFrom) p.date_from = dateFrom
    if (dateTo) p.date_to = dateTo
    if (deletedView) p.deleted = '1'
    return p
  }

  const { data, isLoading } = useQuery({
    queryKey: ['vouchers-accounting', companyFilter, statusFilter, typeFilter, dateFrom, dateTo, deletedView],
    queryFn: () => vouchersApi.accountingList(buildParams()),
  })

  const allVouchers = data?.vouchers ?? []
  const summary = data?.summary ?? { active_count: 0, expiring_soon_count: 0, redeemed_this_month: 0, expired_count: 0, total_active_value: 0 }

  const vouchers = deletedView
    ? allVouchers
    : allVouchers.filter((v) => activeTab === 'archive' ? v.status === 'archived' : v.status !== 'archived')
  const archivedCount = deletedView ? 0 : allVouchers.filter((v) => v.status === 'archived').length

  const [editVoucher, setEditVoucher] = useState<Voucher | null>(null)
  const [editForm, setEditForm] = useState({ client_name: '', contract_number: '', car_vin: '', notes: '' })

  const user = useAuthStore((s) => s.user)
  const perms = user?.permissions || {}
  const isAdmin = !user?.permissions || user?.role_name?.toLowerCase() === 'admin'
  const canEdit = isAdmin || perms['vouchers.accounting.edit']
  const canReissue = isAdmin || perms['vouchers.accounting.reissue']
  // Delete is admin-only (soft delete). Matches backend gate on role_name.
  const canDelete = ['admin', 'superadmin'].includes(user?.role_name?.toLowerCase() ?? '')

  const redeemMutation = useMutation({
    mutationFn: ({ id, notes }: { id: number; notes?: string }) => vouchersApi.redeem(id, notes),
    onSuccess: () => {
      toast.success('Voucher redeemed')
      setRedeemVoucher(null)
      setRedeemNotes('')
      queryClient.invalidateQueries({ queryKey: ['vouchers-accounting'] })
    },
    onError: (err: unknown) => {
      toast.error(err instanceof Error ? err.message : 'Failed to redeem')
    },
  })

  const editMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, string> }) => vouchersApi.editVoucher(id, data),
    onSuccess: () => {
      toast.success('Voucher updated')
      setEditVoucher(null)
      queryClient.invalidateQueries({ queryKey: ['vouchers-accounting'] })
    },
    onError: (err: unknown) => toast.error(err instanceof Error ? err.message : 'Failed to update'),
  })

  const reissueMutation = useMutation({
    mutationFn: (id: number) => vouchersApi.reissueVoucher(id),
    onSuccess: (res) => {
      toast.success(`Reissued as ${res.voucher.voucher_code}`)
      queryClient.invalidateQueries({ queryKey: ['vouchers-accounting'] })
    },
    onError: (err: unknown) => toast.error(err instanceof Error ? err.message : 'Failed to reissue'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => vouchersApi.deleteVoucher(id),
    onSuccess: () => {
      toast.success('Voucher deleted')
      queryClient.invalidateQueries({ queryKey: ['vouchers-accounting'] })
    },
    onError: (err: unknown) => toast.error(err instanceof Error ? err.message : 'Failed to delete'),
  })

  const restoreMutation = useMutation({
    mutationFn: (id: number) => vouchersApi.restoreVoucher(id),
    onSuccess: () => {
      toast.success('Voucher restored')
      queryClient.invalidateQueries({ queryKey: ['vouchers-accounting'] })
    },
    onError: (err: unknown) => toast.error(err instanceof Error ? err.message : 'Failed to restore'),
  })

  const allColumns: ColumnDef<Voucher>[] = [
    { key: 'code', label: 'Code', className: 'font-mono text-xs', render: (v) => v.voucher_code },
    { key: 'issuer', label: 'Issuer', render: (v) => v.issued_by_name || '' },
    { key: 'client', label: 'Client', render: (v) => v.client_name },
    { key: 'contract', label: 'Contract', render: (v) => v.contract_number },
    { key: 'vin', label: 'VIN', className: 'font-mono text-xs', render: (v) => v.car_vin },
    { key: 'type', label: 'Type', render: (v) => v.voucher_type.replace(/_/g, ' ') },
    { key: 'benefit', label: 'Benefit', render: (v) => v.benefit_display },
    { key: 'issued', label: 'Issued', render: (v) => v.issued_at || '—' },
    { key: 'expires', label: 'Expires', render: (v) => <>{v.expires_at || '—'}{v.days_remaining != null && v.days_remaining <= 30 && v.days_remaining > 0 && <span className="ml-1 text-xs text-orange-500">({v.days_remaining}d)</span>}</> },
    { key: 'approver', label: 'Approver', render: (v) => v.approver_name || '—' },
    { key: 'status', label: 'Status', render: (v) => <StatusBadge status={v.status} /> },
    { key: 'actions', label: 'Actions', render: (v) => deletedView ? (
      <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
        {canDelete && (
          <Button size="sm" variant="outline" onClick={() => { if (confirm(`Restore voucher ${v.voucher_code}?`)) restoreMutation.mutate(v.id) }}>
            <RotateCcw className="h-3.5 w-3.5 mr-1" />Restore
          </Button>
        )}
      </div>
    ) : (
      <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
        {v.status === 'active' && (
          <Button size="sm" variant="outline" onClick={() => { setRedeemVoucher(v); setRedeemNotes('') }}>Redeem</Button>
        )}
        {canEdit && (v.status === 'active' || v.status === 'pending_approval') && (
          <Button size="sm" variant="ghost" onClick={() => { setEditVoucher(v); setEditForm({ client_name: v.client_name, contract_number: v.contract_number, car_vin: v.car_vin, notes: v.notes || '' }) }}>
            <Pencil className="h-3.5 w-3.5" />
          </Button>
        )}
        {canReissue && ['archived', 'expired', 'rejected', 'redeemed'].includes(v.status) && (
          <Button size="sm" variant="ghost" onClick={() => { if (confirm(`Reissue voucher ${v.voucher_code}?`)) reissueMutation.mutate(v.id) }}>
            <Copy className="h-3.5 w-3.5" />
          </Button>
        )}
        {canDelete && (
          <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" onClick={() => { if (confirm(`Delete voucher ${v.voucher_code}? It will be removed from the list.`)) deleteMutation.mutate(v.id) }}>
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    )},
  ]

  const defaultCols = ['code', 'client', 'contract', 'vin', 'type', 'benefit', 'issued', 'expires', 'issuer', 'approver', 'status', 'actions']
  const allColKeys = allColumns.map((c) => c.key)
  const { visibleColumns, setVisibleColumns, defaultColumns: defaultColState } = useColumnState('voucherColumns', defaultCols, allColKeys)

  const { data: formData } = useQuery({
    queryKey: ['voucher-form-schema'],
    queryFn: () => vouchersApi.getFormSchema(),
    enabled: view === 'issue',
    staleTime: 5 * 60_000,
  })

  const { schema: issueSchema, defaultValues: voucherDefaults, needsSignatureSave } =
    useVoucherSchema(formData?.schema ?? [], 'voucher-issuance')

  const submitFormMutation = useMutation({
    mutationFn: async (answers: Record<string, unknown>) => {
      if (!formData?.id) throw new Error('Form not loaded')
      if (needsSignatureSave && answers.f_signature && typeof answers.f_signature === 'string') {
        await api.put('/profile/api/signature', { signature: answers.f_signature })
      }
      const { f_signature: _, ...formAnswers } = answers
      return formsApi.submitInternal(formData.id, formAnswers)
    },
    onSuccess: () => {
      toast.success('Voucher submitted for approval!')
      setView('tracking')
      queryClient.invalidateQueries({ queryKey: ['vouchers-accounting'] })
    },
    onError: (err: unknown) => {
      toast.error(err instanceof Error ? err.message : 'Submission failed')
    },
  })

  if (view === 'issue') {
    return (
      <div className="space-y-4 p-6">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => setView('tracking')}>
            <ArrowLeft className="mr-1 h-4 w-4" />Back
          </Button>
          <h1 className="text-2xl font-bold">Issue Voucher</h1>
        </div>
        <div className="mx-auto max-w-2xl rounded-lg border p-6">
          {issueSchema.length ? (
            <FormRenderer
              schema={issueSchema}
              onSubmit={(answers) => submitFormMutation.mutate(answers)}
              submitting={submitFormMutation.isPending}
              submitLabel="Issue Voucher"
              defaultValues={voucherDefaults}
            />
          ) : (
            <div className="py-8 text-center text-muted-foreground">Loading form...</div>
          )}
        </div>
      </div>
    )
  }

  if (view === 'redeem') {
    return (
      <div className="space-y-4 p-6">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => setView('tracking')}>
            <FileText className="mr-1 h-4 w-4" />Back to Tracking
          </Button>
          <h1 className="text-2xl font-bold">Redeem Voucher</h1>
        </div>
        <Suspense fallback={<div className="py-8 text-center text-muted-foreground">Loading...</div>}>
          <RedeemScan />
        </Suspense>
      </div>
    )
  }

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Vouchers</h1>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" asChild>
            <a href={vouchersApi.exportUrl(buildParams())} download>
              <Download className="mr-1 h-4 w-4" />Export CSV
            </a>
          </Button>
          <Button variant="outline" size="sm" onClick={() => setView('redeem')}>
            <ScanLine className="mr-1 h-4 w-4" />Redeem
          </Button>
          <Button size="sm" onClick={() => setView('issue')}>
            <Plus className="mr-1 h-4 w-4" />Issue
          </Button>
        </div>
      </div>

      {activeTab === 'active' && <SummaryBar summary={summary} />}

      {/* Tabs */}
      <div className="flex gap-1 border-b">
        <button
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${activeTab === 'active' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'}`}
          onClick={() => setActiveTab('active')}
        >
          Active
        </button>
        <button
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${activeTab === 'archive' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'}`}
          onClick={() => setActiveTab('archive')}
        >
          Archive {archivedCount > 0 && <span className="ml-1 text-xs bg-muted px-1.5 py-0.5 rounded-full">{archivedCount}</span>}
        </button>
        {canDelete && (
          <button
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${activeTab === 'deleted' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'}`}
            onClick={() => setActiveTab('deleted')}
          >
            Deleted
          </button>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <Select value={companyFilter} onValueChange={setCompanyFilter}>
          <SelectTrigger className="w-56"><SelectValue placeholder="Company" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All Companies</SelectItem>
            {companies.map((c: { id: number; company: string }) => (
              <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-40"><SelectValue placeholder="Status" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All Statuses</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="pending_approval">Pending</SelectItem>
            <SelectItem value="redeemed">Redeemed</SelectItem>
            <SelectItem value="expired">Expired</SelectItem>
            <SelectItem value="rejected">Rejected</SelectItem>
          </SelectContent>
        </Select>
        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="w-48"><SelectValue placeholder="Type" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All Types</SelectItem>
            <SelectItem value="value">Value (LEI)</SelectItem>
            <SelectItem value="accessory_discount_code">Discount Code</SelectItem>
            <SelectItem value="accessory_percentage">Percentage</SelectItem>
            <SelectItem value="service_items">Service Items</SelectItem>
          </SelectContent>
        </Select>
        <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-40" placeholder="From" />
        <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-40" placeholder="To" />
        <ColumnToggle
          visibleColumns={visibleColumns}
          defaultColumns={defaultColState}
          columnDefs={allColumns as ColumnDef<never>[]}
          onChange={setVisibleColumns}
        />
      </div>

      {/* Table */}
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              {visibleColumns.map((key) => {
                const col = allColumns.find((c) => c.key === key)
                return col ? <TableHead key={key} className={col.className}>{col.label}</TableHead> : null
              })}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow><TableCell colSpan={visibleColumns.length} className="text-center py-8 text-muted-foreground">Loading...</TableCell></TableRow>
            ) : vouchers.length === 0 ? (
              <TableRow><TableCell colSpan={visibleColumns.length} className="text-center py-8 text-muted-foreground">No vouchers found</TableCell></TableRow>
            ) : (
              vouchers.map((v) => (
                <TableRow key={v.id} className="cursor-pointer hover:bg-muted/50" onClick={() => setDetailVoucher(v)}>
                  {visibleColumns.map((key) => {
                    const col = allColumns.find((c) => c.key === key)
                    return col ? <TableCell key={key} className={col.className}>{col.render(v)}</TableCell> : null
                  })}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Edit Modal */}
      <Dialog open={!!editVoucher} onOpenChange={() => setEditVoucher(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Edit Voucher {editVoucher?.voucher_code}</DialogTitle>
            <DialogDescription>Update voucher details</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Client Name</Label>
              <Input value={editForm.client_name} onChange={(e) => setEditForm((f) => ({ ...f, client_name: e.target.value }))} />
            </div>
            <div>
              <Label>Contract Number</Label>
              <Input value={editForm.contract_number} onChange={(e) => setEditForm((f) => ({ ...f, contract_number: e.target.value }))} />
            </div>
            <div>
              <Label>Car VIN</Label>
              <Input value={editForm.car_vin} onChange={(e) => setEditForm((f) => ({ ...f, car_vin: e.target.value }))} maxLength={17} className="font-mono" />
            </div>
            <div>
              <Label>Notes</Label>
              <Textarea value={editForm.notes} onChange={(e) => setEditForm((f) => ({ ...f, notes: e.target.value }))} rows={2} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditVoucher(null)}>Cancel</Button>
            <Button onClick={() => editVoucher && editMutation.mutate({ id: editVoucher.id, data: editForm })} disabled={editMutation.isPending}>
              {editMutation.isPending ? 'Saving...' : 'Save'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Redeem Modal */}
      <Dialog open={!!redeemVoucher} onOpenChange={() => setRedeemVoucher(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Confirm Redemption</DialogTitle>
            <DialogDescription>
              Mark voucher <strong>{redeemVoucher?.voucher_code}</strong> as redeemed?
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="text-sm">
              <div>Client: <strong>{redeemVoucher?.client_name}</strong></div>
              <div>Benefit: <strong>{redeemVoucher?.benefit_display}</strong></div>
            </div>
            <div className="grid gap-1.5">
              <Label>Notes (optional)</Label>
              <Textarea value={redeemNotes} onChange={(e) => setRedeemNotes(e.target.value)} placeholder="Redemption notes" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRedeemVoucher(null)}>Cancel</Button>
            <Button onClick={() => redeemVoucher && redeemMutation.mutate({ id: redeemVoucher.id, notes: redeemNotes })} disabled={redeemMutation.isPending}>
              {redeemMutation.isPending ? 'Redeeming...' : 'Confirm Redeem'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail Modal */}
      <Dialog open={!!detailVoucher} onOpenChange={() => setDetailVoucher(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Voucher Detail — {detailVoucher?.voucher_code}</DialogTitle>
          </DialogHeader>
          {detailVoucher && (
            <div className="space-y-2 text-sm">
              <div className="grid grid-cols-2 gap-2">
                <div><span className="text-muted-foreground">Client:</span> {detailVoucher.client_name}</div>
                <div><span className="text-muted-foreground">Contract:</span> {detailVoucher.contract_number}</div>
                <div><span className="text-muted-foreground">VIN:</span> <span className="font-mono">{detailVoucher.car_vin}</span></div>
                <div><span className="text-muted-foreground">Type:</span> {detailVoucher.voucher_type.replace(/_/g, ' ')}</div>
                <div><span className="text-muted-foreground">Benefit:</span> {detailVoucher.benefit_display}</div>
                <div><span className="text-muted-foreground">Validity:</span> {detailVoucher.validity_months} months</div>
                <div><span className="text-muted-foreground">Issued:</span> {detailVoucher.issued_at || '—'}</div>
                <div><span className="text-muted-foreground">Expires:</span> {detailVoucher.expires_at || '—'}</div>
                <div><span className="text-muted-foreground">Status:</span> <StatusBadge status={detailVoucher.status} /></div>
                <div><span className="text-muted-foreground">Issued by:</span> {detailVoucher.issued_by_name}</div>
                {detailVoucher.approver_name && <div><span className="text-muted-foreground">Approver:</span> {detailVoucher.approver_name}</div>}
                {detailVoucher.redeemed_by_name && <div><span className="text-muted-foreground">Redeemed by:</span> {detailVoucher.redeemed_by_name}</div>}
                {detailVoucher.redeemed_at && <div><span className="text-muted-foreground">Redeemed at:</span> {detailVoucher.redeemed_at}</div>}
              </div>
              {detailVoucher.notes && <div><span className="text-muted-foreground">Notes:</span> {detailVoucher.notes}</div>}
              {detailVoucher.redemption_notes && <div><span className="text-muted-foreground">Redemption notes:</span> {detailVoucher.redemption_notes}</div>}
            </div>
          )}
          <DialogFooter className="flex gap-2">
            <Button variant="outline" asChild>
              <a href={vouchersApi.pdfUrl(detailVoucher?.id ?? 0)} download target="_blank" rel="noopener">
                <FileText className="mr-1 h-4 w-4" />Download PDF
              </a>
            </Button>
            {detailVoucher && detailVoucher.status === 'active' && (
              <Button variant="outline" onClick={() => { setShowSendModal(detailVoucher); setSendEmail((detailVoucher as any).client_email || ''); setDetailVoucher(null) }}>
                <Send className="mr-1 h-4 w-4" />Send to Client
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Send to Client Modal */}
      <Dialog open={!!showSendModal} onOpenChange={() => setShowSendModal(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Send Voucher to Client</DialogTitle>
            <DialogDescription>
              Send voucher <strong>{showSendModal?.voucher_code}</strong> PDF to client via email.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-1.5">
            <Label>Client Email</Label>
            <Input type="email" value={sendEmail} onChange={(e) => setSendEmail(e.target.value)} placeholder="client@email.com" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowSendModal(null)}>Cancel</Button>
            <Button
              disabled={!sendEmail.includes('@')}
              onClick={() => {
                if (showSendModal) {
                  vouchersApi.sendToClient(showSendModal.id, sendEmail).then(() => {
                    toast.success(`Voucher sent to ${sendEmail}`)
                    setShowSendModal(null)
                  }).catch(() => toast.error('Failed to send email'))
                }
              }}
            >
              <Send className="mr-1 h-4 w-4" />Send Email
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
