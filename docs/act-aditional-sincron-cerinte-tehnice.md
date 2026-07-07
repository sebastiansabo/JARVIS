# Act Adițional Nr. 7/04.03.2026
## La Contractul Nr. 1732/28.05.2019

---

### Părțile contractante

**SC HR Sincron SRL**, o societate legal constituită și funcționând în baza legilor din România, cu sediul social în București, B-dul Tudor Vladimirescu, Nr. 45, etaj 1, Camera 1, sector 5, înregistrată la Registrul Comerțului sub nr. J40/5289/2007, cod unic de înregistrare 21356389, IBAN account RON RO48BTRL04301202E93890XX deschis la Banca Transilvania sucursala Unirii, reprezentată de **Mihai Stanca**, în calitate de Administrator, denumită în continuare **Furnizor**

și

**SC Autoworld SRL**, o societate legal constituită și funcționând în baza legilor din România, cu sediul în Cluj-Napoca, înmatriculată la Registrul Comerțului sub J12/3388/1991, CUI RO 225615, cod IBAN RO28BABACX0000000430020310 deschisă la Unicredit Bank Cluj, reprezentată de **Mezei Ioan**, în calitate de Director general, denumită în continuare **Beneficiar**

s-a încheiat prezentul act adițional, ale cărui prevederi și clauze, convenite în virtutea principiului libertății Contractuale, au fost stabilite prin acordul comun al părților și cu respectarea legii.

Având în vedere că Beneficiarul a încheiat cu Furnizorul Contractul de mai sus (denumit în cele ce urmează Contractul), se încheie prezentul act adițional, după cum urmează, contractul de bază rămânând nemodificat.

---

## Art.1 — Obiectul Actului Adițional

Furnizorul va realiza o integrare de tip API cu sistemul de card acces al Beneficiarului pentru toate cele 8 entități legale de care acesta dispune. Costul activității este **1224 EUR fără TVA** și se va achita în două tranșe după cum urmează:

- **Tranșa 1** — 50% din valoare, adică 612 EUR fără TVA, se vor achita la semnarea prezentului act adițional.
- **Tranșa 2** — 50% din valoare, adică 612 EUR fără TVA, se vor achita la finalizarea activității.

---

## Art.2 — Cerințe Tehnice Obligatorii pentru Integrarea API

Furnizorul se obligă să pună la dispoziția Beneficiarului un **API REST** (interfață de programare a aplicațiilor de tip transfer de stare reprezentațional) securizat, care să permită extragerea automatizată a datelor din platforma Sincron HR Software, conform specificațiilor tehnice detaliate mai jos.

### 2.1 Specificații Generale ale Interfeței API

Furnizorul va asigura:

a) **Puncte de acces API REST** accesibile prin protocol HTTPS (TLS 1.2 sau superior), cu autentificare prin cheie API, protocol OAuth 2.0 sau token de sesiune;

b) **Format de date JSON** pentru toate răspunsurile interfeței API;

c) **Paginare** — suport pentru navigarea prin seturi mari de date, prin mecanism de tip offset/limită sau cursor;

d) **Filtrare temporală** — posibilitatea de a filtra înregistrările după intervale de timp (dată început, dată sfârșit) pentru sincronizări incrementale;

e) **Limitare de rată documentată** — specificarea clară a numărului maxim de cereri permise pe minut și pe oră;

f) **Documentație API completă** — specificație de tip OpenAPI/Swagger sau document echivalent, cuprinzând toate punctele de acces, parametrii, formatele de răspuns și codurile de eroare;

g) **Mediu de test** — acces la un mediu de dezvoltare/testare separat de producție, pentru validarea integrării înainte de punerea în funcțiune.

---

### 2.2 Module și Date Obligatorii

Furnizorul va expune prin API următoarele categorii de date, pentru **toate cele 8 instanțe/entități legale** ale Beneficiarului:

---

#### A. ANGAJAȚI

Punct de acces pentru listarea și obținerea detaliilor angajaților, conținând minimum următoarele câmpuri:

