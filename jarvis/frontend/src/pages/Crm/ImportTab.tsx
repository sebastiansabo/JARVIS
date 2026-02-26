import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Upload, FileSpreadsheet, CheckCircle2, AlertCircle, Loader2, Download } from 'lucide-react'
import { toast } from 'sonner'
import { crmApi } from '@/api/crm'

const SOURCE_TYPES = [
  { value: 'deals', label: 'Deals (NW + GW)', desc: 'Unified template — DB column names' },
  { value: 'clients', label: 'Clients', desc: 'Unified template — DB column names' },
  { value: 'nw', label: 'NW Legacy (DMS)', desc: 'Romanian DMS dossier export' },
  { value: 'gw', label: 'GW Legacy (DMS)', desc: 'Romanian DMS dossier export' },
  { value: 'crm_clients', label: 'Clients Legacy', desc: 'Workleto CRM export' },
]

export default function ImportTab() {
  const [sourceType, setSourceType] = useState('deals')
  const [file, setFile] = useState<File | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const qc = useQueryClient()

  const { data: batchesData } = useQuery({
    queryKey: ['crm-import-batches'],
    queryFn: () => crmApi.getImportBatches({ limit: '20' }),
  })

  const importMutation = useMutation({
    mutationFn: () => crmApi.importFile(file!, sourceType),
    onSuccess: (data) => {
      const s = data.stats
      toast.success(`Import complete: ${s.total || 0} rows processed, ${s.new || 0} new, ${s.new_clients || 0} new clients`)
      setFile(null)
      qc.invalidateQueries({ queryKey: ['crm-import-batches'] })
      qc.invalidateQueries({ queryKey: ['crm-stats'] })
      qc.invalidateQueries({ queryKey: ['crm-deals'] })
      qc.invalidateQueries({ queryKey: ['crm-clients'] })
    },
    onError: (err: Error) => {
      toast.error(`Import failed: ${err.message}`)
    },
  })

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const f = e.dataTransfer.files[0]
    if (f && (f.name.endsWith('.xlsx') || f.name.endsWith('.xls') || f.name.endsWith('.csv'))) {
      setFile(f)
    } else {
      toast.error('Only .xlsx, .xls, .csv files supported')
    }
  }

  const batches = batchesData?.batches || []

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle className="text-base">Import Data</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-4 items-end">
            <div className="space-y-1">
              <label className="text-sm font-medium">Source Type</label>
              <Select value={sourceType} onValueChange={setSourceType}>
                <SelectTrigger className="w-[250px]"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {SOURCE_TYPES.map(t => (
                    <SelectItem key={t.value} value={t.value}>
                      <div><div className="font-medium">{t.label}</div><div className="text-xs text-muted-foreground">{t.desc}</div></div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <a href="/api/crm/import/template" className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline pb-2">
              <Download className="h-4 w-4" />Download import template
            </a>
          </div>

          <div
            className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer
              ${file ? 'border-primary bg-primary/5' : 'border-muted-foreground/25 hover:border-primary/50'}`}
            onDragOver={e => e.preventDefault()}
            onDrop={handleDrop}
            onClick={() => fileRef.current?.click()}
          >
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.xls,.csv"
              className="hidden"
              onChange={e => { if (e.target.files?.[0]) setFile(e.target.files[0]) }}
            />
            {file ? (
              <div className="flex items-center justify-center gap-3">
                <FileSpreadsheet className="h-8 w-8 text-primary" />
                <div className="text-left">
                  <p className="font-medium">{file.name}</p>
                  <p className="text-sm text-muted-foreground">{(file.size / 1024).toFixed(0)} KB</p>
                </div>
              </div>
            ) : (
              <div>
                <Upload className="h-8 w-8 mx-auto text-muted-foreground mb-2" />
                <p className="text-sm text-muted-foreground">Drop .xlsx / .csv file here or click to browse</p>
              </div>
            )}
          </div>

          <Button
            onClick={() => importMutation.mutate()}
            disabled={!file || importMutation.isPending}
            className="w-full"
          >
            {importMutation.isPending ? (
              <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Importing...</>
            ) : (
              <><Upload className="h-4 w-4 mr-2" />Import {SOURCE_TYPES.find(t => t.value === sourceType)?.label}</>
            )}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Import History</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>File</TableHead>
                <TableHead>By</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Rows</TableHead>
                <TableHead className="text-right">New</TableHead>
                <TableHead className="text-right">Clients</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {batches.length === 0 ? (
                <TableRow><TableCell colSpan={8} className="text-center py-8 text-muted-foreground">No imports yet</TableCell></TableRow>
              ) : batches.map(b => (
                <TableRow key={b.id}>
                  <TableCell className="text-xs">{new Date(b.created_at).toLocaleString()}</TableCell>
                  <TableCell><Badge variant="outline">{b.source_type.toUpperCase()}</Badge></TableCell>
                  <TableCell className="text-xs max-w-[160px] truncate">{b.filename}</TableCell>
                  <TableCell className="text-xs">{b.uploaded_by_name || '-'}</TableCell>
                  <TableCell>
                    {b.status === 'completed' ? (
                      <CheckCircle2 className="h-4 w-4 text-green-500" />
                    ) : b.status === 'failed' ? (
                      <AlertCircle className="h-4 w-4 text-red-500" />
                    ) : (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    )}
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs">{b.total_rows}</TableCell>
                  <TableCell className="text-right font-mono text-xs">{b.new_rows}</TableCell>
                  <TableCell className="text-right font-mono text-xs">{b.new_clients} new / {b.matched_clients} matched</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
