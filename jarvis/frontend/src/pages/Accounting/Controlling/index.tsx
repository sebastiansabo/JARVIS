import { useState, useCallback, useMemo, Fragment } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload, Lock, Unlock, FileSpreadsheet, AlertTriangle, Download, ChevronRight, ChevronDown, Plus, Trash2, Pencil, Save, X, Star, Check } from 'lucide-react'
import { toast } from 'sonner'

import { api } from '@/api/client'
import { controllingApi } from '@/api/controlling'
import { useAuthStore } from '@/stores/authStore'
import type { BabPeriod, MarjaReportData, BabAccountGroup, BabConfigRow } from '@/types/controlling'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
// Tooltip removed — not used in current layout

const MONTH_NAMES = ['', 'IAN', 'FEB', 'MAR', 'APR', 'MAI', 'IUN', 'IUL', 'AUG', 'SEP', 'OCT', 'NOI', 'DEC']
const MONTH_NAMES_LONG = ['', 'Ianuarie', 'Februarie', 'Martie', 'Aprilie', 'Mai', 'Iunie', 'Iulie', 'August', 'Septembrie', 'Octombrie', 'Noiembrie', 'Decembrie']

function fmtNum(value: number): string {
  return new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)
}

// configToSections removed — report sections come directly from API now

