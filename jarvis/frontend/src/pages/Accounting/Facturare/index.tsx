import { useState, useEffect } from 'react'

import { PageHeader } from '@/components/shared/PageHeader'
import ComenziTab from './ComenziTab'
import DocumentItemsTab from './DocumentItemsTab'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

// ── Shared types ──────────────────────────────────────────────

interface Company {
  id: number
  company: string
  vat: string | null
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
      <PageHeader
        title="Comenzi Externe"
        description="Manage contracts, anexas, and invoices"
      />

      <Tabs defaultValue={new URLSearchParams(window.location.search).get('tab') || 'comenzi'} className="w-full"
        onValueChange={(v) => {
          const url = new URL(window.location.href)
          url.searchParams.set('tab', v)
          window.history.replaceState({}, '', url.toString())
        }}>
        <TabsList>
          <TabsTrigger value="comenzi">Comenzi</TabsTrigger>
          <TabsTrigger value="invoices">Invoices</TabsTrigger>
        </TabsList>
        <TabsContent value="comenzi" className="mt-4">
          <ComenziTab companies={companies} />
        </TabsContent>
        <TabsContent value="invoices" className="mt-4">
          <DocumentItemsTab docType="PROFORMA,INVOICE,STORNO,FINAL" />
        </TabsContent>
      </Tabs>
    </div>
  )
}
