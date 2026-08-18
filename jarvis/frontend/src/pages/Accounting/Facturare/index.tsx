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
  eurofib_klient_id: number | null
}

// ── Konto Settings Tab ──────────────────────────────────────────

const INVOICE_TYPES = [
  { key: 'INVOICE', label: 'Advance', fields: ['konto_credit', 'centru_gestiune', 'text_template'] as const },
  { key: 'STORNO', label: 'Storno', fields: ['konto_credit', 'centru_gestiune', 'text_template'] as const },
  { key: 'FINAL', label: 'Final', fields: ['konto_credit', 'centru_gestiune', 'text_template'] as const },
] as const

const FIELD_LABELS: Record<string, string> = {
  konto_credit: 'Konto Credit',
  centru_gestiune: 'Centru Gest.',
  text_template: 'Text Template',
}

interface KontoEntry {
  konto_credit: string
  centru_gestiune: string
  text_template: string
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
            m[String(c.id)][t.key] = { konto_credit: '', centru_gestiune: '', text_template: '' }
          }
        }
        for (const cfg of data.configs || []) {
          const sid = String(cfg.supplier_id)
          if (m[sid]) {
            m[sid][cfg.invoice_type] = {
              konto_credit: cfg.konto_credit || '',
              centru_gestiune: cfg.centru_gestiune || '',
              text_template: cfg.text_template || '',
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
    const items: { supplier_id: number; invoice_type: string; konto_credit: string; centru_gestiune: string; text_template: string }[] = []
    for (const [sid, types] of Object.entries(matrix)) {
      for (const [type, entry] of Object.entries(types)) {
        if (entry.konto_credit || entry.centru_gestiune) {
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
                    const entry = matrix[String(c.id)]?.[t.key] || { konto_credit: '', centru_gestiune: '', text_template: '' }
                    return (
                      <React.Fragment key={t.key}>
                        {t.fields.map(f => (
                          <td key={f} className="px-0.5 py-1">
                            <Input className={`h-7 text-xs text-center ${f === 'text_template' ? 'w-32' : f === 'centru_gestiune' ? 'w-16' : 'w-20'}`}
                              value={entry[f]} onChange={e => update(String(c.id), t.key, f, e.target.value)}
                              placeholder={f === 'text_template' ? (t.key === 'INVOICE' ? 'avans {model} {comanda}' : t.key === 'STORNO' ? 'storno avans {model} {comanda}' : '{model} {comanda}') : undefined} />
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

// ── Venituri Rules Section ─────────────────────────────────────

interface VenituriRule {
  id?: number
  supplier_id: string
  comanda_prefix: string
  konto_venituri: string
  kostenstelle: string
}

function VenituriRulesSection({ companies }: { companies: Company[] }) {
  const [rules, setRules] = useState<VenituriRule[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    fetch('/facturare/api/venituri-rules')
      .then(r => r.ok ? r.json() : { rules: [] })
      .then(data => {
        setRules((data.rules || []).map((r: any) => ({
          id: r.id, supplier_id: String(r.supplier_id),
          comanda_prefix: r.comanda_prefix, konto_venituri: r.konto_venituri,
          kostenstelle: r.kostenstelle,
        })))
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const updateRule = (idx: number, field: keyof VenituriRule, value: string) => {
    setRules(prev => prev.map((r, i) => i === idx ? { ...r, [field]: value } : r))
  }

  const addRule = () => {
    setRules(prev => [...prev, { supplier_id: '', comanda_prefix: '', konto_venituri: '', kostenstelle: '' }])
  }

  const removeRule = async (idx: number) => {
    const rule = rules[idx]
    if (rule.id) {
      await fetch(`/facturare/api/venituri-rules/${rule.id}`, { method: 'DELETE' })
    }
    setRules(prev => prev.filter((_, i) => i !== idx))
  }

  const save = async () => {
    setSaving(true)
    const items = rules.filter(r => r.supplier_id && r.comanda_prefix && r.konto_venituri && r.kostenstelle)
      .map(r => ({ supplier_id: parseInt(r.supplier_id), comanda_prefix: r.comanda_prefix, konto_venituri: r.konto_venituri, kostenstelle: r.kostenstelle }))
    try {
      const res = await fetch('/facturare/api/venituri-rules', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items }),
      })
      if (!res.ok) throw new Error('Failed to save')
      toast.success(`Saved ${items.length} rules`)
      load()
    } catch (err: any) { toast.error(err.message) }
    finally { setSaving(false) }
  }

  if (loading) return <div className="flex justify-center py-6"><Loader2 className="h-5 w-5 animate-spin" /></div>

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-muted-foreground">Reguli Venituri — Facturi Finale (supplier × prefix nr comandă → cont + kostenstelle)</h3>
        <div className="flex gap-2">
          <Button onClick={addRule} size="sm" variant="outline">+ Add Rule</Button>
          <Button onClick={save} disabled={saving} size="sm">
            {saving ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Save className="h-4 w-4 mr-1" />} Save
          </Button>
        </div>
      </div>
      <Card>
        <CardContent className="p-0">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="text-left px-3 py-2 font-medium">Supplier</th>
                <th className="text-left px-3 py-2 font-medium">Prefix Comandă</th>
                <th className="text-left px-3 py-2 font-medium">Cont Venituri</th>
                <th className="text-left px-3 py-2 font-medium">Kostenstelle</th>
                <th className="px-2 py-2 w-8"></th>
              </tr>
            </thead>
            <tbody>
              {rules.map((rule, idx) => (
                <tr key={idx} className="border-b hover:bg-muted/20">
                  <td className="px-2 py-1">
                    <select className="h-7 text-xs border rounded px-1 w-full" value={rule.supplier_id}
                      onChange={e => updateRule(idx, 'supplier_id', e.target.value)}>
                      <option value="">Select</option>
                      {companies.map(c => <option key={c.id} value={String(c.id)}>{c.company}</option>)}
                    </select>
                  </td>
                  <td className="px-2 py-1"><Input className="h-7 text-xs w-16" value={rule.comanda_prefix} placeholder="5, 3, *"
                    onChange={e => updateRule(idx, 'comanda_prefix', e.target.value)} /></td>
                  <td className="px-2 py-1"><Input className="h-7 text-xs w-20" value={rule.konto_venituri}
                    onChange={e => updateRule(idx, 'konto_venituri', e.target.value)} /></td>
                  <td className="px-2 py-1"><Input className="h-7 text-xs w-20" value={rule.kostenstelle}
                    onChange={e => updateRule(idx, 'kostenstelle', e.target.value)} /></td>
                  <td className="px-2 py-1">
                    <button onClick={() => removeRule(idx)} className="text-red-500 hover:text-red-700 text-xs">✕</button>
                  </td>
                </tr>
              ))}
              {rules.length === 0 && <tr><td colSpan={5} className="px-3 py-4 text-center text-muted-foreground">No rules configured</td></tr>}
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
          <ComenziTab companies={companies} archived />
        </TabsContent>
        <TabsContent value="settings" className="mt-4 space-y-6">
          <KontoSettingsTab companies={companies} />
          <VenituriRulesSection companies={companies} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
