"""Cost-center seed rows, extracted verbatim from
'centre cost firme grup AW 2026.xlsx' (6 sheets). One-time seed only;
in-app CRUD is authoritative afterwards. Code kept zero-padded (EuroFib form)."""

# sheet_key -> exact companies.company value (resolved against
# `SELECT id, company FROM companies ORDER BY company` on localhost/defaultdb).
SHEET_TO_COMPANY = {
    'AW':               'AUTOWORLD S.R.L.',            # holding, id=16
    'AW INTERNATIONAL': 'Autoworld INTERNATIONAL S.R.L.',  # id=10
    'AW PREMIUM':       'Autoworld PREMIUM S.R.L.',    # id=11
    'AW PRESTIGE':      'Autoworld PRESTIGE S.R.L.',   # id=12
    'AW PLUS':          'Autoworld PLUS S.R.L.',       # id=9
    'AW NEXT':          'Autoworld NEXT S.R.L.',       # id=13
}

SEED_ROWS = [
    # AW (holding)
    ('AW', '0281', 'IT'),
    ('AW', '0291', 'Conducere'),
    ('AW', '0292', 'Contabilitate'),
    ('AW', '0293', 'Administrativ VW'),
    # AW INTERNATIONAL
    ('AW INTERNATIONAL', '0211', 'Masini noi VW PKW'),
    ('AW INTERNATIONAL', '0212', 'Masini noi VW LNF'),
    ('AW INTERNATIONAL', '0231', 'Reparatii generale VW'),
    ('AW INTERNATIONAL', '0232', 'Tinichigerie VW'),
    ('AW INTERNATIONAL', '0233', 'Vopsitorie VW'),
    ('AW INTERNATIONAL', '0235', 'Piese de schimb VW'),
    ('AW INTERNATIONAL', '0234', 'Centru daune Oradiei'),
    ('AW INTERNATIONAL', '0240', 'Logistica'),
    ('AW INTERNATIONAL', '0241', 'Spalatorie VW'),
    ('AW INTERNATIONAL', '0281', 'IT'),
    ('AW INTERNATIONAL', '0291', 'Conducere'),
    ('AW INTERNATIONAL', '0292', 'Contabilitate'),
    ('AW INTERNATIONAL', '0293', 'Administrativ VW'),
    # AW PREMIUM
    ('AW PREMIUM', '0281', 'IT'),
    ('AW PREMIUM', '0291', 'Conducere'),
    ('AW PREMIUM', '0292', 'Contabilitate'),
    ('AW PREMIUM', '0313', 'Masini noi AUDI'),
    ('AW PREMIUM', '0322', 'AAP'),
    ('AW PREMIUM', '0331', 'Reparatii generale AUDI'),
    ('AW PREMIUM', '0335', 'Piese de schimb AUDI'),
    ('AW PREMIUM', '0341', 'Spalatorie AUDI'),
    ('AW PREMIUM', '0393', 'Administrativ AUDI'),
    ('AW PREMIUM', '0451', 'Asigurari'),
    # AW PRESTIGE
    ('AW PRESTIGE', '0411', 'Masini noi VOLVO'),
    ('AW PRESTIGE', '0431', 'Reparatii generale Volvo'),
    ('AW PRESTIGE', '0432', 'Tinichigerie VOLVO'),
    ('AW PRESTIGE', '0433', 'Vopsitorie VOLVO'),
    ('AW PRESTIGE', '0435', 'Piese de schimb VOLVO'),
    ('AW PRESTIGE', '0441', 'Spalatorie VOLVO'),
    ('AW PRESTIGE', '0481', 'IT VOLVO'),
    ('AW PRESTIGE', '0491', 'Conducere VOLVO'),
    ('AW PRESTIGE', '0492', 'Contabilitate VOLVO'),
    ('AW PRESTIGE', '0493', 'Administrativ VOLVO'),
    # AW PLUS
    ('AW PLUS', '0281', 'IT'),
    ('AW PLUS', '0291', 'Conducere'),
    ('AW PLUS', '0292', 'Contabilitate'),
    ('AW PLUS', '0611', 'Masini noi MG'),
    ('AW PLUS', '0612', 'Masini noi Mazda'),
    ('AW PLUS', '0631', 'Reparatii generale MG'),
    ('AW PLUS', '0632', 'Tinichigerie MG'),
    ('AW PLUS', '0633', 'Vopsitorie MG'),
    ('AW PLUS', '0635', 'Piese de schimb MG'),
    ('AW PLUS', '0641', 'Reparatii generale Mazda'),
    ('AW PLUS', '0642', 'Tinichigerie Mazda'),
    ('AW PLUS', '0643', 'Vopsitorie Mazda'),
    ('AW PLUS', '0645', 'Piese de schimb Mazda'),
    ('AW PLUS', '0654', 'Spalatorie'),
    ('AW PLUS', '0693', 'Administrativ'),
    # AW NEXT
    ('AW NEXT', '0281', 'IT'),
    ('AW NEXT', '0291', 'Conducere'),
    ('AW NEXT', '0292', 'Contabilitate'),
    ('AW NEXT', '0293', 'Administrativ VW'),
    ('AW NEXT', '0421', 'Masini Weltauto CarCloud'),
    ('AW NEXT', '0452', 'Motion'),
]
