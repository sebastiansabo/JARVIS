import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Save, Send, Bell, Newspaper } from 'lucide-react'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { settingsApi } from '@/api/settings'
import { toast } from 'sonner'

export default function NotificationsTab() {
  const queryClient = useQueryClient()

  const { data: settings, isLoading } = useQuery({
    queryKey: ['settings', 'notifications'],
    queryFn: settingsApi.getNotificationSettings,
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
    // Daily digest
    daily_digest_enabled: false,
    daily_digest_recipients: 'admins',
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
        daily_digest_enabled: String(settings.daily_digest_enabled) === 'true',
        daily_digest_recipients: settings.daily_digest_recipients || 'admins',
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
    saveMutation.mutate({
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
      daily_digest_enabled: String(form.daily_digest_enabled),
      daily_digest_recipients: form.daily_digest_recipients,
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

      {/* Daily Digest */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Newspaper className="h-5 w-5" />
            Daily Digest
          </CardTitle>
          <CardDescription>AI-generated morning summary with key metrics, pending items, and anomalies. Runs daily at 8:00 AM UTC.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Enable Daily Digest</p>
              <p className="text-xs text-muted-foreground">Send a morning summary notification to selected users</p>
            </div>
            <Switch
              checked={form.daily_digest_enabled}
              onCheckedChange={(v) => setForm({ ...form, daily_digest_enabled: v })}
            />
          </div>
          {form.daily_digest_enabled && (
            <div className="grid gap-1.5 border-l-2 border-muted pl-4">
              <Label className="text-xs font-medium">Recipients</Label>
              <Select
                value={form.daily_digest_recipients}
                onValueChange={(v) => setForm({ ...form, daily_digest_recipients: v })}
              >
                <SelectTrigger className="w-48">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="admins">Admins only</SelectItem>
                  <SelectItem value="managers">Admins & Managers</SelectItem>
                  <SelectItem value="all">All active users</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">Who receives the daily digest notification</p>
            </div>
          )}
        </CardContent>
      </Card>

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
