import jsPDF from 'jspdf'
import type { InvoicePreview } from '@/api/profile'

// Client-side PDF generator used as the fallback when the official ANAF
// XML→PDF render is unavailable. Draws a vector layout that mirrors the
// InvoicePreviewModal so the download always matches what the user previewed.

const MARGIN = 15
const PAGE_W = 210 // A4 mm
const PAGE_H = 297
const CONTENT_W = PAGE_W - MARGIN * 2
const RIGHT = PAGE_W - MARGIN

// jsPDF's built-in helvetica uses WinAnsi encoding, which lacks the Romanian
// ă/ș/ț glyphs. Transliterate to ASCII so the fallback never shows broken
// boxes; the primary ANAF PDF keeps full diacritics.
const DIACRITICS: Record<string, string> = {
  ă: 'a', â: 'a', î: 'i', ș: 's', ş: 's', ț: 't', ţ: 't',
  Ă: 'A', Â: 'A', Î: 'I', Ș: 'S', Ş: 'S', Ț: 'T', Ţ: 'T',
}
function ascii(s: unknown): string {
  return String(s ?? '').replace(/[ăâîșşțţĂÂÎȘŞȚŢ]/g, (c) => DIACRITICS[c] ?? c)
}

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

// Article table columns (widths sum to CONTENT_W = 180mm)
const COLS = [
  { key: '#', w: 8, align: 'left' as const },
  { key: 'Descriere', w: 74, align: 'left' as const },
  { key: 'Cant.', w: 18, align: 'right' as const },
  { key: 'U.M.', w: 16, align: 'left' as const },
  { key: 'Pret unitar', w: 24, align: 'right' as const },
  { key: 'Valoare', w: 24, align: 'right' as const },
  { key: 'TVA %', w: 16, align: 'right' as const },
]

