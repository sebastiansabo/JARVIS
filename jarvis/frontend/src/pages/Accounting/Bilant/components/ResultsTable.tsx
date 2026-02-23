import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { BilantResult } from '@/types/bilant'

interface ResultsTableProps {
  results: BilantResult[]
}

function fmtValue(n: number): string {
  return new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(n)
}

export function ResultsTable({ results }: ResultsTableProps) {
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set())

  const toggleRow = (id: number) => {
    setExpandedRows(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  if (results.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">No results</p>
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-12">Nr.</TableHead>
            <TableHead>Description</TableHead>
            <TableHead className="w-32 text-right">Value</TableHead>
            <TableHead className="w-10" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {results.map(r => {
            const isExpanded = expandedRows.has(r.id)
            const hasVerification = !!r.verification
            const isSeparator = r.row_type === 'separator'
            const isSection = r.row_type === 'section'
            const isTotal = r.row_type === 'total' || r.is_bold

            if (isSeparator) {
              return (
                <TableRow key={r.id} className="border-t-2">
                  <TableCell colSpan={4} className="h-1 p-0" />
                </TableRow>
              )
            }

            return (
              <>
                <TableRow
                  key={r.id}
                  className={cn(
                    hasVerification && 'cursor-pointer',
                    isSection && 'bg-muted/50',
                    isTotal && 'font-semibold',
                  )}
                  onClick={() => hasVerification && toggleRow(r.id)}
                >
                  <TableCell className="text-xs text-muted-foreground">{r.nr_rd || ''}</TableCell>
                  <TableCell>
                    <span
                      className={cn('text-sm', isSection && 'font-semibold text-muted-foreground uppercase text-xs')}
                      style={{ paddingLeft: `${(r.indent_level || 0) * 16}px` }}
                    >
                      {r.description}
                    </span>
                  </TableCell>
                  <TableCell className={cn('text-right tabular-nums text-sm', isTotal && 'font-bold')}>
                    {r.value !== 0 || isTotal ? fmtValue(r.value) : ''}
                  </TableCell>
                  <TableCell>
                    {hasVerification && (
                      isExpanded
                        ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                        : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                    )}
                  </TableCell>
                </TableRow>
                {isExpanded && hasVerification && (
                  <TableRow key={`${r.id}-detail`} className="bg-muted/30">
                    <TableCell />
                    <TableCell colSpan={3}>
                      <div className="py-1 text-xs text-muted-foreground font-mono whitespace-pre-wrap">
                        {r.formula_ct && <div className="mb-1"><span className="font-medium">CT:</span> {r.formula_ct}</div>}
                        {r.formula_rd && <div className="mb-1"><span className="font-medium">RD:</span> {r.formula_rd}</div>}
                        <div><span className="font-medium">Verification:</span> {r.verification}</div>
                      </div>
                    </TableCell>
                  </TableRow>
                )}
              </>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
