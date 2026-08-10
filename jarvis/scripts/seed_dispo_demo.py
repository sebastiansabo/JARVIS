"""Demo seed for the CarPark Dispo module (Phase 5, Task 5.3).

Inserts a small, hand-curated fleet of vehicles that together cover every
stage of the Dispo pipeline (STAGE_STATUS_MAP in dispo_repository.py):

    in_pregatire -> ACQUIRED, INSPECTION, RECONDITIONING
    in_stoc      -> READY_FOR_SALE (x3, at 3 different aging buckets)
    promovat     -> LISTED, PRICE_REDUCED
    rezervat     -> RESERVED (+ an active carpark_reservations row)
    vandut       -> SOLD (with a NEGATIVE gross margin, on purpose)
    livrat       -> DELIVERED (with a positive gross margin + stock_removed)
    iesit        -> TRANSFERRED

...plus the cost/revenue/document rows needed to light up the Dispo
workspace's aging colors, margin coloring, reservation widget, document
checklist, MISSING_PV_LIVRARE flag, and per-vehicle timeline.

Every demo vehicle's VIN is prefixed 'DEMO' (DEMODISPO00000001..12) so the
rows are trivially identifiable and safe to re-seed. This script writes raw
parameterized SQL directly (not through VehicleRepository/CostRepository/...)
for two reasons: (1) it needs one shared transaction across ~12 vehicles +
their children, so a failure partway through never leaves a half-seeded
fleet, and the repos each open-and-commit their own connection per call
(see BaseRepository); (2) VehicleRepository.create()'s VIN regex
(^[A-HJ-NPR-Z0-9]{17}$, excluding I/O/Q per ISO 3779) would reject the
'DEMODISPO...' prefix the brief asked for outright (it contains 'O' and
'I') — a real client-input safety check that doesn't apply to a seed
script writing directly to the DB. carpark_vehicles.vin has no DB-level
CHECK constraint, only VARCHAR(17) UNIQUE NOT NULL, so this is safe.

Idempotent: every run first deletes any existing demo rows for the target
company (`DELETE FROM carpark_vehicles WHERE vin LIKE 'DEMO%%' AND
company_id = %s`), then inserts the fleet fresh. Every carpark child table
(costs, revenues, documents, reservations, status_history, ...) has
`vehicle_id ... REFERENCES carpark_vehicles(id) ON DELETE CASCADE`
(confirmed against the live schema), so deleting the vehicle row is
sufficient to clean up every dependent row too — no separate per-table
DELETEs needed.

Usage:
    DATABASE_URL=postgresql://localhost/defaultdb \
        python scripts/seed_dispo_demo.py --company-id 16

    # remove the demo fleet without reinserting it:
    DATABASE_URL=postgresql://localhost/defaultdb \
        python scripts/seed_dispo_demo.py --company-id 16 --clean
"""
import argparse
import os
import sys
from datetime import date, datetime, timedelta

import psycopg2

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://localhost/defaultdb')

VIN_PREFIX = 'DEMO'

# carpark_locations row seeded for company 16 (Autoworld Showroom Cluj); if
# the target company has no such location, location_id is simply left NULL
# below (looked up at runtime, not hardcoded to company 16 specifically —
# see _pick_location()).
DEFAULT_LOCATION_TEXT = 'Cluj-Napoca'


def _d(offset_days: int) -> date:
    """today() + offset_days (offset is typically negative — days ago)."""
    return date.today() + timedelta(days=offset_days)


def _dt(offset_days: int, hour: int = 10) -> datetime:
    return datetime.combine(_d(offset_days), datetime.min.time()) + timedelta(hours=hour)