export function buildInvoicePreviewPdf(p: InvoicePreview): void {
  const doc = new jsPDF()
  const cur = p.currency || 'RON'
  let y = MARGIN

  function checkPage(needed: number) {
    if (y + needed > PAGE_H - MARGIN) {
      doc.addPage()
      y = MARGIN
    }
  }

  function text(s: string, x: number, ty: number, align: 'left' | 'right' = 'left') {
    doc.text(ascii(s), x, ty, { align })
  }

  // ── Title ──────────────────────────────────────────────
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(15)
  doc.setTextColor(20)
  text(`Factura ${p.invoice_series ? p.invoice_series + ' ' : ''}${p.invoice_number || ''}`.trim(), MARGIN, y)
  y += 8
  doc.setDrawColor(210)
  doc.line(MARGIN, y, RIGHT, y)
  y += 6

  // ── Header fields (serie / numar / data / scadenta) ────
  const fields = [
    ['Serie', p.invoice_series || '-'],
    ['Numar', p.invoice_number || '-'],
    ['Data emiterii', fmtDate(p.issue_date)],
    ['Scadenta', fmtDate(p.due_date)],
  ]
  const fw = CONTENT_W / 4
  fields.forEach(([label, value], i) => {
    const x = MARGIN + fw * i
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(7)
    doc.setTextColor(130)
    text(label.toUpperCase(), x, y)
    doc.setFont('helvetica', 'bold')
    doc.setFontSize(9)
    doc.setTextColor(30)
    text(value, x, y + 5)
  })
  y += 12

  // ── Parties (furnizor / client) ────────────────────────
  const boxGap = 6
  const boxW = (CONTENT_W - boxGap) / 2
  const partyStartY = y
  const seller = drawParty(doc, MARGIN, y, boxW, 'Furnizor', p.seller.name, [
    p.seller.cif && `CIF: ${p.seller.cif}`,
    p.seller.reg_number && `Nr. reg.: ${p.seller.reg_number}`,
    p.seller.address,
  ])
  const buyer = drawParty(doc, MARGIN + boxW + boxGap, y, boxW, 'Client', p.buyer.name, [
    p.buyer.cif && `CIF: ${p.buyer.cif}`,
    p.buyer.address,
  ])
  y = Math.max(seller, buyer)
  // draw the two party borders now that heights are known
  doc.setDrawColor(220)
  doc.roundedRect(MARGIN, partyStartY, boxW, y - partyStartY, 1.5, 1.5)
  doc.roundedRect(MARGIN + boxW + boxGap, partyStartY, boxW, y - partyStartY, 1.5, 1.5)
  y += 8

  // ── Articole table ─────────────────────────────────────
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(8)
  doc.setTextColor(110)
  text('ARTICOLE', MARGIN, y)
  y += 4

  // header row
  checkPage(10)
  doc.setFillColor(244, 245, 247)
  doc.rect(MARGIN, y, CONTENT_W, 7, 'F')
  doc.setFontSize(7.5)
  doc.setTextColor(90)
  let cx = MARGIN
  COLS.forEach((c) => {
    const tx = c.align === 'right' ? cx + c.w - 2 : cx + 2
    text(c.key, tx, y + 4.7, c.align)
    cx += c.w
  })
  y += 7

  doc.setFont('helvetica', 'normal')
  doc.setTextColor(35)
  if (p.line_items.length === 0) {
    doc.setFontSize(8)
    doc.setTextColor(140)
    text('Fara articole detaliate in XML', MARGIN + CONTENT_W / 2, y + 5, 'left')
    y += 9
  } else {
    p.line_items.forEach((li) => {
      const descLines = doc.splitTextToSize(ascii(li.description), COLS[1].w - 4) as string[]
      const rowH = Math.max(descLines.length * 4 + 3, 7)
      checkPage(rowH)
      const cells = [
        String(li.line_number),
        '', // description drawn separately (multi-line)
        Number(li.quantity).toLocaleString('ro-RO'),
        li.unit || '',
        money(li.unit_price, cur),
        money(li.line_amount, cur),
        `${Number(li.vat_rate)}%`,
      ]
      let colX = MARGIN
      doc.setFontSize(8)
      doc.setTextColor(35)
      COLS.forEach((c, i) => {
        if (i === 1) {
          doc.text(descLines, colX + 2, y + 4.5)
        } else {
          const tx = c.align === 'right' ? colX + c.w - 2 : colX + 2
          text(cells[i], tx, y + 4.5, c.align)
        }
        colX += c.w
      })
      y += rowH
      doc.setDrawColor(232)
      doc.line(MARGIN, y, RIGHT, y)
    })
  }
  y += 8

  // ── Defalcare TVA + Totals (two columns) ───────────────
  checkPage(34)
  const colW = (CONTENT_W - boxGap) / 2
  const blockTop = y

  // left: VAT breakdown
  if (p.vat_breakdown.length > 0) {
    doc.setFont('helvetica', 'bold')
    doc.setFontSize(7)
    doc.setTextColor(110)
    text('DEFALCARE TVA', MARGIN + 3, y + 5)
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(7.5)
    doc.setTextColor(60)
    let ly = y + 11
    // Both amounts are right-aligned (grow leftward) so a long value never
    // runs into the next column — the left-aligned bug this replaces.
    p.vat_breakdown.forEach((b) => {
      text(`Cota ${Number(b.rate)}%`, MARGIN + 3, ly)
      text(`baza ${money(b.taxable, cur)}`, MARGIN + colW - 30, ly, 'right')
      text(`TVA ${money(b.amount, cur)}`, MARGIN + colW - 3, ly, 'right')
      ly += 5
    })
    doc.setDrawColor(220)
    doc.roundedRect(MARGIN, blockTop, colW, ly - blockTop + 1, 1.5, 1.5)
  }

  // right: totals
  const tX = MARGIN + colW + boxGap
  let ty = y + 6
  const totRows: [string, string, boolean][] = [
    ['Total fara TVA', money(p.totals.without_vat, cur), false],
    ['TVA', money(p.totals.vat, cur), false],
    ['Total', money(p.totals.total, cur), true],
  ]
  totRows.forEach(([label, value, strong]) => {
    if (strong) {
      doc.setDrawColor(220)
      doc.line(tX + 3, ty - 3, tX + colW - 3, ty - 3)
      doc.setFont('helvetica', 'bold')
      doc.setFontSize(10)
      doc.setTextColor(20)
    } else {
      doc.setFont('helvetica', 'normal')
      doc.setFontSize(9)
      doc.setTextColor(90)
    }
    text(label, tX + 3, ty)
    doc.setTextColor(strong ? 20 : 40)
    text(value, tX + colW - 3, ty, 'right')
    ty += strong ? 7 : 6
  })
  doc.setDrawColor(220)
  doc.roundedRect(tX, blockTop, colW, ty - blockTop, 1.5, 1.5)
  y = Math.max(y, ty) + 8

  // ── Payment / IBAN / note ──────────────────────────────
  const notes = [
    p.payment.bank_account && `IBAN: ${p.payment.bank_account}`,
    p.payment.terms && `Termeni de plata: ${p.payment.terms}`,
    p.note && `Nota: ${p.note}`,
  ].filter(Boolean) as string[]
  if (notes.length > 0) {
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(7.5)
    doc.setTextColor(110)
    notes.forEach((n) => {
      const lines = doc.splitTextToSize(ascii(n), CONTENT_W - 6) as string[]
      checkPage(lines.length * 4 + 3)
      doc.text(lines, MARGIN + 3, y + 4)
      y += lines.length * 4 + 2
    })
  }

  const safeNum = (p.invoice_number || 'factura').replace(/[^\w.-]+/g, '_')
  doc.save(`factura-${safeNum}.pdf`)
}

// Draws party text and returns the y coordinate where the box ends.
function drawParty(
  doc: jsPDF,
  x: number,
  top: number,
  w: number,
  title: string,
  name: string,
  lines: (string | null | undefined | false)[],
): number {
  let y = top + 5
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(7)
  doc.setTextColor(120)
  doc.text(ascii(title.toUpperCase()), x + 3, y)
  y += 5
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(9)
  doc.setTextColor(30)
  const nameLines = doc.splitTextToSize(ascii(name || '-'), w - 6) as string[]
  doc.text(nameLines, x + 3, y)
  y += nameLines.length * 4.5
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(7.5)
  doc.setTextColor(110)
  lines.filter(Boolean).forEach((ln) => {
    const wrapped = doc.splitTextToSize(ascii(ln as string), w - 6) as string[]
    doc.text(wrapped, x + 3, y + 1)
    y += wrapped.length * 4 + 0.5
  })
  return y + 3
}
