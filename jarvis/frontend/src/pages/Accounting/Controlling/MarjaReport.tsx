import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Download } from 'lucide-react'

import { controllingApi } from '@/api/controlling'
import type { MarjaSection } from '@/types/controlling'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useState } from 'react'

const MONTH_NAMES = ['', 'Ianuarie', 'Februarie', 'Martie', 'Aprilie', 'Mai', 'Iunie',
  'Iulie', 'August', 'Septembrie', 'Octombrie', 'Noiembrie', 'Decembrie']

export default function MarjaReport() {
  const { uploadId } = useParams<{ uploadId: string }>()
  const navigate = useNavigate()
  const [showEur, setShowEur] = useState(false)

  const { data, isLoading, error } = useQuery({
    queryKey: ['bab-report', uploadId],
    queryFn: () => controllingApi.getReport(Number(uploadId)),
    enabled: !!uploadId,
  })

  if (isLoading) return <div className="p-6 text-center text-muted-foreground">Se încarcă raportul...</div>
  if (error) return <div className="p-6 text-center text-red-500">Eroare: {(error as Error).message}</div>

  const report = data?.report
  const upload = data?.upload
  if (!report || !upload) return <div className="p-6 text-center text-muted-foreground">Raport negăsit</div>

  const monthName = MONTH_NAMES[upload.period_month] || ''

  const handleExport = () => {
    window.open(controllingApi.exportReport(Number(uploadId)), '_blank')
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => navigate('/app/accounting/controlling')}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-xl font-semibold">Raport Marjă Vânzări</h1>
            <p className="text-sm text-muted-foreground">
              {monthName} {upload.period_year} &middot; Curs: {report.eur_rate} LEI/EUR
              {upload.locked_at && <span className="ml-2 text-blue-600 font-medium">🔒 BLOCAT</span>}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowEur(!showEur)}
          >
            {showEur ? 'EUR → LEI' : 'LEI → EUR'}
          </Button>
          <Button variant="outline" size="sm" onClick={handleExport}>
            <Download className="h-4 w-4 mr-1" /> Export XLSX
          </Button>
        </div>
      </div>

      {/* Report Table */}
      <Card>
        <CardHeader className="py-3 px-4 bg-[#1B2A4A] rounded-t-lg">
          <CardTitle className="text-white text-sm font-medium flex justify-between">
            <span>Indicator</span>
            <span>{showEur ? 'EUR' : 'LEI'}</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <TooltipProvider>
            <table className="w-full text-sm">
              <tbody>
                {report.sections.map((section: MarjaSection) => (
                  <SectionBlock key={section.section} section={section} showEur={showEur} />
                ))}
              </tbody>
            </table>
          </TooltipProvider>
        </CardContent>
      </Card>

      {/* Summary */}
      <div className="mt-4 grid grid-cols-2 gap-4">
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-xs text-muted-foreground mb-1">MARJA FINALĂ (LEI)</div>
            <div className={`text-2xl font-bold ${report.marja_finala_lei < 0 ? 'text-red-600' : ''}`}>
              {formatNumber(report.marja_finala_lei)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-xs text-muted-foreground mb-1">MARJA FINALĂ (EUR)</div>
            <div className={`text-2xl font-bold ${report.marja_finala_eur < 0 ? 'text-red-600' : ''}`}>
              {formatNumber(report.marja_finala_eur)}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}


function SectionBlock({ section, showEur }: { section: MarjaSection; showEur: boolean }) {
  const isMarjaFinala = section.section.includes('MARJA FINALĂ')

  return (
    <>
      {/* Section header */}
      <tr className={isMarjaFinala ? 'bg-[#1B2A4A]' : 'bg-gray-100'}>
        <td colSpan={2} className={`px-4 py-2 font-semibold text-xs ${isMarjaFinala ? 'text-white' : 'text-gray-700'}`}>
          {section.section}
        </td>
      </tr>
      {/* Rows */}
      {section.rows.map((row) => {
        const isMainMarja = row.label === 'MARJA FINALĂ'
        const value = showEur ? row.eur : row.lei
        const isNegative = value < 0

        return (
          <Tooltip key={row.label + row.kst}>
            <TooltipTrigger asChild>
              <tr className={`border-b border-gray-100 hover:bg-gray-50 cursor-default ${isMainMarja ? 'bg-[#1B2A4A]' : ''}`}>
                <td className={`px-4 py-2 ${isMainMarja ? 'text-white font-bold' : 'pl-8 text-gray-700'}`}>
                  {row.label}
                </td>
                <td className={`px-4 py-2 text-right font-mono tabular-nums ${
                  isMainMarja ? 'text-white font-bold'
                    : isNegative ? 'text-red-600'
                    : 'text-gray-900'
                }`}>
                  {formatNumber(value)}
                </td>
              </tr>
            </TooltipTrigger>
            {row.accounts.length > 0 && (
              <TooltipContent>
                <p className="text-xs">Conturi: {row.accounts.join(', ')} | KST {row.kst}</p>
              </TooltipContent>
            )}
          </Tooltip>
        )
      })}
    </>
  )
}


function formatNumber(value: number): string {
  return new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)
}
