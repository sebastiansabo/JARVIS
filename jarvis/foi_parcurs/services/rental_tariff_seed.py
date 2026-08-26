"""SHARETOO RENT corporate tariff scheme (Octombrie 2025), transcribed from
`Tarife Coporate - Sharetoo Rent Octombrie 2025.pdf`. Pure data — imported by
the schema-incremental seed to populate the rental-tariff tables for Autoworld
PREMIUM (company_id 11). All amounts EUR ex-VAT. Transmission is folded into
`models_note` (it is not a pricing dimension). Daily rates only; the PDF's
monthly-estimate columns are intentionally omitted (deferred)."""

SHARETOO_COMPANY_ID = 11

# (label, min_days, max_days, sort_order); max_days None = open-ended top band.
SHARETOO_INTERVALS = [
    ('1-8 zile',     1,    8, 0),
    ('9-30 zile',    9,   30, 1),
    ('31-90 zile',  31,   90, 2),
    ('91-180 zile', 91,  180, 3),
    ('181+ zile',  181, None, 4),
]

# (name, models_note, franchise_eur, extra_km_eur, prices) — prices align to
# SHARETOO_INTERVALS order (1-8 / 9-30 / 31-90 / 91-180 / 181+), EUR per day.
SHARETOO_CATEGORIES = [
    ('ECONOMY',          'Skoda Fabia, VW Polo (manuală)',                                        200, 0.25, (20, 18, 16, 15, 14)),
    ('ECONOMY +',        'Skoda Fabia, VW Polo (automată)',                                       200, 0.25, (21, 19, 18, 17, 16)),
    ('INTERMEDIATE',     'VW T-Cross, Skoda Kamiq (manuală)',                                     200, 0.25, (22, 20, 19, 18, 17)),
    ('INTERMEDIATE +',   'Skoda Scala, VW T-Cross, Skoda Kamiq, Seat Arona, VW Taigo (automată)', 200, 0.25, (24, 21, 20, 19, 18)),
    ('COMPACT',          'VW Golf, Skoda Octavia, Seat & Cupra Leon (manuală)',                   200, 0.25, (25, 23, 21, 20, 19)),
    ('COMPACT +',        'VW Golf, Skoda Octavia, Seat & Cupra Leon, Audi A3 (automată)',         200, 0.25, (30, 26, 23, 22, 21)),
    ('SUV',              'Skoda Karoq, VW T-Roc (manuală)',                                       200, 0.25, (31, 29, 26, 24, 22)),
    ('SUV+',             'Skoda Karoq, VW T-Roc, Cupra Formentor (automată)',                     250, 0.25, (33, 31, 28, 24, 23)),
    ('ELECTRIC COMPACT', 'VW ID3',                                                                250, 0.25, (36, 32, 30, 28, 27)),
    ('PREMIUM',          'Skoda Superb, VW Passat, VW Arteon',                                    250, 0.35, (36, 32, 29, 27, 26)),
    ('PREMIUM SUV',      'VW Tiguan, Audi Q3, Skoda Kodiaq, Seat Tarraco, Cupra Terramar',        250, 0.35, (40, 35, 30, 28, 27)),
    ('ELECTRIC SUV',     'VW ID4',                                                                300, 0.35, (44, 40, 38, 35, 34)),
    ('PREMIUM +',        'Audi A4 / Audi A5',                                                     250, 0.35, (45, 42, 32, 30, 29)),
    ('PREMIUM SUV +',    'Audi Q5',                                                               300, 0.50, (55, 49, 40, 38, 37)),
    ('EXECUTIVE',        'Audi A6',                                                               300, 0.50, (61, 57, 50, 47, 45)),
    ('EXECUTIVE +',      'VW Touareg, Audi Q7, Porsche Macan',                                    400, 0.50, (84, 81, 70, 66, 62)),
    ('LUXURY',           'Audi Q8',                                                               500, 0.50, (105, 99, 94, 86, 80)),
    ('PICKUP',           'VW Amarok',                                                             300, 0.35, (51, 48, 44, 42, 40)),
]
