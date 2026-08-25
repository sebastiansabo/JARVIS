import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { FileText, ChevronDown, ChevronRight, Plus, KeyRound, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { foiParcursApi } from '@/api/foiParcurs'

// Every placeholder the backend renderer substitutes. SOURCE OF TRUTH is
// jarvis/foi_parcurs/services/contract_template.py PLACEHOLDERS — keep in sync
// when tokens are added there. Grouped purely for readability.
const PLACEHOLDER_GROUPS: { label: string; tokens: string[] }[] = [
  { label: 'Client', tokens: [
    '{client_name}', '{client_phone}', '{client_address}', '{client_company}',
    '{client_cui}', '{client_ci_serie}', '{client_email}',
  ] },
  { label: 'Vehicul & rută', tokens: [
    '{brand}', '{vehicle_model}', '{vin}', '{registration_number}',
    '{km_start}', '{km_end}', '{distance_km}',
    '{departure_datetime}', '{return_datetime}', '{service_order_ref}', '{advisor_name}',
  ] },
  { label: 'Companie (date legale)', tokens: [
    '{company_name}', '{company_reg_no}', '{company_vat}', '{company_iban}',
    '{company_bank}', '{company_street}', '{company_city}', '{company_county}',
    '{company_email}', '{company_administrator}', '{dealer_phone}',
  ] },
  { label: 'Preț închiriere (curtoazie)', tokens: [
    '{svc_rate_basis}', '{svc_tariff_eur}', '{svc_units}', '{svc_total_eur}',
    '{svc_garantie_eur}', '{svc_fransiza_eur}', '{svc_limita_km_zi}', '{svc_extra_km_eur}',
  ] },
  { label: 'General', tokens: ['{general_conditions}'] },
]

type DtItem = Awaited<ReturnType<typeof foiParcursApi.getDocumentTypes>>['types'][number]
type DtDraft = { label: string; title: string; body_template: string; general_conditions: string; is_rental: boolean; is_active: boolean }

/** Per-company document-type registry — each type IS its contract (title/body/
 *  T&C). 'sales' is the fixed default (no template). Rental types (is_rental)
 *  expose the car pricing fields. Uses the header-selected company. */
export default function ContractConfigSection({ companyId }: { companyId?: number | null } = {}) {
  const qc = useQueryClient()
  const [newLabel, setNewLabel] = useState('')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const { data, isLoading } = useQuery({
    queryKey: ['fp-document-types', companyId, 'all'],
    queryFn: () => foiParcursApi.getDocumentTypes(companyId!, true),
    enabled: !!companyId,
    staleTime: 30_000,
  })
  const types = data?.types ?? []

  const addMut = useMutation({
    mutationFn: (label: string) => foiParcursApi.addDocumentType({ company_id: companyId!, label }),
    onSuccess: (res) => {
      setNewLabel('')
      setExpanded((s) => new Set(s).add(res.key))
      qc.invalidateQueries({ queryKey: ['fp-document-types', companyId, 'all'] })
      // Selectors elsewhere (header, car form) also need the fresh list.
      qc.invalidateQueries({ queryKey: ['fp-document-types'] })
    },
    onError: (err: any) => toast.error(err?.status === 403 ? 'Doar administratorii pot adăuga tipuri.' : (err?.message || 'Adăugarea a eșuat')),
  })

  const saveMut = useMutation({
    mutationFn: (values: DtDraft & { key: string }) =>
      foiParcursApi.putDocumentType({ company_id: companyId!, ...values }),
    onSuccess: () => {
      toast.success('Salvat')
      qc.invalidateQueries({ queryKey: ['fp-document-types', companyId, 'all'] })
      qc.invalidateQueries({ queryKey: ['fp-document-types'] })
    },
    onError: (err: any) => toast.error(err?.status === 403 ? 'Nu ai permisiuni de administrator pentru a salva.' : 'Salvarea a eșuat'),
  })

  const deleteMut = useMutation({
    mutationFn: (key: string) => foiParcursApi.deleteDocumentType({ company_id: companyId!, key }),
    onSuccess: () => {
      toast.success('Șters')
      qc.invalidateQueries({ queryKey: ['fp-document-types', companyId, 'all'] })
      qc.invalidateQueries({ queryKey: ['fp-document-types'] })
    },
    onError: (err: any) => toast.error(err?.data?.error || err?.message || 'Ștergerea a eșuat'),
  })

  const toggle = (key: string) => setExpanded((s) => {
    const n = new Set(s); n.has(key) ? n.delete(key) : n.add(key); return n
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <FileText className="h-5 w-5 text-muted-foreground" />
        <h3 className="text-lg font-semibold">Tipuri de document &amp; contracte</h3>
      </div>
      <p className="text-sm text-muted-foreground">
        Tipurile de document (ex. Vânzări, Mașini de curtoazie) pentru compania selectată în antet. Fiecare tip
        are propriul contract (titlu + conținut + condiții). Un tip „Închiriere” afișează prețul pe mașină.
      </p>

      <Card className="p-3 bg-muted/30">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Token-uri disponibile
        </p>
        <div className="space-y-2.5">
          {PLACEHOLDER_GROUPS.map((group) => (
            <div key={group.label}>
              <p className="mb-1 text-[11px] font-medium text-muted-foreground">{group.label}</p>
              <div className="flex flex-wrap gap-1.5">
                {group.tokens.map((p) => (
                  <code key={p} className="rounded border bg-background px-1.5 py-0.5 text-xs">{p}</code>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>

      {!companyId ? null : (
        <>
          <div className="flex items-end gap-2">
            <div className="flex-1 space-y-1.5">
              <Label className="text-xs">Adaugă tip document</Label>
              <Input
                value={newLabel}
                onChange={(e) => setNewLabel(e.target.value)}
                placeholder="Ex: Comodat, Contract vânzare…"
                onKeyDown={(e) => { if (e.key === 'Enter' && newLabel.trim()) addMut.mutate(newLabel.trim()) }}
              />
            </div>
            <Button size="sm" className="h-10" disabled={!newLabel.trim() || addMut.isPending} onClick={() => addMut.mutate(newLabel.trim())}>
              <Plus className="mr-1.5 h-4 w-4" />{addMut.isPending ? 'Se adaugă…' : 'Adaugă'}
            </Button>
          </div>

          {isLoading ? (
            <p className="py-4 text-sm text-muted-foreground">Se încarcă…</p>
          ) : !types.length ? (
            <p className="py-4 text-sm text-muted-foreground">Niciun tip de document.</p>
          ) : (
            <div className="space-y-2">
              {types.map((t) => (
                <DocTypeRow
                  key={t.key}
                  type={t}
                  open={expanded.has(t.key)}
                  onToggle={() => toggle(t.key)}
                  isSaving={saveMut.isPending}
                  onSave={(values) => saveMut.mutate({ ...values, key: t.key })}
                  onDelete={() => { if (window.confirm(`Ștergi tipul „${t.label}”? Această acțiune este definitivă.`)) deleteMut.mutate(t.key) }}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function DocTypeRow({ type, open, onToggle, onSave, onDelete, isSaving }: {
  type: DtItem
  open: boolean
  onToggle: () => void
  onSave: (values: DtDraft) => void
  onDelete: () => void
  isSaving: boolean
}) {
  const [draft, setDraft] = useState<DtDraft>(() => fromType(type))
  useEffect(() => { setDraft(fromType(type)) }, [type])
  const set = <K extends keyof DtDraft>(k: K, v: DtDraft[K]) => setDraft((p) => ({ ...p, [k]: v }))

  return (
    <Card className="overflow-hidden">
      <div className="flex items-center">
        <button
          type="button"
          onClick={onToggle}
          className="flex flex-1 items-center gap-2 px-4 py-3 text-left hover:bg-accent/40"
        >
          {open ? <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />}
          <span className="text-sm font-medium">{type.label}</span>
          {type.is_default && <Badge variant="secondary" className="text-[10px]">Implicit</Badge>}
          {type.is_rental && <Badge variant="secondary" className="gap-1 text-[10px]"><KeyRound className="h-3 w-3" />Închiriere</Badge>}
          {!type.is_active && <Badge variant="outline" className="text-[10px] text-muted-foreground">Inactiv</Badge>}
          <span className="ml-auto font-mono text-[10px] text-muted-foreground">{type.key}</span>
        </button>
        {!type.is_default && (
          <button
            type="button"
            onClick={onDelete}
            aria-label={`Șterge ${type.label}`}
            title="Șterge tip"
            className="shrink-0 px-3 py-3 text-muted-foreground transition-colors hover:text-destructive"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>

      {open && (
        <div className={cn('space-y-3 border-t px-4 py-3', type.is_default && 'opacity-90')}>
          {type.is_default ? (
            <p className="text-sm text-muted-foreground">
              Tipul implicit „Vânzări” folosește contractul legal standard — nu are șablon editabil și nu poate fi
              dezactivat.
            </p>
          ) : (
            <>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label className="text-xs">Denumire</Label>
                  <Input value={draft.label} onChange={(e) => set('label', e.target.value)} placeholder="Denumire tip document" />
                </div>
                <div className="flex items-center gap-6 pt-6">
                  <label className="flex items-center gap-2 text-xs">
                    <Switch checked={draft.is_rental} onCheckedChange={(v) => set('is_rental', v)} />
                    Închiriere (rent-a-car) — preț pe mașină
                  </label>
                  <label className="flex items-center gap-2 text-xs">
                    <Switch checked={draft.is_active} onCheckedChange={(v) => set('is_active', v)} />
                    Activ
                  </label>
                </div>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs">Titlu contract</Label>
                <Input value={draft.title} onChange={(e) => set('title', e.target.value)} placeholder="Ex: Contract închiriere autovehicul" />
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs">Conținut contract</Label>
                <Textarea
                  className="min-h-[160px] font-mono text-xs"
                  value={draft.body_template}
                  onChange={(e) => set('body_template', e.target.value)}
                  placeholder="Textul contractului, folosind token-urile de mai sus…"
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs">Condiții generale</Label>
                <Textarea
                  className="min-h-[120px] font-mono text-xs"
                  value={draft.general_conditions}
                  onChange={(e) => set('general_conditions', e.target.value)}
                  placeholder="Condiții generale ale contractului…"
                />
              </div>

              <Button size="sm" onClick={() => onSave(draft)} disabled={isSaving || !draft.label.trim()}>
                {isSaving ? 'Se salvează…' : 'Salvează'}
              </Button>
            </>
          )}
        </div>
      )}
    </Card>
  )
}

function fromType(t: DtItem): DtDraft {
  return {
    label: t.label ?? '',
    title: t.title ?? '',
    body_template: t.body_template ?? '',
    general_conditions: t.general_conditions ?? '',
    is_rental: !!t.is_rental,
    is_active: !!t.is_active,
  }
}
