from core.base_repository import BaseRepository


class CostCenterRepository(BaseRepository):

    def list_companies(self):
        return self.query_all("""
            SELECT c.id AS company_id, c.company, COUNT(cc.id) AS count
            FROM companies c
            LEFT JOIN cost_centers cc ON cc.company_id = c.id
            GROUP BY c.id, c.company
            ORDER BY c.company
        """)

    def list_by_company(self, company_id):
        return self.query_all("""
            SELECT cc.id, cc.company_id, cc.code, cc.name, cc.active, cc.display_order,
                   m.structure_node_id,
                   sn.name AS structure_node_name
            FROM cost_centers cc
            LEFT JOIN cost_center_structure_map m ON m.cost_center_id = cc.id
            LEFT JOIN structure_nodes sn ON sn.id = m.structure_node_id
            WHERE cc.company_id = %s
            ORDER BY cc.code
        """, (company_id,))

    def create(self, company_id, code, name):
        row = self.query_one(
            "INSERT INTO cost_centers (company_id, code, name) VALUES (%s, %s, %s) RETURNING id",
            (company_id, code.strip(), name.strip()),
        )
        return row['id'] if row else None

    def update(self, cc_id, code=None, name=None, active=None):
        sets, params = [], []
        if code is not None:
            sets.append('code = %s'); params.append(code.strip())
        if name is not None:
            sets.append('name = %s'); params.append(name.strip())
        if active is not None:
            sets.append('active = %s'); params.append(bool(active))
        if not sets:
            return
        sets.append('updated_at = NOW()')
        params.append(cc_id)
        self.execute(f"UPDATE cost_centers SET {', '.join(sets)} WHERE id = %s", tuple(params))

    def delete(self, cc_id):
        self.execute("DELETE FROM cost_centers WHERE id = %s", (cc_id,))  # cascades map row

    def list_structure_nodes(self, company_id):
        return self.query_all(
            "SELECT id, name, level FROM structure_nodes WHERE company_id = %s ORDER BY level, name",
            (company_id,),
        )

    def set_map(self, cc_id, structure_node_id):
        if structure_node_id is None:
            self.execute("DELETE FROM cost_center_structure_map WHERE cost_center_id = %s", (cc_id,))
            return
        self.execute("""
            INSERT INTO cost_center_structure_map (cost_center_id, structure_node_id)
            VALUES (%s, %s)
            ON CONFLICT (cost_center_id)
            DO UPDATE SET structure_node_id = EXCLUDED.structure_node_id
        """, (cc_id, int(structure_node_id)))

    def auto_seed_map_exact(self, company_id):
        """Map each still-unmapped cost center to the ONLY structure node in the
        same company whose name matches case-insensitively. Skips ambiguous/none."""
        rows = self.query_all("""
            SELECT cc.id AS cc_id,
                   (SELECT sn.id FROM structure_nodes sn
                     WHERE sn.company_id = cc.company_id
                       AND LOWER(sn.name) = LOWER(cc.name)
                     LIMIT 1) AS node_id,
                   (SELECT COUNT(*) FROM structure_nodes sn
                     WHERE sn.company_id = cc.company_id
                       AND LOWER(sn.name) = LOWER(cc.name)) AS match_count
            FROM cost_centers cc
            WHERE cc.company_id = %s
              AND NOT EXISTS (SELECT 1 FROM cost_center_structure_map m WHERE m.cost_center_id = cc.id)
        """, (company_id,))
        inserted = 0
        for r in rows:
            if r['match_count'] == 1 and r['node_id'] is not None:
                self.execute(
                    "INSERT INTO cost_center_structure_map (cost_center_id, structure_node_id) "
                    "VALUES (%s, %s) ON CONFLICT (cost_center_id) DO NOTHING",
                    (r['cc_id'], r['node_id']),
                )
                inserted += 1
        return inserted
