import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download, Loader2 } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { profileApi, type InvoicePreview } from '@/api/profile'
import { efacturaApi } from '@/api/efactura'
import { invoicesApi } from '@/api/invoices'

function money(value: string | null | undefined, currency: string): string {
  const n = Number(value)
  if (!value || !isFinite(n)) return `${value ?? '-'} ${currency}`.trim()
  return `${n.toLocaleString('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`
}

function fmtDate(iso: string | null): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString('ro-RO')
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col">
      <span className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className="text-sm">{value || '-'}</span>
    </div>
  )
}

function Party({ title, name, cif, reg, address }: {
  title: string; name: string; cif: string; reg?: string | null; address: string | null
}) {
  return (
    <div className="rounded-md border p-3">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{title}</div>
      <div className="text-sm font-medium">{name || '-'}</div>
      {cif && <div className="text-xs text-muted-foreground">CIF: {cif}</div>}
      {reg && <div className="text-xs text-muted-foreground">Nr. reg.: {reg}</div>}
      {address && <div className="mt-1 text-xs text-muted-foreground">{address}</div>}
    </div>
  )
}

function PreviewBody({ p }: { p: InvoicePreview }) {
  const cur = p.currency || 'RON'
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Field label="Serie" value={p.invoice_series} />
        <Field label="Număr" value={p.invoice_number} />
        <Field label="Data emiterii" value={fmtDate(p.issue_date)} />
        <Field label="Scadență" value={fmtDate(p.due_date)} />
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Party title="Furnizor" name={p.seller.name} cif={p.seller.cif} reg={p.seller.reg_number} address={p.seller.address} />
        <Party title="Client" name={p.buyer.name} cif={p.buyer.cif} address={p.buyer.address} />
      </div>

      <div>
        <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Articole</div>
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-xs text-muted-foreground">
              <tr>
                <th className="px-2 py-1.5 text-left font-medium">#</th>
                <th className="px-2 py-1.5 text-left font-medium">Descriere</th>
                <th className="px-2 py-1.5 text-right font-medium">Cant.</th>
                <th className="px-2 py-1.5 text-left font-medium">U.M.</th>
                <th className="px-2 py-1.5 text-right font-medium">Preț unitar</th>
                <th className="px-2 py-1.5 text-right font-medium">Valoare</th>
                <th className="px-2 py-1.5 text-right font-medium">TVA %</th>
              </tr>
            </thead>
            <tbody>
              {p.line_items.length === 0 ? (
                <tr><td colSpan={7} className="px-2 py-3 text-center text-xs text-muted-foreground">
                  Fără articole detaliate în XML
                </td></tr>
              ) : p.line_items.map((li) => (
                <tr key={li.line_number} className="border-t">
                  <td className="px-2 py-1.5 text-muted-foreground">{li.line_number}</td>
                  <td className="px-2 py-1.5">{li.description}</td>
                  <td className="px-2 py-1.5 text-right">{Number(li.quantity).toLocaleString('ro-RO')}</td>
                  <td className="px-2 py-1.5">{li.unit}</td>
                  <td className="px-2 py-1.5 text-right">{money(li.unit_price, cur)}</td>
                  <td className="px-2 py-1.5 text-right">{money(li.line_amount, cur)}</td>
                  <td className="px-2 py-1.5 text-right">{Number(li.vat_rate)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {p.vat_breakdown.length > 0 && (
          <div className="rounded-md border p-3">
            <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Defalcare TVA</div>
            <table className="w-full text-sm">
              <tbody>
                {p.vat_breakdown.map((b, i) => (
                  <tr key={i}>
                    <td className="py-0.5 text-muted-foreground">Cotă {Number(b.rate)}%</td>
                    <td className="py-0.5 text-right">bază {money(b.taxable, cur)}</td>
                    <td className="py-0.5 text-right">TVA {money(b.amount, cur)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="rounded-md border p-3 sm:ml-auto sm:w-full">
          <div className="flex justify-between py-0.5 text-sm">
            <span className="text-muted-foreground">Total fără TVA</span>
            <span>{money(p.totals.without_vat, cur)}</span>
          </div>
          <div className="flex justify-between py-0.5 text-sm">
            <span className="text-muted-foreground">TVA</span>
            <span>{money(p.totals.vat, cur)}</span>
          </div>
          <div className="mt-1 flex justify-between border-t pt-1.5 text-base font-semibold">
            <span>Total</span>
            <span>{money(p.totals.total, cur)}</span>
          </div>
        </div>
      </div>

      {(p.payment.bank_account || p.payment.terms || p.note) && (
        <div className="space-y-1 rounded-md border p-3 text-xs text-muted-foreground">
          {p.payment.bank_account && <div>IBAN: <span className="font-mono">{p.payment.bank_account}</span></div>}
          {p.payment.terms && <div>Termeni de plată: {p.payment.terms}</div>}
          {p.note && <div>Notă: {p.note}</div>}
        </div>
      )}
    </div>
  )
}

const PREVIEW_FETCHERS = {
  profile: (id: number) => profileApi.getInvoicePreview(id),   // /profile/api, by jarvis invoice id (ownership-scoped)
  efactura: (id: number) => efacturaApi.getInvoicePreview(id), // /efactura/api, by e-Factura PK (efactura access)
  invoices: (id: number) => invoicesApi.getInvoicePreview(id), // /api/db/invoices, by jarvis invoice id (accounting scope)
} as const

// Sources that expose an official ANAF-rendered PDF endpoint. Others (profile)
// only get the client-side fallback. A "Descarcă PDF" button shows for any
// source listed here.
const PDF_URL_BUILDERS: Partial<Record<keyof typeof PREVIEW_FETCHERS, (id: number) => string>> = {
  efactura: (id) => efacturaApi.getInvoicePdfUrl(id),
  invoices: (id) => invoicesApi.getInvoicePdfUrl(id),
}

export function InvoicePreviewModal({ invoiceId, onClose, source = 'profile' }: {
  invoiceId: number
  onClose: () => void
  source?: keyof typeof PREVIEW_FETCHERS
}) {
  const [downloading, setDownloading] = useState(false)

  const { data, isLoading, isError } = useQuery({
    queryKey: [source, 'invoice-preview', invoiceId],
    queryFn: () => PREVIEW_FETCHERS[source](invoiceId),
  })

  // Try the official ANAF-rendered PDF first (for sources that expose one); if
  // it's unavailable (no live ANAF connection, error, non-PDF response) fall
  // back to a client-side PDF built from the preview data already loaded here.
  const handleDownloadPdf = async () => {
    if (!data) return
    setDownloading(true)
    try {
      const pdfUrl = PDF_URL_BUILDERS[source]?.(invoiceId)
      if (pdfUrl) {
        try {
          const res = await fetch(pdfUrl)
          const ct = res.headers.get('Content-Type') || ''
          if (res.ok && ct.includes('pdf')) {
            const blob = await res.blob()
            const filename =
              res.headers.get('Content-Disposition')?.match(/filename="?([^";\n]+)"?/)?.[1] ||
              `factura-${data.invoice_number || invoiceId}.pdf`
            const a = document.createElement('a')
            a.href = URL.createObjectURL(blob)
            a.download = filename
            document.body.appendChild(a)
            a.click()
            URL.revokeObjectURL(a.href)
            a.remove()
            return
          }
        } catch {
          /* fall through to client-side generation */
        }
      }
      const { buildInvoicePreviewPdf } = await import('./buildInvoicePreviewPdf')
      buildInvoicePreviewPdf(data)
    } finally {
      setDownloading(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="max-h-[85vh] w-[95vw] max-w-[1120px] overflow-y-auto sm:max-w-[1120px]">
        <DialogHeader>
          <div className="flex items-center justify-between gap-2 pr-8">
            <DialogTitle>
              Previzualizare factură{data?.invoice_number ? ` #${data.invoice_number}` : ''}
            </DialogTitle>
            {data && PDF_URL_BUILDERS[source] && (
              <Button
                variant="outline"
                size="sm"
                className="shrink-0 gap-1.5"
                onClick={handleDownloadPdf}
                disabled={downloading}
              >
                {downloading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Download className="h-4 w-4" />
                )}
                Descarcă PDF
              </Button>
            )}
          </div>
        </DialogHeader>

        {isLoading && (
          <div className="space-y-3">
            <Skeleton className="h-6 w-1/2" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        )}
        {isError && (
          <p className="py-6 text-center text-sm text-destructive">
            Nu s-a putut încărca conținutul facturii.
          </p>
        )}
        {data && <PreviewBody p={data} />}
      </DialogContent>
    </Dialog>
  )
}
