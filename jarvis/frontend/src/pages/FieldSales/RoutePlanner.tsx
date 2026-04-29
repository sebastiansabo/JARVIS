import { useState, useMemo, useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { DateField } from '@/components/ui/date-field'
import {
  ArrowLeft, Search, X, User, Building2, Plus,
  ChevronUp, ChevronDown, Trash2, Route, Save,
} from 'lucide-react'
import { toast } from 'sonner'
import { useDebounce } from '@/lib/utils'
import { fieldSalesApi, type CreateRoutePayload, type FSClientSearch } from '@/api/fieldSales'
import { usersApi } from '@/api/users'

const VISIT_TYPES: Record<string, string> = {
  general: 'General',
  fleet_review: 'Fleet Review',
  renewal_discussion: 'Reinnoire',
  test_drive_followup: 'Test Drive Follow-up',
  service_followup: 'Service Follow-up',
  new_acquisition: 'Achizitie Noua',
  contract_negotiation: 'Negociere Contract',
  prospecting: 'Prospectare',
}

interface Stop {
  key: string
  client: { id: number; name: string; city?: string } | null
  plannedTime: string
  visitType: string
  goals: string
}

let stopKey = 0
function newStop(): Stop {
  return { key: `s-${++stopKey}`, client: null, plannedTime: '', visitType: 'general', goals: '' }
}

export default function RoutePlanner() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // Route-level state
  const [plannedDate, setPlannedDate] = useState('')
  const [routeName, setRouteName] = useState('')

  // KAM picker
  const [kamOpen, setKamOpen] = useState(false)
  const [kamSearch, setKamSearch] = useState('')
  const [selectedKam, setSelectedKam] = useState<{ id: number; name: string } | null>(null)

  // Stops
  const [stops, setStops] = useState<Stop[]>([newStop()])

  // Client search (shared for adding)
  const [addClientOpen, setAddClientOpen] = useState(false)
  const [clientSearch, setClientSearch] = useState('')
  const debouncedClientSearch = useDebounce(clientSearch, 300)

  // Users query
  const { data: users = [] } = useQuery({
    queryKey: ['users-list'],
    queryFn: () => usersApi.getUsers(),
    staleTime: 5 * 60_000,
  })
  const activeUsers = useMemo(() => users.filter(u => u.is_active), [users])
  const filteredUsers = useMemo(() => {
    const q = kamSearch.trim().toLowerCase()
    if (!q) return activeUsers
    return activeUsers.filter(u =>
      u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q),
    )
  }, [activeUsers, kamSearch])

  // Client search query
  const { data: clientsData } = useQuery({
    queryKey: ['fs-clients-search', debouncedClientSearch],
    queryFn: () => fieldSalesApi.searchClients(debouncedClientSearch),
    enabled: debouncedClientSearch.length >= 2,
  })

  // Stop management
  const addStop = useCallback((client: FSClientSearch) => {
    setStops(prev => [
      ...prev.filter(s => s.client !== null),
      {
        key: `s-${++stopKey}`,
        client: { id: client.id, name: client.display_name, city: client.city },
        plannedTime: '',
        visitType: 'general',
        goals: '',
      },
    ])
    setAddClientOpen(false)
    setClientSearch('')
  }, [])

  const removeStop = useCallback((key: string) => {
    setStops(prev => prev.filter(s => s.key !== key))
  }, [])

  const moveStop = useCallback((idx: number, direction: -1 | 1) => {
    setStops(prev => {
      const newIdx = idx + direction
      if (newIdx < 0 || newIdx >= prev.length) return prev
      const arr = [...prev]
      ;[arr[idx], arr[newIdx]] = [arr[newIdx], arr[idx]]
      return arr
    })
  }, [])

  const updateStop = useCallback((key: string, field: keyof Stop, value: string) => {
    setStops(prev => prev.map(s => s.key === key ? { ...s, [field]: value } : s))
  }, [])

  // Filter out already-selected clients from search results
  const selectedClientIds = useMemo(() => new Set(stops.filter(s => s.client).map(s => s.client!.id)), [stops])
  const filteredClients = useMemo(() => {
    return (clientsData?.clients || []).filter(c => !selectedClientIds.has(c.id))
  }, [clientsData?.clients, selectedClientIds])

  // Valid stops (with client selected)
  const validStops = useMemo(() => stops.filter(s => s.client !== null), [stops])

  // Mutation
  const createMutation = useMutation({
    mutationFn: (data: CreateRoutePayload) => fieldSalesApi.createRoute(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fs-manager-overview'] })
      toast.success(`Ruta creata cu ${validStops.length} opriri`)
      navigate('/app/sales/field-sales')
    },
    onError: () => toast.error('Eroare la crearea rutei'),
  })

  const canSubmit = !!selectedKam && !!plannedDate && validStops.length > 0

  const handleSubmit = () => {
    if (!canSubmit || !selectedKam) return
    createMutation.mutate({
      kam_id: selectedKam.id,
      planned_date: plannedDate,
      name: routeName || undefined,
      stops: validStops.map(s => ({
        client_id: s.client!.id,
        planned_time: s.plannedTime || undefined,
        visit_type: s.visitType,
        goals: s.goals || undefined,
      })),
    })
  }

  return (
    <div className="space-y-5 max-w-4xl">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => navigate('/app/sales/field-sales')}>
          <ArrowLeft className="h-4 w-4 mr-1" />
          Inapoi
        </Button>
        <Route className="h-6 w-6 text-blue-500" />
        <h1 className="text-2xl font-bold">Planifica Ruta</h1>
      </div>

      {/* Route settings */}
      <Card>
        <CardContent className="p-4 grid grid-cols-1 sm:grid-cols-3 gap-4">
          {/* KAM Picker */}
          <div className="space-y-1.5">
            <Label>KAM *</Label>
            <Popover open={kamOpen} onOpenChange={setKamOpen}>
              <PopoverTrigger asChild>
                <Button variant="outline" className="w-full justify-start font-normal">
                  {selectedKam ? (
                    <span className="flex items-center gap-2">
                      <User className="h-4 w-4 text-muted-foreground" />
                      {selectedKam.name}
                      <X
                        className="ml-auto h-4 w-4 text-muted-foreground hover:text-foreground"
                        onClick={e => { e.stopPropagation(); setSelectedKam(null) }}
                      />
                    </span>
                  ) : (
                    <span className="text-muted-foreground">Selecteaza KAM...</span>
                  )}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-72 p-2" align="start">
                <div className="relative mb-2">
                  <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Cauta..."
                    value={kamSearch}
                    onChange={e => setKamSearch(e.target.value)}
                    className="pl-8 h-9"
                  />
                </div>
                <div className="max-h-48 overflow-y-auto space-y-0.5">
                  {filteredUsers.map(u => (
                    <button
                      key={u.id}
                      className="w-full text-left px-2 py-1.5 rounded text-sm hover:bg-accent"
                      onClick={() => { setSelectedKam({ id: u.id, name: u.name }); setKamOpen(false); setKamSearch('') }}
                    >
                      {u.name}
                    </button>
                  ))}
                  {filteredUsers.length === 0 && (
                    <p className="text-xs text-muted-foreground text-center py-2">Niciun rezultat</p>
                  )}
                </div>
              </PopoverContent>
            </Popover>
          </div>

          {/* Date */}
          <div className="space-y-1.5">
            <Label>Data *</Label>
            <DateField value={plannedDate} onChange={setPlannedDate} />
          </div>

          {/* Route name */}
          <div className="space-y-1.5">
            <Label>Nume ruta</Label>
            <Input
              placeholder="ex: Ruta Bucuresti Nord"
              value={routeName}
              onChange={e => setRouteName(e.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      {/* Stops list */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Opriri ({validStops.length})</h2>
          <Popover open={addClientOpen} onOpenChange={setAddClientOpen}>
            <PopoverTrigger asChild>
              <Button variant="outline" size="sm">
                <Plus className="h-4 w-4 mr-1" />
                Adauga Client
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-80 p-2" align="end">
              <div className="relative mb-2">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Nume, companie, CUI..."
                  value={clientSearch}
                  onChange={e => setClientSearch(e.target.value)}
                  className="pl-8 h-9"
                  autoFocus
                />
              </div>
              <div className="max-h-48 overflow-y-auto space-y-0.5">
                {filteredClients.map(c => (
                  <button
                    key={c.id}
                    className="w-full text-left px-2 py-1.5 rounded text-sm hover:bg-accent"
                    onClick={() => addStop(c)}
                  >
                    <div className="font-medium">{c.display_name}</div>
                    {c.city && <div className="text-xs text-muted-foreground">{c.city}</div>}
                  </button>
                ))}
                {debouncedClientSearch.length >= 2 && filteredClients.length === 0 && (
                  <p className="text-xs text-muted-foreground text-center py-2">Niciun rezultat</p>
                )}
                {debouncedClientSearch.length < 2 && (
                  <p className="text-xs text-muted-foreground text-center py-2">Min. 2 caractere</p>
                )}
              </div>
            </PopoverContent>
          </Popover>
        </div>

        {validStops.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-muted-foreground">
              Adauga clienti pentru a construi ruta
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-2">
            {validStops.map((stop, idx) => (
              <Card key={stop.key}>
                <CardContent className="p-3">
                  <div className="flex items-start gap-3">
                    {/* Sequence number */}
                    <div className="flex flex-col items-center gap-0.5 pt-1">
                      <span className="w-7 h-7 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-sm font-bold">
                        {idx + 1}
                      </span>
                      <div className="flex flex-col gap-0">
                        <Button
                          variant="ghost" size="sm"
                          className="h-5 w-5 p-0"
                          onClick={() => moveStop(idx, -1)}
                          disabled={idx === 0}
                        >
                          <ChevronUp className="h-3 w-3" />
                        </Button>
                        <Button
                          variant="ghost" size="sm"
                          className="h-5 w-5 p-0"
                          onClick={() => moveStop(idx, 1)}
                          disabled={idx === validStops.length - 1}
                        >
                          <ChevronDown className="h-3 w-3" />
                        </Button>
                      </div>
                    </div>

                    {/* Stop details */}
                    <div className="flex-1 grid grid-cols-1 sm:grid-cols-[1fr_auto_auto] gap-3">
                      {/* Client info */}
                      <div>
                        <div className="flex items-center gap-1.5">
                          <Building2 className="h-4 w-4 text-muted-foreground" />
                          <span className="font-medium">{stop.client!.name}</span>
                        </div>
                        {stop.client!.city && (
                          <span className="text-xs text-muted-foreground ml-5.5">{stop.client!.city}</span>
                        )}
                      </div>

                      {/* Time */}
                      <div className="space-y-1">
                        <Label className="text-xs">Ora</Label>
                        <Input
                          type="time"
                          value={stop.plannedTime}
                          onChange={e => updateStop(stop.key, 'plannedTime', e.target.value)}
                          className="w-28 h-8 text-sm"
                        />
                      </div>

                      {/* Visit type */}
                      <div className="space-y-1">
                        <Label className="text-xs">Tip</Label>
                        <Select value={stop.visitType} onValueChange={v => updateStop(stop.key, 'visitType', v)}>
                          <SelectTrigger className="w-40 h-8 text-sm">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {Object.entries(VISIT_TYPES).map(([key, label]) => (
                              <SelectItem key={key} value={key}>{label}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>

                    {/* Remove */}
                    <Button
                      variant="ghost" size="sm"
                      className="h-7 w-7 p-0 text-destructive mt-1"
                      onClick={() => removeStop(stop.key)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>

                  {/* Goals (expandable) */}
                  <div className="mt-2 ml-10">
                    <Textarea
                      placeholder="Obiective (optional)..."
                      value={stop.goals}
                      onChange={e => updateStop(stop.key, 'goals', e.target.value)}
                      rows={1}
                      className="text-sm resize-none"
                    />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <Card>
        <CardContent className="p-4 flex items-center justify-between">
          <div className="text-sm text-muted-foreground">
            {validStops.length} opriri
            {selectedKam && <> · KAM: <span className="font-medium text-foreground">{selectedKam.name}</span></>}
            {plannedDate && <> · Data: <span className="font-medium text-foreground">{plannedDate}</span></>}
          </div>
          <Button onClick={handleSubmit} disabled={!canSubmit || createMutation.isPending}>
            <Save className="h-4 w-4 mr-1.5" />
            {createMutation.isPending ? 'Se creeaza...' : 'Salveaza Ruta'}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
