import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Image, Key, Save, Loader2, XCircle, Coins, Star } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { carbackgroundApi } from '@/api/carbackground'
import { toast } from 'sonner'

// ════════════════════════════════════════════════
// CarBackground Section (CarPark — AI studio backdrop)
// Admins pick a SET of preferred backdrops and star one as the default. The
// gallery picker offers the preferred set; the default is pre-selected there
// and is the fallback for any non-interactive path.
// ════════════════════════════════════════════════

export function CarBackgroundSettings() {
  const qc = useQueryClient()
  const [apiKey, setApiKey] = useState('')
  // null = untouched (fall back to the saved connector); a value = user's edit.
  const [preferredEdit, setPreferredEdit] = useState<Set<string> | null>(null)
  const [defaultEdit, setDefaultEdit] = useState<string | null>(null)

  const { data: cfg, isLoading } = useQuery({
    queryKey: ['carbackground', 'config'],
    queryFn: carbackgroundApi.getConfig,
  })
  const connector = cfg?.connector
  const configured = cfg?.configured ?? false

  const { data: bgData } = useQuery({
    queryKey: ['carbackground', 'backgrounds'],
    queryFn: carbackgroundApi.listBackgrounds,
  })
  const backgrounds = bgData?.backgrounds ?? []

  const { data: creditsData } = useQuery({
    queryKey: ['carbackground', 'credits'],
    queryFn: carbackgroundApi.credits,
    enabled: configured,
    refetchInterval: configured ? 60_000 : false,
  })

  // Saved baseline: an explicit preferred list, else the single legacy default.
  const savedPreferred =
    connector?.preferred_background_ids ??
    (connector?.background_id ? [connector.background_id] : [])
  const preferred = preferredEdit ?? new Set(savedPreferred)
  const defaultId = defaultEdit ?? connector?.background_id ?? ''

  // Toggle a backdrop in/out of the preferred set. Removing the current default
  // reassigns the star to the first remaining preferred (or clears it) so the
  // "default must be preferred" invariant always holds.
  const togglePreferred = (id: string) => {
    const next = new Set(preferred)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setPreferredEdit(next)
    if (!next.has(id) && defaultId === id) {
      setDefaultEdit(next.values().next().value ?? '')
    }
  }

  // Starring a backdrop makes it the default AND pulls it into the preferred set.
  const starDefault = (id: string) => {
    setDefaultEdit(id)
    if (!preferred.has(id)) {
      const next = new Set(preferred)
      next.add(id)
      setPreferredEdit(next)
    }
  }

  const saveMut = useMutation({
    mutationFn: () =>
      carbackgroundApi.saveConfig({
        ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
        preferred_background_ids: Array.from(preferred),
        // House default is required — only send it when one is starred.
        ...(defaultId ? { background_id: defaultId } : {}),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['carbackground'] })
      setApiKey('')
      setPreferredEdit(null)
      setDefaultEdit(null)
      toast.success('CarBackground settings saved')
    },
    onError: () => toast.error('Failed to save CarBackground settings'),
  })

  if (isLoading) {
    return <div className="h-48 animate-pulse rounded-lg border bg-muted/50" />
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold flex items-center gap-2">
            <Image className="h-5 w-5" /> CarBackground (Fundal Studio)
          </h3>
          <p className="text-sm text-muted-foreground mt-0.5">
            Elimină fundalul din poze și aplică un fundal de studio AI
            (în galeria vehiculului → “Generează studio”).
          </p>
        </div>
        <StatusBadge status={connector?.has_api_key ? 'active' : 'inactive'} />
      </div>

      <div className="rounded-lg border p-4 space-y-3">
        <Label className="text-xs flex items-center gap-1.5">
          <Key className="h-3.5 w-3.5" /> CarBackground API key
          {connector?.has_api_key
            ? <span className="font-normal text-green-600">— configured</span>
            : <span className="font-normal text-muted-foreground">— not set</span>}
        </Label>
        <Input
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder={connector?.has_api_key ? '•••••• (leave blank to keep)' : 'paste CarBackground API key'}
          className="h-8 text-sm"
        />

        <div className="grid gap-1.5">
          <Label className="text-xs">Fundaluri preferate</Label>
          <p className="text-xs text-muted-foreground">
            Bifează fundalurile disponibile în galerie; apasă pe stea pentru cel implicit.
          </p>
          <ul className="divide-y rounded-md border">
            {backgrounds.map((bg) => {
              const isPreferred = preferred.has(bg.id)
              const isDefault = defaultId === bg.id
              return (
                <li key={bg.id} className="flex items-center gap-3 px-3 py-2">
                  <input
                    type="checkbox"
                    aria-label={`Preferă ${bg.name}`}
                    checked={isPreferred}
                    onChange={() => togglePreferred(bg.id)}
                    className="h-4 w-4 shrink-0 accent-violet-600"
                  />
                  <span className="min-w-0 flex-1 truncate text-sm">{bg.name}</span>
                  <button
                    type="button"
                    role="radio"
                    aria-checked={isDefault}
                    aria-label={`Implicit: ${bg.name}`}
                    onClick={() => starDefault(bg.id)}
                    title={isDefault ? 'Fundal implicit' : 'Setează ca implicit'}
                    className={`rounded p-1 transition ${isDefault ? 'text-amber-500' : 'text-muted-foreground hover:text-amber-500'}`}
                  >
                    <Star className={`h-4 w-4 ${isDefault ? 'fill-amber-400' : ''}`} />
                  </button>
                </li>
              )
            })}
            {backgrounds.length === 0 && (
              <li className="px-3 py-2 text-sm text-muted-foreground">
                Niciun fundal disponibil (verifică cheia API).
              </li>
            )}
          </ul>
        </div>

        <div className="flex items-center justify-between pt-1">
          <div className="flex items-center gap-1.5 text-sm">
            <Coins className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">Credite rămase:</span>
            <span className="font-medium">{creditsData?.balance ?? '—'}</span>
          </div>
          <Button size="sm" onClick={() => saveMut.mutate()} disabled={saveMut.isPending}>
            {saveMut.isPending ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Save className="mr-1 h-3.5 w-3.5" />}
            Salvează
          </Button>
        </div>

        {connector?.last_error && (
          <div className="rounded border border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950 p-2.5 flex items-start gap-2">
            <XCircle className="h-4 w-4 text-red-500 mt-0.5 shrink-0" />
            <p className="text-xs text-red-700 dark:text-red-300">{connector.last_error}</p>
          </div>
        )}
      </div>
    </div>
  )
}
