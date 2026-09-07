"""Repository for HR Divisions — a JARVIS overlay grouping Sincron departments
across companies with responsable(s). See
docs/superpowers/specs/2026-09-07-hr-divisions-design.md.
"""
from core.base_repository import BaseRepository


class DivisionRepository(BaseRepository):
    def list_divisions(self):
        """All divisions with their responsables and departments (aggregated)."""
        return self.query_all("""
            SELECT d.id, d.name,
                   COALESCE((
                       SELECT json_agg(json_build_object('id', u.id, 'name', u.name) ORDER BY u.name)
                       FROM hr_division_responsables r
                       JOIN users u ON u.id = r.user_id
                       WHERE r.division_id = d.id
                   ), '[]'::json) AS responsables,
                   COALESCE((
                       SELECT json_agg(json_build_object(
                                  'node_id', n.id, 'name', n.name,
                                  'company_id', n.company_id, 'company', c.company
                              ) ORDER BY c.company, n.name)
                       FROM hr_division_departments dd
                       JOIN sincron_org_nodes n ON n.id = dd.node_id
                       LEFT JOIN companies c ON c.id = n.company_id
                       WHERE dd.division_id = d.id
                   ), '[]'::json) AS departments
            FROM hr_divisions d
            ORDER BY d.name
        """)

    def get(self, division_id):
        return self.query_one("SELECT id, name FROM hr_divisions WHERE id = %s", (division_id,))

    def create(self, name):
        row = self.query_one("INSERT INTO hr_divisions (name) VALUES (%s) RETURNING id", (name,))
        return row['id'] if row else None

    def rename(self, division_id, name):
        self.execute("UPDATE hr_divisions SET name = %s, updated_at = NOW() WHERE id = %s",
                     (name, division_id))

    def delete(self, division_id):
        self.execute("DELETE FROM hr_divisions WHERE id = %s", (division_id,))  # cascades children

    def set_departments(self, division_id, node_ids):
        """Replace this division's departments. Nodes already owned by another
        division are skipped (UNIQUE node_id) — the picker disables those."""
        def _cb(cur):
            cur.execute("DELETE FROM hr_division_departments WHERE division_id = %s", (division_id,))
            for nid in node_ids:
                cur.execute(
                    "INSERT INTO hr_division_departments (division_id, node_id) "
                    "VALUES (%s, %s) ON CONFLICT (node_id) DO NOTHING",
                    (division_id, int(nid)),
                )
        self.execute_many(_cb)

    def set_responsables(self, division_id, user_ids):
        """Replace this division's responsables."""
        def _cb(cur):
            cur.execute("DELETE FROM hr_division_responsables WHERE division_id = %s", (division_id,))
            for uid in user_ids:
                cur.execute(
                    "INSERT INTO hr_division_responsables (division_id, user_id) "
                    "VALUES (%s, %s) ON CONFLICT (division_id, user_id) DO NOTHING",
                    (division_id, int(uid)),
                )
        self.execute_many(_cb)

    def available_departments(self):
        """All Sincron nodes for the picker, grouped-friendly (company + level),
        flagged with the division that already owns each node (if any)."""
        return self.query_all("""
            SELECT n.id AS node_id, n.name, n.level, n.node_type,
                   n.company_id, c.company,
                   dd.division_id AS taken_by_division_id
            FROM sincron_org_nodes n
            LEFT JOIN companies c ON c.id = n.company_id
            LEFT JOIN hr_division_departments dd ON dd.node_id = n.id
            ORDER BY c.company NULLS LAST, n.level, n.name
        """)
