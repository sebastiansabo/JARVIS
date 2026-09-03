import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Loader2, Upload, Plus, Minus, ArrowRightLeft,
  ChevronDown, TrendingUp, TrendingDown, Check, X, Clock, CheckCircle2,
  HelpCircle, ArrowDown, MessageCircle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { SearchSelect } from '@/components/shared/SearchSelect'
import { EphemeralChatPopup } from '@/components/EphemeralChatPopup'
import { timeBankApi } from '@/api/timeBank'
import type { TimeBankBalance } from '@/api/timeBank'
import { connecteamApi } from '@/api/connecteam'
import type { ConnecteamSubmission, ConversionRequest } from '@/api/connecteam'
import { toast } from 'sonner'

const now = new Date()

const TX_TYPE_LABELS: Record<string, string> = {
  T0: 'Starting Balance',
  marketing_event: 'Marketing Event',
  manual_credit: 'Manual Credit',
  manual_debit: 'Manual Debit',
  leave_permit: 'Leave Permit',
  connecteam: 'Connecteam',
  co_conversion: 'CO Conversion',
}

function formatDate(iso: string) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('ro-RO', { day: '2-digit', month: 'short', year: 'numeric' })
}

function formatTime(iso: string) {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' })
}

export default function TimeBankTab({ search }: { search: string }) {
  const [innerTab, setInnerTab] = useState<'balances' | 'transactions' | 'conversion' | 'help'>('balances')

  return (
    <div className="space-y-4">
      <Tabs value={innerTab} onValueChange={(v) => setInnerTab(v as typeof innerTab)}>
        <TabsList>
          <TabsTrigger value="balances">Balances</TabsTrigger>
          <TabsTrigger value="transactions">Transactions</TabsTrigger>
          <TabsTrigger value="conversion">CO Conversion</TabsTrigger>
          <TabsTrigger value="help"><HelpCircle className="mr-1 h-3.5 w-3.5" />Help</TabsTrigger>
        </TabsList>
      </Tabs>

      {innerTab === 'balances' && <BalancesPanel search={search} />}
      {innerTab === 'transactions' && <TransactionsPanel search={search} />}
      {innerTab === 'conversion' && <ConversionPanel search={search} />}
      {innerTab === 'help' && <HelpPanel />}
    </div>
  )
}

// ─── Balances Panel ───

