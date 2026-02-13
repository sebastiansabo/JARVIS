import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { CurrencyDisplay } from '@/components/shared/CurrencyDisplay'
import { EmptyState } from '@/components/shared/EmptyState'
import type { InvoiceSummary } from '@/types/invoices'

interface SummaryTableProps {
  data: InvoiceSummary[]
  nameKey: 'company' | 'department' | 'brand' | 'supplier'
  label: string
}

export function SummaryTable({ data, nameKey, label }: SummaryTableProps) {
  if (data.length === 0) {
    return <EmptyState title={`No ${label.toLowerCase()} data`} description="Try adjusting your filters." />
  }

  const totalRon = data.reduce((sum, d) => sum + Number(d.total_value_ron ?? 0), 0)
  const totalEur = data.reduce((sum, d) => sum + Number(d.total_value_eur ?? 0), 0)
  const totalInvoices = data.reduce((sum, d) => sum + Number(d.invoice_count ?? 0), 0)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          By {label} ({data.length})
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{label}</TableHead>
                <TableHead className="text-right">Invoices</TableHead>
                <TableHead className="text-right">Total RON</TableHead>
                <TableHead className="text-right">Total EUR</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((row, idx) => (
                <TableRow key={`${row[nameKey]}-${idx}`}>
                  <TableCell className="font-medium">{row[nameKey] || 'N/A'}</TableCell>
                  <TableCell className="text-right">{row.invoice_count}</TableCell>
                  <TableCell className="text-right">
                    <CurrencyDisplay value={row.total_value_ron} currency="RON" />
                  </TableCell>
                  <TableCell className="text-right">
                    <CurrencyDisplay value={row.total_value_eur} currency="EUR" />
                  </TableCell>
                </TableRow>
              ))}
              <TableRow className="font-semibold">
                <TableCell>Total</TableCell>
                <TableCell className="text-right">{totalInvoices}</TableCell>
                <TableCell className="text-right">
                  <CurrencyDisplay value={totalRon} currency="RON" />
                </TableCell>
                <TableCell className="text-right">
                  <CurrencyDisplay value={totalEur} currency="EUR" />
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}
