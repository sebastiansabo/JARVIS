import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, Download, ShieldCheck } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Checkbox } from '@/components/ui/checkbox'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { EmptyState } from '@/components/shared/EmptyState'
import { consentsApi } from '@/api/consents'
import type { ConsentComplianceUser } from '@/api/consents'

// Used only when the compliance response is empty (no user to derive columns from) —
// keeps the table header non-empty rather than blank. See core/consents/repositories
// seed data for the canonical doc_keys.
const FALLBACK_DOC_KEYS = ['data_usage', 'gdpr', 'nda']

function csvEscape(value: string): string {
  if (/[",\n]/.test(value)) return `"${value.replace(/"/g, '""')}"`
  return value
}

function formatSignedAt(signedAt: string | null): string {
  if (!signedAt) return ''
  const d = new Date(signedAt)
  if (Number.isNaN(d.getTime())) return signedAt
  return d.toLocaleString('ro-RO', { dateStyle: 'medium', timeStyle: 'short' })
}

export default function ConsentComplianceTab() {
  const [pendingOnly, setPendingOnly] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['consent-compliance', pendingOnly],
    queryFn: () => consentsApi.getCompliance(pendingOnly ? 'pending' : undefined),
  })

  const rows: ConsentComplianceUser[] = data?.compliance ?? []

  const docColumns = useMemo(() => {
    const fromData = rows[0]?.documents
    if (fromData && fromData.length > 0) {
      return fromData.map((d) => ({ doc_key: d.doc_key, title: d.title }))
    }
    return FALLBACK_DOC_KEYS.map((key) => ({ doc_key: key, title: key }))
  }, [rows])

  const exportCsv = () => {
    const header = ['Nume', 'Email', 'Companie', ...docColumns.map((c) => c.title)]
    const lines = rows.map((u) => {
      const docByKey = new Map(u.documents.map((d) => [d.doc_key, d]))
      const cells = docColumns.map((c) => {
        const doc = docByKey.get(c.doc_key)
        if (!doc || !doc.signed) return 'nu'
        return doc.signed_at ?? 'da'
      })
      return [u.name, u.email, u.company, ...cells].map(csvEscape).join(',')
    })
    const csv = [header.map(csvEscape).join(','), ...lines].join('\n')
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `acorduri-conformitate-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
          <Checkbox
            checked={pendingOnly}
            onCheckedChange={(checked) => setPendingOnly(checked === true)}
          />
          Doar cu acorduri lipsă
        </label>
        <Button
          variant="outline"
          size="sm"
          className="ml-auto h-8 text-xs"
          onClick={exportCsv}
          disabled={rows.length === 0}
        >
          <Download className="mr-1.5 h-3.5 w-3.5" />
          Export CSV
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
        </div>
      ) : rows.length === 0 ? (
        <EmptyState
          icon={<ShieldCheck className="h-10 w-10" />}
          title={pendingOnly ? 'Toată lumea e la zi' : 'Niciun angajat găsit'}
          description={
            pendingOnly
              ? 'Toți angajații au semnat toate acordurile obligatorii.'
              : undefined
          }
        />
      ) : (
        <TooltipProvider>
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Nume</TableHead>
                      <TableHead>Email</TableHead>
                      <TableHead>Companie</TableHead>
                      {docColumns.map((c) => (
                        <TableHead key={c.doc_key} className="text-center">{c.title}</TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rows.map((u) => {
                      const docByKey = new Map(u.documents.map((d) => [d.doc_key, d]))
                      return (
                        <TableRow key={u.user_id}>
                          <TableCell className="font-medium">{u.name}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">{u.email}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">{u.company}</TableCell>
                          {docColumns.map((c) => {
                            const doc = docByKey.get(c.doc_key)
                            const signed = doc?.signed ?? false
                            return (
                              <TableCell key={c.doc_key} className="text-center">
                                {signed ? (
                                  <Tooltip>
                                    <TooltipTrigger asChild>
                                      <CheckCircle2 className="mx-auto h-4 w-4 text-green-600 cursor-help" />
                                    </TooltipTrigger>
                                    <TooltipContent>
                                      Semnat{formatSignedAt(doc?.signed_at ?? null) ? ` — ${formatSignedAt(doc?.signed_at ?? null)}` : ''}
                                    </TooltipContent>
                                  </Tooltip>
                                ) : (
                                  <span className="text-muted-foreground" title="Nesemnat">—</span>
                                )}
                              </TableCell>
                            )
                          })}
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TooltipProvider>
      )}
    </div>
  )
}
