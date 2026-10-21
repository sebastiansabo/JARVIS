import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { buybackApi } from '@/api/buyback'
import type { BuybackContractTemplate } from '@/types/buyback'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'

type DocType = 'purchase' | 'consignment'
const DOC_TYPES: { value: DocType; label: string }[] = [
  { value: 'purchase', label: 'Contract achiziție' },
  { value: 'consignment', label: 'Contract depozit (consignație)' },
]

// Mirrors the backend token set — the renderer (P3b) substitutes these.
const TOKENS = [
  '{contract_number}', '{contract_date}', '{seller_name}', '{seller_address}',
  '{seller_cnp}', '{seller_ci}', '{seller_cui}', '{seller_reg_no}', '{seller_legal_rep}',
  '{company_name}', '{company_reg_no}', '{company_vat}', '{company_iban}', '{company_administrator}',
  '{advisor_name}', '{brand}', '{model}', '{vin}', '{engine_no}', '{engine_capacity}',
  '{power_cp}', '{civ_no}', '{mileage}', '{first_registration}',
  '{price_eur}', '{price_ron}', '{price_words}',
  '{owner_price}', '{promo_price}', '{min_price}', '{commission}', '{deposit_months}', '{monthly_fee}',
]

function TemplateCard(
  { companyId, brand, docType, label, existing }:
  { companyId: number; brand: { id: number; name: string }; docType: DocType;
    label: string; existing?: BuybackContractTemplate },
) {
  const qc = useQueryClient()
  const [title, setTitle] = useState(existing?.title ?? '')
  const [body, setBody] = useState(existing?.body_template ?? '')
  const [gc, setGc] = useState(existing?.general_conditions ?? '')
  const [active, setActive] = useState(existing?.is_active ?? true)

  const save = useMutation({
    mutationFn: () => buybackApi.putContractTemplate(companyId, brand.id, {
      document_type: docType, title, body_template: body,
      general_conditions: gc, is_active: active,
    }),
    onSuccess: () => {
      toast.success('Șablon salvat')
      qc.invalidateQueries({ queryKey: ['bb-contract-templates', companyId] })
    },
    onError: () => toast.error('Salvarea a eșuat'),
  })

  return (
    <div className="rounded-md border p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">{brand.name} — {label}</h4>
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          Activ <Switch checked={active} onCheckedChange={setActive} />
        </label>
      </div>
      <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Titlu contract" />
      <Textarea rows={6} value={body} onChange={(e) => setBody(e.target.value)}
        placeholder="Corpul contractului, cu {tokenuri}" />
      <Textarea rows={3} value={gc} onChange={(e) => setGc(e.target.value)}
        placeholder="Condiții generale (opțional)" />
      <Button size="sm" disabled={save.isPending} onClick={() => save.mutate()}>Salvează</Button>
    </div>
  )
}

/** Admin editor for per-company×brand purchase/consignment contract templates.
 *  Uses the company selected in the parent BuyBack settings tab. */
export default function BuyBackContractsSection({ companyId }: { companyId: number | null }) {
  const { data: brandsData } = useQuery({
    queryKey: ['bb-contract-brands', companyId],
    queryFn: () => buybackApi.getContractBrands(companyId as number),
    enabled: companyId != null,
  })
  const { data: tplData } = useQuery({
    queryKey: ['bb-contract-templates', companyId],
    queryFn: () => buybackApi.listContractTemplates(companyId as number),
    enabled: companyId != null,
  })
  if (companyId == null) return null

  const brands = brandsData?.brands ?? []
  const templates = tplData?.templates ?? []
  const find = (brandId: number, dt: DocType) =>
    templates.find((t) => t.brand_id === brandId && t.document_type === dt)

  return (
    <div className="space-y-3">
      <h3 className="text-base font-semibold">Contracte</h3>
      <details className="text-xs text-muted-foreground">
        <summary className="cursor-pointer">Tokenuri disponibile (click pentru listă)</summary>
        <div className="mt-1 flex flex-wrap gap-1">
          {TOKENS.map((t) => <code key={t} className="rounded bg-muted px-1 py-0.5">{t}</code>)}
        </div>
      </details>
      {brands.length === 0 && (
        <p className="text-sm text-muted-foreground">Nicio marcă pentru compania selectată.</p>
      )}
      {brands.map((brand) => (
        <div key={brand.id} className="grid gap-3 sm:grid-cols-2">
          {DOC_TYPES.map((dt) => {
            const existing = find(brand.id, dt.value)
            return (
              <TemplateCard
                // remount when the template row loads so initial state picks it up
                key={`${brand.id}-${dt.value}-${existing?.id ?? 'new'}`}
                companyId={companyId} brand={brand} docType={dt.value}
                label={dt.label} existing={existing}
              />
            )
          })}
        </div>
      ))}
    </div>
  )
}
