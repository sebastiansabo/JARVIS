"""Idempotent seed of the three real AAP buyback contract templates, templatized.

Deal-specific values are replaced with {tokens} the P3b renderer substitutes;
the legal boilerplate is kept. Admins refine the exact wording in
Settings → BuyBack → Contracte. Company/brand are resolved BY NAME (robust
across environments); each row is inserted only WHERE NOT EXISTS so admin edits
are never overwritten.

Seeded (company, brand, document_type):
  - Autoworld International × DasWeltAuto × purchase    (Contract de achiziție)
  - Autoworld Prestige    × Volvo       × purchase    (Antecontract vânzare-cumpărare)
  - Autoworld International × Volkswagen (PKW) × consignment (Contract de depozit)
"""
import logging

logger = logging.getLogger('jarvis.buyback.contract_seed')

# ── Purchase — Contract de achiziție (DasWeltAuto / general) ────────────────
_PURCHASE_BODY = """CONTRACT DE ACHIZITIE AUTOVEHICUL RULAT
Nr. {contract_number} din data de {contract_date}

A. PARTILE
CUMPARATOR: {company_name}, cu sediul in {company_address}, numar de ordine la Registrul Comertului {company_reg_no}, Cod de inregistrare in scopuri de TVA {company_vat}, reprezentata legal de {company_administrator}, avand functia de Director General, prin {advisor_name} in calitate de consultant vanzari, denumit in continuare „Cumparator".
VANZATOR: {seller_name}, cu domiciliul/sediul in {seller_address}, CNP {seller_cnp} / CUI {seller_cui}, serie si numar CI {seller_ci}, numar de ordine la Registrul Comertului {seller_reg_no}, reprezentat legal prin {seller_legal_rep}, denumit in continuare „Vanzator".

B. OBIECTUL CONTRACTULUI
In baza prezentului contract, Vanzatorul vinde si transfera dreptul de proprietate, iar Cumparatorul cumpara si primeste dreptul de proprietate asupra autovehiculului: marca {brand}, tipul {model}, numar de identificare (VIN) {vin}, serie motor {engine_no}, cilindree {engine_capacity} cmc, {power_cp} CP, numarul cartii de identitate a vehiculului {civ_no}, kilometraj {mileage} km, prima inmatriculare {first_registration}.

C. PRETUL CONTRACTUAL
Pretul de vanzare al autovehiculului este in cuantum total de {price_eur} EUR, respectiv echivalentul in lei al sumei de {price_ron} RON ({price_words}), calculat la cursul de schimb EUR/RON publicat de Banca Nationala a Romaniei + 1% la data semnarii prezentului Contract. {vat_note}
Plata Pretului se va efectua exclusiv in lei (RON), la cursul BNR + 1% la data semnarii.

D. PREDAREA SI TRANSFERUL PROPRIETATII
Autovehiculul va fi predat de catre Vanzator Cumparatorului in maximum 2 zile lucratoare de la semnarea prezentului contract, la sediul Cumparatorului, pe baza de proces-verbal de predare-primire (Anexa 1). Dreptul de proprietate si riscurile se transfera la momentul incheierii valabile a Contractului si semnarii procesului-verbal.

E. GARANTIE
Vanzatorul garanteaza ca autovehiculul este lipsit de vicii ascunse la data predarii, raspunderea sa fiind antrenata in cazul descoperirii ulterioare a unor vicii ascunse pe care le-a cunoscut sau trebuia sa le cunoasca, inclusiv privind accidente anterioare sau kilometrajul real. Vanzatorul garanteaza pentru evictiune, declarand ca autovehiculul se afla in circuitul civil, este liber de orice sarcini, nu este sechestrat sau urmarit, nu face obiectul vreunui litigiu si nu figureaza pe lista autovehiculelor furate, iar obligatiile fiscale sunt achitate la zi.

Prezentul Contract a fost semnat astazi, {contract_date}, in exemplare originale, cate unul pentru fiecare parte.

Cumparator,                                   Vanzator,
{company_name}                                {seller_name}
prin {advisor_name}                           prin {seller_legal_rep}
"""

