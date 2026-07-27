import { useEffect, useRef, useState, Suspense, lazy } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, ChevronLeft } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import { foiParcursApi } from '@/api/foiParcurs'
import type { ReturnFuelLevel } from '@/types/foiParcurs'
import { DamageReport } from './testDriveDamage'
import {
  seedReturnDamage, kmEndError, returnMissing, isReturnValid, buildReturnPayload,
  type ReturnFormState,
} from './returnLogic'

const SignatureCanvas = lazy(() => import('@/components/shared/SignatureCanvas'))
const ADVISOR_SIG_KEY = 'fp_advisor_signature'
const FUEL_OPTIONS: ReturnFuelLevel[] = ['Gol', '1/4', '1/2', '3/4', 'Plin']

interface Props {
  id?: number
  embedded?: boolean
  onDone?: (contract: unknown) => void
  onCancel?: () => void
}

export default function TestDriveReturn({ id: idProp, embedded, onDone, onCancel }: Props) {
  const params = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const id = idProp ?? (params.id ? Number(params.id) : undefined)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['fp-test-drive', id],
    queryFn: () => foiParcursApi.getTestDrive(id!),
    enabled: id != null,
  })
  const contract = data?.contract
  const kmStart = contract?.km_start != null ? Number(contract.km_start) : undefined

  const [form, setForm] = useState<ReturnFormState>({
    kmEnd: '', fuel: null, damage: seedReturnDamage({ departure_damage: null }).damage,
    notes: '', advisorSignature: '', clientSignature: '',
  })
  const [showDamage, setShowDamage] = useState(false)
  const [attempted, setAttempted] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  // Seed advisor signature (reused across submissions) once.
  useEffect(() => {
    try { const s = localStorage.getItem(ADVISOR_SIG_KEY); if (s) setForm((f) => ({ ...f, advisorSignature: s })) } catch { /* ignore */ }
  }, [])

  // Seed damage from departure once the contract loads.
  const seededRef = useRef(false)
  useEffect(() => {
    if (seededRef.current || !contract) return
    seededRef.current = true
    const { damage, seeded } = seedReturnDamage(contract)
    if (seeded) { setForm((f) => ({ ...f, damage })); setShowDamage(true) }
  }, [contract])

  const mutation = useMutation({
    mutationFn: () => foiParcursApi.submitTestDriveReturn(id!, buildReturnPayload(form)),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['foi-contracts-all'] })
      queryClient.invalidateQueries({ queryKey: ['fp-test-drive', id] })
      queryClient.invalidateQueries({ queryKey: ['odometer-history'] })
      if (embedded) onDone?.(res.contract)
      else navigate(`/app/foi-parcurs?tab=parcurs`)
    },
    onError: (e: unknown) => setSubmitError(e instanceof Error ? e.message : 'Trimiterea a eșuat.'),
  })

  const goBack = () => { if (embedded) onCancel?.(); else navigate('/app/foi-parcurs') }
  const kmErr = kmEndError(form.kmEnd, kmStart)
  const missing = returnMissing(form, kmStart)
  const err = (bad: boolean) => attempted && bad
  const set = (patch: Partial<ReturnFormState>) => setForm((f) => ({ ...f, ...patch }))

  const handleSubmit = () => {
    if (mutation.isPending) return
    if (!isReturnValid(form, kmStart)) { setAttempted(true); return }
    setSubmitError(null)
    mutation.mutate()
  }

  const Header = (
    <div className="flex items-center gap-2 mb-4">
      <Button variant="ghost" size="icon" onClick={goBack}><ChevronLeft className="h-4 w-4" /></Button>
      <h2 className="text-lg font-semibold">Retur test drive</h2>
    </div>
  )

  if (id == null) return <div className="p-4">{Header}<p className="text-sm text-destructive">Lipsă id.</p></div>
  if (isLoading) return <div className="p-4">{Header}<Skeleton className="h-48 w-full" /></div>
  if (isError || !contract) return <div className="p-4">{Header}<p className="text-sm text-destructive">Nu s-a putut încărca test drive-ul.</p></div>
  if (contract.status === 'COMPLETED') return <div className="p-4">{Header}<p className="text-sm text-muted-foreground py-8 text-center">Acest test drive a fost deja finalizat.</p></div>

  return (
    <div className="p-4 max-w-2xl mx-auto">
      {Header}
      <div className="space-y-4">
        {/* KM retur */}
        <div className="space-y-1.5">
          <Label htmlFor="km-retur" className="text-xs">Km retur</Label>
          <Input id="km-retur" inputMode="numeric" value={form.kmEnd}
            onChange={(e) => set({ kmEnd: e.target.value })}
            className={cn(err(missing.km) && 'ring-2 ring-destructive')} />
          {kmErr && <p className="text-xs text-destructive">{kmErr}</p>}
        </div>

        {/* Combustibil */}
        <div className="space-y-1.5">
          <Label className="text-xs">Nivel combustibil</Label>
          <div className={cn('flex gap-1', err(missing.fuel) && 'ring-2 ring-destructive rounded-md p-0.5')}>
            {FUEL_OPTIONS.map((f) => (
              <Button key={f} type="button" variant={form.fuel === f ? 'default' : 'outline'} size="sm"
                className="flex-1" onClick={() => set({ fuel: f })}>{f}</Button>
            ))}
          </div>
        </div>

        {/* Raport avarii (seeded from departure) */}
        <div className="space-y-1.5">
          <Button type="button" variant="outline" size="sm" onClick={() => setShowDamage((s) => !s)}>
            {showDamage ? 'Ascunde' : 'Arată'} raport avarii
          </Button>
          {showDamage && <DamageReport value={form.damage} onChange={(damage) => set({ damage })} />}
        </div>

        {/* Observații */}
        <div className="space-y-1.5">
          <Label htmlFor="notes" className="text-xs">Observații (opțional)</Label>
          <Textarea id="notes" value={form.notes} onChange={(e) => set({ notes: e.target.value })} />
        </div>

        {/* Semnătură consilier (reused) */}
        <div className="space-y-1.5">
          <Label className={cn('text-xs', err(missing.advisorSig) && 'text-destructive')}>Semnătură consilier</Label>
          {form.advisorSignature ? (
            <div className="flex items-center justify-between rounded-md border bg-muted/40 p-2">
              <span className="text-sm text-green-600 flex items-center gap-1.5"><CheckCircle2 className="h-4 w-4" />Semnătură salvată</span>
              <Button type="button" variant="ghost" size="sm" onClick={() => set({ advisorSignature: '' })}>Schimbă</Button>
            </div>
          ) : (
            <Suspense fallback={<Skeleton className="h-[200px] w-full" />}>
              <SignatureCanvas onSave={(sig) => { set({ advisorSignature: sig }); try { localStorage.setItem(ADVISOR_SIG_KEY, sig) } catch { /* ignore */ } }} onClear={() => set({ advisorSignature: '' })} width={500} height={200} />
            </Suspense>
          )}
        </div>

        {/* Semnătură client (fresh) */}
        <div className="space-y-1.5">
          <Label className={cn('text-xs', err(missing.clientSig) && 'text-destructive')}>Semnătură client</Label>
          {form.clientSignature ? (
            <div className="flex items-center justify-between rounded-md border bg-muted/40 p-2">
              <span className="text-sm text-green-600 flex items-center gap-1.5"><CheckCircle2 className="h-4 w-4" />Semnat</span>
              <Button type="button" variant="ghost" size="sm" onClick={() => set({ clientSignature: '' })}>Șterge</Button>
            </div>
          ) : (
            <Suspense fallback={<Skeleton className="h-[200px] w-full" />}>
              <SignatureCanvas onSave={(sig) => set({ clientSignature: sig })} onClear={() => set({ clientSignature: '' })} width={500} height={200} />
            </Suspense>
          )}
        </div>

        {submitError && <p className="text-sm text-destructive">{submitError}</p>}
        {attempted && !isReturnValid(form, kmStart) && <p className="text-sm text-destructive">Completează câmpurile marcate cu roșu.</p>}

        <Button className={cn('w-full', attempted && !isReturnValid(form, kmStart) && 'bg-destructive hover:bg-destructive')}
          onClick={handleSubmit} disabled={mutation.isPending}>
          {mutation.isPending ? 'Se trimite…' : 'Finalizează retur'}
        </Button>
      </div>
    </div>
  )
}
