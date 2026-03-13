import { StatusBadge } from '@/components/shared/StatusBadge'
import { CurrencyDisplay } from '@/components/shared/CurrencyDisplay'
import type { EFacturaInvoice } from '@/types/efactura'

export type InvoiceRow = EFacturaInvoice & { _hidden?: boolean }

export interface ColumnDef {
  key: string
  label: string
  align?: 'left' | 'right'
  render: (inv: InvoiceRow) => React.ReactNode
}

export const fmtDate = (d: string | null) => d ? new Date(d).toLocaleDateString('ro-RO') : '—'

export const columnDefs: ColumnDef[] = [
  {
    key: 'supplier',
    label: 'Supplier',
    render: (inv) => (
      <>
        <div className="font-medium">
          {inv.partner_name}
          {inv._hidden && (
            <span className="ml-1.5 rounded bg-muted px-1.5 py-0.5 text-[10px] font-normal text-muted-foreground">
              hidden
            </span>
          )}
        </div>
        {inv.partner_cif && <div className="text-xs text-muted-foreground">{inv.partner_cif}</div>}
      </>
    ),
  },
  {
    key: 'invoice_number',
    label: 'Invoice #',
    render: (inv) => (
      <span className="font-mono text-xs">
        {inv.invoice_series ? `${inv.invoice_series}-` : ''}
        {inv.invoice_number}
      </span>
    ),
  },
  {
    key: 'date',
    label: 'Date',
    render: (inv) => <span className="text-muted-foreground">{fmtDate(inv.issue_date)}</span>,
  },
  {
    key: 'due_date',
    label: 'Due Date',
    render: (inv) => <span className="text-muted-foreground">{fmtDate(inv.due_date ?? null)}</span>,
  },
  {
    key: 'direction',
    label: 'Direction',
    render: (inv) => <StatusBadge status={inv.direction} />,
  },
  {
    key: 'amount',
    label: 'Amount',
    align: 'right',
    render: (inv) => <CurrencyDisplay value={inv.total_amount} currency={inv.currency} />,
  },
  {
    key: 'vat',
    label: 'VAT',
    align: 'right',
    render: (inv) => <CurrencyDisplay value={inv.total_vat} currency={inv.currency} />,
  },
  {
    key: 'without_vat',
    label: 'Without VAT',
    align: 'right',
    render: (inv) => <CurrencyDisplay value={inv.total_without_vat} currency={inv.currency} />,
  },
  {
    key: 'company',
    label: 'Company',
    render: (inv) => <span className="text-xs text-muted-foreground">{inv.company_name || inv.cif_owner}</span>,
  },
  {
    key: 'type',
    label: 'Type',
    render: (inv) => <>{inv.type_override || inv.mapped_type_names?.join(', ') || '—'}</>,
  },
  {
    key: 'department',
    label: 'Department',
    render: (inv) => <>{inv.department_override || inv.mapped_department || '—'}</>,
  },
  {
    key: 'subdepartment',
    label: 'Subdepartment',
    render: (inv) => <>{inv.subdepartment_override || inv.mapped_subdepartment || '—'}</>,
  },
  {
    key: 'mapped_supplier',
    label: 'Mapped Supplier',
    render: (inv) => <>{inv.mapped_supplier_name || '—'}</>,
  },
  {
    key: 'mapped_brand',
    label: 'Brand',
    render: (inv) => <>{inv.mapped_brand || '—'}</>,
  },
  {
    key: 'kod_konto',
    label: 'Kod Konto',
    render: (inv) => <span className="font-mono text-xs">{inv.mapped_kod_konto || '—'}</span>,
  },
]

export const columnDefMap = new Map(columnDefs.map((c) => [c.key, c]))

export const defaultColumns = [
  'supplier', 'invoice_number', 'date', 'direction', 'amount', 'company', 'type',
]

export const STORAGE_KEY = 'efactura-unallocated-columns'
