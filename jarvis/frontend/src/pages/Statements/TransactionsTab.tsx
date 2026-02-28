import { useState, useMemo, useCallback, memo } from 'react'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { MobileCardList, type MobileCardField } from '@/components/shared/MobileCardList'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Search,
  Trash2,
  ArrowLeftRight,
  Link2,
  Link2Off,
  Wand2,
  Merge,
  Split,
  Eye,
  EyeOff,
  ChevronDown,
  ChevronRight,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { DatePresetSelect } from '@/components/shared/DatePresetSelect'
import { statementsApi } from '@/api/statements'
import { toast } from 'sonner'
import { cn, usePersistedState } from '@/lib/utils'
import { TagBadgeList } from '@/components/shared/TagBadge'
import { TagPicker, TagPickerButton } from '@/components/shared/TagPicker'
import { TagFilter } from '@/components/shared/TagFilter'
import { QueryError } from '@/components/QueryError'
import { tagsApi } from '@/api/tags'
import type { EntityTag } from '@/types/tags'
import type { Transaction, TransactionFilters } from '@/types/statements'

const SORT_OPTIONS = [
  { value: 'newest', label: 'Date: Newest' },
  { value: 'oldest', label: 'Date: Oldest' },
  { value: 'amount_high', label: 'Amount: High' },
  { value: 'amount_low', label: 'Amount: Low' },
]

const STATUS_OPTIONS = [
  { value: '__all__', label: 'All statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'ignored', label: 'Ignored' },
]

function formatDate(d: string) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ro-RO')
}

function formatAmount(amount: number, currency: string) {
  return new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount) + ' ' + currency
}

const statusColors: Record<string, string> = {
  pending: 'bg-yellow-500/10 text-yellow-600 border-yellow-500/30',
  resolved: 'bg-green-500/10 text-green-600 border-green-500/30',
  ignored: 'bg-muted text-muted-foreground',
}

