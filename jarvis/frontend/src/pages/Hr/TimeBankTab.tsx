import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Loader2, Upload, Plus, Minus, ArrowRightLeft,
  ChevronDown, TrendingUp, TrendingDown,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { SearchSelect } from '@/components/shared/SearchSelect'
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
  const [innerTab, setInnerTab] = useState<'balances' | 'transactions' | 'conversion'>('balances')

  return (
    <div className="space-y-4">
      <Tabs value={innerTab} onValueChange={(v) => setInnerTab(v as typeof innerTab)}>
        <TabsList>
          <TabsTrigger value="balances">Balances</TabsTrigger>
          <TabsTrigger value="transactions">Transactions</TabsTrigger>
          <TabsTrigger value="conversion">CO Conversion</TabsTrigger>
        </TabsList>
      </Tabs>

      {innerTab === 'balances' && <BalancesPanel search={search} />}
      {innerTab === 'transactions' && <TransactionsPanel search={search} />}
      {innerTab === 'conversion' && <ConversionPanel search={search} />}
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
                    {b.balance > 0 ? (
                      <Badge variant="outline" className="text-[10px] border-green-300 text-green-600 bg-green-50 dark:bg-green-950/30">Active</Badge>
                    ) : b.balance < 0 ? (
                      <Badge variant="outline" className="text-[10px] border-red-300 text-red-600 bg-red-50 dark:bg-red-950/30">Overdrawn</Badge>
                    ) : (
                      <Badge variant="outline" className="text-[10px] border-gray-300 text-gray-500 bg-gray-50 dark:bg-gray-950/30">Not Set</Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums font-medium">
                    <span className={b.balance > 0 ? 'text-green-600 dark:text-green-400' : b.balance < 0 ? 'text-red-600 dark:text-red-400' : ''}>
                      {b.balance}h
                    </span>
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
  const { data, isLoading } = useQuery({
    queryKey: ['time-bank', 'transactions', user.id],
    queryFn: () => timeBankApi.getUserTransactions(user.id, { limit: 200 }),
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
                <TableHead>By</TableHead>
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
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">{tx.created_by_name || 'System'}</TableCell>
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
  const [txType, setTxType] = useState<string>('all')
  const [page, setPage] = useState(0)
  const pageSize = 50

  const { data, isLoading } = useQuery({
    queryKey: ['time-bank', 'all-transactions', txType, page],
    queryFn: () => timeBankApi.getTransactions({
      limit: pageSize,
      offset: page * pageSize,
      tx_type: txType !== 'all' ? txType : undefined,
    }),
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
        <Select value={txType} onValueChange={(v) => { setTxType(v); setPage(0) }}>
          <SelectTrigger className="w-[200px] h-8 text-xs">
            <SelectValue placeholder="All Types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Types</SelectItem>
            {Object.entries(TX_TYPE_LABELS).map(([k, v]) => (
              <SelectItem key={k} value={k}>{v}</SelectItem>
            ))}
          </SelectContent>
        </Select>
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
                <TableHead>By</TableHead>
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
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">{tx.created_by_name || 'System'}</TableCell>
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
  const [conversionTarget, setConversionTarget] = useState<{
    employeeName: string
    employeeUserId: number
    totalHours: number
    submissions: ConnecteamSubmission[]
  } | null>(null)
  const [coDays, setCoDays] = useState('1')
  const [approverId, setApproverId] = useState<string>('')
  const [approverMode, setApproverMode] = useState<'hierarchy' | 'free'>('hierarchy')

  const { data: recentData, isLoading } = useQuery({
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

  const grouped = useMemo(() => {
    if (!recentData) return []
    const flt = search
      ? recentData.filter(s => {
          const q = search.toLowerCase()
          return (s.connecteam_user_name || '').toLowerCase().includes(q)
        })
      : recentData
    const map = new Map<string, { submissions: ConnecteamSubmission[]; totalHours: number; company: string | null; userId: number | null }>()
    for (const s of flt) {
      const key = s.connecteam_user_name || `User #${s.connecteam_user_id}`
      if (!map.has(key)) map.set(key, { submissions: [], totalHours: 0, company: s.jarvis_user_company ?? null, userId: s.mapped_jarvis_user_id })
      const group = map.get(key)!
      group.submissions.push(s)
      group.totalHours += s.leave_hours ?? 0
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]))
  }, [recentData, search])

  const conversionsByUser = useMemo(() => {
    const map = new Map<number, ConversionRequest>()
    if (conversions) {
      for (const c of conversions) map.set(c.employee_user_id, c)
    }
    return map
  }, [conversions])

  const monthLabel = new Date(year, month - 1).toLocaleString('ro-RO', { month: 'long', year: 'numeric' })
  const prevMonth = () => { if (month === 1) { setMonth(12); setYear(y => y - 1) } else setMonth(m => m - 1) }
  const nextMonth = () => { if (month === 12) { setMonth(1); setYear(y => y + 1) } else setMonth(m => m + 1) }

  const openConversion = (name: string, userId: number, totalHours: number, submissions: ConnecteamSubmission[]) => {
    setConversionTarget({ employeeName: name, employeeUserId: userId, totalHours, submissions })
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

  const maxCoDays = conversionTarget ? Math.max(1, Math.floor(conversionTarget.totalHours / 8)) : 1

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
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading...
        </div>
      ) : grouped.length === 0 ? (
        <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
          No leave permits for {monthLabel}
        </div>
      ) : (
        <div className="rounded-md border overflow-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Employee</TableHead>
                <TableHead>Company</TableHead>
                <TableHead className="text-right">Permits</TableHead>
                <TableHead className="text-right">Total Hours</TableHead>
                <TableHead className="text-center">CO Conversion</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {grouped.map(([name, { submissions, totalHours, company, userId }]) => {
                const existing = userId ? conversionsByUser.get(userId) : undefined
                return (
                  <TableRow key={name}>
                    <TableCell className="font-medium whitespace-nowrap">{name}</TableCell>
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                      {company?.replace(' S.R.L.', '') || '—'}
                    </TableCell>
                    <TableCell className="text-right text-xs">{submissions.length}</TableCell>
                    <TableCell className="text-right tabular-nums font-medium text-xs">{totalHours}h</TableCell>
                    <TableCell className="text-center">
                      {existing ? (
                        <ConversionStatusBadge conversion={existing} />
                      ) : userId && totalHours >= 8 ? (
                        <Button
                          variant="outline" size="sm" className="h-6 text-[10px] gap-1"
                          onClick={() => openConversion(name, userId, totalHours, submissions)}
                        >
                          <ArrowRightLeft className="h-3 w-3" />
                          Convert to CO
                        </Button>
                      ) : totalHours < 8 ? (
                        <span className="text-[10px] text-muted-foreground">Need 8h+</span>
                      ) : null}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Conversion Dialog */}
      <Dialog open={!!conversionTarget} onOpenChange={(open) => { if (!open) { setConversionTarget(null); setApproverMode('hierarchy') } }}>
        <DialogContent className="sm:max-w-[420px]">
          <DialogHeader>
            <DialogTitle>Convert Leave Permits to CO</DialogTitle>
          </DialogHeader>
          {conversionTarget && (
            <div className="space-y-4">
              <div className="space-y-1">
                <p className="text-sm font-medium">{conversionTarget.employeeName}</p>
                <p className="text-xs text-muted-foreground">
                  Total accumulated: <span className="font-medium text-foreground">{conversionTarget.totalHours}h</span> in {monthLabel}
                </p>
                <p className="text-xs text-muted-foreground">
                  {conversionTarget.submissions.length} permit{conversionTarget.submissions.length !== 1 ? 's' : ''} will be marked as converted
                </p>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">CO Days to convert</label>
                <Select value={coDays} onValueChange={setCoDays}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Array.from({ length: maxCoDays }, (_, i) => i + 1).map(n => (
                      <SelectItem key={n} value={String(n)}>
                        {n} day{n > 1 ? 's' : ''} ({n * 8}h)
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-[10px] text-muted-foreground">
                  1 CO day = 8 hours. Max {maxCoDays} day{maxCoDays > 1 ? 's' : ''} based on {conversionTarget.totalHours}h accumulated.
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
