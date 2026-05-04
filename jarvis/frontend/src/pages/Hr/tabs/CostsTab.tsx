import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/shared/EmptyState'
import {
  FileText, Link2, Search, Check, Plus, Pencil, Trash2, Receipt,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { coursesApi } from '@/api/courses'
import { invoicesApi } from '@/api/invoices'
import { toast } from 'sonner'
import { useDebounce } from '@/lib/utils'
import type { Course, EnrollmentCost, CourseTransaction } from '@/types/courses'
import type { Invoice } from '@/types/invoices'
import { fmt, fmtDate } from './utils'

export function CostsTab({ course }: { course: Course }) {
  const queryClient = useQueryClient()
  const [linkDialogOpen, setLinkDialogOpen] = useState(false)
  const [spendDialogOpen, setSpendDialogOpen] = useState(false)
  const [editTx, setEditTx] = useState<CourseTransaction | null>(null)

  // Enrollment cost breakdown
  const { data: costData, isLoading: costsLoading } = useQuery({
    queryKey: ['course-enrollment-costs', course.id],
    queryFn: () => coursesApi.getEnrollmentCosts(course.id),
  })

  // Transactions (spending log)
  const { data: txData, isLoading: txLoading } = useQuery({
    queryKey: ['course-transactions', course.id],
    queryFn: () => coursesApi.getTransactions(course.id),
  })

  const deleteTxMut = useMutation({
    mutationFn: (txId: number) => coursesApi.deleteTransaction(course.id, txId),
    onSuccess: () => {
      invalidate()
      toast.success('Transaction deleted')
    },
  })

  const costs: EnrollmentCost[] = costData?.costs ?? []
  const transactions: CourseTransaction[] = txData?.transactions ?? []
  const totals = txData?.totals

  const loading = costsLoading || txLoading
  if (loading) return <Skeleton className="h-32 w-full" />

  // Budget computation: actual cost = net spend from transactions
  const actualCost = totals?.net_cost ?? 0
  const budget = Number(course.budget) || 0
  const variance = budget - actualCost
  const execPct = budget > 0 ? Math.round((actualCost / budget) * 100) : 0

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['course-transactions', course.id] })
    queryClient.invalidateQueries({ queryKey: ['course-enrollment-costs', course.id] })
  }

  return (
    <div className="space-y-6">
      {/* Budget overview */}
      <div className="rounded-lg border p-4 space-y-3">
        <h3 className="font-semibold text-sm">Budget Overview</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
          <div>
            <div className="text-xs text-muted-foreground">Planned Budget</div>
            <div className="text-lg font-bold tabular-nums">{budget > 0 ? fmt(budget, course.currency) : '—'}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">Net Cost</div>
            <div className="text-lg font-bold tabular-nums">{fmt(actualCost, course.currency)}</div>
            {(totals?.total_credit ?? 0) > 0 && (
              <div className="text-[10px] text-green-600">+{fmt(totals!.total_credit, course.currency)} credits</div>
            )}
          </div>
          <div>
            <div className="text-xs text-muted-foreground">Variance</div>
            {budget > 0 ? (
              <div className={`text-lg font-bold tabular-nums ${variance < 0 ? 'text-red-600' : 'text-green-600'}`}>
                {variance >= 0 ? '+' : ''}{fmt(variance, course.currency)}
              </div>
            ) : <div className="text-lg font-bold">—</div>}
          </div>
          <div>
            <div className="text-xs text-muted-foreground">Execution</div>
            <div className={`text-lg font-bold tabular-nums ${execPct > 100 ? 'text-red-600' : execPct > 90 ? 'text-yellow-600' : ''}`}>
              {budget > 0 ? `${execPct}%` : '—'}
            </div>
          </div>
        </div>

        {/* Execution bar */}
        {budget > 0 && (
          <div className="space-y-1">
            <div className="h-2.5 rounded-full bg-muted overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  execPct > 100 ? 'bg-red-500' : execPct > 90 ? 'bg-yellow-500' : 'bg-primary'
                }`}
                style={{ width: `${Math.min(100, execPct)}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Spending log */}
      <div className="rounded-lg border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-sm">Spending ({transactions.length})</h3>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setSpendDialogOpen(true)}>
              <Plus className="h-3.5 w-3.5 mr-1" />
              Record Spend
            </Button>
            <Button variant="outline" size="sm" onClick={() => setLinkDialogOpen(true)}>
              <Link2 className="h-3.5 w-3.5 mr-1" />
              Link Invoice
            </Button>
          </div>
        </div>

        {transactions.length === 0 ? (
          <EmptyState
            icon={<Receipt className="h-8 w-8" />}
            title="No spending recorded"
            description="Record manual spending or link invoices to track budget execution."
          />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Date</TableHead>
                  <TableHead className="text-xs text-right">Amount</TableHead>
                  <TableHead className="text-xs">Type</TableHead>
                  <TableHead className="text-xs">Source</TableHead>
                  <TableHead className="text-xs">Description</TableHead>
                  <TableHead className="text-xs">Recorded By</TableHead>
                  <TableHead className="w-20" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {transactions.map((tx) => (
                  <TableRow key={tx.id}>
                    <TableCell className="text-xs">{fmtDate(tx.transaction_date)}</TableCell>
                    <TableCell className="text-right text-xs tabular-nums font-medium">
                      {fmt(tx.amount, course.currency)}
                    </TableCell>
                    <TableCell>
                      <Badge className={`text-[10px] px-1.5 py-0 border-0 ${
                        tx.direction === 'credit' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                      }`}>
                        {tx.direction}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs">
                      {tx.source === 'invoice' ? (
                        <span className="flex items-center gap-1">
                          <FileText className="h-3 w-3" />
                          {tx.invoice_number ?? 'Invoice'}
                        </span>
                      ) : 'Manual'}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground max-w-[200px] truncate">
                      {tx.description ?? (tx.invoice_supplier ? `${tx.invoice_supplier} #${tx.invoice_number}` : '—')}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{tx.recorded_by_name ?? '—'}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex gap-1 justify-end">
                        {tx.source === 'manual' && (
                          <Button variant="ghost" size="icon" className="h-6 w-6"
                            onClick={() => setEditTx(tx)} title="Edit">
                            <Pencil className="h-3 w-3" />
                          </Button>
                        )}
                        <Button variant="ghost" size="icon" className="h-6 w-6 text-destructive"
                          onClick={() => deleteTxMut.mutate(tx.id)} title="Delete">
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {/* Totals */}
                <TableRow className="bg-muted/50 font-semibold">
                  <TableCell className="text-xs">Total</TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{fmt(totals?.net_cost ?? 0, course.currency)}</TableCell>
                  <TableCell colSpan={5} />
                </TableRow>
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {/* Enrollment cost breakdown */}
      {costs.length > 0 && (
        <div className="rounded-lg border p-4 space-y-3">
          <h3 className="font-semibold text-sm">Cost Allocation by Participant ({costs.length})</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-2 font-medium">Employee</th>
                  <th className="text-left py-2 font-medium">Department</th>
                  <th className="text-right py-2 font-medium">Training</th>
                  <th className="text-right py-2 font-medium">Diurna</th>
                  <th className="text-right py-2 font-medium">Cazare</th>
                  <th className="text-right py-2 font-medium">Transport</th>
                  <th className="text-right py-2 font-medium">Taxi</th>
                  <th className="text-right py-2 font-medium">Total</th>
                </tr>
              </thead>
              <tbody>
                {costs.map(c => (
                  <tr key={c.enrollment_id} className="border-b last:border-0 hover:bg-muted/30">
                    <td className="py-2 font-medium">{c.employee_name}</td>
                    <td className="py-2 text-muted-foreground">{c.enrollment_department ?? c.user_department ?? '—'}</td>
                    <td className="py-2 text-right tabular-nums">{fmt(c.training_fee, c.currency)}</td>
                    <td className="py-2 text-right tabular-nums">{fmt(c.per_diem, c.currency)}</td>
                    <td className="py-2 text-right tabular-nums">{fmt(c.accommodation, c.currency)}</td>
                    <td className="py-2 text-right tabular-nums">{fmt(c.transport, c.currency)}</td>
                    <td className="py-2 text-right tabular-nums">{fmt(c.taxi, c.currency)}</td>
                    <td className="py-2 text-right tabular-nums font-semibold">{fmt(c.total_cost, c.currency)}</td>
                  </tr>
                ))}
                <tr className="font-semibold bg-muted/50">
                  <td className="py-2" colSpan={2}>Total</td>
                  <td className="py-2 text-right tabular-nums">{fmt(costs.reduce((s, c) => s + c.training_fee, 0), course.currency)}</td>
                  <td className="py-2 text-right tabular-nums">{fmt(costs.reduce((s, c) => s + c.per_diem, 0), course.currency)}</td>
                  <td className="py-2 text-right tabular-nums">{fmt(costs.reduce((s, c) => s + c.accommodation, 0), course.currency)}</td>
                  <td className="py-2 text-right tabular-nums">{fmt(costs.reduce((s, c) => s + c.transport, 0), course.currency)}</td>
                  <td className="py-2 text-right tabular-nums">{fmt(costs.reduce((s, c) => s + c.taxi, 0), course.currency)}</td>
                  <td className="py-2 text-right tabular-nums">{fmt(costs.reduce((s, c) => s + c.total_cost, 0), course.currency)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Record Spend Dialog */}
      <SpendDialog
        open={spendDialogOpen}
        onOpenChange={setSpendDialogOpen}
        courseId={course.id}
        onSuccess={invalidate}
      />

      {/* Edit Transaction Dialog */}
      {editTx && (
        <SpendDialog
          open={!!editTx}
          onOpenChange={(open) => { if (!open) setEditTx(null) }}
          courseId={course.id}
          editTx={editTx}
          onSuccess={() => { invalidate(); setEditTx(null) }}
        />
      )}

      {/* Link Invoice Dialog */}
      <LinkInvoiceDialog
        open={linkDialogOpen}
        onOpenChange={setLinkDialogOpen}
        courseId={course.id}
        onSuccess={invalidate}
      />
    </div>
  )
}

/* ── Record / Edit Spend Dialog ─────────────────────────────── */

function SpendDialog({
  open, onOpenChange, courseId, editTx, onSuccess,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  courseId: number
  editTx?: CourseTransaction | null
  onSuccess: () => void
}) {
  const [form, setForm] = useState({
    amount: editTx ? String(editTx.amount) : '',
    transaction_date: editTx?.transaction_date ?? new Date().toISOString().slice(0, 10),
    description: editTx?.description ?? '',
    direction: editTx?.direction ?? 'debit' as 'debit' | 'credit',
  })

  const createMut = useMutation({
    mutationFn: () => editTx
      ? coursesApi.updateTransaction(courseId, editTx.id, {
          amount: Number(form.amount),
          transaction_date: form.transaction_date,
          description: form.description || undefined,
        })
      : coursesApi.createTransaction(courseId, {
          amount: Number(form.amount),
          direction: form.direction,
          transaction_date: form.transaction_date,
          description: form.description || undefined,
        }),
    onSuccess: () => {
      toast.success(editTx ? 'Transaction updated' : 'Spend recorded')
      onSuccess()
      onOpenChange(false)
    },
    onError: () => toast.error('Failed to save'),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[400px]" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{editTx ? 'Edit Transaction' : 'Record Spend'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Amount</Label>
            <Input type="number" step="0.01" placeholder="0.00" value={form.amount}
              onChange={(e) => setForm(f => ({ ...f, amount: e.target.value }))} autoFocus />
          </div>
          {!editTx && (
            <div className="space-y-1.5">
              <Label>Direction</Label>
              <Select value={form.direction} onValueChange={(v) => setForm(f => ({ ...f, direction: v as 'debit' | 'credit' }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="debit">Debit (Cost)</SelectItem>
                  <SelectItem value="credit">Credit (Refund/Sponsorship)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="space-y-1.5">
            <Label>Date</Label>
            <Input type="date" value={form.transaction_date}
              onChange={(e) => setForm(f => ({ ...f, transaction_date: e.target.value }))} />
          </div>
          <div className="space-y-1.5">
            <Label>Description</Label>
            <Input placeholder="What was this for?" value={form.description}
              onChange={(e) => setForm(f => ({ ...f, description: e.target.value }))} />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button size="sm" onClick={() => createMut.mutate()}
              disabled={!form.amount || Number(form.amount) <= 0 || createMut.isPending}>
              {editTx ? 'Update' : 'Record'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

/* ── Link Invoice Dialog ────────────────────────────────────── */

function LinkInvoiceDialog({
  open, onOpenChange, courseId, onSuccess,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  courseId: number
  onSuccess: () => void
}) {
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounce(search, 300)
  const [linkedIds, setLinkedIds] = useState<Set<number>>(new Set())

  const { data: results = [], isLoading: isSearching } = useQuery({
    queryKey: ['invoice-search', debouncedSearch],
    queryFn: () => invoicesApi.searchInvoices(debouncedSearch),
    enabled: open && debouncedSearch.length >= 2,
  })

  const linkMut = useMutation({
    mutationFn: (inv: Invoice) => coursesApi.createTransaction(courseId, {
      amount: inv.invoice_value,
      direction: 'debit',
      source: 'invoice',
      invoice_id: inv.id,
      transaction_date: inv.invoice_date,
      description: `${inv.supplier} #${inv.invoice_number}`,
    }),
    onSuccess: (_data, inv) => {
      toast.success('Invoice linked')
      setLinkedIds(prev => new Set(prev).add(inv.id))
      onSuccess()
    },
    onError: () => toast.error('Failed to link invoice'),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[900px]" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>Link Invoice to Course</DialogTitle>
          {linkedIds.size > 0 && (
            <p className="text-sm text-muted-foreground">{linkedIds.size} invoice{linkedIds.size > 1 ? 's' : ''} linked</p>
          )}
        </DialogHeader>
        <div className="space-y-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input className="pl-9" placeholder="Search by supplier or invoice number..."
              value={search} onChange={(e) => setSearch(e.target.value)} autoFocus />
          </div>

          {isSearching && <div className="text-center text-xs text-muted-foreground py-2">Searching...</div>}

          {(results as Invoice[]).length > 0 && (
            <div className="rounded-md border max-h-72 overflow-auto">
              <Table>
                <TableHeader className="sticky top-0 bg-background z-10">
                  <TableRow>
                    <TableHead className="text-xs">Supplier</TableHead>
                    <TableHead className="text-xs">Invoice Nr</TableHead>
                    <TableHead className="text-xs w-24">Date</TableHead>
                    <TableHead className="text-xs text-right w-28">Value</TableHead>
                    <TableHead className="w-16" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(results as Invoice[]).map((inv) => {
                    const alreadyLinked = linkedIds.has(inv.id)
                    return (
                      <TableRow key={inv.id} className={alreadyLinked ? 'opacity-50' : ''}>
                        <TableCell className="text-xs max-w-[200px] truncate">{inv.supplier}</TableCell>
                        <TableCell className="text-xs font-mono">{inv.invoice_number}</TableCell>
                        <TableCell className="text-xs">{fmtDate(inv.invoice_date)}</TableCell>
                        <TableCell className="text-right text-xs tabular-nums">{fmt(inv.invoice_value, inv.currency)}</TableCell>
                        <TableCell className="text-right">
                          {alreadyLinked ? (
                            <Check className="h-4 w-4 text-green-500 ml-auto" />
                          ) : (
                            <Button size="sm" variant="outline" className="h-6 text-xs px-2"
                              disabled={linkMut.isPending}
                              onClick={() => linkMut.mutate(inv)}>
                              Link
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
          )}

          {debouncedSearch.length >= 2 && !isSearching && (results as Invoice[]).length === 0 && (
            <div className="text-center text-xs text-muted-foreground py-4">No invoices found.</div>
          )}
        </div>
        <div className="flex justify-end">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>Done</Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