# ── Vehicle fleet definition ────────────────────────────────────────────
# One dict per vehicle. `history` is a list of (old_status, new_status,
# notes, when) tuples inserted into carpark_status_history so the Detail
# page's Timeline tab has a real transition chain, not just the vehicle's
# raw lifecycle-date columns. `documents` is a list of (document_type,
# title, uploaded_at_offset_days). `costs`/`revenues` are lists of dicts
# matching carpark_vehicle_costs / carpark_vehicle_revenues columns.
# `reservation` (only on the RESERVED vehicle) matches carpark_reservations.
def build_fleet(company_id: int, location_id):
    fleet = []

    # 1) ACQUIRED — recent, is_impus flag
    fleet.append(dict(
        seq=1, vin='DEMODISPO00000001', nr_stoc='STOC-DEMO-001',
        brand='BMW', model='X3', variant='xDrive20d', year_of_manufacture=2021,
        category='SH', fuel_type='Diesel', transmission='Automat',
        mileage_km=68000, color_exterior='Negru',
        status='ACQUIRED', source='DEALER', supplier_name='Auto Trade Import SRL',
        acquisition_date=_d(-2), acquisition_price=21000, acquisition_currency='EUR',
        minimum_price=None, current_price=None,
        is_impus=True, missing_civ=False,
        acquisition_manager_id=3, salesperson_user_id=None,
        notes='Achiziție recentă — demo seed (Task 5.3)',
        history=[(None, 'ACQUIRED', 'Vehicul achiziționat', _dt(-2))],
        documents=[],
        costs=[], revenues=[],
    ))

    # 2) INSPECTION — missing_civ flag
    fleet.append(dict(
        seq=2, vin='DEMODISPO00000002', nr_stoc='STOC-DEMO-002',
        brand='Audi', model='A4', variant='2.0 TDI', year_of_manufacture=2020,
        category='SH', fuel_type='Diesel', transmission='Automat',
        mileage_km=82000, color_exterior='Gri',
        status='INSPECTION', source='BUY BACK PF', supplier_name=None,
        acquisition_date=_d(-6), acquisition_price=17500, acquisition_currency='EUR',
        minimum_price=None, current_price=None,
        is_impus=False, missing_civ=True,
        acquisition_manager_id=4, salesperson_user_id=None,
        notes=None,
        history=[
            (None, 'ACQUIRED', 'Vehicul achiziționat', _dt(-6)),
            ('ACQUIRED', 'INSPECTION', 'Trimis la inspecție tehnică', _dt(-4)),
        ],
        documents=[('pv_intrare', 'PV intrare — Audi A4', -5)],
        costs=[], revenues=[],
    ))

    # 3) RECONDITIONING — full intake checklist + repair costs
    fleet.append(dict(
        seq=3, vin='DEMODISPO00000003', nr_stoc='STOC-DEMO-003',
        brand='Skoda', model='Octavia', variant='Combi 2.0 TDI', year_of_manufacture=2019,
        category='SH', fuel_type='Diesel', transmission='Manuală',
        mileage_km=95000, color_exterior='Alb',
        status='RECONDITIONING', source='IRC', supplier_name='IRC Leasing SA',
        acquisition_date=_d(-12), acquisition_price=12800, acquisition_currency='EUR',
        minimum_price=None, current_price=None,
        is_impus=False, missing_civ=False,
        acquisition_manager_id=3, salesperson_user_id=None,
        intake_pv_date=_d(-11), supplier_payment_date=_d(-9),
        notes=None,
        history=[
            (None, 'ACQUIRED', 'Vehicul achiziționat', _dt(-12)),
            ('ACQUIRED', 'INSPECTION', 'Trimis la inspecție tehnică', _dt(-9)),
            ('INSPECTION', 'RECONDITIONING', 'Necesită reconditionare', _dt(-5)),
        ],
        documents=[
            ('pv_intrare', 'PV intrare — Skoda Octavia', -11),
            ('factura_achizitie', 'Factură achiziție — Skoda Octavia', -10),
        ],
        costs=[
            dict(cost_type='repair', description='Reparație suspensie', amount=650,
                 currency='RON', date=_d(-3)),
            dict(cost_type='cleaning', description='Detailing interior/exterior', amount=150,
                 currency='RON', date=_d(-2)),
        ],
        revenues=[],
    ))

    # 4) READY_FOR_SALE — ~20 days aged (green aging)
    fleet.append(dict(
        seq=4, vin='DEMODISPO00000004', nr_stoc='STOC-DEMO-004',
        brand='Toyota', model='Corolla', variant='1.8 Hybrid', year_of_manufacture=2021,
        category='SH', fuel_type='Hibrid', transmission='Automat',
        mileage_km=45000, color_exterior='Albastru',
        status='READY_FOR_SALE', source='EXTERN STOC', supplier_name=None,
        acquisition_date=_d(-20), acquisition_price=13500, acquisition_currency='EUR',
        minimum_price=14800, current_price=15900,
        is_impus=False, missing_civ=False,
        acquisition_manager_id=3, salesperson_user_id=4,
        ready_for_sale_date=_d(-13),
        notes=None,
        history=[
            (None, 'ACQUIRED', 'Vehicul achiziționat', _dt(-20)),
            ('ACQUIRED', 'INSPECTION', 'Trimis la inspecție tehnică', _dt(-18)),
            ('INSPECTION', 'RECONDITIONING', 'Reconditionare minoră', _dt(-16)),
            ('RECONDITIONING', 'READY_FOR_SALE', 'Pregătit pentru vânzare', _dt(-13)),
        ],
        documents=[
            ('pv_intrare', 'PV intrare — Toyota Corolla', -19),
            ('factura_achizitie', 'Factură achiziție — Toyota Corolla', -18),
        ],
        costs=[
            dict(cost_type='repair', description='Revizie + plăcuțe frână', amount=300,
                 currency='RON', date=_d(-15)),
        ],
        revenues=[],
    ))

    # 5) READY_FOR_SALE — ~75 days aged (red aging)
    fleet.append(dict(
        seq=5, vin='DEMODISPO00000005', nr_stoc='STOC-DEMO-005',
        brand='Ford', model='Focus', variant='1.5 EcoBlue', year_of_manufacture=2019,
        category='SH', fuel_type='Diesel', transmission='Manuală',
        mileage_km=110000, color_exterior='Roșu',
        status='READY_FOR_SALE', source='CUSTODIE', supplier_name=None,
        acquisition_date=_d(-75), acquisition_price=8200, acquisition_currency='EUR',
        minimum_price=9500, current_price=10200,
        is_impus=False, missing_civ=False,
        acquisition_manager_id=None, salesperson_user_id=None,
        ready_for_sale_date=_d(-68),
        notes=None,
        history=[
            (None, 'ACQUIRED', 'Vehicul achiziționat', _dt(-75)),
            ('ACQUIRED', 'READY_FOR_SALE', 'Pregătit pentru vânzare', _dt(-68)),
        ],
        documents=[
            ('pv_intrare', 'PV intrare — Ford Focus', -74),
            ('factura_achizitie', 'Factură achiziție — Ford Focus', -73),
        ],
        costs=[
            dict(cost_type='repair', description='Reparație curea distribuție', amount=400,
                 currency='RON', date=_d(-70)),
            dict(cost_type='transport', description='Transport la showroom', amount=150,
                 currency='RON', date=_d(-74)),
        ],
        revenues=[],
    ))

    # 6) READY_FOR_SALE — ~100 days aged (dark-red aging)
    fleet.append(dict(
        seq=6, vin='DEMODISPO00000006', nr_stoc='STOC-DEMO-006',
        brand='Hyundai', model='Tucson', variant='1.6 CRDi', year_of_manufacture=2020,
        category='SH', fuel_type='Diesel', transmission='Automat',
        mileage_km=88000, color_exterior='Gri',
        status='READY_FOR_SALE', source='BUY BACK PJ', supplier_name='Fleet Corp SRL',
        acquisition_date=_d(-100), acquisition_price=15200, acquisition_currency='EUR',
        minimum_price=16800, current_price=17900,
        is_impus=False, missing_civ=False,
        acquisition_manager_id=None, salesperson_user_id=None,
        ready_for_sale_date=_d(-92),
        notes='Stoc vechi — necesită atenție (demo seed)',
        history=[
            (None, 'ACQUIRED', 'Vehicul achiziționat', _dt(-100)),
            ('ACQUIRED', 'READY_FOR_SALE', 'Pregătit pentru vânzare', _dt(-92)),
        ],
        documents=[
            ('pv_intrare', 'PV intrare — Hyundai Tucson', -99),
            ('factura_achizitie', 'Factură achiziție — Hyundai Tucson', -98),
        ],
        costs=[], revenues=[],
    ))

    # 7) LISTED — promovat
    fleet.append(dict(
        seq=7, vin='DEMODISPO00000007', nr_stoc='STOC-DEMO-007',
        brand='Kia', model='Sportage', variant='1.6 CRDi', year_of_manufacture=2021,
        category='SH', fuel_type='Diesel', transmission='Automat',
        mileage_km=52000, color_exterior='Alb',
        status='LISTED', source='DEALER', supplier_name=None,
        acquisition_date=_d(-35), acquisition_price=16200, acquisition_currency='EUR',
        minimum_price=17800, current_price=18900,
        is_impus=False, missing_civ=False,
        acquisition_manager_id=3, salesperson_user_id=22,
        ready_for_sale_date=_d(-30), listing_date=_d(-28),
        list_price=18900,
        notes=None,
        history=[
            (None, 'ACQUIRED', 'Vehicul achiziționat', _dt(-35)),
            ('ACQUIRED', 'READY_FOR_SALE', 'Pregătit pentru vânzare', _dt(-30)),
            ('READY_FOR_SALE', 'LISTED', 'Anunț publicat', _dt(-28)),
        ],
        documents=[
            ('pv_intrare', 'PV intrare — Kia Sportage', -34),
            ('factura_achizitie', 'Factură achiziție — Kia Sportage', -33),
        ],
        costs=[], revenues=[],
    ))

    # 8) PRICE_REDUCED — promovat
    fleet.append(dict(
        seq=8, vin='DEMODISPO00000008', nr_stoc='STOC-DEMO-008',
        brand='Renault', model='Megane', variant='1.5 dCi', year_of_manufacture=2019,
        category='SH', fuel_type='Diesel', transmission='Manuală',
        mileage_km=102000, color_exterior='Negru',
        status='PRICE_REDUCED', source='EXTERN COMANDA', supplier_name=None,
        acquisition_date=_d(-55), acquisition_price=7800, acquisition_currency='EUR',
        minimum_price=8600, current_price=8900,
        is_impus=False, missing_civ=False,
        acquisition_manager_id=None, salesperson_user_id=22,
        ready_for_sale_date=_d(-50), listing_date=_d(-48),
        list_price=9600, promotional_price=8900,
        notes=None,
        history=[
            (None, 'ACQUIRED', 'Vehicul achiziționat', _dt(-55)),
            ('ACQUIRED', 'READY_FOR_SALE', 'Pregătit pentru vânzare', _dt(-50)),
            ('READY_FOR_SALE', 'LISTED', 'Anunț publicat', _dt(-48)),
            ('LISTED', 'PRICE_REDUCED', 'Preț redus — stoc vechi', _dt(-10)),
        ],
        documents=[
            ('pv_intrare', 'PV intrare — Renault Megane', -54),
            ('factura_achizitie', 'Factură achiziție — Renault Megane', -53),
        ],
        costs=[], revenues=[],
    ))

    # 9) RESERVED — + active reservation row
    fleet.append(dict(
        seq=9, vin='DEMODISPO00000009', nr_stoc='STOC-DEMO-009',
        brand='Mercedes-Benz', model='C-Class', variant='C220d AMG Line', year_of_manufacture=2021,
        category='SH', fuel_type='Diesel', transmission='Automat',
        mileage_km=58000, color_exterior='Gri',
        status='RESERVED', source='AW NEXT', supplier_name=None,
        acquisition_date=_d(-40), acquisition_price=23500, acquisition_currency='EUR',
        minimum_price=25500, current_price=26900,
        is_impus=False, missing_civ=False,
        acquisition_manager_id=3, salesperson_user_id=4,
        ready_for_sale_date=_d(-35), listing_date=_d(-33), reservation_date=_d(-3),
        list_price=26900,
        notes=None,
        history=[
            (None, 'ACQUIRED', 'Vehicul achiziționat', _dt(-40)),
            ('ACQUIRED', 'READY_FOR_SALE', 'Pregătit pentru vânzare', _dt(-35)),
            ('READY_FOR_SALE', 'LISTED', 'Anunț publicat', _dt(-33)),
            ('LISTED', 'RESERVED', 'Rezervat pentru Andrei Popescu', _dt(-3)),
        ],
        documents=[
            ('pv_intrare', 'PV intrare — Mercedes-Benz C-Class', -39),
            ('factura_achizitie', 'Factură achiziție — Mercedes-Benz C-Class', -38),
        ],
        costs=[], revenues=[],
        reservation=dict(
            client_name='Andrei Popescu', client_phone='0722123456',
            client_email='andrei.popescu@example.com',
            user_id=4, reservation_start=_dt(-3), reservation_end=_dt(5, hour=18),
            deposit_amount=2500, deposit_paid=True, status='active',
            notes='Rezervare demo seed — Task 5.3',
        ),
    ))

    # 10) SOLD — negative gross margin, missing pv_livrare (surfaces the
    # paperclip "MISSING_PV_LIVRARE" flag on the Dispo row)
    fleet.append(dict(
        seq=10, vin='DEMODISPO00000010', nr_stoc='STOC-DEMO-010',
        brand='Volkswagen', model='Passat', variant='2.0 TDI Highline', year_of_manufacture=2018,
        category='SH', fuel_type='Diesel', transmission='Automat',
        mileage_km=145000, color_exterior='Negru',
        status='SOLD', source='DEALER', supplier_name=None,
        acquisition_date=_d(-60), acquisition_price=14000, acquisition_currency='EUR',
        minimum_price=13500, current_price=13800,
        is_impus=False, missing_civ=False,
        acquisition_manager_id=3, salesperson_user_id=22,
        ready_for_sale_date=_d(-53), listing_date=_d(-52),
        sale_price=13200, sale_date=_d(-5), sale_type='CASH', buyer_name='Ion Vasilescu',
        notes='Vânzare sub prețul minim — demo margine negativă (Task 5.3)',
        history=[
            (None, 'ACQUIRED', 'Vehicul achiziționat', _dt(-60)),
            ('ACQUIRED', 'READY_FOR_SALE', 'Pregătit pentru vânzare', _dt(-53)),
            ('READY_FOR_SALE', 'LISTED', 'Anunț publicat', _dt(-52)),
            ('LISTED', 'SOLD', 'Vehicul vândut', _dt(-5)),
        ],
        documents=[
            ('pv_intrare', 'PV intrare — Volkswagen Passat', -59),
            ('factura_achizitie', 'Factură achiziție — Volkswagen Passat', -58),
            ('contract_vanzare', 'Contract vânzare — Volkswagen Passat', -5),
        ],
        costs=[
            dict(cost_type='repair', description='Reparație cutie viteze', amount=800,
                 currency='RON', date=_d(-15)),
            dict(cost_type='cheltuieli_vanzare', description='Comision + pregătire livrare',
                 amount=500, currency='RON', date=_d(-5)),
        ],
        revenues=[
            dict(revenue_type='bonus_leasing', description='Bonus leasing furnizor',
                 amount=300, currency='RON', date=_d(-5), client_name='Ion Vasilescu'),
        ],
    ))

    # 11) DELIVERED — positive gross margin, stock_removed flag
    fleet.append(dict(
        seq=11, vin='DEMODISPO00000011', nr_stoc='STOC-DEMO-011',
        brand='Dacia', model='Duster', variant='TCe 150 4x2', year_of_manufacture=2020,
        category='SH', fuel_type='Benzină', transmission='Manuală',
        mileage_km=62000, color_exterior='Maro',
        status='DELIVERED', source='BUY BACK PF', supplier_name=None,
        acquisition_date=_d(-90), acquisition_price=10800, acquisition_currency='EUR',
        minimum_price=11500, current_price=13200,
        is_impus=False, missing_civ=False,
        acquisition_manager_id=3, salesperson_user_id=4,
        ready_for_sale_date=_d(-83), listing_date=_d(-80),
        sale_price=14200, sale_date=_d(-20), sale_type='BT LEASING', buyer_name='Maria Ionescu',
        delivery_date=_d(-10),
        stock_removed=True, stock_removed_date=_d(-2),
        gw_file_number='GW-2026-0456',
        notes=None,
        history=[
            (None, 'ACQUIRED', 'Vehicul achiziționat', _dt(-90)),
            ('ACQUIRED', 'READY_FOR_SALE', 'Pregătit pentru vânzare', _dt(-83)),
            ('READY_FOR_SALE', 'LISTED', 'Anunț publicat', _dt(-80)),
            ('LISTED', 'SOLD', 'Vehicul vândut', _dt(-20)),
            ('SOLD', 'DELIVERED', 'Vehicul livrat', _dt(-10)),
        ],
        documents=[
            ('pv_intrare', 'PV intrare — Dacia Duster', -89),
            ('factura_achizitie', 'Factură achiziție — Dacia Duster', -88),
            ('contract_vanzare', 'Contract vânzare — Dacia Duster', -20),
            ('pv_livrare', 'PV livrare — Dacia Duster', -10),
            ('factura_vanzare', 'Factură vânzare — Dacia Duster', -10),
        ],
        costs=[
            dict(cost_type='repair', description='Revizie generală', amount=400,
                 currency='RON', date=_d(-85)),
            dict(cost_type='transport', description='Transport la client', amount=200,
                 currency='RON', date=_d(-11)),
        ],
        revenues=[
            dict(revenue_type='bonus_leasing', description='Bonus leasing BT',
                 amount=250, currency='RON', date=_d(-20), client_name='Maria Ionescu'),
        ],
    ))

    # 12) TRANSFERRED — iesit
    fleet.append(dict(
        seq=12, vin='DEMODISPO00000012', nr_stoc='STOC-DEMO-012',
        brand='Volvo', model='V60', variant='D3 Momentum', year_of_manufacture=2018,
        category='SH', fuel_type='Diesel', transmission='Automat',
        mileage_km=130000, color_exterior='Albastru',
        status='TRANSFERRED', source='MOTION', supplier_name=None,
        acquisition_date=_d(-120), acquisition_price=9500, acquisition_currency='EUR',
        minimum_price=None, current_price=None,
        is_impus=False, missing_civ=False,
        acquisition_manager_id=None, salesperson_user_id=None,
        ready_for_sale_date=_d(-110), listing_date=_d(-100),
        notes='Transferat către AW Next — demo seed (Task 5.3)',
        history=[
            (None, 'ACQUIRED', 'Vehicul achiziționat', _dt(-120)),
            ('ACQUIRED', 'READY_FOR_SALE', 'Pregătit pentru vânzare', _dt(-110)),
            ('READY_FOR_SALE', 'LISTED', 'Anunț publicat', _dt(-100)),
            ('LISTED', 'TRANSFERRED', 'Transferat către altă locație', _dt(-15)),
        ],
        documents=[
            ('pv_intrare', 'PV intrare — Volvo V60', -119),
            ('factura_achizitie', 'Factură achiziție — Volvo V60', -118),
        ],
        costs=[], revenues=[],
    ))

    for v in fleet:
        v['company_id'] = company_id
        v.setdefault('location_id', location_id)
        v.setdefault('location_text', DEFAULT_LOCATION_TEXT if location_id else None)
        v.setdefault('minimum_price', None)
        v.setdefault('current_price', None)
        v.setdefault('reservation', None)

    return fleet


