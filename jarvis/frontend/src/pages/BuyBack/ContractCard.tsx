import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Link } from 'react-router-dom'
import { buybackApi } from '@/api/buyback'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'

// The per-record contract (P3c): shows the generated contract under the
// Acțiuni panel, editable inline. "Salvează & regenerează" re-renders the PDF
// from the edited text; "Regenerează din date" rebuilds from the template +
// current client/car data (discarding manual edits). The PDF also lives in the
// Documente section — this card is the edit/download surface.
export default function ContractCard({
  recordId,
  canEdit,
}: {
  recordId: number
  canEdit: boolean
}) {
  const qc = useQueryClient()
  const { data: draft, isLoading } = useQuery({
    queryKey: ['buyback-contract', recordId],
    queryFn: () => buybackApi.getContractDraft(recordId),
    enabled: !!recordId,
  })

  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [gc, setGc] = useState('')
  const [gcOpen, setGcOpen] = useState(false)
  const [dirty, setDirty] = useState(false)

  // Seed the editor from the draft; keep the user's in-progress edits (don't
  // clobber them on a background refetch).
  useEffect(() => {
    if (!draft || dirty) return
    setTitle(draft.title)
    setBody(draft.body)
    setGc(draft.general_conditions)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft])

  const onSaved = (warnings?: string[]) => {
    setDirty(false)
    qc.invalidateQueries({ queryKey: ['buyback-contract', recordId] })
    qc.invalidateQueries({ queryKey: ['buyback-record', recordId] })
    warnings?.length ? toast.warning(warnings.join(' ')) : toast.success('Contract salvat')
  }

  const saveMutation = useMutation({
    mutationFn: () => buybackApi.saveContract(recordId, { title, body, general_conditions: gc }),
    onSuccess: (res) => onSaved(res.warnings),
    onError: () => toast.error('Salvarea contractului a eșuat'),
  })

  const regenMutation = useMutation({
    mutationFn: () => buybackApi.regenerateContractFromData(recordId),
    onSuccess: (res) => onSaved(res.warnings),
    onError: () => toast.error('Regenerarea a eșuat'),
  })

  const busy = saveMutation.isPending || regenMutation.isPending

  const handleRegenerate = () => {
    if (dirty && !window.confirm('Regenerarea din date suprascrie modificările manuale. Continuați?')) return
    regenMutation.mutate()
  }

  if (isLoading || !draft) return null

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle className="text-base">Contract</CardTitle>
        {draft.generated_at && (
          <span className="text-xs text-muted-foreground">
            Generat {new Date(draft.generated_at).toLocaleString('ro-RO')}
          </span>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {!draft.has_template && !draft.has_contract ? (
          <p className="text-sm text-muted-foreground">
            Niciun model de contract activ pentru acest brand.{' '}
            <Link to="/app/settings" className="font-medium text-primary hover:underline">
              Configurează în Setări → BuyBack → Contracte
            </Link>
            .
          </p>
        ) : (
          <>
            <div className="space-y-1">
              <Label className="text-xs">Titlu</Label>
              <Input
                value={title}
                maxLength={300}
                disabled={!canEdit}
                onChange={(e) => { setTitle(e.target.value); setDirty(true) }}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Conținut contract</Label>
              <Textarea
                className="font-mono text-xs leading-relaxed"
                rows={16}
                value={body}
                disabled={!canEdit}
                onChange={(e) => { setBody(e.target.value); setDirty(true) }}
              />
            </div>

            <button
              type="button"
              className="text-xs font-medium text-muted-foreground hover:text-foreground"
              onClick={() => setGcOpen((v) => !v)}
            >
              {gcOpen ? '▾' : '▸'} Condiții generale
            </button>
            {gcOpen && (
              <Textarea
                className="font-mono text-xs leading-relaxed"
                rows={6}
                value={gc}
                disabled={!canEdit}
                onChange={(e) => { setGc(e.target.value); setDirty(true) }}
              />
            )}

            <div className="flex flex-wrap items-center gap-2 pt-1">
              {canEdit && (
                <Button size="sm" disabled={busy} onClick={() => saveMutation.mutate()}>
                  {saveMutation.isPending
                    ? 'Se generează…'
                    : draft.has_contract ? 'Salvează & regenerează' : 'Generează contract'}
                </Button>
              )}
              {draft.download_url && (
                <a
                  href={draft.download_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex h-8 items-center rounded-md border px-3 text-sm font-medium hover:bg-muted"
                >
                  ↓ Descarcă PDF
                </a>
              )}
              {canEdit && (
                <Button size="sm" variant="ghost" disabled={busy} onClick={handleRegenerate}>
                  {regenMutation.isPending ? 'Se regenerează…' : 'Regenerează din date'}
                </Button>
              )}
            </div>

            {draft.warnings.length > 0 && (
              <p className="text-xs text-amber-600">{draft.warnings.join(' · ')}</p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
