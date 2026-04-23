import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Save, Send, Bell, Newspaper, Smartphone, Trash2, Plus, Clock, Calendar, Play } from 'lucide-react'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { settingsApi } from '@/api/settings'
import type { PushCategory } from '@/api/settings'
import { toast } from 'sonner'

export default function NotificationsTab() {
  const queryClient = useQueryClient()

  const { data: settings, isLoading } = useQuery({
    queryKey: ['settings', 'notifications'],
    queryFn: settingsApi.getNotificationSettings,
    staleTime: 10 * 60_000,
  })

  const [form, setForm] = useState({
    smtp_host: '',
    smtp_port: '',
    smtp_tls: true,
    smtp_username: '',
    smtp_password: '',
    from_email: '',
    from_name: '',
    notify_on_allocation: false,
    global_cc: '',
    // Smart alerts
    smart_alerts_enabled: true,
    smart_kpi_alerts_enabled: true,
    smart_budget_alerts_enabled: true,
    smart_invoice_anomaly_enabled: true,
    smart_efactura_backlog_enabled: true,
    smart_efactura_backlog_threshold: '50',
    smart_alert_cooldown_hours: '24',
    smart_invoice_anomaly_sigma: '2',
    // Commit digest
    commit_digest_daily_enabled: true,
    commit_digest_daily_recipients: '',
    commit_digest_daily_time: '08:00',
    commit_digest_weekly_enabled: true,
    commit_digest_weekly_recipients: '',
    commit_digest_weekly_day: '5',
    commit_digest_weekly_time: '17:00',
    commit_digest_monthly_enabled: true,
    commit_digest_monthly_recipients: '',
    commit_digest_monthly_day: '1',
    commit_digest_monthly_time: '08:00',
    // Pontaje digest
    pontaje_digest_enabled: false,
    pontaje_digest_daily_enabled: true,
    pontaje_digest_daily_recipients: '',
    pontaje_digest_daily_time: '10:30',
    pontaje_digest_monthly_enabled: true,
    pontaje_digest_monthly_recipients: '',
    pontaje_digest_monthly_day: '1',
    // HR Weekly Digest
    hr_weekly_digest_enabled: false,
    hr_weekly_digest_recipients: '',
  })

  const [testEmail, setTestEmail] = useState('')

  useEffect(() => {
    if (settings && typeof settings === 'object') {
      setForm({
        smtp_host: settings.smtp_host || '',
        smtp_port: settings.smtp_port || '',
        smtp_tls: String(settings.smtp_tls) === 'true',
        smtp_username: settings.smtp_username || '',
        smtp_password: settings.smtp_password || '',
        from_email: settings.from_email || '',
        from_name: settings.from_name || '',
        notify_on_allocation: String(settings.notify_on_allocation) === 'true',
        global_cc: settings.global_cc || '',
        smart_alerts_enabled: String(settings.smart_alerts_enabled ?? 'true') === 'true',
        smart_kpi_alerts_enabled: String(settings.smart_kpi_alerts_enabled ?? 'true') === 'true',
        smart_budget_alerts_enabled: String(settings.smart_budget_alerts_enabled ?? 'true') === 'true',
        smart_invoice_anomaly_enabled: String(settings.smart_invoice_anomaly_enabled ?? 'true') === 'true',
        smart_efactura_backlog_enabled: String(settings.smart_efactura_backlog_enabled ?? 'true') === 'true',
        smart_efactura_backlog_threshold: settings.smart_efactura_backlog_threshold || '50',
        smart_alert_cooldown_hours: settings.smart_alert_cooldown_hours || '24',
        smart_invoice_anomaly_sigma: settings.smart_invoice_anomaly_sigma || '2',
        commit_digest_daily_enabled: String(settings.commit_digest_daily_enabled ?? 'true') === 'true',
        commit_digest_daily_recipients: settings.commit_digest_daily_recipients || '',
        commit_digest_daily_time: settings.commit_digest_daily_time || '08:00',
        commit_digest_weekly_enabled: String(settings.commit_digest_weekly_enabled ?? 'true') === 'true',
        commit_digest_weekly_recipients: settings.commit_digest_weekly_recipients || '',
        commit_digest_weekly_day: settings.commit_digest_weekly_day || '5',
        commit_digest_weekly_time: settings.commit_digest_weekly_time || '17:00',
        commit_digest_monthly_enabled: String(settings.commit_digest_monthly_enabled ?? 'true') === 'true',
        commit_digest_monthly_recipients: settings.commit_digest_monthly_recipients || '',
        commit_digest_monthly_day: settings.commit_digest_monthly_day || '1',
        commit_digest_monthly_time: settings.commit_digest_monthly_time || '08:00',
        pontaje_digest_enabled: String(settings.pontaje_digest_enabled) === 'true',
        pontaje_digest_daily_enabled: String(settings.pontaje_digest_daily_enabled ?? 'true') === 'true',
        pontaje_digest_daily_recipients: settings.pontaje_digest_daily_recipients || '',
        pontaje_digest_daily_time: settings.pontaje_digest_daily_time || '10:30',
        pontaje_digest_monthly_enabled: String(settings.pontaje_digest_monthly_enabled ?? 'true') === 'true',
        pontaje_digest_monthly_recipients: settings.pontaje_digest_monthly_recipients || '',
        pontaje_digest_monthly_day: settings.pontaje_digest_monthly_day || '1',
        hr_weekly_digest_enabled: String(settings.hr_weekly_digest_enabled) === 'true',
        hr_weekly_digest_recipients: settings.hr_weekly_digest_recipients || '',
      })
    }
  }, [settings])

  const saveMutation = useMutation({
    mutationFn: (data: Record<string, string | boolean>) => settingsApi.saveNotificationSettings(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'notifications'] })
      toast.success('Settings saved')
    },
    onError: () => toast.error('Failed to save settings'),
  })

  const testMutation = useMutation({
    mutationFn: (email: string) => settingsApi.testEmail({ to: email }),
    onSuccess: () => toast.success('Test email sent'),
    onError: () => toast.error('Failed to send test email'),
  })

  const handleSave = () => {
    return saveMutation.mutateAsync({
      smtp_host: form.smtp_host,
      smtp_port: form.smtp_port,
      smtp_tls: String(form.smtp_tls),
      smtp_username: form.smtp_username,
      smtp_password: form.smtp_password,
      from_email: form.from_email,
      from_name: form.from_name,
      notify_on_allocation: String(form.notify_on_allocation),
      global_cc: form.global_cc,
      smart_alerts_enabled: String(form.smart_alerts_enabled),
      smart_kpi_alerts_enabled: String(form.smart_kpi_alerts_enabled),
      smart_budget_alerts_enabled: String(form.smart_budget_alerts_enabled),
      smart_invoice_anomaly_enabled: String(form.smart_invoice_anomaly_enabled),
      smart_efactura_backlog_enabled: String(form.smart_efactura_backlog_enabled),
      smart_efactura_backlog_threshold: form.smart_efactura_backlog_threshold,
      smart_alert_cooldown_hours: form.smart_alert_cooldown_hours,
      smart_invoice_anomaly_sigma: form.smart_invoice_anomaly_sigma,
      commit_digest_daily_enabled: String(form.commit_digest_daily_enabled),
      commit_digest_daily_recipients: form.commit_digest_daily_recipients,
      commit_digest_daily_time: form.commit_digest_daily_time,
      commit_digest_weekly_enabled: String(form.commit_digest_weekly_enabled),
      commit_digest_weekly_recipients: form.commit_digest_weekly_recipients,
      commit_digest_weekly_day: form.commit_digest_weekly_day,
      commit_digest_weekly_time: form.commit_digest_weekly_time,
      commit_digest_monthly_enabled: String(form.commit_digest_monthly_enabled),
      commit_digest_monthly_recipients: form.commit_digest_monthly_recipients,
      commit_digest_monthly_day: form.commit_digest_monthly_day,
      commit_digest_monthly_time: form.commit_digest_monthly_time,
      pontaje_digest_enabled: String(form.pontaje_digest_enabled),
      pontaje_digest_daily_enabled: String(form.pontaje_digest_daily_enabled),
      pontaje_digest_daily_recipients: form.pontaje_digest_daily_recipients,
      pontaje_digest_daily_time: form.pontaje_digest_daily_time,
      pontaje_digest_monthly_enabled: String(form.pontaje_digest_monthly_enabled),
      pontaje_digest_monthly_recipients: form.pontaje_digest_monthly_recipients,
      pontaje_digest_monthly_day: form.pontaje_digest_monthly_day,
      hr_weekly_digest_enabled: String(form.hr_weekly_digest_enabled),
      hr_weekly_digest_recipients: form.hr_weekly_digest_recipients,
    })
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-24 animate-pulse rounded bg-muted" />
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* SMTP Configuration */}
      <Card>
        <CardHeader>
          <CardTitle>SMTP Configuration</CardTitle>
          <CardDescription>Configure the email server for sending notifications.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label>SMTP Host</Label>
              <Input value={form.smtp_host} onChange={(e) => setForm({ ...form, smtp_host: e.target.value })} placeholder="smtp.example.com" />
            </div>
            <div className="grid gap-2">
              <Label>SMTP Port</Label>
              <Input value={form.smtp_port} onChange={(e) => setForm({ ...form, smtp_port: e.target.value })} placeholder="587" />
            </div>
            <div className="grid gap-2">
              <Label>Username</Label>
              <Input value={form.smtp_username} onChange={(e) => setForm({ ...form, smtp_username: e.target.value })} />
            </div>
            <div className="grid gap-2">
              <Label>Password</Label>
              <Input type="password" value={form.smtp_password} onChange={(e) => setForm({ ...form, smtp_password: e.target.value })} />
            </div>
            <div className="grid gap-2">
              <Label>From Email</Label>
              <Input value={form.from_email} onChange={(e) => setForm({ ...form, from_email: e.target.value })} placeholder="noreply@example.com" />
            </div>
            <div className="grid gap-2">
              <Label>From Name</Label>
              <Input value={form.from_name} onChange={(e) => setForm({ ...form, from_name: e.target.value })} placeholder="JARVIS" />
            </div>
          </div>
          <div className="mt-4 flex items-center gap-2">
            <Switch checked={form.smtp_tls} onCheckedChange={(v) => setForm({ ...form, smtp_tls: v })} />
            <Label>Use TLS</Label>
          </div>
        </CardContent>
      </Card>

      {/* Notification Preferences */}
      <Card>
        <CardHeader>
          <CardTitle>Preferences</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Allocation Notifications</p>
              <p className="text-xs text-muted-foreground">Send email when invoice is allocated to a department</p>
            </div>
            <Switch
              checked={form.notify_on_allocation}
              onCheckedChange={(v) => setForm({ ...form, notify_on_allocation: v })}
            />
          </div>
          <div className="grid gap-2">
            <Label>Global CC Address</Label>
            <Input value={form.global_cc} onChange={(e) => setForm({ ...form, global_cc: e.target.value })} placeholder="cc@example.com" />
          </div>
        </CardContent>
      </Card>

      {/* Smart Alerts */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bell className="h-5 w-5" />
            Smart Alerts
          </CardTitle>
          <CardDescription>Automated alerts for KPIs, budgets, invoices, and e-Factura. Checks run every 4 hours.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Enable Smart Alerts</p>
              <p className="text-xs text-muted-foreground">Master switch for all automated alerts</p>
            </div>
            <Switch
              checked={form.smart_alerts_enabled}
              onCheckedChange={(v) => setForm({ ...form, smart_alerts_enabled: v })}
            />
          </div>

          {form.smart_alerts_enabled && (
            <div className="space-y-4 border-l-2 border-muted pl-4">
              {/* KPI Alerts */}
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium">KPI Threshold Alerts</p>
                  <p className="text-xs text-muted-foreground">Notify project owners when KPIs breach warning/critical thresholds</p>
                </div>
                <Switch
                  checked={form.smart_kpi_alerts_enabled}
                  onCheckedChange={(v) => setForm({ ...form, smart_kpi_alerts_enabled: v })}
                />
              </div>

              {/* Budget Alerts */}
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium">Budget Utilization Alerts</p>
                  <p className="text-xs text-muted-foreground">Notify when budget lines reach 80% or exceed 100%</p>
                </div>
                <Switch
                  checked={form.smart_budget_alerts_enabled}
                  onCheckedChange={(v) => setForm({ ...form, smart_budget_alerts_enabled: v })}
                />
              </div>

              {/* Invoice Anomaly */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">Invoice Anomaly Detection</p>
                    <p className="text-xs text-muted-foreground">Alert admins when invoice amounts are unusually high or low</p>
                  </div>
                  <Switch
                    checked={form.smart_invoice_anomaly_enabled}
                    onCheckedChange={(v) => setForm({ ...form, smart_invoice_anomaly_enabled: v })}
                  />
                </div>
                {form.smart_invoice_anomaly_enabled && (
                  <div className="grid gap-1.5 pl-4">
                    <Label className="text-xs">Sensitivity (standard deviations)</Label>
                    <Input
                      type="number"
                      min="1"
                      max="5"
                      step="0.5"
                      className="h-8 w-24 text-sm"
                      value={form.smart_invoice_anomaly_sigma}
                      onChange={(e) => setForm({ ...form, smart_invoice_anomaly_sigma: e.target.value })}
                    />
                    <p className="text-xs text-muted-foreground">Lower = more sensitive. Default: 2</p>
                  </div>
                )}
              </div>

              {/* e-Factura Backlog */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">e-Factura Backlog Alert</p>
                    <p className="text-xs text-muted-foreground">Alert admins when unallocated e-Factura invoices pile up</p>
                  </div>
                  <Switch
                    checked={form.smart_efactura_backlog_enabled}
                    onCheckedChange={(v) => setForm({ ...form, smart_efactura_backlog_enabled: v })}
                  />
                </div>
                {form.smart_efactura_backlog_enabled && (
                  <div className="grid gap-1.5 pl-4">
                    <Label className="text-xs">Threshold (unallocated count)</Label>
                    <Input
                      type="number"
                      min="5"
                      max="500"
                      className="h-8 w-24 text-sm"
                      value={form.smart_efactura_backlog_threshold}
                      onChange={(e) => setForm({ ...form, smart_efactura_backlog_threshold: e.target.value })}
                    />
                    <p className="text-xs text-muted-foreground">Alert when unallocated invoices exceed this number. Default: 50</p>
                  </div>
                )}
              </div>

              {/* Cooldown */}
              <div className="grid gap-1.5 border-t pt-3">
                <Label className="text-xs font-medium">Alert Cooldown (hours)</Label>
                <Input
                  type="number"
                  min="1"
                  max="168"
                  className="h-8 w-24 text-sm"
                  value={form.smart_alert_cooldown_hours}
                  onChange={(e) => setForm({ ...form, smart_alert_cooldown_hours: e.target.value })}
                />
                <p className="text-xs text-muted-foreground">Minimum hours between repeat alerts for the same issue. Default: 24</p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Commit Digest */}
      <CommitDigestSection form={form} setForm={setForm} onSave={handleSave} saving={saveMutation.isPending} />

      {/* Pontaje Digest */}
      <PontajeDigestSection form={form} setForm={setForm} onSave={handleSave} saving={saveMutation.isPending} />

      {/* HR Weekly Digest */}
      <HrWeeklyDigestSection form={form} setForm={setForm} onSave={handleSave} saving={saveMutation.isPending} />

      {/* Push Notifications */}
      <PushNotificationsSection />

      {/* Actions */}
      <div className="flex items-center gap-3">
        <Button onClick={handleSave} disabled={saveMutation.isPending}>
          <Save className="mr-1.5 h-4 w-4" />
          {saveMutation.isPending ? 'Saving...' : 'Save Settings'}
        </Button>
        <div className="flex gap-2">
          <Input
            placeholder="test@example.com"
            value={testEmail}
            onChange={(e) => setTestEmail(e.target.value)}
            className="w-56"
          />
          <Button
            variant="outline"
            disabled={!testEmail || testMutation.isPending}
            onClick={() => testMutation.mutate(testEmail)}
          >
            <Send className="mr-1.5 h-4 w-4" />
            Send Test
          </Button>
        </div>
      </div>
    </div>
  )
}


// ============== Commit Digest Section ==============

type DigestPeriod = 'daily' | 'weekly' | 'monthly'

const DIGEST_PERIODS: { key: DigestPeriod; label: string }[] = [
  { key: 'daily', label: 'Zilnic' },
  { key: 'weekly', label: 'Săptămânal' },
  { key: 'monthly', label: 'Lunar' },
]

function CommitDigestSection({
  form,
  setForm,
  onSave,
  saving,
}: {
  form: Record<string, any>
  setForm: (f: any) => void
  onSave: () => Promise<any>
  saving: boolean
}) {
  const [triggering, setTriggering] = useState<DigestPeriod | null>(null)
  const [status, setStatus] = useState<Record<string, { last_sent: string | null; commit_count: number }>>({})

  useEffect(() => {
    fetch('/api/commit-digest/status')
      .then((r) => r.json())
      .then((data) => setStatus(data))
      .catch(() => {})
  }, [])

  const saveAndTrigger = async (period: DigestPeriod) => {
    await onSave()
    setTriggering(period)
    try {
      const res = await fetch('/api/commit-digest/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ period }),
      })
      const data = await res.json()
      if (data.success) {
        toast.success(`${period} digest trimis`)
      } else {
        toast.error(data.error || 'Failed to trigger digest')
      }
    } catch {
      toast.error('Failed to trigger digest')
    } finally {
      setTriggering(null)
    }
  }

  const formatLastSent = (iso: string | null, count: number) => {
    if (!iso) return 'Niciodată'
    try {
      const d = new Date(iso)
      const day = d.getDate()
      const month = d.toLocaleString('ro-RO', { month: 'short' })
      return `${day} ${month} — ${count} commit-uri`
    } catch {
      return iso
    }
  }

  const WEEKDAYS = [
    { value: '1', label: 'Luni' },
    { value: '2', label: 'Marți' },
    { value: '3', label: 'Miercuri' },
    { value: '4', label: 'Joi' },
    { value: '5', label: 'Vineri' },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Newspaper className="h-5 w-5" />
          Commit Digest
        </CardTitle>
        <CardDescription>
          Rezumate AI ale commit-urilor.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {DIGEST_PERIODS.map(({ key, label }) => {
          const enabledKey = `commit_digest_${key}_enabled` as string
          const recipientsKey = `commit_digest_${key}_recipients` as string
          const timeKey = `commit_digest_${key}_time` as string
          const dayKey = key === 'weekly' ? 'commit_digest_weekly_day' : key === 'monthly' ? 'commit_digest_monthly_day' : ''
          const enabled = form[enabledKey]
          const periodStatus = status[key]

          return (
            <div key={key} className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium">{label}</p>
                  {periodStatus && (
                    <p className="text-xs text-muted-foreground">
                      Ultima trimitere: {formatLastSent(periodStatus.last_sent, periodStatus.commit_count)}
                    </p>
                  )}
                </div>
                <Switch
                  checked={enabled}
                  onCheckedChange={(v) => setForm({ ...form, [enabledKey]: v })}
                />
              </div>

              {enabled && (
                <div className="space-y-3 border-l-2 border-muted pl-4">
                  <div className="grid gap-1.5">
                    <Label className="text-xs font-medium">Destinatari (comma-separated)</Label>
                    <Input
                      value={form[recipientsKey]}
                      onChange={(e) => setForm({ ...form, [recipientsKey]: e.target.value })}
                      placeholder="email1@company.com, email2@company.com"
                    />
                    <p className="text-xs text-muted-foreground">Lasă gol pentru destinatarii impliciți din script</p>
                  </div>
                  <div className="flex items-center gap-3">
                    {key === 'weekly' && (
                      <div className="grid gap-1">
                        <Label className="text-xs">Ziua</Label>
                        <Select
                          value={form[dayKey]}
                          onValueChange={(v) => setForm({ ...form, [dayKey]: v })}
                        >
                          <SelectTrigger className="h-8 w-28 text-sm">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {WEEKDAYS.map((wd) => (
                              <SelectItem key={wd.value} value={wd.value}>
                                {wd.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    )}
                    {key === 'monthly' && (
                      <div className="grid gap-1">
                        <Label className="text-xs">Ziua din lună</Label>
                        <Select
                          value={form[dayKey]}
                          onValueChange={(v) => setForm({ ...form, [dayKey]: v })}
                        >
                          <SelectTrigger className="h-8 w-28 text-sm">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {[1, 2, 3, 5, 10, 15].map((d) => (
                              <SelectItem key={d} value={String(d)}>
                                {d === 1 ? '1 (prima zi)' : `${d}`}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    )}
                    <div className="grid gap-1">
                      <Label className="text-xs">Ora (Romania)</Label>
                      <Input
                        type="time"
                        className="h-8 w-28 text-sm"
                        value={form[timeKey]}
                        onChange={(e) => setForm({ ...form, [timeKey]: e.target.value })}
                      />
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={triggering !== null}
                    onClick={() => saveAndTrigger(key)}
                  >
                    <Play className="mr-1.5 h-3.5 w-3.5" />
                    {triggering === key ? 'Se trimite...' : 'Trimite Acum'}
                  </Button>
                </div>
              )}

              {key !== 'monthly' && <div className="border-t" />}
            </div>
          )
        })}

        {/* Save button inside card */}
        <div className="border-t pt-3">
          <Button size="sm" onClick={onSave} disabled={saving}>
            <Save className="mr-1.5 h-3.5 w-3.5" />
            {saving ? 'Se salvează...' : 'Salvează Setări Commit'}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}


// ============== Pontaje Digest Section ==============

function PontajeDigestSection({
  form, setForm, onSave, saving,
}: {
  form: Record<string, any>
  setForm: (f: any) => void
  onSave: () => Promise<any>
  saving: boolean
}) {
  const [triggering, setTriggering] = useState<'daily' | 'monthly' | null>(null)

  const saveAndTrigger = async (type: 'daily' | 'monthly') => {
    await onSave()
    setTriggering(type)
    try {
      const endpoint = type === 'daily'
        ? '/biostar/api/trigger-daily-digest'
        : '/biostar/api/trigger-monthly-digest'
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'X-Admin-Token': 'jarvis-trigger-2026' },
      })
      const data = await res.json()
      if (data.success) {
        toast.success(`${type === 'daily' ? 'Zilnic' : 'Lunar'} digest trimis`)
      } else {
        toast.error(data.error || 'Failed to trigger digest')
      }
    } catch {
      toast.error('Failed to trigger digest')
    } finally {
      setTriggering(null)
    }
  }

  const enabled = form.pontaje_digest_enabled

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Clock className="h-5 w-5" />
          Pontaje Digest
        </CardTitle>
        <CardDescription>
          Rapoarte pontaj trimise pe email. CSV cu prezența angajaților din BioStar.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">Activează Pontaje Digest</p>
            <p className="text-xs text-muted-foreground">Trimite rapoarte CSV de prezență pe email</p>
          </div>
          <Switch
            checked={enabled}
            onCheckedChange={(v) => setForm({ ...form, pontaje_digest_enabled: v })}
          />
        </div>

        {enabled && (
          <>
            {/* Daily Digest */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium">Zilnic</p>
                  <p className="text-xs text-muted-foreground">Pontaj ziua anterioară + check-in azi</p>
                </div>
                <Switch
                  checked={form.pontaje_digest_daily_enabled}
                  onCheckedChange={(v) => setForm({ ...form, pontaje_digest_daily_enabled: v })}
                />
              </div>

              {form.pontaje_digest_daily_enabled && (
                <div className="space-y-3 border-l-2 border-muted pl-4">
                  <div className="grid gap-1.5">
                    <Label className="text-xs font-medium">Destinatari (comma-separated)</Label>
                    <Input
                      value={form.pontaje_digest_daily_recipients}
                      onChange={(e) => setForm({ ...form, pontaje_digest_daily_recipients: e.target.value })}
                      placeholder="hr@company.com, manager@company.com"
                    />
                    <p className="text-xs text-muted-foreground">Lasă gol pentru destinatarii globali</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="grid gap-1">
                      <Label className="text-xs">Ora trimitere (Romania)</Label>
                      <Input
                        type="time"
                        className="h-8 w-28 text-sm"
                        value={form.pontaje_digest_daily_time}
                        onChange={(e) => setForm({ ...form, pontaje_digest_daily_time: e.target.value })}
                      />
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={triggering !== null}
                    onClick={() => saveAndTrigger('daily')}
                  >
                    <Play className="mr-1.5 h-3.5 w-3.5" />
                    {triggering === 'daily' ? 'Se trimite...' : 'Trimite Acum'}
                  </Button>
                </div>
              )}

              <div className="border-t" />
            </div>

            {/* Monthly Digest */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium">Lunar</p>
                  <p className="text-xs text-muted-foreground">Sumar complet luna anterioară, per angajat/zi</p>
                </div>
                <Switch
                  checked={form.pontaje_digest_monthly_enabled}
                  onCheckedChange={(v) => setForm({ ...form, pontaje_digest_monthly_enabled: v })}
                />
              </div>

              {form.pontaje_digest_monthly_enabled && (
                <div className="space-y-3 border-l-2 border-muted pl-4">
                  <div className="grid gap-1.5">
                    <Label className="text-xs font-medium">Destinatari (comma-separated)</Label>
                    <Input
                      value={form.pontaje_digest_monthly_recipients}
                      onChange={(e) => setForm({ ...form, pontaje_digest_monthly_recipients: e.target.value })}
                      placeholder="hr@company.com, director@company.com"
                    />
                    <p className="text-xs text-muted-foreground">Lasă gol pentru destinatarii globali</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="grid gap-1">
                      <Label className="text-xs">Ziua din lună</Label>
                      <Select
                        value={form.pontaje_digest_monthly_day}
                        onValueChange={(v) => setForm({ ...form, pontaje_digest_monthly_day: v })}
                      >
                        <SelectTrigger className="h-8 w-28 text-sm">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {[1, 2, 3, 5, 10, 15].map((d) => (
                            <SelectItem key={d} value={String(d)}>
                              {d === 1 ? '1 (prima zi)' : `${d}`}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={triggering !== null}
                    onClick={() => saveAndTrigger('monthly')}
                  >
                    <Calendar className="mr-1.5 h-3.5 w-3.5" />
                    {triggering === 'monthly' ? 'Se trimite...' : 'Trimite Acum'}
                  </Button>
                </div>
              )}
            </div>

            {/* Save button inside the card */}
            <div className="border-t pt-3">
              <Button size="sm" onClick={onSave} disabled={saving}>
                <Save className="mr-1.5 h-3.5 w-3.5" />
                {saving ? 'Se salvează...' : 'Salvează Setări Pontaje'}
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}


// ============== HR Weekly Digest Section ==============

function HrWeeklyDigestSection({
  form, setForm, onSave, saving,
}: {
  form: Record<string, any>
  setForm: (f: any) => void
  onSave: () => Promise<any>
  saving: boolean
}) {
  const [triggering, setTriggering] = useState(false)

  const saveAndTrigger = async () => {
    await onSave()
    setTriggering(true)
    try {
      const res = await fetch('/biostar/api/trigger-hr-weekly-digest', {
        method: 'POST',
        headers: { 'X-Admin-Token': 'jarvis-trigger-2026' },
      })
      const data = await res.json()
      if (data.success) {
        toast.success('HR Weekly Digest trimis')
      } else {
        toast.error(data.error || 'Failed to trigger digest')
      }
    } catch {
      toast.error('Failed to trigger digest')
    } finally {
      setTriggering(false)
    }
  }

  const enabled = form.hr_weekly_digest_enabled

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Newspaper className="h-5 w-5" />
          HR Weekly Digest
        </CardTitle>
        <CardDescription>
          Raport săptămânal HR: concedii YTD, CO rămas, ore lucrate vs potențial — trimis luni dimineața.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">Activează HR Weekly Digest</p>
            <p className="text-xs text-muted-foreground">Trimite raport HTML săptămânal cu metrici HR pe companie</p>
          </div>
          <Switch
            checked={enabled}
            onCheckedChange={(v) => setForm({ ...form, hr_weekly_digest_enabled: v })}
          />
        </div>

        {enabled && (
          <>
            <div className="space-y-3 border-l-2 border-muted pl-4">
              <div className="grid gap-1.5">
                <Label className="text-xs font-medium">Destinatari (comma-separated)</Label>
                <Input
                  value={form.hr_weekly_digest_recipients}
                  onChange={(e) => setForm({ ...form, hr_weekly_digest_recipients: e.target.value })}
                  placeholder="hr@company.com, director@company.com"
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Se trimite automat luni la 10:00 (Romania). Conține: concedii YTD, CO rămas, check-in/out mediu, ore lucrate vs potențial.
              </p>
              <Button
                size="sm"
                variant="outline"
                disabled={triggering}
                onClick={saveAndTrigger}
              >
                <Play className="mr-1.5 h-3.5 w-3.5" />
                {triggering ? 'Se trimite...' : 'Trimite Acum'}
              </Button>
            </div>

            <div className="border-t pt-3">
              <Button size="sm" onClick={onSave} disabled={saving}>
                <Save className="mr-1.5 h-3.5 w-3.5" />
                {saving ? 'Se salvează...' : 'Salvează Setări'}
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}


// ============== Push Notification Manager Section ==============

function PushNotificationsSection() {
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['settings', 'push-manager'],
    queryFn: settingsApi.getPushManagerSettings,
    staleTime: 30_000,
  })

  const pushSettings = data?.settings ?? {}
  const categories = data?.categories ?? []
  const stats = data?.stats

  const [form, setForm] = useState({
    push_global_enabled: true,
    push_quiet_hours_enabled: false,
    push_quiet_hours_start: '22:00',
    push_quiet_hours_end: '07:00',
    push_quiet_hours_allow_critical: true,
    push_global_rate_limit: '20',
    push_retry_count: '1',
    push_default_ttl: '86400',
  })

  const [newCat, setNewCat] = useState<{ slug: string; name: string; priority: PushCategory['priority'] }>({ slug: '', name: '', priority: 'normal' })
  const [showNewCat, setShowNewCat] = useState(false)

  useEffect(() => {
    if (pushSettings && Object.keys(pushSettings).length > 0) {
      setForm({
        push_global_enabled: pushSettings.push_global_enabled !== 'false',
        push_quiet_hours_enabled: pushSettings.push_quiet_hours_enabled === 'true',
        push_quiet_hours_start: pushSettings.push_quiet_hours_start || '22:00',
        push_quiet_hours_end: pushSettings.push_quiet_hours_end || '07:00',
        push_quiet_hours_allow_critical: pushSettings.push_quiet_hours_allow_critical !== 'false',
        push_global_rate_limit: pushSettings.push_global_rate_limit || '20',
        push_retry_count: pushSettings.push_retry_count || '1',
        push_default_ttl: pushSettings.push_default_ttl || '86400',
      })
    }
  }, [pushSettings])

  const saveMutation = useMutation({
    mutationFn: (d: Record<string, string>) => settingsApi.savePushManagerSettings(d),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'push-manager'] })
      toast.success('Push settings saved')
    },
    onError: () => toast.error('Failed to save push settings'),
  })

  const updateCatMutation = useMutation({
    mutationFn: ({ id, ...d }: { id: number } & Partial<PushCategory>) =>
      settingsApi.updatePushCategory(id, d),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['settings', 'push-manager'] }),
    onError: () => toast.error('Failed to update category'),
  })

  const createCatMutation = useMutation({
    mutationFn: (d: Partial<PushCategory>) => settingsApi.createPushCategory(d),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'push-manager'] })
      setShowNewCat(false)
      setNewCat({ slug: '', name: '', priority: 'normal' })
      toast.success('Category created')
    },
    onError: () => toast.error('Failed to create category'),
  })

  const deleteCatMutation = useMutation({
    mutationFn: (id: number) => settingsApi.deletePushCategory(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'push-manager'] })
      toast.success('Category deleted')
    },
    onError: () => toast.error('Failed to delete category'),
  })

  const testPushMutation = useMutation({
    mutationFn: () => settingsApi.testPush(),
    onSuccess: () => toast.success('Test push notification sent'),
    onError: () => toast.error('Failed to send test push'),
  })

  const handleSavePush = () => {
    saveMutation.mutate({
      push_global_enabled: String(form.push_global_enabled),
      push_quiet_hours_enabled: String(form.push_quiet_hours_enabled),
      push_quiet_hours_start: form.push_quiet_hours_start,
      push_quiet_hours_end: form.push_quiet_hours_end,
      push_quiet_hours_allow_critical: String(form.push_quiet_hours_allow_critical),
      push_global_rate_limit: form.push_global_rate_limit,
      push_retry_count: form.push_retry_count,
      push_default_ttl: form.push_default_ttl,
    })
  }

  const ttlHours = Math.round(Number(form.push_default_ttl) / 3600) || 24

  if (isLoading) {
    return <div className="h-32 animate-pulse rounded bg-muted" />
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Smartphone className="h-5 w-5" />
          Push Notifications
        </CardTitle>
        <CardDescription>
          Manage mobile push notification delivery: quiet hours, rate limits, categories, and TTL.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Master toggle */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">Push Notifications Enabled</p>
            <p className="text-xs text-muted-foreground">Master switch — disables all mobile push notifications</p>
          </div>
          <Switch
            checked={form.push_global_enabled}
            onCheckedChange={(v) => setForm({ ...form, push_global_enabled: v })}
          />
        </div>

        {form.push_global_enabled && (
          <>
            {/* Quiet Hours */}
            <div className="space-y-3 border-l-2 border-muted pl-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium">Quiet Hours</p>
                  <p className="text-xs text-muted-foreground">Block non-critical pushes during off-hours (Europe/Bucharest)</p>
                </div>
                <Switch
                  checked={form.push_quiet_hours_enabled}
                  onCheckedChange={(v) => setForm({ ...form, push_quiet_hours_enabled: v })}
                />
              </div>
              {form.push_quiet_hours_enabled && (
                <div className="space-y-3 pl-4">
                  <div className="flex items-center gap-3">
                    <div className="grid gap-1">
                      <Label className="text-xs">Start</Label>
                      <Input
                        type="time"
                        className="h-8 w-28 text-sm"
                        value={form.push_quiet_hours_start}
                        onChange={(e) => setForm({ ...form, push_quiet_hours_start: e.target.value })}
                      />
                    </div>
                    <div className="grid gap-1">
                      <Label className="text-xs">End</Label>
                      <Input
                        type="time"
                        className="h-8 w-28 text-sm"
                        value={form.push_quiet_hours_end}
                        onChange={(e) => setForm({ ...form, push_quiet_hours_end: e.target.value })}
                      />
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Switch
                      checked={form.push_quiet_hours_allow_critical}
                      onCheckedChange={(v) => setForm({ ...form, push_quiet_hours_allow_critical: v })}
                    />
                    <Label className="text-xs">Allow critical notifications during quiet hours</Label>
                  </div>
                </div>
              )}
            </div>

            {/* Rate Limits */}
            <div className="space-y-3 border-l-2 border-muted pl-4">
              <p className="text-sm font-medium">Rate Limits & Delivery</p>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div className="grid gap-1">
                  <Label className="text-xs">Max per user/hour</Label>
                  <Input
                    type="number"
                    min="1"
                    max="100"
                    className="h-8 w-24 text-sm"
                    value={form.push_global_rate_limit}
                    onChange={(e) => setForm({ ...form, push_global_rate_limit: e.target.value })}
                  />
                </div>
                <div className="grid gap-1">
                  <Label className="text-xs">Default TTL (hours)</Label>
                  <Input
                    type="number"
                    min="1"
                    max="672"
                    className="h-8 w-24 text-sm"
                    value={ttlHours}
                    onChange={(e) => setForm({ ...form, push_default_ttl: String(Number(e.target.value) * 3600) })}
                  />
                </div>
                <div className="grid gap-1">
                  <Label className="text-xs">Retry count</Label>
                  <Input
                    type="number"
                    min="0"
                    max="3"
                    className="h-8 w-24 text-sm"
                    value={form.push_retry_count}
                    onChange={(e) => setForm({ ...form, push_retry_count: e.target.value })}
                  />
                </div>
              </div>
            </div>

            {/* Categories */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">Categories</p>
                <Button size="sm" variant="outline" onClick={() => setShowNewCat(!showNewCat)}>
                  <Plus className="mr-1 h-3.5 w-3.5" />
                  Add
                </Button>
              </div>

              {showNewCat && (
                <div className="flex items-end gap-2 rounded border p-3">
                  <div className="grid gap-1">
                    <Label className="text-xs">Slug</Label>
                    <Input
                      className="h-8 w-32 text-sm"
                      placeholder="my_category"
                      value={newCat.slug}
                      onChange={(e) => setNewCat({ ...newCat, slug: e.target.value })}
                    />
                  </div>
                  <div className="grid gap-1">
                    <Label className="text-xs">Name</Label>
                    <Input
                      className="h-8 w-36 text-sm"
                      placeholder="My Category"
                      value={newCat.name}
                      onChange={(e) => setNewCat({ ...newCat, name: e.target.value })}
                    />
                  </div>
                  <div className="grid gap-1">
                    <Label className="text-xs">Priority</Label>
                    <Select value={newCat.priority} onValueChange={(v) => setNewCat({ ...newCat, priority: v as PushCategory['priority'] })}>
                      <SelectTrigger className="h-8 w-28 text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="critical">Critical</SelectItem>
                        <SelectItem value="high">High</SelectItem>
                        <SelectItem value="normal">Normal</SelectItem>
                        <SelectItem value="low">Low</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <Button
                    size="sm"
                    disabled={!newCat.slug || !newCat.name || createCatMutation.isPending}
                    onClick={() => createCatMutation.mutate(newCat)}
                  >
                    {createCatMutation.isPending ? '...' : 'Create'}
                  </Button>
                </div>
              )}

              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[140px]">Name</TableHead>
                      <TableHead className="w-[100px]">Priority</TableHead>
                      <TableHead className="w-[90px]">Limit/hr</TableHead>
                      <TableHead className="w-[80px]">TTL (h)</TableHead>
                      <TableHead className="w-[70px]">24h</TableHead>
                      <TableHead className="w-[60px]">Active</TableHead>
                      <TableHead className="w-[50px]"></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {categories.map((cat) => (
                      <TableRow key={cat.id}>
                        <TableCell>
                          <div>
                            <p className="text-sm font-medium">{cat.name}</p>
                            <p className="text-xs text-muted-foreground">{cat.slug}</p>
                          </div>
                        </TableCell>
                        <TableCell>
                          <Select
                            value={cat.priority}
                            onValueChange={(v) => updateCatMutation.mutate({ id: cat.id, priority: v as PushCategory['priority'] })}
                          >
                            <SelectTrigger className="h-7 w-24 text-xs">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="critical">Critical</SelectItem>
                              <SelectItem value="high">High</SelectItem>
                              <SelectItem value="normal">Normal</SelectItem>
                              <SelectItem value="low">Low</SelectItem>
                            </SelectContent>
                          </Select>
                        </TableCell>
                        <TableCell>
                          <Input
                            type="number"
                            min="0"
                            className="h-7 w-16 text-xs"
                            placeholder="--"
                            value={cat.max_per_hour ?? ''}
                            onChange={(e) => {
                              const val = e.target.value ? Number(e.target.value) : null
                              updateCatMutation.mutate({ id: cat.id, max_per_hour: val })
                            }}
                          />
                        </TableCell>
                        <TableCell>
                          <Input
                            type="number"
                            min="0"
                            className="h-7 w-16 text-xs"
                            placeholder="--"
                            value={cat.ttl_seconds ? Math.round(cat.ttl_seconds / 3600) : ''}
                            onChange={(e) => {
                              const val = e.target.value ? Number(e.target.value) * 3600 : null
                              updateCatMutation.mutate({ id: cat.id, ttl_seconds: val })
                            }}
                          />
                        </TableCell>
                        <TableCell>
                          <span className="text-xs text-muted-foreground">{cat.sends_24h ?? 0}</span>
                        </TableCell>
                        <TableCell>
                          <Switch
                            checked={cat.is_active}
                            onCheckedChange={(v) => updateCatMutation.mutate({ id: cat.id, is_active: v })}
                          />
                        </TableCell>
                        <TableCell>
                          {!cat.is_builtin && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7"
                              onClick={() => deleteCatMutation.mutate(cat.id)}
                            >
                              <Trash2 className="h-3.5 w-3.5 text-destructive" />
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>

            {/* Stats */}
            {stats && (
              <div className="flex gap-6 rounded-md border p-3">
                <div>
                  <p className="text-lg font-bold">{stats.sends_24h ?? 0}</p>
                  <p className="text-xs text-muted-foreground">Pushes (24h)</p>
                </div>
                <div>
                  <p className="text-lg font-bold">{stats.sends_7d ?? 0}</p>
                  <p className="text-xs text-muted-foreground">Pushes (7d)</p>
                </div>
                <div>
                  <p className="text-lg font-bold">{stats.active_devices ?? 0}</p>
                  <p className="text-xs text-muted-foreground">Active devices</p>
                </div>
              </div>
            )}
          </>
        )}

        {/* Save + Test */}
        <div className="flex items-center gap-3 border-t pt-4">
          <Button onClick={handleSavePush} disabled={saveMutation.isPending}>
            <Save className="mr-1.5 h-4 w-4" />
            {saveMutation.isPending ? 'Saving...' : 'Save Push Settings'}
          </Button>
          <Button
            variant="outline"
            disabled={testPushMutation.isPending}
            onClick={() => testPushMutation.mutate()}
          >
            <Smartphone className="mr-1.5 h-4 w-4" />
            {testPushMutation.isPending ? 'Sending...' : 'Send Test Push'}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