# ── DB helpers ───────────────────────────────────────────────────────────

VEHICLE_COLUMNS = [
    'vin', 'nr_stoc', 'brand', 'model', 'variant', 'year_of_manufacture',
    'category', 'status', 'fuel_type', 'transmission', 'mileage_km',
    'color_exterior', 'source', 'supplier_name',
    'acquisition_date', 'acquisition_price', 'acquisition_currency',
    'acquisition_manager_id', 'salesperson_user_id',
    'minimum_price', 'current_price', 'list_price', 'promotional_price',
    'ready_for_sale_date', 'listing_date', 'reservation_date',
    'sale_price', 'sale_date', 'sale_type', 'buyer_name', 'delivery_date',
    'stock_removed', 'stock_removed_date', 'gw_file_number',
    'intake_pv_date', 'supplier_payment_date',
    'is_impus', 'missing_civ', 'location_id', 'location_text',
    'company_id', 'notes',
]


def clean_demo_rows(cursor, company_id: int) -> int:
    """Delete every demo vehicle (and, via ON DELETE CASCADE, all of its
    costs/revenues/documents/reservations/status_history rows) for the
    target company. Returns the number of vehicles removed."""
    cursor.execute(
        "DELETE FROM carpark_vehicles WHERE vin LIKE %s AND company_id = %s RETURNING id",
        (f'{VIN_PREFIX}%', company_id),
    )
    return len(cursor.fetchall())


