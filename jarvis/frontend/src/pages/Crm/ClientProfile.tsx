import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Building2, Pencil, Save, X, Car, MapPin, Truck, MessageSquare,
  Star, RefreshCw, Search, Loader2, Phone, Mail, Hash, Globe, User,
  Shield, Database, ChevronDown, ChevronUp, Sparkles, Lightbulb,
  AlertTriangle, TrendingUp, Target, Brain, CreditCard, BarChart3,
  ShieldCheck, ChevronRight,
} from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { crmApi, type CrmDeal, type CrmVisit, type FleetVehicle, type ClientInteraction } from '@/api/crm'

function InfoRow({ icon: Icon, label, value, className }: { icon?: React.ElementType; label: string; value: string | number | null | undefined; className?: string }) {
  return (
    <div className={`flex items-start gap-3 py-1.5 ${className || ''}`}>
      {Icon && <Icon className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />}
      <div className="min-w-0 flex-1">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="text-sm font-medium truncate">{value || '—'}</div>
      </div>
    </div>
  )
}



function _fmtCurrency(val: number | undefined | null, currency = 'RON'): string {
  if (!val && val !== 0) return '—'
  return new Intl.NumberFormat('ro-RO', { style: 'decimal', maximumFractionDigits: 0 }).format(val) + ` ${currency}`
}
function _fmtEur(val: number | undefined | null): string {
  if (!val && val !== 0) return ''
  return '~' + new Intl.NumberFormat('ro-RO', { style: 'decimal', maximumFractionDigits: 0 }).format(val) + ' EUR'
}

const CONNECTOR_META: Record<string, { icon: string; label: string }> = {
  anaf: { icon: '🏛️', label: 'ANAF' },
  termene: { icon: '⚖️', label: 'Termene.ro' },
  risco: { icon: '📊', label: 'RisCo' },
  listafirme: { icon: '📋', label: 'ListaFirme' },
  openapi_ro: { icon: '🔌', label: 'OpenAPI.ro' },
  firmeapi: { icon: '⚡', label: 'FirmeAPI' },
}

