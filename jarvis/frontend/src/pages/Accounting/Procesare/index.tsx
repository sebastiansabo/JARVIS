import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PageHeader } from '@/components/shared/PageHeader'
import { suppliersApi, type MasterSupplier, type WorklistItem } from '@/api/suppliers'

export default function Procesare() {
  const qc = useQueryClient()
  const [tab, setTab] = useState<'worklist' | 'master'>('worklist')
  const [search, setSearch] = useState('')

  const { data: wl } = useQuery({ queryKey: ['supplier-worklist'], queryFn: () => suppliersApi.worklist() })
  const { data: masters } = useQuery({ queryKey: ['supplier-master', search], queryFn: () => suppliersApi.list(search) })

  const resolveMut = useMutation({
    mutationFn: (i: WorklistItem) =>
      suppliersApi.resolve(i.candidate_id
        ? { action: 'link', partner_name: i.partner_name, partner_cif: i.partner_cif, supplier_id: i.candidate_id }
        : { action: 'create', partner_name: i.partner_name, partner_cif: i.partner_cif }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['supplier-worklist'] }); toast.success('Resolved') },
    onError: () => toast.error('Failed to resolve'),
  })

  return (
    <div className="space-y-4">
      <PageHeader title="Procesare Furnizori" breadcrumbs={[{ label: 'Accounting' }, { label: 'Procesare' }]} />
      <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)}>
        <TabsList>
          <TabsTrigger value="worklist">Worklist ({wl?.items.length ?? 0})</TabsTrigger>
          <TabsTrigger value="master">Master</TabsTrigger>
        </TabsList>

        <TabsContent value="worklist">
          <Card><CardContent className="p-0">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Source</TableHead><TableHead>Name</TableHead><TableHead>CUI</TableHead>
                <TableHead>Suggested</TableHead><TableHead>Confidence</TableHead><TableHead /></TableRow></TableHeader>
              <TableBody>
                {(wl?.items ?? []).map((i, idx) => (
                  <TableRow key={idx}>
                    <TableCell>{i.source}</TableCell>
                    <TableCell>{i.partner_name}</TableCell>
                    <TableCell>{i.partner_cif ?? '-'}</TableCell>
                    <TableCell>{i.candidate_id ? `#${i.candidate_id} (${i.method})` : '—'}</TableCell>
                    <TableCell>{i.confidence}</TableCell>
                    <TableCell className="text-right">
                      <Button size="sm" onClick={() => resolveMut.mutate(i)} disabled={resolveMut.isPending}>
                        {i.candidate_id ? 'Link' : 'Create'}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="master">
          <div className="mb-3"><Input placeholder="Search suppliers…" value={search} onChange={(e) => setSearch(e.target.value)} className="max-w-xs" /></div>
          <Card><CardContent className="p-0">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Name</TableHead><TableHead>CUI</TableHead>
                <TableHead>Konto (D/C)</TableHead><TableHead>Gegenkonto (D/C)</TableHead>
                <TableHead>Kostenstelle (D/C)</TableHead><TableHead>Extbeleg (D/C)</TableHead><TableHead>Klient</TableHead></TableRow></TableHeader>
              <TableBody>
                {(masters?.suppliers ?? []).map((s: MasterSupplier) => (
                  <TableRow key={s.id}>
                    <TableCell>{s.name}</TableCell>
                    <TableCell>{s.cui ?? '-'}</TableCell>
                    <TableCell>{`${s.konto_debit ?? '-'} / ${s.konto_credit ?? '-'}`}</TableCell>
                    <TableCell>{`${s.gegenkonto_debit ?? '-'} / ${s.gegenkonto_credit ?? '-'}`}</TableCell>
                    <TableCell>{`${s.kostenstelle_debit ?? '-'} / ${s.kostenstelle_credit ?? '-'}`}</TableCell>
                    <TableCell>{`${s.extbeleg_debit ?? '-'} / ${s.extbeleg_credit ?? '-'}`}</TableCell>
                    <TableCell>{s.klient ?? '-'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent></Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