function BalancesPanel({ search }: { search: string }) {
  const qc = useQueryClient()
  const [creditDialog, setCreditDialog] = useState<TimeBankBalance | null>(null)
  const [debitDialog, setDebitDialog] = useState<TimeBankBalance | null>(null)
  const [t0Dialog, setT0Dialog] = useState<TimeBankBalance | null>(null)
  const [amount, setAmount] = useState('')
  const [description, setDescription] = useState('')
  const [detailUser, setDetailUser] = useState<{ id: number; name: string } | null>(null)
  const [addMode, setAddMode] = useState<'credit' | 'debit' | 't0' | null>(null)
  const [selectedUserId, setSelectedUserId] = useState<string>('')

  const { data: balances, isLoading } = useQuery({
    queryKey: ['time-bank', 'balances'],
    queryFn: () => timeBankApi.getBalances(),
  })


  const creditMut = useMutation({
    mutationFn: (data: { user_id: number; amount: number; description?: string }) =>
      timeBankApi.credit(data),
    onSuccess: () => {
      toast.success('Credit added')
      qc.invalidateQueries({ queryKey: ['time-bank'] })
      setCreditDialog(null)
      setAmount('')
      setDescription('')
    },
    onError: () => toast.error('Failed to add credit'),
  })

  const debitMut = useMutation({
    mutationFn: (data: { user_id: number; amount: number; description?: string }) =>
      timeBankApi.debit(data),
    onSuccess: () => {
      toast.success('Debit applied')
      qc.invalidateQueries({ queryKey: ['time-bank'] })
      setDebitDialog(null)
      setAmount('')
      setDescription('')
    },
    onError: (err: { data?: { error?: string } }) => {
      toast.error(err.data?.error || 'Failed to apply debit')
    },
  })

  const t0Mut = useMutation({
    mutationFn: (data: { userId: number; amount: number }) =>
      timeBankApi.setT0(data.userId, data.amount),
    onSuccess: () => {
      toast.success('T0 balance set')
      qc.invalidateQueries({ queryKey: ['time-bank'] })
      setT0Dialog(null)
      setAmount('')
    },
    onError: () => toast.error('Failed to set T0'),
  })

  const importMut = useMutation({
    mutationFn: (file: File) => timeBankApi.importT0(file),
    onSuccess: (res) => {
      const d = res.data
      if (d.rows_matched > 0) {
        toast.success(`Imported T0 for ${d.rows_matched} employees (${d.rows_unmatched} unmatched, ${d.rows_skipped} skipped)`)
      } else {
        toast.info('No employees matched')
      }
      if (d.errors.length > 0) {
        toast.warning(`${d.errors.length} error(s) during import`)
      }
      qc.invalidateQueries({ queryKey: ['time-bank'] })
    },
    onError: () => toast.error('Import failed'),
  })

  const filtered = useMemo(() => {
    if (!balances) return []
    if (!search) return balances
    const q = search.toLowerCase()
    return balances.filter(b =>
      b.name.toLowerCase().includes(q) ||
      (b.company || '').toLowerCase().includes(q) ||
      (b.email || '').toLowerCase().includes(q),
    )
  }, [balances, search])

  if (detailUser) {
    return <UserTransactions user={detailUser} onBack={() => setDetailUser(null)} />
  }

  return (
    <>
      <div className="flex items-center justify-between flex-wrap gap-2">
        <span className="text-xs text-muted-foreground">
          {filtered.length} employee{filtered.length !== 1 ? 's' : ''}
        </span>
        <div className="flex items-center gap-2">
          <Button variant="default" size="sm" onClick={() => { setAddMode('credit'); setSelectedUserId(''); setAmount(''); setDescription('') }}>
            <Plus className="mr-1.5 h-4 w-4" /> Add Credit
          </Button>
          <Button variant="outline" size="sm" onClick={() => { setAddMode('debit'); setSelectedUserId(''); setAmount(''); setDescription('') }}>
            <Minus className="mr-1.5 h-4 w-4" /> Add Debit
          </Button>
          <Button variant="outline" size="sm" onClick={() => { setAddMode('t0'); setSelectedUserId(''); setAmount('') }}>
            <TrendingUp className="mr-1.5 h-4 w-4" /> Set T0
          </Button>
          <div className="w-px h-5 bg-border" />
          <input
            type="file" accept=".xlsx" className="hidden" id="tb-import-t0"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) { importMut.mutate(file); e.target.value = '' }
            }}
          />
          <Button
            variant="outline" size="sm"
            onClick={() => document.getElementById('tb-import-t0')?.click()}
            disabled={importMut.isPending}
          >
            {importMut.isPending
              ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
              : <Upload className="mr-1.5 h-4 w-4" />}
            Import T0
          </Button>
          <a
            href="/hr/api/time-bank/t0-template"
            download="time_bank_t0_template.xlsx"
            className="text-xs text-muted-foreground hover:text-foreground underline"
          >
            Download Template
          </a>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading...
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
          No Time Bank balances found
        </div>
      ) : (
        <div className="rounded-md border overflow-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Company</TableHead>
                <TableHead>Department</TableHead>
                <TableHead className="text-center">Status</TableHead>
                <TableHead className="text-right">Balance (h)</TableHead>
                <TableHead className="text-right">Sold Personal</TableHead>
                <TableHead className="text-right">Sold Eveniment</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((b) => (
                <TableRow
                  key={b.user_id}
                  className="cursor-pointer hover:bg-muted/40"
                  onClick={() => setDetailUser({ id: b.user_id, name: b.name })}
                >
                  <TableCell className="font-medium whitespace-nowrap">{b.name}</TableCell>
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                    {b.company?.replace(' S.R.L.', '') || '—'}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{b.department || '—'}</TableCell>
                  <TableCell className="text-center">
                    <div className="flex items-center justify-center gap-1">
                      {b.balance > 0 ? (
                        <Badge variant="outline" className="text-[10px] border-green-300 text-green-600 bg-green-50 dark:bg-green-950/30">
                          <CheckCircle2 className="mr-0.5 h-3 w-3" />Active
                        </Badge>
                      ) : b.balance < 0 ? (
                        <Badge variant="outline" className="text-[10px] border-red-300 text-red-600 bg-red-50 dark:bg-red-950/30">Overdrawn</Badge>
                      ) : (
                        <Badge variant="outline" className="text-[10px] border-gray-300 text-gray-500 bg-gray-50 dark:bg-gray-950/30">Not Set</Badge>
                      )}
                      {b.pending_count > 0 && (
                        <Badge variant="outline" className="text-[10px] border-yellow-300 text-yellow-600 bg-yellow-50 dark:bg-yellow-950/30">
                          <Clock className="mr-0.5 h-3 w-3" />{b.pending_count} pending
                        </Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-right tabular-nums font-medium">
                    <span className={b.balance > 0 ? 'text-green-600 dark:text-green-400' : b.balance < 0 ? 'text-red-600 dark:text-red-400' : ''}>
                      {b.balance}h
                    </span>
                  </TableCell>
                  {/* Personal pool — may go negative (red) */}
                  <TableCell className="text-right tabular-nums">
                    <span className={b.personal_balance < 0 ? 'text-red-600 dark:text-red-400' : 'text-muted-foreground'}>
                      {b.personal_balance}h
                    </span>
                  </TableCell>
                  {/* Event pool ("Ore Libere din Eveniment") — capped, never negative */}
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {b.event_balance}h
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                      <Button variant="ghost" size="icon" className="h-7 w-7" title="Credit"
                        onClick={() => { setCreditDialog(b); setAmount(''); setDescription('') }}>
                        <Plus className="h-3.5 w-3.5 text-green-600" />
                      </Button>
                      <Button variant="ghost" size="icon" className="h-7 w-7" title="Debit"
                        onClick={() => { setDebitDialog(b); setAmount(''); setDescription('') }}>
                        <Minus className="h-3.5 w-3.5 text-red-600" />
                      </Button>
                      <Button variant="ghost" size="icon" className="h-7 w-7" title="Set T0"
                        onClick={() => { setT0Dialog(b); setAmount(String(b.balance || '')) }}>
                        <TrendingUp className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Credit Dialog */}
      <AmountDialog
        open={!!creditDialog}
        title={`Credit hours to ${creditDialog?.name}`}
        label="Hours to credit"
        showDescription
        amount={amount}
        description={description}
        onAmountChange={setAmount}
        onDescriptionChange={setDescription}
        onClose={() => setCreditDialog(null)}
        onSubmit={() => {
          if (!creditDialog || !amount) return
          creditMut.mutate({ user_id: creditDialog.user_id, amount: parseFloat(amount), description: description || undefined })
        }}
        isPending={creditMut.isPending}
        submitLabel="Add Credit"
      />

      {/* Debit Dialog */}
      <AmountDialog
        open={!!debitDialog}
        title={`Debit hours from ${debitDialog?.name}`}
        label="Hours to debit"
        showDescription
        amount={amount}
        description={description}
        onAmountChange={setAmount}
        onDescriptionChange={setDescription}
        onClose={() => setDebitDialog(null)}
        onSubmit={() => {
          if (!debitDialog || !amount) return
          debitMut.mutate({ user_id: debitDialog.user_id, amount: parseFloat(amount), description: description || undefined })
        }}
        isPending={debitMut.isPending}
        submitLabel="Apply Debit"
      />

      {/* T0 Dialog */}
      <AmountDialog
        open={!!t0Dialog}
        title={`Set T0 for ${t0Dialog?.name}`}
        label="Starting balance (hours)"
        amount={amount}
        onAmountChange={setAmount}
        onClose={() => setT0Dialog(null)}
        onSubmit={() => {
          if (!t0Dialog || amount === '') return
          t0Mut.mutate({ userId: t0Dialog.user_id, amount: parseFloat(amount) })
        }}
        isPending={t0Mut.isPending}
        submitLabel="Set T0"
      />

      {/* Add Credit/Debit/T0 with employee picker */}
      <Dialog open={!!addMode} onOpenChange={(o) => { if (!o) setAddMode(null) }}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>
              {addMode === 'credit' ? 'Add Credit' : addMode === 'debit' ? 'Add Debit' : 'Set T0 Balance'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Employee</label>
              <SearchSelect
                value={selectedUserId}
                onValueChange={setSelectedUserId}
                options={(balances ?? []).map(u => ({ value: String(u.user_id), label: u.name }))}
                placeholder="Select employee..."
                searchPlaceholder="Type to search..."
                emptyMessage="No employees found."
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">
                {addMode === 't0' ? 'Starting balance (hours)' : 'Hours'}
              </label>
              <Input
                type="number" step="0.5" min="0"
                value={amount} onChange={(e) => setAmount(e.target.value)}
                placeholder="0"
              />
            </div>
            {addMode !== 't0' && (
              <div className="space-y-2">
                <label className="text-sm font-medium">Description</label>
                <Input
                  value={description} onChange={(e) => setDescription(e.target.value)}
                  placeholder="Optional description..."
                />
              </div>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setAddMode(null)}>Cancel</Button>
              <Button
                disabled={!selectedUserId || !amount || creditMut.isPending || debitMut.isPending || t0Mut.isPending}
                onClick={() => {
                  const uid = parseInt(selectedUserId)
                  const amt = parseFloat(amount)
                  if (!uid || !amt) return
                  if (addMode === 'credit') {
                    creditMut.mutate({ user_id: uid, amount: amt, description: description || undefined })
                  } else if (addMode === 'debit') {
                    debitMut.mutate({ user_id: uid, amount: amt, description: description || undefined })
                  } else {
                    t0Mut.mutate({ userId: uid, amount: amt })
                  }
                  setAddMode(null)
                }}
              >
                {(creditMut.isPending || debitMut.isPending || t0Mut.isPending) && (
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                )}
                {addMode === 'credit' ? 'Add Credit' : addMode === 'debit' ? 'Apply Debit' : 'Set T0'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

// ─── User Transactions Detail ───

function UserTransactions({ user, onBack }: { user: { id: number; name: string }; onBack: () => void }) {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['time-bank', 'transactions', user.id],
    queryFn: () => timeBankApi.getUserTransactions(user.id, { limit: 200 }),
  })

  const approveMut = useMutation({
    mutationFn: (txId: number) => timeBankApi.approve(txId),
    onSuccess: () => { toast.success('Approved'); qc.invalidateQueries({ queryKey: ['time-bank'] }) },
    onError: () => toast.error('Failed to approve'),
  })
  const rejectMut = useMutation({
    mutationFn: (txId: number) => timeBankApi.reject(txId),
    onSuccess: () => { toast.success('Rejected'); qc.invalidateQueries({ queryKey: ['time-bank'] }) },
    onError: () => toast.error('Failed to reject'),
  })
  const processMut = useMutation({
    mutationFn: (txId: number) => timeBankApi.process(txId),
    onSuccess: () => { toast.success('Processed'); qc.invalidateQueries({ queryKey: ['time-bank'] }) },
    onError: () => toast.error('Failed to process'),
  })

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={onBack}>
          &larr; Back
        </Button>
        <span className="font-medium">{user.name}</span>
        {data && (
          <Badge variant="outline" className="ml-auto">
            Balance: {data.balance}h
          </Badge>
        )}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading...
        </div>
      ) : !data?.data.length ? (
        <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
          No transactions
        </div>
      ) : (
        <div className="rounded-md border overflow-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Type</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead>Description</TableHead>
                <TableHead className="text-center">Status</TableHead>
                <TableHead>By</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.data.map((tx) => (
                <TableRow key={tx.id}>
                  <TableCell className="whitespace-nowrap text-xs">
                    {formatDate(tx.created_at)} {formatTime(tx.created_at)}
                  </TableCell>
                  <TableCell>
                    <TxTypeBadge type={tx.tx_type} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums font-medium">
                    <span className={tx.amount > 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}>
                      {tx.amount > 0 ? '+' : ''}{tx.amount}h
                    </span>
                  </TableCell>
                  <TableCell className="text-xs max-w-[250px] truncate">{tx.description || '—'}</TableCell>
                  <TableCell className="text-center">
                    <TxStatusBadge status={tx.status} />
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">{tx.created_by_name || 'System'}</TableCell>
                  <TableCell className="text-right">
                    <TxActions tx={tx} onApprove={approveMut.mutate} onReject={rejectMut.mutate} onProcess={processMut.mutate} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

// ─── Transactions Panel ───

function TransactionsPanel({ search }: { search: string }) {
  const qc = useQueryClient()
  const [txType, setTxType] = useState<string>('all')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [page, setPage] = useState(0)
  const pageSize = 50

  // Default: month-to-date
  const [dateFrom, setDateFrom] = useState(() => {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
  })
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10))

  const { data, isLoading } = useQuery({
    queryKey: ['time-bank', 'all-transactions', txType, statusFilter, page, dateFrom, dateTo],
    queryFn: () => timeBankApi.getTransactions({
      limit: pageSize,
      offset: page * pageSize,
      tx_type: txType !== 'all' ? txType : undefined,
      status: statusFilter !== 'all' ? statusFilter : undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
    }),
  })

  const approveMut = useMutation({
    mutationFn: (txId: number) => timeBankApi.approve(txId),
    onSuccess: () => { toast.success('Approved'); qc.invalidateQueries({ queryKey: ['time-bank'] }) },
    onError: () => toast.error('Failed to approve'),
  })
  const rejectMut = useMutation({
    mutationFn: (txId: number) => timeBankApi.reject(txId),
    onSuccess: () => { toast.success('Rejected'); qc.invalidateQueries({ queryKey: ['time-bank'] }) },
    onError: () => toast.error('Failed to reject'),
  })
  const processMut = useMutation({
    mutationFn: (txId: number) => timeBankApi.process(txId),
    onSuccess: () => { toast.success('Processed'); qc.invalidateQueries({ queryKey: ['time-bank'] }) },
    onError: () => toast.error('Failed to process'),
  })

  const filtered = useMemo(() => {
    if (!data?.data) return []
    if (!search) return data.data
    const q = search.toLowerCase()
    return data.data.filter(tx =>
      (tx.employee_name || '').toLowerCase().includes(q) ||
      (tx.description || '').toLowerCase().includes(q),
    )
  }, [data?.data, search])

  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Select value={txType} onValueChange={(v) => { setTxType(v); setPage(0) }}>
            <SelectTrigger className="w-[180px] h-8 text-xs">
              <SelectValue placeholder="All Types" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Types</SelectItem>
              {Object.entries(TX_TYPE_LABELS).map(([k, v]) => (
                <SelectItem key={k} value={k}>{v}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(0) }}>
            <SelectTrigger className="w-[140px] h-8 text-xs">
              <SelectValue placeholder="All Statuses" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Statuses</SelectItem>
              <SelectItem value="pending">Pending</SelectItem>
              <SelectItem value="approved">Approved</SelectItem>
              <SelectItem value="processed">Processed</SelectItem>
              <SelectItem value="rejected">Rejected</SelectItem>
            </SelectContent>
          </Select>
          <Input type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(0) }}
            className="w-[140px] h-8 text-xs" />
          <span className="text-xs text-muted-foreground">→</span>
          <Input type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(0) }}
            className="w-[140px] h-8 text-xs" />
        </div>
        <span className="text-xs text-muted-foreground">{total} transaction{total !== 1 ? 's' : ''}</span>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading...
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
          No transactions found
        </div>
      ) : (
        <div className="rounded-md border overflow-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Employee</TableHead>
                <TableHead>Type</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead>Description</TableHead>
                <TableHead className="text-center">Status</TableHead>
                <TableHead>By</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((tx) => (
                <TableRow key={tx.id}>
                  <TableCell className="whitespace-nowrap text-xs">
                    {formatDate(tx.created_at)}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-xs font-medium">
                    {tx.employee_name || '—'}
                  </TableCell>
                  <TableCell>
                    <TxTypeBadge type={tx.tx_type} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums font-medium">
                    <span className={tx.amount > 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}>
                      {tx.amount > 0 ? '+' : ''}{tx.amount}h
                    </span>
                  </TableCell>
                  <TableCell className="text-xs max-w-[250px] truncate">{tx.description || '—'}</TableCell>
                  <TableCell className="text-center">
                    <TxStatusBadge status={tx.status} />
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">{tx.created_by_name || 'System'}</TableCell>
                  <TableCell className="text-right">
                    <TxActions tx={tx} onApprove={approveMut.mutate} onReject={rejectMut.mutate} onProcess={processMut.mutate} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(p => p - 1)}>
            Previous
          </Button>
          <span className="text-xs text-muted-foreground">Page {page + 1} of {totalPages}</span>
          <Button variant="outline" size="sm" disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}>
            Next
          </Button>
        </div>
      )}
    </div>
  )
}