def _pick_location_id(cursor, company_id: int):
    """First active carpark_locations row for the company, if any (FK'd
    column — must reference a real row or stay NULL)."""
    cursor.execute(
        "SELECT id FROM carpark_locations WHERE company_id = %s AND is_active = TRUE "
        "ORDER BY id LIMIT 1",
        (company_id,),
    )
    row = cursor.fetchone()
    return row[0] if row else None


def insert_vehicle(cursor, v: dict) -> int:
    row = {col: v.get(col) for col in VEHICLE_COLUMNS}
    cols = list(row.keys())
    placeholders = ', '.join(['%s'] * len(cols))
    col_str = ', '.join(cols)
    cursor.execute(
        f'INSERT INTO carpark_vehicles ({col_str}) VALUES ({placeholders}) RETURNING id',
        tuple(row[c] for c in cols),
    )
    return cursor.fetchone()[0]


def insert_history(cursor, vehicle_id: int, history: list) -> int:
    n = 0
    for old_status, new_status, notes, when in history:
        cursor.execute(
            '''INSERT INTO carpark_status_history
                   (vehicle_id, old_status, new_status, notes, created_at)
               VALUES (%s, %s, %s, %s, %s)''',
            (vehicle_id, old_status, new_status, notes, when),
        )
        n += 1
    return n


