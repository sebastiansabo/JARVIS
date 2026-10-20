import { useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ExternalLink, Loader2 } from 'lucide-react'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { autovitApi, type AutovitAccount } from '@/api/autovit'
import { carparkApi } from '@/api/carpark'
import { AutovitLogo } from '@/components/icons/MarketplaceLogos'
import { PlatformPublishRow } from './PlatformPublishRow'
import type { Freshness } from './ListingFreshness'

// Small dt/dd field used only by the preview step below — a local copy of
// Detail.tsx's (unexported) `Field` helper, since this dialog was lifted out
// of Detail.tsx and that helper isn't exported for reuse.
function PreviewField({ label, value, className }: { label: string; value: ReactNode; className?: string }) {
  if (value == null || value === '' || value === '-') return null
  return (
    <div className={`min-w-0 ${className ?? ''}`}>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm font-medium break-words">{value}</dd>
    </div>
  )
}

function advertField(params: Record<string, unknown>, key: string): string {
  const v = params[key]
  return v === undefined || v === null || v === '' ? '—' : String(v)
}

// ── Autovit publish row — adapts autovitApi + the per-vehicle auto-update
// schedule onto the shared PlatformPublishRow. Keeps the original 4-step
// account → preview → publish wizard (lifted verbatim from Detail.tsx's old
// AutovitPublishAction, now removed — superseded by this adapter). ──
export function AutovitPublishRow({
  vehicleId,
  canEdit,
}: {
  vehicleId: number
  canEdit: boolean
}) {
  const [open, setOpen] = useState(false)
  const [accountId, setAccountId] = useState('')
  const [step, setStep] = useState<'select' | 'preview' | 'missing' | 'success'>('select')
  const [advert, setAdvert] = useState<Record<string, unknown> | null>(null)
  const [missing, setMissing] = useState<string[]>([])
  const [externalUrl, setExternalUrl] = useState<string | null>(null)
  const [publishOutcome, setPublishOutcome] = useState<{ updated: boolean; status?: string } | null>(null)

  const queryClient = useQueryClient()
  const statusKey = ['autovit', 'vehicle-status', vehicleId]
  const scheduleKey = ['listing-schedule', vehicleId, 'autovit']

  const { data: accounts = [], isLoading: accountsLoading } = useQuery({
    queryKey: ['autovit', 'accounts'],
    queryFn: autovitApi.getAccounts,
    enabled: open,
  })
  const connectedAccounts = accounts.filter((a) => a.status === 'connected')

  // Current Autovit publish state (across accounts) — surfaces the status/last
  // error that used to be visible only in the DB.
  const { data: autovitListings = [] } = useQuery({
    queryKey: statusKey,
    queryFn: () => autovitApi.getVehicleStatus(vehicleId),
    enabled: !!vehicleId,
  })
  const listing = autovitListings[0] ?? null
  const freshness: Freshness = listing?.freshness ?? 'not_published'

  const { data: scheduleData } = useQuery({
    queryKey: scheduleKey,
    queryFn: () => carparkApi.getListingSchedule(vehicleId, 'autovit'),
    enabled: !!vehicleId,
  })
  const schedule = scheduleData?.schedule ?? null
  const autoEnabled = !!schedule?.enabled && schedule.cadence !== 'manual'

  const reset = () => {
    setStep('select')
    setAccountId('')
    setAdvert(null)
    setMissing([])
    setExternalUrl(null)
    setPublishOutcome(null)
  }

  const previewMutation = useMutation({
    mutationFn: () => autovitApi.publish(Number(accountId), vehicleId, { dryRun: true }),
    onSuccess: (res) => {
      setAdvert((res.advert as Record<string, unknown>) ?? null)
      setStep('preview')
    },
    onError: (err: unknown) => {
      const apiErr = err as { data?: { error?: string; missing?: string[] } }
      if (apiErr?.data?.missing?.length) {
        setMissing(apiErr.data.missing)
        setStep('missing')
      } else {
        toast.error(apiErr?.data?.error || 'Previzualizarea a eșuat')
      }
    },
  })

  const publishMutation = useMutation({
    mutationFn: () => autovitApi.publish(Number(accountId), vehicleId, { draft: true }),
    onSuccess: (res) => {
      if (res.success) {
        setExternalUrl(res.external_url || null)
        setPublishOutcome({ updated: !!res.updated_existing, status: res.status })
        setStep('success')
        queryClient.invalidateQueries({ queryKey: statusKey })
        toast.success(res.updated_existing
          ? 'Anunț actualizat pe Autovit'
          : res.status === 'active' ? 'Anunț publicat (activ) pe Autovit'
          : 'Anunț publicat ca draft pe Autovit')
        // Surface "already published → updated" + any dropped-param warnings.
        if (res.warnings && res.warnings.length > 0) {
          toast.info(res.warnings.join(' · '))
        }
      } else {
        toast.error(res.error || 'Publicarea a eșuat')
      }
    },
    onError: (err: unknown) => {
      const apiErr = err as { data?: { error?: string } }
      toast.error(apiErr?.data?.error || 'Publicarea a eșuat')
    },
  })

  const refreshStatus = () => queryClient.invalidateQueries({ queryKey: statusKey })
  const autovitErr = (e: unknown, fallback: string) =>
    toast.error((e as { data?: { error?: string } })?.data?.error || fallback)

  const verifyStatusMutation = useMutation({
    mutationFn: () => autovitApi.verifyStatus(vehicleId),
    onSuccess: (res) => {
      refreshStatus()
      toast.success(res.refreshed > 0 ? 'Status Autovit actualizat' : 'Niciun anunț de verificat')
    },
    onError: () => toast.error('Verificarea statusului a eșuat'),
  })

  // A live Autovit advert exists only once published and not removed. Without
  // this, deactivate/delete would compute Number(undefined) = NaN and POST to
  // /accounts/NaN/... for a never-published car (the most common state).
  const autovitLive =
    !!listing?.external_advert_id && !String(listing?.status ?? '').startsWith('removed')

  // Deactivate = disable on Autovit (reversible — re-publishing reactivates).
  const deactivateMutation = useMutation({
    mutationFn: (): Promise<{ success: boolean; error?: string }> => {
      if (!listing?.account_id) return Promise.resolve({ success: false })
      return autovitApi.unpublish(Number(listing.account_id), vehicleId)
    },
    onSuccess: (res) => {
      if (res.success) { refreshStatus(); toast.success('Anunț dezactivat pe Autovit') }
      else toast.error(res.error || 'Dezactivarea a eșuat')
    },
    onError: (e) => autovitErr(e, 'Dezactivarea a eșuat'),
  })

  // Delete = permanent removal on Autovit (re-publishing creates a new advert).
  const deleteMutation = useMutation({
    mutationFn: (): Promise<{ success: boolean; error?: string }> => {
      if (!listing?.account_id) return Promise.resolve({ success: false })
      return autovitApi.deleteAdvert(Number(listing.account_id), vehicleId)
    },
    onSuccess: (res) => {
      if (res.success) { refreshStatus(); toast.success('Anunț șters de pe Autovit') }
      else toast.error(res.error || 'Ștergerea a eșuat')
    },
    onError: (e) => autovitErr(e, 'Ștergerea a eșuat'),
  })

  const scheduleMutation = useMutation({
    mutationFn: (on: boolean) =>
      carparkApi.setListingSchedule(vehicleId, {
        platform: 'autovit',
        cadence: on ? '1h' : 'manual',
        enabled: on,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: scheduleKey }),
    onError: () => toast.error('Salvarea programării automate a eșuat'),
  })

  const params = (advert?.params as Record<string, unknown>) || {}
  const price = params.price as { '1'?: number; currency?: string } | undefined
  const busy = previewMutation.isPending || publishMutation.isPending

  return (
    <>
      <PlatformPublishRow
        logo={<AutovitLogo className="h-9 w-9" />}
        name="Autovit.ro"
        freshness={freshness}
        lastSync={listing?.last_sync}
        externalUrl={listing?.external_url}
        externalLinkLabel="Vezi anunțul"
        autoEnabled={autoEnabled}
        busy={busy}
        canEdit={canEdit}
        onPrimary={() => setOpen(true)}
        onVerify={() => verifyStatusMutation.mutate()}
        onToggleAuto={(on) => scheduleMutation.mutate(on)}
        onDeactivate={() => deactivateMutation.mutate()}
        onDelete={autovitLive ? () => deleteMutation.mutate() : undefined}
      />

      <Dialog
        open={open}
        onOpenChange={(v) => {
          setOpen(v)
          if (!v) reset()
        }}
      >
        <DialogContent className="sm:max-w-lg" aria-describedby={undefined}>
          <DialogHeader>
            <DialogTitle>Publică pe Autovit</DialogTitle>
            {step === 'select' && (
              <DialogDescription>Alege contul Autovit conectat pentru publicare.</DialogDescription>
            )}
          </DialogHeader>

          {step === 'select' && (
            <div className="space-y-4 py-2">
              {accountsLoading ? (
                <Skeleton className="h-9 w-full" />
              ) : connectedAccounts.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Niciun cont Autovit conectat. Configurează unul din Setări → Connectori.
                </p>
              ) : (
                <Select value={accountId} onValueChange={setAccountId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Selectează contul Autovit" />
                  </SelectTrigger>
                  <SelectContent>
                    {connectedAccounts.map((a: AutovitAccount) => (
                      <SelectItem key={a.id} value={String(a.id)}>
                        {a.email}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
          )}

          {step === 'missing' && (
            <div className="space-y-3 py-2">
              <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <div>
                  <p className="font-medium">Câmpuri obligatorii lipsă</p>
                  <ul className="mt-1 list-disc pl-4 text-xs">
                    {missing.map((m) => (
                      <li key={m}>{m}</li>
                    ))}
                  </ul>
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                Completează aceste câmpuri pe fișa vehiculului, apoi încearcă din nou.
              </p>
            </div>
          )}

          {step === 'preview' && advert && (
            <div className="space-y-3 py-2">
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <PreviewField label="Titlu" value={String(advert.title || '—')} className="col-span-2" />
                <PreviewField
                  label="Preț"
                  value={price?.['1'] ? `${Number(price['1']).toLocaleString('ro-RO')} ${price.currency || ''}` : '—'}
                />
                <PreviewField label="Marcă / Model" value={`${advertField(params, 'make')} ${advertField(params, 'model')}`} />
                <PreviewField label="An" value={advertField(params, 'year')} />
                <PreviewField label="Km" value={advertField(params, 'mileage')} />
                <PreviewField label="Combustibil" value={advertField(params, 'fuel_type')} />
              </dl>
              {advert.description ? (
                <div className="max-h-24 overflow-y-auto rounded-md border p-2 text-xs text-muted-foreground">
                  {String(advert.description)}
                </div>
              ) : null}
              <p className="text-xs text-muted-foreground">
                Anunțul va fi publicat ca <strong>draft</strong> (dezactivat) — îl poți activa manual de pe Autovit.ro.
              </p>
            </div>
          )}

          {step === 'success' && (
            <div className="space-y-3 py-2">
              <p className="text-sm">
                {publishOutcome?.updated
                  ? 'Anunțul existent a fost actualizat pe Autovit.'
                  : publishOutcome?.status === 'active'
                    ? 'Anunțul a fost publicat (activ) pe Autovit.'
                    : 'Anunțul a fost publicat ca draft (neplătit) pe Autovit.'}
              </p>
              {externalUrl && (
                <a
                  href={externalUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-sm text-primary underline"
                >
                  <ExternalLink className="h-3.5 w-3.5" /> Deschide anunțul
                </a>
              )}
            </div>
          )}

          <DialogFooter>
            {step === 'select' && (
              <>
                <Button variant="outline" onClick={() => setOpen(false)}>
                  Anulează
                </Button>
                <Button disabled={!accountId || previewMutation.isPending} onClick={() => previewMutation.mutate()}>
                  {previewMutation.isPending ? (
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  ) : null}
                  Previzualizează
                </Button>
              </>
            )}
            {step === 'missing' && (
              <>
                <Button variant="outline" onClick={() => setStep('select')}>
                  Înapoi
                </Button>
                <Button variant="outline" onClick={() => setOpen(false)}>
                  Închide
                </Button>
              </>
            )}
            {step === 'preview' && (
              <>
                <Button variant="outline" onClick={() => setStep('select')}>
                  Înapoi
                </Button>
                <Button disabled={publishMutation.isPending} onClick={() => publishMutation.mutate()}>
                  {publishMutation.isPending ? (
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  ) : null}
                  Publică (draft)
                </Button>
              </>
            )}
            {step === 'success' && <Button onClick={() => setOpen(false)}>Închide</Button>}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

export default AutovitPublishRow