_PURCHASE_GC = """PROTECTIA DATELOR: {company_name} prelucreaza datele personale furnizate in cadrul acestui contract doar in scopul executarii lui si pentru demersuri la cererea dumneavoastra, in conformitate cu Regulamentul (UE) 2016/679. Cereri privind datele: protectiadatelor@autoworld.ro.
DIVERSE: Orice modificare produce efecte doar daca este scrisa si semnata de ambele parti. Anexele fac parte integranta din contract. Contractul este guvernat de legea romana; litigiile se solutioneaza pe cale amiabila sau de instantele competente din Romania."""

# ── Purchase — Antecontract de vânzare-cumpărare (leasing payoff, Volvo) ────
_ANTECONTRACT_BODY = """ANTECONTRACT DE VANZARE-CUMPARARE
Nr. {contract_number} / {contract_date}

Incheiat astazi, {contract_date}, intre:
{seller_name}, cu sediul/domiciliul in {seller_address}, Cod de inregistrare in scopuri de TVA {seller_cui}, CNP {seller_cnp}, serie si numar CI {seller_ci}, reprezentat legal de {seller_legal_rep}, in calitate de promitent vanzator,
si
{company_name}, cu sediul social in {company_address}, inmatriculata la Registrul Comertului sub nr. {company_reg_no}, Cod unic de inregistrare {company_vat}, reprezentata de {advisor_name}, in calitate de promitent cumparator,
care convin sa incheie prezentul antecontract in urmatoarele conditii:

Promitentul vanzator se obliga sa vanda catre {company_name} intregul drept de proprietate asupra autoturismului marca {brand}, tipul {model}, serie sasiu {vin}, prima inmatriculare {first_registration}, kilometraj {mileage} km, de indata ce devine proprietar de drept (inclusiv, daca este cazul, prin inchiderea contractului de leasing aferent).

Pretul vanzarii stabilit de comun acord este de {price_eur} EUR TVA inclus, respectiv {price_ron} RON ({price_words}). {vat_note}

Transmiterea proprietatii se va face la data semnarii contractului de vanzare-cumparare, in termen de 10 zile de la semnarea prezentului antecontract. Promitentul vanzator se obliga sa efectueze operatiunile necesare si declara ca, la data transferului, nu va mai avea obligatii de plata fata de eventualul finantator, sub sanctiunea incetarii de drept a prezentului antecontract.

Promitent vanzator,                           Promitent cumparator,
{seller_name}                                 {company_name}
prin {seller_legal_rep}                       prin {advisor_name}
"""

# ── Consignment — Contract de depozit (International / depozit) ─────────────
_CONSIGNMENT_BODY = """CONTRACT DE DEPOZIT
Nr. {contract_number} incheiat astazi {contract_date} la {company_name}

I. PARTILE CONTRACTANTE
1.1. {seller_name}, avand sediul/domiciliul in {seller_address}, CUI {seller_cui} / CNP {seller_cnp}, reprezentat legal prin {seller_legal_rep}, in calitate de deponent;
1.2. {company_name}, cu sediul in {company_address}, inregistrata la Registrul Comertului sub nr. {company_reg_no}, cod fiscal {company_vat}, cont bancar {company_iban} deschis la {company_bank}, reprezentata legal prin {company_administrator}, in calitate de depozitar,
au convenit incheierea prezentului contract de depozit cu respectarea art. 2103-2123 Cod civil.

II. OBIECTUL CONTRACTULUI
2.1. Deponentul incredinteaza spre pastrare, cu titlu de depozit, autovehiculul: marca {brand}, tipul {model}, serie sasiu {vin}, prima inmatriculare {first_registration}, kilometraj {mileage} km.
Pret dorit de client: {owner_price}, negociabil pana la {min_price}.
Pret promovare: {promo_price} pentru primele 10 zile.
Comision in urma vanzarii: {commission} din valoarea tranzactionata.
2.2. Depozitarul va promova spre vanzare autovehiculul pe www.autoworld.ro si va asigura expunerea in showroom-ul / parcul auto al depozitarului.

III. DURATA
3.1. Durata depozitarii este de 90 de zile de la semnare, prelungindu-se automat pentru perioade egale daca autovehiculul nu este vandut sau restituit la cerere.

IV. PRETUL CONTRACTULUI
4.2. Pretul promovarii si al expunerii este de {monthly_fee} pe luna + TVA, prima luna fiind gratuita.
4.4. In cazul vanzarii de catre depozitar, deponentul achita comisionul de {commission} din valoarea contractului.

V. RISCURI
Riscurile sunt suportate de proprietar, inclusiv riscul pieirii sau deteriorarii fortuite, pe durata depozitului.

Deponent,                                     Depozitar,
{seller_name}                                 {company_name}
prin {seller_legal_rep}                       prin {company_administrator}
"""