| Denumire câmp | Descriere | Exemplu |
|---------------|-----------|---------|
| Identificator angajat (marcă) | Cod unic numeric al angajatului în sistem | `665` |
| Nume complet | Numele și prenumele angajatului | `SABO SEBASTIAN NICOLAE` |
| Email corporativ | Adresa de email de serviciu | `sebastian.sabo@autoworld.ro` |
| Număr telefon | Număr de telefon de contact | `0740...` |
| Funcția / Poziția COR | Funcția conform Clasificării Ocupațiilor din România | `Manager Dezvoltare & Inovare` |
| Cod COR | Codul numeric COR asociat funcției | `122107` |
| Departament | Departamentul în care activează angajatul | `Dezvoltare & Inovare` |
| Entitate juridică | Compania/firma din cadrul grupului | `AUTOWORLD S.R.L.` |
| Identificator manager direct | Marca managerului direct | `98` |
| Nume manager direct | Numele complet al managerului direct | `LASZLO LEHEL MEZEI` |
| Data angajării în organizație | Data la care a început raportul de muncă | `21-11-2016` |
| Status angajat | Starea curentă: activ / inactiv / suspendat | `activ` |
| Status prezență zilnic | Starea de prezență în ziua curentă | `Sunt la birou` / `Concediu medical` |
| Data nașterii | Ziua și luna nașterii | `04-03` |

---

#### B. CONTRACTE DE MUNCĂ

Punct de acces pentru detaliile contractelor individuale de muncă, conținând minimum:

| Denumire câmp | Descriere | Exemplu |
|---------------|-----------|---------|
| Identificator contract | Cod unic al contractului în sistem | - |
| Număr contract | Numărul contractului individual de muncă | `642` |
| Marcă angajat | Identificatorul unic al angajatului | `665` |
| Entitate juridică | Firma angajatoare | `AUTOWORLD S.R.L.` |
| Data început contract | Data de la care este valabil contractul | `21-11-2016` |
| Data sfârșit contract | Data expirării (nul pentru perioadă nedeterminată) | `nul` |
| Tip colaborare | Tipul contractului: permanent / determinat | `permanent` |
| Norma de lucru | Numărul de ore lucrate pe zi conform contractului | `8 ore/zi` |
| Salariu brut | Salariul brut lunar | `17603` |
| Monedă | Moneda în care este exprimat salariul | `RON` |
| Funcție COR | Denumirea funcției conform COR | `MANAGER MARKETING (TARIFE, CONTRACTE, ACHIZIȚII)` |
| Cod COR | Codul numeric al funcției COR | `122107` |
| Status contract | Starea contractului: Generat / Activ / Suspendat / Încetat | `Generat` |
| Perioadă de probă | Durata perioadei de probă în zile lucrătoare | `90 zile lucrătoare` |
| Preaviz concediere | Durata preavizului de concediere în zile lucrătoare | `20 zile lucrătoare` |
| Preaviz demisie | Durata preavizului de demisie în zile lucrătoare | - |
| Data expirare medicina muncii | Data la care expiră fișa de aptitudine | - |
| Data plată lichidare salariu | Ziua lunii în care se efectuează plata | `30 în luna următoare` |
| Detalii plată salariu | Informații suplimentare despre modalitatea de plată | `30 ȘI 15 ALE LUNII URMĂTOARE` |

---

#### C. PONTAJ (Foaia de prezență)

Punct de acces pentru extragerea pontajului lunar per angajat, pentru fiecare entitate legală. Datele vor fi structurate astfel:

**C.1 — Intrări zilnice:**

| Denumire câmp | Descriere | Exemplu |
|---------------|-----------|---------|
| Marcă angajat | Identificatorul unic al angajatului | `665` |
| An | Anul calendaristic | `2026` |
| Lună | Luna calendaristică | `3` |
| Entitate juridică | Firma | `AUTOWORLD S.R.L.` |
| Intrări zilnice | Lista cu înregistrarea fiecărei zile din lună | vezi mai jos |
| → Data | Data calendaristică a zilei | `02-03-2026` |
| → Cod pontaj | Codul care descrie tipul de prezență/absență | `8` / `CO` / `CES` / `CM` |
| → Ore | Numărul de ore pontate în ziua respectivă | `8` |
| → Tip zi | Clasificarea zilei: lucrătoare / weekend / sărbătoare legală | `lucrătoare` |

