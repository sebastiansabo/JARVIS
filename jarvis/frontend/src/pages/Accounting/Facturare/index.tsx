import React, { useState, useEffect, useCallback } from 'react'
import { toast } from 'sonner'
import { Loader2, Save } from 'lucide-react'

import { PageHeader } from '@/components/shared/PageHeader'
import ComenziTab from './ComenziTab'
import DocumentItemsTab from './DocumentItemsTab'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

// ── Shared types ──────────────────────────────────────────────

interface Company {
  id: number
  company: string
  vat: string | null
}

// ── Konto Settings Tab ──────────────────────────────────────────

const INVOICE_TYPES = [
  { key: 'INVOICE', label: 'Advance', fields: ['konto_debit', 'konto_credit', 'centru_gestiune'] as const },
  { key: 'STORNO', label: 'Storno', fields: ['konto_debit', 'konto_credit', 'centru_gestiune'] as const },
  { key: 'FINAL', label: 'Final', fields: ['konto_debit', 'konto_credit', 'centru_gestiune'] as const },
] as const

const FIELD_LABELS: Record<string, string> = {
  konto_debit: 'Konto Debit',
  konto_credit: 'Konto Credit',
  centru_gestiune: 'Centru Gest.',
}

interface KontoEntry {
  konto_debit: string
  konto_credit: string
  centru_gestiune: string
}

type KontoMatrix = Record<string, Record<string, KontoEntry>> // supplier_id -> invoice_type -> entry

function KontoSettingsTab({ companies }: { companies: Company[] }) {
  const [matrix, setMatrix] = useState<KontoMatrix>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    fetch('/facturare/api/konto-config')
      .then(r => r.ok ? r.json() : { configs: [] })
      .then(data => {
        const m: KontoMatrix = {}
        for (const c of companies) {
          m[String(c.id)] = {}
          for (const t of INVOICE_TYPES) {
            m[String(c.id)][t.key] = { konto_debit: '', konto_credit: '', centru_gestiune: '' }
          }
        }
        for (const cfg of data.configs || []) {
          const sid = String(cfg.supplier_id)
          if (m[sid]) {
            m[sid][cfg.invoice_type] = {
              konto_debit: cfg.konto_debit || '',
              konto_credit: cfg.konto_credit || '',
              centru_gestiune: cfg.centru_gestiune || '',
            }
          }
        }
        setMatrix(m)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [companies])

  useEffect(() => { if (companies.length > 0) load() }, [load, companies])

  const update = (supplierId: string, invoiceType: string, field: keyof KontoEntry, value: string) => {
    setMatrix(prev => ({
      ...prev,
      [supplierId]: {
        ...prev[supplierId],
        [invoiceType]: { ...prev[supplierId]?.[invoiceType], [field]: value },
      },
    }))
  }

  const save = async () => {
    setSaving(true)
    const items: { supplier_id: number; invoice_type: string; konto_debit: string; konto_credit: string; centru_gestiune: string }[] = []
    for (const [sid, types] of Object.entries(matrix)) {
      for (const [type, entry] of Object.entries(types)) {
        if (entry.konto_debit || entry.konto_credit || entry.centru_gestiune) {
          items.push({ supplier_id: parseInt(sid), invoice_type: type, ...entry })
        }
      }
    }
    try {
      const res = await fetch('/facturare/api/konto-config', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items }),
      })
      if (!res.ok) throw new Error('Failed to save')
      toast.success(`Saved ${items.length} configs`)
    } catch (err: any) { toast.error(err.message) }
    finally { setSaving(false) }
  }

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin" /></div>

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-muted-foreground">Konto Debit, Konto Credit & Centru Intern Gestiune per Supplier × Invoice Type</h3>
        <Button onClick={save} disabled={saving} size="sm">
          {saving ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Save className="h-4 w-4 mr-1" />} Save
        </Button>
      </div>

      <Card>
        <CardContent className="p-0 overflow-x-auto">
          <table className="w-full text-xs min-w-[700px]">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="text-left px-3 py-2 font-medium w-[180px]">Supplier</th>
                {INVOICE_TYPES.map(t => (
                  <th key={t.key} className="text-center px-1 py-2 font-medium" colSpan={t.fields.length}>
                    <span className="text-xs">{t.label}</span>
                  </th>
                ))}
              </tr>
              <tr className="border-b bg-muted/30">
                <th></th>
                {INVOICE_TYPES.map(t => (
                  <React.Fragment key={t.key}>
                    {t.fields.map(f => (
                      <th key={f} className="px-1 py-1 text-center text-[10px] text-muted-foreground font-normal">{FIELD_LABELS[f]}</th>
                    ))}
                  </React.Fragment>
                ))}
              </tr>
            </thead>
            <tbody>
              {companies.map(c => (
                <tr key={c.id} className="border-b hover:bg-muted/20">
                  <td className="px-3 py-1.5 font-medium text-xs whitespace-nowrap">{c.company}</td>
                  {INVOICE_TYPES.map(t => {
                    const entry = matrix[String(c.id)]?.[t.key] || { konto_debit: '', konto_credit: '', centru_gestiune: '' }
                    return (
                      <React.Fragment key={t.key}>
                        {t.fields.map(f => (
                          <td key={f} className="px-0.5 py-1">
                            <Input className={`h-7 text-xs text-center ${f === 'centru_gestiune' ? 'w-16' : 'w-20'}`}
                              value={entry[f]} onChange={e => update(String(c.id), t.key, f, e.target.value)} />
                          </td>
                        ))}
                      </React.Fragment>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  )
}

// ── Main Page ────────────────────────────────────────────────

export default function Facturare() {
  const [companies, setCompanies] = useState<Company[]>([])

  useEffect(() => {
    fetch('/api/companies-vat')
      .then(r => r.ok ? r.json() : [])
      .then(data => setCompanies(Array.isArray(data) ? data : []))
      .catch(() => {})
  }, [])

  return (
    <div className="space-y-6">
      <Tabs defaultValue={new URLSearchParams(window.location.search).get('tab') || 'comenzi'} className="w-full"
        onValueChange={(v) => {
          const url = new URL(window.location.href)
          url.searchParams.set('tab', v)
          window.history.replaceState({}, '', url.toString())
        }}>
        <div className="flex items-center justify-between">
          <PageHeader
            title="Comenzi Externe"
            description="Manage contracts, anexas, and invoices"
          />
          <TabsList>
            <TabsTrigger value="comenzi">Comenzi</TabsTrigger>
            <TabsTrigger value="invoices">Invoices</TabsTrigger>
            <TabsTrigger value="archive">Archive</TabsTrigger>
            <TabsTrigger value="settings">Settings</TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="comenzi" className="mt-4">
          <ComenziTab companies={companies} />
        </TabsContent>
        <TabsContent value="invoices" className="mt-4">
          <DocumentItemsTab docType="PROFORMA,INVOICE,STORNO,FINAL" />
        </TabsContent>
        <TabsContent value="archive" className="mt-4">
          <DocumentItemsTab docType="PROFORMA,INVOICE,STORNO,FINAL" archived />
        </TabsContent>
        <TabsContent value="settings" className="mt-4">
          <KontoSettingsTab companies={companies} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
