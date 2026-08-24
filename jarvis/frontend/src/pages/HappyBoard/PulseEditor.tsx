import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus, Trash2, Play, Square, X } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ApiError } from '@/api/client'
import { digestApi } from '@/api/digest'
import {
  happyAdminApi,
  useAdminPulse,
  usePulseResults,
  type AdminPulseQuestion,
  type HappyPulseQType,
} from '@/api/happyAdmin'
import { PulseResultsView } from './PulseResultsView'

const QTYPES: { value: HappyPulseQType; label: string }[] = [
  { value: 'likert5', label: 'Scală 1–5' },
  { value: 'enps', label: 'eNPS 0–10' },
  { value: 'single', label: 'Alegere unică' },
  { value: 'open', label: 'Răspuns liber' },
]

export interface PulseEditorProps {
  pulseId: number | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function PulseEditor({ pulseId, open, onOpenChange }: PulseEditorProps) {
  const queryClient = useQueryClient()
  const { data, isLoading } = useAdminPulse(open ? pulseId : null)
  const { data: results } = usePulseResults(open ? pulseId : null)
  const [questions, setQuestions] = useState<AdminPulseQuestion[]>([])
  const [audience, setAudience] = useState<{ id: number; name: string }[]>([])
  const [search, setSearch] = useState('')

  useEffect(() => {
    if (data?.questions) setQuestions(data.questions)
  }, [data])

  useEffect(() => {
    setAudience([])
    setSearch('')
  }, [pulseId])

  const { data: searchRes } = useQuery({
    queryKey: ['happy', 'pulse-audience', search],
    queryFn: () => digestApi.searchUsers(search),
    enabled: search.trim().length >= 2,
  })
  const searchResults = searchRes?.data ?? []

  const pulse = data?.pulse
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['happy', 'admin', 'pulse', pulseId] })

  const saveQuestions = useMutation({
    mutationFn: () => happyAdminApi.updateQuestions(pulseId as number, questions),
    onSuccess: () => {
      toast.success('Întrebări salvate.')
      invalidate()
    },
    onError: () => toast.error('Nu am putut salva întrebările.'),
  })

  const openPulse = useMutation({
    mutationFn: (ids: number[]) => happyAdminApi.openPulse(pulseId as number, ids.length ? ids : undefined),
    onSuccess: (r) => {
      toast.success(`Pulse deschis · ${r.invited} invitați.`)
      invalidate()
      queryClient.invalidateQueries({ queryKey: ['happy', 'admin', 'pulses'] })
    },
    onError: (err) => {
      const msg = err instanceof ApiError ? (err.data as { error?: string } | null)?.error : undefined
      toast.error(msg || 'Nu am putut deschide pulse-ul.')
    },
  })

  const addRespondent = (u: { id: number; name: string }) => {
    setAudience((prev) => (prev.some((x) => x.id === u.id) ? prev : [...prev, u]))
    setSearch('')
  }

  const handleOpen = () => {
    const ids = audience.map((u) => u.id)
    if (
      ids.length === 0 &&
      !window.confirm(
        'Deschizi acest Pulse pentru TOȚI angajații activi? Pentru un test, adaugă întâi persoane la „Audiență de test”.',
      )
    )
      return
    openPulse.mutate(ids)
  }

  const closePulse = useMutation({
    mutationFn: () => happyAdminApi.closePulse(pulseId as number),
    onSuccess: () => {
      toast.success('Pulse închis.')
      invalidate()
      queryClient.invalidateQueries({ queryKey: ['happy', 'admin', 'pulses'] })
    },
    onError: () => toast.error('Nu am putut închide pulse-ul.'),
  })

  const addQuestion = () => {
    setQuestions((prev) => [
      ...prev,
      { position: prev.length + 1, prompt_ro: '', qtype: 'likert5', driver: '' },
    ])
  }

  const updateQuestion = (idx: number, patch: Partial<AdminPulseQuestion>) => {
    setQuestions((prev) => prev.map((q, i) => (i === idx ? { ...q, ...patch } : q)))
  }

  const removeQuestion = (idx: number) => {
    setQuestions((prev) => prev.filter((_, i) => i !== idx).map((q, i) => ({ ...q, position: i + 1 })))
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] max-w-[640px] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {pulse?.title ?? 'Pulse'}
            {pulse && <Badge variant="outline">{pulse.status}</Badge>}
          </DialogTitle>
        </DialogHeader>

        {isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <div className="space-y-5">
            {/* Questions editor */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">Întrebări</p>
                <Button size="sm" variant="outline" onClick={addQuestion}>
                  <Plus className="h-3.5 w-3.5" /> Adaugă
                </Button>
              </div>

              {questions.length === 0 && (
                <p className="text-sm text-muted-foreground">Nicio întrebare încă.</p>
              )}

              {questions.map((q, idx) => (
                <div key={idx} className="space-y-2 rounded-md border p-3">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">#{q.position}</span>
                    <Input
                      value={q.prompt_ro}
                      onChange={(e) => updateQuestion(idx, { prompt_ro: e.target.value })}
                      placeholder="Textul întrebării"
                    />
                    <Button
                      size="icon-xs"
                      variant="ghost"
                      aria-label="Șterge întrebarea"
                      onClick={() => removeQuestion(idx)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                  <div className="flex gap-2">
                    <Select
                      value={q.qtype}
                      onValueChange={(v) => updateQuestion(idx, { qtype: v as HappyPulseQType })}
                    >
                      <SelectTrigger className="w-40">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {QTYPES.map((t) => (
                          <SelectItem key={t.value} value={t.value}>
                            {t.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Input
                      value={q.driver ?? ''}
                      onChange={(e) => updateQuestion(idx, { driver: e.target.value })}
                      placeholder="Driver (opțional)"
                    />
                  </div>
                </div>
              ))}

              <Button size="sm" onClick={() => saveQuestions.mutate()} disabled={saveQuestions.isPending}>
                Salvează întrebările
              </Button>
            </div>

            {/* Test audience (optional) */}
            <div className="space-y-2 border-t pt-4">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">
                  Audiență de test <span className="font-normal text-muted-foreground">(opțional)</span>
                </p>
                {audience.length > 0 && <Badge variant="secondary">{audience.length} selectați</Badge>}
              </div>
              <p className="text-xs text-muted-foreground">
                Fără selecție, „Deschide” trimite Pulse-ul <strong>tuturor</strong> angajaților. Adaugă persoane aici
                ca să-l deschizi doar pentru un grup de test.
              </p>
              {audience.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {audience.map((u) => (
                    <Badge key={u.id} variant="outline" className="gap-1 pr-1">
                      {u.name}
                      <button
                        type="button"
                        aria-label={`Elimină ${u.name}`}
                        className="rounded-sm hover:bg-muted"
                        onClick={() => setAudience((prev) => prev.filter((x) => x.id !== u.id))}
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
              )}
              <div className="relative">
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Caută coleg după nume…"
                />
                {search.trim().length >= 2 && searchResults.length > 0 && (
                  <div className="absolute z-20 mt-1 max-h-48 w-full overflow-y-auto rounded-md border bg-popover shadow-md">
                    {searchResults.map((u) => (
                      <button
                        type="button"
                        key={u.id}
                        onClick={() => addRespondent({ id: u.id, name: u.name })}
                        className="block w-full px-3 py-2 text-left text-sm hover:bg-accent"
                      >
                        <span className="font-medium">{u.name}</span>
                        {(u.department || u.company) && (
                          <span className="ml-2 text-xs text-muted-foreground">
                            {[u.department, u.company].filter(Boolean).join(' · ')}
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Lifecycle */}
            <div className="flex items-center gap-2 border-t pt-4">
              <Button size="sm" variant="outline" onClick={handleOpen} disabled={openPulse.isPending}>
                <Play className="h-3.5 w-3.5" />{' '}
                {audience.length ? `Deschide pt. test · ${audience.length}` : 'Deschide (tuturor)'}
              </Button>
              <Button size="sm" variant="outline" onClick={() => closePulse.mutate()} disabled={closePulse.isPending}>
                <Square className="h-3.5 w-3.5" /> Închide
              </Button>
            </div>

            {/* Results */}
            {results && (
              <div className="space-y-2 border-t pt-4">
                <p className="text-sm font-medium">Rezultate</p>
                <PulseResultsView results={results} />
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

export default PulseEditor

export interface NewPulseDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function NewPulseDialog({ open, onOpenChange }: NewPulseDialogProps) {
  const queryClient = useQueryClient()
  const [slug, setSlug] = useState('')
  const [title, setTitle] = useState('')
  const [cadence, setCadence] = useState('weekly')
  const [minGroup, setMinGroup] = useState(5)
  const [minComment, setMinComment] = useState(10)

  const create = useMutation({
    mutationFn: () =>
      happyAdminApi.createPulse({
        slug,
        title,
        cadence,
        min_group_size: minGroup,
        min_comment_group: minComment,
      }),
    onSuccess: () => {
      toast.success('Pulse creat.')
      queryClient.invalidateQueries({ queryKey: ['happy', 'admin', 'pulses'] })
      onOpenChange(false)
    },
    onError: () => toast.error('Nu am putut crea pulse-ul.'),
  })

  const canSubmit = slug.trim() && title.trim() && !create.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[480px]">
        <DialogHeader>
          <DialogTitle>Pulse nou</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Slug</Label>
            <Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="pulse-2026-w35" />
          </div>
          <div className="space-y-1.5">
            <Label>Titlu</Label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Pulse săptămânal" />
          </div>
          <div className="space-y-1.5">
            <Label>Cadență</Label>
            <Select value={cadence} onValueChange={setCadence}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {['weekly', 'biweekly', 'monthly', 'quarterly', 'adhoc'].map((c) => (
                  <SelectItem key={c} value={c}>
                    {c}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Prag grup minim</Label>
              <Input
                type="number"
                value={minGroup}
                onChange={(e) => setMinGroup(Number(e.target.value))}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Prag comentarii</Label>
              <Input
                type="number"
                value={minComment}
                onChange={(e) => setMinComment(Number(e.target.value))}
              />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              Anulează
            </Button>
            <Button disabled={!canSubmit} onClick={() => create.mutate()}>
              Creează
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
