import { useState, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload, FileSpreadsheet, X, Download, Info } from 'lucide-react'
import { toast } from 'sonner'

import { bilantApi } from '@/api/bilant'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { BilantTemplate } from '@/types/bilant'

interface UploadDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  companies: { id: number; company: string }[]
  templates: BilantTemplate[]
}

export function UploadDialog({ open, onOpenChange, companies, templates }: UploadDialogProps) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [companyId, setCompanyId] = useState('')
  const [templateId, setTemplateId] = useState('')
  const [periodLabel, setPeriodLabel] = useState('')
  const [periodDate, setPeriodDate] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const reset = () => {
    setCompanyId('')
    setTemplateId('')
    setPeriodLabel('')
    setPeriodDate('')
    setFile(null)
  }

  // Filter templates: show global + company-specific
  const filteredTemplates = templates.filter(
    t => !t.company_id || (companyId && t.company_id === Number(companyId))
  )

  const uploadMut = useMutation({
    mutationFn: () => {
      if (!file || !templateId || !companyId) throw new Error('Missing fields')
      return bilantApi.createGeneration(
        file,
        Number(templateId),
        Number(companyId),
        periodLabel || undefined,
        periodDate || undefined,
      )
    },
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['bilant-generations'] })
      toast.success(`Bilant generated: ${res.row_count} rows`)
      onOpenChange(false)
      reset()
      if (res.generation_id) navigate(`/app/accounting/bilant/${res.generation_id}`)
    },
    onError: (err: Error & { data?: { error?: string } }) => {
      toast.error(err.data?.error || err.message || 'Upload failed')
    },
  })

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files[0]
    if (f && (f.name.endsWith('.xlsx') || f.name.endsWith('.xls'))) {
      setFile(f)
    } else {
      toast.error('Please upload an Excel file (.xlsx)')
    }
  }, [])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) setFile(f)
  }

  const canSubmit = !!file && !!templateId && !!companyId && !uploadMut.isPending

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) reset(); onOpenChange(v) }}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>New Bilant Generation</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Company */}
          <div className="space-y-2">
            <Label>Company *</Label>
            <Select value={companyId} onValueChange={setCompanyId}>
              <SelectTrigger>
                <SelectValue placeholder="Select company" />
              </SelectTrigger>
              <SelectContent>
                {companies.map(c => (
                  <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Template */}
          <div className="space-y-2">
            <Label>Template *</Label>
            <Select value={templateId} onValueChange={setTemplateId}>
              <SelectTrigger>
                <SelectValue placeholder="Select template" />
              </SelectTrigger>
              <SelectContent>
                {filteredTemplates.map(t => (
                  <SelectItem key={t.id} value={String(t.id)}>
                    {t.name} {t.is_default && '(Default)'} {t.company_name ? `- ${t.company_name}` : '- Global'}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Period */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label>Period Label</Label>
              <Input value={periodLabel} onChange={e => setPeriodLabel(e.target.value)} placeholder="e.g. Q4 2025" />
            </div>
            <div className="space-y-2">
              <Label>Period Date</Label>
              <Input type="date" value={periodDate} onChange={e => setPeriodDate(e.target.value)} />
            </div>
          </div>

          {/* File Upload */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Balanta Excel File *</Label>
              <Button
                variant="link"
                size="sm"
                className="h-auto p-0 text-xs"
                onClick={() => bilantApi.downloadTemplate()}
              >
                <Download className="mr-1 h-3 w-3" />
                Download Template
              </Button>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xls"
              onChange={handleFileChange}
              className="hidden"
            />
            <div
              onClick={() => fileInputRef.current?.click()}
              onDragOver={e => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 transition-colors ${
                dragOver ? 'border-primary bg-primary/5' : 'border-muted-foreground/25 hover:border-muted-foreground/50'
              }`}
            >
              {file ? (
                <div className="flex items-center gap-2">
                  <FileSpreadsheet className="h-5 w-5 text-emerald-600" />
                  <span className="text-sm font-medium">{file.name}</span>
                  <span className="text-xs text-muted-foreground">({(file.size / 1024).toFixed(0)} KB)</span>
                  <Button variant="ghost" size="icon" className="h-6 w-6" onClick={(e) => { e.stopPropagation(); setFile(null) }}>
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ) : (
                <>
                  <Upload className="mb-2 h-8 w-8 text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">Drag & drop your Balanta Excel file here</p>
                  <p className="text-xs text-muted-foreground">or click to browse (.xlsx)</p>
                </>
              )}
            </div>
          </div>

          {/* Instructions */}
          <div className="rounded-md border border-blue-200 bg-blue-50 p-3 dark:border-blue-900/50 dark:bg-blue-950/30">
            <div className="flex gap-2">
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-blue-600 dark:text-blue-400" />
              <div className="space-y-1 text-xs text-blue-800 dark:text-blue-300">
                <p className="font-medium">Cerinte fisier Excel:</p>
                <ul className="list-inside list-disc space-y-0.5">
                  <li>Sheet-ul <strong>&quot;Balanta&quot;</strong> cu coloanele: Cont, SFD, SFC</li>
                  <li>Valorile bilantului se calculeaza automat din formulele template-ului</li>
                </ul>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => { reset(); onOpenChange(false) }}>Cancel</Button>
            <Button disabled={!canSubmit} onClick={() => uploadMut.mutate()}>
              {uploadMut.isPending ? 'Processing...' : 'Generate Bilant'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