export default function Controlling() {
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  // Persist company + tab to URL params
  const params = new URLSearchParams(window.location.search)
  const [companyId, setCompanyIdState] = useState<number>(Number(params.get('company')) || (user as unknown as Record<string, unknown>)?.company_id as number || 0)
  const [activeTab, setActiveTab] = useState(params.get('tab') || 'marja')

  const setCompanyId = useCallback((id: number) => {
    setCompanyIdState(id)
    const url = new URL(window.location.href)
    url.searchParams.set('company', String(id))
    window.history.replaceState({}, '', url.toString())
  }, [])

  const handleTabChange = useCallback((tab: string) => {
    setActiveTab(tab)
    const url = new URL(window.location.href)
    url.searchParams.set('tab', tab)
    window.history.replaceState({}, '', url.toString())
  }, [])
  const [showEur, setShowEur] = useState(false)
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())

  // Import modal
  const [importModal, setImportModal] = useState<{ year: number; month: number; existing?: BabPeriod } | null>(null)
  const [importFile, setImportFile] = useState<File | null>(null)
  const [eurRateInput, setEurRateInput] = useState('')
  const [eurRateLoading, setEurRateLoading] = useState(false)

  // Lock confirm
  const [lockConfirm, setLockConfirm] = useState<BabPeriod | null>(null)

  // Verification tab state
  const [verifyUploadId, setVerifyUploadId] = useState<number | null>(null)

  // Companies
  const { data: companiesData } = useQuery({
    queryKey: ['bab-companies'],
    queryFn: () => api.get<{ success: boolean; companies: { id: number; company: string }[] }>('/controlling/bab/api/companies'),
  })
  const companies: { id: number; company: string }[] = companiesData?.companies || []
  if (companyId === 0 && companies.length > 0) setCompanyId(companies[0].id)

  // Periods
  const { data: periodsData, isLoading: periodsLoading } = useQuery({
    queryKey: ['bab-periods', companyId],
    queryFn: () => controllingApi.getPeriods(companyId),
    enabled: companyId > 0,
  })
  const periods: BabPeriod[] = periodsData?.periods || []
  const importedPeriods = useMemo(() => periods.filter(p => p.status !== 'MISSING' && p.upload_id), [periods])

  // Fetch all reports
  const { data: reportsData } = useQuery({
    queryKey: ['bab-all-reports', companyId, importedPeriods.map(p => p.upload_id).join(',')],
    queryFn: async () => {
      const results: Record<number, MarjaReportData> = {}
      await Promise.all(importedPeriods.map(async (p) => {
        if (!p.upload_id) return
        try {
          const res = await controllingApi.getReport(p.upload_id)
          if (res?.report) results[p.upload_id] = res.report
        } catch { /* skip */ }
      }))
      return results
    },
    enabled: importedPeriods.length > 0,
  })
  const reports = reportsData || {}

  // Report config (drives the table structure)
  const { data: configData } = useQuery({
    queryKey: ['bab-config', companyId],
    queryFn: () => controllingApi.getConfig(companyId),
    enabled: companyId > 0,
  })
  const configRows: BabConfigRow[] = configData?.config || []

  // Verification data
  const { data: verificationData } = useQuery({
    queryKey: ['bab-verification', verifyUploadId],
    queryFn: () => controllingApi.getVerification(verifyUploadId!),
    enabled: !!verifyUploadId,
  })

  const toggleRow = useCallback((key: string) => {
    setExpandedRows(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }, [])

  // Import mutation
  const importMutation = useMutation({
    mutationFn: async () => {
      if (!importFile || !importModal) throw new Error('No file selected')
      if (eurRateInput) {
        await controllingApi.setEurRate(importModal.year, importModal.month, companyId, parseFloat(eurRateInput))
      }
      return controllingApi.importBab(importFile, importModal.year, importModal.month, companyId)
    },
    onSuccess: (data) => {
      toast.success(`BAB importat: ${data.row_count} linii (import #${data.import_count})`)
      queryClient.invalidateQueries({ queryKey: ['bab-periods'] })
      queryClient.invalidateQueries({ queryKey: ['bab-all-reports'] })
      setImportModal(null)
      setImportFile(null)
      setEurRateInput('')
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const lockMutation = useMutation({
    mutationFn: (uploadId: number) => controllingApi.lockUpload(uploadId),
    onSuccess: () => { toast.success('Perioadă blocată'); queryClient.invalidateQueries({ queryKey: ['bab-periods'] }); setLockConfirm(null) },
    onError: (err: Error) => toast.error(err.message),
  })

  const unlockMutation = useMutation({
    mutationFn: (uploadId: number) => controllingApi.unlockUpload(uploadId),
    onSuccess: () => { toast.success('Perioadă deblocată'); queryClient.invalidateQueries({ queryKey: ['bab-periods'] }) },
    onError: (err: Error) => toast.error(err.message),
  })

  const openImportModal = useCallback((year: number, month: number, existing?: BabPeriod) => {
    setImportModal({ year, month, existing })
    setImportFile(null)
    setEurRateInput('')
    setEurRateLoading(true)
    // Auto-fetch BNR rate
    controllingApi.getBnrRate(year, month)
      .then(res => { if (res?.eur_rate) setEurRateInput(String(res.eur_rate)) })
      .catch(() => {})
      .finally(() => setEurRateLoading(false))
    // Also check if rate already saved
    if (companyId > 0) {
      controllingApi.getEurRate(year, month, companyId)
        .then(res => { if (res?.rate) setEurRateInput(String(res.rate.eur_rate)) })
        .catch(() => {})
    }
  }, [companyId])

  const handleFileDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const f = e.dataTransfer.files[0]
    if (f && f.name.toLowerCase().endsWith('.xlsx')) setImportFile(f)
    else toast.error('Doar fișiere .xlsx')
  }, [])

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) setImportFile(f)
  }, [])

  return (
    <div className="p-4 sm:p-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">Controlling — BAB</h1>
          <p className="text-sm text-muted-foreground">Raport Marjă Vânzări</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button variant="outline" size="sm" onClick={() => openImportModal(new Date().getFullYear(), new Date().getMonth() + 1)}>
            <Upload className="h-3.5 w-3.5 mr-1.5" /> Import perioadă
          </Button>
          <Button variant="outline" size="sm" onClick={() => setShowEur(!showEur)}>
            {showEur ? 'EUR → LEI' : 'LEI → EUR'}
          </Button>
          <Select value={String(companyId)} onValueChange={(v) => setCompanyId(Number(v))}>
            <SelectTrigger className="w-56">
              <SelectValue placeholder="Selectează compania" />
            </SelectTrigger>
            <SelectContent>
              {companies.map((c: { id: number; company: string }) => (
                <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList>
          <TabsTrigger value="marja">Marjă</TabsTrigger>
          <TabsTrigger value="verificare">Verificare</TabsTrigger>
          <TabsTrigger value="configurare">Configurare</TabsTrigger>
        </TabsList>

        {/* ═══ TAB: Marjă ═══ */}
        <TabsContent value="marja" className="mt-4">
          {periodsLoading ? (
            <div className="text-center py-12 text-muted-foreground">Se încarcă...</div>
          ) : importedPeriods.length === 0 ? (
            <Card><CardContent className="py-12 text-center text-muted-foreground text-sm">Nicio perioadă importată. Folosește butonul "Import perioadă" pentru a începe.</CardContent></Card>
          ) : (
            <Card>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-6 px-1"></TableHead>
                      <TableHead className="w-14">An</TableHead>
                      <TableHead className="w-28">Perioadă</TableHead>
                      <TableHead className="w-24">Status</TableHead>
                      <TableHead className="text-right w-44">Marjă Finală (LEI)</TableHead>
                      <TableHead className="text-right w-44">Marjă Finală (EUR)</TableHead>
                      <TableHead className="w-28 text-right">Acțiuni</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {importedPeriods.map((p) => {
                      const isExpanded = expandedRows.has(`period-${p.upload_id}`)
                      const report = p.upload_id ? reports[p.upload_id] : null
                      return (
                        <Fragment key={p.upload_id}>
                          <TableRow
                            className="cursor-pointer"
                            onClick={() => toggleRow(`period-${p.upload_id}`)}
                          >
                            <TableCell className="px-1 w-6">
                              {isExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                            </TableCell>
                            <TableCell className="font-medium">{p.year}</TableCell>
                            <TableCell className="font-medium">{MONTH_NAMES_LONG[p.month]}</TableCell>
                            <TableCell>
                              {p.status === 'LOCKED' && (
                                <span className="inline-flex items-center gap-1 text-xs font-medium text-blue-700 bg-blue-100 rounded-full px-2 py-0.5">
                                  <Lock className="h-2.5 w-2.5" /> Blocat
                                </span>
                              )}
                              {p.status === 'IMPORTED' && (
                                <span className="inline-flex items-center gap-1 text-xs font-medium text-green-700 bg-green-100 rounded-full px-2 py-0.5">
                                  ✓ Importat
                                </span>
                              )}
                            </TableCell>
                            <TableCell className={`text-right font-mono tabular-nums ${p.marja_finala_lei != null && p.marja_finala_lei < 0 ? 'text-destructive' : ''}`}>
                              {p.marja_finala_lei != null ? fmtNum(p.marja_finala_lei) : '—'}
                            </TableCell>
                            <TableCell className={`text-right font-mono tabular-nums ${p.marja_finala_eur != null && p.marja_finala_eur < 0 ? 'text-destructive' : ''}`}>
                              {p.marja_finala_eur != null ? fmtNum(p.marja_finala_eur) : '—'}
                            </TableCell>
                            <TableCell className="text-right" onClick={e => e.stopPropagation()}>
                              <div className="flex items-center justify-end gap-1">
                                {p.status === 'IMPORTED' && (
                                  <>
                                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openImportModal(p.year, p.month, p)} title="Re-import"><Upload className="h-3.5 w-3.5" /></Button>
                                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setLockConfirm(p)} title="Blochează"><Lock className="h-3.5 w-3.5" /></Button>
                                  </>
                                )}
                                {p.status === 'LOCKED' && (
                                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => p.upload_id && unlockMutation.mutate(p.upload_id)} title="Deblochează"><Unlock className="h-3.5 w-3.5" /></Button>
                                )}
                                {p.upload_id && (
                                  <a href={controllingApi.exportReport(p.upload_id)} target="_blank" rel="noreferrer">
                                    <Button variant="ghost" size="icon" className="h-7 w-7" title="Export XLSX"><Download className="h-3.5 w-3.5" /></Button>
                                  </a>
                                )}
                              </div>
                            </TableCell>
                          </TableRow>
                          {/* Expanded: cascaded margin report breakdown */}
                          {isExpanded && report && (
                            <tr className="border-b">
                              <td colSpan={7} className="p-0">
                                <ExpandedReport report={report} />
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      )
                    })}
                  </TableBody>
                </Table>
                <div className="border-t px-4 py-2 text-xs text-muted-foreground">
                  {importedPeriods.length} perioad{importedPeriods.length !== 1 ? 'e' : 'ă'} importat{importedPeriods.length !== 1 ? 'e' : 'ă'}
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* ═══ TAB: Verificare ═══ */}
        <TabsContent value="verificare" className="mt-4">
          <Card>
            <CardContent className="p-4">
              {/* Period selector for verification */}
              <div className="flex items-center gap-3 mb-4">
                <Label className="text-sm shrink-0">Perioada:</Label>
                <Select value={verifyUploadId ? String(verifyUploadId) : ''} onValueChange={(v) => setVerifyUploadId(Number(v))}>
                  <SelectTrigger className="w-64">
                    <SelectValue placeholder="Selectează perioada" />
                  </SelectTrigger>
                  <SelectContent>
                    {importedPeriods.map((p) => (
                      <SelectItem key={p.upload_id} value={String(p.upload_id)}>
                        {MONTH_NAMES[p.month]} {p.year} — {p.filename}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {verifyUploadId && verificationData ? (
                <VerificationTable accounts={verificationData.accounts} totalEntries={verificationData.total_entries} allPeriods={importedPeriods} />
              ) : (
                <div className="text-center py-8 text-muted-foreground text-sm">
                  Selectează o perioadă pentru a vedea datele importate
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ═══ TAB: Configurare ═══ */}
        <TabsContent value="configurare" className="mt-4">
          <Card>
            <CardContent className="p-4">
              <ConfigTable companyId={companyId} setCompanyId={setCompanyId} companies={companies} configRows={configRows} queryClient={queryClient} />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ═══ Import Modal ═══ */}
      <Dialog open={!!importModal} onOpenChange={() => setImportModal(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Import BAB — {importModal ? `${MONTH_NAMES[importModal.month]} ${importModal.year}` : ''}</DialogTitle>
            <DialogDescription>
              {importModal?.existing
                ? `Re-import: va înlocui ${importModal.existing.filename} (import #${(importModal.existing.import_count || 0) + 1})`
                : 'Încarcă fișierul BAB (.xlsx) exportat din ERP.'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            {/* Period selectors */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Luna</Label>
                <Select value={String(importModal?.month || 1)} onValueChange={(v) => {
                  if (!importModal) return
                  const m = Number(v)
                  setImportModal({ ...importModal, month: m })
                  setEurRateLoading(true)
                  controllingApi.getBnrRate(importModal.year, m).then(r => { if (r?.eur_rate) setEurRateInput(String(r.eur_rate)) }).catch(() => {}).finally(() => setEurRateLoading(false))
                }}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {MONTH_NAMES.slice(1).map((name, i) => (
                      <SelectItem key={i + 1} value={String(i + 1)}>{name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Anul</Label>
                <Select value={String(importModal?.year || new Date().getFullYear())} onValueChange={(v) => {
                  if (!importModal) return
                  const y = Number(v)
                  setImportModal({ ...importModal, year: y })
                  setEurRateLoading(true)
                  controllingApi.getBnrRate(y, importModal.month).then(r => { if (r?.eur_rate) setEurRateInput(String(r.eur_rate)) }).catch(() => {}).finally(() => setEurRateLoading(false))
                }}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {[2024, 2025, 2026, 2027].map(y => (
                      <SelectItem key={y} value={String(y)}>{y}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label>Curs EUR BNR (LEI/EUR)</Label>
              <Input
                type="number" step="0.0001"
                placeholder={eurRateLoading ? 'Se preia de la BNR...' : 'ex: 4.9750'}
                value={eurRateInput}
                onChange={(e) => setEurRateInput(e.target.value)}
                disabled={eurRateLoading}
              />
              <p className="text-[11px] text-muted-foreground mt-1">Preluat automat de la BNR (ultima zi a lunii)</p>
            </div>
            <div
              className="border-2 border-dashed rounded-lg p-6 text-center cursor-pointer hover:border-primary transition-colors"
              onDragOver={(e) => e.preventDefault()} onDrop={handleFileDrop}
              onClick={() => document.getElementById('bab-file-input')?.click()}
            >
              {importFile ? (
                <div className="flex items-center justify-center gap-2">
                  <FileSpreadsheet className="h-5 w-5 text-green-600" />
                  <span className="text-sm font-medium">{importFile.name}</span>
                  <span className="text-xs text-muted-foreground">({(importFile.size / 1024).toFixed(0)} KB)</span>
                </div>
              ) : (
                <div>
                  <Upload className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">Drag & drop .xlsx sau click</p>
                </div>
              )}
              <input id="bab-file-input" type="file" accept=".xlsx" className="hidden" onChange={handleFileSelect} />
            </div>
            {importModal?.existing && (
              <div className="flex items-center gap-2 text-amber-600 bg-amber-50 rounded p-2 text-xs">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>Datele existente vor fi înlocuite</span>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setImportModal(null)}>Anulează</Button>
            <Button onClick={() => importMutation.mutate()} disabled={!importFile || !eurRateInput || importMutation.isPending}>
              {importMutation.isPending ? 'Se importă...' : 'Importă BAB'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ═══ Lock Confirm ═══ */}
      <Dialog open={!!lockConfirm} onOpenChange={() => setLockConfirm(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Blochează perioada</DialogTitle>
            <DialogDescription>
              Blochezi {lockConfirm ? `${MONTH_NAMES[lockConfirm.month]} ${lockConfirm.year}` : ''}? Poate fi deblocată ulterior.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setLockConfirm(null)}>Anulează</Button>
            <Button variant="destructive" onClick={() => lockConfirm?.upload_id && lockMutation.mutate(lockConfirm.upload_id)} disabled={lockMutation.isPending}>
              Blochează
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

/* ═══════════════════════════════════════════════════
   Verification Table — raw imported data by account
   ═══════════════════════════════════════════════════ */

/* ═══════════════════════════════════════════
   Expanded Report — cascaded section/row view
   ═══════════════════════════════════════════ */

function ExpandedReport({ report }: { report: MarjaReportData }) {
  return (
    <div className="border-l-2 border-l-primary/30 shadow-[inset_0_1px_0_0_hsl(var(--border)),inset_0_-1px_0_0_hsl(var(--border))]">
      {report.sections.map((section) => (
        <Fragment key={section.section}>
          {/* Section label */}
          <div className="px-8 py-1 bg-muted/40 text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
            {section.section}
          </div>
          {/* Rows */}
          {section.rows.map((row, ri) => {
            const isSubtotal = row.row_type === 'subtotal'
            if (isSubtotal) {
              // Subtotal at top level — same as period row
              return (
                <div key={ri} className="flex items-center justify-between border-b border-border/30 font-semibold" style={{ backgroundColor: 'hsl(0 0% 90%)' }}>
                  <div className="py-2 pl-4 text-sm font-bold">{row.label}</div>
                  <div className="flex shrink-0">
                    <div className="w-44 text-right px-4 py-2 font-mono tabular-nums text-sm">{fmtNum(row.lei)}</div>
                    <div className="w-44 text-right px-4 py-2 font-mono tabular-nums text-sm">{fmtNum(row.eur)}</div>
                  </div>
                </div>
              )
            }
            return (
              <div
                key={ri}
                className="flex items-center justify-between border-b border-border/30 hover:bg-muted/30"
              >
                <div className="py-1.5 text-sm pl-14">
                  {row.label}
                </div>
                <div className="flex shrink-0">
                  <div className={`w-44 text-right px-4 py-1.5 font-mono tabular-nums text-sm ${
                    isSubtotal ? '' : row.lei < 0 ? 'text-destructive' : ''
                  }`}>
                    {fmtNum(row.lei)}
                  </div>
                  <div className={`w-44 text-right px-4 py-1.5 font-mono tabular-nums text-sm ${
                    isSubtotal ? '' : row.eur < 0 ? 'text-destructive' : ''
                  }`}>
                    {fmtNum(row.eur)}
                  </div>
                </div>
              </div>
            )
          })}
        </Fragment>
      ))}
    </div>
  )
}


function VerificationTable({ accounts, totalEntries }: { accounts: BabAccountGroup[]; totalEntries: number; allPeriods?: BabPeriod[] }) {
  const [expandedAccounts, setExpandedAccounts] = useState<Set<number>>(new Set())
  const [kstFilter, setKstFilter] = useState<string>('')

  // Get unique KST values from all accounts
  const allKst = useMemo(() => {
    const kstSet = new Set<number>()
    accounts.forEach(a => a.lines.forEach(l => kstSet.add(l.kostenstelle)))
    return Array.from(kstSet).sort((a, b) => a - b)
  }, [accounts])

  // Filter accounts by selected KST
  const filteredAccounts = useMemo(() => {
    if (!kstFilter) return accounts
    const kst = Number(kstFilter)
    return accounts
      .map(a => ({
        ...a,
        lines: a.lines.filter(l => l.kostenstelle === kst),
        total: a.lines.filter(l => l.kostenstelle === kst).reduce((sum, l) => sum + l.saldo1, 0),
      }))
      .filter(a => a.lines.length > 0)
  }, [accounts, kstFilter])

  const toggleAccount = (konto: number) => {
    setExpandedAccounts(prev => {
      const next = new Set(prev)
      next.has(konto) ? next.delete(konto) : next.add(konto)
      return next
    })
  }

  return (
    <>
      {/* KST filter */}
      <div className="flex items-center gap-3 mb-3">
        <Label className="text-sm shrink-0">Centru de cost (KST):</Label>
        <Select value={kstFilter || 'all'} onValueChange={(v) => setKstFilter(v === 'all' ? '' : v)}>
          <SelectTrigger className="w-48">
            <SelectValue placeholder="Toate" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Toate</SelectItem>
            {allKst.map(k => (
              <SelectItem key={k} value={String(k)}>{k}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        {kstFilter && (
          <Button variant="ghost" size="sm" className="text-xs" onClick={() => setKstFilter('')}>Resetează</Button>
        )}
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8"></TableHead>
            <TableHead className="w-24">Cont</TableHead>
            <TableHead>Denumire</TableHead>
            <TableHead className="text-center">Linii</TableHead>
            <TableHead className="text-right">Total (LEI)</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {filteredAccounts.map((acct) => {
            const isExpanded = expandedAccounts.has(acct.konto)
            return (
              <Fragment key={acct.konto}>
                <TableRow className="cursor-pointer" onClick={() => toggleAccount(acct.konto)}>
                  <TableCell className="w-8">
                    {isExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                  </TableCell>
                  <TableCell className="font-mono text-xs font-medium">{acct.konto}</TableCell>
                  <TableCell className="text-xs">{acct.konto_bez || '—'}</TableCell>
                  <TableCell className="text-center text-xs text-muted-foreground">{acct.lines.length}</TableCell>
                  <TableCell className={`text-right font-mono tabular-nums text-xs ${acct.total < 0 ? 'text-destructive' : ''}`}>
                    {fmtNum(acct.total)}
                  </TableCell>
                </TableRow>
                {isExpanded && (
                  <TableRow>
                    <TableCell colSpan={5} className="p-0">
                      <div className="bg-muted/30 border-l-2 border-l-primary/30">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="border-b">
                              <th className="text-left px-8 py-1 text-muted-foreground font-medium">KST</th>
                              <th className="text-left px-2 py-1 text-muted-foreground font-medium">Centru cost</th>
                              <th className="text-right px-4 py-1 text-muted-foreground font-medium">Saldo (LEI)</th>
                            </tr>
                          </thead>
                          <tbody>
                            {acct.lines.map((line, i) => (
                              <tr key={i} className="border-b border-border/50">
                                <td className="px-8 py-1 font-mono">{line.kostenstelle}</td>
                                <td className="px-2 py-1">{line.kst_bez1 || '—'}</td>
                                <td className={`text-right px-4 py-1 font-mono tabular-nums ${line.saldo1 < 0 ? 'text-destructive' : ''}`}>
                                  {fmtNum(line.saldo1)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            )
          })}
        </TableBody>
      </Table>
      <div className="border-t px-4 py-2 text-xs text-muted-foreground">
        {filteredAccounts.length} conturi{kstFilter ? ` (KST ${kstFilter})` : ''} &middot; {totalEntries} linii importate total
      </div>
    </>
  )
}


/* ═══════════════════════════════════════
   Config Table — editable report setup
   ═══════════════════════════════════════ */

function ConfigTable({ companyId, setCompanyId, companies, configRows, queryClient }: { companyId: number; setCompanyId: (id: number) => void; companies: { id: number; company: string }[]; configRows: BabConfigRow[]; queryClient: ReturnType<typeof useQueryClient> }) {
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editRow, setEditRow] = useState<Partial<BabConfigRow>>({})
  const [addingSum, setAddingSum] = useState(false)
  const [addingTotal, setAddingTotal] = useState(false)
  const [newSumRow, setNewSumRow] = useState<Partial<BabConfigRow>>({ kst: 0, row_type: 'sum', sort_order: 0, konto_list: '', group_name: '', item_label: '' })
  const [newTotalRow, setNewTotalRow] = useState<Partial<BabConfigRow>>({ kst: 0, row_type: 'subtotal', sort_order: 0, group_name: '', item_label: '', subtotal_of: '', is_main_total: false })

  const sorted = useMemo(() => [...configRows].sort((a, b) => a.sort_order - b.sort_order), [configRows])
  const sumRows = useMemo(() => sorted.filter(r => r.row_type === 'sum'), [sorted])
  const totalRows = useMemo(() => sorted.filter(r => r.row_type === 'subtotal'), [sorted])

  // Available indicators for subtotal picker (only sum rows), qualified with group
  const availableIndicators = useMemo(() => {
    return sumRows.map(r => ({
      label: r.item_label,
      group: r.group_name,
      qualified: `${r.group_name} → ${r.item_label}`,
    }))
  }, [sumRows])

  const invalidateAll = () => { queryClient.invalidateQueries({ queryKey: ['bab-config'] }); queryClient.invalidateQueries({ queryKey: ['bab-all-reports'] }); queryClient.invalidateQueries({ queryKey: ['bab-periods'] }) }

  const addMutation = useMutation({
    mutationFn: (row: Partial<BabConfigRow>) => controllingApi.addConfigRow({ ...row, company_id: companyId }),
    onSuccess: (_d, vars) => { invalidateAll(); if (vars.row_type === 'subtotal') { setAddingTotal(false); setNewTotalRow({ kst: 0, row_type: 'subtotal', sort_order: 0, group_name: '', item_label: '', subtotal_of: '', is_main_total: false }) } else { setAddingSum(false); setNewSumRow({ kst: 0, row_type: 'sum', sort_order: 0, konto_list: '', group_name: '', item_label: '' }) }; toast.success('Rând adăugat') },
    onError: (e: Error) => toast.error(e.message),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, row }: { id: number; row: Partial<BabConfigRow> }) => controllingApi.updateConfigRow(id, row),
    onSuccess: () => { invalidateAll(); setEditingId(null); toast.success('Rând actualizat') },
    onError: (e: Error) => toast.error(e.message),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => controllingApi.deleteConfigRow(id),
    onSuccess: () => { invalidateAll(); toast.success('Rând șters') },
    onError: (e: Error) => toast.error(e.message),
  })

  const startEdit = (row: BabConfigRow) => { setEditingId(row.id!); setEditRow({ ...row }) }

  const toggleSubtotalOf = (prev: string | null | undefined, qualified: string) => {
    const set = new Set((prev || '').split(',').map(s => s.trim()).filter(Boolean))
    set.has(qualified) ? set.delete(qualified) : set.add(qualified)
    return Array.from(set).join(',')
  }

  return (
    <>
      <div className="flex items-center gap-3 mb-6">
        <Label className="text-sm shrink-0 font-medium">Companie:</Label>
        <Select value={String(companyId)} onValueChange={(v) => setCompanyId(Number(v))}>
          <SelectTrigger className="w-72">
            <SelectValue placeholder="Selectează compania" />
          </SelectTrigger>
          <SelectContent>
            {companies.map((c) => (
              <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* ── Table 1: Indicatori (sum rows) ── */}
      <div className="flex items-center justify-between mb-2">
        <div>
          <h3 className="text-sm font-semibold">Indicatori</h3>
          <p className="text-xs text-muted-foreground">Conturi și grupuri pentru raportul de marjă</p>
        </div>
        <Button size="sm" variant="outline" onClick={() => setAddingSum(true)} disabled={addingSum}>
          <Plus className="h-3.5 w-3.5 mr-1" /> Adaugă indicator
        </Button>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-14">Poziție</TableHead>
            <TableHead className="w-16">KST</TableHead>
            <TableHead>Grup</TableHead>
            <TableHead>Indicator</TableHead>
            <TableHead>Conturi</TableHead>
            <TableHead className="w-20">Acțiuni</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {addingSum && (
            <TableRow className="bg-green-50/50">
              <TableCell><Input type="number" className="h-7 w-20 text-xs" value={newSumRow.sort_order} onChange={e => setNewSumRow(prev => ({ ...prev, sort_order: Number(e.target.value) }))} /></TableCell>
              <TableCell><Input type="number" className="h-7 w-20 text-xs" value={newSumRow.kst} onChange={e => setNewSumRow(prev => ({ ...prev, kst: Number(e.target.value) }))} /></TableCell>
              <TableCell><Input className="h-7 text-xs" placeholder="Grup" value={newSumRow.group_name} onChange={e => setNewSumRow(prev => ({ ...prev, group_name: e.target.value }))} /></TableCell>
              <TableCell><Input className="h-7 text-xs" placeholder="Indicator" value={newSumRow.item_label} onChange={e => setNewSumRow(prev => ({ ...prev, item_label: e.target.value }))} /></TableCell>
              <TableCell><Input className="h-7 text-xs font-mono" placeholder="707111,707116" value={newSumRow.konto_list} onChange={e => setNewSumRow(prev => ({ ...prev, konto_list: e.target.value }))} /></TableCell>
              <TableCell>
                <div className="flex gap-1">
                  <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => addMutation.mutate(newSumRow)}><Save className="h-3 w-3" /></Button>
                  <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setAddingSum(false)}><X className="h-3 w-3" /></Button>
                </div>
              </TableCell>
            </TableRow>
          )}
          {sumRows.map((row) => {
            const isEditing = editingId === row.id
            return (
              <TableRow key={row.id}>
                {isEditing ? (
                  <>
                    <TableCell><Input type="number" className="h-7 w-20 text-xs" value={editRow.sort_order} onChange={e => setEditRow(prev => ({ ...prev, sort_order: Number(e.target.value) }))} /></TableCell>
                    <TableCell><Input type="number" className="h-7 w-20 text-xs" value={editRow.kst} onChange={e => setEditRow(prev => ({ ...prev, kst: Number(e.target.value) }))} /></TableCell>
                    <TableCell><Input className="h-7 text-xs" value={editRow.group_name} onChange={e => setEditRow(prev => ({ ...prev, group_name: e.target.value }))} /></TableCell>
                    <TableCell><Input className="h-7 text-xs" value={editRow.item_label} onChange={e => setEditRow(prev => ({ ...prev, item_label: e.target.value }))} /></TableCell>
                    <TableCell><Input className="h-7 text-xs font-mono" value={editRow.konto_list} onChange={e => setEditRow(prev => ({ ...prev, konto_list: e.target.value }))} /></TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => updateMutation.mutate({ id: row.id!, row: editRow })}><Save className="h-3 w-3" /></Button>
                        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setEditingId(null)}><X className="h-3 w-3" /></Button>
                      </div>
                    </TableCell>
                  </>
                ) : (
                  <>
                    <TableCell className="text-xs text-muted-foreground">{row.sort_order}</TableCell>
                    <TableCell className="font-mono text-xs">{row.kst}</TableCell>
                    <TableCell className="text-xs">{row.group_name}</TableCell>
                    <TableCell className="text-xs">{row.item_label}</TableCell>
                    <TableCell className="text-xs font-mono text-muted-foreground">{row.konto_list || '—'}</TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => startEdit(row)}><Pencil className="h-3 w-3" /></Button>
                        <Button variant="ghost" size="icon" className="h-6 w-6 text-destructive" onClick={() => row.id && deleteMutation.mutate(row.id)}><Trash2 className="h-3 w-3" /></Button>
                      </div>
                    </TableCell>
                  </>
                )}
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
      <div className="border-t px-4 py-2 text-xs text-muted-foreground mb-6">
        {sumRows.length} indicatori configurați
      </div>

      {/* ── Table 2: Totaluri (subtotal rows) ── */}
      <div className="flex items-center justify-between mb-2">
        <div>
          <h3 className="text-sm font-semibold">Totaluri</h3>
          <p className="text-xs text-muted-foreground">Subtotaluri și totaluri — selectează indicatorii de sumat. Poziția determină locul în raport.</p>
        </div>
        <Button size="sm" variant="outline" onClick={() => setAddingTotal(true)} disabled={addingTotal || sumRows.length === 0}>
          <Plus className="h-3.5 w-3.5 mr-1" /> Adaugă total
        </Button>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-14">Poziție</TableHead>
            <TableHead className="w-16">KST</TableHead>
            <TableHead>Grup</TableHead>
            <TableHead>Denumire total</TableHead>
            <TableHead>Indicatori incluși</TableHead>
            <TableHead className="w-24">Acțiuni</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {addingTotal && (
            <TableRow className="bg-green-50/50">
              <TableCell><Input type="number" className="h-7 w-20 text-xs" value={newTotalRow.sort_order} onChange={e => setNewTotalRow(prev => ({ ...prev, sort_order: Number(e.target.value) }))} /></TableCell>
              <TableCell><Input type="number" className="h-7 w-20 text-xs" value={newTotalRow.kst} onChange={e => setNewTotalRow(prev => ({ ...prev, kst: Number(e.target.value) }))} /></TableCell>
              <TableCell><Input className="h-7 text-xs" placeholder="Grup" value={newTotalRow.group_name} onChange={e => setNewTotalRow(prev => ({ ...prev, group_name: e.target.value }))} /></TableCell>
              <TableCell>
                <div className="space-y-1">
                  <Input className="h-7 text-xs" placeholder="Denumire total" value={newTotalRow.item_label} onChange={e => setNewTotalRow(prev => ({ ...prev, item_label: e.target.value }))} />
                  <label className="flex items-center gap-1.5 cursor-pointer text-[11px] text-muted-foreground">
                    <input type="checkbox" className="rounded" checked={!!newTotalRow.is_main_total} onChange={e => setNewTotalRow(prev => ({ ...prev, is_main_total: e.target.checked }))} />
                    <Star className="h-3 w-3 text-amber-400" /> Total principal
                  </label>
                </div>
              </TableCell>
              <TableCell>
                <SubtotalPicker
                  indicators={availableIndicators}
                  selected={newTotalRow.subtotal_of || ''}
                  onToggle={qualified => setNewTotalRow(prev => ({ ...prev, subtotal_of: toggleSubtotalOf(prev.subtotal_of, qualified) }))}
                />
              </TableCell>
              <TableCell>
                <div className="flex gap-1">
                  <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => addMutation.mutate(newTotalRow)}><Save className="h-3 w-3" /></Button>
                  <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setAddingTotal(false)}><X className="h-3 w-3" /></Button>
                </div>
              </TableCell>
            </TableRow>
          )}
          {totalRows.map((row) => {
            const isEditing = editingId === row.id
            return (
              <TableRow key={row.id} className="bg-primary/5">
                {isEditing ? (
                  <>
                    <TableCell><Input type="number" className="h-7 w-20 text-xs" value={editRow.sort_order} onChange={e => setEditRow(prev => ({ ...prev, sort_order: Number(e.target.value) }))} /></TableCell>
                    <TableCell><Input type="number" className="h-7 w-20 text-xs" value={editRow.kst} onChange={e => setEditRow(prev => ({ ...prev, kst: Number(e.target.value) }))} /></TableCell>
                    <TableCell><Input className="h-7 text-xs" value={editRow.group_name} onChange={e => setEditRow(prev => ({ ...prev, group_name: e.target.value }))} /></TableCell>
                    <TableCell>
                      <div className="space-y-1">
                        <Input className="h-7 text-xs" value={editRow.item_label} onChange={e => setEditRow(prev => ({ ...prev, item_label: e.target.value }))} />
                        <label className="flex items-center gap-1.5 cursor-pointer text-[11px] text-muted-foreground">
                          <input type="checkbox" className="rounded" checked={!!editRow.is_main_total} onChange={e => setEditRow(prev => ({ ...prev, is_main_total: e.target.checked }))} />
                          <Star className="h-3 w-3 text-amber-400" /> Total principal
                        </label>
                      </div>
                    </TableCell>
                    <TableCell>
                      <SubtotalPicker
                        indicators={availableIndicators}
                        selected={editRow.subtotal_of || ''}
                        onToggle={qualified => setEditRow(prev => ({ ...prev, subtotal_of: toggleSubtotalOf(prev.subtotal_of, qualified) }))}
                      />
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => updateMutation.mutate({ id: row.id!, row: editRow })}><Save className="h-3 w-3" /></Button>
                        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setEditingId(null)}><X className="h-3 w-3" /></Button>
                      </div>
                    </TableCell>
                  </>
                ) : (
                  <>
                    <TableCell className="text-xs text-muted-foreground">{row.sort_order}</TableCell>
                    <TableCell className="font-mono text-xs">{row.kst}</TableCell>
                    <TableCell className="text-xs font-semibold">{row.group_name}</TableCell>
                    <TableCell className="text-xs">
                      <span className="inline-flex items-center gap-1 font-semibold">
                        {row.item_label}
                        {row.is_main_total && <Star className="h-3 w-3 fill-amber-400 text-amber-400" />}
                      </span>
                    </TableCell>
                    <TableCell className="text-xs">
                      {row.subtotal_of ? (
                        <div className="flex flex-wrap gap-1">
                          {row.subtotal_of.split(',').filter(Boolean).map((ref, i) => {
                            const short = ref.includes('→') ? ref.split('→').pop()!.trim() : ref.trim()
                            return <span key={i} className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-[11px] text-primary font-medium" title={ref.trim()}>{short}</span>
                          })}
                        </div>
                      ) : '—'}
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => startEdit(row)}><Pencil className="h-3 w-3" /></Button>
                        <Button variant="ghost" size="icon" className="h-6 w-6 text-destructive" onClick={() => row.id && deleteMutation.mutate(row.id)}><Trash2 className="h-3 w-3" /></Button>
                      </div>
                    </TableCell>
                  </>
                )}
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
      <div className="border-t px-4 py-2 text-xs text-muted-foreground">
        {totalRows.length} totaluri configurate
      </div>
    </>
  )
}


/* ═══════════════════════════════════
   SubtotalPicker — select indicators
   ═══════════════════════════════════ */

function SubtotalPicker({ indicators, selected, onToggle }: {
  indicators: { label: string; group: string; qualified: string }[]
  selected: string
  onToggle: (qualified: string) => void
}) {
  const selectedSet = new Set(selected.split(',').map(s => s.trim()).filter(Boolean))
  const selectedCount = selectedSet.size

  // Group indicators by group_name
  const grouped = useMemo(() => {
    const map = new Map<string, { label: string; qualified: string }[]>()
    for (const ind of indicators) {
      if (!map.has(ind.group)) map.set(ind.group, [])
      map.get(ind.group)!.push({ label: ind.label, qualified: ind.qualified })
    }
    return map
  }, [indicators])

  const toggleGroup = (items: { qualified: string }[]) => {
    const allSelected = items.every(i => selectedSet.has(i.qualified))
    for (const item of items) {
      if (allSelected) { if (selectedSet.has(item.qualified)) onToggle(item.qualified) }
      else { if (!selectedSet.has(item.qualified)) onToggle(item.qualified) }
    }
  }

  if (indicators.length === 0) return <span className="text-xs text-muted-foreground">Adaugă mai întâi rânduri de tip Sum</span>

  return (
    <div className="space-y-2">
      {/* Selected summary */}
      {selectedCount > 0 && (
        <div className="text-[11px] text-primary font-medium">{selectedCount} indicator{selectedCount !== 1 ? 'i' : ''} selecta{selectedCount !== 1 ? 'ți' : 't'}</div>
      )}

      {/* Grouped chips */}
      <div className="space-y-2">
        {[...grouped.entries()].map(([group, items]) => {
          const groupAllSelected = items.every(i => selectedSet.has(i.qualified))
          return (
            <div key={group} className="space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">{group}</span>
                <button
                  type="button"
                  onPointerDown={e => e.stopPropagation()}
                  onClick={e => { e.stopPropagation(); toggleGroup(items) }}
                  className={`text-[10px] px-1.5 py-0.5 rounded cursor-pointer transition-colors ${
                    groupAllSelected ? 'text-primary font-medium hover:text-primary/80' : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {groupAllSelected ? 'Deselectează tot' : 'Selectează tot'}
                </button>
              </div>
              <div className="flex flex-wrap gap-1">
                {items.map(item => {
                  const isSelected = selectedSet.has(item.qualified)
                  return (
                    <button
                      key={item.qualified}
                      type="button"
                      onPointerDown={e => e.stopPropagation()}
                      onClick={e => { e.stopPropagation(); onToggle(item.qualified) }}
                      className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-medium transition-all cursor-pointer ${
                        isSelected
                          ? 'border-primary bg-primary/10 text-primary'
                          : 'border-border bg-background text-muted-foreground hover:border-primary/40 hover:text-foreground'
                      }`}
                    >
                      {isSelected && <Check className="h-3 w-3" />}
                      {item.label}
                    </button>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>

    </div>
  )
}
