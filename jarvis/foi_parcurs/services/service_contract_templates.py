"""AutoWorld courtesy-car ("Service") rental contract templates.

Extracted verbatim from the legacy AutoWorld Word documents in
~/Desktop/cortoazie (face `rev6` + termeni si conditii `rev7_2023`), with the
company/client/vehicle/pricing blanks replaced by curly-brace tokens so ONE
template can serve every company (resolved from the `companies` row) and
every Service session. Plain string constants only — no logic. Substitution
happens in render_contract_template() (contract_template.py) against the
PLACEHOLDERS whitelist.
"""

SERVICE_CONTRACT_FACE = """CONTRACT INCHIRIERE AUTO

Partile contractante:

{company_name}, cu sediul in {company_street}, {company_city}, jud. {company_county}, numar de ordine in Registrul Comertului {company_reg_no}, CUI {company_vat}, cont {company_iban}, deschis la {company_bank}, telefon: {dealer_phone}, reprezentata de {company_administrator}, denumita in continuare „Prestator”,
si
Dl./D-na/ {client_name}, cu adresa {client_address}, serie si numar C.I. /Pasaport {client_ci_serie}, tel. {client_phone}, e-mail {client_email}, reprezentant al S.C. {client_company}, identificat cu CUI {client_cui}, denumita in continuare „Beneficiar”

Obiectul si durata contractului:

Il constituie inchirierea autovehiculului marca {brand}, model {vehicle_model}, serie sasiu: {vin}, nr inmatriculare {registration_number}, cu incepere din data {departure_datetime}, pana la data {return_datetime}.

Autoturismul este preluat de catre beneficiar conform procesului Verbal de Predare Primire urmand sa fie predat ca atare.

Observatii la predare catre client (daune):	Observatii la primire de la client (daune):

KM la predarea catre client:	Data/Ora:
KM la preluarea de la client:	Data/Ora:

Autoturismul a fost predat cu: 1 cheie, certificat de inmatriculare sau autorizatie provizorie de circulatie, asigurare RCA,  respectiv trebuie alimentat cu combustibil  benzina/motorina tip EURO V.

Tarif:
Tariful este de {svc_tariff_eur} EUR/{svc_rate_basis}. Total {svc_units} × {svc_tariff_eur} = {svc_total_eur} EURO inclusiv TVA. Limita km/zi {svc_limita_km_zi}, km depasiti fiind facturati cu {svc_extra_km_eur} EUR/km. Garantia depusa de catre Beneficiar este in cuantum de {svc_garantie_eur} EURO.
Fransiza in caz de dauna partiala {svc_fransiza_eur} EUR.
Plata pretului se va efectua in lei, la cursul valutar Autoworld afisat la casierii, la data emiterii facturii.

Prin semnarea prezentului contract, beneficiarul recunoaste ca a citit, a inteles si se obliga sa respecte prezentele conditii contractuale anexate.
"""


