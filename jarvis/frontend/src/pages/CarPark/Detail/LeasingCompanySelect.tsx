import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { carparkSaleDocsApi } from '@/api/carparkSaleDocs'
import type { LeasingCompany, LeasingCompanyCreate } from '@/types/carpark'
import { apiErrorMessage } from '../Dispo/dispoApiError'

const LEASING_COMPANIES_QUERY_KEY = ['carpark', 'leasing-companies']

const EMPTY_FORM: LeasingCompanyCreate = {
  name: '',
  cui: '',
  reg_no: '',
  address: '',
  city: '',
  county: '',
  legal_rep: '',
  legal_rep_role: '',
  iban: '',
}

// Trims the inline-add form down to a create body: only `name` is required;
// blank optional fields are dropped rather than sent as empty strings.
function toCreateBody(form: LeasingCompanyCreate): LeasingCompanyCreate {
  const body: LeasingCompanyCreate = { name: form.name.trim() }
  const optionalKeys = ['cui', 'reg_no', 'address', 'city', 'county', 'legal_rep', 'legal_rep_role', 'iban'] as const
  for (const key of optionalKeys) {
    const v = form[key]?.trim()
    if (v) body[key] = v
  }
  return body
}

/** Reusable leasing-company picker: a Select over the global leasing-company
 *  directory, plus an inline "add new" form for when the Cumpărător isn't
 *  in the directory yet. Self-contained (owns its own react-query cache) so
 *  the sale-documents dialog (Task 9) can embed it directly for a leasing
 *  sale's Cumpărător field. */
export function LeasingCompanySelect({
  value,
  onSelect,
}: {
  value?: number | null
  onSelect: (lc: LeasingCompany) => void
}) {
  const queryClient = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState<LeasingCompanyCreate>(EMPTY_FORM)
  const [error, setError] = useState<string | null>(null)

  const { data } = useQuery({
    queryKey: LEASING_COMPANIES_QUERY_KEY,
    queryFn: async () => (await carparkSaleDocsApi.listLeasingCompanies()).leasing_companies,
  })
  const companies = data ?? []

  const createMutation = useMutation({
    mutationFn: (body: LeasingCompanyCreate) => carparkSaleDocsApi.createLeasingCompany(body),
    onSuccess: ({ leasing_company }) => {
      queryClient.invalidateQueries({ queryKey: LEASING_COMPANIES_QUERY_KEY })
      onSelect(leasing_company)
      setAdding(false)
      setForm(EMPTY_FORM)
      setError(null)
    },
    onError: (err: unknown) => {
      setError(apiErrorMessage(err, 'Eroare la salvarea firmei de leasing'))
    },
  })

  function handleValueChange(id: string) {
    const lc = companies.find((c) => String(c.id) === id)
    if (lc) onSelect(lc)
  }

  function updateField(key: keyof LeasingCompanyCreate, v: string) {
    setForm((f) => ({ ...f, [key]: v }))
  }

  function handleCancel() {
    setAdding(false)
    setForm(EMPTY_FORM)
    setError(null)
  }

  function handleSubmit() {
    if (!form.name.trim()) return
    setError(null)
    createMutation.mutate(toCreateBody(form))
  }

  return (
    <div className="space-y-2">
      <Select value={value != null ? String(value) : undefined} onValueChange={handleValueChange}>
        <SelectTrigger className="w-full">
          <SelectValue placeholder="Firmă de leasing" />
        </SelectTrigger>
        <SelectContent>
          {companies.map((lc) => (
            <SelectItem key={lc.id} value={String(lc.id)}>
              {lc.cui ? `${lc.name} (${lc.cui})` : lc.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {!adding && (
        <Button type="button" variant="ghost" size="sm" onClick={() => setAdding(true)}>
          <Plus className="h-4 w-4" />
          Adaugă firmă de leasing
        </Button>
      )}

      {adding && (
        <div className="space-y-2 rounded-md border p-3">
          <div className="space-y-1">
            <Label htmlFor="leasing-company-name">Nume *</Label>
            <Input
              id="leasing-company-name"
              value={form.name}
              onChange={(e) => updateField('name', e.target.value)}
              autoFocus
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <Label htmlFor="leasing-company-cui">CUI</Label>
              <Input id="leasing-company-cui" value={form.cui ?? ''} onChange={(e) => updateField('cui', e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="leasing-company-reg-no">Nr. Reg. Com.</Label>
              <Input
                id="leasing-company-reg-no"
                value={form.reg_no ?? ''}
                onChange={(e) => updateField('reg_no', e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="leasing-company-address">Adresă</Label>
              <Input
                id="leasing-company-address"
                value={form.address ?? ''}
                onChange={(e) => updateField('address', e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="leasing-company-city">Oraș</Label>
              <Input id="leasing-company-city" value={form.city ?? ''} onChange={(e) => updateField('city', e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="leasing-company-county">Județ</Label>
              <Input
                id="leasing-company-county"
                value={form.county ?? ''}
                onChange={(e) => updateField('county', e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="leasing-company-iban">IBAN</Label>
              <Input id="leasing-company-iban" value={form.iban ?? ''} onChange={(e) => updateField('iban', e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="leasing-company-legal-rep">Reprezentant legal</Label>
              <Input
                id="leasing-company-legal-rep"
                value={form.legal_rep ?? ''}
                onChange={(e) => updateField('legal_rep', e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="leasing-company-legal-rep-role">Funcție reprezentant</Label>
              <Input
                id="leasing-company-legal-rep-role"
                value={form.legal_rep_role ?? ''}
                onChange={(e) => updateField('legal_rep_role', e.target.value)}
              />
            </div>
          </div>
          {error && <p className="text-xs text-destructive">{error}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" size="sm" onClick={handleCancel}>
              Anulează
            </Button>
            <Button type="button" size="sm" disabled={!form.name.trim() || createMutation.isPending} onClick={handleSubmit}>
              {createMutation.isPending ? 'Se salvează...' : 'Salvează'}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
