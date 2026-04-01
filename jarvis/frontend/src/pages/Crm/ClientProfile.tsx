import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, Building2, Pencil, Save, X, Car, MapPin, Truck, MessageSquare,
  Star, RefreshCw, Search, Loader2, Phone, Mail, Hash, Globe, User,
  Shield, Database, ChevronDown, ChevronUp,
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

  // ANAF enrich mutation
  const enrichMutation = useMutation({
    mutationFn: (cui: string) => crmApi.enrichClient(id, cui),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['crm-client', id] })
      toast.success('ANAF data fetched')
      setCuiInput('')
    },
    onError: () => toast.error('ANAF fetch failed'),
  })

  // Connector-specific enrich mutation
  const connectorEnrichMutation = useMutation({
    mutationFn: ({ cui, connectorType }: { cui: string; connectorType: string }) =>
      crmApi.enrichFromConnector(id, cui, connectorType),
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['crm-client', id] })
      toast.success(`${CONNECTOR_META[vars.connectorType]?.label || vars.connectorType} data fetched`)
    },
    onError: (_, vars) => toast.error(`${CONNECTOR_META[vars.connectorType]?.label || vars.connectorType} fetch failed`),
  })

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
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => navigate(-1)}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-xl font-bold flex items-center gap-2">
              <Building2 className="h-5 w-5 text-primary" />
              {client.display_name}
            </h1>
            <div className="flex items-center gap-2 mt-0.5">
              <Badge variant={client.client_type === 'company' ? 'default' : 'secondary'}>{client.client_type}</Badge>
              {profile?.cui && <Badge variant="outline" className="font-mono text-xs">CUI: {profile.cui}</Badge>}
              {profile?.priority && <Badge variant="secondary">{profile.priority}</Badge>}
              {client.is_blacklisted && <Badge variant="destructive">Blacklisted</Badge>}
            </div>
          </div>
        </div>
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

      {/* Contact Info + Profile side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Contact Info */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-1.5">
              <User className="h-4 w-4" />Contact Information
            </CardTitle>
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

      {/* Business Data Enrichment — Multi-connector */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm flex items-center gap-1.5">
              <Database className="h-4 w-4" />Business Data Enrichment
            </CardTitle>
            {!profile?.cui && (
              <div className="flex items-center gap-2">
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
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent>
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
              <div className="grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-1 text-sm">
                <InfoRow label="Company Name" value={fiscal.denumire as string} />
                <InfoRow label="CUI" value={fiscal.cui as string} />
                <InfoRow label="Nr. Reg" value={fiscal.nrRegCom as string} />
                <InfoRow label="Address" value={fiscal.adresa as string} />
                <InfoRow label="CAEN Code" value={fiscal.cod_CAEN as string} />
                <InfoRow label="CAEN Activity" value={fiscal.aut as string} />
                <InfoRow label="VAT Registered" value={(fiscal.scpTVA === true || fiscal.tva === true) ? 'Yes' : 'No'} />
                <InfoRow label="Active" value={fiscal.statusInactivi === true ? 'Inactive' : 'Active'} />
                <InfoRow label="Split TVA" value={fiscal.splitTVA === true ? 'Yes' : 'No'} />
                {profile?.anaf_fetched_at && <InfoRow label="Last Fetched" value={new Date(profile.anaf_fetched_at).toLocaleString('ro-RO')} />}
              </div>
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
                        disabled={connectorEnrichMutation.isPending}
                      >
                        <RefreshCw className={`h-3 w-3 mr-1 ${connectorEnrichMutation.isPending ? 'animate-spin' : ''}`} />
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