**C.2 — Sumar lunar obligatoriu per angajat:**

| Denumire câmp | Descriere |
|---------------|-----------|
| Total ore lucrătoare | Norma de ore a lunii respective |
| Total ore lucrate efectiv | Orele efectiv lucrate de angajat |
| Total ore nelucrate | Orele în care angajatul nu a prestat muncă |
| Total zile lucrătoare | Numărul de zile lucrătoare din lună |
| Total zile lucrate | Numărul de zile efectiv lucrate |
| Total zile nelucrate | Numărul de zile în care nu s-a prestat muncă |
| Ore suplimentare | Ore lucrate peste norma programului |
| Ore weekend | Ore lucrate în zilele de sâmbătă și duminică |
| Ore weekend zi | Ore weekend în intervalul de zi |
| Ore weekend noapte | Ore weekend în intervalul de noapte |
| Ore suplimentare weekend | Ore suplimentare lucrate în weekend |
| Ore sărbători legale | Ore lucrate în zilele de sărbătoare legală |
| Ore sărbători legale zi | Ore de sărbătoare legală — interval zi |
| Ore sărbători legale noapte | Ore de sărbătoare legală — interval noapte |
| Ore regie | Ore de regie |
| Total zile delegație | Numărul total de zile de delegație |
| Total zile lucrătoare delegație | Zile lucrătoare petrecute în delegație |
| Total ore delegație zi | Ore de delegație în intervalul de zi |
| Total zile nemuncite lucrătoare | Zile lucrătoare nemuncite |
| Total ore nemuncite lucrătoare | Ore corespunzătoare zilelor lucrătoare nemuncite |
| Total zile lucrătoare legale (luna întreagă) | Zile lucrătoare conform calendarului legal |
| Total ore lucrătoare legale | Ore lucrătoare conform normei legale |
| Total zile timp redus muncă | Zile cu program redus de muncă |
| Total zile suspendate muncă | Zile cu contract suspendat |
| Total ore suspendate muncă | Ore aferente zilelor cu contract suspendat |
| Total ore noapte ture vineri-sâmbătă | Ore de noapte în turele vineri spre sâmbătă |
| Total ore noapte ture duminică-luni | Ore de noapte în turele duminică spre luni |
| Total ore recuperare overtime | Ore de recuperare a timpului suplimentar |
| Total ore suplimentare | Totalul general al orelor suplimentare |

**C.3 — Coduri absențe și abateri de la program — fiecare tip trebuie returnat separat, cu numărul de zile aferent:**

| Cod | Descriere completă |
|-----|--------------------|
| CO | Concediu de odihnă |
| CM | Concediu medical |
| CMS | Concediu medical — suspendare contract |
| CES | Concediu pentru evenimente speciale (căsătorie, deces, naștere copil etc.) |
| CIC | Concediu de îngrijire a copilului |
| CFP | Concediu fără plată |
| D | Delegație (generic) |
| DFD | Delegație fără diurnă |
| DCD | Delegație cu diurnă |
| DEP | Deplasare |
| ZLP | Zi liberă plătită |
| ZLPS | Zi liberă plătită — compensare program sâmbătă |
| ZLCCM | Zi liberă conform Contractului Colectiv de Muncă |
| ZLIC | Zi liberă pentru îngrijirea sănătății copilului |
| ZN | Zile nemuncite (absență nemotivată sau alte situații) |
| ZLP75 | Zile libere pentru părinți — plătite 75% |
| R | Recuperare (compensarea orelor suplimentare cu timp liber) |
| RSL | Recuperare aferentă sărbătorilor legale |
| ST | Șomaj tehnic |
| STU | Șomaj tehnic — regim de urgență |
| AMZ | Adeverință medicală — zi neplătită |

---

#### D. PROGRAM DE LUCRU

Punct de acces pentru programul de lucru lunar per angajat, structurat zilnic:

| Denumire câmp | Descriere | Exemplu |
|---------------|-----------|---------|
| Marcă angajat | Identificatorul unic al angajatului | `665` |
| An | Anul calendaristic | `2026` |
| Lună | Luna calendaristică | `3` |
| Intrări zilnice program | Lista cu programul fiecărei zile | vezi mai jos |
| → Data | Data calendaristică | `02-03-2026` |
| → Ora intrare (I) | Ora la care începe programul de lucru | `08:00` |
| → Ora ieșire (O) | Ora la care se termină programul de lucru | `17:00` |
| → Pauza de masă (minute) | Durata pauzei de masă în minute | `60` |
| → Zi lucrătoare | Indicator dacă ziua respectivă este lucrătoare | `da` / `nu` |
| → Tip program | Tipul programului aplicat | `editat manual` / `standard` / `tură` |

---

#### E. CONCEDII ȘI ABSENȚE

**E.1 — Sold concedii per angajat și an calendaristic:**

| Denumire câmp | Descriere | Exemplu |
|---------------|-----------|---------|
| Marcă angajat | Identificatorul unic al angajatului | `665` |
| An | Anul calendaristic | `2026` |
| Număr contract | Numărul contractului de muncă | `642` |
| Entitate juridică | Firma | `AUTOWORLD S.R.L.` |
| Total zile disponibile | Numărul total de zile de concediu de odihnă disponibile | `63` |
| Zile CO anul curent — total | Dreptul de CO pentru anul în curs | `25` |
| Zile CO anul curent — folosite | Zile de CO deja utilizate din anul curent | `0` |
| Zile CO din anul trecut — total | Dreptul de CO rămas din anul anterior | `44` |
| Zile CO din anul trecut — rămase | Zile de CO neutilizate din anul anterior | `38` |
| Zile CO conform contract | Numărul de zile de CO prevăzut în contractul individual | `21` |
| Zile CO vechime | Zile suplimentare de CO acordate pentru vechime | `4` |
| Ore suplimentare disponibile | Ore suplimentare necompensate, disponibile ca timp liber | `0` |

**E.2 — Cereri de concediu:**

| Denumire câmp | Descriere | Exemplu |
|---------------|-----------|---------|
| Identificator cerere | Cod unic al cererii în sistem | - |
| Marcă angajat | Identificatorul angajatului care solicită concediul | `665` |
| Data început | Prima zi de concediu | `12-01-2026` |
| Data sfârșit | Ultima zi de concediu | `14-01-2026` |
| Tip concediu | Tipul de concediu solicitat | `Concediu de odihnă` |
| Număr zile | Numărul de zile de concediu solicitate | `3` |
| Status cerere | Starea cererii de concediu | `Aprobat` / `În așteptare` / `Respins` |
| Anul din care se decontează | Anul din care se scad zilele de concediu | `2024` |
| Număr contract | Contractul de muncă asociat cererii | `642` |
| Entitate juridică | Firma | `AUTOWORLD S.R.L.` |
| Aprobat de | Numele/identificatorul persoanei care a aprobat | - |
| Data creării cererii | Momentul la care a fost depusă cererea | - |

---

#### F. STRUCTURĂ ORGANIZAȚIONALĂ

Punct de acces pentru organigrama și departamentele fiecărei entități juridice:

| Denumire câmp | Descriere | Exemplu |
|---------------|-----------|---------|
| Identificator entitate | Cod unic al entității juridice | - |
| Denumire entitate juridică | Numele firmei | `AUTOWORLD S.R.L.` |
| Lista departamente | Toate departamentele din cadrul entității | - |
| → Identificator departament | Cod unic al departamentului | - |
| → Denumire departament | Numele departamentului | `Dezvoltare & Inovare` |
| → Departament părinte | Departamentul ierarhic superior (dacă există) | - |
| → Manager departament | Marca managerului departamentului | - |
| Lista pozițiilor/funcțiilor | Toate funcțiile existente în organigramă | - |

---

### 2.3 Cerințe de Acces și Acoperire

Furnizorul garantează că interfața API va asigura:

a) **Acces la toate cele 8 instanțe** (entități legale) ale Beneficiarului, configurabil per instanță cu credențiale dedicate;

b) **Acces de tip citire** pentru toate modulele specificate la Art. 2.2, fără posibilitatea de modificare a datelor din sistem;

