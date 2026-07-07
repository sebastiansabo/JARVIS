# EuroFib Export Fixes — Design Spec

**Date:** 2026-06-26
**Module:** Facturare (Comenzi Externe)
**Page:** https://jarvis.autoworld.ro/app/accounting/facturare
**Trigger:** Feedback contabilă — 8 buguri + configurări lipsă în exportul BMD/EuroFib

---

## Context

Exportul EuroFib generează fișiere XLSX pentru import în programul de contabilitate BMD. Contabila a raportat probleme la toate cele 4 tipuri de facturi: avans (INVOICE), storno avans 10%, storno avans integral, și final (FINAL).

### Fișiere cheie
- **Export route:** `jarvis/accounting/facturare/routes_orders.py` (L1265-1385)
- **XLSX renderer:** `jarvis/accounting/facturare/generators/eurofib_xlsx.py`
- **Config schema:** `jarvis/accounting/facturare/config.py`
- **Models:** `jarvis/accounting/facturare/models.py`
- **Settings UI:** `jarvis/frontend/src/pages/Accounting/Facturare/index.tsx`
- **Contract UI:** `jarvis/frontend/src/pages/Accounting/Facturare/ComenziTab.tsx`

### Date existente (deja în DB, neutilizate de export)
- `companies.eurofib_klient_id` — Firmennr per supplier (138-141)
- `crm_clients.eurofib_konto_debit` — JSONB, cont debit per firmă AW
- `facturare_konto_config` — konto_debit, konto_credit, centru_gestiune per supplier × invoice_type

---

## 1. Schema DB

### 1a. Tabel nou: `facturare_venituri_rules`

Mapare per supplier: prefix nr comandă → cont venituri + kostenstelle (folosit doar la facturi FINAL).

| Coloană | Tip | Descriere | Exemplu |
|---|---|---|---|
| id | serial PK | | |
| supplier_id | int FK → companies | Furnizorul | 10 |
| comanda_prefix | varchar(5) NOT NULL | Prefix nr comandă ("5", "3", "*") | "5" |
| konto_venituri | varchar(20) NOT NULL | Cont venituri | "707127" |
| kostenstelle | varchar(20) NOT NULL | Centru de cost | "0215" |
| updated_at | timestamp | | |
| updated_by | int FK → users | | |

**Constraint:** UNIQUE (supplier_id, comanda_prefix)

**Date inițiale (migration seed):**

| Supplier | Prefix | Cont | Kostenstelle | Logică |
|---|---|---|---|---|
| AW International (10) | 5 | 707127 | 0215 | PKW — nr comandă 5XXXXX |
| AW International (10) | 3 | 707128 | 0216 | LNF — nr comandă 3XXXXX |
| AW Premium (11) | * | 707132 | 0314 | Audi — orice prefix |

**Logică de matching:** se caută prima regulă unde `nr_comanda` începe cu `comanda_prefix`. Wildcard `*` se potrivește cu orice (fallback/default).

### 1b. Coloană nouă pe `facturare_konto_config`

```sql
ALTER TABLE facturare_konto_config ADD COLUMN text_template varchar(100);
```

Valori default (migration seed):
- INVOICE: `"avans {model} {comanda}"`
- STORNO: `"storno avans {model} {comanda}"`
- FINAL: `"{model} {comanda}"`

---

## 2. Settings Tab UI

### 2a. Tabel Konto Config — coloană nouă "Text"

Se adaugă o coloană `Text Template` la fiecare celulă din matricea existentă (supplier × invoice_type). Input text, placeholder cu valoarea default.

### 2b. Secțiune nouă: "Reguli Venituri Facturi Finale"

Card separat sub tabelul konto. Tabel editabil cu coloane:
- Supplier (dropdown)
- Prefix Comandă (input text)
- Cont Venituri (input text)
- Kostenstelle (input text)

Buton "Add Rule" + buton "Save" global. Se salvează via `PUT /facturare/api/venituri-rules`.

---

## 3. Contract Modal + Contract View

### 3a. Contract Modal — validare client

După selectarea Customer + Supplier:
1. Se citește `crm_clients.eurofib_konto_debit` pentru clientul selectat
2. Se determină `eurofib_klient_id` din `companies` pentru supplier-ul selectat
3. Se verifică dacă clientul are konto debit completat pentru acea firmă

- **Dacă DA:** badge verde cu contul (ex: "Konto AW Intl: 41214286 ✓")
- **Dacă NU:** warning + câmp input inline pentru completare. La salvare se actualizează `crm_clients.eurofib_konto_debit` JSONB

### 3b. Contract View — card "Date Contabile" (vizibil permanent)

Pe pagina fiecărui contract, card read-only cu:

| Câmp | Sursă |
|---|---|
| Firmennr | `companies.eurofib_klient_id` |
| Client | `crm_clients.display_name` |
| Konto Debit Client | `crm_clients.eurofib_konto_debit[klient_id]` |
| Konto Credit (Avans) | `facturare_konto_config` INVOICE |
| Konto Credit (Storno) | `facturare_konto_config` STORNO |
| Konto Credit (Final) | din `facturare_venituri_rules` (depinde de prefix comandă) |
| Centru Gestiune | `facturare_konto_config.centru_gestiune` |
| Kostenstelle (Final) | din `facturare_venituri_rules` |