export default function ClientProfile() {
  const { clientId } = useParams<{ clientId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const id = Number(clientId)

  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<Record<string, string>>({})
  const [cuiInput, setCuiInput] = useState('')
  const [expandedConnector, setExpandedConnector] = useState<string | null>(null)
  const [cuiResults, setCuiResults] = useState<{ cui: string; name: string; address: string; nr_reg: string; source: string }[]>([])
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [aiResearch, setAiResearch] = useState<Record<string, any> | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['crm-client', id],
    queryFn: () => crmApi.getClient(id),
    enabled: !!id,
  })

  const client = data?.client
  const deals = data?.deals ?? []
  const visits = data?.visits ?? []
  const profile = data?.profile
  const fleet = data?.fleet ?? []
  const interactions = data?.interactions ?? []
  const renewalCandidates = data?.renewal_candidates ?? []
  const fiscal = data?.fiscal as Record<string, unknown> | null
  const enrichmentData = data?.enrichment_data ?? {}
  const connectors = data?.connectors ?? []
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const bv = (data as any)?.business_value as {
    score: number; grade: string;
    breakdown: Record<string, { score: number; max: number; [k: string]: unknown }>
  } | undefined

  // Edit mutation
  const editMutation = useMutation({
    mutationFn: (formData: Record<string, string>) => crmApi.updateClient(id, formData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['crm-client', id] })
      toast.success('Client updated')
      setEditing(false)
      setForm({})
    },
    onError: () => toast.error('Failed to update client'),
  })

  // ANAF enrich mutation (CUI optional — server auto-detects from name)
  const enrichMutation = useMutation({
    mutationFn: (cui?: string) => crmApi.enrichClient(id, cui),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['crm-client', id] })
      const correction = (res as Record<string, unknown>).cui_correction as { old_cui: string; new_cui: string; found_name: string; source: string } | undefined
      if (correction) {
        toast.warning(`CUI corectat: ${correction.old_cui} → ${correction.new_cui} (${correction.found_name}, via ${correction.source})`, { duration: 8000 })
      }
      const source = (res as Record<string, unknown>).source as string
      toast.success(source === 'ai' ? 'Date completate via AI (ANAF indisponibil)' : 'Date ANAF actualizate')
      setCuiInput('')
    },
    onError: () => toast.error('Enrichment failed'),
  })

  // Connector-specific enrich mutation (track which connector is loading)
  const [fetchingConnector, setFetchingConnector] = useState<string | null>(null)
  const connectorEnrichMutation = useMutation({
    mutationFn: ({ cui, connectorType }: { cui: string; connectorType: string }) => {
      setFetchingConnector(connectorType)
      return crmApi.enrichFromConnector(id, cui, connectorType)
    },
    onSuccess: (_, vars) => {
      setFetchingConnector(null)
      queryClient.invalidateQueries({ queryKey: ['crm-client', id] })
      toast.success(`${CONNECTOR_META[vars.connectorType]?.label || vars.connectorType} data fetched`)
    },
    onError: (_, vars) => {
      setFetchingConnector(null)
      toast.error(`${CONNECTOR_META[vars.connectorType]?.label || vars.connectorType} fetch failed`)
    },
  })

  // CUI lookup mutation
  const lookupCuiMutation = useMutation({
    mutationFn: () => crmApi.lookupCui(id),
    onSuccess: (res) => {
      if (res.results && res.results.length > 0) {
        setCuiResults(res.results)
        toast.success(`Found ${res.results.length} matching companies`)
      } else {
        toast.info('No companies found. Try entering CUI manually.')
      }
    },
    onError: () => toast.error('CUI lookup failed'),
  })

  // AI research mutation
  const aiResearchMutation = useMutation({
    mutationFn: () => crmApi.aiResearch(id),
    onSuccess: (res) => {
      if (res.research) {
        setAiResearch(res.research)
        queryClient.invalidateQueries({ queryKey: ['crm-client', id] })
        toast.success('AI research complete')
      }
    },
    onError: () => toast.error('AI research failed'),
  })

  // Load existing AI research from enrichment data on first load
  useEffect(() => {
    const existing = enrichmentData?.ai_research as { data?: Record<string, unknown> } | undefined
    if (existing?.data && !aiResearch) {
      setAiResearch(existing.data)
    }
  }, [enrichmentData]) // eslint-disable-line react-hooks/exhaustive-deps

  // Start editing
  const startEdit = () => {
    if (!client) return
    const init: Record<string, string> = {}
    for (const k of ['display_name', 'client_type', 'phone', 'email', 'street', 'city', 'region', 'country', 'company_name', 'responsible', 'nr_reg']) {
      init[k] = (client as unknown as Record<string, unknown>)[k] as string ?? ''
    }
    setForm(init)
    setEditing(true)
  }

  const set = (k: string, v: string) => setForm(prev => ({ ...prev, [k]: v }))

  const cui = profile?.cui || cuiInput.trim()

  if (isLoading) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid grid-cols-2 gap-4">
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
      </div>
    )
  }

  if (!client) {
    return (
      <div className="p-6 text-center">
        <p className="text-muted-foreground">Client not found</p>
        <Button variant="outline" className="mt-4" onClick={() => navigate(-1)}>Go Back</Button>
      </div>
    )
  }

  return (
    <div className="space-y-6 pb-8">
      {/* Breadcrumb Header */}
      <div className="flex items-center justify-between">
        <div>
          <nav className="flex items-center gap-1.5 text-sm mb-1">
            <button
              onClick={() => navigate('/app/sales/crm?tab=clients')}
              className="text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            >
              Clienți
            </button>
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
            <h1 className="text-xl font-bold flex items-center gap-2">
              <Building2 className="h-5 w-5 text-primary" />
              {client.display_name}
            </h1>
          </nav>
          <div className="flex items-center gap-2 ml-[4.5rem]">
            <Badge variant={client.client_type === 'company' ? 'default' : 'secondary'}>{client.client_type}</Badge>
            {profile?.cui && <Badge variant="outline" className="font-mono text-xs">CUI: {profile.cui}</Badge>}
            {profile?.priority && <Badge variant="secondary">{profile.priority}</Badge>}
            {client.is_blacklisted && <Badge variant="destructive">Blacklisted</Badge>}
          </div>
        </div>
        {/* Client tier + score near title */}
        {bv && (() => {
          const tier = (bv as unknown as { tier: string }).tier
          return (
            <div className="flex items-center gap-2">
              <span className={`text-xs font-bold px-2.5 py-1 rounded-full ${
                tier === 'Platinum' ? 'bg-violet-100 text-violet-700' :
                tier === 'Gold' ? 'bg-yellow-100 text-yellow-700' :
                tier === 'Silver' ? 'bg-gray-200 text-gray-700' :
                tier === 'Bronze' ? 'bg-orange-100 text-orange-700' :
                'bg-muted text-muted-foreground'
              }`}>
                {tier}
              </span>
              <span className="text-sm font-mono text-muted-foreground">{bv.score}/100</span>
            </div>
          )
        })()}
        <div className="flex gap-2">
          {editing ? (
            <>
              <Button size="sm" variant="outline" onClick={() => { setEditing(false); setForm({}) }}>
                <X className="h-3.5 w-3.5 mr-1" />Cancel
              </Button>
              <Button size="sm" onClick={() => editMutation.mutate(form)} disabled={editMutation.isPending}>
                <Save className="h-3.5 w-3.5 mr-1" />{editMutation.isPending ? 'Saving...' : 'Save'}
              </Button>
            </>
          ) : (
            <Button size="sm" variant="outline" onClick={startEdit}>
              <Pencil className="h-3.5 w-3.5 mr-1" />Edit Client
            </Button>
          )}
        </div>
      </div>

      {/* Business KPIs strip */}
      {bv && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
          {(() => {
            const pv = bv.breakdown.purchase_value || {} as Record<string, unknown>
            const ret = bv.breakdown.retention || {} as Record<string, unknown>
            const fv = bv.breakdown.fleet_volume || {} as Record<string, unknown>
            const bvExt = bv as unknown as { clv: number; clv_eur: number; annual_revenue: number; annual_revenue_eur: number; total_sales_eur: number; total_margin_eur: number; avg_deal_value_eur: number; years_per_purchase: number; tier: string }
            const kpis = [
              { label: 'Total Sales', value: _fmtCurrency(pv.total_sales as number), sub: _fmtEur(bvExt.total_sales_eur) || `${pv.deal_count || 0} deals` },
              { label: 'Total Margin', value: _fmtCurrency(pv.total_margin as number), sub: `${_fmtEur(bvExt.total_margin_eur)} · ${pv.margin_pct || 0}%` },
              { label: 'Avg Deal Value', value: _fmtCurrency(pv.avg_deal_value as number), sub: _fmtEur(bvExt.avg_deal_value_eur) },
              { label: 'Client Since', value: String(ret.first_deal_date || '—'), sub: `${ret.years_as_client || 0} yrs · ${pv.deal_count || 0} deals` },
              { label: 'Return Rate', value: bvExt.years_per_purchase ? `${bvExt.years_per_purchase} yrs/purchase` : '—', sub: ret.avg_return_months ? `~${ret.avg_return_months}mo interval` : undefined },
              { label: 'Fleet Size', value: String(fv.effective_fleet || 0), sub: 'vehicles' },
              { label: 'Est. CLV', value: _fmtCurrency(bvExt.clv), sub: _fmtEur(bvExt.clv_eur) || `${_fmtCurrency(bvExt.annual_revenue)}/yr` },
            ]
            return kpis.map((kpi) => (
              <div key={kpi.label} className="rounded-lg border bg-card p-2.5 text-center">
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider">{kpi.label}</div>
                <div className="text-sm font-bold mt-0.5">{kpi.value}</div>
                {kpi.sub && <div className="text-[10px] text-muted-foreground">{kpi.sub}</div>}
              </div>
            ))
          })()}
        </div>
      )}

      {/* Contact Info + Profile side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Contact Info */}
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm flex items-center gap-1.5">
                <User className="h-4 w-4" />Contact Information
              </CardTitle>
              {!editing && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs gap-1 text-muted-foreground"
                  disabled={enrichMutation.isPending}
                  onClick={() => enrichMutation.mutate(profile?.cui || undefined)}
                >
                  <RefreshCw className={`h-3 w-3 ${enrichMutation.isPending ? 'animate-spin' : ''}`} />
                  {profile?.cui ? 'ANAF' : 'Auto-detect'}
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {editing ? (
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2">
                  <Label className="text-xs">Display Name</Label>
                  <Input value={form.display_name ?? ''} onChange={e => set('display_name', e.target.value)} />
                </div>
                <div>
                  <Label className="text-xs">Type</Label>
                  <Select value={form.client_type || 'person'} onValueChange={v => set('client_type', v)}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="person">Person</SelectItem>
                      <SelectItem value="company">Company</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">Company</Label>
                  <Input value={form.company_name ?? ''} onChange={e => set('company_name', e.target.value)} />
                </div>
                <div>
                  <Label className="text-xs">Phone</Label>
                  <Input value={form.phone ?? ''} onChange={e => set('phone', e.target.value)} />
                </div>
                <div>
                  <Label className="text-xs">Email</Label>
                  <Input value={form.email ?? ''} onChange={e => set('email', e.target.value)} />
                </div>
                <div>
                  <Label className="text-xs">Nr. Reg</Label>
                  <Input value={form.nr_reg ?? ''} onChange={e => set('nr_reg', e.target.value)} />
                </div>
                <div>
                  <Label className="text-xs">City</Label>
                  <Input value={form.city ?? ''} onChange={e => set('city', e.target.value)} />
                </div>
                <div>
                  <Label className="text-xs">Region</Label>
                  <Input value={form.region ?? ''} onChange={e => set('region', e.target.value)} />
                </div>
                <div>
                  <Label className="text-xs">Country</Label>
                  <Input value={form.country ?? ''} onChange={e => set('country', e.target.value)} />
                </div>
                <div className="col-span-2">
                  <Label className="text-xs">Street</Label>
                  <Input value={form.street ?? ''} onChange={e => set('street', e.target.value)} />
                </div>
                <div className="col-span-2">
                  <Label className="text-xs">Responsible</Label>
                  <Input value={form.responsible ?? ''} onChange={e => set('responsible', e.target.value)} />
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-x-4">
                <InfoRow icon={Building2} label="Company" value={client.company_name} />
                <InfoRow icon={Hash} label="Nr. Reg" value={client.nr_reg} />
                <InfoRow icon={Phone} label="Phone" value={client.phone} />
                <InfoRow icon={Mail} label="Email" value={client.email} />
                <InfoRow icon={MapPin} label="City" value={client.city} />
                <InfoRow icon={MapPin} label="Region" value={client.region} />
                <InfoRow icon={Globe} label="Country" value={client.country} />
                <InfoRow icon={MapPin} label="Street" value={client.street} />
                <InfoRow icon={User} label="Responsible" value={client.responsible} />
                <InfoRow icon={Hash} label="Client Since" value={client.client_since ? new Date(client.client_since).toLocaleDateString('ro-RO') : undefined} />
                <InfoRow label="Sources" value={Object.keys(client.source_flags || {}).filter(k => client.source_flags[k]).join(', ')} className="col-span-2" />
              </div>
            )}
          </CardContent>
        </Card>

        {/* Profile & Scoring */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-1.5">
              <Shield className="h-4 w-4" />Profile & Scoring
            </CardTitle>
          </CardHeader>
          <CardContent>
            {profile ? (
              <div className="grid grid-cols-2 gap-x-4">
                <InfoRow icon={Hash} label="CUI" value={profile.cui} />
                <InfoRow label="Client Type" value={profile.client_type} />
                <InfoRow icon={Globe} label="Country Code" value={profile.country_code} />
                <InfoRow label="Industry" value={profile.industry} />
                <InfoRow label="Legal Form" value={profile.legal_form} />
                <InfoRow label="Priority" value={profile.priority} />
                <InfoRow icon={Star} label="Renewal Score" value={profile.renewal_score != null ? `${profile.renewal_score}/100` : undefined} />
                <InfoRow icon={Truck} label="Fleet Size" value={profile.fleet_size} />
                <InfoRow label="Est. Annual Value" value={profile.estimated_annual_value != null ? `${Number(profile.estimated_annual_value).toLocaleString('ro-RO')} EUR` : undefined} />
                <InfoRow label="Last Scored" value={profile.last_scored_at ? new Date(profile.last_scored_at).toLocaleDateString('ro-RO') : undefined} />
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No profile data yet. Enter a CUI below to start enrichment.</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* AI Company Intelligence */}
      <Card className="border-primary/20 bg-gradient-to-br from-primary/[0.02] to-transparent">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm flex items-center gap-1.5">
              <Brain className="h-4 w-4 text-primary" />Analiza Financiara AI
            </CardTitle>
            <Button
              size="sm" className="h-8"
              onClick={() => aiResearchMutation.mutate()}
              disabled={aiResearchMutation.isPending}
            >
              {aiResearchMutation.isPending ? (
                <><Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />Se analizeaza...</>
              ) : (
                <><Sparkles className="h-3.5 w-3.5 mr-1" />{aiResearch ? 'Re-analizeaza' : 'Analizeaza Compania'}</>
              )}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {aiResearchMutation.isPending && (
            <div className="flex items-center gap-3 p-4 rounded-lg bg-muted/50 animate-pulse">
              <Loader2 className="h-5 w-5 animate-spin text-primary" />
              <div>
                <p className="text-sm font-medium">Analiza financiara pentru {client.display_name}...</p>
                <p className="text-xs text-muted-foreground">Se evalueaza profilul financiar, riscuri, oportunitati si potentialul de flota</p>
              </div>
            </div>
          )}
          {aiResearch && !aiResearch._raw && (
            <div className="space-y-3">
              {/* Overview */}
              {aiResearch.company_overview && (
                <div className="rounded-lg border p-3 bg-background">
                  <p className="text-sm">{String(aiResearch.company_overview)}</p>
                  <div className="flex gap-2 mt-2 flex-wrap">
                    {aiResearch.industry && <Badge variant="secondary" className="text-[10px]">{String(aiResearch.industry)}</Badge>}
                    {aiResearch.company_type && <Badge variant="outline" className="text-[10px]">{String(aiResearch.company_type)}</Badge>}
                    {aiResearch.estimated_size && <Badge variant="outline" className="text-[10px]">{String(aiResearch.estimated_size)}</Badge>}
                    {aiResearch.risk_level && (
                      <Badge variant={aiResearch.risk_level === 'ridicat' ? 'destructive' : aiResearch.risk_level === 'mediu' ? 'secondary' : 'default'} className="text-[10px]">
                        Risc: {String(aiResearch.risk_level)}
                      </Badge>
                    )}
                    {aiResearch.competitive_position && (
                      <Badge variant="outline" className="text-[10px]">{String(aiResearch.competitive_position)}</Badge>
                    )}
                  </div>
                </div>
              )}

              {/* Suggested CUI */}
              {aiResearch.suggested_cui && !profile?.cui && (
                <div className="rounded-lg border border-primary/30 p-3 bg-primary/5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Lightbulb className="h-4 w-4 text-primary" />
                      <span className="text-sm font-medium">CUI identificat: <span className="font-mono">{String(aiResearch.suggested_cui)}</span></span>
                    </div>
                    <Button size="sm" className="h-7 text-xs" onClick={() => {
                      setCuiInput(String(aiResearch.suggested_cui))
                      enrichMutation.mutate(String(aiResearch.suggested_cui))
                    }} disabled={enrichMutation.isPending}>
                      {enrichMutation.isPending ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Search className="h-3 w-3 mr-1" />}
                      Foloseste CUI
                    </Button>
                  </div>
                </div>
              )}

              {/* Financial Profile */}
              {aiResearch.financial_profile && typeof aiResearch.financial_profile === 'object' && (
                <div className="rounded-lg border border-blue-200 dark:border-blue-900 p-3 bg-blue-50/30 dark:bg-blue-950/20">
                  <p className="text-xs font-medium text-blue-700 dark:text-blue-400 mb-2 flex items-center gap-1">
                    <BarChart3 className="h-3 w-3" /> Profil Financiar
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1.5">
                    {(aiResearch.financial_profile as Record<string, string>).estimated_revenue_range && (
                      <div className="flex items-start gap-2">
                        <CreditCard className="h-3.5 w-3.5 mt-0.5 text-blue-500 shrink-0" />
                        <div>
                          <p className="text-[10px] text-muted-foreground">Cifra de afaceri estimata</p>
                          <p className="text-xs font-medium">{String((aiResearch.financial_profile as Record<string, string>).estimated_revenue_range)}</p>
                        </div>
                      </div>
                    )}
                    {(aiResearch.financial_profile as Record<string, string>).profitability_assessment && (
                      <div className="flex items-start gap-2">
                        <TrendingUp className="h-3.5 w-3.5 mt-0.5 text-blue-500 shrink-0" />
                        <div>
                          <p className="text-[10px] text-muted-foreground">Profitabilitate</p>
                          <p className="text-xs font-medium">{String((aiResearch.financial_profile as Record<string, string>).profitability_assessment)}</p>
                        </div>
                      </div>
                    )}
                    {(aiResearch.financial_profile as Record<string, string>).debt_indicators && (
                      <div className="flex items-start gap-2">
                        <AlertTriangle className="h-3.5 w-3.5 mt-0.5 text-blue-500 shrink-0" />
                        <div>
                          <p className="text-[10px] text-muted-foreground">Indicatori de indatorare</p>
                          <p className="text-xs font-medium">{String((aiResearch.financial_profile as Record<string, string>).debt_indicators)}</p>
                        </div>
                      </div>
                    )}
                    {(aiResearch.financial_profile as Record<string, string>).payment_behavior && (
                      <div className="flex items-start gap-2">
                        <ShieldCheck className="h-3.5 w-3.5 mt-0.5 text-blue-500 shrink-0" />
                        <div>
                          <p className="text-[10px] text-muted-foreground">Comportament de plata</p>
                          <p className="text-xs font-medium">{String((aiResearch.financial_profile as Record<string, string>).payment_behavior)}</p>
                        </div>
                      </div>
                    )}
                    {(aiResearch.financial_profile as Record<string, string>).growth_trend && (
                      <div className="flex items-start gap-2 col-span-full">
                        <BarChart3 className="h-3.5 w-3.5 mt-0.5 text-blue-500 shrink-0" />
                        <div>
                          <p className="text-[10px] text-muted-foreground">Trend de crestere</p>
                          <p className="text-xs font-medium">{String((aiResearch.financial_profile as Record<string, string>).growth_trend)}</p>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Credit Assessment */}
              {aiResearch.credit_assessment && (
                <div className="rounded-lg border p-3">
                  <p className="text-xs font-medium text-muted-foreground mb-1 flex items-center gap-1">
                    <ShieldCheck className="h-3 w-3" /> Evaluare Risc de Credit
                  </p>
                  <p className="text-sm">{String(aiResearch.credit_assessment)}</p>
                </div>
              )}

              {/* Key Insights */}
              {Array.isArray(aiResearch.key_insights) && (aiResearch.key_insights as string[]).length > 0 && (
                <div className="rounded-lg border p-3">
                  <p className="text-xs font-medium text-muted-foreground mb-1.5 flex items-center gap-1">
                    <Lightbulb className="h-3 w-3" /> Informatii Cheie
                  </p>
                  <ul className="space-y-1">
                    {(aiResearch.key_insights as string[]).map((insight, i) => (
                      <li key={i} className="text-sm flex items-start gap-2">
                        <span className="text-primary mt-0.5">{'\u2022'}</span>{String(insight)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Opportunities + Risks side by side */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {Array.isArray(aiResearch.opportunities) && (aiResearch.opportunities as string[]).length > 0 && (
                  <div className="rounded-lg border border-green-200 dark:border-green-900 p-3 bg-green-50/50 dark:bg-green-950/20">
                    <p className="text-xs font-medium text-green-700 dark:text-green-400 mb-1.5 flex items-center gap-1">
                      <TrendingUp className="h-3 w-3" /> Oportunitati
                    </p>
                    <ul className="space-y-1">
                      {(aiResearch.opportunities as string[]).map((opp, i) => (
                        <li key={i} className="text-xs flex items-start gap-2">
                          <span className="text-green-600 mt-0.5">{'\u2022'}</span>{String(opp)}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {Array.isArray(aiResearch.risks) && (aiResearch.risks as string[]).length > 0 && (
                  <div className="rounded-lg border border-amber-200 dark:border-amber-900 p-3 bg-amber-50/50 dark:bg-amber-950/20">
                    <p className="text-xs font-medium text-amber-700 dark:text-amber-400 mb-1.5 flex items-center gap-1">
                      <AlertTriangle className="h-3 w-3" /> Riscuri
                    </p>
                    <ul className="space-y-1">
                      {(aiResearch.risks as string[]).map((risk, i) => (
                        <li key={i} className="text-xs flex items-start gap-2">
                          <span className="text-amber-600 mt-0.5">{'\u2022'}</span>{String(risk)}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* Recommended Actions */}
              {Array.isArray(aiResearch.recommended_actions) && (aiResearch.recommended_actions as string[]).length > 0 && (
                <div className="rounded-lg border p-3">
                  <p className="text-xs font-medium text-muted-foreground mb-1.5 flex items-center gap-1">
                    <Target className="h-3 w-3" /> Actiuni Recomandate
                  </p>
                  <ul className="space-y-1">
                    {(aiResearch.recommended_actions as string[]).map((action, i) => (
                      <li key={i} className="text-sm flex items-start gap-2">
                        <span className="text-blue-500 mt-0.5">{i + 1}.</span>{String(action)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Car Sale Opportunity */}
              {aiResearch.car_sale_opportunity && typeof aiResearch.car_sale_opportunity === 'object' && (
                <div className="rounded-lg border border-emerald-200 dark:border-emerald-900 p-3 bg-emerald-50/30 dark:bg-emerald-950/20">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs font-medium text-emerald-700 dark:text-emerald-400 flex items-center gap-1">
                      <Car className="h-3 w-3" /> Oportunitate Vanzare Auto
                    </p>
                    {(aiResearch.car_sale_opportunity as Record<string, string>).score ? (
                      <Badge variant="default" className="text-[10px] bg-emerald-600">
                        Scor: {String((aiResearch.car_sale_opportunity as Record<string, string>).score)}/10
                      </Badge>
                    ) : null}
                  </div>
                  {(aiResearch.car_sale_opportunity as Record<string, string>).assessment && (
                    <p className="text-xs mb-2">{String((aiResearch.car_sale_opportunity as Record<string, string>).assessment)}</p>
                  )}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                    {Array.isArray((aiResearch.car_sale_opportunity as Record<string, unknown>).vehicle_types) && (
                      <div>
                        <p className="text-[10px] text-muted-foreground">Tipuri vehicule</p>
                        <p className="text-xs font-medium">{((aiResearch.car_sale_opportunity as Record<string, string[]>).vehicle_types).join(', ')}</p>
                      </div>
                    )}
                    {(aiResearch.car_sale_opportunity as Record<string, string>).estimated_units_year && (
                      <div>
                        <p className="text-[10px] text-muted-foreground">Unitati estimate/an</p>
                        <p className="text-xs font-medium">{String((aiResearch.car_sale_opportunity as Record<string, string>).estimated_units_year)}</p>
                      </div>
                    )}
                    {(aiResearch.car_sale_opportunity as Record<string, string>).budget_range && (
                      <div>
                        <p className="text-[10px] text-muted-foreground">Buget estimat/an</p>
                        <p className="text-xs font-medium">{String((aiResearch.car_sale_opportunity as Record<string, string>).budget_range)}</p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Market Position + Mobility Needs */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {aiResearch.market_position && typeof aiResearch.market_position === 'object' && (
                  <div className="rounded-lg border p-3">
                    <p className="text-xs font-medium text-muted-foreground mb-2 flex items-center gap-1">
                      <BarChart3 className="h-3 w-3" /> Pozitie pe Piata & Expansiune
                    </p>
                    <div className="space-y-1.5">
                      {(aiResearch.market_position as Record<string, string>).market_share && (
                        <div><p className="text-[10px] text-muted-foreground">Cota de piata</p><p className="text-xs">{String((aiResearch.market_position as Record<string, string>).market_share)}</p></div>
                      )}
                      {(aiResearch.market_position as Record<string, string>).representation && (
                        <div><p className="text-[10px] text-muted-foreground">Prezenta geografica</p><p className="text-xs">{String((aiResearch.market_position as Record<string, string>).representation)}</p></div>
                      )}
                      {(aiResearch.market_position as Record<string, string>).brand_strength && (
                        <div><p className="text-[10px] text-muted-foreground">Forta brand</p><p className="text-xs">{String((aiResearch.market_position as Record<string, string>).brand_strength)}</p></div>
                      )}
                      {(aiResearch.market_position as Record<string, string>).expansion_plans && (
                        <div><p className="text-[10px] text-muted-foreground">Potential expansiune</p><p className="text-xs">{String((aiResearch.market_position as Record<string, string>).expansion_plans)}</p></div>
                      )}
                    </div>
                  </div>
                )}
                {aiResearch.mobility_needs && typeof aiResearch.mobility_needs === 'object' && (
                  <div className="rounded-lg border p-3">
                    <p className="text-xs font-medium text-muted-foreground mb-2 flex items-center gap-1">
                      <Car className="h-3 w-3" /> Nevoi de Mobilitate
                    </p>
                    <div className="space-y-1.5">
                      {(aiResearch.mobility_needs as Record<string, string>).current_assessment && (
                        <div><p className="text-[10px] text-muted-foreground">Evaluare curenta</p><p className="text-xs">{String((aiResearch.mobility_needs as Record<string, string>).current_assessment)}</p></div>
                      )}
                      {(aiResearch.mobility_needs as Record<string, string>).sales_force_mobility && (
                        <div><p className="text-[10px] text-muted-foreground">Mobilitate echipa vanzari</p><p className="text-xs">{String((aiResearch.mobility_needs as Record<string, string>).sales_force_mobility)}</p></div>
                      )}
                      {(aiResearch.mobility_needs as Record<string, string>).logistics_needs && (
                        <div><p className="text-[10px] text-muted-foreground">Nevoi logistice</p><p className="text-xs">{String((aiResearch.mobility_needs as Record<string, string>).logistics_needs)}</p></div>
                      )}
                      {(aiResearch.mobility_needs as Record<string, string>).executive_mobility && (
                        <div><p className="text-[10px] text-muted-foreground">Mobilitate management</p><p className="text-xs">{String((aiResearch.mobility_needs as Record<string, string>).executive_mobility)}</p></div>
                      )}
                      {(aiResearch.mobility_needs as Record<string, string>).service_vehicles && (
                        <div><p className="text-[10px] text-muted-foreground">Vehicule serviciu</p><p className="text-xs">{String((aiResearch.mobility_needs as Record<string, string>).service_vehicles)}</p></div>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* Fleet Potential + News */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {aiResearch.fleet_potential && (
                  <div className="rounded-lg border p-3">
                    <p className="text-xs font-medium text-muted-foreground mb-1 flex items-center gap-1">
                      <Truck className="h-3 w-3" /> Potential Flota
                    </p>
                    <p className="text-sm">{String(aiResearch.fleet_potential)}</p>
                  </div>
                )}
                {aiResearch.news_summary && (
                  <div className="rounded-lg border p-3">
                    <p className="text-xs font-medium text-muted-foreground mb-1 flex items-center gap-1">
                      <MessageSquare className="h-3 w-3" /> Stiri si Dezvoltari
                    </p>
                    <p className="text-sm">{String(aiResearch.news_summary)}</p>
                  </div>
                )}
              </div>

              {/* Timestamp */}
              {aiResearch._generated_at && (
                <p className="text-[10px] text-muted-foreground text-right">
                  Generat {new Date(String(aiResearch._generated_at)).toLocaleString('ro-RO')} {'\u2022'} {String(aiResearch._model || 'Claude AI')}
                </p>
              )}
            </div>
          )}
          {aiResearch?._raw && (
            <div className="rounded-lg border p-3">
              <p className="text-sm whitespace-pre-wrap">{String(aiResearch.summary)}</p>
            </div>
          )}
          {!aiResearch && !aiResearchMutation.isPending && (
            <p className="text-sm text-muted-foreground">Apasa "Analizeaza Compania" pentru a genera un raport de analiza financiara AI.</p>
          )}
        </CardContent>
      </Card>

      {/* Business Data Enrichment — Multi-connector */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm flex items-center gap-1.5">
              <Database className="h-4 w-4" />Business Data Enrichment
            </CardTitle>
            <div className="flex items-center gap-2">
              {!profile?.cui && (
                <>
                  <Input
                    placeholder="Enter CUI (e.g. 12345678)"
                    value={cuiInput}
                    onChange={e => setCuiInput(e.target.value)}
                    className="w-48 h-8 text-sm"
                    onKeyDown={e => e.key === 'Enter' && cuiInput.trim() && enrichMutation.mutate(cuiInput.trim())}
                  />
                  <Button size="sm" className="h-8" onClick={() => enrichMutation.mutate(cuiInput.trim())} disabled={!cuiInput.trim() || enrichMutation.isPending}>
                    {enrichMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : <Search className="h-3.5 w-3.5 mr-1" />}
                    Set CUI
                  </Button>
                  <Button size="sm" variant="outline" className="h-8" onClick={() => lookupCuiMutation.mutate()} disabled={lookupCuiMutation.isPending}>
                    {lookupCuiMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : <Sparkles className="h-3.5 w-3.5 mr-1" />}
                    Auto-detect
                  </Button>
                </>
              )}
              {profile?.cui && (
                <Badge variant="outline" className="font-mono text-xs">CUI: {profile.cui}</Badge>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {/* CUI Lookup Results */}
          {cuiResults.length > 0 && !profile?.cui && (
            <div className="rounded-lg border border-primary/30 p-3 mb-3 bg-primary/5">
              <p className="text-xs font-medium mb-2 flex items-center gap-1.5">
                <Search className="h-3 w-3" /> Found {cuiResults.length} matching {cuiResults.length === 1 ? 'company' : 'companies'}:
              </p>
              <div className="space-y-1.5">
                {cuiResults.map((r, i) => (
                  <div key={i} className="flex items-center justify-between rounded border p-2 bg-background hover:bg-muted/50 transition-colors">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium truncate">{r.name}</p>
                      <p className="text-xs text-muted-foreground">CUI: <span className="font-mono">{r.cui}</span>{r.nr_reg ? ` • Nr. Reg: ${r.nr_reg}` : ''}{r.address ? ` • ${r.address}` : ''}</p>
                    </div>
                    <Button size="sm" className="h-7 text-xs ml-2 shrink-0" onClick={() => {
                      setCuiInput(r.cui)
                      enrichMutation.mutate(r.cui)
                      setCuiResults([])
                    }}>
                      Use CUI
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ANAF Section */}
          <div className="rounded-lg border p-3 mb-3">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-medium flex items-center gap-1.5">
                <span>🏛️</span> ANAF Fiscal Data
              </p>
              {(profile?.cui || cuiInput.trim()) && (
                <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => enrichMutation.mutate(profile?.cui || cuiInput.trim())} disabled={enrichMutation.isPending}>
                  <RefreshCw className={`h-3 w-3 mr-1 ${enrichMutation.isPending ? 'animate-spin' : ''}`} />
                  {fiscal ? 'Refresh' : 'Fetch'}
                </Button>
              )}
            </div>
            {fiscal ? (
              (() => {
                const dg = (fiscal.date_generale || fiscal) as Record<string, unknown>
                const ax = (enrichmentData?.anaf_extra || {}) as Record<string, unknown>
                const tva = (fiscal.inregistrare_scop_Tva || {}) as Record<string, unknown>
                const inact = (fiscal.stare_inactiv || {}) as Record<string, unknown>
                const split = (fiscal.inregistrare_SplitTVA || {}) as Record<string, unknown>
                return (
                  <div className="space-y-2 text-sm">
                    {/* Row 1: Identity */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-1">
                      <InfoRow label="Denumire" value={String(dg.denumire || '')} />
                      <InfoRow label="CUI" value={String(dg.cui || ax.cui || '')} />
                      <InfoRow label="Nr. Reg. Com." value={String(dg.nrRegCom || ax.nr_reg_com || '')} />
                      <InfoRow label="Data Inregistrare" value={String(dg.data_inregistrare || ax.data_inregistrare || '')} />
                    </div>
                    {/* Row 2: Legal & Fiscal */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-1">
                      <InfoRow label="Forma Juridica" value={String(dg.forma_juridica || ax.forma_juridica || '')} />
                      <InfoRow label="Forma Proprietate" value={String(dg.forma_de_proprietate || ax.forma_de_proprietate || '')} />
                      <InfoRow label="Cod CAEN" value={String(dg.cod_CAEN || dg.cod_caen || ax.cod_caen || '')} />
                      <InfoRow label="Organ Fiscal" value={String(dg.organFiscalCompetent || ax.organ_fiscal || '')} />
                    </div>
                    {/* Row 3: Address */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-1">
                      <InfoRow label="Adresa" value={String(dg.adresa || '')} />
                      <InfoRow label="Cod Postal" value={String(dg.codPostal || ax.cod_postal || '')} />
                      <InfoRow label="Telefon" value={String(dg.telefon || '')} />
                      <InfoRow label="Fax" value={String(dg.fax || ax.fax || '')} />
                    </div>
                    {/* Row 4: Status indicators */}
                    <div className="grid grid-cols-3 md:grid-cols-6 gap-x-3 gap-y-1">
                      <div><span className="text-[10px] text-muted-foreground block">Platitor TVA</span><span className={`text-xs font-medium ${(tva.scpTVA || ax.scp_tva || dg.scpTVA) ? 'text-green-600' : 'text-muted-foreground'}`}>{(tva.scpTVA || ax.scp_tva || dg.scpTVA) ? 'Da' : 'Nu'}</span></div>
                      <div><span className="text-[10px] text-muted-foreground block">Activ</span><span className={`text-xs font-medium ${(inact.statusInactivi || ax.is_inactive) ? 'text-red-600' : 'text-green-600'}`}>{(inact.statusInactivi || ax.is_inactive) ? 'Inactiv' : 'Activ'}</span></div>
                      <div><span className="text-[10px] text-muted-foreground block">Split TVA</span><span className="text-xs font-medium">{(split.statusSplitTVA || ax.split_tva) ? 'Da' : 'Nu'}</span></div>
                      <div><span className="text-[10px] text-muted-foreground block">TVA Incasare</span><span className="text-xs font-medium">{ax.tva_incasare ? 'Da' : 'Nu'}</span></div>
                      <div><span className="text-[10px] text-muted-foreground block">e-Factura</span><span className={`text-xs font-medium ${(dg.statusRO_e_Factura || ax.e_factura) ? 'text-green-600' : 'text-muted-foreground'}`}>{(dg.statusRO_e_Factura || ax.e_factura) ? 'Da' : 'Nu'}</span></div>
                      <div><span className="text-[10px] text-muted-foreground block">Stare</span><span className="text-xs font-medium">{String(dg.stare_inregistrare || ax.stare_inregistrare || '—')}</span></div>
                    </div>
                    {/* IBAN if available */}
                    {!!(dg.iban || ax.iban) && <InfoRow label="IBAN" value={String(dg.iban || ax.iban || '')} />}
                    {profile?.anaf_fetched_at && <div className="text-[10px] text-muted-foreground pt-1 border-t">Ultima actualizare: {new Date(profile.anaf_fetched_at).toLocaleString('ro-RO')}</div>}
                  </div>
                )
              })()
            ) : (
              <p className="text-xs text-muted-foreground">{profile?.cui ? 'No ANAF data yet. Click Fetch to retrieve.' : 'Set a CUI first to fetch ANAF data.'}</p>
            )}
          </div>

          {/* Other Business Connectors */}
          {connectors.filter(c => c.connector_type !== 'anaf').map(connector => {
            const meta = CONNECTOR_META[connector.connector_type] || { icon: '📡', label: connector.name }
            const enriched = enrichmentData[connector.connector_type]
            const hasData = enriched && enriched.data && !enriched.error
            const isExpanded = expandedConnector === connector.connector_type

            return (
              <div key={connector.connector_type} className="rounded-lg border p-3 mb-3">
                <div className="flex items-center justify-between">
                  <button
                    className="text-sm font-medium flex items-center gap-1.5 hover:text-primary transition-colors"
                    onClick={() => setExpandedConnector(isExpanded ? null : connector.connector_type)}
                  >
                    <span>{meta.icon}</span> {meta.label}
                    {hasData && <Badge variant="secondary" className="text-[10px] ml-1">Data Available</Badge>}
                    {connector.status !== 'connected' && <Badge variant="outline" className="text-[10px] ml-1">Not Connected</Badge>}
                    {hasData ? (isExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />) : null}
                  </button>
                  <div className="flex items-center gap-2">
                    {enriched?.fetched_at && (
                      <span className="text-[10px] text-muted-foreground">{new Date(enriched.fetched_at).toLocaleDateString('ro-RO')}</span>
                    )}
                    {connector.status === 'connected' && cui && (
                      <Button
                        size="sm" variant="ghost" className="h-7 text-xs"
                        onClick={() => connectorEnrichMutation.mutate({ cui, connectorType: connector.connector_type })}
                        disabled={fetchingConnector === connector.connector_type}
                      >
                        <RefreshCw className={`h-3 w-3 mr-1 ${fetchingConnector === connector.connector_type ? 'animate-spin' : ''}`} />
                        {hasData ? 'Refresh' : 'Fetch'}
                      </Button>
                    )}
                  </div>
                </div>
                {enriched?.error && (
                  <p className="text-xs text-destructive mt-1">Error: {enriched.error}</p>
                )}
                {isExpanded && hasData && (
                  <div className="mt-2 grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-1 text-sm">
                    {Object.entries(enriched.data).map(([key, value]) => (
                      <InfoRow key={key} label={key} value={typeof value === 'object' ? JSON.stringify(value) : String(value ?? '')} />
                    ))}
                  </div>
                )}
                {connector.status !== 'connected' && (
                  <p className="text-xs text-muted-foreground mt-1">Configure credentials in Settings → Connectors to enable.</p>
                )}
              </div>
            )
          })}
        </CardContent>
      </Card>

      {/* Cars Purchased (Deals) */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-1.5">
            <Car className="h-4 w-4" />Cars Purchased ({deals.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {deals.length === 0 ? (
            <p className="text-sm text-muted-foreground">No deals linked to this client</p>
          ) : (
            <div className="rounded border overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/50">
                    <TableHead className="text-xs py-1.5">Source</TableHead>
                    <TableHead className="text-xs py-1.5">Brand</TableHead>
                    <TableHead className="text-xs py-1.5">Model</TableHead>
                    <TableHead className="text-xs py-1.5">VIN</TableHead>
                    <TableHead className="text-xs py-1.5">Contract Date</TableHead>
                    <TableHead className="text-xs py-1.5">Status</TableHead>
                    <TableHead className="text-xs py-1.5 text-right">Sale Price</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {deals.map((d: CrmDeal) => (
                    <TableRow key={d.id}>
                      <TableCell className="py-1.5">
                        <Badge variant={d.source === 'nw' ? 'default' : 'secondary'} className="text-[10px] px-1.5 py-0">
                          {d.source?.toUpperCase()}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs py-1.5">{d.brand || '—'}</TableCell>
                      <TableCell className="text-xs py-1.5">{d.model_name || '—'}</TableCell>
                      <TableCell className="text-xs font-mono py-1.5">{d.vin || '—'}</TableCell>
                      <TableCell className="text-xs py-1.5">{d.contract_date ? new Date(d.contract_date).toLocaleDateString() : '—'}</TableCell>
                      <TableCell className="text-xs py-1.5">{d.dossier_status || '—'}</TableCell>
                      <TableCell className="text-xs font-mono py-1.5 text-right">
                        {d.sale_price_net ? Number(d.sale_price_net).toLocaleString('ro-RO') : '—'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Fleet Vehicles */}
      {fleet.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-1.5">
              <Truck className="h-4 w-4" />Fleet ({fleet.length})
              {renewalCandidates.length > 0 && (
                <Badge variant="secondary" className="text-[10px] ml-1"><Star className="h-2.5 w-2.5 mr-0.5" />{renewalCandidates.length} renewal</Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="rounded border overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/50">
                    <TableHead className="text-xs py-1.5">Make</TableHead>
                    <TableHead className="text-xs py-1.5">Model</TableHead>
                    <TableHead className="text-xs py-1.5">Year</TableHead>
                    <TableHead className="text-xs py-1.5">VIN</TableHead>
                    <TableHead className="text-xs py-1.5">Plate</TableHead>
                    <TableHead className="text-xs py-1.5">Status</TableHead>
                    <TableHead className="text-xs py-1.5">Renewal</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {fleet.map((v: FleetVehicle) => (
                    <TableRow key={v.id}>
                      <TableCell className="text-xs py-1.5 font-medium">{v.vehicle_make || '—'}</TableCell>
                      <TableCell className="text-xs py-1.5">{v.vehicle_model || '—'}</TableCell>
                      <TableCell className="text-xs py-1.5">{v.vehicle_year || '—'}</TableCell>
                      <TableCell className="text-xs font-mono py-1.5">{v.vin || '—'}</TableCell>
                      <TableCell className="text-xs font-mono py-1.5">{v.license_plate || '—'}</TableCell>
                      <TableCell className="py-1.5">
                        <Badge variant={v.status === 'active' ? 'default' : 'secondary'} className="text-[10px] px-1.5 py-0">{v.status || '—'}</Badge>
                      </TableCell>
                      <TableCell className="py-1.5">
                        {v.renewal_candidate ? (
                          <Badge className="text-[10px] px-1.5 py-0 bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200">
                            <Star className="h-2.5 w-2.5 mr-0.5" />Yes
                          </Badge>
                        ) : '—'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Field Sales Visits + Interactions side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-1.5">
              <MapPin className="h-4 w-4" />Field Sales Visits ({visits.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {visits.length === 0 ? (
              <p className="text-sm text-muted-foreground">No field sales visits</p>
            ) : (
              <div className="rounded border overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/50">
                      <TableHead className="text-xs py-1.5">Date</TableHead>
                      <TableHead className="text-xs py-1.5">KAM</TableHead>
                      <TableHead className="text-xs py-1.5">Type</TableHead>
                      <TableHead className="text-xs py-1.5">Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {visits.map((v: CrmVisit) => (
                      <TableRow key={v.id}>
                        <TableCell className="text-xs py-1.5">{v.planned_date ? new Date(v.planned_date).toLocaleDateString() : '—'}</TableCell>
                        <TableCell className="text-xs py-1.5 font-medium">{v.kam_name || '—'}</TableCell>
                        <TableCell className="py-1.5">
                          <Badge variant="secondary" className="text-[10px] px-1.5 py-0">{v.visit_type?.replace(/_/g, ' ') || '—'}</Badge>
                        </TableCell>
                        <TableCell className="py-1.5">
                          <Badge variant={v.status === 'completed' ? 'default' : v.status === 'in_progress' ? 'secondary' : 'outline'} className="text-[10px] px-1.5 py-0">{v.status || '—'}</Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-1.5">
              <MessageSquare className="h-4 w-4" />Recent Interactions ({interactions.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {interactions.length === 0 ? (
              <p className="text-sm text-muted-foreground">No interactions recorded</p>
            ) : (
              <div className="space-y-2">
                {interactions.slice(0, 8).map((i: ClientInteraction) => (
                  <div key={i.id} className="rounded border p-2.5 text-xs space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{i.kam_name || 'Unknown'}</span>
                      <span className="text-muted-foreground">{i.created_at ? new Date(i.created_at).toLocaleDateString() : ''}</span>
                    </div>
                    {i.visit_type && <Badge variant="secondary" className="text-[10px] px-1.5 py-0">{i.visit_type.replace(/_/g, ' ')}</Badge>}
                    <p className="text-muted-foreground line-clamp-2">
                      {(i.structured_note as Record<string, string>)?.visit_summary || i.raw_note || '—'}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
