"""JARVIS Parc (Logistics / Yard-Ops) schema — Task 1 of the spine plan.

See docs/superpowers/specs/2026-11-27-jarvis-parc-design.md §3 "Core domain
model" for the field list and enumerations this mirrors.

Tables (creation order respects FK dependencies):
  logistics_locations       — physical yard locations (name, code)
  logistics_positions       — bays within a location (A-01, Rampă 1, Atelier…)
  logistics_vehicles        — the stock register (order_ref = identity)
  logistics_intake_events   — raw jarvis-alpha event log (idempotency/ordering)
  logistics_tasks           — Kanban cards (one per unit of work on a car)
  logistics_vehicle_history — audit trail (every state change)
  logistics_mapping_rules   — event -> action rules (Reguli Dispo)

Every table carries `company_id` (independent module, shared Postgres,
company_id-scoped per §5 of the design spec). `CREATE TABLE IF NOT EXISTS`
throughout — safe to re-run on every app boot (database.init_db()).
"""


def create_schema_logistics(conn, cursor):
    """Create all JARVIS Parc (logistics) module tables and indexes."""

    # ── Locations (must exist before vehicles/positions FK) ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logistics_locations (
            id SERIAL PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            code VARCHAR(20) NOT NULL UNIQUE,
            company_id INTEGER,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ── Positions (bays within a location: A-01, Rampă 1, Atelier…) ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logistics_positions (
            id SERIAL PRIMARY KEY,
            location_id INTEGER NOT NULL REFERENCES logistics_locations(id) ON DELETE CASCADE,
            code VARCHAR(30) NOT NULL,
            company_id INTEGER,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (location_id, code)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_lpos_location ON logistics_positions(location_id)')

    # ── Vehicles: the stock register. order_ref (AW-####) is identity — the
    # dedup key the intake pipeline (Task 2) matches "same order delivered
    # twice" against. ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logistics_vehicles (
            id SERIAL PRIMARY KEY,

            order_ref VARCHAR(50) NOT NULL UNIQUE,
            vin VARCHAR(17),
            model VARCHAR(200),
            plate VARCHAR(20),
            destinatie VARCHAR(20),

            location_id INTEGER REFERENCES logistics_locations(id),
            position_id INTEGER REFERENCES logistics_positions(id),

            etapa_parc VARCHAR(20) NOT NULL DEFAULT 'În tranzit',
            predare VARCHAR(30) NOT NULL DEFAULT 'În așteptare',

            eta TIMESTAMP,
            arrived_at TIMESTAMP,

            -- Fields a human has confirmed (bay, VIN, keys, condition…) at
            -- Recepție — authoritative over the feed per §2 acceptance test 3:
            -- a later *older* intake event must not overwrite these.
            confirmed_fields JSONB NOT NULL DEFAULT '{}',

            -- Monotonic event timestamp/sequence of the last intake event
            -- applied to this vehicle — the stale-event ordering guard.
            last_event_ts BIGINT,

            company_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_lveh_company ON logistics_vehicles(company_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_lveh_etapa ON logistics_vehicles(etapa_parc)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_lveh_location ON logistics_vehicles(location_id)')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_lveh_vin ON logistics_vehicles(vin) WHERE vin IS NOT NULL")

    # ── Intake events: the raw jarvis-alpha event log. Not FK'd to a vehicle
    # (an event for an order that doesn't have a vehicle row yet is still
    # logged) — matched back to a vehicle by order_ref at processing time
    # (Task 2). ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logistics_intake_events (
            id SERIAL PRIMARY KEY,
            order_ref VARCHAR(50) NOT NULL,
            code VARCHAR(100) NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}',
            event_ts BIGINT NOT NULL,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            result VARCHAR(20),
            company_id INTEGER
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_lie_order_ref ON logistics_intake_events(order_ref)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_lie_event_ts ON logistics_intake_events(event_ts)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_lie_code ON logistics_intake_events(code)')

    # ── Tasks: Kanban cards, one per unit of work on a car. ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logistics_tasks (
            id SERIAL PRIMARY KEY,
            vehicle_id INTEGER NOT NULL REFERENCES logistics_vehicles(id) ON DELETE CASCADE,

            action TEXT NOT NULL,
            type VARCHAR(20) NOT NULL,

            location_id INTEGER REFERENCES logistics_locations(id),
            position_id INTEGER REFERENCES logistics_positions(id),

            assignee VARCHAR(100),
            due_at TIMESTAMP,
            status VARCHAR(20) NOT NULL DEFAULT 'De făcut',

            -- Move-gate fields (→ Blocat requires both; §4.2)
            block_reason TEXT,
            block_next_action TEXT,

            -- Move-gate field (Îngrijire/battery checks before Finalizat; §4.2)
            measured_result JSONB,

            -- The intake event that created/last touched this task, if any
            -- (so an ETA-update event can be traced back to the task it moved).
            source_event_id INTEGER REFERENCES logistics_intake_events(id) ON DELETE SET NULL,

            company_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ltask_vehicle ON logistics_tasks(vehicle_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ltask_status ON logistics_tasks(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ltask_type ON logistics_tasks(type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ltask_company ON logistics_tasks(company_id)')

    # ── Vehicle history: audit trail, one row per state change. ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logistics_vehicle_history (
            id SERIAL PRIMARY KEY,
            vehicle_id INTEGER NOT NULL REFERENCES logistics_vehicles(id) ON DELETE CASCADE,
            event_type VARCHAR(50) NOT NULL,
            old_value JSONB,
            new_value JSONB,
            actor VARCHAR(100),
            company_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_lvh_vehicle ON logistics_vehicle_history(vehicle_id)')

    # ── Mapping rules: event -> action rules (Setări → Reguli / "Reguli
    # Dispo"), versioned (rev) with a Simulare/Activ mode. ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logistics_mapping_rules (
            id SERIAL PRIMARY KEY,
            trigger_code VARCHAR(100) NOT NULL,
            actions JSONB NOT NULL DEFAULT '{}',
            rev INTEGER NOT NULL DEFAULT 1,
            mode VARCHAR(20) NOT NULL DEFAULT 'Simulare',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            company_id INTEGER,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_lmr_trigger ON logistics_mapping_rules(trigger_code)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_lmr_active ON logistics_mapping_rules(is_active, mode)')

    conn.commit()
