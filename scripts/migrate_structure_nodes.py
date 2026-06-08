"""
Migrate department_structure → structure_nodes + structure_node_members.

Tree mapping:
  L1  = brand          (unique per company)
  L2  = department     (unique per company+brand)
  L3  = subdepartment  (unique per company+brand+department, only when present)

Responsables:
  manager_ids from old rows → structure_node_members.role = 'responsable'
  Assigned at the deepest level (L3 if subdept exists, else L2).
"""
import os
import sys
import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ['DATABASE_URL']

def migrate(conn):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # ── 0. Check if already migrated ────────────────────────────────────────
    cur.execute("SELECT COUNT(*) AS n FROM structure_nodes")
    if cur.fetchone()["n"] > 0:
        print("structure_nodes already has data — aborting to avoid duplicates.")
        print("Run with --force to truncate and re-migrate.")
        if "--force" not in sys.argv:
            return
        print("--force detected. Truncating structure_nodes and structure_node_members…")
        cur.execute("TRUNCATE structure_node_members, structure_nodes RESTART IDENTITY CASCADE")

    # ── 1. Load source data (distinct rows) ─────────────────────────────────
    cur.execute("""
        SELECT DISTINCT ON (company, brand, department, subdepartment)
            company, brand, department, subdepartment,
            manager_ids
        FROM department_structure
        WHERE company IS NOT NULL AND brand IS NOT NULL AND department IS NOT NULL
        ORDER BY company, brand, department, subdepartment
    """)
    rows = cur.fetchall()
    print(f"Source rows (distinct): {len(rows)}")

    # ── 2. Load company name → id map ────────────────────────────────────────
    cur.execute("SELECT id, company FROM companies")
    company_map = {r["company"]: r["id"] for r in cur.fetchall()}

    # ── 3. Build tree structure in memory ────────────────────────────────────
    # l1_key: (company_id, brand) → node_id
    # l2_key: (l1_id, department) → node_id
    # l3_key: (l2_id, subdepartment) → node_id
    l1_nodes = {}   # (company_id, brand) → node_id
    l2_nodes = {}   # (l1_id, department) → node_id
    l3_nodes = {}   # (l2_id, subdept) → node_id

    # members to insert: set of (node_id, user_id)
    members = {}    # (node_id, user_id) → 'responsable'

    skipped = []

    for row in rows:
        company_name = row["company"]
        brand = row["brand"]
        department = row["department"]
        subdept = row["subdepartment"]
        manager_ids = row["manager_ids"] or []

        company_id = company_map.get(company_name)
        if not company_id:
            skipped.append(f"No company_id for '{company_name}'")
            continue

        # ── L1: brand ────────────────────────────────────────────────────────
        l1_key = (company_id, brand)
        if l1_key not in l1_nodes:
            cur.execute(
                "INSERT INTO structure_nodes (company_id, parent_id, name, level, display_order) "
                "VALUES (%s, NULL, %s, 1, %s) RETURNING id",
                (company_id, brand, len(l1_nodes))
            )
            l1_nodes[l1_key] = cur.fetchone()["id"]
            print(f"  L1 created: [{company_name}] {brand}")
        l1_id = l1_nodes[l1_key]

        # ── L2: department ───────────────────────────────────────────────────
        l2_key = (l1_id, department)
        if l2_key not in l2_nodes:
            cur.execute(
                "INSERT INTO structure_nodes (company_id, parent_id, name, level, display_order) "
                "VALUES (%s, %s, %s, 2, %s) RETURNING id",
                (company_id, l1_id, department, len(l2_nodes))
            )
            l2_nodes[l2_key] = cur.fetchone()["id"]
            print(f"    L2 created: [{company_name}] {brand} → {department}")
        l2_id = l2_nodes[l2_key]

        # ── L3: subdepartment (optional) ─────────────────────────────────────
        target_node_id = l2_id
        if subdept:
            l3_key = (l2_id, subdept)
            if l3_key not in l3_nodes:
                cur.execute(
                    "INSERT INTO structure_nodes (company_id, parent_id, name, level, display_order) "
                    "VALUES (%s, %s, %s, 3, %s) RETURNING id",
                    (company_id, l2_id, subdept, len(l3_nodes))
                )
                l3_nodes[l3_key] = cur.fetchone()["id"]
                print(f"      L3 created: [{company_name}] {brand} → {department} → {subdept}")
            target_node_id = l3_nodes[l3_key]

        # ── Responsables from manager_ids ─────────────────────────────────────
        for uid in manager_ids:
            key = (target_node_id, uid)
            if key not in members:
                members[key] = "responsable"

    # ── 4. Insert members ────────────────────────────────────────────────────
    inserted_members = 0
    for (node_id, user_id), role in members.items():
        try:
            cur.execute(
                "INSERT INTO structure_node_members (node_id, user_id, role) "
                "VALUES (%s, %s, %s) ON CONFLICT (node_id, user_id) DO NOTHING",
                (node_id, user_id, role)
            )
            inserted_members += 1
        except Exception as e:
            print(f"  Warning: member ({node_id}, {user_id}) skipped: {e}")
            conn.rollback()

    conn.commit()

    print(f"\n✅ Migration complete:")
    print(f"   L1 nodes (brands):        {len(l1_nodes)}")
    print(f"   L2 nodes (departments):   {len(l2_nodes)}")
    print(f"   L3 nodes (subdepts):      {len(l3_nodes)}")
    print(f"   Members inserted:         {inserted_members}")
    if skipped:
        print(f"   Skipped rows:")
        for s in skipped:
            print(f"     - {s}")


if __name__ == "__main__":
    conn = psycopg2.connect(DATABASE_URL)
    try:
        migrate(conn)
    finally:
        conn.close()
