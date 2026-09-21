import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Globe, Loader2, Undo2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { shopifyApi } from '@/api/shopify'
import { ListingFreshness } from './ListingFreshness'

// RO labels for the store's custom.* metafield keys, so the pre-publish modal
// reads like the vehicle form rather than dumping raw backend warning strings.
const FIELD_LABELS: Record<string, string> = {
  culoare_tapiterie: 'Culoare tapițerie',
  dotari: 'Dotări',
  emisii_co2: 'Emisii CO₂',
  nivel_de_echipare: 'Nivel de echipare',
  nr_de_usi: 'Număr uși',
  nr_dos_: 'Număr dosar',
  nr_imatr_: 'Număr înmatriculare',
  putere_kw: 'Putere (kW)',
  transmisie: 'Tracțiune',
  bodu_type: 'Caroserie', // store theme key is misspelled 'bodu_type' (known gotcha)
  marca: 'Marcă',
  model: 'Model',
  sku: 'SKU (VIN)',
  fuel: 'Combustibil',
  cutie_viteze: 'Cutie de viteze',
  culoare: 'Culoare',
  kilometraj: 'Kilometraj',
  cilindree: 'Cilindree',
  putere_cp: 'Putere (CP)',
  anul_modelului: 'Anul modelului',
  data_livrarii: 'Data livrării',
  body_type: 'Caroserie',
  clasa_de_emisii_noxe: 'Clasă emisii',
}

// Turn "empty value for custom.emisii_co2 (source='co2_emissions')" into "Emisii CO₂".
function humanizeWarning(w: string): string {
  const m = w.match(/(?:custom|carpark)\.([a-z0-9_]+)/i)
  if (!m) return w
  const key = m[1]
  const label = FIELD_LABELS[key] ?? key.replace(/_/g, ' ')
  return /stale|no longer in store/i.test(w) ? `${label} (câmp eliminat din magazin)` : label
}

// Backend blocking reasons are English (is_eligible) — translate to actionable RO.
function humanizeBlocking(reason?: string | null): string {
  if (!reason) return 'Vehiculul nu îndeplinește condițiile de publicare.'
  if (/photo/i.test(reason)) return 'Adaugă cel puțin o fotografie înainte de publicare.'
  if (/price/i.test(reason)) return 'Setează un preț de vânzare pozitiv înainte de publicare.'
  if (/status/i.test(reason)) return 'Vehiculul nu are un status valabil pentru vânzare (ex: Listat).'
  return reason
}

type PublishModal =
  | { mode: 'warnings'; items: string[] }
  | { mode: 'blocked'; reason?: string | null }

function apiError(err: unknown, fallback: string): string {
  return (err as { data?: { error?: string } })?.data?.error || fallback
}

