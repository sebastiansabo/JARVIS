import { useState, useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { DateField } from '@/components/ui/date-field'
import { Search, X, User, Building2 } from 'lucide-react'
import { toast } from 'sonner'
import { useDebounce } from '@/lib/utils'
import { fieldSalesApi, type CreateVisitPayload } from '@/api/fieldSales'
import { usersApi } from '@/api/users'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
}

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

export function CreateVisitDialog({ open, onOpenChange }: Props) {
  const queryClient = useQueryClient()

  // Form state
  const [plannedDate, setPlannedDate] = useState('')
  const [plannedTime, setPlannedTime] = useState('')
  const [visitType, setVisitType] = useState('general')
  const [goals, setGoals] = useState('')

  // KAM picker
  const [kamOpen, setKamOpen] = useState(false)
  const [kamSearch, setKamSearch] = useState('')
  const [selectedKam, setSelectedKam] = useState<{ id: number; name: string } | null>(null)

  // Client picker
  const [clientOpen, setClientOpen] = useState(false)
  const [clientSearch, setClientSearch] = useState('')
  const [selectedClient, setSelectedClient] = useState<{ id: number; name: string } | null>(null)
  const debouncedClientSearch = useDebounce(clientSearch, 300)

  // Queries
  const { data: users = [] } = useQuery({
    queryKey: ['users-list'],
    queryFn: () => usersApi.getUsers(),
    staleTime: 5 * 60_000,
    enabled: open,
  })

  const { data: clientsData } = useQuery({
    queryKey: ['fs-clients-search', debouncedClientSearch],
    queryFn: () => fieldSalesApi.searchClients(debouncedClientSearch),
    enabled: open && debouncedClientSearch.length >= 2,
  })

  const activeUsers = useMemo(() => users.filter(u => u.is_active), [users])
  const filteredUsers = useMemo(() => {
    const q = kamSearch.trim().toLowerCase()
    if (!q) return activeUsers
    return activeUsers.filter(u =>
      u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q),
    )
  }, [activeUsers, kamSearch])

  // Mutation
  const createMutation = useMutation({
    mutationFn: (data: CreateVisitPayload) => fieldSalesApi.createVisit(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fs-manager-overview'] })
      toast.success('Vizita creata cu succes')
      resetForm()
      onOpenChange(false)
    },
    onError: () => toast.error('Eroare la crearea vizitei'),
  })

  const resetForm = () => {
    setPlannedDate('')
    setPlannedTime('')
    setVisitType('general')
    setGoals('')
    setSelectedKam(null)
    setSelectedClient(null)
    setClientSearch('')
    setKamSearch('')
  }

  const handleSubmit = () => {
    if (!selectedKam || !selectedClient || !plannedDate) return
    createMutation.mutate({
      kam_id: selectedKam.id,
      client_id: selectedClient.id,
      planned_date: plannedDate,
      planned_time: plannedTime || undefined,
      visit_type: visitType,
      goals: goals || undefined,
    })
  }

  const canSubmit = !!selectedKam && !!selectedClient && !!plannedDate

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) resetForm(); onOpenChange(v) }}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Planifica Vizita</DialogTitle>
        </DialogHeader>

        <div className="grid gap-4 py-2">
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

          {/* Client Picker */}
          <div className="space-y-1.5">
            <Label>Client *</Label>
            <Popover open={clientOpen} onOpenChange={setClientOpen}>
              <PopoverTrigger asChild>
                <Button variant="outline" className="w-full justify-start font-normal">
                  {selectedClient ? (
                    <span className="flex items-center gap-2">
                      <Building2 className="h-4 w-4 text-muted-foreground" />
                      {selectedClient.name}
                      <X
                        className="ml-auto h-4 w-4 text-muted-foreground hover:text-foreground"
                        onClick={e => { e.stopPropagation(); setSelectedClient(null) }}
                      />
                    </span>
                  ) : (
                    <span className="text-muted-foreground">Cauta client...</span>
                  )}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-80 p-2" align="start">
                <div className="relative mb-2">
                  <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Nume, companie, CUI..."
                    value={clientSearch}
                    onChange={e => setClientSearch(e.target.value)}
                    className="pl-8 h-9"
                  />
                </div>
                <div className="max-h-48 overflow-y-auto space-y-0.5">
                  {(clientsData?.clients || []).map(c => (
                    <button
                      key={c.id}
                      className="w-full text-left px-2 py-1.5 rounded text-sm hover:bg-accent"
                      onClick={() => {
                        setSelectedClient({ id: c.id, name: c.display_name })
                        setClientOpen(false)
                        setClientSearch('')
                      }}
                    >
                      <div className="font-medium">{c.display_name}</div>
                      {c.city && <div className="text-xs text-muted-foreground">{c.city}</div>}
                    </button>
                  ))}
                  {debouncedClientSearch.length >= 2 && (clientsData?.clients || []).length === 0 && (
                    <p className="text-xs text-muted-foreground text-center py-2">Niciun rezultat</p>
                  )}
                  {debouncedClientSearch.length < 2 && (
                    <p className="text-xs text-muted-foreground text-center py-2">Min. 2 caractere</p>
                  )}
                </div>
              </PopoverContent>
            </Popover>
          </div>

          {/* Date & Time */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Data *</Label>
              <DateField value={plannedDate} onChange={setPlannedDate} />
            </div>
            <div className="space-y-1.5">
              <Label>Ora</Label>
              <Input type="time" value={plannedTime} onChange={e => setPlannedTime(e.target.value)} />
            </div>
          </div>

          {/* Visit Type */}
          <div className="space-y-1.5">
            <Label>Tip vizita</Label>
            <Select value={visitType} onValueChange={setVisitType}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(VISIT_TYPES).map(([key, label]) => (
                  <SelectItem key={key} value={key}>{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Goals */}
          <div className="space-y-1.5">
            <Label>Obiective</Label>
            <Textarea
              placeholder="Obiectivele vizitei..."
              value={goals}
              onChange={e => setGoals(e.target.value)}
              rows={3}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Anuleaza</Button>
          <Button onClick={handleSubmit} disabled={!canSubmit || createMutation.isPending}>
            {createMutation.isPending ? 'Se creeaza...' : 'Creeaza Vizita'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