# Each spec: (company ILIKE, brand name, document_type, title, body, general_conditions)
_SPECS = [
    ('%INTERNATIONAL%', 'DasWeltAuto', 'purchase',
     'Contract de achiziție autovehicul rulat', _PURCHASE_BODY, _PURCHASE_GC),
    ('%PRESTIGE%', 'Volvo', 'purchase',
     'Antecontract de vânzare-cumpărare', _ANTECONTRACT_BODY, _PURCHASE_GC),
    ('%INTERNATIONAL%', 'Volkswagen (PKW)', 'consignment',
     'Contract de depozit', _CONSIGNMENT_BODY, ''),
]


def _scalar(row):
    if row is None:
        return None
    return row[0] if not isinstance(row, dict) else next(iter(row.values()))


def seed_contract_templates(conn, cursor, specs=None):
    """Insert the AAP templates (WHERE NOT EXISTS). Best-effort: a resolution or
    insert failure for one spec is logged and the others continue.

    The real boot path (init_db -> get_db) runs autocommit=True, so each
    statement is its own implicit transaction and a failure can't poison later
    ones. When a caller instead runs us inside an open transaction
    (autocommit=False), a failed statement would abort that whole transaction
    (InFailedSqlTransaction on every later statement, including other schema
    domains), so there we wrap each spec in a SAVEPOINT and roll back to it on
    error. Picking the mode off conn.autocommit keeps both paths correct."""
    use_savepoint = not getattr(conn, 'autocommit', True)
    for company_like, brand_name, doc_type, title, body, gc in (specs or _SPECS):
        try:
            if use_savepoint:
                cursor.execute('SAVEPOINT bb_seed')
            cursor.execute('SELECT id FROM companies WHERE company ILIKE %s ORDER BY id LIMIT 1',
                           (company_like,))
            company_id = _scalar(cursor.fetchone())
            cursor.execute('SELECT id FROM brands WHERE name ILIKE %s ORDER BY id LIMIT 1',
                           (brand_name,))
            brand_id = _scalar(cursor.fetchone())
            if company_id is None or brand_id is None:
                if use_savepoint:
                    cursor.execute('RELEASE SAVEPOINT bb_seed')
                logger.info('buyback contract seed: skipped %s/%s (company/brand not found)',
                            company_like, brand_name)
                continue
            cursor.execute(
                'INSERT INTO buyback_contract_templates '
                '(company_id, brand_id, document_type, title, body_template, '
                ' general_conditions, is_active) '
                'SELECT %s, %s, %s, %s, %s, %s, TRUE WHERE NOT EXISTS ('
                '  SELECT 1 FROM buyback_contract_templates '
                '  WHERE company_id = %s AND brand_id = %s AND document_type = %s)',
                (company_id, brand_id, doc_type, title, body, gc,
                 company_id, brand_id, doc_type),
            )
            if use_savepoint:
                cursor.execute('RELEASE SAVEPOINT bb_seed')
        except Exception:
            if use_savepoint:
                try:
                    cursor.execute('ROLLBACK TO SAVEPOINT bb_seed')
                except Exception:
                    logger.exception('buyback contract seed: savepoint rollback failed')
            logger.exception('buyback contract seed failed for %s/%s', company_like, brand_name)
