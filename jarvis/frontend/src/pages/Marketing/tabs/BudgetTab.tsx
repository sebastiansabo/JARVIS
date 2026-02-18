import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import {
  Plus, Trash2, DollarSign, Link2, Search, Pencil, Check,
  ChevronDown, ChevronRight,
} from 'lucide-react'
import { marketingApi } from '@/api/marketing'
import { settingsApi } from '@/api/settings'
import type { MktBudgetLine, InvoiceSearchResult } from '@/types/marketing'
import { fmt, fmtDate } from './utils'

export function BudgetTab({ projectId, currency }: { projectId: number; currency: string }) {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [addForm, setAddForm] = useState({ channel: '', planned_amount: '', description: '', period_type: 'campaign' })
  const [linkLineId, setLinkLineId] = useState<number | null>(null)
  const [invoiceSearch, setInvoiceSearch] = useState('')
  const [invoiceResults, setInvoiceResults] = useState<InvoiceSearchResult[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [linkedInvoiceIds, setLinkedInvoiceIds] = useState<Set<number>>(new Set())
  const [spendLineId, setSpendLineId] = useState<number | null>(null)
  const [spendForm, setSpendForm] = useState({ amount: '', transaction_date: '', description: '' })
  const [expandedLineId, setExpandedLineId] = useState<number | null>(null)
  const [linkTxId, setLinkTxId] = useState<number | null>(null)
  const [txInvoiceSearch, setTxInvoiceSearch] = useState('')
  const [txInvoiceResults, setTxInvoiceResults] = useState<InvoiceSearchResult[]>([])
  const [isTxSearching, setIsTxSearching] = useState(false)
  const [editTxId, setEditTxId] = useState<number | null>(null)
  const [editTxForm, setEditTxForm] = useState({ amount: '', transaction_date: '', description: '' })

  const { data } = useQuery({
    queryKey: ['mkt-budget-lines', projectId],
    queryFn: () => marketingApi.getBudgetLines(projectId),
  })
  const lines = data?.budget_lines ?? []

  const { data: channelOpts } = useQuery({
    queryKey: ['dropdown-options', 'mkt_channel'],
    queryFn: () => settingsApi.getDropdownOptions('mkt_channel'),
  })

  const addMut = useMutation({
    mutationFn: (d: Record<string, unknown>) => marketingApi.createBudgetLine(projectId, d as Partial<MktBudgetLine>),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-budget-lines', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-project', projectId] })
      setShowAdd(false)
      setAddForm({ channel: '', planned_amount: '', description: '', period_type: 'campaign' })
    },
  })

  const deleteMut = useMutation({
    mutationFn: (lineId: number) => marketingApi.deleteBudgetLine(projectId, lineId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-budget-lines', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-project', projectId] })
    },
  })

  const spendMut = useMutation({
    mutationFn: () => marketingApi.createTransaction(spendLineId!, {
      amount: Number(spendForm.amount),
      transaction_date: spendForm.transaction_date,
      direction: 'debit',
      source: 'manual',
      description: spendForm.description || undefined,
    } as Record<string, unknown>),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-budget-lines', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-project', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-transactions'] })
      setSpendLineId(null)
      setSpendForm({ amount: '', transaction_date: '', description: '' })
    },
  })

  const linkInvoiceMut = useMutation({
    mutationFn: (inv: InvoiceSearchResult) => marketingApi.createTransaction(linkLineId!, {
      amount: inv.invoice_value,
      transaction_date: inv.invoice_date,
      direction: 'debit',
      source: 'invoice',
      invoice_id: inv.id,
      description: `${inv.supplier} #${inv.invoice_number}`,
    } as Record<string, unknown>),
    onSuccess: (_data, inv) => {
      queryClient.invalidateQueries({ queryKey: ['mkt-budget-lines', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-project', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-transactions'] })
      setLinkedInvoiceIds((prev) => new Set(prev).add(inv.id))
    },
  })

  const { data: txData } = useQuery({
    queryKey: ['mkt-transactions', expandedLineId],
    queryFn: () => marketingApi.getTransactions(expandedLineId!),
    enabled: !!expandedLineId,
  })
  const transactions = txData?.transactions ?? []

  const deleteTxMut = useMutation({
    mutationFn: (txId: number) => marketingApi.deleteTransaction(txId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-transactions', expandedLineId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-budget-lines', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-project', projectId] })
    },
  })

  const linkTxInvoiceMut = useMutation({
    mutationFn: ({ txId, invoiceId }: { txId: number; invoiceId: number | null }) =>
      marketingApi.linkTransactionInvoice(txId, invoiceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-transactions', expandedLineId] })
      setLinkTxId(null)
      setTxInvoiceSearch('')
      setTxInvoiceResults([])
    },
  })

  const editTxMut = useMutation({
    mutationFn: () => marketingApi.updateTransaction(editTxId!, {
      amount: Number(editTxForm.amount),
      transaction_date: editTxForm.transaction_date,
      description: editTxForm.description || undefined,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-transactions', expandedLineId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-budget-lines', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-project', projectId] })
      setEditTxId(null)
    },
  })

  async function searchTxInvoices(q: string) {
    setTxInvoiceSearch(q)
    if (q.length < 2) { setTxInvoiceResults([]); return }
    setIsTxSearching(true)
    try {
      const res = await marketingApi.searchInvoices(q)
      setTxInvoiceResults(res?.invoices ?? [])
    } catch { setTxInvoiceResults([]) }
    setIsTxSearching(false)
  }

  async function searchInvoices(q: string) {
    setInvoiceSearch(q)
    if (q.length < 2) { setInvoiceResults([]); return }
    setIsSearching(true)
    try {
      const res = await marketingApi.searchInvoices(q)
      setInvoiceResults(res?.invoices ?? [])
    } catch { setInvoiceResults([]) }
    setIsSearching(false)
  }

  const totalPlanned = lines.reduce((s, l) => s + (Number(l.planned_amount) || 0), 0)
  const totalApproved = lines.reduce((s, l) => s + (Number(l.approved_amount) || 0), 0)
  const totalSpent = lines.reduce((s, l) => s + (Number(l.spent_amount) || 0), 0)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex gap-4 text-sm">
          <span>Planned: <strong>{fmt(totalPlanned, currency)}</strong></span>
          <span>Approved: <strong>{fmt(totalApproved, currency)}</strong></span>
          <span>Spent: <strong>{fmt(totalSpent, currency)}</strong></span>
        </div>
        <Button size="sm" onClick={() => setShowAdd(true)}>
          <Plus className="h-3.5 w-3.5 mr-1.5" /> Add Line
        </Button>
      </div>

      {lines.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">No budget lines yet.</div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-6 px-2" />
                <TableHead>Channel</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Period</TableHead>
                <TableHead className="text-right">Planned</TableHead>
                <TableHead className="text-right">Approved</TableHead>
                <TableHead className="text-right">Spent</TableHead>
                <TableHead>Utilization</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {lines.map((l) => {
                const planned = Number(l.planned_amount) || 0
                const spent = Number(l.spent_amount) || 0
                const util = planned ? Math.round((spent / planned) * 100) : 0
                const isExpanded = expandedLineId === l.id
                return (
                  <>
                    <TableRow
                      key={l.id}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => setExpandedLineId(isExpanded ? null : l.id)}
                    >
                      <TableCell className="w-6 px-2">
                        {isExpanded ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="text-xs">{(l.channel ?? '').replace('_', ' ')}</Badge>
                      </TableCell>
                      <TableCell className="text-sm max-w-[200px] truncate">{l.description || '—'}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">{l.period_type}</TableCell>
                      <TableCell className="text-right text-sm tabular-nums">{fmt(l.planned_amount, currency)}</TableCell>
                      <TableCell className="text-right text-sm tabular-nums">{fmt(l.approved_amount, currency)}</TableCell>
                      <TableCell className="text-right text-sm tabular-nums">{fmt(l.spent_amount, currency)}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <div className="w-14 h-1.5 rounded-full bg-muted overflow-hidden">
                            <div
                              className={`h-full rounded-full ${util > 90 ? 'bg-red-500' : util > 70 ? 'bg-yellow-500' : 'bg-blue-500'}`}
                              style={{ width: `${Math.min(util, 100)}%` }}
                            />
                          </div>
                          <span className="text-xs text-muted-foreground">{util}%</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-0.5" onClick={(e) => e.stopPropagation()}>
                          <Button variant="ghost" size="icon" className="h-7 w-7" title="Record Spend"
                            onClick={() => { setSpendLineId(l.id); setSpendForm({ amount: '', transaction_date: new Date().toISOString().slice(0, 10), description: '' }) }}>
                            <DollarSign className="h-3.5 w-3.5 text-muted-foreground" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-7 w-7" title="Link Invoice"
                            onClick={() => { setLinkLineId(l.id); setInvoiceSearch(''); setInvoiceResults([]); setLinkedInvoiceIds(new Set()) }}>
                            <Link2 className="h-3.5 w-3.5 text-muted-foreground" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-7 w-7" title="Delete" onClick={() => deleteMut.mutate(l.id)}>
                            <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                    {isExpanded && (
                      <TableRow key={`${l.id}-expand`} className="bg-muted/30 hover:bg-muted/30">
                        <TableCell colSpan={9} className="p-0">
                          <div className="px-6 py-3 space-y-3">
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Transactions</span>
                              <div className="flex gap-1.5">
                                <Button variant="outline" size="sm" className="h-7 text-xs"
                                  onClick={(e) => { e.stopPropagation(); setSpendLineId(l.id); setSpendForm({ amount: '', transaction_date: new Date().toISOString().slice(0, 10), description: '' }) }}>
                                  <DollarSign className="h-3 w-3 mr-1" /> Record Spend
                                </Button>
                                <Button variant="outline" size="sm" className="h-7 text-xs"
                                  onClick={(e) => { e.stopPropagation(); setLinkLineId(l.id); setInvoiceSearch(''); setInvoiceResults([]); setLinkedInvoiceIds(new Set()) }}>
                                  <Link2 className="h-3 w-3 mr-1" /> Link Invoice
                                </Button>
                              </div>
                            </div>
                            {transactions.length === 0 ? (
                              <div className="text-xs text-muted-foreground text-center py-3">No transactions recorded yet.</div>
                            ) : (
                              <div className="rounded-md border bg-background">
                                <Table>
                                  <TableHeader>
                                    <TableRow>
                                      <TableHead className="text-xs">Date</TableHead>
                                      <TableHead className="text-xs text-right">Amount</TableHead>
                                      <TableHead className="text-xs">Direction</TableHead>
                                      <TableHead className="text-xs">Source</TableHead>
                                      <TableHead className="text-xs">Description</TableHead>
                                      <TableHead className="text-xs">Invoice</TableHead>
                                      <TableHead className="text-xs">Recorded By</TableHead>
                                      <TableHead className="w-14" />
                                    </TableRow>
                                  </TableHeader>
                                  <TableBody>
                                    {transactions.map((tx) => (
                                      <TableRow key={tx.id}>
                                        <TableCell className="text-xs">{fmtDate(tx.transaction_date)}</TableCell>
                                        <TableCell className="text-xs text-right tabular-nums font-medium">{fmt(tx.amount, currency)}</TableCell>
                                        <TableCell>
                                          <Badge variant="outline" className={cn('text-[10px]', tx.direction === 'debit' ? 'border-red-300 text-red-600' : 'border-green-300 text-green-600')}>
                                            {tx.direction}
                                          </Badge>
                                        </TableCell>
                                        <TableCell className="text-xs text-muted-foreground">{tx.source}</TableCell>
                                        <TableCell className="text-xs max-w-[200px] truncate">{tx.description || '—'}</TableCell>
                                        <TableCell className="text-xs">
                                          {tx.invoice_id ? (
                                            <div className="flex items-center gap-1">
                                              <Badge variant="secondary" className="text-[10px] gap-0.5 max-w-[160px]">
                                                <span className="truncate">{tx.invoice_supplier || ''} #{tx.invoice_number_ref || tx.invoice_id}</span>
                                                {tx.source !== 'invoice' && (
                                                  <button
                                                    className="ml-0.5 hover:text-destructive"
                                                    onClick={(e) => { e.stopPropagation(); linkTxInvoiceMut.mutate({ txId: tx.id, invoiceId: null }) }}
                                                  >
                                                    <Trash2 className="h-2.5 w-2.5" />
                                                  </button>
                                                )}
                                              </Badge>
                                            </div>
                                          ) : (
                                            <Button variant="ghost" size="sm" className="h-5 text-[10px] px-1.5 text-muted-foreground"
                                              onClick={(e) => { e.stopPropagation(); setLinkTxId(tx.id); setTxInvoiceSearch(''); setTxInvoiceResults([]) }}>
                                              <Link2 className="h-3 w-3 mr-0.5" /> Link
                                            </Button>
                                          )}
                                        </TableCell>
                                        <TableCell className="text-xs text-muted-foreground">{tx.recorded_by_name || '—'}</TableCell>
                                        <TableCell>
                                          <div className="flex items-center gap-0.5">
                                            {tx.source !== 'invoice' && (
                                              <Button variant="ghost" size="icon" className="h-6 w-6" title="Edit"
                                                onClick={(e) => {
                                                  e.stopPropagation()
                                                  setEditTxId(tx.id)
                                                  setEditTxForm({
                                                    amount: String(tx.amount),
                                                    transaction_date: tx.transaction_date?.slice(0, 10) || '',
                                                    description: tx.description || '',
                                                  })
                                                }}>
                                                <Pencil className="h-3 w-3 text-muted-foreground" />
                                              </Button>
                                            )}
                                            {!tx.invoice_id && (
                                              <Button variant="ghost" size="icon" className="h-6 w-6"
                                                onClick={(e) => { e.stopPropagation(); deleteTxMut.mutate(tx.id) }}>
                                                <Trash2 className="h-3 w-3 text-muted-foreground" />
                                              </Button>
                                            )}
                                          </div>
                                        </TableCell>
                                      </TableRow>
                                    ))}
                                  </TableBody>
                                </Table>
                              </div>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Link Invoice Dialog */}
      <Dialog open={!!linkLineId} onOpenChange={(open) => { if (!open) setLinkLineId(null) }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Link Invoices to Budget Line</DialogTitle>
            {linkedInvoiceIds.size > 0 && (
              <p className="text-sm text-muted-foreground">{linkedInvoiceIds.size} invoice{linkedInvoiceIds.size > 1 ? 's' : ''} linked</p>
            )}
          </DialogHeader>
          <div className="space-y-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                className="pl-9"
                placeholder="Search by supplier or invoice number..."
                value={invoiceSearch}
                onChange={(e) => searchInvoices(e.target.value)}
                autoFocus
              />
            </div>
            {isSearching && <div className="text-center text-xs text-muted-foreground py-2">Searching...</div>}
            {invoiceResults.length > 0 && (
              <div className="rounded-md border max-h-72 overflow-y-auto">
                <Table>
                  <TableHeader className="sticky top-0 bg-background z-10">
                    <TableRow>
                      <TableHead className="text-xs">Supplier</TableHead>
                      <TableHead className="text-xs">Invoice Number</TableHead>
                      <TableHead className="text-xs w-24">Date</TableHead>
                      <TableHead className="text-xs text-right w-28">Value</TableHead>
                      <TableHead className="w-16" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {invoiceResults.map((inv) => {
                      const alreadyLinked = linkedInvoiceIds.has(inv.id)
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
                                disabled={linkInvoiceMut.isPending}
                                onClick={() => linkInvoiceMut.mutate(inv)}>
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
            {invoiceSearch.length >= 2 && !isSearching && invoiceResults.length === 0 && (
              <div className="text-center text-xs text-muted-foreground py-4">No invoices found.</div>
            )}
          </div>
          <div className="flex justify-end">
            <Button variant="outline" size="sm" onClick={() => setLinkLineId(null)}>Done</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Link Invoice to Transaction Dialog */}
      <Dialog open={!!linkTxId} onOpenChange={(open) => { if (!open) { setLinkTxId(null); setTxInvoiceSearch(''); setTxInvoiceResults([]) } }}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Link Invoice to Transaction</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                className="pl-9"
                placeholder="Search by supplier or invoice number..."
                value={txInvoiceSearch}
                onChange={(e) => searchTxInvoices(e.target.value)}
                autoFocus
              />
            </div>
            {isTxSearching && <div className="text-center text-xs text-muted-foreground py-2">Searching...</div>}
            {txInvoiceResults.length > 0 && (
              <div className="rounded-md border max-h-72 overflow-y-auto">
                <Table>
                  <TableHeader className="sticky top-0 bg-background z-10">
                    <TableRow>
                      <TableHead className="text-xs min-w-[180px]">Supplier</TableHead>
                      <TableHead className="text-xs min-w-[180px]">Invoice Number</TableHead>
                      <TableHead className="text-xs w-28">Date</TableHead>
                      <TableHead className="text-xs text-right w-28">Value</TableHead>
                      <TableHead className="w-14" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {txInvoiceResults.map((inv) => (
                      <TableRow key={inv.id}>
                        <TableCell className="text-xs">{inv.supplier}</TableCell>
                        <TableCell className="text-xs font-mono">{inv.invoice_number}</TableCell>
                        <TableCell className="text-xs">{fmtDate(inv.invoice_date)}</TableCell>
                        <TableCell className="text-right text-xs tabular-nums whitespace-nowrap">{fmt(inv.invoice_value, inv.currency)}</TableCell>
                        <TableCell className="text-right">
                          <Button size="sm" variant="outline" className="h-6 text-xs px-2"
                            disabled={linkTxInvoiceMut.isPending}
                            onClick={() => linkTxInvoiceMut.mutate({ txId: linkTxId!, invoiceId: inv.id })}>
                            Link
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
            {txInvoiceSearch.length >= 2 && !isTxSearching && txInvoiceResults.length === 0 && (
              <div className="text-center text-xs text-muted-foreground py-4">No invoices found.</div>
            )}
          </div>
          <div className="flex justify-end">
            <Button variant="outline" size="sm" onClick={() => { setLinkTxId(null); setTxInvoiceSearch(''); setTxInvoiceResults([]) }}>Cancel</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Transaction Dialog */}
      <Dialog open={!!editTxId} onOpenChange={(open) => { if (!open) setEditTxId(null) }}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Edit Transaction</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Amount *</Label>
              <Input type="number" value={editTxForm.amount} onChange={(e) => setEditTxForm((f) => ({ ...f, amount: e.target.value }))} autoFocus />
            </div>
            <div className="space-y-1.5">
              <Label>Date *</Label>
              <Input type="date" value={editTxForm.transaction_date} onChange={(e) => setEditTxForm((f) => ({ ...f, transaction_date: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label>Description</Label>
              <Input value={editTxForm.description} onChange={(e) => setEditTxForm((f) => ({ ...f, description: e.target.value }))} />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setEditTxId(null)}>Cancel</Button>
              <Button
                disabled={!editTxForm.amount || !editTxForm.transaction_date || editTxMut.isPending}
                onClick={() => editTxMut.mutate()}
              >
                {editTxMut.isPending ? 'Saving...' : 'Save'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Record Spend Dialog */}
      <Dialog open={!!spendLineId} onOpenChange={(open) => { if (!open) setSpendLineId(null) }}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Record Spend</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Amount *</Label>
              <Input type="number" value={spendForm.amount} onChange={(e) => setSpendForm((f) => ({ ...f, amount: e.target.value }))} autoFocus placeholder="0" />
            </div>
            <div className="space-y-1.5">
              <Label>Date *</Label>
              <Input type="date" value={spendForm.transaction_date} onChange={(e) => setSpendForm((f) => ({ ...f, transaction_date: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label>Description</Label>
              <Input value={spendForm.description} onChange={(e) => setSpendForm((f) => ({ ...f, description: e.target.value }))} placeholder="e.g., Agency fee Q1" />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setSpendLineId(null)}>Cancel</Button>
              <Button
                disabled={!spendForm.amount || !spendForm.transaction_date || spendMut.isPending}
                onClick={() => spendMut.mutate()}
              >
                {spendMut.isPending ? 'Saving...' : 'Record'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Add Budget Line Dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Add Budget Line</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Channel *</Label>
              <Select value={addForm.channel} onValueChange={(v) => setAddForm((f) => ({ ...f, channel: v }))}>
                <SelectTrigger><SelectValue placeholder="Select channel" /></SelectTrigger>
                <SelectContent>
                  {(channelOpts ?? []).map((o: { value: string; label: string }) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Planned Amount</Label>
              <Input
                type="number"
                value={addForm.planned_amount}
                onChange={(e) => setAddForm((f) => ({ ...f, planned_amount: e.target.value }))}
                placeholder="0"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Description</Label>
              <Input
                value={addForm.description}
                onChange={(e) => setAddForm((f) => ({ ...f, description: e.target.value }))}
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowAdd(false)}>Cancel</Button>
              <Button
                disabled={!addForm.channel || addMut.isPending}
                onClick={() => addMut.mutate({
                  channel: addForm.channel,
                  planned_amount: Number(addForm.planned_amount) || 0,
                  description: addForm.description || undefined,
                  period_type: addForm.period_type,
                  currency,
                })}
              >
                {addMut.isPending ? 'Adding...' : 'Add'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
