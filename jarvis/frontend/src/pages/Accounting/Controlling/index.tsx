import { useState, useCallback, useMemo, Fragment, Suspense } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload, Lock, Unlock, FileSpreadsheet, AlertTriangle, ChevronRight, ChevronDown, Plus, Trash2, Pencil, Save, X, Star, Check, Download } from 'lucide-react'
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
// MONTH_NAMES_LONG removed — cross-tab uses MONTH_NAMES (short)

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
  const [showEur, setShowEur] = useState(true)
  // expandedRows removed — Marja tab now uses cross-tab view

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
          <Button variant="outline" size="sm" disabled={importedPeriods.length === 0} onClick={async () => {
            const mp = importedPeriods.filter(p => p.upload_id && reports[p.upload_id!])
            if (mp.length === 0) return
            const allSections: { section: string; rows: { label: string }[] }[] = []
            const seenKeys = new Set<string>()
            for (const p of mp) { const r = reports[p.upload_id!]; if (!r) continue; for (const sec of r.sections) { for (const row of sec.rows) { const key = `${sec.section}|${row.label}`; if (!seenKeys.has(key)) { seenKeys.add(key); let s = allSections.find(x => x.section === sec.section); if (!s) { s = { section: sec.section, rows: [] }; allSections.push(s) }; s.rows.push({ label: row.label }) } } } }
            const gv = (uid: number, sn: string, lb: string) => { const r = reports[uid]; if (!r) return null; for (const s of r.sections) { if (s.section === sn) { for (const row of s.rows) { if (row.label === lb) return { lei: row.lei, eur: row.eur } } } }; return null }
            const XLSX = await import('xlsx')
            const header = ['Indicator', ...mp.map(p => `${MONTH_NAMES[p.month]} ${p.year}`)]
            const eurRows: (string | number)[][] = [header]; const leiRows: (string | number)[][] = [header]
            for (const sec of allSections) { eurRows.push([sec.section]); leiRows.push([sec.section]); for (const row of sec.rows) { eurRows.push([`  ${row.label}`, ...mp.map(p => { const v = gv(p.upload_id!, sec.section, row.label); return v ? v.eur : 0 })]); leiRows.push([`  ${row.label}`, ...mp.map(p => { const v = gv(p.upload_id!, sec.section, row.label); return v ? v.lei : 0 })]) } }
            const wb = XLSX.utils.book_new()
            const wsEur = XLSX.utils.aoa_to_sheet(eurRows); const wsLei = XLSX.utils.aoa_to_sheet(leiRows)
            wsEur['!cols'] = [{ wch: 40 }, ...mp.map(() => ({ wch: 18 }))]; wsLei['!cols'] = [{ wch: 40 }, ...mp.map(() => ({ wch: 18 }))]
            XLSX.utils.book_append_sheet(wb, wsEur, 'Marjă EUR'); XLSX.utils.book_append_sheet(wb, wsLei, 'Marjă LEI')
            const company = companies.find(c => c.id === companyId)
            XLSX.writeFile(wb, `Marja_${company?.company || companyId}_${new Date().toISOString().slice(0,10)}.xlsx`)
            toast.success('Export XLSX descărcat')
          }}>
            <Download className="h-3.5 w-3.5 mr-1.5" /> Export XLSX
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
          <TabsTrigger value="analiza">Analiză AI</TabsTrigger>
        </TabsList>

        {/* ═══ TAB: Marjă ═══ */}
        <TabsContent value="marja" className="mt-4">
          {periodsLoading ? (
            <div className="text-center py-12 text-muted-foreground">Se încarcă...</div>
          ) : importedPeriods.length === 0 ? (
            <Card><CardContent className="py-12 text-center text-muted-foreground text-sm">Nicio perioadă importată. Folosește butonul "Import perioadă" pentru a începe.</CardContent></Card>
          ) : (() => {
            // Build cross-tab: rows = indicators, columns = months
            const monthPeriods = importedPeriods.filter(p => p.upload_id && reports[p.upload_id!])
            // Collect all unique rows across all reports (preserving order from first report)
            const allRowKeys: { section: string; label: string; row_type: string }[] = []
            const seenKeys = new Set<string>()
            for (const p of monthPeriods) {
              const r = reports[p.upload_id!]
              if (!r) continue
              for (const sec of r.sections) {
                for (const row of sec.rows) {
                  const key = `${sec.section}|${row.label}`
                  if (!seenKeys.has(key)) { seenKeys.add(key); allRowKeys.push({ section: sec.section, label: row.label, row_type: row.row_type || 'sum' }) }
                }
              }
            }
            // Group rows by section
            const sections: { section: string; rows: { label: string; row_type: string }[] }[] = []
            let currentSection = ''
            for (const rk of allRowKeys) {
              if (rk.section !== currentSection) { currentSection = rk.section; sections.push({ section: rk.section, rows: [] }) }
              sections[sections.length - 1].rows.push({ label: rk.label, row_type: rk.row_type })
            }
            // Helper to look up a value
            const getValue = (uploadId: number, sectionName: string, label: string): { lei: number; eur: number } | null => {
              const r = reports[uploadId]
              if (!r) return null
              for (const sec of r.sections) {
                if (sec.section === sectionName) {
                  for (const row of sec.rows) { if (row.label === label) return { lei: row.lei, eur: row.eur } }
                }
              }
              return null
            }
            return (
              <>
              {monthPeriods.length > 1 && <MarjaChart sections={sections} monthPeriods={monthPeriods} getValue={getValue} />}
              <div className="border rounded-lg overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b bg-muted/50">
                        <th className="text-left px-4 py-2.5 font-semibold text-xs min-w-[250px] sticky left-0 bg-muted/50 z-10">Indicator</th>
                        {monthPeriods.map(p => (
                          <th key={p.upload_id} className="text-right px-3 py-2.5 font-semibold text-xs min-w-[130px]">
                            <div className="flex items-center justify-end gap-1">
                              <div className="text-right">
                                <div>{MONTH_NAMES[p.month]}</div>
                                <div className="text-[10px] text-muted-foreground font-normal">{p.year}</div>
                                {reports[p.upload_id!]?.eur_rate && (
                                  <div className="text-[9px] text-muted-foreground font-normal">1 EUR = {reports[p.upload_id!].eur_rate} LEI</div>
                                )}
                              </div>
                              <div className="flex gap-0.5" onClick={e => e.stopPropagation()}>
                                {p.status === 'IMPORTED' && (
                                  <Button variant="ghost" size="icon" className="h-5 w-5" onClick={() => setLockConfirm(p)} title="Blochează"><Lock className="h-2.5 w-2.5" /></Button>
                                )}
                                {p.status === 'LOCKED' && (
                                  <Button variant="ghost" size="icon" className="h-5 w-5" onClick={() => p.upload_id && unlockMutation.mutate(p.upload_id)} title="Deblochează"><Unlock className="h-2.5 w-2.5" /></Button>
                                )}
                              </div>
                            </div>
                          </th>
                        ))}
                        {monthPeriods.length > 1 && <th className="text-right px-3 py-2.5 font-semibold text-xs min-w-[130px] bg-muted/80">TOTAL</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {sections.map(sec => (
                        <Fragment key={sec.section}>
                          <tr className="bg-muted/30">
                            <td colSpan={monthPeriods.length + (monthPeriods.length > 1 ? 2 : 1)} className="px-4 py-1.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">{sec.section}</td>
                          </tr>
                          {sec.rows.map(row => {
                            const isSubtotal = row.row_type === 'subtotal'
                            return (
                              <tr key={`${sec.section}|${row.label}`} className={`border-b border-border/30 ${isSubtotal ? 'bg-primary/5 font-semibold' : 'hover:bg-muted/20'}`}>
                                <td className={`px-4 py-1.5 sticky left-0 z-10 ${isSubtotal ? 'bg-primary/5 font-bold text-sm' : 'pl-8 bg-background'}`}>{row.label}</td>
                                {monthPeriods.map(p => {
                                  const val = getValue(p.upload_id!, sec.section, row.label)
                                  if (!val) return <td key={p.upload_id} className="text-right px-3 py-1.5 text-muted-foreground">—</td>
                                  return (
                                    <td key={p.upload_id} className="text-right px-3 py-1.5">
                                      <div className={`font-mono tabular-nums text-sm ${(showEur ? val.eur : val.lei) < 0 ? 'text-destructive' : ''}`}>{fmtNum(showEur ? val.eur : val.lei)} <span className="text-[9px] font-normal text-muted-foreground">{showEur ? 'EUR' : 'LEI'}</span></div>
                                      <div className={`font-mono tabular-nums text-[10px] text-muted-foreground ${(showEur ? val.lei : val.eur) < 0 ? 'text-destructive' : ''}`}>{fmtNum(showEur ? val.lei : val.eur)} <span className="text-[8px]">{showEur ? 'LEI' : 'EUR'}</span></div>
                                    </td>
                                  )
                                })}
                                {monthPeriods.length > 1 && (() => {
                                  let totalEur = 0, totalLei = 0
                                  for (const p of monthPeriods) { const v = getValue(p.upload_id!, sec.section, row.label); if (v) { totalEur += v.eur; totalLei += v.lei } }
                                  return (
                                    <td className="text-right px-3 py-1.5 bg-muted/30 border-l">
                                      <div className={`font-mono tabular-nums text-sm ${(showEur ? totalEur : totalLei) < 0 ? 'text-destructive' : ''}`}>{fmtNum(showEur ? totalEur : totalLei)} <span className="text-[9px] font-normal text-muted-foreground">{showEur ? 'EUR' : 'LEI'}</span></div>
                                      <div className={`font-mono tabular-nums text-[10px] text-muted-foreground ${(showEur ? totalLei : totalEur) < 0 ? 'text-destructive' : ''}`}>{fmtNum(showEur ? totalLei : totalEur)} <span className="text-[8px]">{showEur ? 'LEI' : 'EUR'}</span></div>
                                    </td>
                                  )
                                })()}
                              </tr>
                            )
                          })}
                        </Fragment>
                      ))}
                    </tbody>
                  </table>
                  <div className="border-t px-4 py-2 text-xs text-muted-foreground">
                    {monthPeriods.length} perioad{monthPeriods.length !== 1 ? 'e' : 'ă'} &middot; Valori: EUR / LEI
                  </div>
              </div>

              </>
            )
          })()}
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

        {/* ═══ TAB: Analiză AI ═══ */}
        <TabsContent value="analiza" className="mt-4">
          <AnalysisTab companyId={companyId} />
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
   Analysis Tab — AI-powered insights
   ═══════════════════════════════════════ */

function AnalysisTab({ companyId }: { companyId: number }) {
  const [autoAnalysis, setAutoAnalysis] = useState<string | null>(null)
  const [autoLoading, setAutoLoading] = useState(false)
  const [queryHistory, setQueryHistory] = useState<{ prompt: string; response: string }[]>([])
  const [queryInput, setQueryInput] = useState('')
  const [queryLoading, setQueryLoading] = useState(false)
  const [crossCompany, setCrossCompany] = useState(false)

  const runAutoAnalysis = async () => {
    setAutoLoading(true)
    try {
      const res = await controllingApi.analyze(companyId, 'auto', undefined, crossCompany)
      setAutoAnalysis(res.analysis)
    } catch (e: unknown) {
      setAutoAnalysis(`Eroare: ${e instanceof Error ? e.message : 'necunoscută'}`)
    } finally {
      setAutoLoading(false)
    }
  }

  const runQuery = async () => {
    if (!queryInput.trim()) return
    const prompt = queryInput.trim()
    setQueryInput('')
    setQueryLoading(true)
    try {
      const res = await controllingApi.analyze(companyId, 'query', prompt, crossCompany)
      setQueryHistory(prev => [...prev, { prompt, response: res.analysis }])
    } catch (e: unknown) {
      setQueryHistory(prev => [...prev, { prompt, response: `Eroare: ${e instanceof Error ? e.message : 'necunoscută'}` }])
    } finally {
      setQueryLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Auto-analysis section */}
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-lg font-semibold">Analiză Financiară AI</h3>
              <p className="text-sm text-muted-foreground">Analiză de tip Big 4 — profitabilitate, variații, riscuri și oportunități</p>
            </div>
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
                <input type="checkbox" className="rounded" checked={crossCompany} onChange={e => setCrossCompany(e.target.checked)} />
                Include toate companiile
              </label>
              <Button onClick={runAutoAnalysis} disabled={autoLoading}>
                {autoLoading ? (
                  <><span className="animate-spin mr-2">⏳</span> Se generează...</>
                ) : (
                  <><FileSpreadsheet className="h-4 w-4 mr-2" /> Generează analiză</>
                )}
              </Button>
            </div>
          </div>

          {autoAnalysis ? (
            <div className="prose prose-sm max-w-none dark:prose-invert">
              <MarkdownRenderer content={autoAnalysis} />
            </div>
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              <FileSpreadsheet className="h-10 w-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm">Apasă butonul pentru a genera analiza financiară AI</p>
              <p className="text-xs mt-1">Analiza acoperă: profitabilitate, variații lunare, structura costurilor, riscuri și oportunități</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Query section */}
      <Card>
        <CardContent className="p-6">
          <h3 className="text-sm font-semibold mb-3">Întreabă despre date</h3>

          {/* Query history */}
          {queryHistory.length > 0 && (
            <div className="space-y-4 mb-4 max-h-[500px] overflow-y-auto">
              {queryHistory.map((qa, i) => (
                <div key={i} className="space-y-2">
                  <div className="flex justify-end">
                    <div className="bg-primary text-primary-foreground rounded-lg px-3 py-2 text-sm max-w-[80%]">{qa.prompt}</div>
                  </div>
                  <div className="bg-muted rounded-lg px-4 py-3 prose prose-sm max-w-none dark:prose-invert">
                    <MarkdownRenderer content={qa.response} />
                  </div>
                </div>
              ))}
            </div>
          )}

          {queryLoading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground mb-3">
              <span className="animate-spin">⏳</span> Se generează răspunsul...
            </div>
          )}

          <div className="flex gap-2">
            <Input
              placeholder="ex: De ce a scăzut marja în aprilie? Care segment are cea mai bună evoluție?"
              value={queryInput}
              onChange={e => setQueryInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !queryLoading && runQuery()}
              className="flex-1"
            />
            <Button onClick={runQuery} disabled={queryLoading || !queryInput.trim()}>
              Trimite
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function MarkdownRenderer({ content }: { content: string }) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [Md, setMd] = useState<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [gfm, setGfm] = useState<any>(null)

  useMemo(() => {
    import('react-markdown').then(m => setMd(() => m.default))
    import('remark-gfm').then(m => setGfm(() => m.default))
  }, [])

  if (!Md) return <div className="whitespace-pre-wrap text-sm">{content}</div>
  return <Md remarkPlugins={gfm ? [gfm] : []}>{content}</Md>
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
  const [newTotalRow, setNewTotalRow] = useState<Partial<BabConfigRow>>({ kst: 0, row_type: 'subtotal', sort_order: 0, group_name: '', item_label: '', indicator_ids: [], is_main_total: false })

  const sorted = useMemo(() => [...configRows].sort((a, b) => a.sort_order - b.sort_order), [configRows])
  const sumRows = useMemo(() => sorted.filter(r => r.row_type === 'sum'), [sorted])
  const totalRows = useMemo(() => sorted.filter(r => r.row_type === 'subtotal'), [sorted])

  // Available indicators for subtotal picker (only sum rows), keyed by id
  const availableIndicators = useMemo(() => {
    return sumRows.map(r => ({
      id: r.id!,
      label: r.item_label,
      group: r.group_name,
    }))
  }, [sumRows])

  const invalidateAll = () => { queryClient.invalidateQueries({ queryKey: ['bab-config'] }); queryClient.invalidateQueries({ queryKey: ['bab-all-reports'] }); queryClient.invalidateQueries({ queryKey: ['bab-periods'] }) }

  const addMutation = useMutation({
    mutationFn: (row: Partial<BabConfigRow>) => controllingApi.addConfigRow({ ...row, company_id: companyId }),
    onSuccess: (_d, vars) => { invalidateAll(); if (vars.row_type === 'subtotal') { setAddingTotal(false); setNewTotalRow({ kst: 0, row_type: 'subtotal', sort_order: 0, group_name: '', item_label: '', indicator_ids: [], is_main_total: false }) } else { setAddingSum(false); setNewSumRow({ kst: 0, row_type: 'sum', sort_order: 0, konto_list: '', group_name: '', item_label: '' }) }; toast.success('Rând adăugat') },
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

  const toggleIndicatorId = (prev: number[] | undefined, id: number): number[] => {
    const arr = prev || []
    return arr.includes(id) ? arr.filter(x => x !== id) : [...arr, id]
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

      {/* ── Indicatori (sum rows) — grouped by group_name+kst ── */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-semibold">Indicatori</h3>
          <p className="text-xs text-muted-foreground">Definește grupuri, apoi adaugă indicatori cu conturi contabile</p>
        </div>
        <Button size="sm" variant="outline" onClick={() => { setAddingSum(true); setNewSumRow({ kst: 0, row_type: 'sum', sort_order: 0, konto_list: '', group_name: '', item_label: '' }) }}>
          <Plus className="h-3.5 w-3.5 mr-1" /> Adaugă grup nou
        </Button>
      </div>

      {(() => {
        // Group sum rows by "group_name|kst"
        const groups = new Map<string, { group_name: string; kst: number; rows: BabConfigRow[] }>()
        for (const r of sumRows) {
          const key = `${r.group_name}|${r.kst}`
          if (!groups.has(key)) groups.set(key, { group_name: r.group_name, kst: r.kst, rows: [] })
          groups.get(key)!.rows.push(r)
        }
        const addingToGroup = addingSum && newSumRow.group_name && newSumRow.kst && groups.has(`${newSumRow.group_name}|${newSumRow.kst}`)
        return (
          <div className="space-y-3 mb-6">
            {[...groups.entries()].map(([key, { group_name, kst, rows: groupRows }]) => (
              <div key={key} className="border rounded-lg overflow-hidden">
                <div className="bg-muted/50 px-4 py-2 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-semibold">{group_name}</span>
                    <span className="text-xs font-mono text-muted-foreground bg-background px-1.5 py-0.5 rounded">KST {kst}</span>
                    <span className="text-xs text-muted-foreground">{groupRows.length} indicator{groupRows.length !== 1 ? 'i' : ''}</span>
                  </div>
                  <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => { setAddingSum(true); setNewSumRow({ kst, row_type: 'sum', sort_order: Math.max(0, ...groupRows.map(r => r.sort_order)) + 5, konto_list: '', group_name, item_label: '' }) }}>
                    <Plus className="h-3 w-3 mr-1" /> Indicator
                  </Button>
                </div>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-14">Poz.</TableHead>
                      <TableHead>Indicator</TableHead>
                      <TableHead>Conturi</TableHead>
                      <TableHead className="w-20">Acțiuni</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {groupRows.map(row => {
                      const isEditing = editingId === row.id
                      return (
                        <TableRow key={row.id}>
                          {isEditing ? (
                            <>
                              <TableCell><Input type="number" className="h-7 w-20 text-xs" value={editRow.sort_order} onChange={e => setEditRow(prev => ({ ...prev, sort_order: Number(e.target.value) }))} /></TableCell>
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
                    {addingSum && newSumRow.group_name === group_name && newSumRow.kst === kst && (
                      <TableRow className="bg-green-50/50">
                        <TableCell><Input type="number" className="h-7 w-20 text-xs" value={newSumRow.sort_order} onChange={e => setNewSumRow(prev => ({ ...prev, sort_order: Number(e.target.value) }))} /></TableCell>
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
                  </TableBody>
                </Table>
              </div>
            ))}

            {/* New group form */}
            {addingSum && !addingToGroup && (
              <div className="border rounded-lg border-dashed border-green-300 bg-green-50/30 p-4 space-y-3">
                <div className="text-xs font-semibold text-muted-foreground">Grup nou</div>
                <div className="flex items-center gap-3">
                  <div className="flex-1">
                    <Label className="text-xs text-muted-foreground mb-1">Nume grup</Label>
                    <Input className="h-8 text-xs" placeholder="ex: VW PKW INTERN (retail)" value={newSumRow.group_name} onChange={e => setNewSumRow(prev => ({ ...prev, group_name: e.target.value }))} />
                  </div>
                  <div className="w-24">
                    <Label className="text-xs text-muted-foreground mb-1">KST</Label>
                    <Input type="number" className="h-8 w-24 text-xs" placeholder="211" value={newSumRow.kst || ''} onChange={e => setNewSumRow(prev => ({ ...prev, kst: Number(e.target.value) }))} />
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex-1">
                    <Label className="text-xs text-muted-foreground mb-1">Primul indicator</Label>
                    <Input className="h-8 text-xs" placeholder="ex: Venit Sales realizat" value={newSumRow.item_label} onChange={e => setNewSumRow(prev => ({ ...prev, item_label: e.target.value }))} />
                  </div>
                  <div className="flex-1">
                    <Label className="text-xs text-muted-foreground mb-1">Conturi</Label>
                    <Input className="h-8 text-xs font-mono" placeholder="707111,707116" value={newSumRow.konto_list} onChange={e => setNewSumRow(prev => ({ ...prev, konto_list: e.target.value }))} />
                  </div>
                  <div className="w-20">
                    <Label className="text-xs text-muted-foreground mb-1">Poz.</Label>
                    <Input type="number" className="h-8 w-20 text-xs" value={newSumRow.sort_order} onChange={e => setNewSumRow(prev => ({ ...prev, sort_order: Number(e.target.value) }))} />
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => addMutation.mutate(newSumRow)}><Save className="h-3.5 w-3.5 mr-1" /> Salvează</Button>
                  <Button size="sm" variant="ghost" onClick={() => setAddingSum(false)}>Anulează</Button>
                </div>
              </div>
            )}

            {groups.size === 0 && !addingSum && (
              <div className="text-center py-6 text-sm text-muted-foreground">Niciun indicator configurat. Adaugă un grup nou pentru a începe.</div>
            )}

            <div className="text-xs text-muted-foreground">{sumRows.length} indicatori în {groups.size} grupuri</div>
          </div>
        )
      })()}

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
                  selectedIds={newTotalRow.indicator_ids || []}
                  onToggle={id => setNewTotalRow(prev => ({ ...prev, indicator_ids: toggleIndicatorId(prev.indicator_ids, id) }))}
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
                        selectedIds={editRow.indicator_ids || []}
                        onToggle={id => setEditRow(prev => ({ ...prev, indicator_ids: toggleIndicatorId(prev.indicator_ids, id) }))}
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
                      {(row.indicator_ids && row.indicator_ids.length > 0) ? (
                        <div className="flex flex-wrap gap-1">
                          {row.indicator_ids.map(indicatorId => {
                            const sumRow = sumRows.find(r => r.id === indicatorId)
                            const label = sumRow ? sumRow.item_label : String(indicatorId)
                            const title = sumRow ? `${sumRow.group_name} → ${sumRow.item_label}` : String(indicatorId)
                            return <span key={indicatorId} className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-[11px] text-primary font-medium" title={title}>{label}</span>
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
   MarjaChart — evolution graph
   ═══════════════════════════════════ */

function MarjaChart({ sections, monthPeriods, getValue }: {
  sections: { section: string; rows: { label: string; row_type: string }[] }[]
  monthPeriods: { upload_id?: number; month: number; year: number }[]
  getValue: (uploadId: number, section: string, label: string) => { lei: number; eur: number } | null
}) {
  // Collect all subtotal rows + all indicator rows for the selector
  const allRows: { key: string; label: string; section: string; isSubtotal: boolean }[] = []
  for (const sec of sections) {
    for (const row of sec.rows) {
      allRows.push({ key: `${sec.section}|${row.label}`, label: row.label, section: sec.section, isSubtotal: row.row_type === 'subtotal' })
    }
  }
  const subtotalRows = allRows.filter(r => r.isSubtotal)
  const [selectedKeys, setSelectedKeys] = useState<string[]>(() => subtotalRows.map(r => r.key))

  // Build chart data
  const chartData = monthPeriods.map(p => {
    const point: Record<string, string | number> = { month: `${MONTH_NAMES[p.month]} ${p.year}` }
    for (const key of selectedKeys) {
      const [sec, label] = key.split('|')
      const val = getValue(p.upload_id!, sec, label)
      point[label] = val ? val.eur : 0
    }
    return point
  })

  const COLORS = ['#2563eb', '#dc2626', '#16a34a', '#d97706', '#7c3aed', '#0891b2', '#be185d', '#65a30d']

  return (
    <div className="mt-4 border rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold">Evoluție lunară (EUR)</h3>
        <div className="flex flex-wrap gap-1">
          {allRows.map((row) => {
            const isActive = selectedKeys.includes(row.key)
            return (
              <button
                key={row.key}
                type="button"
                onClick={() => setSelectedKeys(prev => prev.includes(row.key) ? prev.filter(k => k !== row.key) : [...prev, row.key])}
                className={`text-[10px] px-2 py-0.5 rounded-full border cursor-pointer transition-all ${
                  isActive
                    ? 'border-primary bg-primary/10 text-primary font-medium'
                    : 'border-border text-muted-foreground hover:border-primary/40'
                }`}
              >
                {row.label}
              </button>
            )
          })}
        </div>
      </div>
      {selectedKeys.length > 0 && chartData.length > 0 ? (
        <Suspense fallback={<div className="text-center py-8 text-sm text-muted-foreground">Se încarcă graficul...</div>}>
          <MarjaChartInner data={chartData} keys={selectedKeys.map(k => k.split('|')[1])} colors={COLORS} />
        </Suspense>
      ) : (
        <div className="text-center py-8 text-sm text-muted-foreground">Selectează indicatori pentru a vedea graficul</div>
      )}
    </div>
  )
}

const LazyRecharts = (() => {
  let mod: typeof import('recharts') | null = null
  let promise: Promise<typeof import('recharts')> | null = null
  return () => {
    if (mod) return mod
    if (!promise) { promise = import('recharts').then(m => { mod = m; return m }) }
    throw promise
  }
})()

function MarjaChartInner({ data, keys, colors }: { data: Record<string, string | number>[]; keys: string[]; colors: string[] }) {
  const { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } = LazyRecharts()
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 20 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
        <XAxis dataKey="month" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => new Intl.NumberFormat('ro-RO', { notation: 'compact' }).format(v)} />
        <Tooltip formatter={(v: unknown) => new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(v)) + ' EUR'} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {keys.map((key, i) => (
          <Line key={key} type="monotone" dataKey={key} stroke={colors[i % colors.length]} strokeWidth={2} dot={{ r: 3 }} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}


/* ═══════════════════════════════════
   SubtotalPicker — select indicators
   ═══════════════════════════════════ */

function SubtotalPicker({ indicators, selectedIds, onToggle }: {
  indicators: { id: number; label: string; group: string }[]
  selectedIds: number[]
  onToggle: (id: number) => void
}) {
  const [open, setOpen] = useState(false)
  const selectedCount = selectedIds.length

  const grouped = useMemo(() => {
    const map = new Map<string, { id: number; label: string }[]>()
    for (const ind of indicators) {
      if (!map.has(ind.group)) map.set(ind.group, [])
      map.get(ind.group)!.push({ id: ind.id, label: ind.label })
    }
    return map
  }, [indicators])

  if (indicators.length === 0) return <span className="text-xs text-muted-foreground">Adaugă mai întâi indicatori</span>

  return (
    <div className="space-y-2">
      {/* Dropdown trigger */}
      <button
        type="button"
        onClick={() => setOpen(p => !p)}
        className="flex items-center justify-between w-full h-8 px-3 rounded-md border border-input bg-transparent text-xs cursor-pointer hover:bg-accent/50 transition-colors"
      >
        <span className={selectedCount > 0 ? 'text-foreground' : 'text-muted-foreground'}>
          {selectedCount > 0 ? `${selectedCount} indicator${selectedCount !== 1 ? 'i' : ''} selecta${selectedCount !== 1 ? 'ți' : 't'}` : 'Selectează indicatori...'}
        </span>
        <ChevronDown className={`h-3.5 w-3.5 text-muted-foreground transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown panel */}
      {open && (
        <div className="border rounded-md bg-popover shadow-md max-h-60 overflow-y-auto">
          {[...grouped.entries()].map(([group, items]) => (
            <div key={group}>
              <div className="px-3 py-1.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-wide bg-muted/50 sticky top-0">{group}</div>
              {items.map(item => {
                const isSelected = selectedIds.includes(item.id)
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => onToggle(item.id)}
                    className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-left hover:bg-accent/50 cursor-pointer transition-colors"
                  >
                    <div className={`flex items-center justify-center h-4 w-4 rounded border ${isSelected ? 'bg-primary border-primary' : 'border-input'}`}>
                      {isSelected && <Check className="h-3 w-3 text-primary-foreground" />}
                    </div>
                    {item.label}
                  </button>
                )
              })}
            </div>
          ))}
        </div>
      )}

      {/* Selected chips */}
      {selectedCount > 0 && (
        <div className="flex flex-wrap gap-1">
          {selectedIds.map(id => {
            const ind = indicators.find(i => i.id === id)
            return ind ? (
              <span key={id} className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] text-primary font-medium">
                {ind.label}
                <button type="button" onClick={() => onToggle(id)} className="hover:text-destructive cursor-pointer"><X className="h-3 w-3" /></button>
              </span>
            ) : null
          })}
        </div>
      )}
    </div>
  )
}
