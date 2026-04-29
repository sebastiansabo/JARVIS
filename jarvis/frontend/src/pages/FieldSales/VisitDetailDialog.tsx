import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DateField } from '@/components/ui/date-field'
import {
  Calendar, Clock, User, Building2, MapPin, Target, FileText,
  Brain, MessageSquare, Phone, Mail, Factory, Hash, Star,
  Pencil, Save, X, ClipboardList, ClipboardCheck, ListTodo,
} from 'lucide-react'
import { toast } from 'sonner'
import { fieldSalesApi, type FSVisit, type PreVisitData, type PostVisitData, type VisitUpdatePayload } from '@/api/fieldSales'
import { PreVisitForm } from './PreVisitForm'
import { PostVisitForm } from './PostVisitForm'
import { TaskList } from './TaskList'

interface Props {
  visitId: number | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

const STATUS_LABELS: Record<string, string> = {
  planned: 'Planificat',
  in_progress: 'In desfasurare',
  completed: 'Finalizat',
  no_show: 'Absent',
  rescheduled: 'Reprogramat',
  partial: 'Partial',
}

const STATUS_STYLES: Record<string, string> = {
  planned: 'bg-gray-100 text-gray-700',
  in_progress: 'bg-blue-100 text-blue-700',
  completed: 'bg-green-100 text-green-700',
  no_show: 'bg-red-100 text-red-700',
  rescheduled: 'bg-yellow-100 text-yellow-700',
  partial: 'bg-orange-100 text-orange-700',
}

const VISIT_TYPE_LABELS: Record<string, string> = {
  general: 'General',
  fleet_review: 'Fleet Review',
  renewal_discussion: 'Reinnoire',
  test_drive_followup: 'Test Drive Follow-up',
  service_followup: 'Service Follow-up',
  new_acquisition: 'Achizitie Noua',
  contract_negotiation: 'Negociere Contract',
  prospecting: 'Prospectare',
}

const OUTCOME_LABELS: Record<string, string> = {
  completed: 'Finalizat',
  no_show: 'Absent',
  rescheduled: 'Reprogramat',
  partial: 'Partial',
}

const PRIORITY_STYLES: Record<string, string> = {
  high: 'text-red-600',
  medium: 'text-yellow-600',
  low: 'text-green-600',
}

function InfoRow({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value?: string | number | null }) {
  if (!value && value !== 0) return null
  return (
    <div className="flex items-start gap-2 text-sm">
      <Icon className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
      <div>
        <span className="text-muted-foreground">{label}: </span>
        <span className="font-medium">{value}</span>
      </div>
    </div>
  )
}

function formatDateTime(dt?: string | null) {
  if (!dt) return null
  try {
    const d = new Date(dt)
    return d.toLocaleString('ro-RO', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return dt }
}

export function VisitDetailDialog({ visitId, open, onOpenChange }: Props) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [activeTab, setActiveTab] = useState('info')

  // Edit form state
  const [editDate, setEditDate] = useState('')
  const [editTime, setEditTime] = useState('')
  const [editType, setEditType] = useState('')
  const [editGoals, setEditGoals] = useState('')
  const [editStatus, setEditStatus] = useState('')
  const [editOutcome, setEditOutcome] = useState('')
  const [editPreVisit, setEditPreVisit] = useState<PreVisitData>({})
  const [editPostVisit, setEditPostVisit] = useState<PostVisitData>({})

  const { data, isLoading } = useQuery({
    queryKey: ['fs-visit-detail', visitId],
    queryFn: () => fieldSalesApi.getVisit(visitId!),
    enabled: open && !!visitId,
  })

  const visit: FSVisit | undefined = data?.visit

  const startEditing = () => {
    if (!visit) return
    setEditDate(visit.planned_date)
    setEditTime(visit.planned_time || '')
    setEditType(visit.visit_type)
    setEditGoals(visit.goals || '')
    setEditStatus(visit.status)
    setEditOutcome(visit.outcome || '')
    setEditPreVisit(visit.pre_visit_data || {})
    setEditPostVisit(visit.post_visit_data || {})
    setEditing(true)
  }

  const cancelEditing = () => setEditing(false)

  const updateMutation = useMutation({
    mutationFn: (payload: VisitUpdatePayload) =>
      fieldSalesApi.updateVisit(visitId!, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fs-visit-detail', visitId] })
      queryClient.invalidateQueries({ queryKey: ['fs-manager-overview'] })
      toast.success('Vizita actualizata')
      setEditing(false)
    },
    onError: () => toast.error('Eroare la actualizare'),
  })

  const handleSave = () => {
    if (!visit) return
    const changes: VisitUpdatePayload = {}
    if (editDate !== visit.planned_date) changes.planned_date = editDate
    if (editTime !== (visit.planned_time || '')) changes.planned_time = editTime || undefined
    if (editType !== visit.visit_type) changes.visit_type = editType
    if (editGoals !== (visit.goals || '')) changes.goals = editGoals
    if (editStatus !== visit.status) changes.status = editStatus
    if (editOutcome !== (visit.outcome || '')) changes.outcome = editOutcome || undefined

    // Always send pre/post visit data when editing (they may have changed)
    const origPre = visit.pre_visit_data || {}
    const origPost = visit.post_visit_data || {}
    if (JSON.stringify(editPreVisit) !== JSON.stringify(origPre)) {
      changes.pre_visit_data = editPreVisit
    }
    if (JSON.stringify(editPostVisit) !== JSON.stringify(origPost)) {
      changes.post_visit_data = editPostVisit
    }

    if (Object.keys(changes).length === 0) {
      setEditing(false)
      return
    }
    updateMutation.mutate(changes)
  }

  const handleClose = (v: boolean) => {
    if (!v) {
      setEditing(false)
      setActiveTab('info')
    }
    onOpenChange(v)
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center justify-between">
            <DialogTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Detalii Vizita
            </DialogTitle>
            {visit && !editing && (
              <Button variant="outline" size="sm" onClick={startEditing}>
                <Pencil className="h-3.5 w-3.5 mr-1" />
                Editeaza
              </Button>
            )}
            {editing && (
              <div className="flex items-center gap-1.5">
                <Button variant="ghost" size="sm" onClick={cancelEditing}>
                  <X className="h-3.5 w-3.5 mr-1" />
                  Anuleaza
                </Button>
                <Button size="sm" onClick={handleSave} disabled={updateMutation.isPending}>
                  <Save className="h-3.5 w-3.5 mr-1" />
                  {updateMutation.isPending ? 'Se salveaza...' : 'Salveaza'}
                </Button>
              </div>
            )}
          </div>
        </DialogHeader>

        {isLoading ? (
          <div className="space-y-3 py-4">
            <Skeleton className="h-6 w-64" />
            <Skeleton className="h-4 w-48" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        ) : !visit ? (
          <p className="text-muted-foreground py-4 text-center">Vizita nu a fost gasita</p>
        ) : (
          <div className="space-y-3 py-2">
            {/* Status + Type header (always visible) */}
            {!editing && (
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${STATUS_STYLES[visit.status] || 'bg-gray-100 text-gray-700'}`}>
                  {STATUS_LABELS[visit.status] || visit.status}
                </span>
                <Badge variant="outline">
                  {VISIT_TYPE_LABELS[visit.visit_type] || visit.visit_type}
                </Badge>
                {visit.outcome && (
                  <Badge variant="secondary" className="text-xs">
                    Rezultat: {OUTCOME_LABELS[visit.outcome] || visit.outcome}
                  </Badge>
                )}
              </div>
            )}

            {editing ? (
              /* ── EDIT MODE ── */
              <div className="space-y-4">
                {/* Basic visit fields */}
                <div className="rounded-lg border p-3 space-y-3">
                  <h3 className="text-sm font-semibold">Detalii vizita</h3>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <Label className="text-xs">Status</Label>
                      <Select value={editStatus} onValueChange={setEditStatus}>
                        <SelectTrigger className="h-9">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {Object.entries(STATUS_LABELS).map(([k, v]) => (
                            <SelectItem key={k} value={k}>{v}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs">Rezultat</Label>
                      <Select value={editOutcome || '_none'} onValueChange={v => setEditOutcome(v === '_none' ? '' : v)}>
                        <SelectTrigger className="h-9">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="_none">— Fara —</SelectItem>
                          {Object.entries(OUTCOME_LABELS).map(([k, v]) => (
                            <SelectItem key={k} value={k}>{v}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs">Data</Label>
                      <DateField value={editDate} onChange={setEditDate} />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs">Ora</Label>
                      <Input type="time" value={editTime} onChange={e => setEditTime(e.target.value)} className="h-9" />
                    </div>
                    <div className="space-y-1.5 col-span-2">
                      <Label className="text-xs">Tip vizita</Label>
                      <Select value={editType} onValueChange={setEditType}>
                        <SelectTrigger className="h-9">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {Object.entries(VISIT_TYPE_LABELS).map(([k, v]) => (
                            <SelectItem key={k} value={k}>{v}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1.5 col-span-2">
                      <Label className="text-xs">Obiective</Label>
                      <Textarea
                        value={editGoals}
                        onChange={e => setEditGoals(e.target.value)}
                        rows={3}
                        className="text-sm"
                      />
                    </div>
                  </div>
                </div>

                {/* Pre-visit form */}
                <PreVisitForm data={editPreVisit} onChange={setEditPreVisit} />

                {/* Post-visit form */}
                <PostVisitForm data={editPostVisit} onChange={setEditPostVisit} />
              </div>
            ) : (
            /* ── READ MODE WITH TABS ── */
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList className="w-full grid grid-cols-4">
                <TabsTrigger value="info" className="text-xs gap-1">
                  <FileText className="h-3 w-3" />Info
                </TabsTrigger>
                <TabsTrigger value="pre" className="text-xs gap-1">
                  <ClipboardList className="h-3 w-3" />Pre
                </TabsTrigger>
                <TabsTrigger value="post" className="text-xs gap-1">
                  <ClipboardCheck className="h-3 w-3" />Post
                </TabsTrigger>
                <TabsTrigger value="tasks" className="text-xs gap-1">
                  <ListTodo className="h-3 w-3" />Task-uri
                </TabsTrigger>
              </TabsList>

              {/* ── INFO TAB ── */}
              <TabsContent value="info" className="space-y-4 mt-3">
                {/* Client section */}
                <div className="rounded-lg border p-3 space-y-2">
                  <h3 className="text-sm font-semibold flex items-center gap-1.5">
                    <Building2 className="h-4 w-4" />
                    Client
                  </h3>
                  <div className="text-base font-medium">{visit.client_name}</div>
                  {visit.client_company && visit.client_company !== visit.client_name && (
                    <div className="text-sm text-muted-foreground">{visit.client_company}</div>
                  )}
                  <div className="grid grid-cols-2 gap-2 mt-1">
                    <InfoRow icon={MapPin} label="Oras" value={visit.client_city} />
                    <InfoRow icon={Phone} label="Telefon" value={visit.client_phone} />
                    <InfoRow icon={Mail} label="Email" value={visit.client_email} />
                    <InfoRow icon={Hash} label="CUI" value={visit.cui} />
                    <InfoRow icon={Factory} label="Industrie" value={visit.industry} />
                    <InfoRow icon={Star} label="Scor reinnoire" value={visit.renewal_score} />
                    {visit.client_priority && (
                      <div className="flex items-center gap-2 text-sm">
                        <Target className="h-4 w-4 text-muted-foreground shrink-0" />
                        <span className="text-muted-foreground">Prioritate: </span>
                        <span className={`font-medium capitalize ${PRIORITY_STYLES[visit.client_priority] || ''}`}>
                          {visit.client_priority}
                        </span>
                      </div>
                    )}
                    {visit.fleet_size != null && visit.fleet_size > 0 && (
                      <InfoRow icon={Hash} label="Flota" value={`${visit.fleet_size} vehicule`} />
                    )}
                  </div>
                </div>

                {/* Visit timing */}
                <div className="rounded-lg border p-3 space-y-2">
                  <h3 className="text-sm font-semibold flex items-center gap-1.5">
                    <Calendar className="h-4 w-4" />
                    Vizita
                  </h3>
                  <div className="grid grid-cols-2 gap-2">
                    <InfoRow icon={Calendar} label="Data" value={visit.planned_date} />
                    <InfoRow icon={Clock} label="Ora" value={visit.planned_time} />
                    <InfoRow icon={User} label="KAM" value={visit.kam_name} />
                    {visit.contact_person && <InfoRow icon={User} label="Contact" value={visit.contact_person} />}
                    <InfoRow icon={Clock} label="Check-in" value={formatDateTime(visit.checkin_at)} />
                    <InfoRow icon={Clock} label="Check-out" value={formatDateTime(visit.checkout_at)} />
                  </div>
                  {visit.companions && visit.companions.length > 0 && (
                    <div className="text-sm"><span className="text-muted-foreground">Insotitori: </span><span className="font-medium">{visit.companions.join(', ')}</span></div>
                  )}
                  {visit.checkin_lat && visit.checkin_lng && (
                    <div className="text-xs text-muted-foreground">
                      GPS: {visit.checkin_lat.toFixed(5)}, {visit.checkin_lng.toFixed(5)}
                    </div>
                  )}
                </div>

                {/* Goals */}
                {visit.goals && (
                  <div className="rounded-lg border p-3 space-y-1.5">
                    <h3 className="text-sm font-semibold flex items-center gap-1.5">
                      <Target className="h-4 w-4" />
                      Obiective
                    </h3>
                    <p className="text-sm whitespace-pre-wrap">{visit.goals}</p>
                  </div>
                )}

                {/* AI Brief */}
                {visit.ai_brief && (
                  <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-3 space-y-1.5">
                    <h3 className="text-sm font-semibold flex items-center gap-1.5 text-blue-700">
                      <Brain className="h-4 w-4" />
                      AI Brief
                    </h3>
                    <p className="text-sm whitespace-pre-wrap">{visit.ai_brief}</p>
                    {visit.ai_brief_generated_at && (
                      <p className="text-xs text-muted-foreground mt-1">
                        Generat: {formatDateTime(visit.ai_brief_generated_at)}
                      </p>
                    )}
                  </div>
                )}

                {/* Notes */}
                {visit.notes && visit.notes.length > 0 && (
                  <div className="rounded-lg border p-3 space-y-3">
                    <h3 className="text-sm font-semibold flex items-center gap-1.5">
                      <MessageSquare className="h-4 w-4" />
                      Note ({visit.notes.length})
                    </h3>
                    {visit.notes.map(note => (
                      <div key={note.id} className="border-l-2 border-muted pl-3 space-y-1">
                        <p className="text-sm whitespace-pre-wrap">{note.raw_note}</p>
                        {note.structured_note && (
                          <details className="text-xs">
                            <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                              Nota structurata AI
                            </summary>
                            <pre className="mt-1 text-xs bg-muted/50 rounded p-2 overflow-x-auto">
                              {JSON.stringify(note.structured_note, null, 2)}
                            </pre>
                          </details>
                        )}
                        <p className="text-xs text-muted-foreground">
                          {formatDateTime(note.created_at)}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </TabsContent>

              {/* ── PRE-VISIT TAB ── */}
              <TabsContent value="pre" className="mt-3">
                <PreVisitForm
                  data={visit.pre_visit_data || {}}
                  onChange={() => {}}
                  readOnly
                />
                {!visit.pre_visit_data || Object.keys(visit.pre_visit_data).length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-6">
                    Nicio informatie pre-vizita completata.
                    <br />
                    <button className="text-blue-600 hover:underline mt-1" onClick={startEditing}>
                      Completeaza acum
                    </button>
                  </p>
                ) : null}
              </TabsContent>

              {/* ── POST-VISIT TAB ── */}
              <TabsContent value="post" className="mt-3">
                <PostVisitForm
                  data={visit.post_visit_data || {}}
                  onChange={() => {}}
                  readOnly
                />
                {!visit.post_visit_data || Object.keys(visit.post_visit_data).length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-6">
                    Nicio informatie post-vizita completata.
                    <br />
                    <button className="text-blue-600 hover:underline mt-1" onClick={startEditing}>
                      Completeaza acum
                    </button>
                  </p>
                ) : null}
              </TabsContent>

              {/* ── TASKS TAB ── */}
              <TabsContent value="tasks" className="mt-3">
                <TaskList visitId={visit.id} />
              </TabsContent>
            </Tabs>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
