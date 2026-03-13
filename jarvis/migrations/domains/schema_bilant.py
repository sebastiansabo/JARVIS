"""Bilant schema: bilant_templates, bilant_template_rows, bilant_metric_configs, bilant_generations, bilant_results, bilant_metrics."""
import psycopg2
import psycopg2.errors


def create_schema_bilant(conn, cursor):
    """Create Bilant (Balance Sheet) Generator tables."""
    # ============== Bilant (Balance Sheet) Generator ==============

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bilant_templates (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
            is_default BOOLEAN DEFAULT FALSE,
            version INTEGER DEFAULT 1,
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_templates_company ON bilant_templates(company_id)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bilant_template_rows (
            id SERIAL PRIMARY KEY,
            template_id INTEGER NOT NULL REFERENCES bilant_templates(id) ON DELETE CASCADE,
            description TEXT NOT NULL,
            nr_rd TEXT,
            formula_ct TEXT,
            formula_rd TEXT,
            row_type TEXT DEFAULT 'data',
            is_bold BOOLEAN DEFAULT FALSE,
            indent_level INTEGER DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_tpl_rows_template ON bilant_template_rows(template_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_tpl_rows_order ON bilant_template_rows(template_id, sort_order)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bilant_metric_configs (
            id SERIAL PRIMARY KEY,
            template_id INTEGER NOT NULL REFERENCES bilant_templates(id) ON DELETE CASCADE,
            metric_key TEXT NOT NULL,
            metric_label TEXT NOT NULL,
            nr_rd TEXT NOT NULL,
            metric_group TEXT DEFAULT 'summary',
            sort_order INTEGER DEFAULT 0,
            CONSTRAINT bilant_metric_unique UNIQUE (template_id, metric_key)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_metric_cfg_template ON bilant_metric_configs(template_id)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bilant_generations (
            id SERIAL PRIMARY KEY,
            template_id INTEGER NOT NULL REFERENCES bilant_templates(id),
            company_id INTEGER NOT NULL REFERENCES companies(id),
            period_label TEXT,
            period_date DATE,
            status TEXT DEFAULT 'completed',
            error_message TEXT,
            original_filename TEXT,
            generated_by INTEGER NOT NULL REFERENCES users(id),
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_gen_company ON bilant_generations(company_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_gen_date ON bilant_generations(period_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_gen_template ON bilant_generations(template_id)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bilant_results (
            id SERIAL PRIMARY KEY,
            generation_id INTEGER NOT NULL REFERENCES bilant_generations(id) ON DELETE CASCADE,
            template_row_id INTEGER REFERENCES bilant_template_rows(id) ON DELETE SET NULL,
            nr_rd TEXT,
            description TEXT,
            formula_ct TEXT,
            formula_rd TEXT,
            value NUMERIC(15,2) DEFAULT 0,
            verification TEXT,
            sort_order INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_results_gen ON bilant_results(generation_id)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bilant_metrics (
            id SERIAL PRIMARY KEY,
            generation_id INTEGER NOT NULL REFERENCES bilant_generations(id) ON DELETE CASCADE,
            metric_key TEXT NOT NULL,
            metric_label TEXT NOT NULL,
            metric_group TEXT NOT NULL,
            value NUMERIC(15,4),
            interpretation TEXT,
            percent NUMERIC(7,2),
            CONSTRAINT bilant_metric_gen_unique UNIQUE (generation_id, metric_key)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_metrics_gen ON bilant_metrics(generation_id)')

    # Add ai_analysis column to bilant_generations (incremental migration)
    cursor.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'bilant_generations' AND column_name = 'ai_analysis') THEN
                ALTER TABLE bilant_generations ADD COLUMN ai_analysis JSONB;
            END IF;
        END $$;
    """)

    # Seed default Bilant template if not present
    cursor.execute("SELECT COUNT(*) as cnt FROM bilant_templates")
    if cursor.fetchone()['cnt'] == 0:
        _seed_bilant_default_template(cursor)
        conn.commit()


def _seed_bilant_default_template(cursor):
    """Seed default Romanian Bilant template from fixture JSON."""
    import json
    import os
    fixture_path = os.path.join(os.path.dirname(__file__), '..', 'accounting', 'bilant', 'fixtures', 'default_template.json')
    if not os.path.exists(fixture_path):
        return

    with open(fixture_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Use user id 1 (admin) as creator
    cursor.execute('''
        INSERT INTO bilant_templates (name, description, is_default, created_by)
        VALUES (%s, %s, %s, 1) RETURNING id
    ''', (data['name'], data.get('description'), data.get('is_default', True)))
    template_id = cursor.fetchone()['id']

    for row in data.get('rows', []):
        cursor.execute('''
            INSERT INTO bilant_template_rows
                (template_id, description, nr_rd, formula_ct, formula_rd, row_type, is_bold, indent_level, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (template_id, row['description'], row.get('nr_rd'), row.get('formula_ct'),
              row.get('formula_rd'), row.get('row_type', 'data'), row.get('is_bold', False),
              row.get('indent_level', 0), row.get('sort_order', 0)))

    for mc in data.get('metric_configs', []):
        cursor.execute('''
            INSERT INTO bilant_metric_configs
                (template_id, metric_key, metric_label, nr_rd, metric_group, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (template_id, mc['metric_key'], mc['metric_label'], mc['nr_rd'],
              mc.get('metric_group', 'summary'), mc.get('sort_order', 0)))


def _seed_bilant_dynamic_metrics(cursor):
    """Seed ratio, derived, and structure metric configs for the default Bilant template."""
    cursor.execute("SELECT id FROM bilant_templates WHERE is_default = TRUE LIMIT 1")
    row = cursor.fetchone()
    if not row:
        return
    tid = row['id']

    # (metric_key, metric_label, metric_group, nr_rd, formula_expr, display_format, interpretation, threshold_good, threshold_warning, structure_side, sort_order)
    configs = [
        # Derived summaries
        ('total_active', 'Total Active', 'derived', None, 'active_imobilizate + active_circulante', 'currency', None, None, None, None, 0),
        ('total_datorii', 'Total Datorii', 'derived', None, 'datorii_termen_scurt + datorii_termen_lung', 'currency', None, None, None, None, 5),
        # Ratios
        ('lichiditate_curenta', 'Lichiditate Curenta', 'ratio', None, 'active_circulante / datorii_termen_scurt', 'ratio', 'Ideal > 1', 2.0, 1.0, None, 10),
        ('lichiditate_rapida', 'Lichiditate Rapida', 'ratio', None, '(active_circulante - stocuri) / datorii_termen_scurt', 'ratio', 'Ideal > 0.8', 1.0, 0.5, None, 11),
        ('lichiditate_imediata', 'Lichiditate Imediata', 'ratio', None, 'disponibilitati / datorii_termen_scurt', 'ratio', 'Ideal > 0.2', 0.5, 0.2, None, 12),
        ('solvabilitate', 'Solvabilitate', 'ratio', None, 'capitaluri_proprii / total_active * 100', 'percent', 'Ideal > 50%', 50.0, 30.0, None, 13),
        ('indatorare', 'Indatorare', 'ratio', None, 'total_datorii / total_active * 100', 'percent', 'Ideal < 50%', None, None, None, 14),
        ('autonomie_financiara', 'Autonomie Financiara', 'ratio', None, 'capitaluri_proprii / (capitaluri_proprii + total_datorii) * 100', 'percent', 'Ideal > 50%', 50.0, 30.0, None, 15),
        # Structure — assets
        ('struct_active_imobilizate', 'Active Imobilizate', 'structure', '25', None, 'currency', None, None, None, 'assets', 20),
        ('struct_stocuri', 'Stocuri', 'structure', '30', None, 'currency', None, None, None, 'assets', 21),
        ('struct_creante', 'Creante', 'structure', '36', None, 'currency', None, None, None, 'assets', 22),
        ('struct_disponibilitati', 'Disponibilitati', 'structure', '40', None, 'currency', None, None, None, 'assets', 23),
        # Structure — liabilities
        ('struct_capitaluri_proprii', 'Capitaluri Proprii', 'structure', '100', None, 'currency', None, None, None, 'liabilities', 24),
        ('struct_datorii_scurt', 'Datorii < 1 an', 'structure', '53', None, 'currency', None, None, None, 'liabilities', 25),
        ('struct_datorii_lung', 'Datorii > 1 an', 'structure', '64', None, 'currency', None, None, None, 'liabilities', 26),
    ]

    for c in configs:
        cursor.execute('''
            INSERT INTO bilant_metric_configs
                (template_id, metric_key, metric_label, metric_group, nr_rd, formula_expr,
                 display_format, interpretation, threshold_good, threshold_warning, structure_side, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (template_id, metric_key) DO NOTHING
        ''', (tid, *c))


def _seed_chart_of_accounts(cursor):
    """Seed standard Romanian Plan General de Conturi (classes + groups + synthetic accounts)."""
    # (code, name, account_class, account_type, parent_code)
    accounts = [
        # ── Class 1: Capitaluri (Equity) ──
        ('1', 'Capitaluri', 1, 'class', None),
        ('10', 'Capital si rezerve', 1, 'group', '1'),
        ('101', 'Capital social', 1, 'synthetic', '10'),
        ('104', 'Prime de capital', 1, 'synthetic', '10'),
        ('105', 'Rezerve', 1, 'synthetic', '10'),
        ('106', 'Rezerve din reevaluare', 1, 'synthetic', '10'),
        ('107', 'Diferente de curs valutar din conversie', 1, 'synthetic', '10'),
        ('108', 'Interese care nu controleaza', 1, 'synthetic', '10'),
        ('109', 'Actiuni proprii', 1, 'synthetic', '10'),
        ('11', 'Rezultatul reportat', 1, 'group', '1'),
        ('117', 'Rezultatul reportat', 1, 'synthetic', '11'),
        ('12', 'Rezultatul exercitiului financiar', 1, 'group', '1'),
        ('121', 'Profit sau pierdere', 1, 'synthetic', '12'),
        ('129', 'Repartizarea profitului', 1, 'synthetic', '12'),
        ('14', 'Castiguri/pierderi legate de instrumente de capitaluri proprii', 1, 'group', '1'),
        ('141', 'Castiguri legate de vanzarea instrumentelor de capitaluri proprii', 1, 'synthetic', '14'),
        ('149', 'Pierderi legate de emiterea instrumentelor de capitaluri proprii', 1, 'synthetic', '14'),
        ('15', 'Provizioane', 1, 'group', '1'),
        ('151', 'Provizioane', 1, 'synthetic', '15'),
        ('16', 'Imprumuturi si datorii asimilate', 1, 'group', '1'),
        ('161', 'Imprumuturi din emisiuni de obligatiuni', 1, 'synthetic', '16'),
        ('162', 'Credite bancare pe termen lung', 1, 'synthetic', '16'),
        ('166', 'Datorii din concesiuni/inchirieri/locatii de gestiune', 1, 'synthetic', '16'),
        ('167', 'Alte imprumuturi si datorii asimilate', 1, 'synthetic', '16'),
        ('168', 'Dobanzi aferente imprumuturilor', 1, 'synthetic', '16'),
        ('169', 'Prime privind rambursarea obligatiunilor', 1, 'synthetic', '16'),
        # ── Class 2: Imobilizari (Fixed Assets) ──
        ('2', 'Imobilizari', 2, 'class', None),
        ('20', 'Imobilizari necorporale', 2, 'group', '2'),
        ('201', 'Cheltuieli de constituire', 2, 'synthetic', '20'),
        ('203', 'Cheltuieli de dezvoltare', 2, 'synthetic', '20'),
        ('205', 'Concesiuni, brevete, licente, marci comerciale', 2, 'synthetic', '20'),
        ('206', 'Active necorporale de explorare', 2, 'synthetic', '20'),
        ('207', 'Fond comercial', 2, 'synthetic', '20'),
        ('208', 'Alte imobilizari necorporale', 2, 'synthetic', '20'),
        ('21', 'Imobilizari corporale', 2, 'group', '2'),
        ('211', 'Terenuri si amenajari de terenuri', 2, 'synthetic', '21'),
        ('212', 'Constructii', 2, 'synthetic', '21'),
        ('213', 'Instalatii tehnice si masini', 2, 'synthetic', '21'),
        ('214', 'Alte instalatii, utilaje si mobilier', 2, 'synthetic', '21'),
        ('215', 'Investitii imobiliare', 2, 'synthetic', '21'),
        ('216', 'Active corporale de explorare', 2, 'synthetic', '21'),
        ('217', 'Active biologice productive', 2, 'synthetic', '21'),
        ('22', 'Imobilizari corporale in curs', 2, 'group', '2'),
        ('223', 'Instalatii tehnice in curs de montaj', 2, 'synthetic', '22'),
        ('224', 'Alte imobilizari corporale in curs', 2, 'synthetic', '22'),
        ('231', 'Imobilizari corporale in curs de executie', 2, 'synthetic', '22'),
        ('235', 'Investitii imobiliare in curs', 2, 'synthetic', '22'),
        ('26', 'Imobilizari financiare', 2, 'group', '2'),
        ('261', 'Actiuni detinute la filiale', 2, 'synthetic', '26'),
        ('262', 'Actiuni detinute la entitati asociate', 2, 'synthetic', '26'),
        ('263', 'Actiuni detinute la entitati controlate in comun', 2, 'synthetic', '26'),
        ('265', 'Alte titluri imobilizate', 2, 'synthetic', '26'),
        ('267', 'Creante imobilizate', 2, 'synthetic', '26'),
        ('269', 'Varsaminte de efectuat pentru imobilizari financiare', 2, 'synthetic', '26'),
        ('28', 'Amortizari privind imobilizarile', 2, 'group', '2'),
        ('280', 'Amortizarea imobilizarilor necorporale', 2, 'synthetic', '28'),
        ('281', 'Amortizarea imobilizarilor corporale', 2, 'synthetic', '28'),
        ('29', 'Ajustari pentru deprecierea imobilizarilor', 2, 'group', '2'),
        ('290', 'Ajustari pentru deprecierea imobilizarilor necorporale', 2, 'synthetic', '29'),
        ('291', 'Ajustari pentru deprecierea imobilizarilor corporale', 2, 'synthetic', '29'),
        ('296', 'Ajustari pentru pierderea de valoare a imobilizarilor financiare', 2, 'synthetic', '29'),
        # ── Class 3: Stocuri (Inventories) ──
        ('3', 'Stocuri si productie in curs de executie', 3, 'class', None),
        ('30', 'Stocuri de materii prime si materiale', 3, 'group', '3'),
        ('301', 'Materii prime', 3, 'synthetic', '30'),
        ('302', 'Materiale consumabile', 3, 'synthetic', '30'),
        ('303', 'Materiale de natura obiectelor de inventar', 3, 'synthetic', '30'),
        ('308', 'Diferente de pret la materii prime si materiale', 3, 'synthetic', '30'),
        ('32', 'Stocuri in curs de aprovizionare', 3, 'group', '3'),
        ('321', 'Materii prime in curs de aprovizionare', 3, 'synthetic', '32'),
        ('322', 'Materiale consumabile in curs de aprovizionare', 3, 'synthetic', '32'),
        ('323', 'Materiale de natura obiectelor de inventar in curs', 3, 'synthetic', '32'),
        ('327', 'Marfuri in curs de aprovizionare', 3, 'synthetic', '32'),
        ('33', 'Productie in curs de executie', 3, 'group', '3'),
        ('331', 'Produse in curs de executie', 3, 'synthetic', '33'),
        ('332', 'Lucrari si servicii in curs de executie', 3, 'synthetic', '33'),
        ('34', 'Produse', 3, 'group', '3'),
        ('341', 'Semifabricate', 3, 'synthetic', '34'),
        ('345', 'Produse finite', 3, 'synthetic', '34'),
        ('346', 'Produse reziduale', 3, 'synthetic', '34'),
        ('348', 'Diferente de pret la produse', 3, 'synthetic', '34'),
        ('35', 'Stocuri aflate la terti', 3, 'group', '3'),
        ('351', 'Materii si materiale aflate la terti', 3, 'synthetic', '35'),
        ('354', 'Produse aflate la terti', 3, 'synthetic', '35'),
        ('356', 'Animale aflate la terti', 3, 'synthetic', '35'),
        ('357', 'Marfuri aflate la terti', 3, 'synthetic', '35'),
        ('36', 'Animale', 3, 'group', '3'),
        ('361', 'Animale si pasari', 3, 'synthetic', '36'),
        ('37', 'Marfuri', 3, 'group', '3'),
        ('371', 'Marfuri', 3, 'synthetic', '37'),
        ('378', 'Diferente de pret la marfuri', 3, 'synthetic', '37'),
        ('38', 'Ambalaje', 3, 'group', '3'),
        ('381', 'Ambalaje', 3, 'synthetic', '38'),
        ('39', 'Ajustari pentru deprecierea stocurilor', 3, 'group', '3'),
        ('391', 'Ajustari pentru deprecierea materiilor prime', 3, 'synthetic', '39'),
        ('392', 'Ajustari pentru deprecierea materialelor', 3, 'synthetic', '39'),
        ('397', 'Ajustari pentru deprecierea marfurilor', 3, 'synthetic', '39'),
        # ── Class 4: Terti (Receivables & Payables) ──
        ('4', 'Conturi de terti', 4, 'class', None),
        ('40', 'Furnizori si conturi asimilate', 4, 'group', '4'),
        ('401', 'Furnizori', 4, 'synthetic', '40'),
        ('403', 'Efecte de platit', 4, 'synthetic', '40'),
        ('404', 'Furnizori de imobilizari', 4, 'synthetic', '40'),
        ('405', 'Efecte de platit pentru imobilizari', 4, 'synthetic', '40'),
        ('408', 'Furnizori - facturi nesosite', 4, 'synthetic', '40'),
        ('409', 'Furnizori - debitori', 4, 'synthetic', '40'),
        ('41', 'Clienti si conturi asimilate', 4, 'group', '4'),
        ('411', 'Clienti', 4, 'synthetic', '41'),
        ('413', 'Efecte de primit de la clienti', 4, 'synthetic', '41'),
        ('418', 'Clienti - facturi de intocmit', 4, 'synthetic', '41'),
        ('419', 'Clienti - creditori', 4, 'synthetic', '41'),
        ('42', 'Personal si conturi asimilate', 4, 'group', '4'),
        ('421', 'Personal - salarii datorate', 4, 'synthetic', '42'),
        ('423', 'Personal - ajutoare materiale datorate', 4, 'synthetic', '42'),
        ('424', 'Prime reprezentand participarea personalului la profit', 4, 'synthetic', '42'),
        ('425', 'Avansuri acordate personalului', 4, 'synthetic', '42'),
        ('426', 'Drepturi de personal neridicate', 4, 'synthetic', '42'),
        ('427', 'Retineri din salarii datorate tertilor', 4, 'synthetic', '42'),
        ('428', 'Alte datorii si creante in legatura cu personalul', 4, 'synthetic', '42'),
        ('43', 'Asigurari sociale, protectia sociala', 4, 'group', '4'),
        ('431', 'Asigurari sociale', 4, 'synthetic', '43'),
        ('436', 'Contributia asiguratorie pentru munca', 4, 'synthetic', '43'),
        ('437', 'Ajutor de somaj', 4, 'synthetic', '43'),
        ('438', 'Alte datorii si creante sociale', 4, 'synthetic', '43'),
        ('44', 'Bugetul statului, fonduri speciale', 4, 'group', '4'),
        ('441', 'Impozitul pe profit/venit', 4, 'synthetic', '44'),
        ('442', 'Taxa pe valoarea adaugata', 4, 'synthetic', '44'),
        ('444', 'Impozitul pe venituri de natura salariilor', 4, 'synthetic', '44'),
        ('445', 'Subventii', 4, 'synthetic', '44'),
        ('446', 'Alte impozite, taxe si varsaminte asimilate', 4, 'synthetic', '44'),
        ('447', 'Fonduri speciale - taxe si varsaminte asimilate', 4, 'synthetic', '44'),
        ('448', 'Alte datorii si creante cu bugetul statului', 4, 'synthetic', '44'),
        ('45', 'Grup si actionari/asociati', 4, 'group', '4'),
        ('451', 'Decontari intre entitatile afiliate', 4, 'synthetic', '45'),
        ('453', 'Decontari privind interesele de participare', 4, 'synthetic', '45'),
        ('455', 'Sume datorate actionarilor/asociatilor', 4, 'synthetic', '45'),
        ('456', 'Decontari cu actionarii/asociatii privind capitalul', 4, 'synthetic', '45'),
        ('457', 'Dividende de plata', 4, 'synthetic', '45'),
        ('46', 'Debitori si creditori diversi', 4, 'group', '4'),
        ('461', 'Debitori diversi', 4, 'synthetic', '46'),
        ('462', 'Creditori diversi', 4, 'synthetic', '46'),
        ('47', 'Conturi de regularizare si asimilate', 4, 'group', '4'),
        ('471', 'Cheltuieli inregistrate in avans', 4, 'synthetic', '47'),
        ('472', 'Venituri inregistrate in avans', 4, 'synthetic', '47'),
        ('473', 'Decontari din operatii in curs de clarificare', 4, 'synthetic', '47'),
        ('475', 'Subventii pentru investitii', 4, 'synthetic', '47'),
        ('49', 'Ajustari pentru deprecierea creantelor', 4, 'group', '4'),
        ('491', 'Ajustari pentru deprecierea creantelor - clienti', 4, 'synthetic', '49'),
        ('495', 'Ajustari pentru deprecierea creantelor - decontari in cadrul grupului', 4, 'synthetic', '49'),
        ('496', 'Ajustari pentru deprecierea creantelor - debitori diversi', 4, 'synthetic', '49'),
        # ── Class 5: Trezorerie (Cash & Treasury) ──
        ('5', 'Conturi de trezorerie', 5, 'class', None),
        ('50', 'Investitii pe termen scurt', 5, 'group', '5'),
        ('501', 'Actiuni detinute la entitatile afiliate', 5, 'synthetic', '50'),
        ('505', 'Obligatiuni emise si rascumparate', 5, 'synthetic', '50'),
        ('506', 'Obligatiuni', 5, 'synthetic', '50'),
        ('508', 'Alte investitii pe termen scurt', 5, 'synthetic', '50'),
        ('509', 'Varsaminte de efectuat pentru investitii pe termen scurt', 5, 'synthetic', '50'),
        ('51', 'Conturi la banci', 5, 'group', '5'),
        ('511', 'Valori de incasat', 5, 'synthetic', '51'),
        ('512', 'Conturi curente la banci', 5, 'synthetic', '51'),
        ('519', 'Credite bancare pe termen scurt', 5, 'synthetic', '51'),
        ('53', 'Casa', 5, 'group', '5'),
        ('531', 'Casa', 5, 'synthetic', '53'),
        ('532', 'Alte valori', 5, 'synthetic', '53'),
        ('54', 'Acreditive', 5, 'group', '5'),
        ('541', 'Acreditive', 5, 'synthetic', '54'),
        ('542', 'Avansuri de trezorerie', 5, 'synthetic', '54'),
        ('58', 'Viramente interne', 5, 'group', '5'),
        ('581', 'Viramente interne', 5, 'synthetic', '58'),
        ('59', 'Ajustari pentru pierderea de valoare a investitiilor pe termen scurt', 5, 'group', '5'),
        ('591', 'Ajustari pentru pierderea de valoare a actiunilor', 5, 'synthetic', '59'),
        ('595', 'Ajustari pentru pierderea de valoare a obligatiunilor', 5, 'synthetic', '59'),
        ('596', 'Ajustari pentru pierderea de valoare a altor investitii', 5, 'synthetic', '59'),
        # ── Class 6: Cheltuieli (Expenses) ──
        ('6', 'Conturi de cheltuieli', 6, 'class', None),
        ('60', 'Cheltuieli privind stocurile', 6, 'group', '6'),
        ('601', 'Cheltuieli cu materiile prime', 6, 'synthetic', '60'),
        ('602', 'Cheltuieli cu materialele consumabile', 6, 'synthetic', '60'),
        ('603', 'Cheltuieli privind materialele de natura obiectelor de inventar', 6, 'synthetic', '60'),
        ('604', 'Cheltuieli privind materialele nestocate', 6, 'synthetic', '60'),
        ('605', 'Cheltuieli privind energia si apa', 6, 'synthetic', '60'),
        ('607', 'Cheltuieli privind marfurile', 6, 'synthetic', '60'),
        ('608', 'Cheltuieli privind ambalajele', 6, 'synthetic', '60'),
        ('609', 'Reduceri comerciale primite', 6, 'synthetic', '60'),
        ('61', 'Cheltuieli cu serviciile executate de terti', 6, 'group', '6'),
        ('611', 'Cheltuieli de intretinere si reparatii', 6, 'synthetic', '61'),
        ('612', 'Cheltuieli cu redeventele, locatiile de gestiune', 6, 'synthetic', '61'),
        ('613', 'Cheltuieli cu primele de asigurare', 6, 'synthetic', '61'),
        ('614', 'Cheltuieli cu studiile si cercetarile', 6, 'synthetic', '61'),
        ('62', 'Cheltuieli cu alte servicii executate de terti', 6, 'group', '6'),
        ('621', 'Cheltuieli cu colaboratorii', 6, 'synthetic', '62'),
        ('622', 'Cheltuieli privind comisioanele si onorariile', 6, 'synthetic', '62'),
        ('623', 'Cheltuieli de protocol, reclama si publicitate', 6, 'synthetic', '62'),
        ('624', 'Cheltuieli cu transportul de bunuri si personal', 6, 'synthetic', '62'),
        ('625', 'Cheltuieli cu deplasari, detasari si transferari', 6, 'synthetic', '62'),
        ('626', 'Cheltuieli postale si taxe de telecomunicatii', 6, 'synthetic', '62'),
        ('627', 'Cheltuieli cu serviciile bancare si asimilate', 6, 'synthetic', '62'),
        ('628', 'Alte cheltuieli cu serviciile executate de terti', 6, 'synthetic', '62'),
        ('63', 'Cheltuieli cu alte impozite, taxe', 6, 'group', '6'),
        ('635', 'Cheltuieli cu alte impozite, taxe si varsaminte asimilate', 6, 'synthetic', '63'),
        ('64', 'Cheltuieli cu personalul', 6, 'group', '6'),
        ('641', 'Cheltuieli cu salariile personalului', 6, 'synthetic', '64'),
        ('642', 'Cheltuieli cu tichetele de masa acordate salariatilor', 6, 'synthetic', '64'),
        ('645', 'Cheltuieli privind asigurarile si protectia sociala', 6, 'synthetic', '64'),
        ('646', 'Cheltuieli privind contributia asiguratorie pentru munca', 6, 'synthetic', '64'),
        ('65', 'Alte cheltuieli de exploatare', 6, 'group', '6'),
        ('654', 'Pierderi din creante si debitori diversi', 6, 'synthetic', '65'),
        ('655', 'Cheltuieli din reevaluarea imobilizarilor corporale', 6, 'synthetic', '65'),
        ('658', 'Alte cheltuieli de exploatare', 6, 'synthetic', '65'),
        ('66', 'Cheltuieli financiare', 6, 'group', '6'),
        ('663', 'Pierderi din creante legate de participatii', 6, 'synthetic', '66'),
        ('664', 'Cheltuieli privind investitiile financiare cedate', 6, 'synthetic', '66'),
        ('665', 'Cheltuieli din diferente de curs valutar', 6, 'synthetic', '66'),
        ('666', 'Cheltuieli privind dobanzile', 6, 'synthetic', '66'),
        ('667', 'Cheltuieli privind sconturile acordate', 6, 'synthetic', '66'),
        ('668', 'Alte cheltuieli financiare', 6, 'synthetic', '66'),
        ('68', 'Cheltuieli cu amortizarile, provizioanele si ajustarile', 6, 'group', '6'),
        ('681', 'Cheltuieli de exploatare privind amortizarile, provizioanele', 6, 'synthetic', '68'),
        ('686', 'Cheltuieli financiare privind amortizarile si ajustarile', 6, 'synthetic', '68'),
        ('69', 'Cheltuieli cu impozitul pe profit', 6, 'group', '6'),
        ('691', 'Cheltuieli cu impozitul pe profit', 6, 'synthetic', '69'),
        ('698', 'Cheltuieli cu impozitul pe venit si alte impozite', 6, 'synthetic', '69'),
        # ── Class 7: Venituri (Revenue) ──
        ('7', 'Conturi de venituri', 7, 'class', None),
        ('70', 'Cifra de afaceri neta', 7, 'group', '7'),
        ('701', 'Venituri din vanzarea produselor finite', 7, 'synthetic', '70'),
        ('702', 'Venituri din vanzarea semifabricatelor', 7, 'synthetic', '70'),
        ('703', 'Venituri din vanzarea produselor reziduale', 7, 'synthetic', '70'),
        ('704', 'Venituri din servicii prestate', 7, 'synthetic', '70'),
        ('705', 'Venituri din studii si cercetari', 7, 'synthetic', '70'),
        ('706', 'Venituri din redevente, locatii de gestiune', 7, 'synthetic', '70'),
        ('707', 'Venituri din vanzarea marfurilor', 7, 'synthetic', '70'),
        ('708', 'Venituri din activitati diverse', 7, 'synthetic', '70'),
        ('709', 'Reduceri comerciale acordate', 7, 'synthetic', '70'),
        ('71', 'Venituri aferente costului productiei in curs', 7, 'group', '7'),
        ('711', 'Venituri aferente costurilor stocurilor de produse', 7, 'synthetic', '71'),
        ('72', 'Venituri din productia de imobilizari', 7, 'group', '7'),
        ('721', 'Venituri din productia de imobilizari necorporale', 7, 'synthetic', '72'),
        ('722', 'Venituri din productia de imobilizari corporale', 7, 'synthetic', '72'),
        ('74', 'Venituri din subventii de exploatare', 7, 'group', '7'),
        ('741', 'Venituri din subventii de exploatare', 7, 'synthetic', '74'),
        ('75', 'Alte venituri din exploatare', 7, 'group', '7'),
        ('754', 'Venituri din creante reactivate si debitori diversi', 7, 'synthetic', '75'),
        ('755', 'Venituri din reevaluarea imobilizarilor corporale', 7, 'synthetic', '75'),
        ('758', 'Alte venituri din exploatare', 7, 'synthetic', '75'),
        ('76', 'Venituri financiare', 7, 'group', '7'),
        ('761', 'Venituri din imobilizari financiare', 7, 'synthetic', '76'),
        ('762', 'Venituri din investitii financiare pe termen scurt', 7, 'synthetic', '76'),
        ('763', 'Venituri din creante imobilizate', 7, 'synthetic', '76'),
        ('764', 'Venituri din investitii financiare cedate', 7, 'synthetic', '76'),
        ('765', 'Venituri din diferente de curs valutar', 7, 'synthetic', '76'),
        ('766', 'Venituri din dobanzi', 7, 'synthetic', '76'),
        ('767', 'Venituri din sconturi obtinute', 7, 'synthetic', '76'),
        ('768', 'Alte venituri financiare', 7, 'synthetic', '76'),
        ('78', 'Venituri din provizioane si ajustari', 7, 'group', '7'),
        ('781', 'Venituri din provizioane si ajustari de exploatare', 7, 'synthetic', '78'),
        ('786', 'Venituri financiare din ajustari', 7, 'synthetic', '78'),
        # ── Class 8: Conturi speciale ──
        ('8', 'Conturi speciale', 8, 'class', None),
        ('80', 'Conturi in afara bilantului', 8, 'group', '8'),
        # ── Class 9: Conturi de gestiune ──
        ('9', 'Conturi de gestiune', 9, 'class', None),
        ('90', 'Decontari interne', 9, 'group', '9'),
    ]
    for code, name, acls, atype, parent in accounts:
        cursor.execute('''
            INSERT INTO chart_of_accounts (code, name, account_class, account_type, parent_code, company_id)
            VALUES (%s, %s, %s, %s, %s, NULL)
        ''', (code, name, acls, atype, parent))
