import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Image, Key, Save, Loader2, XCircle, Coins } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { carbackgroundApi } from '@/api/carbackground'
import { toast } from 'sonner'

// ════════════════════════════════════════════════
// CarBackground Section (CarPark — AI studio backdrop)
// ════════════════════════════════════════════════

export function CarBackgroundSettings() {
  const qc = useQueryClient()
  const [apiKey, setApiKey] = useState('')
  // null = untouched (fall back to the saved value); any string = user's choice.
  const [backgroundId, setBackgroundId] = useState<string | null>(null)

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

  // null (untouched) → fall back to the saved value. Use ?? so a user picking
  // the empty placeholder isn't conflated with "untouched".
  const selectedBackgroundId = backgroundId ?? connector?.background_id ?? ''

  const saveMut = useMutation({
    mutationFn: () =>
      carbackgroundApi.saveConfig({
        ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
        // House backdrop is required — never wipe it with an empty string.
        ...(selectedBackgroundId ? { background_id: selectedBackgroundId } : {}),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['carbackground'] })
      setApiKey('')
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

        <div className="grid gap-1.5 max-w-xs">
          <Label htmlFor="cbg-backdrop" className="text-xs">Fundal studio</Label>
          <select
            id="cbg-backdrop"
            aria-label="Fundal studio"
            value={selectedBackgroundId}
            onChange={(e) => setBackgroundId(e.target.value)}
            className="h-8 rounded-md border bg-background px-2 text-sm"
          >
            <option value="">— alege un fundal —</option>
            {backgrounds.map((bg) => (
              <option key={bg.id} value={bg.id}>{bg.name}</option>
            ))}
          </select>
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
