import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus, Trash2, Users, Download, Rocket, Pause } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { ApiError } from '@/api/client'
import {
  happyAdminApi,
  useAdminCampaign,
  useCampaignStats,
  type AdminAudienceRule,
  type AdminQuizQuestion,
  type ComplianceExport,
  type HappyAckMode,
  type HappyTier,
  type PreviewAudienceResponse,
} from '@/api/happyAdmin'
import { ReachFunnel } from './ReachFunnel'

const KINDS = ['hr_announcement', 'event', 'action', 'policy', 'survey', 'recognition']
const PLACEMENTS = ['interstitial', 'dash_banner', 'hub_card', 'feed', 'push', 'email']
const TIERS: HappyTier[] = ['normal', 'important', 'critical']
const ACK_MODES: HappyAckMode[] = ['none', 'click', 'quiz']
// Phase-0: only `company` and `department` are populated enough to target on.
const DIMENSIONS = ['company', 'department']

function isoToLocal(iso?: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function localToIso(local: string): string | undefined {
  if (!local) return undefined
  const d = new Date(local)
  return Number.isNaN(d.getTime()) ? undefined : d.toISOString()
}

interface CampaignForm {
  slug: string
  kind: string
  tier: HappyTier
  placements: string[]
  title: string
  summary: string
  body_md: string
  ack_mode: HappyAckMode
  ack_deadline_at: string
  starts_at: string
  ends_at: string
  media_key: string
  media_alt: string
  cta_label: string
  cta_href: string
  cta_deeplink: string
}

const EMPTY_FORM: CampaignForm = {
  slug: '',
  kind: 'hr_announcement',
  tier: 'normal',
  placements: ['hub_card'],
  title: '',
  summary: '',
  body_md: '',
  ack_mode: 'none',
  ack_deadline_at: '',
  starts_at: '',
  ends_at: '',
  media_key: '',
  media_alt: '',
  cta_label: '',
  cta_href: '',
  cta_deeplink: '',
}

export interface CampaignEditorProps {
  campaignId: number | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CampaignEditor({ campaignId, open, onOpenChange }: CampaignEditorProps) {
  const queryClient = useQueryClient()
  const isEdit = campaignId != null
  const { data: detail, isLoading } = useAdminCampaign(open && isEdit ? campaignId : null)
  const { data: stats } = useCampaignStats(open && isEdit ? campaignId : null)

  const [form, setForm] = useState<CampaignForm>(EMPTY_FORM)
  const [audience, setAudience] = useState<AdminAudienceRule[]>([])
  const [quiz, setQuiz] = useState<AdminQuizQuestion[]>([])
  const [preview, setPreview] = useState<PreviewAudienceResponse | null>(null)
  const [compliance, setCompliance] = useState<ComplianceExport | null>(null)
  const [publishErrors, setPublishErrors] = useState<string[]>([])

  const set = <K extends keyof CampaignForm>(k: K, v: CampaignForm[K]) =>
    setForm((f) => ({ ...f, [k]: v }))

  // Load existing campaign into the form (edit mode).
  useEffect(() => {
    if (!open) return
    if (!isEdit) {
      setForm(EMPTY_FORM)
      setAudience([])
      setQuiz([])
      setPreview(null)
      setCompliance(null)
      setPublishErrors([])
      return
    }
    if (detail) {
      const c = detail.campaign
      setForm({
        slug: c.slug ?? '',
        kind: c.kind ?? 'hr_announcement',
        tier: c.tier ?? 'normal',
        placements: c.placements ?? [],
        title: c.title ?? '',
        summary: c.summary ?? '',
        body_md: c.body_md ?? '',
        ack_mode: c.ack_mode ?? 'none',
        ack_deadline_at: isoToLocal(c.ack_deadline_at),
        starts_at: isoToLocal(c.starts_at),
        ends_at: isoToLocal(c.ends_at),
        media_key: c.media_key ?? '',
        media_alt: c.media_alt ?? '',
        cta_label: c.cta_label ?? '',
        cta_href: c.cta_href ?? '',
        cta_deeplink: c.cta_deeplink ?? '',
      })
      setAudience(detail.audience ?? [])
      setQuiz(detail.quiz ?? [])
    }
  }, [open, isEdit, detail])

  const buildPayload = () => ({
    slug: form.slug.trim(),
    kind: form.kind,
    tier: form.tier,
    placements: form.placements,
    title: form.title.trim(),
    summary: form.summary || undefined,
    body_md: form.body_md || undefined,
    ack_mode: form.ack_mode,
    ack_deadline_at: localToIso(form.ack_deadline_at) ?? null,
    starts_at: localToIso(form.starts_at),
    ends_at: localToIso(form.ends_at),
    media_key: form.media_key || undefined,
    media_alt: form.media_alt || undefined,
    cta_label: form.cta_label || undefined,
    cta_href: form.cta_href || undefined,
    cta_deeplink: form.cta_deeplink || undefined,
  })

  const invalidateList = () => queryClient.invalidateQueries({ queryKey: ['happy', 'admin', 'campaigns'] })

  const save = useMutation({
    mutationFn: async () => {
      if (isEdit) {
        return happyAdminApi.updateCampaign(campaignId as number, {
          ...buildPayload(),
          audience,
          quiz: form.ack_mode === 'quiz' ? quiz : undefined,
        })
      }
      return happyAdminApi.createCampaign(buildPayload())
    },
    onSuccess: () => {
      toast.success(isEdit ? 'Campanie salvată.' : 'Campanie creată.')
      invalidateList()
      if (isEdit) queryClient.invalidateQueries({ queryKey: ['happy', 'admin', 'campaign', campaignId] })
      else onOpenChange(false)
    },
    onError: () => toast.error('Nu am putut salva campania.'),
  })

  const publish = useMutation({
    mutationFn: () => happyAdminApi.publishCampaign(campaignId as number),
    onSuccess: (r) => {
      toast.success(`Publicat · ${r.targeted} destinatari.`)
      setPublishErrors([])
      invalidateList()
      queryClient.invalidateQueries({ queryKey: ['happy', 'admin', 'campaign', campaignId] })
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        const data = err.data as { error?: string; details?: string[] } | null
        setPublishErrors(data?.details ?? (data?.error ? [data.error] : ['Publicare eșuată.']))
      } else {
        setPublishErrors(['Publicare eșuată.'])
      }
      toast.error('Publicare eșuată — vezi detaliile.')
    },
  })

  const pause = useMutation({
    mutationFn: () => happyAdminApi.pauseCampaign(campaignId as number),
    onSuccess: () => {
      toast.success('Campanie pusă pe pauză.')
      invalidateList()
      queryClient.invalidateQueries({ queryKey: ['happy', 'admin', 'campaign', campaignId] })
    },
    onError: () => toast.error('Nu am putut pune pe pauză.'),
  })

  const runPreview = async () => {
    if (!isEdit) return
    try {
      const r = await happyAdminApi.previewAudience(campaignId as number, audience)
      setPreview(r)
    } catch {
      toast.error('Nu am putut estima audiența.')
    }
  }

  const loadCompliance = async () => {
    if (!isEdit) return
    try {
      const r = await happyAdminApi.complianceExport(campaignId as number)
      setCompliance(r)
    } catch {
      toast.error('Nu am putut încărca exportul de conformitate.')
    }
  }

  const downloadComplianceCsv = () => {
    if (!compliance) return
    const header = 'user_id,acknowledged,acknowledged_at,method'
    const rows = compliance.acknowledgements.map(
      (a) => `${a.user_id},${a.acknowledged},${a.acknowledged_at ?? ''},${a.method ?? ''}`,
    )
    const csv = [header, ...rows].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `compliance-${compliance.campaign_id}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

  const togglePlacement = (p: string) => {
    set('placements', form.placements.includes(p) ? form.placements.filter((x) => x !== p) : [...form.placements, p])
  }

  const canSave = form.slug.trim() && form.title.trim() && form.placements.length > 0 && !save.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-[680px] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {isEdit ? detail?.campaign.title || 'Campanie' : 'Campanie nouă'}
            {isEdit && detail && <Badge variant="outline">{detail.campaign.status}</Badge>}
          </DialogTitle>
        </DialogHeader>

        {isEdit && isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : (
          <div className="space-y-5">
            {/* ── Core fields ── */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Slug</Label>
                <Input value={form.slug} onChange={(e) => set('slug', e.target.value)} placeholder="beneficii-2026" />
              </div>
              <div className="space-y-1.5">
                <Label>Tip</Label>
                <Select value={form.kind} onValueChange={(v) => set('kind', v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {KINDS.map((k) => <SelectItem key={k} value={k}>{k}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>Titlu</Label>
              <Input value={form.title} onChange={(e) => set('title', e.target.value)} />
            </div>

            <div className="space-y-1.5">
              <Label>Rezumat</Label>
              <Input value={form.summary} onChange={(e) => set('summary', e.target.value)} />
            </div>

            <div className="space-y-1.5">
              <Label>Conținut (markdown)</Label>
              <Textarea value={form.body_md} onChange={(e) => set('body_md', e.target.value)} rows={4} />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Nivel</Label>
                <Select value={form.tier} onValueChange={(v) => set('tier', v as HappyTier)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {TIERS.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Confirmare</Label>
                <Select value={form.ack_mode} onValueChange={(v) => set('ack_mode', v as HappyAckMode)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {ACK_MODES.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Placements */}
            <div className="space-y-1.5">
              <Label>Plasări</Label>
              <div className="flex flex-wrap gap-1.5">
                {PLACEMENTS.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => togglePlacement(p)}
                    className={cn(
                      'rounded-md border px-2.5 py-1 text-xs transition-colors',
                      form.placements.includes(p)
                        ? 'border-primary bg-primary text-primary-foreground'
                        : 'border-border hover:bg-accent/50',
                    )}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>

            {/* Dates */}
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5">
                <Label>Start</Label>
                <Input type="datetime-local" value={form.starts_at} onChange={(e) => set('starts_at', e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label>Sfârșit</Label>
                <Input type="datetime-local" value={form.ends_at} onChange={(e) => set('ends_at', e.target.value)} />
              </div>
              {form.ack_mode !== 'none' && (
                <div className="space-y-1.5">
                  <Label>Termen confirmare</Label>
                  <Input
                    type="datetime-local"
                    value={form.ack_deadline_at}
                    onChange={(e) => set('ack_deadline_at', e.target.value)}
                  />
                </div>
              )}
            </div>

            {/* CTA */}
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5">
                <Label>CTA etichetă</Label>
                <Input value={form.cta_label} onChange={(e) => set('cta_label', e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label>CTA href</Label>
                <Input value={form.cta_href} onChange={(e) => set('cta_href', e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label>CTA deeplink</Label>
                <Input value={form.cta_deeplink} onChange={(e) => set('cta_deeplink', e.target.value)} />
              </div>
            </div>

            {/* Media */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Media key</Label>
                <Input value={form.media_key} onChange={(e) => set('media_key', e.target.value)} placeholder="private/happy/…" />
              </div>
              <div className="space-y-1.5">
                <Label>Media alt</Label>
                <Input value={form.media_alt} onChange={(e) => set('media_alt', e.target.value)} />
              </div>
            </div>

            <Button onClick={() => save.mutate()} disabled={!canSave}>
              {isEdit ? 'Salvează' : 'Creează'}
            </Button>

            {/* ── Edit-only sections ── */}
            {isEdit && (
              <>
                {/* Audience */}
                <div className="space-y-2 border-t pt-4">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium">Audiență</p>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        setAudience((a) => [...a, { mode: 'include', dimension: 'company', value: '' }])
                      }
                    >
                      <Plus className="h-3.5 w-3.5" /> Regulă
                    </Button>
                  </div>
                  {audience.length === 0 && (
                    <p className="text-xs text-muted-foreground">Fără reguli — toți utilizatorii eligibili.</p>
                  )}
                  {audience.map((rule, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <Select
                        value={rule.mode}
                        onValueChange={(v) =>
                          setAudience((a) => a.map((r, i) => (i === idx ? { ...r, mode: v as 'include' | 'exclude' } : r)))
                        }
                      >
                        <SelectTrigger className="w-28"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="include">Include</SelectItem>
                          <SelectItem value="exclude">Exclude</SelectItem>
                        </SelectContent>
                      </Select>
                      <Select
                        value={rule.dimension}
                        onValueChange={(v) =>
                          setAudience((a) => a.map((r, i) => (i === idx ? { ...r, dimension: v } : r)))
                        }
                      >
                        <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {DIMENSIONS.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
                        </SelectContent>
                      </Select>
                      <Input
                        value={rule.value}
                        onChange={(e) =>
                          setAudience((a) => a.map((r, i) => (i === idx ? { ...r, value: e.target.value } : r)))
                        }
                        placeholder="valoare"
                      />
                      <Button
                        size="icon-xs"
                        variant="ghost"
                        aria-label="Șterge regula"
                        onClick={() => setAudience((a) => a.filter((_, i) => i !== idx))}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  ))}
                  <Button size="sm" variant="secondary" onClick={runPreview}>
                    <Users className="h-3.5 w-3.5" /> Estimează audiența
                  </Button>
                  {preview && (
                    <div className="rounded-md border p-3 text-sm">
                      <p className="font-medium">{preview.count} persoane</p>
                      <div className="mt-1 flex flex-wrap gap-1.5">
                        {preview.cohorts.map((c) => (
                          <Badge key={c.company} variant="secondary">
                            {c.company}: {c.n}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {/* Quiz editor (quiz ack only) */}
                {form.ack_mode === 'quiz' && (
                  <div className="space-y-2 border-t pt-4">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium">Întrebări (comprehensiune)</p>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          setQuiz((q) => [...q, { position: q.length + 1, prompt: '', options: ['', ''], correct_index: 0 }])
                        }
                      >
                        <Plus className="h-3.5 w-3.5" /> Întrebare
                      </Button>
                    </div>
                    {quiz.map((q, idx) => (
                      <div key={idx} className="space-y-2 rounded-md border p-3">
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-muted-foreground">#{q.position}</span>
                          <Input
                            value={q.prompt}
                            onChange={(e) => setQuiz((qs) => qs.map((x, i) => (i === idx ? { ...x, prompt: e.target.value } : x)))}
                            placeholder="Întrebarea"
                          />
                          <Button
                            size="icon-xs"
                            variant="ghost"
                            aria-label="Șterge întrebarea"
                            onClick={() => setQuiz((qs) => qs.filter((_, i) => i !== idx))}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                        <Input
                          value={q.options.join(' | ')}
                          onChange={(e) =>
                            setQuiz((qs) =>
                              qs.map((x, i) => (i === idx ? { ...x, options: e.target.value.split('|').map((s) => s.trim()) } : x)),
                            )
                          }
                          placeholder="Opțiuni separate prin |"
                        />
                        <div className="flex items-center gap-2">
                          <Label className="text-xs">Index corect</Label>
                          <Input
                            type="number"
                            className="w-20"
                            value={q.correct_index}
                            onChange={(e) =>
                              setQuiz((qs) => qs.map((x, i) => (i === idx ? { ...x, correct_index: Number(e.target.value) } : x)))
                            }
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Lifecycle */}
                <div className="flex items-center gap-2 border-t pt-4">
                  <Button size="sm" onClick={() => publish.mutate()} disabled={publish.isPending}>
                    <Rocket className="h-3.5 w-3.5" /> Publică
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => pause.mutate()} disabled={pause.isPending}>
                    <Pause className="h-3.5 w-3.5" /> Pauză
                  </Button>
                </div>
                {publishErrors.length > 0 && (
                  <ul className="list-inside list-disc rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
                    {publishErrors.map((e, i) => <li key={i}>{e}</li>)}
                  </ul>
                )}

                {/* Stats funnel */}
                {stats && (
                  <div className="space-y-2 border-t pt-4">
                    <p className="text-sm font-medium">Pâlnie</p>
                    <ReachFunnel funnel={stats.funnel} />
                  </div>
                )}

                {/* Compliance export */}
                <div className="space-y-2 border-t pt-4">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium">Conformitate</p>
                    <div className="flex gap-2">
                      <Button size="sm" variant="outline" onClick={loadCompliance}>
                        <Users className="h-3.5 w-3.5" /> Încarcă
                      </Button>
                      {compliance && (
                        <Button size="sm" variant="outline" onClick={downloadComplianceCsv}>
                          <Download className="h-3.5 w-3.5" /> Export CSV
                        </Button>
                      )}
                    </div>
                  </div>
                  {compliance && (
                    <div className="max-h-56 overflow-y-auto rounded-md border">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>User</TableHead>
                            <TableHead>Confirmat</TableHead>
                            <TableHead>Data</TableHead>
                            <TableHead>Metodă</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {compliance.acknowledgements.map((a) => (
                            <TableRow key={a.user_id}>
                              <TableCell>#{a.user_id}</TableCell>
                              <TableCell>{a.acknowledged ? 'Da' : 'Nu'}</TableCell>
                              <TableCell className="text-muted-foreground">
                                {a.acknowledged_at ? new Date(a.acknowledged_at).toLocaleString('ro-RO') : '—'}
                              </TableCell>
                              <TableCell className="text-muted-foreground">{a.method ?? '—'}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

export default CampaignEditor
