import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { vouchersApi } from '@/api/vouchers'
import type { Voucher } from '@/types/vouchers'

const STATUS_COLORS: Record<string, string> = {
  pending_approval: 'bg-yellow-100 text-yellow-800',
  active: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  redeemed: 'bg-gray-200 text-gray-600',
  expired: 'bg-red-50 text-red-600',
}

function expiringClass(v: Voucher): string {
  if (v.status !== 'active') return ''
  if (v.days_remaining !== null && v.days_remaining !== undefined && v.days_remaining <= 30)
    return 'bg-orange-50'
  return ''
}

export default function VouchersPanel() {
  const [selected, setSelected] = useState<Voucher | null>(null)

  const { data: vouchers = [], isLoading } = useQuery({
    queryKey: ['my-vouchers'],
    queryFn: () => vouchersApi.myVouchers(),
  })

  if (isLoading) return <div className="py-8 text-center text-muted-foreground">Loading...</div>
  if (vouchers.length === 0) return <div className="py-8 text-center text-muted-foreground">No vouchers issued yet.</div>

  return (
    <>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Code</TableHead>
              <TableHead>Client</TableHead>
              <TableHead>Contract</TableHead>
              <TableHead>VIN</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Benefit</TableHead>
              <TableHead>Issued</TableHead>
              <TableHead>Expires</TableHead>
              <TableHead>Days Left</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {vouchers.map((v) => (
              <TableRow key={v.id} className={`cursor-pointer hover:bg-muted/50 ${expiringClass(v)}`} onClick={() => setSelected(v)}>
                <TableCell className="font-mono text-xs">{v.voucher_code}</TableCell>
                <TableCell>{v.client_name}</TableCell>
                <TableCell>{v.contract_number}</TableCell>
                <TableCell className="font-mono text-xs">{v.car_vin}</TableCell>
                <TableCell>{v.voucher_type.replace(/_/g, ' ')}</TableCell>
                <TableCell>{v.benefit_display}</TableCell>
                <TableCell>{v.issued_at || '—'}</TableCell>
                <TableCell>{v.expires_at || '—'}</TableCell>
                <TableCell>
                  {v.days_remaining !== null && v.days_remaining !== undefined ? (
                    <span className={v.days_remaining <= 30 ? 'text-orange-500 font-medium' : ''}>{v.days_remaining}d</span>
                  ) : '—'}
                </TableCell>
                <TableCell>
                  <Badge variant="outline" className={STATUS_COLORS[v.status] || ''}>{v.status.replace('_', ' ')}</Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <Dialog open={!!selected} onOpenChange={() => setSelected(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{selected?.voucher_code}</DialogTitle>
          </DialogHeader>
          {selected && (
            <div className="space-y-2 text-sm">
              <div className="grid grid-cols-2 gap-2">
                <div><span className="text-muted-foreground">Client:</span> {selected.client_name}</div>
                <div><span className="text-muted-foreground">Contract:</span> {selected.contract_number}</div>
                <div><span className="text-muted-foreground">VIN:</span> <span className="font-mono">{selected.car_vin}</span></div>
                <div><span className="text-muted-foreground">Type:</span> {selected.voucher_type.replace(/_/g, ' ')}</div>
                <div><span className="text-muted-foreground">Benefit:</span> {selected.benefit_display}</div>
                <div><span className="text-muted-foreground">Validity:</span> {selected.validity_months} months</div>
                <div><span className="text-muted-foreground">Issued:</span> {selected.issued_at || '—'}</div>
                <div><span className="text-muted-foreground">Expires:</span> {selected.expires_at || '—'}</div>
                <div><span className="text-muted-foreground">Status:</span> <Badge variant="outline" className={STATUS_COLORS[selected.status] || ''}>{selected.status.replace('_', ' ')}</Badge></div>
              </div>
              {selected.notes && <div><span className="text-muted-foreground">Notes:</span> {selected.notes}</div>}
              {selected.redemption_notes && <div><span className="text-muted-foreground">Redemption notes:</span> {selected.redemption_notes}</div>}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" asChild>
              <a href={vouchersApi.pdfUrl(selected?.id ?? 0)} download target="_blank" rel="noopener">
                <FileText className="mr-1 h-4 w-4" />Download PDF
              </a>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
