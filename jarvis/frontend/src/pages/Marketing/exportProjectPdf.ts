import jsPDF from 'jspdf'
import type { MktProject } from '@/types/marketing'
import { marketingApi } from '@/api/marketing'

const MARGIN = 20
const PAGE_WIDTH = 210 // A4 mm
const CONTENT_WIDTH = PAGE_WIDTH - MARGIN * 2
const LINE_HEIGHT = 6
const SECTION_GAP = 10

function stripHtml(html: string): string {
  const div = document.createElement('div')
  div.innerHTML = html
  return div.textContent || div.innerText || ''
}

function fmtDate(d: string | null | undefined): string {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}

function fmtCurrency(val: number | string | null | undefined, currency = 'RON'): string {
  const num = typeof val === 'string' ? parseFloat(val) : (val ?? 0)
  return `${num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`
}

export async function exportProjectPdf(project: MktProject) {
  const doc = new jsPDF()
  let y = MARGIN

  function checkPage(needed = 20) {
    if (y + needed > 280) {
      doc.addPage()
      y = MARGIN
    }
  }

  function heading(text: string) {
    checkPage(16)
    doc.setFontSize(14)
    doc.setFont('helvetica', 'bold')
    doc.text(text, MARGIN, y)
    y += 8
    doc.setDrawColor(200)
    doc.line(MARGIN, y, PAGE_WIDTH - MARGIN, y)
    y += 4
  }

  function label(key: string, value: string) {
    checkPage()
    doc.setFontSize(9)
    doc.setFont('helvetica', 'bold')
    doc.text(`${key}:`, MARGIN, y)
    doc.setFont('helvetica', 'normal')
    const lines = doc.splitTextToSize(value, CONTENT_WIDTH - 35)
    doc.text(lines, MARGIN + 35, y)
    y += Math.max(lines.length * LINE_HEIGHT, LINE_HEIGHT)
  }

  function paragraph(text: string) {
    checkPage()
    doc.setFontSize(9)
    doc.setFont('helvetica', 'normal')
    const lines = doc.splitTextToSize(text, CONTENT_WIDTH)
    for (const line of lines) {
      checkPage(LINE_HEIGHT)
      doc.text(line, MARGIN, y)
      y += LINE_HEIGHT
    }
  }

  // ── Title ──
  doc.setFontSize(20)
  doc.setFont('helvetica', 'bold')
  const titleLines = doc.splitTextToSize(project.name, CONTENT_WIDTH)
  doc.text(titleLines, MARGIN, y)
  y += titleLines.length * 9 + 2

  doc.setFontSize(10)
  doc.setFont('helvetica', 'normal')
  doc.setTextColor(100)
  doc.text(`Exported ${new Date().toLocaleDateString('en-GB')} — JARVIS Marketing`, MARGIN, y)
  doc.setTextColor(0)
  y += SECTION_GAP

  // ── Project Info ──
  heading('Project Information')
  label('Status', (project.status ?? '').replace('_', ' '))
  label('Type', (project.project_type ?? '').replace('_', ' '))
  label('Company', project.company_name ?? '—')
  if (project.brand_name) label('Brand', project.brand_name)
  label('Owner', project.owner_name ?? '—')
  label('Start Date', fmtDate(project.start_date))
  label('End Date', fmtDate(project.end_date))
  if (project.external_ref) label('External Ref', project.external_ref)
  y += SECTION_GAP / 2

  // ── Budget ──
  heading('Budget')
  const budget = typeof project.total_budget === 'string' ? parseFloat(project.total_budget) : (project.total_budget ?? 0)
  const spent = typeof project.total_spent === 'string' ? parseFloat(project.total_spent) : (project.total_spent ?? 0)
  label('Total Budget', fmtCurrency(budget, project.currency))
  label('Total Spent', fmtCurrency(spent, project.currency))
  label('Utilization', budget ? `${Math.round((spent / budget) * 100)}%` : '—')

  // Fetch budget lines
  try {
    const budgetData = await marketingApi.getBudgetLines(project.id)
    const lines = budgetData?.budget_lines ?? []
    if (lines.length > 0) {
      y += 4
      doc.setFontSize(9)
      doc.setFont('helvetica', 'bold')
      doc.text('Channel', MARGIN, y)
      doc.text('Planned', MARGIN + 50, y)
      doc.text('Spent', MARGIN + 85, y)
      doc.text('Remaining', MARGIN + 120, y)
      y += LINE_HEIGHT
      doc.setFont('helvetica', 'normal')
      for (const bl of lines) {
        checkPage()
        const planned = typeof bl.planned_amount === 'string' ? parseFloat(bl.planned_amount) : (bl.planned_amount ?? 0)
        const blSpent = typeof bl.spent_amount === 'string' ? parseFloat(bl.spent_amount) : (bl.spent_amount ?? 0)
        doc.text(bl.channel ?? '—', MARGIN, y)
        doc.text(fmtCurrency(planned, project.currency), MARGIN + 50, y)
        doc.text(fmtCurrency(blSpent, project.currency), MARGIN + 85, y)
        doc.text(fmtCurrency(planned - blSpent, project.currency), MARGIN + 120, y)
        y += LINE_HEIGHT
      }
    }
  } catch { /* skip if budget lines unavailable */ }
  y += SECTION_GAP / 2

  // ── Description ──
  if (project.description) {
    heading('Description')
    paragraph(stripHtml(project.description))
    y += SECTION_GAP / 2
  }

  // ── Objective ──
  if (project.objective) {
    heading('Objective')
    paragraph(project.objective)
    y += SECTION_GAP / 2
  }

  // ── Target Audience ──
  if (project.target_audience) {
    heading('Target Audience')
    paragraph(project.target_audience)
    y += SECTION_GAP / 2
  }

  // ── Channel Mix ──
  if (project.channel_mix?.length > 0) {
    heading('Channel Mix')
    paragraph(project.channel_mix.map((c) => c.replace('_', ' ')).join(', '))
    y += SECTION_GAP / 2
  }

  // ── KPIs ──
  try {
    const kpiData = await marketingApi.getProjectKpis(project.id)
    const kpis = kpiData?.kpis ?? []
    if (kpis.length > 0) {
      heading('KPIs')
      doc.setFontSize(9)
      doc.setFont('helvetica', 'bold')
      doc.text('KPI', MARGIN, y)
      doc.text('Target', MARGIN + 60, y)
      doc.text('Current', MARGIN + 95, y)
      doc.text('Progress', MARGIN + 130, y)
      y += LINE_HEIGHT
      doc.setFont('helvetica', 'normal')
      for (const kpi of kpis) {
        checkPage()
        const target = typeof kpi.target_value === 'string' ? parseFloat(kpi.target_value) : (kpi.target_value ?? 0)
        const current = typeof kpi.current_value === 'string' ? parseFloat(kpi.current_value) : (kpi.current_value ?? 0)
        const progress = target ? Math.round((current / target) * 100) : 0
        doc.text(kpi.kpi_name ?? '—', MARGIN, y)
        doc.text(String(target), MARGIN + 60, y)
        doc.text(String(current), MARGIN + 95, y)
        doc.text(`${progress}%`, MARGIN + 130, y)
        y += LINE_HEIGHT
      }
      y += SECTION_GAP / 2
    }
  } catch { /* skip */ }

  // ── Team ──
  try {
    const teamData = await marketingApi.getMembers(project.id)
    const members = teamData?.members ?? []
    if (members.length > 0) {
      heading('Team')
      for (const m of members) {
        checkPage()
        label(m.role ?? 'member', m.user_name ?? `User #${m.user_id}`)
      }
      y += SECTION_GAP / 2
    }
  } catch { /* skip */ }

  // ── Save ──
  const slug = project.slug || project.name.toLowerCase().replace(/\s+/g, '-').slice(0, 30)
  doc.save(`${slug}-project-report.pdf`)
}