def insert_documents(cursor, vehicle_id: int, documents: list) -> int:
    n = 0
    for document_type, title, offset_days in documents:
        cursor.execute(
            '''INSERT INTO carpark_vehicle_documents
                   (vehicle_id, document_type, title, upload_date)
               VALUES (%s, %s, %s, %s)''',
            (vehicle_id, document_type, title, _dt(offset_days)),
        )
        n += 1
    return n


def insert_costs(cursor, vehicle_id: int, costs: list) -> int:
    for c in costs:
        cursor.execute(
            '''INSERT INTO carpark_vehicle_costs
                   (vehicle_id, cost_type, description, amount, currency, date)
               VALUES (%s, %s, %s, %s, %s, %s)''',
            (vehicle_id, c['cost_type'], c.get('description'), c['amount'],
             c.get('currency', 'RON'), c['date']),
        )
    return len(costs)


def insert_revenues(cursor, vehicle_id: int, revenues: list) -> int:
    for r in revenues:
        cursor.execute(
            '''INSERT INTO carpark_vehicle_revenues
                   (vehicle_id, revenue_type, description, amount, currency, date, client_name)
               VALUES (%s, %s, %s, %s, %s, %s, %s)''',
            (vehicle_id, r['revenue_type'], r.get('description'), r['amount'],
             r.get('currency', 'RON'), r['date'], r.get('client_name')),
        )
    return len(revenues)


