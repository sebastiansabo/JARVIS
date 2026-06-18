import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload, Lock, Unlock, FileSpreadsheet, AlertTriangle, Eye } from 'lucide-react'
import { toast } from 'sonner'

import { controllingApi } from '@/api/controlling'
import { useAuthStore } from '@/stores/authStore'
import type { BabPeriod } from '@/types/controlling'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

const MONTH_NAMES = ['', 'IAN', 'FEB', 'MAR', 'APR', 'MAI', 'IUN', 'IUL', 'AUG', 'SEP', 'OCT', 'NOI', 'DEC']

export default function Controlling() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)

  // Company selector — default to user's company or first available
  const [companyId, setCompanyId] = useState<number>(user?.company_id || 0)

  // Import modal state
  const [importModal, setImportModal] = useState<{ year: number; month: number; existing?: BabPeriod } | null>(null)
  const [importFile, setImportFile] = useState<File | null>(null)
  const [eurRateInput, setEurRateInput] = useState('')

  // Lock confirm state
  const [lockConfirm, setLockConfirm] = useState<BabPeriod | null>(null)

  // Fetch companies for selector
  const { data: companiesData } = useQuery({
    queryKey: ['companies'],
    queryFn: () => fetch('/hr/events/api/structure/companies', { credentials: 'same-origin' }).then(r => r.json()),
  })
  const companies: { id: number; company: string }[] = companiesData?.companies || companiesData || []

  // Set default company when loaded
  if (companyId === 0 && companies.length > 0) {
    setCompanyId(companies[0].id)
  }

  // Fetch periods
  const { data: periodsData, isLoading } = useQuery({
    queryKey: ['bab-periods', companyId],
    queryFn: () => controllingApi.getPeriods(companyId),
    enabled: companyId > 0,
  })
  const periods: BabPeriod[] = periodsData?.periods || []

  // Import mutation
  const importMutation = useMutation({
    mutationFn: async () => {
      if (!importFile || !importModal) throw new Error('No file selected')
      // Set EUR rate first if provided
      if (eurRateInput) {
        await controllingApi.setEurRate(importModal.year, importModal.month, companyId, parseFloat(eurRateInput))
      }
      return controllingApi.importBab(importFile, importModal.year, importModal.month, companyId)
    },
    onSuccess: (data) => {
      toast.success(`BAB importat: ${data.row_count} linii (import #${data.import_count})`)
      queryClient.invalidateQueries({ queryKey: ['bab-periods'] })
      setImportModal(null)
      setImportFile(null)
      setEurRateInput('')
    },
    onError: (err: Error) => toast.error(err.message),
  })

  // Lock mutation
  const lockMutation = useMutation({
    mutationFn: (uploadId: number) => controllingApi.lockUpload(uploadId),
    onSuccess: () => {
      toast.success('Perioadă blocată')
      queryClient.invalidateQueries({ queryKey: ['bab-periods'] })
      setLockConfirm(null)
    },
    onError: (err: Error) => toast.error(err.message),
  })

  // Unlock mutation
  const unlockMutation = useMutation({
    mutationFn: (uploadId: number) => controllingApi.unlockUpload(uploadId),
    onSuccess: () => {
      toast.success('Perioadă deblocată')
      queryClient.invalidateQueries({ queryKey: ['bab-periods'] })
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const openImportModal = useCallback((year: number, month: number, existing?: BabPeriod) => {
    setImportModal({ year, month, existing })
    setImportFile(null)
    setEurRateInput('')
    // Pre-fill EUR rate if exists
    if (companyId > 0) {
      controllingApi.getEurRate(year, month, companyId).then(res => {
        if (res?.rate) setEurRateInput(String(res.rate.eur_rate))
      }).catch(() => {})
    }
  }, [companyId])

  const handleFileDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file && file.name.toLowerCase().endsWith('.xlsx')) {
      setImportFile(file)
    } else {
      toast.error('Doar fișiere .xlsx')
    }
  }, [])

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) setImportFile(file)
  }, [])

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold">Controlling — BAB</h1>
          <p className="text-sm text-muted-foreground">Import BAB lunar și raport marjă</p>
        </div>
        <Select value={String(companyId)} onValueChange={(v) => setCompanyId(Number(v))}>
          <SelectTrigger className="w-64">
            <SelectValue placeholder="Selectează compania" />
          </SelectTrigger>
          <SelectContent>
            {companies.map((c: { id: number; company: string }) => (
              <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Period Grid */}
      {isLoading ? (
        <div className="text-center py-12 text-muted-foreground">Se încarcă...</div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
          {periods.map((p) => (
            <PeriodCard
              key={`${p.year}-${p.month}`}
              period={p}
              onImport={() => openImportModal(p.year, p.month, p.status !== 'MISSING' ? p : undefined)}
              onView={() => p.upload_id && navigate(`/app/accounting/controlling/${p.upload_id}`)}
              onLock={() => setLockConfirm(p)}
              onUnlock={() => p.upload_id && unlockMutation.mutate(p.upload_id)}
            />
          ))}
        </div>
      )}

      {/* Import Modal */}
      <Dialog open={!!importModal} onOpenChange={() => setImportModal(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              Import BAB — {importModal ? `${MONTH_NAMES[importModal.month]} ${importModal.year}` : ''}
            </DialogTitle>
            <DialogDescription>
              {importModal?.existing
                ? `Acest BAB va înlocui importul din ${importModal.existing.uploaded_at?.split('T')[0]} (${importModal.existing.filename}). Import #${(importModal.existing.import_count || 0) + 1}.`
                : 'Încarcă fișierul BAB (.xlsx) exportat din ERP.'}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {/* EUR Rate */}
            <div>
              <Label>Curs EUR (LEI/EUR)</Label>
              <Input
                type="number"
                step="0.0001"
                placeholder="ex: 4.9750"
                value={eurRateInput}
                onChange={(e) => setEurRateInput(e.target.value)}
              />
            </div>

            {/* File Drop Zone */}
            <div
              className="border-2 border-dashed rounded-lg p-6 text-center cursor-pointer hover:border-primary transition-colors"
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleFileDrop}
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
                  <p className="text-sm text-muted-foreground">Drag & drop .xlsx sau click pentru a selecta</p>
                </div>
              )}
              <input
                id="bab-file-input"
                type="file"
                accept=".xlsx"
                className="hidden"
                onChange={handleFileSelect}
              />
            </div>

            {importModal?.existing && (
              <div className="flex items-center gap-2 text-amber-600 bg-amber-50 rounded p-2 text-xs">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>Re-import: datele existente vor fi înlocuite</span>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setImportModal(null)}>Anulează</Button>
            <Button
              onClick={() => importMutation.mutate()}
              disabled={!importFile || !eurRateInput || importMutation.isPending}
            >
              {importMutation.isPending ? 'Se importă...' : 'Importă BAB'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Lock Confirm Dialog */}
      <Dialog open={!!lockConfirm} onOpenChange={() => setLockConfirm(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Blochează perioada</DialogTitle>
            <DialogDescription>
              Blochezi perioada {lockConfirm ? `${MONTH_NAMES[lockConfirm.month]} ${lockConfirm.year}` : ''}?
              Perioada poate fi deblocată ulterior de un utilizator cu permisiune.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setLockConfirm(null)}>Anulează</Button>
            <Button
              variant="destructive"
              onClick={() => lockConfirm?.upload_id && lockMutation.mutate(lockConfirm.upload_id)}
              disabled={lockMutation.isPending}
            >
              Blochează
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}


function PeriodCard({ period, onImport, onView, onLock, onUnlock }: {
  period: BabPeriod
  onImport: () => void
  onView: () => void
  onLock: () => void
  onUnlock: () => void
}) {
  const { status, year, month, marja_finala_eur } = period

  const bgClass = status === 'LOCKED'
    ? 'bg-blue-50 border-blue-200'
    : status === 'IMPORTED'
    ? 'bg-green-50 border-green-200'
    : 'bg-gray-50 border-gray-200'

  return (
    <Card className={`${bgClass} transition-all hover:shadow-md`}>
      <CardContent className="p-3 text-center space-y-2">
        <div className="font-semibold text-sm">{MONTH_NAMES[month]} {year}</div>

        {status === 'LOCKED' && (
          <>
            <div className="flex items-center justify-center gap-1 text-blue-600 text-xs font-medium">
              <Lock className="h-3 w-3" /> BLOCAT
            </div>
            {marja_finala_eur != null && (
              <div className="text-lg font-bold">{formatEur(marja_finala_eur)}</div>
            )}
            <div className="flex gap-1">
              <Button size="sm" variant="outline" className="flex-1 text-xs h-7" onClick={onView}>
                <Eye className="h-3 w-3 mr-1" /> Vezi
              </Button>
              <Button size="sm" variant="ghost" className="text-xs h-7 px-2" onClick={onUnlock} title="Deblochează">
                <Unlock className="h-3 w-3" />
              </Button>
            </div>
          </>
        )}

        {status === 'IMPORTED' && (
          <>
            <div className="text-green-600 text-xs font-medium">✓ IMPORTAT</div>
            {marja_finala_eur != null && (
              <div className="text-lg font-bold">{formatEur(marja_finala_eur)}</div>
            )}
            <div className="flex gap-1">
              <Button size="sm" variant="outline" className="flex-1 text-xs h-7" onClick={onView}>
                <Eye className="h-3 w-3 mr-1" /> Vezi
              </Button>
              <Button size="sm" variant="ghost" className="text-xs h-7 px-2" onClick={onImport} title="Re-import">
                <Upload className="h-3 w-3" />
              </Button>
              <Button size="sm" variant="ghost" className="text-xs h-7 px-2" onClick={onLock} title="Blochează">
                <Lock className="h-3 w-3" />
              </Button>
            </div>
          </>
        )}

        {status === 'MISSING' && (
          <>
            <div className="flex items-center justify-center gap-1 text-gray-400 text-xs">
              <AlertTriangle className="h-3 w-3" /> LIPSĂ
            </div>
            <Button size="sm" variant="default" className="w-full text-xs h-7" onClick={onImport}>
              <Upload className="h-3 w-3 mr-1" /> Import
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  )
}


function formatEur(value: number): string {
  if (Math.abs(value) >= 1000) {
    return `${(value / 1000).toFixed(0)}k €`
  }
  return `${value.toFixed(0)} €`
}
