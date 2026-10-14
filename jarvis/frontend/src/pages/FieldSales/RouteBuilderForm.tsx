import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Plus, Trash2, MapPin } from 'lucide-react'
import { cn } from '@/lib/utils'
import { fieldSalesApi, type RouteStop } from '@/api/fieldSales'
import { VISIT_TYPE_LABELS } from '@/pages/Hub/HubFieldSalesPanel'
import FSClientPicker from './FSClientPicker'

const todayStr = () => new Date().toISOString().split('T')[0]

interface StopDraft {
  client_id: number
  client_name: string
  planned_time?: string
  visit_type: string
  goals?: string
}

const inputClass =
  'h-11 w-full rounded-xl border border-border bg-background px-3 text-base focus:outline-none focus:ring-2 focus:ring-teal-600/40'

export default function RouteBuilderForm({ companyId, onDone, onCancel }: {
  companyId: number
  onDone: () => void
  onCancel: () => void
}) {
  const [plannedDate, setPlannedDate] = useState(todayStr())
  const [name, setName] = useState('')
  const [stops, setStops] = useState<StopDraft[]>([])
  const [pickerOpen, setPickerOpen] = useState(false)

  const mut = useMutation({
    mutationFn: (data: Parameters<typeof fieldSalesApi.createMyRoute>[0]) => fieldSalesApi.createMyRoute(data),
    onSuccess: () => onDone(),
  })
  const err = mut.error as { data?: { error?: string } } | null

  const addStop = (c: { id: number; display_name: string }) => {
    setStops((p) => [...p, { client_id: c.id, client_name: c.display_name, visit_type: 'general' }])
    setPickerOpen(false)
  }
  const removeStop = (i: number) => setStops((p) => p.filter((_, idx) => idx !== i))
  const patchStop = (i: number, patch: Partial<StopDraft>) =>
    setStops((p) => p.map((s, idx) => (idx === i ? { ...s, ...patch } : s)))

  const valid = plannedDate.length > 0 && stops.length > 0

  const submit = () => {
    if (!valid || mut.isPending) return
    mut.mutate({
      planned_date: plannedDate,
      name: name.trim() || undefined,
      stops: stops.map<RouteStop>((s) => ({
        client_id: s.client_id,
        ...(s.planned_time ? { planned_time: s.planned_time } : {}),
        visit_type: s.visit_type,
        ...(s.goals && s.goals.trim() ? { goals: s.goals } : {}),
      })),
    })
  }

  return (
    <div className="space-y-4 p-4 pb-8">
      <h3 className="text-lg font-bold">Ruta noua</h3>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">Data</label>
          <input type="date" value={plannedDate} onChange={(e) => setPlannedDate(e.target.value)} className={inputClass} />
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">Nume ruta (optional)</label>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="ex. Zona Nord" className={inputClass} />
        </div>
      </div>

      {stops.map((s, i) => (
        <div key={i} className="space-y-2 rounded-xl border border-border bg-card p-3">
          <div className="flex items-center gap-2">
            <MapPin className="h-4 w-4 shrink-0 text-teal-600" />
            <span className="flex-1 truncate font-medium">{s.client_name}</span>
            <button aria-label="Sterge oprire" onClick={() => removeStop(i)} className="text-muted-foreground hover:text-destructive">
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
          <input
            type="time"
            value={s.planned_time ?? ''}
            onChange={(e) => patchStop(i, { planned_time: e.target.value })}
            className={inputClass}
          />
          <select
            value={s.visit_type}
            onChange={(e) => patchStop(i, { visit_type: e.target.value })}
            className={cn(inputClass, 'appearance-none')}
          >
            {Object.entries(VISIT_TYPE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
          <textarea
            value={s.goals ?? ''}
            onChange={(e) => patchStop(i, { goals: e.target.value })}
            rows={2}
            placeholder="Obiective (optional)"
            className="w-full resize-none rounded-xl border border-border bg-background px-3 py-2 text-base placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-teal-600/40"
          />
        </div>
      ))}

      {pickerOpen ? (
        <div className="rounded-xl border border-dashed border-border p-3">
          <FSClientPicker companyId={companyId} onPick={addStop} autoFocus />
        </div>
      ) : (
        <button
          onClick={() => setPickerOpen(true)}
          className="flex w-full items-center justify-center gap-2 rounded-xl border border-border py-2.5 text-sm font-semibold active:bg-muted"
        >
          <Plus className="h-4 w-4" /> Adauga oprire
        </button>
      )}

      <div className="flex gap-2">
        <button onClick={onCancel} className="h-11 flex-1 rounded-xl border border-border text-base font-semibold active:bg-muted">
          Anuleaza
        </button>
        <button
          onClick={submit}
          disabled={!valid || mut.isPending}
          className={cn(
            'h-11 flex-1 rounded-xl text-base font-semibold text-white transition-colors',
            valid && !mut.isPending ? 'bg-teal-600 active:bg-teal-700' : 'bg-muted-foreground/40 cursor-not-allowed',
          )}
        >
          {mut.isPending ? 'Se creeaza...' : 'Creeaza ruta'}
        </button>
      </div>

      {mut.isError && <p className="text-center text-xs text-destructive">{err?.data?.error ?? 'Crearea rutei a esuat'}</p>}
    </div>
  )
}