export default function TransactionsTab() {
  const queryClient = useQueryClient()
  const isMobile = useIsMobile()

  // Filters
  const [status, setStatus] = useState('__all__')
  const [companyCui, setCompanyCui] = useState('__all__')
  const [supplier, setSupplier] = useState('__all__')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('newest')
  const [hideIgnored, setHideIgnored] = useState(false)
  const [filterTagIds, setFilterTagIds] = useState<number[]>([])
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = usePersistedState('statements-page-size', 100)

  // Selection
  const [selected, setSelected] = useState<Set<number>>(new Set())

  // Expanded merged
  const [expandedMerged, setExpandedMerged] = useState<Set<number>>(new Set())

  // Dialogs
  const [linkTxnId, setLinkTxnId] = useState<number | null>(null)
  const [mergeDialogOpen, setMergeDialogOpen] = useState(false)
  const [bulkIgnoreIds, setBulkIgnoreIds] = useState<number[] | null>(null)

  // Build filters object
  const filters: TransactionFilters = useMemo(() => ({
    status: status === '__all__' ? undefined : status,
    company_cui: companyCui === '__all__' ? undefined : companyCui,
    supplier: supplier === '__all__' ? undefined : supplier,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    search: search || undefined,
    sort,
    limit: pageSize,
    offset: page * pageSize,
  }), [status, companyCui, supplier, dateFrom, dateTo, search, sort, page, pageSize])

  // Queries
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['statements-transactions', filters],
    queryFn: () => statementsApi.getTransactions(filters),
  })

  const { data: filterOpts } = useQuery({
    queryKey: ['statements-filter-options'],
    queryFn: () => statementsApi.getFilterOptions(),
    staleTime: 5 * 60 * 1000,
  })

  const transactions = data?.transactions ?? []
  const totalCount = data?.count ?? 0

  // Filter out ignored if hidden
  const visibleTxns = useMemo(() => {
    if (!hideIgnored) return transactions
    return transactions.filter((t) => t.status !== 'ignored')
  }, [transactions, hideIgnored])

  // Entity tags for transactions
  const txnIds = useMemo(() => visibleTxns.map((t) => t.id), [visibleTxns])
  const { data: txnTagsMap = {} } = useQuery({
    queryKey: ['entity-tags', 'transaction', txnIds],
    queryFn: () => tagsApi.getEntityTagsBulk('transaction', txnIds),
    enabled: txnIds.length > 0,
  })

  // Apply tag filter client-side
  const displayedTxns = useMemo(() => {
    if (filterTagIds.length === 0) return visibleTxns
    return visibleTxns.filter((t) => {
      const tags = txnTagsMap[String(t.id)] ?? []
      return tags.some((tag) => filterTagIds.includes(tag.id))
    })
  }, [visibleTxns, filterTagIds, txnTagsMap])

  // Mutations
  const updateStatusMutation = useMutation({
    mutationFn: ({ id, newStatus }: { id: number; newStatus: string }) =>
      statementsApi.updateTransaction(id, { status: newStatus as Transaction['status'] }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['statements-transactions'] })
      queryClient.invalidateQueries({ queryKey: ['statements-summary'] })
    },
    onError: () => toast.error('Failed to update status'),
  })

  const bulkIgnoreMutation = useMutation({
    mutationFn: (ids: number[]) => statementsApi.bulkIgnore(ids),
    onSuccess: (_, ids) => {
      toast.success(`${ids.length} transaction(s) ignored`)
      setSelected(new Set())
      queryClient.invalidateQueries({ queryKey: ['statements-transactions'] })
      queryClient.invalidateQueries({ queryKey: ['statements-summary'] })
    },
    onError: () => toast.error('Bulk ignore failed'),
  })

  const unlinkMutation = useMutation({
    mutationFn: (id: number) => statementsApi.unlinkInvoice(id),
    onSuccess: () => {
      toast.success('Invoice unlinked')
      queryClient.invalidateQueries({ queryKey: ['statements-transactions'] })
    },
    onError: () => toast.error('Failed to unlink'),
  })

  const autoMatchMutation = useMutation({
    mutationFn: () => statementsApi.autoMatch({
      transaction_ids: selected.size > 0 ? Array.from(selected) : undefined,
      use_ai: false,
    }),
    onSuccess: (result) => {
      toast.success(result.message || `Matched: ${result.matched}, Suggested: ${result.suggested}`)
      setSelected(new Set())
      queryClient.invalidateQueries({ queryKey: ['statements-transactions'] })
      queryClient.invalidateQueries({ queryKey: ['statements-summary'] })
    },
    onError: () => toast.error('Auto-match failed'),
  })

  const mergeMutation = useMutation({
    mutationFn: (ids: number[]) => statementsApi.mergeTransactions(ids),
    onSuccess: () => {
      toast.success('Transactions merged')
      setSelected(new Set())
      setMergeDialogOpen(false)
      queryClient.invalidateQueries({ queryKey: ['statements-transactions'] })
    },
    onError: () => toast.error('Merge failed'),
  })

  const unmergeMutation = useMutation({
    mutationFn: (id: number) => statementsApi.unmergeTransaction(id),
    onSuccess: () => {
      toast.success('Transaction unmerged')
      queryClient.invalidateQueries({ queryKey: ['statements-transactions'] })
    },
    onError: () => toast.error('Unmerge failed'),
  })

  const acceptMatchMutation = useMutation({
    mutationFn: (id: number) => statementsApi.acceptMatch(id),
    onSuccess: () => {
      toast.success('Match accepted')
      queryClient.invalidateQueries({ queryKey: ['statements-transactions'] })
    },
    onError: () => toast.error('Failed to accept match'),
  })

  const rejectMatchMutation = useMutation({
    mutationFn: (id: number) => statementsApi.rejectMatch(id),
    onSuccess: () => {
      toast.success('Match rejected')
      queryClient.invalidateQueries({ queryKey: ['statements-transactions'] })
    },
    onError: () => toast.error('Failed to reject match'),
  })

  // Selection helpers
  const toggleSelect = useCallback((id: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const allSelected = displayedTxns.length > 0 && displayedTxns.every((t) => selected.has(t.id))
  const someSelected = displayedTxns.some((t) => selected.has(t.id))

  const toggleSelectAll = () => {
    if (allSelected) setSelected(new Set())
    else setSelected(new Set(displayedTxns.map((t) => t.id)))
  }

  const clearFilters = () => {
    setStatus('__all__')
    setCompanyCui('__all__')
    setSupplier('__all__')
    setDateFrom('')
    setDateTo('')
    setSearch('')
    setSort('newest')
    setPage(0)
  }

  // Can merge: 2+ selected, all pending
  const selectedTxns = displayedTxns.filter((t) => selected.has(t.id))
  const canMerge = selectedTxns.length >= 2 && selectedTxns.every((t) => t.status === 'pending')

  const mobileFields: MobileCardField<Transaction>[] = useMemo(() => [
    {
      key: 'vendor',
      label: 'Vendor',
      isPrimary: true,
      render: (t) => t.matched_supplier || t.vendor_name || t.description?.slice(0, 40) || '—',
    },
    {
      key: 'date',
      label: 'Date',
      isSecondary: true,
      render: (t) => formatDate(t.transaction_date),
    },
    {
      key: 'amount',
      label: 'Amount',
      isSecondary: true,
      render: (t) => (
        <span className={t.amount < 0 ? 'text-red-500' : 'text-green-500'}>
          {formatAmount(t.amount, t.currency)}
        </span>
      ),
    },
    {
      key: 'status',
      label: 'Status',
      render: (t) => (
        <Badge variant="outline" className={cn('text-xs', statusColors[t.status])}>
          {t.status}
        </Badge>
      ),
    },
    {
      key: 'company',
      label: 'Company',
      render: (t) => <span className="text-xs">{t.company_name ?? t.company_cui ?? '—'}</span>,
    },
    {
      key: 'invoice',
      label: 'Invoice',
      expandOnly: true,
      render: (t) =>
        t.invoice_id
          ? <Badge variant="secondary" className="text-xs">{t.invoice_number || `#${t.invoice_id}`}</Badge>
          : t.suggested_invoice_id
            ? <Badge variant="outline" className="text-xs border-yellow-500/50 text-yellow-600">Suggested ({Math.round((t.suggested_confidence ?? 0) * 100)}%)</Badge>
            : <span className="text-muted-foreground">—</span>,
    },
    {
      key: 'description',
      label: 'Description',
      expandOnly: true,
      render: (t) => <span className="text-xs text-muted-foreground">{t.description || '—'}</span>,
    },
  ], [])

  const totalPages = Math.ceil(totalCount / pageSize)

  // Stable callbacks for memoized TransactionRow
  const handleStatusChange = useCallback((id: number, newStatus: string) => {
    updateStatusMutation.mutate({ id, newStatus })
  }, [updateStatusMutation])

  const handleLink = useCallback((id: number) => setLinkTxnId(id), [])
  const handleUnlink = useCallback((id: number) => unlinkMutation.mutate(id), [unlinkMutation])
  const handleUnmerge = useCallback((id: number) => unmergeMutation.mutate(id), [unmergeMutation])
  const handleAcceptMatch = useCallback((id: number) => acceptMatchMutation.mutate(id), [acceptMatchMutation])
  const handleRejectMatch = useCallback((id: number) => rejectMatchMutation.mutate(id), [rejectMatchMutation])
  const handleToggleExpand = useCallback((id: number) => {
    setExpandedMerged((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  return (
    <div className="space-y-4">
      {/* Filters row */}
      <div className="flex flex-col gap-2 md:flex-row md:flex-wrap md:items-center">
        <Select value={status} onValueChange={(v) => { setStatus(v); setPage(0) }}>
          <SelectTrigger className="w-28">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={companyCui} onValueChange={(v) => { setCompanyCui(v); setPage(0) }}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Company" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All companies</SelectItem>
            {filterOpts?.companies?.map((c) => (
              <SelectItem key={c.company_cui} value={c.company_cui}>{c.company_name}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={supplier} onValueChange={(v) => { setSupplier(v); setPage(0) }}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Supplier" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All suppliers</SelectItem>
            {filterOpts?.suppliers?.map((s) => (
              <SelectItem key={s} value={s}>{s}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <DatePresetSelect
          startDate={dateFrom}
          endDate={dateTo}
          onChange={(s, e) => { setDateFrom(s); setDateTo(e); setPage(0) }}
        />
        <Input type="date" className="w-36" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(0) }} />
        <Input type="date" className="w-36" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(0) }} />

        <div className="relative w-full md:flex-1 md:max-w-xs">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input className="pl-8" placeholder="Search..." value={search} onChange={(e) => { setSearch(e.target.value); setPage(0) }} />
        </div>

        <Select value={sort} onValueChange={(v) => { setSort(v); setPage(0) }}>
          <SelectTrigger className="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SORT_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Button
          variant={hideIgnored ? 'default' : 'outline'}
          size="sm"
          onClick={() => setHideIgnored(!hideIgnored)}
        >
          {hideIgnored ? <EyeOff className="mr-1 h-3.5 w-3.5" /> : <Eye className="mr-1 h-3.5 w-3.5" />}
          {hideIgnored ? 'Showing non-ignored' : 'Hide ignored'}
        </Button>

        <TagFilter selectedTagIds={filterTagIds} onChange={setFilterTagIds} />

        <Button variant="ghost" size="sm" onClick={clearFilters}>Clear</Button>
      </div>

      {/* Bulk actions */}
      {selected.size > 0 && (
        <div className="flex items-center gap-2 rounded-lg border px-4 py-2 text-sm">
          <span className="font-medium">{selected.size} selected</span>
          <div className="ml-auto flex gap-1.5">
            <Button size="sm" variant="outline" onClick={() => setBulkIgnoreIds(Array.from(selected))}>
              <Trash2 className="mr-1 h-3.5 w-3.5" />
              Ignore
            </Button>
            {canMerge && (
              <Button size="sm" variant="outline" onClick={() => setMergeDialogOpen(true)}>
                <Merge className="mr-1 h-3.5 w-3.5" />
                Merge
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={() => autoMatchMutation.mutate()} disabled={autoMatchMutation.isPending}>
              <Wand2 className="mr-1 h-3.5 w-3.5" />
              Auto-Match
            </Button>
            <TagPickerButton
              entityType="transaction"
              entityIds={Array.from(selected)}
              onTagsChanged={() => queryClient.invalidateQueries({ queryKey: ['entity-tags'] })}
            />
            <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>Deselect</Button>
          </div>
        </div>
      )}

      {/* Table / Card list */}
      {isError ? (
        <QueryError message="Failed to load transactions" onRetry={() => refetch()} />
      ) : isLoading ? (
        isMobile ? (
          <MobileCardList data={[]} fields={mobileFields} getRowId={(t) => t.id} isLoading />
        ) : (
          <Card>
            <CardContent className="p-6">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-10 animate-pulse rounded bg-muted mb-2" />
              ))}
            </CardContent>
          </Card>
        )
      ) : displayedTxns.length === 0 ? (
        <EmptyState
          icon={<ArrowLeftRight className="h-8 w-8" />}
          title="No transactions found"
          description="Upload a bank statement or adjust your filters."
        />
      ) : isMobile ? (
        <>
          <MobileCardList
            data={displayedTxns}
            fields={mobileFields}
            getRowId={(t) => t.id}
            selectable
            selectedIds={selected}
            onToggleSelect={toggleSelect}
            actions={(txn) => (
              <>
                {!txn.invoice_id && txn.status !== 'ignored' && (
                  <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleLink(txn.id)} title="Link invoice">
                    <Link2 className="h-4 w-4" />
                  </Button>
                )}
                {txn.status !== 'ignored' ? (
                  <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground" onClick={() => handleStatusChange(txn.id, 'ignored')} title="Ignore">
                    <EyeOff className="h-4 w-4" />
                  </Button>
                ) : (
                  <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleStatusChange(txn.id, 'pending')} title="Restore">
                    <Eye className="h-4 w-4" />
                  </Button>
                )}
              </>
            )}
          />
          {/* Mobile pagination */}
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>{displayedTxns.length} of {totalCount}</span>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>Prev</Button>
              <span>{page + 1}/{Math.max(1, totalPages)}</span>
              <Button variant="outline" size="sm" disabled={page + 1 >= totalPages} onClick={() => setPage(page + 1)}>Next</Button>
            </div>
          </div>
        </>
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <Checkbox
                      checked={allSelected ? true : someSelected ? 'indeterminate' : false}
                      onCheckedChange={toggleSelectAll}
                    />
                  </TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead>Company</TableHead>
                  <TableHead>Vendor</TableHead>
                  <TableHead>Supplier</TableHead>
                  <TableHead className="max-w-[200px]">Description</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Tags</TableHead>
                  <TableHead>Invoice</TableHead>
                  <TableHead className="w-28">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {displayedTxns.map((txn) => (
                  <TransactionRow
                    key={txn.id}
                    txn={txn}
                    isSelected={selected.has(txn.id)}
                    tags={txnTagsMap[String(txn.id)] ?? []}
                    onToggleSelect={toggleSelect}
                    onStatusChange={handleStatusChange}
                    onLink={handleLink}
                    onUnlink={handleUnlink}
                    onUnmerge={handleUnmerge}
                    onAcceptMatch={handleAcceptMatch}
                    onRejectMatch={handleRejectMatch}
                    isExpanded={expandedMerged.has(txn.id)}
                    onToggleExpand={handleToggleExpand}
                  />
                ))}
              </TableBody>
            </Table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between border-t px-4 py-2 text-xs text-muted-foreground">
            <span>{displayedTxns.length} of {totalCount} transactions</span>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-muted-foreground">Rows</span>
                <Select
                  value={String(pageSize)}
                  onValueChange={(v) => { setPageSize(Number(v)); setPage(0) }}
                >
                  <SelectTrigger className="h-8 w-[70px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {[25, 50, 100, 200].map((n) => (
                      <SelectItem key={n} value={String(n)}>{n}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>
                  Prev
                </Button>
                <span>Page {page + 1} of {Math.max(1, totalPages)}</span>
                <Button variant="outline" size="sm" disabled={page + 1 >= totalPages} onClick={() => setPage(page + 1)}>
                  Next
                </Button>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Link Invoice Dialog */}
      <LinkInvoiceDialog
        transactionId={linkTxnId}
        onClose={() => setLinkTxnId(null)}
      />

      {/* Merge Confirm */}
      <ConfirmDialog
        open={mergeDialogOpen}
        title="Merge Transactions"
        description={`Merge ${selectedTxns.length} transactions into one? This combines amounts and descriptions. Original transactions will be preserved as sources.`}
        onOpenChange={() => setMergeDialogOpen(false)}
        onConfirm={() => mergeMutation.mutate(Array.from(selected))}
      />

      {/* Bulk Ignore Confirm */}
      <ConfirmDialog
        open={!!bulkIgnoreIds}
        title="Ignore Transactions"
        description={`Mark ${bulkIgnoreIds?.length ?? 0} transaction(s) as ignored?`}
        onOpenChange={() => setBulkIgnoreIds(null)}
        onConfirm={() => bulkIgnoreIds && bulkIgnoreMutation.mutate(bulkIgnoreIds)}
        destructive
      />
    </div>
  )
}

/* ──── Transaction Row ──── */

const TransactionRow = memo(function TransactionRow({
  txn, isSelected, tags, onToggleSelect, onStatusChange, onLink, onUnlink, onUnmerge,
  onAcceptMatch, onRejectMatch, isExpanded, onToggleExpand,
}: {
  txn: Transaction
  isSelected: boolean
  tags: EntityTag[]
  onToggleSelect: (id: number) => void
  onStatusChange: (id: number, status: string) => void
  onLink: (id: number) => void
  onUnlink: (id: number) => void
  onUnmerge: (id: number) => void
  onAcceptMatch: (id: number) => void
  onRejectMatch: (id: number) => void
  isExpanded: boolean
  onToggleExpand: (id: number) => void
}) {
  const isMerged = (txn.merged_count ?? 0) > 0

  // Merged sources query
  const { data: mergedSources } = useQuery({
    queryKey: ['merged-sources', txn.id],
    queryFn: () => statementsApi.getMergedSources(txn.id),
    enabled: isExpanded && isMerged,
  })

  return (
    <>
      <TableRow
        className={cn(
          isSelected && 'bg-muted/50',
          txn.status === 'ignored' && 'opacity-50',
          isMerged && 'cursor-pointer hover:bg-muted/40',
        )}
        onClick={(e) => {
          if (isMerged && !(e.target as HTMLElement).closest('button, input, [role="checkbox"], a, [data-no-row-click]')) {
            onToggleExpand(txn.id)
          }
        }}
        aria-expanded={isMerged ? isExpanded : undefined}
      >
        <TableCell>
          <Checkbox checked={isSelected} onCheckedChange={() => onToggleSelect(txn.id)} />
        </TableCell>
        <TableCell className="text-sm whitespace-nowrap">
          <span className="inline-flex items-center gap-1">
            {isMerged && (isExpanded ? <ChevronDown className="h-3 w-3 shrink-0" /> : <ChevronRight className="h-3 w-3 shrink-0" />)}
            {formatDate(txn.transaction_date)}
          </span>
        </TableCell>
        <TableCell className="text-xs text-muted-foreground truncate max-w-[100px]">
          {txn.company_name ?? txn.company_cui ?? '—'}
        </TableCell>
        <TableCell className="text-sm">{txn.vendor_name ?? '—'}</TableCell>
        <TableCell className="text-sm font-medium">{txn.matched_supplier ?? '—'}</TableCell>
        <TableCell className="text-xs text-muted-foreground max-w-[200px] truncate" title={txn.description}>
          {txn.description}
        </TableCell>
        <TableCell className={cn('text-right text-sm font-medium whitespace-nowrap', txn.amount < 0 ? 'text-red-500' : 'text-green-500')}>
          {formatAmount(txn.amount, txn.currency)}
        </TableCell>
        <TableCell>
          <Badge variant="outline" className={cn('text-xs', statusColors[txn.status])}>
            {txn.status}
          </Badge>
        </TableCell>
        <TableCell>
          <TagPicker entityType="transaction" entityId={txn.id} currentTags={tags} onTagsChanged={() => {}}>
            <TagBadgeList tags={tags} />
          </TagPicker>
        </TableCell>
        <TableCell className="text-xs">
          {txn.invoice_id ? (
            <div className="flex items-center gap-1">
              <Badge variant="secondary" className="text-xs">{txn.invoice_number || `#${txn.invoice_id}`}</Badge>
              <button onClick={() => onUnlink(txn.id)} className="text-muted-foreground hover:text-destructive" title="Unlink">
                <Link2Off className="h-3 w-3" />
              </button>
            </div>
          ) : txn.suggested_invoice_id ? (
            <div className="flex items-center gap-1">
              <Badge variant="outline" className="text-xs border-yellow-500/50 text-yellow-600">
                Suggested ({Math.round((txn.suggested_confidence ?? 0) * 100)}%)
              </Badge>
              <button onClick={() => onAcceptMatch(txn.id)} className="text-green-600 hover:text-green-700" title="Accept">
                <Link2 className="h-3 w-3" />
              </button>
              <button onClick={() => onRejectMatch(txn.id)} className="text-muted-foreground hover:text-destructive" title="Reject">
                <Link2Off className="h-3 w-3" />
              </button>
            </div>
          ) : (
            <span className="text-muted-foreground">—</span>
          )}
        </TableCell>
        <TableCell>
          <div className="flex gap-0.5">
            {!txn.invoice_id && txn.status !== 'ignored' && (
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onLink(txn.id)} title="Link invoice">
                <Link2 className="h-3.5 w-3.5" />
              </Button>
            )}
            {txn.status !== 'ignored' ? (
              <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground" onClick={() => onStatusChange(txn.id, 'ignored')} title="Ignore">
                <EyeOff className="h-3.5 w-3.5" />
              </Button>
            ) : (
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onStatusChange(txn.id, 'pending')} title="Restore">
                <Eye className="h-3.5 w-3.5" />
              </Button>
            )}
            {isMerged && (
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onUnmerge(txn.id)} title="Unmerge">
                <Split className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </TableCell>
      </TableRow>

      {/* Merged sources */}
      {isExpanded && mergedSources?.sources?.map((src) => (
        <TableRow key={src.id} className="bg-muted/30">
          <TableCell />
          <TableCell className="text-xs text-muted-foreground">{formatDate(src.transaction_date)}</TableCell>
          <TableCell className="text-xs text-muted-foreground">{src.company_name ?? '—'}</TableCell>
          <TableCell className="text-xs text-muted-foreground">{src.vendor_name ?? '—'}</TableCell>
          <TableCell className="text-xs text-muted-foreground">{src.matched_supplier ?? '—'}</TableCell>
          <TableCell className="text-xs text-muted-foreground truncate max-w-[200px]">{src.description}</TableCell>
          <TableCell className={cn('text-right text-xs', src.amount < 0 ? 'text-red-400' : 'text-green-400')}>
            {formatAmount(src.amount, src.currency)}
          </TableCell>
          <TableCell />
          <TableCell />
          <TableCell />
          <TableCell />
        </TableRow>
      ))}
    </>
  )
})

/* ──── Link Invoice Dialog ──── */

function LinkInvoiceDialog({ transactionId, onClose }: { transactionId: number | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [invoiceSearch, setInvoiceSearch] = useState('')
  const [searchResults, setSearchResults] = useState<{ id: number; invoice_number: string; supplier: string; invoice_value: number; currency: string }[]>([])
  const [searching, setSearching] = useState(false)
  const [selectedInvoice, setSelectedInvoice] = useState<number | null>(null)

  const linkMutation = useMutation({
    mutationFn: ({ txnId, invId }: { txnId: number; invId: number }) => statementsApi.linkInvoice(txnId, invId),
    onSuccess: () => {
      toast.success('Invoice linked')
      queryClient.invalidateQueries({ queryKey: ['statements-transactions'] })
      queryClient.invalidateQueries({ queryKey: ['statements-summary'] })
      onClose()
    },
    onError: () => toast.error('Failed to link invoice'),
  })

  const handleSearch = async () => {
    if (!invoiceSearch.trim()) return
    setSearching(true)
    try {
      const { invoicesApi } = await import('@/api/invoices')
      const results = await invoicesApi.searchInvoices(invoiceSearch)
      setSearchResults(Array.isArray(results) ? results : [])
    } catch {
      setSearchResults([])
    } finally {
      setSearching(false)
    }
  }

  const reset = () => {
    setInvoiceSearch('')
    setSearchResults([])
    setSelectedInvoice(null)
  }

  return (
    <Dialog open={transactionId !== null} onOpenChange={(v) => { if (!v) { onClose(); reset() } }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Link Invoice</DialogTitle>
          <DialogDescription>Search for an invoice to link to this transaction.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="flex gap-2">
            <Input
              placeholder="Search invoice number, supplier..."
              value={invoiceSearch}
              onChange={(e) => setInvoiceSearch(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            />
            <Button onClick={handleSearch} disabled={searching}>
              <Search className="h-4 w-4" />
            </Button>
          </div>
          {searchResults.length > 0 && (
            <div className="max-h-48 space-y-1 overflow-y-auto">
              {searchResults.map((inv) => (
                <button
                  key={inv.id}
                  onClick={() => setSelectedInvoice(inv.id)}
                  className={cn(
                    'flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm hover:bg-accent',
                    selectedInvoice === inv.id && 'bg-primary/10 ring-1 ring-primary',
                  )}
                >
                  <div>
                    <div className="font-medium">{inv.invoice_number}</div>
                    <div className="text-xs text-muted-foreground">{inv.supplier}</div>
                  </div>
                  <div className="text-sm font-medium">
                    {new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2 }).format(inv.invoice_value)} {inv.currency}
                  </div>
                </button>
              ))}
            </div>
          )}
          {searchResults.length === 0 && invoiceSearch && !searching && (
            <p className="text-xs text-muted-foreground text-center py-3">No invoices found</p>
          )}
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={() => { onClose(); reset() }}>Cancel</Button>
          <Button
            disabled={!selectedInvoice || linkMutation.isPending}
            onClick={() => transactionId !== null && selectedInvoice !== null && linkMutation.mutate({ txnId: transactionId, invId: selectedInvoice })}
          >
            Link
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