SERVICE_CONTRACT_TERMS = """I.Cadru General. Definiții
Locatorul autovehiculului {company_name}, cu sediul in {company_street}, {company_city}, numar de ordine in Registrul Comertului {company_reg_no}, Cod Unic de Inregistrare {company_vat}, cont nr. {company_iban} deschis la {company_bank}, reprezentant legal {company_administrator}, telefon: {dealer_phone}, email: {company_email} denumita in continuare "Prestator”
Persoana care închiriază identificată în condițiile specifice  „Beneficiar” (astfel denumită în continuare)

Condiții specifice: clauzele contractului de închirere încheiat asumate prin semnatură de către părți și care cuprind datele Beneficiarului, datele autovehiculului, durata de închirere, tariful, datele conducătorului auto și garanție.
Autoturism/ Autovehicul - reprezintă autovehiculul descris în Informații Autovehicul din contractul de închiriere.
Rezervare - exprimarea în scris (personal sau prin mijloace de comunicare la distanță) a intenției Beneficiarului de a încheia contractul de închiriere auto cu indicarea perioadei și a tipului de autovehicul in condițiile contractuale și de preț utilizate de Prestator urmată de confirmarea de către Prestator a disponibilității autovehiculului.
Teritoriul - teritoriul pe care poate fi utilizat autovehiculul (teritoriul  este România cu excepția cazului în care nu se stabilește în scris și expres că teritoriul este Uniunea Europeană)
Garanția – reprezintă suma ce trebuie achitată de către Prestatator sau autorizată pe cardul de credit/debit al Prestatatorului și care va putea fi retinuță de catre prestator în conformitate cu condițiile prevăzute în prezentele Condiții contractuale. 
2. OBIECTUL CONTRACTULUI
2.1 Obiectul prezentului contract constă în darea în folosință de către Prestator către Beneficiar a Autovehiculului cu caracteristicile detaliate în contractul de închiriere, în condițiile contractuale mai jos stabilite.
2.2. La solicitarea Beneficiarului și în limita disponibilității Prestatorului, se vor furniza, contra cost, odată cu autovehiculul dispozitive sau echipamente speciale cum ar fi scaun pentru copii, suporturi biciclete, cutie de bagaj…etc, costul acestor accesorii se va comunica la cerere nefiind incluse in tarifele de închiriere ale autovehiculelor.

3. DURATA CONTRACTULUI
Autovehiculul se închiriază pentru perioada specificată în contractul de închiriere. În cazul neindeplinirii de către Beneficiar al obligațiilor contractuale, prestatorul poate rezilia contractul unilateral fără notificarea în prealabil al beneficiarului, fără somație și fără intervenția instanței de judecată, sens în care înțelegem ca, potrivit prezentului document privind ”Termenii și condițiile”, ca de altfel și potrivit contractului de închiriere, această clauză să reprezinte un pact comisoriu expres de grad IV. De asemenea, în cazul neîndeplinirii obligațiilor Beneficiarului și a rezilierii unilaterale a Contractului de închiriere, Prestatorul are dreptul de a recupera și de intra în posesia bunului proprietatea sa prin mijloace aflate la dispoziție.

4. PREDAREA AUTOVEHICULULUI. RESTITUIREA AUTOVEHICULULUI.
4.1 Predarea către Beneficiar a autovehiculului va fi realizată în Cluj-Napoca, str. Calea Floresti Nr. 145. Calea Turzii Nr. 249, sau str. Oradiei nr. 1-3-5-7, a sediul Volkswagen,  Audi sau Volvo/Carcloud. Părțile pot conveni ca predarea autovehiculului către sau la  Beneficiar să aibă Ioc într-o altă locație pe teritoriul României însă numai dacă s-a convenit astfel în scris și sub condiția plății unei taxe suplimentare de comun acord convenite. 
4.2 La predarea autoturismului către Beneficiar se va semna rubrica aferentă din contractul de închiriere și se vor menționa în mod obligatoriu toate eventualele avarii, zgârieturi, lovituri sau abateri de la planeitate ale caroseriei, orice fisuri sau imperfecțiuni ale geamurilor, farurilor ori stopurilor autovehiculului, orice lipsuri din dotarea autovehiculului, orice rupturi sau pete ale materialelor din interiorul autovehiculului.
Cu ocazia predării autovehiculului către Beneficiar se predă in original certificatul de înmatriculare si polița RCA. Prin semnarea procesului verbal de primire predare, Beneficiarul atestă că a intrat în posesia  acestor acte in original, fără să fie necesară nicio mențiune suplimentară.
Autovehiculul se preda cu rezervorul de carburant plin cu excepția cazului în care se specifică altfel in contractul de inchireiere.
Autovehiculul va fi predat într-o stare de conformitate optima pentru a da posibilitatea evaluării structurii exterioare a caroseriei. Dacă autovehiculul este returnat către Prestator într-o stare necorespunzătoare sau este murdar, aceste aspect vor fi consemnate în procesul-verbal de recepție.
În situația în care autovehiculul este returnat către Prestator necorespunzător, murdar sau în afara orelor de program ale Prestatorului, acesta din urmă va comunica neconformitățile constatate ca urmare a inspecției autovehiculului într-un termen de 24 h care va începe să curgă din ziua lucrătoare următoare predării. 
4.3 Beneficiarul se obligă să restituie autovehiculul la data și ora menționata  în Contractul de închiriere în locul din care acesta a fost preluat. 
În ipoteza în care Beneficiarul nu va restitui autovehiculul la ora și data convenită, restituindu-l cu o întârziere mai mare de 2 ore si/sau  în afara orelor de program ale Prestatorului, Beneficiarul va achita, suplimentar, taxa aferentă unei zile de închiriere.
4.4 Cu excepția cazului în care nivelul de carburant nu este consemnat ca fiind mai mic în fișa de predare, autovehiculul se restituie cu rezervorul de carburant plin. În cazul în care se constată la restituirea autovehiculului că acesta nu are rezervorul plin (sau la nivelul menționat in fișa de predare), Beneficiarul va achita o taxa de 140 Euro (TVA inclus). Restituirea autovehiculului se va considera a fi avut loc doar în urma semnării rubricii aferente din fișa de predare de către reprezentantul Prestatorului.
4.5 Autovehiculul va fi returnat cu anvelopele cu care a fost echipat la momentul predării, orice schimbare fiind imputată Beneficiarului, care va achita costul acestora.
5. PREȚUL CONTRACTULUI
5.1 Tarifele sunt cele menționate în contractul de închiriere.
Pentru stabilirea distanței parcurse de către Beneficiar cu autovehiculul închiriat se va avea în vedere diferența dintre numarul de km parcurși astfel cum acestia sunt indicati de către instrumentele de bord la momentul restituirii autovehiculului către Prestator și numărul de km parcurși astfel cum acestia sunt indicați de aparatele de bord la momentul predării autoturismului către Beneficiar în vederea folosirii și cum au fost consemnați în procesul verbal-de predare-primire.
Pentru deplasările în străinătate, tarifele de inchiriere se majorează cu 10% .
Pentru fiecare persoană suplimentar împutemicita de către Beneficiar sa conducă autovehiculul, Prestatorul va putea percepe o taxa de 25 euro (TVAinclus) ținând cont de vârsta și experiența împuternicitului in calitate de conducător auto.
 5.2 Plata prețului se va efectua în lei, la cursul valutar Autoworld afisat la casierii, cel târziu în momentul preluării autovehiculului de către Beneficiar. Neplata sumei de închiriere stabilită potrivit contractului de închiriere și potrivit prezenților termeni și condiții, respective anterior predării autovehiculului, va duce la refuzul Prestatorului de a preda autovehiculul rezervat sau a cărui închiriere se dorește, Beneficiarul nefiind în drept să îl preia ca urmare a rezilierii de drept a Contractului de închiriere. Autovehiculele sunt prevăzute cu limita de km/zi menționate în contractului de închiriere. Atunci când Beneficiarul depășește limita maximă de km, diferența se va achita Ia momentul predării autovehiculului de Beneficiar către Prestator.
5.3 Neplata la termen a facturilor emise de prestator către  Beneficiar generează penalități de 2%/zi de intarziere aplicată asupra valorii debitului restant, până la plata integrală a debitului, valoarea penalităților putând depăși suma la care se aplică.

6. OBLIGAȚIILE PĂRȚILOR

6.1 Obligațiile și drepturile Prestatoului 
6.1.1 Să transmită Beneficiarului dreptul de folosinta asupra autovehiculului ce face obiectul contractului pentru durata și în limitele convenite, intrunind toate condițiile tehnice de folosire, fiind în stare normală de funcționare și neavând defecte și lipsuri.
6.1.2. Să remită Beneficiarului autovehiculul ce face obiectul prezentului contract împreuna cu toate documentele necesare pentru utilizarea lui și conducerea lui pe drumurile publice conform legii (certificat de înmatriculare în orignal și asigurarea RCA) precum și toate celelalte dotări corespunzatoare conform mențiunilor din fișa de predare-preluare.
6.1.3 Să asigure taxa de drum datorată în Romania (rovigneta), polița RCA, nu include taxa de Pod Fetești pentru autovehiculul închiriat, totodată, Prestatorul achită și polița de asigurare CASCO contra accidentelor și contra furtului în condițiile mentionate in art 9 Asiguarea Auto.
6.1.4 Să informeze Beneficiarul asupra faptului dacă autoturismul este prevăzut sau nu cu sistem de monitorizare GPS.
6.1.5 Prestatorul are dreptul de a solicita Beneficiarului informații legate de starea și locația autovehicului și permisiune de a verifica vehiculul fizic in timpul derulării contractului.
6.1.6 Prestatorul nu răspunde de distrugerea sau furtul bunurilor aparținând Beneficiarului sau al pasagerilor, din autovehicul pe parcursul derulării contractului de închiriere.

6.2 Obligațiile și drepturile Beneficiarului 
6.2.1. Autovehiculul poate fi condus numai de persoane care au împlinit 20 ani, dețin un permis de conducere valabil și care a fost dobândit de cel putin cu 2 ani înanintea semnarii contractului de închiriere. În cazul rezervărilor de autovehicule efectuate prin mijloace de comunicare la distanță, Prestatorul iși rezervă dreptul de a anula rezervarea la propria lui discreție, dacă ulterior se dovedește că Beneficiarul nu indeplinește condițiile impuse de lege sau prezentul Contract.
Autovehiculul poate fi condus doar de către persoana /persoanele a/ale cărui/căror permise de conducere au fost comunicate Prestatorului și care figurează ca utilizator în cadrul Contractului de închiriere. Prestatorul nu își asumă nicio responsabilitate cu privire la alte persoane cărora, fără drept, Beneficiarul le permite utilizarea autovehiculului. Clauza de nerăspundere include – dar nu se limitează la – permisiunea utilizării autovehiculului persoanelor care nu dețin permis de conducere sau permis de conducere internațional conform clauzei 6.2.2. de mai jos ori dețin permis de conducere a cărui valabilitate a expirat. Încălcarea obligației de a nu permite altor persoane utilizarea autovehiculului atrage rezilierea de drept a Contractului de închiriere, fără notificare, somație sau apelul la instanța de judecată, înțelegându-se că valoarea prezentei clauze este aceea a unui pact comisoriu expres de grad IV.
6.2.2. Autovehiculul poate fi condus numai de persoane care dețin un permis de conducere international, atunci când acesta este emis de un stat în care condusul autovehiculelor are loc pe partea dreaptă a carosabilului sau atunci când permisul emis de un stat în care nu se folosește alfabetul latin.
6.2.3 Beneficiarul are obligația ca la semnarea contractului să prezinte permisul de conducere în original, actul de identitate/pașaport și un card de credit. 
6.2.4. Autoturismul poate fi condus numai pe drumuri publice. Atunci când autovehiculul va fi condus de către o altă persoană decât Beneficiarul -cu acceptul Prestatorului- sau atunci când mai mult de o persoană va conduce autovehiculul închiriat, aceste persoane vor fi expres nominalizate  în contractul de închiriere, și fiecare dintre acestea vor trebui să îndeplinească condițiile enumerate mai sus. În niciun caz Beneficiarul nu are dreptul de a încredința sau subînchiria autovehiculul terțelor persoane. Totodată, Beneficiarului nu âi est recunoscuta posibilitatea de a cesiona beneficiul prezentului Contract, nici orice drept sau obligație născute în temeiul acestuia. Beneficiarul are obligația să aibă asupra sa contractul de închiriere pe tot parcursul deplasării, pentru a-l prezenta organelor de control competente.
6.2.5 Beneficiarul nu are dreptul de a se deplasa în afara Teritoriului fără acordul prealabil scris al Prestatorului. Deplasarea în afara României va avea loc doar în baza împuternicirii necesare pentru trecerea frontierei acordate de către Prestator Beneficiarului. În niciun caz Beneficiarul nu va putea să se deplaseze cu autovehiculul în afara granițelor Uniunii Europene sau a Spațiului Economic European. In cazul încălcării prevederilor prezentului articol, Beneficiarul va suporta personal costurile pentru toate avariile aduse vehiculului, toate prejudiciile cauzate Prestatorului iar în cazul furtului sau distrugerii autovehiculului, Beneficiarul va achita Prestatorului intreaga sa valoare de nou cu toate dotările suplimentare cu ce s-a predat autovehicului. In cazul incălcării acestei clauze se va percepe o taxa de 100 Eur  (TVA inclus). 
6.2.6 Beneficiarul se obligă să depună o garanție în valoarea specificată în contractul de închiriere, în numerar sau prin carte de credit, cel târziu la semnarea contractului de închiriere sau pana la preluarea autovehiculului de la Prestator. Neplata garanției interzice preluarea autovehiculului de către Beneficiar și duce la rezilierea de drept a Contractului de închiriere, fără notificare, somație sau apelul la instanța de judecată, înțelegându-se că valoarea prezentei clauze este aceea a unui pact comisoriu expres de grad IV.
6.2.7 Beneficiarul este obligat să sisteze călătoria și să anunțe reprezentanții prestatorului, în cazul în care constată aspecte sau semne de funcționare defectuoasă a autovehiculului, care pot periclita starea tehnică a autovehiculului și siguranța în circulația rutieră. În situația nerespectării acestei obligații Beneficiarul este obligat sa suporte în întregime contravloarea reparațiilor și a oricăror altor daune produse. Din valoarea totală a daunelor se va scădea contravaloarea garanției, dacă aceasta nu a fost folosită pentru acoperirea altor prejudicii.
6.2.8 Beneficiarul nu are dreptul sa se angajeze in efectuarea de reparații sau alte lucrări la autovehiculul închiriat fără aprobarea scrisă a reprezentanților prestatorului. Reparațiile ce se vor efectua la autovehiculul închiriat pot fi executate doar la service-urile Autoworld SRL  sau de către un service auto agreat de către SC Autoworld SRL, în cazul intervențiilor în afara țării. Sumele plătite pentru reparații ce nu ii sunt imputabile Beneficiarului, se decontează de către Prestator pe baza documentelor ce atestă efectuarea reparațiilor (factură fiscală, chitanță, deviz cu datele S.C. AUTOWORLD. S.R.L.)
6.2.9 Beneficiarul este obligat să nu efectueze nici o intevenție de nici o natură asupra autoturismului fiind obligat a-l restitui in starea in care acesta a fost predat de Prestatator la momentul începererii contractului. În cazul in care Beneficiarul încalcă prezenta clauză, acesta este obligat să suporte toate costurile pentru aducerea autovehiculului în starea inițială.
6.2.10 In cazul implicării intr-un accident sau al lovirii autovehiculului Beneficiarul are obligația de a anunța atât Prestatorul cât și organele de poliție, de a efectua toate demersurile și de a obține actele doveditoare prevăzute de lege pentru reparație.
6.2.11 Autoturismul va fi predat către Prestator exact așa cum a fost preluat, alimentat cu aceeași cantitate și tip de carburant, curat interior și exterior, în caz contrar Beneficiarul va suporta costurile în acest sens.
In situația în care autovehiculul nu este returnat curat interior și exterior, Beneficiarul va achita o taxă suplimentară de 20 Euro. Starea autovehiculului va fi constatată la momentul predării/returnării de către Beneficiar Prestatorului, împreună cu reprezentantul Prestatorului, care va face mențiuni despre starea autovehiculului în cuprinsul procesului-verbal. Dacă autovehiculul este predat după orele de program sau într-o zi nelucrătoare, procesul verbal și constatările vor fi efectuate fără prezența Beneficiarului, acesta din urmă asumându-și mențiunile realizate de către reprezentantul Prestatorului.
În cazul în care autovehiculul este returnat murdar sau predat fără  a fi preluat de către reprezentanții Motion Rent A Car, Prestatorul poate anunța Beneficiarul în termen de 48 de ore orice neconformitate semnalată în urma preluării autovehiculului și poate imputa contravaloarea prejudiciilor. 
6.2.12 Este interzisă utilizarea autovehiculului în scopuri comerciale (cu excepția cazurilor în care părțile convin altfel), activități de tractare, împingere, concursuri, curse, antrenamente, transport de substanțe sau materii periculoase, activități ilegale. Transportul de animale de companie se va putea efectua doar în cuști speciale. Este de asemenea interzis fumatul în interiorul autovehiculului. În  cazul incălcării acestei clauze se va percepe o taxa de 300 Euro (cu TVA inclus).
6.2.13 Restituirea autovehicului se face în locația menționată la art 4.1 în timpul orelor de program. Dacă restituirea nu se poate efectua  în timpul orelor de program, cheia si documentele se vor lăsa de către Beneficiar în Autoworld easy box, aplicându-se condiția de la art 6.2.11.
6.2.14 Beneficiarul are obligația de a achita o sumă egală cu cea datorată de către Prestator asiguratorului în caz de daună totală ori furt al autoturismului, in condițiile detaliate la art 8.2. În contextul producerii unei daune asupra autovehiculului încadrate la categoria ”daună totală”, având în vedere faptul că asiguratorul suportă numai o cotă de 80% din valoarea autovehiculului, diferența de 20% va fi suportată de către Beneficiar. 
6.2.15 Beneficiarul este singurul răspunzator pentru achitarea taxelor de drum (cu excepția Rovignetei), a carburantului, a amenzilor și sancțiunilor pentru nerespectarea regulilor de circulație pe drumurile publice și a legilor naționale în vigoare. Beneficiarul iși asumă expres, prin semnarea prezentului contract obligația de a achita aceste taxe/sume/despăgubiri. Dacă documentele care stabilesc obligația de a achita amenzi sau sancțiuni aplicate în perioada de închiriere sunt comunicate Prestatorului ulterior încheierii perioadei de închiriere, acesta le va comunica în termen de 3 zile Beneficiarului care își asumă obligația de a le achita. Neachitarea contravalorii amenzilor sau a sancțiunilor aplicate dă posibilitatea Prestatorului de a-l acționa în judecată pe Beneficiar pentru recuperarea eventualelor sume achitate cu acest titlu ca urma a neachitării lor de către Beneficiar.
6.2.16 Beneficiarul va utiliza responsabil și în acord cu legislația aplicabila autovehiculul și îl va întretine pe perioada închirierii ca un bun proprietar în mod atent și responsabil.Copii vor fi transportați numai cu scaun adecvat.
6.2.17 În cazurile de pierdere, distrugere, furt documente auto (talon, RCA) se va reține o taxă în valoare de 150 Euro (TVA Inclus).
6.2.18 Beneficiarul are obligația de a se asigura împotriva furtului prin inchiderea autoturismului și prin activarea sistemelor de alarmă daca autoturismul este prevăzut cu această dotare. Beneficiarul se obligă să nu păstreze bunuri de valoare la vedere. Prestatorul nu este responsabil de dispariția sau furtul oricăror bunuri din interiorul autovehiculului și nici de eventualele daune provocate autovehiculului ca urmare a eventualelor furturi comise. Beneficiarul se obligă să acopere orice daune produse autovehiculului ca urmare a furturilor din interiorul acestuia pe perioada închirierii. Beneficiarul se obligă să anunte furtul autoturismului la politie si sa instiinteze Prestatorul in cel mai scurt timp.


7. GARANȚIA
7.1 Pe perioada închirierii clientul va depune o garanție în suma specifică în contract, în numerar sau achitată prin card de credit. Garanția servește pentru acoperirea pagubelor produse autovehiculului din vina Beneficiarului precum și pentru plata sumelor care cad în sarcina Beneficiarului în caz de întârziere la restituire, întârzieri de plată, predare fără rezervorul de carburant plin, lipsuri sau avarii, nerespectarea condițiilor de întreținere ori alte sume datorate sau pagube cauzate de către Beneficiar.
7.2. Prestatorul are dreptul să rețină toate sumele neachitate de către Beneficiar (sume restante datorate pentru folosința autovehiculului, pentru daunele produse acestuia în urma unei coliziuni, accident sau nerespectarea condițiilor de întretinere a autoturismului, restituirea acestuia fără carburant, amenzi sau alte penalități sau taxe) din garanția prevazută și dacă acesta este neîndestulatoare, direct de pe cardul de credit a Beneficiarului precum si în orice alt mod permis de lege, urmând ca Beneficiarului sa i se transmită o chitanță/factură în acest sens.
Dacă reținerea sumelor în acest mod nu este posibilă, Prestatorul va apela la mijloacele legale pe care le are la dispoziție pentru recuperarea debitelor.
7.3 Răspunderea beneficiarului pentru pagube nu se limiteaza la suma achitată cu titlu de garanție putând depăși această valoare. Întiderea prejudiciului cauzat autoturismului de către beneficiar se va calcula de către un reprezentant al Prestatorului pe baza prețului de Catalog a componentelor avariate și costul manoperei. De asemenea, garanția va putea fi utilizată parțial ori total de către Prestator în vederea acoperirii sumelor de plată restante datorate de către Beneficiar pentru folosința autovehicului cât și pentru acoperirea sumelor datorate de Beneficiar pentru nerespectarea prevederilor art. 8.3.
7.4 Beneficiarul este obligat să achite în favoarea Prestatorului suma garanției înainte de data predării autoturismului, Prestatorul având dreptul de a refuza predarea autoturismului în situația în care Beneficiarul nu face dovada plații garanției. În cazul neachitării garanției, Contractul de închiriere se va rezilia fără notificare, somație sau apelul la instanța de judecată, înțelegându-se că valoarea prezentei clauze este aceea a unui pact comisoriu expres de grad IV.
7.5 Garanția se restituie Beneficiarului la momentul semnării Procesului verbal de predare primire a autovehicului în cazul în care a fost achitată numerar. In cazul în care există indicii că autovehiculul a suferit daune iar acestea nu pot fi estimate imediat, nu sunt vizibile sau nu pot fi identificate pe loc, garanția se va restitui doar după efectuarea unei evaluări și verificări a autovehiculului. 
In cazul în care garanția a fost blocată în contul Beneficiarului acesta va fi de deblocată în maxim 10 zile de la momentul constatării stării corespunzatoare a autovehiculului predat, ulterior inspecției efectuate. Perioada se prelungește in mod corespunzator in situația în care sunt necesare verificări suplimentare, cu termenul necesar efectuării acestor verificări.

8. ASIGURAREA AUTO
8.1. Asigurările cuprinse în acest contract sunt: răspunderea civilă (RCA- obligatorie), asigurarea CASCO contra accidentelor și contra furtului. Acestea sunt valabile numai pe teritoriul României, valabilitatea putând fi extinsă și pentru străinătate Ia cererea clientului, pe baza unui acord prealabil și contra cost.
8.2. Beneficiarul declară ca i-a fost adus la cunoștință faptul că  asigurarea CASCO de care beneficiează autovehicul cuprinde o clauză specificată în contractul de asigurare, potrivit căreia în situația unei daune, avarii sau furt, prejudiciul cauzat în situația survenirii riscului asigurat este acoperit cu obligația achitării unei sume determinate (respectiv, prejudiciul este acoperit doar parțial, existand o parte din daună, stabilită in suma fixă, care este suportată de către Prestator) .  În situația avarierii ori a furtului autovehiculului în perioada de derulare a prezentului contract Beneficiarul este obligat să achite suma prevăzută în contractul de asigurare, pentru fiecare risc asigurat survenit si pentru fiecare eveniment asigurat, daună sau furt, distinct). Plata se va efectua pe Ioc la retrunarea autovehiculului, moment în care suma/sumele datorate vor fi facturate către Beneficiar.
8.3. Asigurările nu includ și nu sunt valabile în urmatoarele cazuri:
- avarierea părți inferioare a autoturismului - șasiu, bloc motor, etc. — prin acțiune deliberată sau neglijentă
- avarierea jantelor sau pneurilor necauzată de accident, conducerea autoturismului de către o altă persoană decât cele trecute în contract/anexa
- pierderea cheilor, actelor autovehiculului
- deteriorarea vizibilă a habitaclului
- avarierea sau pierderea opționalelor inchiriate conform art 2.2 și mențiuni fișa preluare predare  (trusă medicală, cric,  suport echipament sportiv, scaun copii…etc)
-alimentarea autovehiculului cu carburantul greșit
-deteriorarea autovehicului ca urmare a fumatului in interiorul acestuia conducerea sub influența alcoolului, a drogurilor etc.
 nu includ asigurarea pentru persoanele și bagajele aflate în autovehicul
- deplasarea cu autoturismul in tari care sunt angajate in confilcte armate
Costul acestor prejudicii nesuportate de către asiguarea CASCO vor fi suportate integral de către Client
8.4. Beneficiarul își asumă în întregime riscul pierderii, furtului, distrugerii sau avarierii bunului utilizat (partial sau total - dauna totala), inclusiv din cauze fortuite sau forta majora, cu excepția situației în care evenimentul este acoperit de asigurarea CASCO a autovehiculului sau de asigurarea RCA, iar asiguratorul acceptă plata primei de asigurare. Cu toate acestea, în cazul avarierii autovehiculului, oricare ar fi motivul și independent de suportarea daunei de către asigurator, Beneficiarul va achita Prestatorului o sumă suplimentară stabilită în funcție de valoarea reparației.
16% din valoarea de nou a autovehiculului pentru o daună ce depășește contravaloarea de 60.000 euro
11% din valoarea de nou a autovehiculului pentru o daună ce depășește contravaloarea de 50.000 euro
9% din valoarea de nou a autovehiculului pentru o daună ce depășește contravaloarea de 30.000 euro
6% din valoarea de nou a autovehiculului pentru o daună ce depășește contravaloarea de 20.000 euro
3% din valoarea de nou a autovehiculului pentru o daună ce depășește contravaloarea de 10.000 euro
1.5 % din valoarea de nou a autovehiculului pentru o daună ce depășește contravaloarea de 5.000 euro


8.5 Valorile intermediare celor anterior menționate vor fi calculate pe baza algoritmului matematic aplicabil cotațiilor stabilite mai sus.
Sumele stipulate mai sus nu vor fi percepute în situația în care Beneficiarul achiziționează autovehiculul închiriat, urmare a reparației, la prețul de achiziție, din care se scade devalorizarea specifică perioadei de exploatare.
8.6 Prezentul articol se aplică și în situația în care autoturismul este condus de către persoanele împuternicite de către Beneficiar ca având permisiunea de a conduce autoturismul pe perioada duratei de închiriere. De asemenea, în cazurile arătate mai sus, Beneficiarul, respectiv, celelalte persoane titulare ale contractului sunt pe deplin răspunzătoare de daunele produse autoturismului si prejudiciile cauzate terților. Cu atât mai mult va fi responsabil Beneficiarul și va achita sumele de mai sus și toate prejudiciile cauzate, în cazul în care autovehiculul este înredințat unor terțe persoane cărora nu le-a fost acordat, prin contract, dreptul de a conduce autovehiculul închiriat.

9. AVARIEREA AUTOVEHICULULUI
9.1 În cazul implicarii intr-un accident sau al lovirii autovehiculului, Beneficiarul are obligația de a anunța de îndată atât Prestatorul cât și organele de politie.
9.2 Beneficiarul are obligația de a efectua toate demersurile si de a obține toate actele doveditoare prevăzute de lege pentru reparație (completarea constatării amiabile, obținerea asigurărării autoturismului implicat in accident, obținerea Procesului Verbal de constatatare a poliției, a Autorizației de reparație etc).
9.3 Este exclusă orice răspundere a Prestatorului pentru evenimentele care au loc pe durata de timp în care autovehiculul se află în posesia Beneficiarului. Beneficiarul va suporta toate costurile aferente prejudiciilor cauzate de Beneficiar din culpa sa, cele cu autor necunoscut precumși orice alte tipuri de daune care nu sunt acoperite prin contractul de asigurare valabil încheiat de către Prestator.

10. PRELUNGIREA MODIFICAREA CONTRACTULUI
10.1 Durata contractului poate fi prelungită prin telefon sau e-mail și numai dacă Prestatorul acceptă expres acestă prelungire. În cazul în care Beneficiarul dorește prelungirea contractului, fie Beneficiarul sau un delegat al acestuia se va prezenta în termen de o zi în vederea modificării contractului și pentru a plăti diferența de preț, fie modificarea contractului va avea loc prin e-mail, insă diferența de pret se va achita de îndată prin transfer bancar, comunicandu-se dovada plații (documentul aferent, ordin de plata) prin e-mail. Prețul în cazul prelungirii se achită în aceleasi condiții ca și prețul agreeat inițial. Durata contractului de închiriere nu se va prelungi decât la momentul achitării diferenței de preț pentru noua perioadă de închiriere. Contractul se va prelungi, după achitarea diferenței de preț anterior menționată, în aceleași condiții și cu aceleași clauze, cu excepția termenului care va fi menționat de către părți într-o anexă.
10.2 În cazul în care clientul întârzie cu restituirea autovehiculului mai mult de 24 de ore fără să fi anunțat Prestatorul și/sau fără a fi achitată diferența de taxa de închiriere, Prestatorul va proceda automat și fără punere în întârziere la anunțarea organelor competente (poliție, companie de asigurare) și nu va restitui garanția.

11. ÎNCETAREA CONTRACTULUI
11.1.     Contractul încetează  prin predarea autovehiculului.
11.2.     Pentru anularea unei rezervări Beneficiarul este obligat să anunțe Prestatorul in scris cu minim 48 de ore înainte de momentul începerii închirierii. In cazul anulării unei rezervari Prestatorul iși rezervă dreptul de a reține o taxă de anulare reprezentând contravaloarea unei zile de închiriere.
11.3.      În cazul in care Beneficiarul omite sa înștiinteze Prestatorul cu privire anularea rezervării, însă cu toate acestea nu se prezintă pentru a prelua autovehiculul, Prestatorul poate, dupa cum consieră neccesar și fără a fi necesară oferirea unor justificari suplimentare, sa perceapă o penalitate care nu poate fi mai mare decât valoarea integrală a tarifului convenit inițial.
	•	Contractul încetează la expirarea termenului stabilit potrivit prevederilor acestuia. Pentru scopul determinării momentului expirării termenului, va fi luată in considerare predarea efectivă a autovehiculului achizitionat. 
11.5 Contractul încetează și în condițiile în care unul dintre părti comunica părtii celeilalte intenția sa de denunțare unilaterală a prezentei conventii. O notificare va fi trimisa in acest sens in scris, la adresa fizică sau de e-mail, cu cel putin 5 zile anterior cererii de încetare. Denunțarea unilaterală nu va fi efectivă decât dupa trecerea intervalului de 5 de zile, menționat anterior. Pe întreaga perioada de preaviz Beneficiarul va datora chiria prevazută în prezentul contract.
11.6 În cazul denunțării unilaterale de către Beneficiar, acesta datorează un preț al dezicerii stabilit la valoarea chiriei aferente unei luni de închiriere, potrivit contractului.
	•	Contractul va înceta efectiv prin acord comun semanat de către ambele părți, consemnat printr-un act adițional.
	•	Rezilierea prezentului Contract duce, de asemenea la încetarea contractului, în conditiile stabilite mai jos:
Părtile au obligația de a îndeplini întocmai și la timp obligațiile asumate prin prezentul Contract.
Pentru neindeplinirea, fără justificare, a oricareia dintre obligatiile stabilite la punctele 2 si 3 de mai sus, Părțile pot solicita rezilierea prezentului Contrcat, inclusiv prin comunicarea unei notificări de rezoluțiune unilaterală, urmand a produce efecte fară trecerea vreunui timp și fară intervenția instanței de judecată.
	•	Încetarea prezentului contract va avea loc si în cazul decesului/punerii sub interdicție ori, după caz, a deschiderii procedurii de insolvență/faliment, in caz de dizolvare sau radiere a Beneficiarului.
	•	Încetarea Cotractului va avea loc și în cazul intervenției forței majore sau a unui caz fortuit, care duc la imposibilitatea executării obligațiilor. Definiția termenilor de “fortă majoră” si “caz fortuit” este cea oferită de prevederile Codului civil.
11.11     Beneficiarul nu poate refuza sub nici un motiv predarea autoturismului către Prestator la sfârșitul perioadei de închiriere, nefiind în drept a invoca vreun drept de retenție ori de altă natură asupra acestuia. În ipoteza în care autoturismul nu este predat către Prestator la expirarea termenului de inchiriere, ori Beneficiarul refuză predarea autoturismului către Prestator, acesta are dreptul de a intra în posesia bunului proprietatea sa prin mijloace aflate la dispozițłe, chiar fără concursul instanțelor de judecată, executorului judecatoresc ori alte autoritățti publice.
12. DISPOZIȚII FINALE
12.1 Contractului îi este aplicabilă legea română. Orice eventual litigiu va fi soluționat de instanțele de judecată competente din Cluj-Napoca

								Client:
								

Data:


=== VALOAREA FACTURABILĂ A DAUNELOR ===
VALOAREA  FACTURABILA  A DAUNELOR
Cost Dauna Neasigurata*

Pierdere cheie mașina / Car key loss | 250 Eur-400 Eur
Pierdere documente mașina, Pachet Legislativ/ Loss of car document Pierdere numere de inmatriculare/Loss of registration numbers and Law Package | 150 Eur
Elemente vitrate
Parbriz, luneta, oglinda retrovizoare interioara, geam lateral / Windshield, rear window, side window, Interior rear-viewmirror | 160 Eur-600 Eur
Roti
Janta | 100 Eur-800 Eur

Anvelopa (preț per bucata) /Tire (price per piece) (13"-15") | 200 Eur-300 Eur
Capac roata/Wheel cover | 50 Eur
Interior

Scaun fata, bancheta spate, cotiera / Front seat, rear seat, armrest | 240 Eur-360 Eur
Mocheta podea, material plafon, covorase / Floor carpet, ceiling material, car mats | 150 Eur-750 Eur
Radio-CD, sistem de navigație / Radio-CD, navigation system | 200 Eur-740Eur
Cric si cheie de roti, compresor / Jack and wheel wrench, compressor | 160 Eur-200 Eur

*Preturile variaza in functie de clasa si model, preturile afisate includ TVA


AUTOWORLD SRL, persoana juridica romana cu sediul in localitatea Cluj Napoca, Calea Floresti, Nr. 145, inregistrata la Registrul Comertului cu nr.  J12/3388/1991, cod fiscal RO 225615, înregistrata la ANSPDCP ca operator de date cu caracter personal cu numarul 38681, conform Regulamentului (UE) 2016/679 și Consiliului din 27 aprilie 2016, privind protectia datelor cu caracter personal si libera circulatie a acestor date, avem obligatia de a administra in conditii de siguranta si numai pentru scopurile specificate, datele personale ale clientului care ne sunt furnizate de catre client sau reprezentantii acestuia legali si/ sau alti angajati/colaboratori ai clientului.
AUTOWORLD SRL colecteaza, prelucreaza si stocheaza, prin mijloace manuale si/sau automatizate urmatoarele date cu caracter personal ale Clientului:
	•	Nume, prenume, semnatura
	•	Adresa, telefon si e-mail
	•	CNP, seria si numarul actului de identitate/pasaportului 
	•	Date din permisul de conducere
	•	Date de localizare GPS
De asemenea, AUTOWORLD SRL poate solicita clientului / utilizatorilor copii de pe documente (permis de conducere  buletin/pasaport) in vederea folosirii lor in relatiile cu autoritatile publice locale/centrale, societati asigurare/reasigurare,  autoritati vamale. Copiile de pe documentele solicitate au scop justificativ cu privire la inchirierea si folosirea autoturismelor, in cazuri de accidente rutiere, furturi auto si orice speta penala in legatura cu autoturismele ce sunt mentionate in contractul de inchiriere. 
Toate datele cu caracter personal sunt colectate, prelucrate si stocate de catre AUTOWORLD SRL cu buna-credinta in vederea executarii in conditii optime a contractului de inchiriere, monitorizarii bunurilor, prelucrarii cererilor clientului, furnizarii informatiilor privind serviciile oferite, a facturarii acestor servicii, inclusiv efectuarii platilor in numerar, prin tranzactii bancare sau a celor cu cardul, solutionarea cererilor, intrebarilor sau reclamatiilor clientului. Aceste date cu  caracter personal vor fi pastrate pe toata durata contractuala, pana la expirarea obligatiilor contractuale si a termenelor de arhivare.
Conform Regulamentului CUE) 2016/679  si al Consiliului European din 27 aprilie 2016 clientul beneficiaza de dreptul de acces, de interventie asupra datelor, dreptul la portabilitate si dreptul de a nu fi supus unei decizii individuale. Totodata, clientul are dreptul de a se opune prelucrarii datelor cu caracter personal care il privesc si sa solicite stergerea acestora (in masura in care acest lucru nu contravine legii).
Pentru exercitarea acestor drepturi, clientul se poate adresa catre AUTOWORLD SRL, printr-o cerere scrisa datata si semnata la adresa din Cluj Napoca, Calea Floresti, nr 145, Jud.Cluj prin e-mail la protectiadatelor@autoworld.ro.  Daca sunteti de parere ca AUTOWORLD SRL a incalcat vreun drept privind acest subiect, incepand cu 25 mai 2018 clientul se poate adresa Autoritatii Nationale de Supraveghere a Prelucrarii Datelor cu Caracter Personal. Daca unele dintre date sunt neconforme cu realitatea, va rugam sa ne informati cat mai curand posibil pentru a le rectifica. AUTOWORLD SRL se angajeaza sa aplice toate masurile tehnice si organizatorice pentru asigurarea securitatii datelor personale ale clientului, protejarii impotriva distrugerii, modificarii, dezvaluirii ori accesului neautorizat asupra lor.


AUTOWORLD SRL, Romanian legal entity having its headquarters in the city of Cluj-Napoca, 145 Calea Floresti street, Cluj County, registered at the Trade Register under nr J12/3388/1991, fiscal code RO 225615, registered at the ANSPDCP as personal data operator under number 38681, according to the Regulation (EU) 2016/679 of the European Parliament and of the Council of April 27, 2016, on the protection of natural persons with regard to the processing of personal data and on the free movement of such data, has the obligation of managing safely and only for the specified purposes, the client's personal data which are supplied to use by the client or by his legal representatives and/or other employees/ collaborators of our client.
AUTOWORLD SRL collects, processes and stores, through manual and/or automated means, the following personal data belonging to the client:
	•	Name, surname, signature
	•	CNP, series and number of the identity card/passport
	•	Address, telephone number and e-mail address
	•	Data from his driving license
	•	GPS localization data
Furthermore,  AUTOWORLD SRL can also request his client/users copies of their documents (driving license + id card/passport), to be used in relation with locale/central public authorities, insurance/reinsurance companies, customs authorities. The copies of the requested documents have a justifiable purpose in relation to the lease and use of the vehicles, cases of road accidents, car theft and any criminal proceedings related to the vehicles mentioned in the lease contract.
All personal data are collected, processed and stored by  AUTOWORLD SRL in good faith for the purpose of executing, in optimal conditions, the lease contract, monitoring the goods, processing client requests, supplying information with regard to services offered, invoicing those services, including the performance of cash payments, bank transfers or card payments, answering requests, questions, complains. This personal data shall be maintained throughout the contractual period, until the expiration of all contractual obligations and archiving terms.

In accordance with Regulation (EU) 2016/679 and the Council of April 27, 2016, the client benefits of the right of access, of data intervention, the right to portability and the right of not being subjected to an individual decision. Furthermore, the client has the right of opposing the processing of his personal data and to request their deletion (as far as this is not contrary to the law).
For the exercise of those rights, the client can address  AUTOWORLD SRL through a written request, dated and signed at the address: 145 Calea Floresti street, Cluj-Napoca, Cluj County, or through e-mail at protectiadatelor@autoworld.ro. If he believes that  AUTOWORLD SRL has breached any right related to this matter, as of May 25, 2018, the client can address to the National Supervisory Authority for Personal Data Processing. If some of the data does not comply to reality, please inform us as soon as possible, so we can rectify them.
AUTOWORLD SRL undertakes to apply all the technical and organizational measures in order to ensure the security of the client’s personal data, to protect them against destruction, and against their unauthorized modification, disclosure or access.


Sunt de acord sa primesc pe e-mail un chestionar scurt despre experienta colaboarii cu AUTOWORLD SRL                                                       ⃝  DA        ⃝  NU
I agree to receve a short questionnaire on my e-mail regarding my experience in collaborating with AUTOWORLD SRL 		  YES              NO

Sunt de acord ca AUTOWORLD SRL sa-mi poata folosi datele de contact (nume,prenume, adresa de e-mail/telefon) pentru a primi 
informatii, pe e-mail sau telefon , oferte, produse, materiale informative, servicii noi/actuale si/sau evenimente.    	                    ⃝  DA        ⃝  NU
I agree that AUTOWORLD SRL can use my contact data (name, surname, e-mail address/telephone number), so that it can informe me             YES              NO
by e-mail or telephone, about Autoworld, it offers products, informative materials, new/current services and /or events offered.


Beneficiarul (clientul) declara ca i-a fost adus la cunoștința faptul ca asigurarea CASCO de care beneficiază autovehiculul închiriat cuprinde o clauza de fransiza astfel cum este menționat in condițiile specifice. La returnarea autotvehiculului clientul va fi obligat să achite parțial sau total, pe baza facturii emise de către Prestator, suma/sumele datorate de către acesta din urmă asiguratorului ca efect al survenirii riscului asigurat, conform contractului de asigurare, pentru fiecare avariere în parte, in următoarele situații:

	•	Mașina prezintă zgârieturi noi, zone înfundate, faruri sau stopuri crapate sau sparte
	•	Avarii ale geamurilor si oglinzilor (lovituri, crăpături)
	•	Avarii ale cauciucurilor inclusiv cele generate de rularea cu roata dezumflata. 0 Aistrugeri ale interiorului mașinii, tapițeriei scaunelor si aparaturii de bord 0 Alimentarea greșita cu combustibil.
	•	Pierderea documentelor, a plăcutelor de înmatriculare si a inventarului mașinii conform fisei de predare
	•	Murdărirea excesiva
	•	Orice alte daune cauzate autovehiculului intenționat sau din neglijenta 


The beneficiary (the client) states that he has been informed that the CASCO insurance for which the rented vehicle benefits includes a freight clause as mentioned in the specific conditions. Upon returning the customer's car, he will be partially or totally retained (the Client will have the obligation to pay a sum equal to the fee mentioned in the insurance for each damage caused to the vehicle), on the grounds of the invoice issued by the Provider, in the following situations:


	•	The car has new scratches larger than 2.5 cm, clogged areas, cracked or broken headlights or headlights
	•	Damage to windows and mirrors (blows, cracks)
	•	Tire damage including those caused by deflated wheel running.
	•	Destruction of the interior of the car, upholstery of seats and on-board equipment
	•	Wrong fuel supply.
	•	Loss of documents, registration plates and car inventory according to the instruction sheet
	•	Excessive filth
	•	Any other damage caused to the intended vehicle or from negligence


Client:
______________________              


Data:
____________________
"""