// ── Shopify publish control (status chip + publish/retract button) ──
export function ShopifyPublishControl({
  vehicleId,
  canEdit,
}: {
  vehicleId: number
  canEdit: boolean
}) {
  const queryClient = useQueryClient()
  const statusKey = ['shopify', 'status', vehicleId]
  // `modal` holds the content; `modalOpen` drives visibility. Closing flips only
  // `modalOpen` so the retained content renders correctly through Radix's exit
  // animation (clearing content on close flashes the dialog to the wrong variant).
  const [modal, setModal] = useState<PublishModal | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const openModal = (m: PublishModal) => {
    setModal(m)
    setModalOpen(true)
  }

  const { data, isLoading } = useQuery({
    queryKey: statusKey,
    queryFn: () => shopifyApi.vehicleStatus(vehicleId),
    enabled: !!vehicleId,
  })

  const listing = data?.listing ?? null
  const isPublished = listing?.status === 'published'

  const invalidateStatus = () => queryClient.invalidateQueries({ queryKey: statusKey })

  const publishMutation = useMutation({
    mutationFn: () => shopifyApi.publishVehicle(vehicleId),
    onSuccess: (res) => {
      invalidateStatus()
      toast.success('Publicat pe Shopify')
      // Safety net: if the field/value map drifted between the dry-run preview
      // and the actual publish, surface whatever the publish itself skipped.
      if (res.warnings && res.warnings.length > 0) {
        toast.info(`Câmpuri necompletate: ${res.warnings.map(humanizeWarning).join(', ')}`)
      }
    },
    onError: (err: unknown) => toast.error(apiError(err, 'Publicare eșuată')),
  })

  // Dry-run gate: check eligibility + empty optional fields before publishing.
  const previewMutation = useMutation({
    mutationFn: () => shopifyApi.previewVehicle(vehicleId),
    onSuccess: (res) => {
      if (!res.eligible) {
        openModal({ mode: 'blocked', reason: res.blocking_reason })
        return
      }
      if (res.warnings && res.warnings.length > 0) {
        openModal({ mode: 'warnings', items: res.warnings })
        return
      }
      publishMutation.mutate() // nothing to warn about → publish straight away
    },
    onError: (err: unknown) => toast.error(apiError(err, 'Verificare eșuată')),
  })

  const unpublishMutation = useMutation({
    mutationFn: () => shopifyApi.unpublishVehicle(vehicleId),
    onSuccess: () => {
      invalidateStatus()
      toast.success('Retras de pe Shopify')
    },
    onError: (err: unknown) => toast.error(apiError(err, 'Retragere eșuată')),
  })

  const isMutating =
    previewMutation.isPending || publishMutation.isPending || unpublishMutation.isPending

  const onPrimaryClick = () =>
    isPublished ? unpublishMutation.mutate() : previewMutation.mutate()

  return (
    <>
      <div className="flex items-center gap-2">
        {!isLoading && (
          <ListingFreshness
            freshness={data?.freshness ?? 'not_published'}
            lastSync={listing?.last_sync}
            expiresAt={listing?.expires_at}
          />
        )}
        {canEdit && (
          <Button
            size="sm"
            variant={isPublished ? 'outline' : 'default'}
            className="w-44"
            disabled={isMutating || isLoading}
            onClick={onPrimaryClick}
          >
            {isMutating ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : isPublished ? (
              <Undo2 className="mr-1.5 h-3.5 w-3.5" />
            ) : (
              <Globe className="mr-1.5 h-3.5 w-3.5" />
            )}
            {isPublished ? 'Retrage' : 'Publică pe Shopify'}
          </Button>
        )}
      </div>

      <Dialog open={modalOpen} onOpenChange={(open) => !open && setModalOpen(false)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-500" />
              {modal?.mode === 'blocked'
                ? 'Nu se poate publica'
                : 'Câmpuri opționale necompletate'}
            </DialogTitle>
            <DialogDescription>
              {modal?.mode === 'blocked'
                ? 'Completează datele obligatorii înainte de publicare.'
                : 'Următoarele câmpuri nu vor apărea pe anunț (nu sunt obligatorii). Poți publica oricum.'}
            </DialogDescription>
          </DialogHeader>

          {modal?.mode === 'blocked' ? (
            <p className="text-sm text-muted-foreground">{humanizeBlocking(modal.reason)}</p>
          ) : (
            <ul className="max-h-64 space-y-1 overflow-y-auto text-sm">
              {modal?.mode === 'warnings' &&
                modal.items.map((w, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="mt-0.5 text-amber-500">•</span>
                    <span>{humanizeWarning(w)}</span>
                  </li>
                ))}
            </ul>
          )}

          <DialogFooter>
            {modal?.mode === 'blocked' ? (
              <Button onClick={() => setModalOpen(false)}>Am înțeles</Button>
            ) : (
              <>
                <Button variant="outline" onClick={() => setModalOpen(false)}>
                  Anulează
                </Button>
                <Button
                  onClick={() => {
                    setModalOpen(false)
                    publishMutation.mutate()
                  }}
                  disabled={publishMutation.isPending}
                >
                  Publică oricum
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

export default ShopifyPublishControl