// ─── CO Conversion Panel ───

function ConversionPanel({ search }: { search: string }) {
  const qc = useQueryClient()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [expandedUser, setExpandedUser] = useState<number | null>(null)
  const [conversionTarget, setConversionTarget] = useState<{
    employeeName: string
    employeeUserId: number
    balance: number
    submissions: ConnecteamSubmission[]
  } | null>(null)
  const [coDays, setCoDays] = useState('1')
  const [approverId, setApproverId] = useState<string>('')
  const [approverMode, setApproverMode] = useState<'hierarchy' | 'free'>('hierarchy')

  // Fetch Time Bank balances — only employees with >= 8h are eligible
  const { data: balancesData, isLoading: balancesLoading } = useQuery({
    queryKey: ['time-bank', 'balances'],
    queryFn: () => timeBankApi.getBalances(),
  })

  // Fetch Connecteam submissions for the selected month (context info)
  const { data: recentData, isLoading: subsLoading } = useQuery({
    queryKey: ['connecteam', 'submissions', year, month],
    queryFn: () =>
      fetch(`/connecteam/api/submissions/recent?year=${year}&month=${month}&limit=500`, { credentials: 'include' })
        .then(r => r.json())
        .then(r => r.data as ConnecteamSubmission[]),
  })

  const { data: conversions } = useQuery({
    queryKey: ['connecteam', 'conversions', year, month],
    queryFn: () => connecteamApi.getConversions(year, month),
  })

  const { data: approversRes } = useQuery({
    queryKey: ['connecteam', 'approvers'],
    queryFn: () => connecteamApi.getApprovers(),
    enabled: !!conversionTarget,
  })

  const { data: allUsersRes } = useQuery({
    queryKey: ['connecteam', 'approvers', 'all'],
    queryFn: () => connecteamApi.getApprovers('all'),
    enabled: !!conversionTarget && approverMode === 'free',
  })

  const approvers = (approverMode === 'free' ? allUsersRes?.data : approversRes?.data) ?? []

  const conversionMut = useMutation({
    mutationFn: (data: Parameters<typeof connecteamApi.createConversion>[0]) =>
      connecteamApi.createConversion(data),
    onSuccess: () => {
      toast.success('Conversion request sent for approval')
      qc.invalidateQueries({ queryKey: ['connecteam', 'conversions'] })
      qc.invalidateQueries({ queryKey: ['connecteam', 'submissions'] })
      qc.invalidateQueries({ queryKey: ['time-bank'] })
      setConversionTarget(null)
      setCoDays('1')
      setApproverId('')
    },
    onError: (err: { response?: { data?: { error?: string } } }) => {
      toast.error(err.response?.data?.error || 'Failed to create conversion')
    },
  })

  // Group Connecteam submissions by jarvis user id for detail display
  const submissionsByUser = useMemo(() => {
    const map = new Map<number, ConnecteamSubmission[]>()
    if (!recentData) return map
    for (const s of recentData) {
      if (!s.mapped_jarvis_user_id) continue
      const arr = map.get(s.mapped_jarvis_user_id) || []
      arr.push(s)
      map.set(s.mapped_jarvis_user_id, arr)
    }
    return map
  }, [recentData])

  const conversionsByUser = useMemo(() => {
    const map = new Map<number, ConversionRequest>()
    if (conversions) {
      for (const c of conversions) map.set(c.employee_user_id, c)
    }
    return map
  }, [conversions])

  // Eligible employees: balance >= 8h, filtered by search
  const eligible = useMemo(() => {
    if (!balancesData) return []
    return (balancesData as TimeBankBalance[])
      .filter((b: TimeBankBalance) => b.balance >= 8)
      .filter((b: TimeBankBalance) => {
        if (!search) return true
        const q = search.toLowerCase()
        return b.name.toLowerCase().includes(q) || (b.company || '').toLowerCase().includes(q)
      })
      .sort((a: TimeBankBalance, b: TimeBankBalance) => b.balance - a.balance)
  }, [balancesData, search])

  const monthLabel = new Date(year, month - 1).toLocaleString('ro-RO', { month: 'long', year: 'numeric' })
  const prevMonth = () => { if (month === 1) { setMonth(12); setYear(y => y - 1) } else setMonth(m => m - 1) }
  const nextMonth = () => { if (month === 12) { setMonth(1); setYear(y => y + 1) } else setMonth(m => m + 1) }

  const openConversion = (emp: { user_id: number; name: string; balance: number }) => {
    const subs = submissionsByUser.get(emp.user_id) || []
    setConversionTarget({ employeeName: emp.name, employeeUserId: emp.user_id, balance: emp.balance, submissions: subs })
    setCoDays('1')
    setApproverId('')
  }

  const submitConversion = () => {
    if (!conversionTarget || !approverId) return
    conversionMut.mutate({
      employee_user_id: conversionTarget.employeeUserId,
      year, month,
      co_days_requested: parseInt(coDays),
      approver_user_id: parseInt(approverId),
      submission_ids: conversionTarget.submissions.map(s => s.submission_id),
    })
  }

  const maxCoDays = conversionTarget ? Math.max(1, Math.floor(conversionTarget.balance / 8)) : 1
  const isLoading = balancesLoading || subsLoading

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" onClick={prevMonth}>
          <ChevronDown className="h-4 w-4 rotate-90" />
        </Button>
        <span className="text-sm font-medium capitalize w-40 text-center">{monthLabel}</span>
        <Button variant="ghost" size="icon" onClick={nextMonth}>
          <ChevronDown className="h-4 w-4 -rotate-90" />
        </Button>
        <span className="text-xs text-muted-foreground ml-2">
          {eligible.length} employee{eligible.length !== 1 ? 's' : ''} eligible (balance {'\u2265'} 8h)
        </span>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading...
        </div>
      ) : eligible.length === 0 ? (
        <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
          No employees with 8h+ Time Bank balance
        </div>
      ) : (
        <div className="rounded-md border divide-y">
          {eligible.map(emp => {
            const isOpen = expandedUser === emp.user_id
            const existing = conversionsByUser.get(emp.user_id)
            const subs = submissionsByUser.get(emp.user_id) || []
            const maxDays = Math.floor(emp.balance / 8)

            return (
              <div key={emp.user_id}>
                {/* Collapsed row */}
                <button
                  type="button"
                  className="w-full flex items-center gap-3 px-3 py-2 hover:bg-muted/50 transition-colors text-left"
                  onClick={() => setExpandedUser(isOpen ? null : emp.user_id)}
                >
                  <ChevronDown className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform ${isOpen ? '' : '-rotate-90'}`} />
                  <span className="font-medium text-sm flex-1 truncate">{emp.name}</span>
                  <span className="text-xs text-muted-foreground whitespace-nowrap">
                    {emp.company?.replace(' S.R.L.', '') || '—'}
                  </span>
                  <span className="tabular-nums text-sm font-semibold text-green-600 dark:text-green-400 w-16 text-right">
                    {emp.balance}h
                  </span>
                  <span className="text-xs text-muted-foreground w-20 text-right">
                    max {maxDays} CO day{maxDays !== 1 ? 's' : ''}
                  </span>
                  <span className="w-28 text-center">
                    {existing ? (
                      <ConversionStatusBadge conversion={existing} />
                    ) : (
                      <Badge variant="outline" className="text-[10px] border-blue-200 text-blue-600 bg-blue-50 dark:bg-blue-950/30">
                        Eligible
                      </Badge>
                    )}
                  </span>
                </button>

                {/* Expanded detail */}
                {isOpen && (
                  <div className="px-4 pb-3 pt-1 bg-muted/30 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="text-xs text-muted-foreground space-y-0.5">
                        <p>Time Bank balance: <span className="font-semibold text-foreground">{emp.balance}h</span></p>
                        <p>Max convertible: <span className="font-semibold text-foreground">{maxDays} CO day{maxDays !== 1 ? 's' : ''}</span> ({maxDays * 8}h)</p>
                        {subs.length > 0 && (
                          <p>Leave permits this month: <span className="font-medium text-foreground">{subs.length}</span> ({subs.reduce((s, x) => s + (x.leave_hours ?? 0), 0)}h)</p>
                        )}
                      </div>
                      {!existing && (
                        <Button
                          variant="default" size="sm" className="h-7 text-xs gap-1.5"
                          onClick={() => openConversion(emp)}
                        >
                          <ArrowRightLeft className="h-3 w-3" />
                          Convert to CO
                        </Button>
                      )}
                    </div>

                    {/* Permit details if any */}
                    {subs.length > 0 && (
                      <div className="rounded border bg-background">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead className="text-xs py-1">Date</TableHead>
                              <TableHead className="text-xs py-1">Hours</TableHead>
                              <TableHead className="text-xs py-1">Status</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {subs.map(s => (
                              <TableRow key={s.submission_id}>
                                <TableCell className="text-xs py-1">{formatDate(s.leave_date || '')}</TableCell>
                                <TableCell className="text-xs py-1 tabular-nums">{s.leave_hours ?? 0}h</TableCell>
                                <TableCell className="text-xs py-1">
                                  <Badge variant="outline" className="text-[9px]">{s.status || 'submitted'}</Badge>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Conversion Dialog */}
      <Dialog open={!!conversionTarget} onOpenChange={(open) => { if (!open) { setConversionTarget(null); setApproverMode('hierarchy') } }}>
        <DialogContent className="sm:max-w-[420px]">
          <DialogHeader>
            <DialogTitle>Convert Time Bank to CO</DialogTitle>
          </DialogHeader>
          {conversionTarget && (
            <div className="space-y-4">
              <div className="space-y-1">
                <p className="text-sm font-medium">{conversionTarget.employeeName}</p>
                <p className="text-xs text-muted-foreground">
                  Time Bank balance: <span className="font-medium text-foreground">{conversionTarget.balance}h</span>
                </p>
                {conversionTarget.submissions.length > 0 && (
                  <p className="text-xs text-muted-foreground">
                    {conversionTarget.submissions.length} permit{conversionTarget.submissions.length !== 1 ? 's' : ''} will be marked as converted
                  </p>
                )}
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">CO Days to convert</label>
                <Select value={coDays} onValueChange={setCoDays}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Array.from({ length: maxCoDays }, (_, i) => i + 1).map(n => (
                      <SelectItem key={n} value={String(n)}>
                        {n} day{n > 1 ? 's' : ''} ({n * 8}h) — remaining: {conversionTarget.balance - n * 8}h
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-[10px] text-muted-foreground">
                  1 CO day = 8 hours. Max {maxCoDays} day{maxCoDays > 1 ? 's' : ''} from {conversionTarget.balance}h balance.
                  After conversion: <span className="font-medium">{conversionTarget.balance - parseInt(coDays) * 8}h remaining</span>.
                </p>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium">Send for approval to</label>
                  <button
                    type="button"
                    className="text-[11px] text-muted-foreground hover:text-foreground underline"
                    onClick={() => { setApproverMode(m => m === 'hierarchy' ? 'free' : 'hierarchy'); setApproverId('') }}
                  >
                    {approverMode === 'hierarchy' ? 'Select any user' : 'Show managers only'}
                  </button>
                </div>
                {approverMode === 'hierarchy' ? (
                  <Select value={approverId} onValueChange={setApproverId}>
                    <SelectTrigger className="w-full"><SelectValue placeholder="Select manager..." /></SelectTrigger>
                    <SelectContent>
                      {approvers.map(a => (
                        <SelectItem key={a.id} value={String(a.id)}>{a.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <SearchSelect
                    value={approverId}
                    onValueChange={setApproverId}
                    options={approvers.map(a => ({ value: String(a.id), label: a.name }))}
                    placeholder="Search user..."
                    searchPlaceholder="Type to search..."
                    emptyMessage="No users found."
                  />
                )}
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setConversionTarget(null)}>Cancel</Button>
                <Button onClick={submitConversion} disabled={!approverId || conversionMut.isPending}>
                  {conversionMut.isPending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
                  Send for Approval
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ─── Help Panel ───

function HelpPanel() {
  const [expanded, setExpanded] = useState<string | null>(null)
  const [showChat, setShowChat] = useState(false)

  const toggle = (key: string) => setExpanded(expanded === key ? null : key)

  const sections: { key: string; title: string; content: React.ReactNode }[] = [
    {
      key: 'overview',
      title: 'What is the Time Bank?',
      content: (
        <p className="text-sm text-muted-foreground leading-relaxed">
          The Time Bank is an <strong>append-only ledger</strong> that tracks hours for each employee.
          Hours flow in from various sources (leave permits, starting balances, manual credits) and can be
          used for CO (vacation day) conversion or manual debits. Only <strong>approved</strong> and{' '}
          <strong>processed</strong> transactions count toward the visible balance.
        </p>
      ),
    },
    {
      key: 'inflows',
      title: 'Sources of Hours (Inflows)',
      content: (
        <div className="space-y-2 text-sm text-muted-foreground">
          <div className="flex items-start gap-2">
            <Badge variant="outline" className="shrink-0 text-[10px] border-green-300 text-green-600 bg-green-50">T0</Badge>
            <span><strong>Starting Balance</strong> — initial hours imported from Excel or set manually. One-time per employee. Auto-approved.</span>
          </div>
          <div className="flex items-start gap-2">
            <Badge variant="outline" className="shrink-0 text-[10px] border-green-300 text-green-600 bg-green-50">Connecteam</Badge>
            <span><strong>Connecteam Import</strong> — leave permit hours (Bilet de Invoire) from Connecteam Excel export. Auto-approved on import.</span>
          </div>
          <div className="flex items-start gap-2">
            <Badge variant="outline" className="shrink-0 text-[10px] border-green-300 text-green-600 bg-green-50">JARVIS Form</Badge>
            <span><strong>JARVIS Leave Permit</strong> — hours submitted via the internal Bilet de Invoire form in JARVIS. Employees fill in leave date, start/end time, reason, and destination. Requires approval.</span>
          </div>
          <div className="flex items-start gap-2">
            <Badge variant="outline" className="shrink-0 text-[10px] border-green-300 text-green-600 bg-green-50">Manual Credit</Badge>
            <span><strong>Manual Credit</strong> — hours added by an admin. Starts as <em>pending</em>, requires approval.</span>
          </div>
          <div className="flex items-start gap-2">
            <Badge variant="outline" className="shrink-0 text-[10px] border-green-300 text-green-600 bg-green-50">Marketing</Badge>
            <span><strong>Marketing Event</strong> — hours earned from marketing activities. Auto-approved.</span>
          </div>
        </div>
      ),
    },
    {
      key: 'outflows',
      title: 'Uses of Hours (Outflows)',
      content: (
        <div className="space-y-2 text-sm text-muted-foreground">
          <div className="flex items-start gap-2">
            <Badge variant="outline" className="shrink-0 text-[10px] border-red-300 text-red-600 bg-red-50">CO Conversion</Badge>
            <span><strong>CO Conversion</strong> — convert 8 hours = 1 vacation day (CO). Employee must have at least 8h balance. Debits 8h per CO day. Requires approval.</span>
          </div>
          <div className="flex items-start gap-2">
            <Badge variant="outline" className="shrink-0 text-[10px] border-red-300 text-red-600 bg-red-50">Manual Debit</Badge>
            <span><strong>Manual Debit</strong> — hours removed by an admin. Starts as <em>pending</em>, requires approval. Cannot exceed current balance.</span>
          </div>
        </div>
      ),
    },
    {
      key: 'approval',
      title: 'Approval Workflow',
      content: (
        <div className="space-y-3 text-sm text-muted-foreground">
          <p>Transactions go through a lifecycle of statuses:</p>
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="outline" className="text-[10px] border-yellow-300 text-yellow-600 bg-yellow-50">
              <Clock className="mr-0.5 h-3 w-3" />Pending
            </Badge>
            <span className="text-muted-foreground">→</span>
            <Badge variant="outline" className="text-[10px] border-green-300 text-green-600 bg-green-50">
              <Check className="mr-0.5 h-3 w-3" />Approved
            </Badge>
            <span className="text-muted-foreground">→</span>
            <Badge variant="outline" className="text-[10px] border-blue-300 text-blue-600 bg-blue-50">
              <CheckCircle2 className="mr-0.5 h-3 w-3" />Processed
            </Badge>
          </div>
          <p>Or rejected:</p>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-[10px] border-yellow-300 text-yellow-600 bg-yellow-50">
              <Clock className="mr-0.5 h-3 w-3" />Pending
            </Badge>
            <span className="text-muted-foreground">→</span>
            <Badge variant="outline" className="text-[10px] border-red-300 text-red-600 bg-red-50">
              <X className="mr-0.5 h-3 w-3" />Rejected
            </Badge>
          </div>
          <p className="mt-2">
            <strong>Auto-approved types:</strong> T0, Connecteam, Marketing Event, and CO Conversion skip the pending state
            and are immediately approved. Manual credits, manual debits, and JARVIS Form submissions require explicit approval.
          </p>
        </div>
      ),
    },
    {
      key: 'co-conversion',
      title: 'CO Conversion Rules',
      content: (
        <div className="space-y-2 text-sm text-muted-foreground">
          <ul className="list-disc list-inside space-y-1">
            <li><strong>1 CO day = 8 hours</strong> deducted from the Time Bank</li>
            <li>Employee must have <strong>at least 8 hours</strong> approved balance to be eligible</li>
            <li>Maximum CO days = floor(balance / 8). E.g., 20h balance → max 2 CO days</li>
            <li>After conversion, remaining hours stay in the bank. E.g., 20h - 16h (2 days) = 4h remaining</li>
            <li>CO conversion creates an approval request sent to the selected approver</li>
            <li>Once approved, the employee's CO balance is credited in the Sincron system</li>
          </ul>
        </div>
      ),
    },
    {
      key: 't0',
      title: 'T0 — Starting Balance',
      content: (
        <div className="space-y-2 text-sm text-muted-foreground">
          <p>
            T0 is the <strong>initial balance</strong> imported when the Time Bank is first set up for an employee.
            It represents hours accumulated before the system was in place.
          </p>
          <ul className="list-disc list-inside space-y-1">
            <li>Can be set individually via the Balances tab (click T0 on an employee row)</li>
            <li>Can be bulk-imported from an Excel template (download template from the toolbar)</li>
            <li>Only one T0 per employee — re-importing replaces the previous value</li>
            <li>T0 is auto-approved and immediately reflected in the balance</li>
          </ul>
        </div>
      ),
    },
  ]

  return (
    <div className="space-y-6">
      {/* Flow Diagram */}
      <div className="rounded-lg border bg-card p-6">
        <h3 className="text-sm font-semibold mb-4">How Hours Flow Through the Time Bank</h3>
        <div className="flex flex-col items-center gap-2">
          {/* Inflows */}
          <div className="flex flex-wrap justify-center gap-3">
            <div className="rounded-md border border-green-200 bg-green-50 dark:bg-green-950/30 px-3 py-1.5 text-xs font-medium text-green-700 dark:text-green-400">
              T0 (Starting)
            </div>
            <div className="rounded-md border border-green-200 bg-green-50 dark:bg-green-950/30 px-3 py-1.5 text-xs font-medium text-green-700 dark:text-green-400">
              Connecteam Import
            </div>
            <div className="rounded-md border border-green-200 bg-green-50 dark:bg-green-950/30 px-3 py-1.5 text-xs font-medium text-green-700 dark:text-green-400">
              JARVIS Form
            </div>
            <div className="rounded-md border border-green-200 bg-green-50 dark:bg-green-950/30 px-3 py-1.5 text-xs font-medium text-green-700 dark:text-green-400">
              Manual Credit
            </div>
            <div className="rounded-md border border-green-200 bg-green-50 dark:bg-green-950/30 px-3 py-1.5 text-xs font-medium text-green-700 dark:text-green-400">
              Marketing Event
            </div>
          </div>

          {/* Down arrows */}
          <div className="flex gap-8">
            <ArrowDown className="h-5 w-5 text-green-500" />
            <ArrowDown className="h-5 w-5 text-green-500" />
            <ArrowDown className="h-5 w-5 text-green-500" />
          </div>

          {/* Central Bank */}
          <div className="rounded-xl border-2 border-primary bg-primary/5 px-8 py-4 text-center">
            <div className="text-lg font-bold">TIME BANK</div>
            <div className="text-xs text-muted-foreground mt-0.5">Balance = SUM of approved + processed</div>
          </div>

          {/* Down arrows */}
          <div className="flex gap-12">
            <ArrowDown className="h-5 w-5 text-red-500" />
            <ArrowDown className="h-5 w-5 text-red-500" />
          </div>

          {/* Outflows */}
          <div className="flex flex-wrap justify-center gap-3">
            <div className="rounded-md border border-red-200 bg-red-50 dark:bg-red-950/30 px-3 py-1.5 text-xs font-medium text-red-700 dark:text-red-400">
              CO Conversion (8h = 1 day)
            </div>
            <div className="rounded-md border border-red-200 bg-red-50 dark:bg-red-950/30 px-3 py-1.5 text-xs font-medium text-red-700 dark:text-red-400">
              Manual Debit
            </div>
          </div>
        </div>
      </div>

      {/* Collapsible Sections */}
      <div className="rounded-lg border bg-card divide-y">
        {sections.map((s) => (
          <div key={s.key}>
            <button
              className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-muted/50 transition-colors"
              onClick={() => toggle(s.key)}
            >
              <span className="text-sm font-medium">{s.title}</span>
              <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${expanded === s.key ? '' : '-rotate-90'}`} />
            </button>
            {expanded === s.key && (
              <div className="px-4 pb-4">
                {s.content}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* AI Assistant */}
      <div className="rounded-lg border bg-card p-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold">Ask AI about Time Bank</h3>
            <p className="text-xs text-muted-foreground mt-0.5">Get instant answers about how the Time Bank works</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => setShowChat(!showChat)}>
            <MessageCircle className="mr-1.5 h-3.5 w-3.5" />
            {showChat ? 'Hide Chat' : 'Ask AI'}
          </Button>
        </div>
        {showChat && (
          <div className="mt-4 h-[400px] rounded-md border overflow-hidden">
            <EphemeralChatPopup pageContext="/app/hr/time-bank/help" />
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Shared Components ───

function TxTypeBadge({ type }: { type: string }) {
  const label = TX_TYPE_LABELS[type] || type
  const isCredit = type === 'T0' || type === 'marketing_event' || type === 'manual_credit'
  return (
    <Badge variant="outline" className={`text-[10px] ${
      isCredit
        ? 'border-green-300 text-green-600 bg-green-50 dark:bg-green-950/30'
        : 'border-red-300 text-red-600 bg-red-50 dark:bg-red-950/30'
    }`}>
      {isCredit ? <TrendingUp className="mr-1 h-3 w-3" /> : <TrendingDown className="mr-1 h-3 w-3" />}
      {label}
    </Badge>
  )
}

function TxStatusBadge({ status }: { status: string }) {
  switch (status) {
    case 'pending':
      return (
        <Badge variant="outline" className="text-[10px] border-yellow-300 text-yellow-600 bg-yellow-50 dark:bg-yellow-950/30">
          <Clock className="mr-0.5 h-3 w-3" />Pending
        </Badge>
      )
    case 'approved':
      return (
        <Badge variant="outline" className="text-[10px] border-green-300 text-green-600 bg-green-50 dark:bg-green-950/30">
          <Check className="mr-0.5 h-3 w-3" />Approved
        </Badge>
      )
    case 'processed':
      return (
        <Badge variant="outline" className="text-[10px] border-blue-300 text-blue-600 bg-blue-50 dark:bg-blue-950/30">
          <CheckCircle2 className="mr-0.5 h-3 w-3" />Processed
        </Badge>
      )
    case 'rejected':
      return (
        <Badge variant="outline" className="text-[10px] border-red-300 text-red-600 bg-red-50 dark:bg-red-950/30">
          <X className="mr-0.5 h-3 w-3" />Rejected
        </Badge>
      )
    default:
      return <span className="text-[10px] text-muted-foreground">{status}</span>
  }
}

function TxActions({ tx, onApprove, onReject, onProcess }: {
  tx: { id: number; status: string }
  onApprove: (id: number) => void
  onReject: (id: number) => void
  onProcess: (id: number) => void
}) {
  if (tx.status === 'pending') {
    return (
      <div className="flex justify-end gap-1">
        <Button variant="ghost" size="icon" className="h-7 w-7" title="Approve"
          onClick={() => onApprove(tx.id)}>
          <Check className="h-3.5 w-3.5 text-green-600" />
        </Button>
        <Button variant="ghost" size="icon" className="h-7 w-7" title="Reject"
          onClick={() => onReject(tx.id)}>
          <X className="h-3.5 w-3.5 text-red-600" />
        </Button>
      </div>
    )
  }
  if (tx.status === 'approved') {
    return (
      <Button variant="ghost" size="icon" className="h-7 w-7" title="Mark as Processed"
        onClick={() => onProcess(tx.id)}>
        <CheckCircle2 className="h-3.5 w-3.5 text-blue-600" />
      </Button>
    )
  }
  return null
}

function ConversionStatusBadge({ conversion }: { conversion: ConversionRequest }) {
  switch (conversion.status) {
    case 'pending':
      return (
        <Badge variant="outline" className="text-[10px] border-yellow-300 text-yellow-600 bg-yellow-50 dark:bg-yellow-950/30">
          CO pending ({conversion.co_days_requested}d)
        </Badge>
      )
    case 'approved':
      return (
        <Badge variant="outline" className="text-[10px] border-green-300 text-green-600 bg-green-50 dark:bg-green-950/30">
          {conversion.co_days_requested}d converted
        </Badge>
      )
    case 'rejected':
      return (
        <Badge variant="outline" className="text-[10px] border-red-300 text-red-600 bg-red-50 dark:bg-red-950/30">
          CO rejected
        </Badge>
      )
    default:
      return null
  }
}

function AmountDialog({
  open, title, label, amount, description, showDescription,
  onAmountChange, onDescriptionChange, onClose, onSubmit, isPending, submitLabel,
}: {
  open: boolean
  title: string
  label: string
  amount: string
  description?: string
  showDescription?: boolean
  onAmountChange: (v: string) => void
  onDescriptionChange?: (v: string) => void
  onClose: () => void
  onSubmit: () => void
  isPending: boolean
  submitLabel: string
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-[360px]">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">{label}</label>
            <Input
              type="number" step="0.5" min="0"
              value={amount} onChange={(e) => onAmountChange(e.target.value)}
              placeholder="0"
            />
          </div>
          {showDescription && onDescriptionChange && (
            <div className="space-y-2">
              <label className="text-sm font-medium">Description</label>
              <Input
                value={description || ''} onChange={(e) => onDescriptionChange(e.target.value)}
                placeholder="Optional description..."
              />
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>Cancel</Button>
            <Button onClick={onSubmit} disabled={!amount || isPending}>
              {isPending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
              {submitLabel}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
