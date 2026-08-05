import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Sparkles, Car, Target, Calendar, AlertTriangle, Euro, CheckCircle, User } from 'lucide-react'
import { cn } from '@/lib/utils'
import { fieldSalesApi, type FSStructuredNote } from '@/api/fieldSales'

type Step = 'input' | 'processing' | 'review'

const ACTION_LABELS: Record<string, string> = {
  replace: 'Inlocuire',
  buy: 'Achizitie',
  keep: 'Pastrare',
  trade_in: 'Trade-in',
  test_drive: 'Test drive',
}

function fmtEur(v: number) {
  return new Intl.NumberFormat('ro-RO', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(v)
}

function fmtDate(d: string) {
  return new Date(d).toLocaleDateString('ro-RO', { day: '2-digit', month: 'short', year: 'numeric' })
}

// Finalize-with-AI-structured-note flow for the Hub Field Sales panel. The
// backend /note endpoint completes the visit (outcome defaults to
// 'completed'), so saving the reviewed note IS the finalize action. Ported
// from jarvis-mobile/src/pages/FieldSales/VisitNoteModal.tsx (step machine
// input -> processing -> review -> saved), dropping Capacitor Haptics and the
// outer modal chrome -- the Hub panel wraps this in the shared OverlaySheet.
export default function NoteCaptureModal({ visitId, clientId, onDone, onCancel }: {
  visitId: number
  clientId: number
  onDone: () => void
  onCancel: () => void
}) {
  const queryClient = useQueryClient()
  const [step, setStep] = useState<Step>('input')
  const [rawNote, setRawNote] = useState('')
  const [structured, setStructured] = useState<FSStructuredNote | null>(null)

  const addNoteMut = useMutation({
    mutationFn: ({ raw_note }: { raw_note: string }) => fieldSalesApi.addNote(visitId, { raw_note }),
    onSuccess: (res) => {
      const note = res.structured_note ?? (res.note?.structured_note as FSStructuredNote | undefined) ?? null
      setStructured(note)
      setStep('review')
    },
    onError: () => {
      // Fall back to the input step so the user can retry.
      setStep('input')
    },
  })
  const err = addNoteMut.error as { data?: { error?: string } } | null

  const handleProcess = () => {
    if (!rawNote.trim()) return
    setStep('processing')
    addNoteMut.mutate({ raw_note: rawNote })
  }

  // Finalizes the flow: the /note POST already completed the visit server-side,
  // so refresh the affected caches and hand control back to the parent (which
  // closes the overlay). Called from both the structured "Salveaza nota" action
  // and the null-summary "Finalizeaza" fallback, so the visit list always
  // refreshes even when AI structuring returned nothing.
  const handleSave = () => {
    queryClient.invalidateQueries({ queryKey: ['field-sales-visits'] })
    queryClient.invalidateQueries({ queryKey: ['fs-visit-detail', visitId] })
    queryClient.invalidateQueries({ queryKey: ['field-sales-client360', clientId] })
    onDone()
  }

  return (
    <div className="flex flex-col">
      <div className="px-4 pt-4">
        <h3 className="text-lg font-bold">Nota vizita</h3>
      </div>

      <div className="px-4 py-4">
        {step === 'input' && (
          <div className="space-y-4">
            <div className="flex items-start gap-2">
              <Sparkles className="h-5 w-5 text-teal-600 mt-0.5 shrink-0" />
              <div>
                <p className="text-sm font-medium">Notite de teren</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Scrie liber despre vizita. AI-ul va structura automat informatiile relevante si va finaliza vizita.
                </p>
              </div>
            </div>

            <textarea
              value={rawNote}
              onChange={(e) => setRawNote(e.target.value)}
              placeholder="Exemplu: Am discutat cu domnul Popescu despre reinnoirea flotei de 5 vehicule. Este interesat de BMW X3 si X5. Buget estimat 200k EUR. Urmatorul pas: oferta personalizata pana vineri..."
              rows={8}
              autoFocus
              className="w-full rounded-xl border border-border bg-background p-3 text-base text-foreground placeholder:text-muted-foreground resize-none focus:outline-none focus:ring-2 focus:ring-teal-600/40 leading-relaxed"
            />
            <p className="text-xs text-muted-foreground text-right">{rawNote.length} caractere</p>

            {addNoteMut.isError && (
              <p className="text-xs text-destructive text-center">
                {err?.data?.error ?? 'Eroare la procesarea notei'}
              </p>
            )}
          </div>
        )}

        {step === 'processing' && (
          <div className="flex flex-col items-center justify-center py-16">
            <div className="relative mb-6">
              <div className="h-14 w-14 animate-spin rounded-full border-4 border-teal-600/20 border-t-teal-600" />
              <Sparkles className="absolute inset-0 m-auto h-6 w-6 text-teal-600" />
            </div>
            <p className="text-base font-semibold mb-1">Se proceseaza nota</p>
            <p className="text-sm text-muted-foreground text-center max-w-[280px]">
              AI-ul analizeaza si structureaza informatiile din nota ta de teren
            </p>
          </div>
        )}

        {step === 'review' && structured && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <CheckCircle className="h-4 w-4 text-green-500" />
              <p className="text-xs font-medium text-green-600 dark:text-green-400">Nota procesata cu succes</p>
            </div>

            {/* Summary */}
            <div className="rounded-xl border p-3">
              <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">Sumar vizita</h4>
              <p className="text-sm text-foreground leading-relaxed">{structured.visit_summary}</p>
              {structured.contact_person && (
                <div className="flex items-center gap-1.5 mt-2 text-xs text-muted-foreground">
                  <User className="h-3.5 w-3.5" />
                  Contact: {structured.contact_person}
                </div>
              )}
            </div>

            {/* Vehicles discussed */}
            {(structured.vehicles_discussed?.length ?? 0) > 0 && (
              <div className="rounded-xl border p-3">
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                  Vehicule discutate ({structured.vehicles_discussed.length})
                </h4>
                <div className="space-y-2">
                  {structured.vehicles_discussed.map((v, i) => (
                    <div key={i} className="rounded-lg bg-secondary/60 p-2.5">
                      <div className="flex items-center gap-1.5 mb-1">
                        <Car className="h-3.5 w-3.5 text-muted-foreground" />
                        <span className="text-xs font-semibold text-foreground uppercase">
                          {ACTION_LABELS[v.action] ?? v.action}
                        </span>
                      </div>
                      <div className="space-y-0.5 text-xs text-muted-foreground">
                        {v.current_vehicle && <p>Vehicul curent: {v.current_vehicle}</p>}
                        {v.interested_in && <p>Interesat de: {v.interested_in}</p>}
                        {v.budget_eur != null && <p>Buget: {fmtEur(v.budget_eur)}</p>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Commitments */}
            {(structured.commitments_made?.length ?? 0) > 0 && (
              <div className="rounded-xl border p-3">
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                  Angajamente ({structured.commitments_made.length})
                </h4>
                <ul className="space-y-1">
                  {structured.commitments_made.map((c, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-foreground">
                      <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-teal-600 shrink-0" />
                      {c}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Next steps */}
            {(structured.next_steps?.length ?? 0) > 0 && (
              <div className="rounded-xl border p-3">
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                  Pasi urmatori ({structured.next_steps.length})
                </h4>
                <div className="space-y-2">
                  {structured.next_steps.map((s, i) => (
                    <div key={i} className="flex items-start gap-2">
                      <Target className="h-3.5 w-3.5 mt-0.5 text-teal-600 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-foreground">{s.action}</p>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                          <span className={cn(
                            'rounded px-1.5 py-0.5 text-[10px] font-semibold',
                            s.owner === 'KAM'
                              ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300'
                              : 'bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300',
                          )}>
                            {s.owner}
                          </span>
                          {s.deadline && (
                            <span className="flex items-center gap-0.5">
                              <Calendar className="h-3 w-3" />
                              {fmtDate(s.deadline)}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Opportunity + timeline */}
            {(structured.opportunity_value_eur != null || structured.decision_timeline || structured.follow_up_date) && (
              <div className="rounded-xl border p-3">
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Oportunitate</h4>
                <div className="flex flex-wrap gap-3">
                  {structured.opportunity_value_eur != null && (
                    <div className="flex items-center gap-1.5 text-sm">
                      <Euro className="h-4 w-4 text-green-500" />
                      <span className="font-bold text-foreground">{fmtEur(structured.opportunity_value_eur)}</span>
                    </div>
                  )}
                  {structured.decision_timeline && (
                    <div className="text-xs text-muted-foreground">Decizie: {structured.decision_timeline}</div>
                  )}
                  {structured.follow_up_date && (
                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Calendar className="h-3 w-3" />
                      Follow-up: {fmtDate(structured.follow_up_date)}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Objections */}
            {(structured.objections?.length ?? 0) > 0 && (
              <div className="rounded-xl border p-3">
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                  Obiectii ({structured.objections.length})
                </h4>
                <ul className="space-y-1">
                  {structured.objections.map((o, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-foreground">
                      <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-amber-500 shrink-0" />
                      {o}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Risk flags */}
            {(structured.risk_flags?.length ?? 0) > 0 && (
              <div className="rounded-xl bg-red-50 dark:bg-red-900/20 p-3">
                <h4 className="text-xs font-semibold text-red-700 dark:text-red-300 uppercase tracking-wide mb-2 flex items-center gap-1">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  Semnale de risc
                </h4>
                <ul className="space-y-1">
                  {structured.risk_flags.map((r, i) => (
                    <li key={i} className="text-sm text-red-700 dark:text-red-300">{r}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {step === 'review' && !structured && (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <CheckCircle className="h-8 w-8 text-green-500 mb-3" />
            <p className="text-sm text-muted-foreground max-w-[280px]">
              Nota a fost salvata si vizita a fost finalizata, dar nu s-a putut genera un rezumat AI.
            </p>
          </div>
        )}
      </div>

      {step === 'input' && (
        <div className="flex gap-2 border-t border-border/60 p-4">
          <button onClick={onCancel} className="h-11 flex-1 rounded-xl border border-border text-base font-semibold active:bg-muted">
            Anuleaza
          </button>
          <button
            onClick={handleProcess}
            disabled={!rawNote.trim() || addNoteMut.isPending}
            className={cn(
              'h-11 flex-1 rounded-xl text-base font-semibold text-white transition-colors',
              rawNote.trim() && !addNoteMut.isPending ? 'bg-teal-600 active:bg-teal-700' : 'bg-muted-foreground/40 cursor-not-allowed',
            )}
          >
            <span className="flex items-center justify-center gap-2">
              <Sparkles className="h-4 w-4" />
              Proceseaza cu AI
            </span>
          </button>
        </div>
      )}

      {step === 'review' && (
        <div className="border-t border-border/60 p-4">
          <button
            onClick={handleSave}
            className="h-11 w-full rounded-xl bg-green-600 text-base font-semibold text-white active:bg-green-700 transition-colors"
          >
            <span className="flex items-center justify-center gap-2">
              <CheckCircle className="h-4 w-4" />
              {structured ? 'Salveaza nota' : 'Finalizeaza'}
            </span>
          </button>
        </div>
      )}
    </div>
  )
}
