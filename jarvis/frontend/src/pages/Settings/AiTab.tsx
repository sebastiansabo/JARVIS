import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Save, Star, Key, RefreshCw, Database, Lock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { settingsApi, type AiModel } from '@/api/settings'
import { toast } from 'sonner'

const SOURCE_LABELS: Record<string, string> = {
  invoice: 'Invoices',
  company: 'Companies',
  department: 'Departments',
  employee: 'Employees',
  transaction: 'Bank Transactions',
  efactura: 'e-Factura',
  event: 'HR Events',
  marketing: 'Marketing Projects',
  approval: 'Approvals',
  tag: 'Tags',
}

export default function AiTab() {
  const queryClient = useQueryClient()

  // ── Queries ──
  const { data: settings, isLoading: settingsLoading } = useQuery({
    queryKey: ['settings', 'ai'],
    queryFn: settingsApi.getAiSettings,
  })

  const { data: models, isLoading: modelsLoading } = useQuery({
    queryKey: ['settings', 'ai-models'],
    queryFn: settingsApi.getAllModels,
  })

  const { data: ragStats, isLoading: statsLoading } = useQuery({
    queryKey: ['settings', 'rag-stats'],
    queryFn: settingsApi.getRagStats,
  })

  const { data: ragPerms } = useQuery({
    queryKey: ['settings', 'rag-source-permissions'],
    queryFn: settingsApi.getRagSourcePermissions,
  })

  // ── Form state ──
  const [form, setForm] = useState({
    ai_rag_enabled: true,
    ai_analytics_enabled: true,
    ai_rag_top_k: 5,
    ai_temperature: 0.7,
    ai_max_tokens: 2048,
  })

  const [apiKeys, setApiKeys] = useState<Record<number, string>>({})
  const [reindexing, setReindexing] = useState<string | null>(null)

  useEffect(() => {
    if (settings) {
      setForm({
        ai_rag_enabled: settings.ai_rag_enabled !== 'false',
        ai_analytics_enabled: settings.ai_analytics_enabled !== 'false',
        ai_rag_top_k: Number(settings.ai_rag_top_k) || 5,
        ai_temperature: Number(settings.ai_temperature) || 0.7,
        ai_max_tokens: Number(settings.ai_max_tokens) || 2048,
      })
    }
  }, [settings])

  // ── Mutations ──
  const saveSettingsMutation = useMutation({
    mutationFn: (data: Record<string, string>) => settingsApi.saveAiSettings(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'ai'] })
      toast.success('AI settings saved')
    },
    onError: () => toast.error('Failed to save settings'),
  })

  const setDefaultMutation = useMutation({
    mutationFn: (id: number) => settingsApi.setDefaultModel(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'ai-models'] })
      toast.success('Default model updated')
    },
    onError: () => toast.error('Failed to set default model'),
  })

  const toggleModelMutation = useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) => settingsApi.toggleModel(id, active),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'ai-models'] })
    },
    onError: () => toast.error('Failed to toggle model'),
  })

  const updateKeyMutation = useMutation({
    mutationFn: ({ id, key }: { id: number; key: string }) => settingsApi.updateModelApiKey(id, key),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'ai-models'] })
      setApiKeys((prev) => ({ ...prev, [id]: '' }))
      toast.success('API key updated')
    },
    onError: () => toast.error('Failed to update API key'),
  })

  const handleSaveSettings = () => {
    saveSettingsMutation.mutate({
      ai_rag_enabled: String(form.ai_rag_enabled),
      ai_analytics_enabled: String(form.ai_analytics_enabled),
      ai_rag_top_k: String(form.ai_rag_top_k),
      ai_temperature: String(form.ai_temperature),
      ai_max_tokens: String(form.ai_max_tokens),
    })
  }

  const handleReindex = async (sourceType?: string) => {
    const label = sourceType ? SOURCE_LABELS[sourceType] || sourceType : 'all sources'
    setReindexing(sourceType || 'all')
    try {
      await settingsApi.reindexRag(sourceType)
      queryClient.invalidateQueries({ queryKey: ['settings', 'rag-stats'] })
      toast.success(`Reindexed ${label}`)
    } catch {
      toast.error(`Failed to reindex ${label}`)
    } finally {
      setReindexing(null)
    }
  }

  // ── Group models by provider ──
  const providerOrder = ['claude', 'openai', 'groq', 'gemini', 'grok']
  const groupedModels = (models || []).reduce<Record<string, AiModel[]>>((acc, m) => {
    ;(acc[m.provider] ||= []).push(m)
    return acc
  }, {})

  const isLoading = settingsLoading || modelsLoading

  if (isLoading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-32 animate-pulse rounded bg-muted" />
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Card 1: LLM Models */}
      <Card>
        <CardHeader>
          <CardTitle>LLM Models</CardTitle>
          <CardDescription>Manage available language models, set defaults, and configure API keys.</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Provider</TableHead>
                <TableHead>Model</TableHead>
                <TableHead className="text-center">Active</TableHead>
                <TableHead className="text-center">Default</TableHead>
                <TableHead className="text-center">API Key</TableHead>
                <TableHead className="text-right">Cost (in/out per 1K)</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {providerOrder
                .filter((p) => groupedModels[p])
                .flatMap((provider) =>
                  groupedModels[provider].map((model) => (
                    <TableRow key={model.id}>
                      <TableCell>
                        <Badge variant="outline" className="capitalize">
                          {model.provider}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div>
                          <p className="text-sm font-medium">{model.display_name}</p>
                          <p className="text-xs text-muted-foreground">{model.model_name}</p>
                        </div>
                      </TableCell>
                      <TableCell className="text-center">
                        <Switch
                          checked={model.is_active}
                          onCheckedChange={(v) => toggleModelMutation.mutate({ id: model.id, active: v })}
                        />
                      </TableCell>
                      <TableCell className="text-center">
                        <Button
                          variant={model.is_default ? 'default' : 'ghost'}
                          size="icon"
                          className="h-8 w-8"
                          disabled={model.is_default || !model.is_active}
                          onClick={() => setDefaultMutation.mutate(model.id)}
                        >
                          <Star className={`h-4 w-4 ${model.is_default ? 'fill-current' : ''}`} />
                        </Button>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1">
                          <Input
                            type="password"
                            placeholder={model.has_api_key ? '••••••••' : 'Enter key'}
                            value={apiKeys[model.id] || ''}
                            onChange={(e) => setApiKeys((prev) => ({ ...prev, [model.id]: e.target.value }))}
                            className="h-8 w-40 text-xs"
                          />
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            disabled={!apiKeys[model.id] || updateKeyMutation.isPending}
                            onClick={() => updateKeyMutation.mutate({ id: model.id, key: apiKeys[model.id] })}
                          >
                            <Key className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </TableCell>
                      <TableCell className="text-right text-xs text-muted-foreground">
                        ${model.cost_per_1k_input} / ${model.cost_per_1k_output}
                      </TableCell>
                    </TableRow>
                  )),
                )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Card 2: RAG Configuration */}
      <Card>
        <CardHeader>
          <CardTitle>RAG Configuration</CardTitle>
          <CardDescription>Configure retrieval-augmented generation and analytics settings.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            <div className="flex items-center justify-between rounded-lg border p-3">
              <div>
                <p className="text-sm font-medium">RAG Enabled</p>
                <p className="text-xs text-muted-foreground">Use indexed documents to answer questions</p>
              </div>
              <Switch
                checked={form.ai_rag_enabled}
                onCheckedChange={(v) => setForm((f) => ({ ...f, ai_rag_enabled: v }))}
              />
            </div>
            <div className="flex items-center justify-between rounded-lg border p-3">
              <div>
                <p className="text-sm font-medium">Analytics Enabled</p>
                <p className="text-xs text-muted-foreground">AI-powered analytics queries over accounting data</p>
              </div>
              <Switch
                checked={form.ai_analytics_enabled}
                onCheckedChange={(v) => setForm((f) => ({ ...f, ai_analytics_enabled: v }))}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="grid gap-2">
              <Label>Top-K Results</Label>
              <Input
                type="number"
                min={1}
                max={20}
                value={form.ai_rag_top_k}
                onChange={(e) => setForm((f) => ({ ...f, ai_rag_top_k: Number(e.target.value) || 5 }))}
              />
              <p className="text-xs text-muted-foreground">Documents retrieved per query (1-20)</p>
            </div>
            <div className="grid gap-2">
              <Label>Temperature</Label>
              <Input
                type="number"
                min={0}
                max={1}
                step={0.1}
                value={form.ai_temperature}
                onChange={(e) => setForm((f) => ({ ...f, ai_temperature: Number(e.target.value) || 0.7 }))}
              />
              <p className="text-xs text-muted-foreground">LLM creativity (0 = precise, 1 = creative)</p>
            </div>
            <div className="grid gap-2">
              <Label>Max Tokens</Label>
              <Input
                type="number"
                min={256}
                max={16384}
                step={256}
                value={form.ai_max_tokens}
                onChange={(e) => setForm((f) => ({ ...f, ai_max_tokens: Number(e.target.value) || 2048 }))}
              />
              <p className="text-xs text-muted-foreground">Maximum response length</p>
            </div>
          </div>

          <Button onClick={handleSaveSettings} disabled={saveSettingsMutation.isPending}>
            <Save className="mr-1.5 h-4 w-4" />
            {saveSettingsMutation.isPending ? 'Saving...' : 'Save Settings'}
          </Button>
        </CardContent>
      </Card>

      {/* Card 3: Data Sources & Indexing */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Data Sources & Indexing</CardTitle>
              <CardDescription>
                {ragStats
                  ? `${ragStats.total_documents} documents indexed • pgvector: ${ragStats.has_pgvector ? 'active' : 'unavailable'}`
                  : 'Loading stats...'}
              </CardDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              disabled={reindexing !== null}
              onClick={() => handleReindex()}
            >
              <RefreshCw className={`mr-1.5 h-4 w-4 ${reindexing === 'all' ? 'animate-spin' : ''}`} />
              Reindex All
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Source</TableHead>
                <TableHead className="text-right">Documents</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {Object.entries(SOURCE_LABELS).map(([key, label]) => {
                const hasAccess = !ragPerms || ragPerms.allowed_sources.includes(key)
                return (
                  <TableRow key={key} className={hasAccess ? '' : 'opacity-50'}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {hasAccess ? (
                          <Database className="h-4 w-4 text-muted-foreground" />
                        ) : (
                          <Lock className="h-4 w-4 text-muted-foreground" />
                        )}
                        <span className="text-sm font-medium">{label}</span>
                        {!hasAccess && (
                          <Badge variant="outline" className="text-xs">No access</Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {statsLoading ? '...' : ragStats?.by_source_type?.[key] ?? 0}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={reindexing !== null || !hasAccess}
                        onClick={() => handleReindex(key)}
                      >
                        <RefreshCw className={`mr-1 h-3.5 w-3.5 ${reindexing === key ? 'animate-spin' : ''}`} />
                        Reindex
                      </Button>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
