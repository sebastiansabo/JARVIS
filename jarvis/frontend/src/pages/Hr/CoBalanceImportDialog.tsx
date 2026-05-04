import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Upload, X, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogTrigger,
} from '@/components/ui/dialog'
import { hrApi } from '@/api/hr'
import type { CoBalanceImportRun } from '@/types/hr'

interface FileState {
  file: File
  runId: string | null
  status: 'queued' | 'running' | 'completed' | 'failed'
  rowsTotal: number
  rowsMatched: number
  rowsUnmatched: number
  error: string | null
}

interface Props {
  trigger?: React.ReactNode
  defaultYear?: number
  onComplete?: () => void
}

export default function CoBalanceImportDialog({ trigger, defaultYear, onComplete }: Props) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [year, setYear] = useState<number>(defaultYear ?? new Date().getFullYear())
  const [files, setFiles] = useState<FileState[]>([])
  const [running, setRunning] = useState(false)
  const pollRef = useRef<number | null>(null)

  function resetState() {
    setFiles([])
    setRunning(false)
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  function handleOpenChange(next: boolean) {
    setOpen(next)
    if (!next) {
      resetState()
    }
  }

  function onFilesPicked(fl: FileList | null) {
    if (!fl) return
    const list: FileState[] = []
    for (let i = 0; i < fl.length; i++) {
      const f = fl[i]
      if (!/\.(xlsx|xlsm)$/i.test(f.name)) continue
      list.push({
        file: f,
        runId: null,
        status: 'queued',
        rowsTotal: 0,
        rowsMatched: 0,
        rowsUnmatched: 0,
        error: null,
      })
    }
    setFiles(list)
  }

  function removeFile(idx: number) {
    setFiles((prev) => prev.filter((_, i) => i !== idx))
  }

  async function startImport() {
    if (files.length === 0 || !year) return
    setRunning(true)

    // Kick off imports sequentially (server-side lock serializes anyway)
    const started: FileState[] = []
    for (const fs of files) {
      try {
        const res = await hrApi.importCoBalance(fs.file, year)
        started.push({ ...fs, runId: res.run_id, status: 'running' })
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : 'Upload failed'
        started.push({ ...fs, status: 'failed', error: msg })
      }
    }
    setFiles(started)

    // Poll
    pollRef.current = window.setInterval(async () => {
      const current = [...started]
      let stillRunning = false
      for (let i = 0; i < current.length; i++) {
        const f = current[i]
        if (f.status !== 'running' || !f.runId) continue
        try {
          const res = await hrApi.getCoBalanceImportStatus(f.runId)
          const row: CoBalanceImportRun = res.data
          if (row.status !== 'running') {
            current[i] = {
              ...f,
              status: row.status,
              rowsTotal: row.rows_total,
              rowsMatched: row.rows_matched,
              rowsUnmatched: row.rows_unmatched,
              error: row.error_message,
            }
          } else {
            stillRunning = true
          }
        } catch {
          stillRunning = true
        }
      }
      setFiles(current)
      if (!stillRunning) {
        if (pollRef.current) {
          clearInterval(pollRef.current)
          pollRef.current = null
        }
        setRunning(false)
        qc.invalidateQueries({ queryKey: ['hr', 'employees', 'work-stats'] })
        onComplete?.()
      }
    }, 1500)
  }

  const canSubmit = files.length > 0 && year >= 2000 && year <= 2100 && !running

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button variant="outline" size="sm" className="gap-2">
            <Upload className="h-4 w-4" />
            Import CO Sold
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Import CO Balance (annual)</DialogTitle>
          <DialogDescription>
            Upload HR's <code>Raport_concedii_contracte_lunar</code> xlsx files (one per company).
            Re-uploading the same year refreshes the 5 input columns; CO taken is read from Sincron.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <Label htmlFor="co-year" className="w-20">Year</Label>
            <Input
              id="co-year"
              type="number"
              min={2000}
              max={2100}
              value={year}
              onChange={(e) => setYear(parseInt(e.target.value || '0', 10))}
              className="w-32"
              disabled={running}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="co-files">Files</Label>
            <Input
              id="co-files"
              type="file"
              accept=".xlsx,.xlsm"
              multiple
              onChange={(e) => onFilesPicked(e.target.files)}
              disabled={running}
            />
          </div>

          {files.length > 0 && (
            <div className="rounded-md border">
              <table className="w-full text-xs">
                <thead className="bg-muted/50 text-muted-foreground">
                  <tr>
                    <th className="text-left font-medium px-3 py-2">File</th>
                    <th className="text-right font-medium px-3 py-2">Rows</th>
                    <th className="text-right font-medium px-3 py-2">Matched</th>
                    <th className="text-right font-medium px-3 py-2">Unmatched</th>
                    <th className="text-center font-medium px-3 py-2 w-16">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {files.map((f, i) => (
                    <tr key={`${f.file.name}-${i}`} className="border-t">
                      <td className="px-3 py-2 truncate max-w-[240px]" title={f.file.name}>{f.file.name}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{f.status === 'completed' ? f.rowsTotal : '—'}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-green-600">{f.status === 'completed' ? f.rowsMatched : '—'}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-amber-600">{f.status === 'completed' ? f.rowsUnmatched : '—'}</td>
                      <td className="px-3 py-2 text-center">
                        {f.status === 'queued' && (
                          <button onClick={() => removeFile(i)} disabled={running} className="text-muted-foreground hover:text-foreground">
                            <X className="h-3.5 w-3.5 inline" />
                          </button>
                        )}
                        {f.status === 'running' && <Loader2 className="h-3.5 w-3.5 inline animate-spin text-blue-600" />}
                        {f.status === 'completed' && <CheckCircle2 className="h-3.5 w-3.5 inline text-green-600" />}
                        {f.status === 'failed' && (
                          <span title={f.error || 'Failed'}>
                            <AlertCircle className="h-3.5 w-3.5 inline text-red-600" />
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => handleOpenChange(false)} disabled={running}>
            Close
          </Button>
          <Button onClick={startImport} disabled={!canSubmit}>
            {running ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Importing…</> : 'Import'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