Dacă lipsesc date obligatorii → badge roșu cu warning.

---

## 4. Fix-uri Export EuroFib

### Bug 1: Firmennr (klient) = 0
- **Cauză:** `routes_orders.py:1369` hardcodează `klient=0`
- **Fix:** citește `companies.eurofib_klient_id` via `contract.supplier_id`
- **Eroare dacă lipsește:** return 400 "Firmennr not configured for supplier"

### Bug 2: Data facturii = data exportului
- **Cauză:** `routes_orders.py:1314` — `issued_date = inv_row.get("issued_date") or date.today()`
- **Fix:** folosește strict `issued_date`. Dacă e null → return 400 "Invoice has no issued date"
- **Afectează:** Buchdatum (col E) și Belegdatum (col G)

### Bug 3: Data curs valutar greșită
- **Cauză:** `kurs_date` se calculează din `issued_date` (care e data exportului din Bug 2)
- **Fix per tip factură:**
  - **INVOICE (avans):** `issued_date - 1 zi` (comportament actual, corect)
  - **STORNO:** data cursului de pe factura de avans originală reversată (query `facturare_invoices` via `invoice_links` WHERE type=REVERSES)
  - **FINAL:** cursul + data cursului de pe factura de avans integral din aceeași anexă (query `facturare_invoices` WHERE anexa_id AND invoice_type='INVOICE' ORDER BY sequence_number DESC LIMIT 1)
- **Afectează:** Kursdatum (col AF) și Kurs (col AG)

### Bug 4: Conturi inversate la STORNO
- **Cauză:** în DB `facturare_konto_config` pentru STORNO, conturile sunt deja inversate (419968 pe konto_debit, 41214286 pe konto_credit). Codul pune konto_debit pe "s" și konto_credit pe "h". Contabila vrea 419968 pe "h" și 41214286 pe "s".
- **Fix:** la STORNO, inversăm soll/haben: rândul debit folosește `konto_credit` pe "s", rândul credit folosește `konto_debit` pe "h". Alternativ, corectăm valorile din DB și păstrăm logica.
- **Decizie:** corectăm în cod — la STORNO swap-uim s/h fără a schimba DB

### Bug 5: Același nr factură pt toate liniile STORNO
- **Cauză:** `routes_orders.py:1338` — `start_no=start_no` folosește nr facturii de storno
- **Fix:** fiecare linie ia `invoice_number` de pe factura de avans reversată corespunzătoare (din `reversed_invoices` query)

### Bug 6: Valoare storno 10% = preț integral
- **Cauză:** calculul `car_amount` la storno ia `ri_total` corect din factura reversată, dar trebuie verificat că `ri_total` = valoarea avansului, nu prețul de vânzare
- **Fix:** asigurăm că `ri_total = float(ri["total_amount_eur"])` reprezintă totalul facturii de avans (nu prețul de vânzare). Verificare: dacă factura de avans a fost de 10%, `ri_total` trebuie să fie 10% din total, nu 100%.

### Bug 7: Cont venituri FINAL hardcodat
- **Cauză:** `facturare_konto_config.konto_credit` e același pt toți (707132)
- **Fix:** la FINAL, se citesc regulile din `facturare_venituri_rules` pe baza supplier_id + prefix nr_comanda. Fiecare linie (mașină) poate avea cont diferit.

### Bug 8: Coloana "kostenstelle" goală la FINAL
- **Cauză:** coloana AJ (col 36) `kostenstelle` există deja în template dar nu e completată
- **Fix:** la FINAL, scrie `facturare_venituri_rules.kostenstelle` în coloana AJ (col 36) per linie
- **La INVOICE și STORNO:** coloana rămâne goală

---

## 5. Rezumat modificări per fișier

| Fișier | Modificări |
|---|---|
| **Migration nouă** | CREATE TABLE `facturare_venituri_rules` + ALTER TABLE `facturare_konto_config` ADD `text_template` + seed data |
| **routes_orders.py** | Fix-uri Bug 1-8 în `api_generate_eurofib()` + endpoint-uri noi GET/PUT `/facturare/api/venituri-rules` |
| **eurofib_xlsx.py** | Suport kostenstelle coloană, text din template, inversare s/h la STORNO |
| **config.py** | Adăugare `kostenstelle` și `text_template` în `EurofibConfig` |
| **index.tsx** (Settings) | Coloană text_template + secțiune reguli venituri |
| **ComenziTab.tsx** | Card "Date Contabile" pe contract view + validare konto în modal |
| **Repository** | Metode noi: `get_venituri_rules()`, `upsert_venituri_rules()` |

---

## 6. Ce NU se schimbă

- Schema `crm_clients` — `eurofib_konto_debit` rămâne JSONB, se citește doar
- Schema `companies` — `eurofib_klient_id` rămâne int, se citește doar
- PDF generation — nu e afectat
- Proforma export — nu există EuroFib pt proforma
