import { useState } from 'react'
import { HelpCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'

type StepItem = { title: string; body: string }
type StatusItem = { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline'; body: string }

const STEPS: StepItem[] = [
  {
    title: 'Creezi evenimentul',
    body: 'Creează o pagină, adaugă mașinile (fiecare cu un consilier implicit), setează zilele și orele, apoi apasă Generează intervalele și Deschide pagina.',
  },
  {
    title: 'Clientul se programează',
    body: 'Deschide linkul public /td/<slug>, alege o mașină și un interval, lasă nume, telefon și email. Fără login.',
  },
  {
    title: 'Confirmă pe email',
    body: 'Primește un link Confirmă / Anulează. Clic-ul confirmă programarea și dovedește adresa. Rezervările neconfirmate expiră și eliberează intervalul.',
  },
  {
    title: 'Devine o probă reală',
    body: 'La confirmare se creează o fișă de test drive PLANIFICAT, atribuită consilierului mașinii (care e notificat).',
  },
  {
    title: 'Proba are loc la eveniment',
    body: 'Consilierul o activează ca de obicei: semnătură, acord GDPR, kilometraj, PDF.',
  },
]

const STATUSES: StatusItem[] = [
  { label: 'pending_confirm', variant: 'outline', body: 'ține intervalul, așteaptă confirmarea pe email.' },
  { label: 'confirmed', variant: 'default', body: 'confirmată; fișă PLANIFICATĂ creată.' },
  { label: 'completed', variant: 'default', body: 'proba făcută și mașina returnată.' },
  { label: 'cancelled', variant: 'destructive', body: 'anulată; interval eliberat.' },
  { label: 'expired', variant: 'secondary', body: 'neconfirmată la timp; interval eliberat automat.' },
  { label: 'conflict', variant: 'destructive', body: 'mașina a fost ocupată altundeva înainte de confirmare (semnalat, nu dublu-rezervat).' },
]

const GOOD_TO_KNOW = [
  'Fără dublu-rezervări — baza de date garantează o singură programare per interval; confirmarea reverifică disponibilitatea mașinii.',
  'Rezervările neconfirmate expiră automat și eliberează intervalul.',
  'E notificat consilierul potrivit — implicit per mașină, reatribuibil per programare.',
  'Formularul public e limitat ca rată, iar clic-ul din email verifică adresa.',
]

/** "Cum funcționează" help dialog for the Evenimente TD admin screen -- a
 *  static walkthrough of the create → book → confirm → drive flow and the
 *  booking status machine, so staff don't need tribal knowledge to use the
 *  module. Purely presentational; no data fetching. */
export default function TdBookingHelp() {
  const [open, setOpen] = useState(false)

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        <HelpCircle className="mr-1.5 h-4 w-4" />Cum funcționează
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Cum funcționează Evenimente TD</DialogTitle>
          </DialogHeader>

          <div className="space-y-5 text-sm">
            <p className="text-muted-foreground">
              Programări publice de test drive. Creezi un eveniment cu mașinile și orele
              disponibile, clienții se programează singuri printr-un link public, iar la
              confirmare fiecare programare devine o fișă de parcurs planificată, atribuită
              unui consilier.
            </p>

            <section className="space-y-2">
              <h4 className="text-sm font-semibold">Pași</h4>
              <ol className="list-decimal space-y-2 pl-5">
                {STEPS.map((step) => (
                  <li key={step.title}>
                    <span className="font-medium">{step.title}</span>
                    {' — '}
                    <span className="text-muted-foreground">{step.body}</span>
                  </li>
                ))}
              </ol>
            </section>

            <section className="space-y-2">
              <h4 className="text-sm font-semibold">Stările unei programări</h4>
              <ul className="space-y-1.5">
                {STATUSES.map((s) => (
                  <li key={s.label} className="flex items-start gap-2">
                    <Badge variant={s.variant} className="mt-0.5 font-mono">{s.label}</Badge>
                    <span className="text-muted-foreground">{s.body}</span>
                  </li>
                ))}
              </ul>
            </section>

            <section className="space-y-2">
              <h4 className="text-sm font-semibold">Bine de știut</h4>
              <ul className="list-disc space-y-1.5 pl-5 text-muted-foreground">
                {GOOD_TO_KNOW.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </section>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