c) **Acces la datele tuturor angajaților** din fiecare instanță, nu doar ale utilizatorului autentificat sau ale subordonaților direcți — API-ul trebuie să permită extragerea completă a datelor la nivel de administrator;

d) **Acoperire temporală istorică** — posibilitatea de a extrage pontaje, programe de lucru și concedii pentru orice perioadă din trecut disponibilă în sistem (minimum 24 de luni anterioare datei cererii);

e) **Disponibilitate de 99,5%** a punctelor de acces API în intervalul orar 06:00–23:00 (ora României), 7 zile pe săptămână;

f) **Timp de răspuns** sub 5 secunde pentru cereri individuale (un singur angajat) și sub 30 de secunde pentru cereri de masă (toți angajații unei entități);

g) **Sincronizare incrementală** — posibilitatea de a obține doar înregistrările modificate sau create după un anumit moment de timp, pentru a evita re-descărcarea integrală a datelor la fiecare sincronizare;

h) **Notificări automate (opțional, dar de preferat)** — mecanisme de notificare în timp real pentru evenimente critice: aprobare cerere de concediu, modificare pontaj, angajare nouă, încetare contract de muncă.

---

### 2.4 Livrabile

Furnizorul va livra Beneficiarului:

1. **Documentație API completă** — cuprinzând toate punctele de acces, parametrii acceptați, formatele de răspuns, codurile de eroare și exemple concrete de cereri și răspunsuri pentru fiecare modul;

2. **Credențiale de acces** — chei API sau conturi de serviciu dedicate pentru fiecare din cele 8 instanțe ale Beneficiarului;

3. **Acces la mediu de test** — un mediu de dezvoltare/testare separat de producție, pentru validarea integrării fără a afecta datele reale;

4. **Suport tehnic** — un contact tehnic dedicat pe toată durata implementării (estimat 30 de zile calendaristice de la data primirii accesului API), cu timp de răspuns de maximum 24 de ore în zilele lucrătoare;

5. **Acord de nivel de serviciu pentru API** — document cu disponibilitatea garantată, procedura de raportare a incidentelor și timpii de rezoluție.

---

### 2.5 Criterii de Acceptanță

Integrarea se consideră finalizată cu succes, iar Tranșa 2 devine scadentă, atunci când Beneficiarul confirmă în scris că poate realiza cu succes următoarele operațiuni prin intermediul API-ului:

1. Listarea tuturor angajaților activi din toate cele 8 entități juridice, cu toate datele specificate la Art. 2.2.A;
2. Obținerea pontajului lunar complet, incluzând toate codurile de absențe și abaterile de la program specificate la Art. 2.2.C;
3. Obținerea programului de lucru zilnic per angajat, conform Art. 2.2.D;
4. Obținerea soldului de concedii și a istoricului cererilor de concediu, conform Art. 2.2.E;
5. Obținerea structurii organizaționale cu departamente și ierarhie, conform Art. 2.2.F;
6. Efectuarea de sincronizări incrementale pe bază de moment temporal, fără a fi necesară re-descărcarea integrală a datelor;
7. API-ul răspunde în parametrii de performanță specificați la Art. 2.3 lit. f).

---

## Art.3 — Termen de Livrare

Furnizorul va pune la dispoziția Beneficiarului accesul API și documentația aferentă în termen de **30 de zile calendaristice** de la semnarea prezentului act adițional.

---

## Art.4 — Dispoziții Finale

Serviciile și sumele de mai sus modifică cele specificate în Contract. Toate celelalte prevederi ale Contractului și ale documentelor anexate Contractului nemodificate sau la care nu se face referire prin prezentul Act Adițional, rămân neschimbate.

ACUM, ÎN CONSECINȚĂ, Beneficiarul și Furnizorul au semnat prezentul Act Adițional, redactat în două exemplare, câte unul pentru fiecare parte, în ziua și anul consemnate mai sus, în primul paragraf.

---

**SC HR Sincron SRL** — Furnizor

Reprezentant: Mihai Stanca — Administrator

Semnătura: ____________________

Data: ____________________

---

**SC Autoworld SRL** — Beneficiar

Reprezentant: Mezei Ioan — Director General

Semnătura: ____________________

Data: ____________________
