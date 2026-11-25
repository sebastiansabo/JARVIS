import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Lock, Bell } from 'lucide-react'
import { toast } from 'sonner'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Skeleton } from '@/components/ui/skeleton'
import { notificationsApi } from '@/api/notifications'
import type {
  NotificationChannel, NotificationPreferencesView,
} from '@/types/notifications'

const CHANNEL_LABELS: Record<NotificationChannel, string> = {
  in_app: 'În app',
  push: 'Push',
  email: 'Email',
  sms: 'SMS',
}

const QUERY_KEY = ['notification-preferences']

export default function NotificationPreferencesPanel() {
  const queryClient = useQueryClient()
  const { data, isLoading, isError } = useQuery({
    queryKey: QUERY_KEY,
    queryFn: notificationsApi.getPreferences,
  })

  const mutation = useMutation({
    mutationFn: notificationsApi.updatePreference,
    onError: (err: unknown) => {
      toast.error(err instanceof Error ? err.message : 'Nu am putut salva preferința')
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    },
  })

  const handleToggle = (slug: string, channel: NotificationChannel, next: boolean) => {
    if (!data) return
    const updated = { ...data.preferences[slug], [channel]: next }
    // Optimistic update so the switch responds instantly.
    queryClient.setQueryData<NotificationPreferencesView>(QUERY_KEY, (old) =>
      old ? { ...old, preferences: { ...old.preferences, [slug]: updated } } : old,
    )
    mutation.mutate({
      category_slug: slug,
      in_app_enabled: updated.in_app,
      push_enabled: updated.push,
      email_enabled: updated.email,
      sms_enabled: updated.sms,
    })
  }

  if (isLoading) {
    return (
      <Card>
        <CardHeader><Skeleton className="h-6 w-40" /></CardHeader>
        <CardContent className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-8 w-full" />)}
        </CardContent>
      </Card>
    )
  }

  if (isError || !data) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          Nu am putut încărca preferințele de notificare.
        </CardContent>
      </Card>
    )
  }

  const { categories, preferences, channels, has_phone } = data

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Bell className="h-5 w-5" /> Notificări
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Alege pe ce canale primești fiecare tip de notificare. Categoriile
          obligatorii (<Lock className="inline h-3 w-3" />) nu pot fi dezactivate.
          Livrarea pe Email și SMS se activează în curând.
        </p>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <div className="min-w-[32rem]">
            {/* header */}
            <div className="grid grid-cols-[1fr_repeat(4,3.25rem)] gap-2 px-2 pb-2 border-b text-xs font-medium text-muted-foreground">
              <div>Categorie</div>
              {channels.map((ch) => (
                <div key={ch} className="text-center">{CHANNEL_LABELS[ch]}</div>
              ))}
            </div>
            {/* rows */}
            {categories.map((cat) => {
              const flags = preferences[cat.slug]
              return (
                <div
                  key={cat.slug}
                  className="grid grid-cols-[1fr_repeat(4,3.25rem)] gap-2 items-center px-2 py-2 border-b last:border-b-0 hover:bg-muted/40"
                >
                  <div className="flex items-center gap-1.5 text-sm">
                    <span>{cat.name}</span>
                    {cat.mandatory && (
                      <Lock
                        className="h-3.5 w-3.5 text-muted-foreground shrink-0"
                        aria-label="Obligatoriu"
                      />
                    )}
                  </div>
                  {channels.map((ch) => {
                    const smsNoPhone = ch === 'sms' && !has_phone
                    const disabled = cat.mandatory || smsNoPhone
                    const title = cat.mandatory
                      ? 'Obligatoriu — nu poate fi dezactivat'
                      : smsNoPhone
                        ? 'Adaugă un număr de telefon în profil pentru SMS'
                        : undefined
                    return (
                      <div key={ch} className="flex justify-center" title={title}>
                        <Switch
                          checked={!!flags?.[ch]}
                          disabled={disabled}
                          onCheckedChange={(v) => handleToggle(cat.slug, ch, v)}
                          aria-label={`${cat.name} — ${CHANNEL_LABELS[ch]}`}
                        />
                      </div>
                    )
                  })}
                </div>
              )
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
