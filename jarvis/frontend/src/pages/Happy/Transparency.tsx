import { PageHeader } from '@/components/shared/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

/**
 * "Cum funcționează Happy" — the transparency / data-processing notice required
 * by spec §9.1 (Law 190/2018 Art. 5, prior explicit information). Static content,
 * no API calls. Login-gated but visible to every employee.
 */
export default function HappyTransparency() {
  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader title="Cum funcționează Happy" description="Transparență privind datele" />

      <div className="mx-auto max-w-3xl space-y-4">
        <p className="text-sm text-muted-foreground">
          Happy este modulul intern prin care primești anunțuri, confirmi informări importante,
          trimiți aprecieri colegilor și răspunzi la sondaje scurte (Pulse).
        </p>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Ce înregistrăm</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3 text-sm text-muted-foreground">
              <li>
                <span className="font-medium text-foreground">Anunțuri (Spotlight / Marquee):</span>{' '}
                dacă ți-a fost afișat un anunț, dacă a fost citit (vizibil ≥ 8 secunde), dacă ai dat
                click și dacă ai confirmat (cu data confirmării).
              </li>
              <li>
                <span className="font-medium text-foreground">Confirmări obligatorii:</span>{' '}
                data și metoda (bifă sau test de înțelegere). La testul de înțelegere păstrăm doar
                statistici agregate pe întrebare — niciodată răspunsurile tale individuale.
              </li>
              <li>
                <span className="font-medium text-foreground">Aprecieri (Praise):</span>{' '}
                cine a trimis, cui, mesajul, eticheta de valoare și punctele. Nu există clasamente.
              </li>
              <li>
                <span className="font-medium text-foreground">Pulse (sondaje):</span>{' '}
                răspunsurile sunt anonime — nu stocăm cine a răspuns. Rezultatele se raportează doar
                agregat, pe grupuri de minim 5 persoane, iar data e păstrată fără oră.
              </li>
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Cât timp păstrăm</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3 text-sm text-muted-foreground">
              <li>
                <span className="font-medium text-foreground">
                  Datele brute de interacțiune (afișări, citiri, click-uri):
                </span>{' '}
                maximum 30 de zile, apoi șterse automat.
              </li>
              <li>
                <span className="font-medium text-foreground">
                  Confirmările la informări obligatorii:
                </span>{' '}
                păstrate ca dovadă de conformitate, pe o bază legală separată.
              </li>
              <li>
                <span className="font-medium text-foreground">Răspunsurile Pulse:</span>{' '}
                anonime și agregate, fără legătură cu persoana.
              </li>
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Cine poate vedea</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3 text-sm text-muted-foreground">
              <li>
                <span className="font-medium text-foreground">Tu</span> — propriile tale date și
                propriul istoric de aprecieri.
              </li>
              <li>
                <span className="font-medium text-foreground">Manageri / HR</span> — doar statistici
                agregate (rate de citire/confirmare pe echipă, tendințe) pe grupuri; niciodată
                activitatea individuală, niciun clasament.
              </li>
              <li>
                <span className="font-medium text-foreground">Singura excepție:</span>{' '}
                lista de confirmări pentru un anunț obligatoriu (export de conformitate), accesibilă
                doar cu o permisiune specială, iar fiecare accesare este înregistrată (audit).
              </li>
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Ce NU facem</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3 text-sm text-muted-foreground">
              <li>fără clasamente între angajați;</li>
              <li>fără puncte pentru activitate (postare / citire / logare);</li>
              <li>fără tablouri individuale de „cine a citit ce” pentru manageri.</li>
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Baza legală</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              anunțurile operaționale se bazează pe interesul legitim / obligația legală
              (Art. 6(1)(b)/(f)); aprecierile și mesajele sociale se bazează pe consimțământ, pe care
              îl poți retrage oricând din Preferințe.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Controalele tale</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              din Preferințe poți activa/dezactiva notificările pe categorii (Anunțuri, Aprecieri,
              Pulse, Social) și poți seta orele de liniște. Anunțurile marcate critic (obligatorii
              legal) pot depăși orele de liniște — fiecare astfel de caz este înregistrat, cu numele
              campaniei și cine a autorizat-o.
            </p>
          </CardContent>
        </Card>

        <p className="border-t pt-4 text-xs text-muted-foreground">
          Întrebări? Contactează Responsabilul cu Protecția Datelor. [email DPO]
        </p>
      </div>
    </div>
  )
}
