import type { ReactNode } from 'react'
import {
  Route, ListChecks, Users, Shield, Calculator, Compass,
  ChevronRight, ShieldCheck, Lock,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

/** Breadcrumb-style path pill for pointing at a screen in the app. */
function Path({ children }: { children: ReactNode }) {
  return (
    <span className="inline-block rounded-md bg-primary/10 px-2 py-0.5 font-mono text-[11px] leading-5 text-primary">
      {children}
    </span>
  )
}

function SectionHead({ icon: Icon, eyebrow, title }: { icon: typeof Route; eyebrow: string; title: string }) {
  return (
    <div className="mb-4 flex items-center gap-3">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
        <Icon className="h-4.5 w-4.5" />
      </div>
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{eyebrow}</p>
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      </div>
    </div>
  )
}

const ACCENT = {
  hr: { dot: 'bg-violet-500', text: 'text-violet-600 dark:text-violet-400', tint: 'bg-violet-500/10', border: 'border-l-violet-500' },
  rev: { dot: 'bg-emerald-500', text: 'text-emerald-600 dark:text-emerald-400', tint: 'bg-emerald-500/10', border: 'border-l-emerald-500' },
  mgr: { dot: 'bg-blue-500', text: 'text-blue-600 dark:text-blue-400', tint: 'bg-blue-500/10', border: 'border-l-blue-500' },
} as const

type Stage = { n: string; role: keyof typeof ACCENT; state: string; who: string; desc: string; gate?: string; calm?: boolean }
const LIFECYCLE: Stage[] = [
  { n: '01', role: 'hr', state: 'Schiță', who: 'HR', desc: 'Șablon + populație (departamente sau organigramă Sincron) + calendar. Evaluările sunt generate.', gate: 'Prag · ≥3 colegi eligibili / participant' },
  { n: '02', role: 'rev', state: 'Nominalizare', who: 'HR', desc: 'Colegii sunt aleși automat din nodul de organigramă, sau nominalizați manual de HR.' },
  { n: '03', role: 'rev', state: 'Activ', who: 'Evaluatori', desc: 'Toți completează. Autosalvare, trimitere o singură dată.' },
  { n: '04', role: 'mgr', state: 'Calibrare', who: 'Manager', desc: 'Agregate provizorii + rezumat obligatoriu. Nu editează niciodată scorurile.', gate: 'Opțional · din Activ se poate publica direct', calm: true },
  { n: '05', role: 'rev', state: 'Publicat', who: 'Angajat', desc: 'Citește raportul, confirmă → deblochează planul.' },
  { n: '06', role: 'hr', state: 'Închis', who: 'HR', desc: 'Blochează. Alimentează liniile de tendință pentru ciclul următor.' },
  { n: '07', role: 'hr', state: 'Arhivat', who: 'HR', desc: 'Se aplică politica de retenție. Doar citire.' },
]

const STEPS = [
  {
    title: 'Construiește un șablon de formular',
    body: 'În Bibliotecă adaugi competențe (grupate pe clustere), apoi creezi un șablon cu o întrebare de rating per competență plus întrebări deschise și îl Publici. Un șablon publicat este imutabil — editarea creează o versiune nouă (fork), astfel ciclurile active păstrează exact formularul cu care au pornit.',
    path: 'Administrare › Bibliotecă › Șablon nou',
  },
  {
    title: 'Pornește un ciclu',
    body: 'În Cicluri deschizi asistentul. Îi dai un nume, alegi un șablon publicat și setezi datele de final evaluare și de publicare.',
    path: 'Cicluri › Ciclu nou › Detalii',
  },
  {
    title: 'Alege cine este evaluat',
    body: 'La pasul Participanți adaugi departamente întregi, sau comuți pe Organigramă Sincron și alegi noduri din arbore (fiecare arată câți oameni mapați adaugă); sau cauți individual după nume.',
    path: 'Ciclu nou › Participanți',
  },
  {
    title: 'Alege cum sunt aleși colegii',
    body: 'La Confirmare: Automat generează self + manager + subordonați direcți + N colegi din nodul de organigramă al fiecăruia; Nominalizare generează doar self / manager / subordonați și lasă colegii de ales manual. Apoi Creează + generează evaluări — ciclul ajunge în Schiță.',
    path: 'Ciclu nou › Confirmare',
  },
  {
    title: 'Rulează din centrul de control',
    body: 'Avansezi starea (Schiță → Nominalizare → Activ → …), urmărești % de completare, barele pe departamente și verificările de sănătate, și deschizi Nominalizări colegi pentru a adăuga sau schimba colegi per participant.',
    path: 'Cicluri › (status & controale)',
  },
] as const

const ROLES = [
  {
    key: 'rev' as const, badge: 'A', role: 'Angajat & Evaluator', tag: 'Partea de captare — mobile-first',
    items: [
      ['Oferă feedback.', 'O competență per ecran, 1–5 sau „Nu am observat”, autosalvare la fiecare atingere.'],
      ['Trimite o singură dată.', 'Tranzacțional și imutabil — fără editări după.'],
      ['Citește-ți raportul', '— radar self vs. ceilalți, diferențe, Johari — apoi confirmă și construiești un plan de dezvoltare.'],
    ],
    foot: 'Vede: propriul inbox, propriile nominalizări și propriul raport publicat.',
  },
  {
    key: 'mgr' as const, badge: 'M', role: 'Manager', tag: 'Partea de calibrare — Echipa',
    items: [
      ['Panou de echipă.', 'Fiecare raport: număr de evaluatori, status, debrief.'],
      ['Calibrează.', 'Agregate provizorii + semnalări de outlier; scrii un rezumat obligatoriu de 300–1500 caractere — context, niciodată editare de scor.'],
      ['Publică.', 'Gated de manager — blocat până la salvarea rezumatului.'],
      ['Co-deține', 'planul de dezvoltare și check-in-urile lui.'],
    ],
    foot: 'Vede: doar rapoartele subordonaților direcți — niciodată identitatea evaluatorului.',
  },
  {
    key: 'hr' as const, badge: 'H', role: 'HR admin', tag: 'Partea de orchestrare — doar status',
    items: [
      ['Bibliotecă.', 'Creează competențe și șabloane, publică, forkuiește versiuni noi.'],
      ['Ciclu nou.', 'Asistent: șablon → populație → mod colegi → generare.'],
      ['Centru de control.', '% completare, bare pe departamente, verificări de sănătate, Nominalizări per participant.'],
      ['Nu vede niciodată răspunsurile', '— doar status și agregate, impus server-side.'],
    ],
    foot: 'Vede: completare și agregate — niciodată conținutul răspunsurilor.',
  },
] as const

const SCORING = [
  ['categorie', 'Media rating-urilor acelei relații — „Nu am observat” exclus, afișat doar la n ≥ 3.'],
  ['ceilalți', 'Media mediilor pe categorii — nu pooled, astfel un grup mare de colegi nu poate îneca subordonații direcți.'],
  ['gap', 'self − ceilalți. |gap| ≥ 1.0 semnalează o plasare Johari.'],
  ['Johari', 'Împărțit la 3.5 / 3.5 → putere confirmată · punct orb · putere ascunsă · creștere agreată.'],
] as const

const JOHARI = [
  { label: 'Putere confirmată', hint: 'self ↑ · ceilalți ↑', cls: 'bg-emerald-500/10 border-emerald-500/40 text-emerald-600 dark:text-emerald-400' },
  { label: 'Punct orb', hint: 'self ↓ · ceilalți ↑', cls: 'bg-amber-500/10 border-amber-500/40 text-amber-600 dark:text-amber-400' },
  { label: 'Putere ascunsă', hint: 'self ↑ · ceilalți ↓', cls: 'bg-blue-500/10 border-blue-500/40 text-blue-600 dark:text-blue-400' },
  { label: 'Creștere agreată', hint: 'self ↓ · ceilalți ↓', cls: 'bg-rose-500/10 border-rose-500/40 text-rose-600 dark:text-rose-400' },
] as const

const NAV = [
  { key: 'hr' as const, role: 'HR', p2: 'Creează, lansează și monitorizează', stat: 'Bibliotecă (competențe + șabloane) · asistent Ciclu nou · centru de control · Nominalizări.', path: 'Evaluări 360 › Administrare' },
  { key: 'rev' as const, role: 'Angajat', p2: 'Oferă feedback · citește', stat: 'Completează evaluările atribuite · citește raportul publicat și planul de dezvoltare.', path: 'Evaluări 360 › De completat / Rapoartele mele' },
  { key: 'mgr' as const, role: 'Manager', p2: 'Calibrează și publică', stat: 'Rapoarte de echipă, rezumat obligatoriu, publicare gated de manager, planuri de dezvoltare partajate.', path: 'Evaluări 360 › Echipa' },
] as const

export default function Help() {
  return (
    <div className="mx-auto max-w-4xl space-y-10 pb-12">
      {/* Intro */}
      <Card className="overflow-hidden border-none bg-gradient-to-br from-slate-900 to-slate-800 text-slate-100">
        <CardContent className="space-y-2 py-6">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Ghid · Evaluări 360°</p>
          <h1 className="text-2xl font-bold tracking-tight">Cum configurezi și rulezi un ciclu de evaluare</h1>
          <p className="max-w-2xl text-sm leading-relaxed text-slate-300">
            Un ciclu strânge feedback despre fiecare participant din mai multe perspective, îl agregă anonim și îl
            transformă într-un raport și un plan de dezvoltare. Avansează câte o stare pe rând; o verificare poate
            opri o tranziție până când configurarea e corectă.
          </p>
        </CardContent>
      </Card>

      {/* Lifecycle */}
      <section>
        <SectionHead icon={Route} eyebrow="Ciclul de viață" title="Un ciclu, șapte stări — doar înainte, cu verificări" />
        <div className="overflow-x-auto pb-2">
          <div className="flex min-w-[860px] items-stretch gap-2">
            {LIFECYCLE.map((s, i) => {
              const a = ACCENT[s.role]
              return (
                <div key={s.n} className="flex flex-1 items-stretch gap-2">
                  <div className="flex flex-1 flex-col gap-2">
                    <div className={cn('h-full rounded-xl border border-t-2 bg-card p-3 shadow-sm', a.border.replace('border-l-', 'border-t-'))}>
                      <p className={cn('font-mono text-[11px] font-semibold', a.text)}>{s.n}</p>
                      <p className="mt-0.5 text-sm font-semibold tracking-tight">{s.state}</p>
                      <p className="mt-0.5 text-[11px] text-muted-foreground">{s.who}</p>
                      <p className="mt-2 text-xs leading-snug text-foreground/80">{s.desc}</p>
                    </div>
                    {s.gate && (
                      <p className={cn(
                        'rounded-lg border border-dashed px-2 py-1 text-[10.5px] font-medium leading-tight',
                        s.calm ? 'border-border bg-muted text-muted-foreground' : 'border-amber-500/50 bg-amber-500/10 text-amber-600 dark:text-amber-400',
                      )}>
                        {s.gate}
                      </p>
                    )}
                  </div>
                  {i < LIFECYCLE.length - 1 && (
                    <div className="flex items-start pt-8 text-muted-foreground/40">
                      <ChevronRight className="h-4 w-4" />
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5"><i className={cn('h-2.5 w-2.5 rounded-sm', ACCENT.hr.dot)} /> HR orchestrează</span>
          <span className="inline-flex items-center gap-1.5"><i className={cn('h-2.5 w-2.5 rounded-sm', ACCENT.rev.dot)} /> Evaluatori & angajați</span>
          <span className="inline-flex items-center gap-1.5"><i className={cn('h-2.5 w-2.5 rounded-sm', ACCENT.mgr.dot)} /> Managerii calibrează</span>
          <span className="inline-flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-sm bg-amber-500" /> Verificare (prag)</span>
        </div>
      </section>

      {/* Setup steps */}
      <section>
        <SectionHead icon={ListChecks} eyebrow="Configurare ciclu · HR" title="Cinci pași, toți în interfață — fără script" />
        <p className="mb-4 text-sm text-muted-foreground">
          Tot ce urmează se află sub <Path>HR › Evaluări 360 › Administrare</Path>, care are două tab-uri:{' '}
          <b className="text-foreground">Cicluri</b> (centrul de control) și{' '}
          <b className="text-foreground">Bibliotecă</b> (competențe & șabloane).
        </p>
        <div className="space-y-3">
          {STEPS.map((s, i) => (
            <Card key={s.title}>
              <CardContent className="flex gap-4 py-4">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-violet-500 text-sm font-bold text-white">
                  {i + 1}
                </div>
                <div className="space-y-2">
                  <h3 className="text-sm font-semibold tracking-tight">{s.title}</h3>
                  <p className="text-[13px] leading-relaxed text-foreground/80">{s.body}</p>
                  <Path>{s.path}</Path>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Population & peers */}
      <section>
        <SectionHead icon={Users} eyebrow="Cine oferă feedback" title="Populație & colegi — două alegeri independente" />
        <div className="grid gap-4 md:grid-cols-2">
          <Card className="border-l-2 border-l-blue-500">
            <CardContent className="space-y-3 py-4">
              <h3 className="text-sm font-semibold">Populație — cine este evaluat</h3>
              <div>
                <p className="text-[13px] font-semibold">Departamente</p>
                <p className="text-[13px] leading-relaxed text-foreground/80">Câmpul de departament liber-text de pe fiecare utilizator. Rapid, dar dezordonat acolo unde câmpul conține funcții sau e gol.</p>
              </div>
              <div className="border-t border-dashed pt-3">
                <p className="flex items-center gap-2 text-[13px] font-semibold">
                  Organigramă Sincron <Badge variant="secondary" className="text-emerald-600 dark:text-emerald-400">recomandat</Badge>
                </p>
                <p className="text-[13px] leading-relaxed text-foreground/80">Arborele organizațional Sincron, per companie. Alegi un nod și adaugă utilizatorii JARVIS activi mapați sub el (și sub-echipele lui). Numărul de pe fiecare nod e exact câți adaugă.</p>
              </div>
            </CardContent>
          </Card>
          <Card className="border-l-2 border-l-emerald-500">
            <CardContent className="space-y-3 py-4">
              <h3 className="text-sm font-semibold">Colegi — cine îi evaluează</h3>
              <div>
                <p className="text-[13px] font-semibold">Automat</p>
                <p className="text-[13px] leading-relaxed text-foreground/80">Un <b>eșantion aleatoriu</b> de co-membri din nodul de organigramă Sincron al persoanei — așa o echipă mare nu mai produce mereu aceiași câțiva colegi (alfabetic). Revine la colegii din același departament când cineva nu e în organigramă.</p>
              </div>
              <div className="border-t border-dashed pt-3">
                <p className="text-[13px] font-semibold">Nominalizare — HR</p>
                <p className="text-[13px] leading-relaxed text-foreground/80">HR alege manual colegii per participant în <Path>Cicluri › Nominalizări</Path>. Angajații nu își aleg singuri evaluatorii — selecția e controlată de HR. Evaluările deja trimise sunt blocate și nu pot fi eliminate.</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Roles */}
      <section>
        <SectionHead icon={Compass} eyebrow="Trei perspective" title="Ce face fiecare persoană, concret" />
        <div className="grid gap-4 md:grid-cols-3">
          {ROLES.map((r) => {
            const a = ACCENT[r.key]
            return (
              <Card key={r.role} className="flex flex-col overflow-hidden">
                <div className={cn('border-b px-4 py-3', a.tint)}>
                  <div className={cn('flex items-center gap-2 text-sm font-semibold', a.text)}>
                    <span className={cn('flex h-6 w-6 items-center justify-center rounded-md text-xs text-white', a.dot)}>{r.badge}</span>
                    {r.role}
                  </div>
                  <p className="mt-1 text-[11px] text-muted-foreground">{r.tag}</p>
                </div>
                <ul className="flex flex-1 flex-col gap-2.5 px-4 py-3">
                  {r.items.map(([b, rest]) => (
                    <li key={b} className="grid grid-cols-[10px_1fr] gap-2 text-[13px] leading-snug">
                      <span className={cn('font-bold', a.text)}>—</span>
                      <span><b className="font-semibold">{b}</b> {rest}</span>
                    </li>
                  ))}
                </ul>
                <p className="border-t border-dashed px-4 py-2.5 text-[11px] text-muted-foreground">{r.foot}</p>
              </Card>
            )
          })}
        </div>
      </section>

      {/* Guarantees */}
      <section>
        <SectionHead icon={Shield} eyebrow="De ce e de încredere" title="Două garanții, impuse pe server" />
        <div className="grid gap-4 md:grid-cols-2">
          <Card className="border-l-2 border-l-emerald-500">
            <CardContent className="space-y-2 py-4">
              <h3 className="flex items-center gap-2 text-sm font-semibold"><ShieldCheck className="h-4 w-4 text-emerald-500" /> Anonimat — fail-closed</h3>
              <p className="text-[13px] leading-relaxed text-foreground/80">
                O categorie de relație se afișează doar cu <b>≥ 3 răspunsuri trimise</b>. Self și manager sunt mereu
                atribuite; sub prag, o categorie e ascunsă și rating-urile ei nu părăsesc niciodată serverul.
              </p>
              <div className="flex flex-wrap gap-2 pt-1">
                <Badge variant="secondary" className="text-emerald-600 dark:text-emerald-400">Colegi n=5 · afișat</Badge>
                <Badge variant="secondary" className="text-muted-foreground">Subordonați n=1 · ascuns</Badge>
              </div>
            </CardContent>
          </Card>
          <Card className="border-l-2 border-l-blue-500">
            <CardContent className="space-y-2 py-4">
              <h3 className="flex items-center gap-2 text-sm font-semibold"><Lock className="h-4 w-4 text-blue-500" /> Imutabilitate</h3>
              <p className="text-[13px] leading-relaxed text-foreground/80">
                Schițele se autosalvează per întrebare, idempotent. <b>Trimiterea e write-once.</b> Niciun endpoint nu
                returnează vreodată răspunsuri individuale non-self — nimănui, inclusiv HR. Fiecare citire de raport e
                pre-agregată server-side.
              </p>
              <div className="flex flex-wrap gap-2 pt-1">
                <Badge variant="secondary" className="text-emerald-600 dark:text-emerald-400">schiță · idempotent</Badge>
                <Badge variant="secondary" className="text-muted-foreground">trimitere · write-once</Badge>
                <Badge variant="secondary" className="text-rose-600 dark:text-rose-400">n&lt;3 → blocat</Badge>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Scoring */}
      <section>
        <SectionHead icon={Calculator} eyebrow="Calculul" title="Cum se construiesc scorurile" />
        <div className="grid gap-4 md:grid-cols-[1.4fr_1fr]">
          <Card>
            <CardContent className="space-y-3 py-4">
              {SCORING.map(([k, v]) => (
                <div key={k} className="flex items-start gap-3">
                  <span className="mt-0.5 shrink-0 rounded-md bg-primary/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-primary">{k}</span>
                  <p className="text-[13px] leading-snug text-foreground/80">{v}</p>
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardContent className="grid grid-cols-2 gap-2 py-4">
              {JOHARI.map((q) => (
                <div key={q.label} className={cn('rounded-lg border p-3', q.cls)}>
                  <p className="text-[12px] font-semibold leading-tight">{q.label}</p>
                  <p className="mt-1 text-[10.5px] text-muted-foreground">{q.hint}</p>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Nav map */}
      <section>
        <SectionHead icon={Compass} eyebrow="Unde găsești" title="Fiecare ecran, pe rol" />
        <div className="grid gap-4 md:grid-cols-3">
          {NAV.map((d) => {
            const a = ACCENT[d.key]
            return (
              <Card key={d.role} className={cn('border-t-2', a.border.replace('border-l-', 'border-t-'))}>
                <CardContent className="space-y-2 py-4">
                  <p className={cn('text-sm font-semibold', a.text)}>{d.role}</p>
                  <p className="text-xs text-muted-foreground">{d.p2}</p>
                  <p className="text-[13px] leading-relaxed text-foreground/80">{d.stat}</p>
                  <Path>{d.path}</Path>
                </CardContent>
              </Card>
            )
          })}
        </div>
      </section>
    </div>
  )
}
