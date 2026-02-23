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

/** Parse verification lines into account→value map. */
function parseVerification(verification: string): Record<string, number> {
  const map: Record<string, number> = {}
  for (const line of verification.split('\n')) {
    const m = line.trim().match(/^(\d+)\s*=\s*(-?[\d,.]+)$/)
    if (m) map[m[1]] = parseFloat(m[2].replace(',', '.'))
  }
  return map
}

/** Enrich CT formula with per-prefix subtotals from verification data. */
function enrichCtFormula(formulaCt: string, verification: string): string {
  if (!formulaCt || !verification) return formulaCt || ''
  const acctMap = parseVerification(verification)
  if (Object.keys(acctMap).length === 0) return formulaCt

  // Tokenize formula: handle +/-, dinct., regular +/-
  const tokens: { prefix: string; op: string }[] = []
  let i = 0
  let sign = '+'
  const f = formulaCt.replace(/\s/g, '')
  while (i < f.length) {
    // +/- dynamic sign
    if (f.slice(i, i + 3) === '+/-') {
      i += 3
      let num = ''
      while (i < f.length && /\d/.test(f[i])) { num += f[i]; i++ }
      if (num) tokens.push({ prefix: num, op: '+/-' })
      continue
    }
    // dinct. prefix
    if (f.slice(i, i + 6).toLowerCase() === 'dinct.') {
      i += 6
      let num = ''
      while (i < f.length && /\d/.test(f[i])) { num += f[i]; i++ }
      if (num) tokens.push({ prefix: num, op: '-' })
      continue
    }
    if (f[i] === '+') { sign = '+'; i++; continue }
    if (f[i] === '-') { sign = '-'; i++; continue }
    if (/\d/.test(f[i])) {
      let num = ''
      while (i < f.length && /\d/.test(f[i])) { num += f[i]; i++ }
      tokens.push({ prefix: num, op: sign })
      sign = '+'
      continue
    }
    i++
  }

  // Sum verification values per prefix
  const parts: string[] = []
  for (let t = 0; t < tokens.length; t++) {
    const { prefix, op } = tokens[t]
    let total = 0
    let found = false
    for (const [acct, val] of Object.entries(acctMap)) {
      if (acct.startsWith(prefix) || acct === prefix) {
        total += val
        found = true
      }
    }
    const display = found ? fmtValue(Math.round(Math.abs(total))) : '0'
    const opStr = t === 0 ? (op === '-' ? '-' : '') : (op === '-' ? ' - ' : ' + ')
    const dynLabel = tokens[t].op === '+/-' ? '+/-' : ''
    parts.push(`${opStr}${dynLabel}${prefix} (${display})`)
  }

  return parts.join('')
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
                        {r.formula_ct && <div className="mb-1"><span className="font-medium">CT:</span> {enrichCtFormula(r.formula_ct, r.verification || '')} <span className="font-medium">= {fmtValue(r.value)}</span></div>}
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