def insert_reservation(cursor, vehicle_id: int, res: dict) -> int:
    if not res:
        return 0
    cursor.execute(
        '''INSERT INTO carpark_reservations
               (vehicle_id, client_name, client_phone, client_email, user_id,
                reservation_start, reservation_end, deposit_amount, deposit_paid,
                status, notes, created_by)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
        (vehicle_id, res['client_name'], res.get('client_phone'), res.get('client_email'),
         res.get('user_id'), res['reservation_start'], res.get('reservation_end'),
         res.get('deposit_amount', 0), res.get('deposit_paid', False),
         res.get('status', 'active'), res.get('notes'), res.get('user_id')),
    )
    return 1


# ── main ─────────────────────────────────────────────────────────────────

def run(company_id: int, clean_only: bool) -> None:
    conn = psycopg2.connect(DATABASE_URL)
    try:
        conn.autocommit = False
        cursor = conn.cursor()

        removed = clean_demo_rows(cursor, company_id)
        print(f"Removed {removed} existing demo vehicle(s) for company_id={company_id}"
              " (cascade-deleted their costs/revenues/documents/reservations/history).")

        if clean_only:
            conn.commit()
            print("--clean: no rows inserted.")
            return

        location_id = _pick_location_id(cursor, company_id)
        fleet = build_fleet(company_id, location_id)

        stage_by_status = {
            'ACQUIRED': 'in_pregatire', 'INSPECTION': 'in_pregatire',
            'RECONDITIONING': 'in_pregatire', 'IN_TRANSIT': 'in_pregatire',
            'AT_BODYSHOP': 'in_pregatire',
            'READY_FOR_SALE': 'in_stoc',
            'LISTED': 'promovat', 'PRICE_REDUCED': 'promovat',
            'AUCTION_CANDIDATE': 'promovat',
            'RESERVED': 'rezervat',
            'SOLD': 'vandut',
            'DELIVERED': 'livrat',
            'RETURNED': 'iesit', 'SCRAPPED': 'iesit', 'TRANSFERRED': 'iesit',
            'INSURANCE_CLAIM': 'iesit',
        }
        stage_counts: dict = {}
        totals = dict(vehicles=0, costs=0, revenues=0, documents=0,
                       reservations=0, history=0)

        for v in fleet:
            vehicle_id = insert_vehicle(cursor, v)
            totals['history'] += insert_history(cursor, vehicle_id, v['history'])
            totals['documents'] += insert_documents(cursor, vehicle_id, v['documents'])
            totals['costs'] += insert_costs(cursor, vehicle_id, v['costs'])
            totals['revenues'] += insert_revenues(cursor, vehicle_id, v['revenues'])
            totals['reservations'] += insert_reservation(cursor, vehicle_id, v.get('reservation'))
            totals['vehicles'] += 1
            stage = stage_by_status[v['status']]
            stage_counts[stage] = stage_counts.get(stage, 0) + 1

        conn.commit()

        print(f"\nSeeded {totals['vehicles']} demo vehicles for company_id={company_id}:")
        for stage in ('in_pregatire', 'in_stoc', 'promovat', 'rezervat', 'vandut', 'livrat', 'iesit'):
            print(f"  {stage:<14} {stage_counts.get(stage, 0)}")
        print(f"\n  status_history rows:  {totals['history']}")
        print(f"  document rows:        {totals['documents']}")
        print(f"  cost rows:            {totals['costs']}")
        print(f"  revenue rows:         {totals['revenues']}")
        print(f"  reservation rows:     {totals['reservations']}")
        print(f"\nVIN range: {fleet[0]['vin']} .. {fleet[-1]['vin']}")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Seed demo CarPark Dispo vehicles spanning every pipeline stage')
    parser.add_argument('--company-id', type=int, default=16,
                         help='carpark_vehicles.company_id to seed into (default: 16)')
    parser.add_argument('--clean', action='store_true',
                         help='Remove existing demo rows for this company and exit '
                              '(do not reinsert)')
    args = parser.parse_args()

    try:
        run(args.company_id, args.clean)
    except Exception as e:
        print(f'Seed failed (transaction rolled back): {e}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
