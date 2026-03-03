"""Structure Node Repository - Generic tree-based organizational structure.

Supports up to 5 levels of nesting under each company.
"""
from typing import Optional

from core.base_repository import BaseRepository


class StructureNodeRepository(BaseRepository):
    """Repository for generic structure nodes (tree hierarchy)."""

    TABLE = 'structure_nodes'

    def get_all(self) -> list[dict]:
        """Get all structure nodes across all companies."""
        return self.query_all(
            'SELECT * FROM structure_nodes ORDER BY company_id, display_order, name'
        )

    def get_by_company(self, company_id: int) -> list[dict]:
        """Get all structure nodes for a specific company."""
        return self.query_all(
            'SELECT * FROM structure_nodes WHERE company_id = %s ORDER BY display_order, name',
            (company_id,)
        )

    # ── Dropdown helpers (for invoice allocation editor) ──

    def get_company_names(self) -> list[str]:
        """Get all company names that have structure nodes defined."""
        rows = self.query_all('''
            SELECT DISTINCT c.company
            FROM companies c
            JOIN structure_nodes sn ON sn.company_id = c.id
            ORDER BY c.company
        ''')
        return [r['company'] for r in rows]

    def get_l1_names(self, company_name: str) -> list[str]:
        """Get L1 (brand-level) node names for a company."""
        rows = self.query_all('''
            SELECT DISTINCT sn.name
            FROM structure_nodes sn
            JOIN companies c ON sn.company_id = c.id
            WHERE c.company = %s AND sn.level = 1
            ORDER BY sn.name
        ''', (company_name,))
        return [r['name'] for r in rows]

    def get_l2_names(self, company_name: str, level1_name: str = None) -> list[str]:
        """Get L2 node names for a company, optionally filtered by parent L1."""
        if level1_name:
            rows = self.query_all('''
                SELECT DISTINCT l2.name
                FROM structure_nodes l2
                JOIN structure_nodes l1 ON l2.parent_id = l1.id
                JOIN companies c ON l2.company_id = c.id
                WHERE c.company = %s AND l1.level = 1 AND lower(l1.name) = lower(%s) AND l2.level = 2
                ORDER BY l2.name
            ''', (company_name, level1_name))
        else:
            rows = self.query_all('''
                SELECT DISTINCT sn.name
                FROM structure_nodes sn
                JOIN companies c ON sn.company_id = c.id
                WHERE c.company = %s AND sn.level = 2
                ORDER BY sn.name
            ''', (company_name,))
        return [r['name'] for r in rows]

    def get_l3_names(self, company_name: str, department: str) -> list[str]:
        """Get L3 (subdepartment-level) node names under a given L2 department."""
        rows = self.query_all('''
            SELECT DISTINCT child.name
            FROM structure_nodes child
            JOIN structure_nodes parent ON child.parent_id = parent.id
            JOIN companies c ON child.company_id = c.id
            WHERE c.company = %s
              AND parent.level = 2
              AND lower(parent.name) = lower(%s)
              AND child.level = 3
            ORDER BY child.name
        ''', (company_name, department))
        return [r['name'] for r in rows]

    def get(self, node_id: int) -> Optional[dict]:
        """Get a specific node by ID."""
        return self.query_one('SELECT * FROM structure_nodes WHERE id = %s', (node_id,))

    def create(self, company_id: int, name: str, parent_id: int = None) -> int:
        """Create a new structure node. Returns node ID.

        Level is auto-computed: root nodes = 1, children = parent.level + 1.
        Enforces max 5 levels.
        """
        if parent_id:
            parent = self.query_one('SELECT level FROM structure_nodes WHERE id = %s', (parent_id,))
            if not parent:
                raise ValueError('Parent node not found')
            level = parent['level'] + 1
            if level > 5:
                raise ValueError('Maximum nesting depth (5 levels) reached')
        else:
            level = 1

        result = self.execute('''
            INSERT INTO structure_nodes (company_id, parent_id, name, level)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        ''', (company_id, parent_id, name, level), returning=True)
        return result['id']

    def update(self, node_id: int, name: str) -> bool:
        """Rename a structure node."""
        return self.execute(
            'UPDATE structure_nodes SET name = %s WHERE id = %s',
            (name, node_id)
        ) > 0

    def delete(self, node_id: int) -> bool:
        """Delete a structure node. CASCADE removes children."""
        return self.execute(
            'DELETE FROM structure_nodes WHERE id = %s', (node_id,)
        ) > 0

    def update_has_team(self, node_id: int, has_team: bool) -> bool:
        """Toggle the has_team flag on a node."""
        return self.execute(
            'UPDATE structure_nodes SET has_team = %s WHERE id = %s',
            (has_team, node_id)
        ) > 0

    def reorder(self, node_id: int, display_order: int) -> bool:
        """Update display order for a node."""
        return self.execute(
            'UPDATE structure_nodes SET display_order = %s WHERE id = %s',
            (display_order, node_id)
        ) > 0

    # ── Member management ──

    def get_all_members(self) -> list[dict]:
        """Get all members across all nodes (bulk load for frontend)."""
        return self.query_all('''
            SELECT snm.id, snm.node_id, snm.user_id, snm.role,
                   u.name AS user_name, u.email AS user_email
            FROM structure_node_members snm
            JOIN users u ON snm.user_id = u.id
            ORDER BY snm.node_id, snm.role, u.name
        ''')

    def add_member(self, node_id: int, user_id: int, role: str = 'team') -> int:
        """Add a user to a node. Returns member row ID."""
        if role not in ('responsable', 'team'):
            raise ValueError('role must be "responsable" or "team"')
        result = self.execute('''
            INSERT INTO structure_node_members (node_id, user_id, role)
            VALUES (%s, %s, %s)
            ON CONFLICT (node_id, user_id) DO UPDATE SET role = EXCLUDED.role
            RETURNING id
        ''', (node_id, user_id, role), returning=True)
        return result['id']

    def remove_member(self, node_id: int, user_id: int) -> bool:
        """Remove a user from a node."""
        return self.execute(
            'DELETE FROM structure_node_members WHERE node_id = %s AND user_id = %s',
            (node_id, user_id)
        ) > 0

    def set_members(self, node_id: int, role: str, user_ids: list[int]) -> None:
        """Atomic replace: delete all members of role, insert new list."""
        if role not in ('responsable', 'team'):
            raise ValueError('role must be "responsable" or "team"')

        def _work(cursor):
            cursor.execute(
                'DELETE FROM structure_node_members WHERE node_id = %s AND role = %s',
                (node_id, role)
            )
            for uid in user_ids:
                cursor.execute('''
                    INSERT INTO structure_node_members (node_id, user_id, role)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (node_id, user_id) DO UPDATE SET role = EXCLUDED.role
                ''', (node_id, uid, role))
        self.execute_many(_work)

    def find_node_by_path(self, company_id: int, names: list[str]) -> Optional[dict]:
        """Walk the tree matching a path of node names (e.g. ['Volkswagen', 'Sales']).

        Returns the deepest matched node, or None if the path doesn't match.
        """
        if not names:
            return None
        nodes = self.get_by_company(company_id)

        # Build parent→children lookup
        children_of: dict = {}
        for n in nodes:
            pid = n['parent_id']
            children_of.setdefault(pid, []).append(n)

        # Walk the path level by level
        current_parent = None
        matched_node = None
        for name in names:
            candidates = children_of.get(current_parent, [])
            found = next((c for c in candidates if c['name'].lower() == name.lower()), None)
            if not found:
                break
            matched_node = found
            current_parent = found['id']

        return matched_node

    def get_node_responsable_names(self, node_id: int) -> str:
        """Get comma-separated responsable names for a node (no fallback)."""
        rows = self.query_all('''
            SELECT u.name
            FROM structure_node_members snm
            JOIN users u ON snm.user_id = u.id
            WHERE snm.node_id = %s AND snm.role = 'responsable'
            ORDER BY u.name
        ''', (node_id,))
        return ', '.join(r['name'] for r in rows)

    def get_node_responsable_names_with_fallback(self, node_id: int, company_id: int) -> str:
        """Get responsable names, walking up ancestors if none at current level,
        then falling back to company_responsables (L0)."""
        rows = self.query_all('''
            WITH RECURSIVE ancestors AS (
                SELECT id, parent_id, 0 AS depth
                FROM structure_nodes WHERE id = %s
                UNION ALL
                SELECT sn.id, sn.parent_id, a.depth + 1
                FROM structure_nodes sn
                JOIN ancestors a ON sn.id = a.parent_id
            ),
            ranked AS (
                SELECT u.name, a.depth,
                       MIN(a.depth) OVER () AS min_depth
                FROM ancestors a
                JOIN structure_node_members snm ON snm.node_id = a.id
                JOIN users u ON u.id = snm.user_id
                WHERE snm.role = 'responsable'
            )
            SELECT name FROM ranked WHERE depth = min_depth ORDER BY name
        ''', (node_id,))
        if rows:
            return ', '.join(r['name'] for r in rows)
        # Fall back to company-level responsables
        comp_rows = self.query_all('''
            SELECT u.name FROM company_responsables cr
            JOIN users u ON u.id = cr.user_id
            WHERE cr.company_id = %s ORDER BY u.name
        ''', (company_id,))
        return ', '.join(r['name'] for r in comp_rows)

    def get_node_responsable_users_with_fallback(self, node_id: int, company_id: int) -> list[dict]:
        """Get responsable user dicts, walking up ancestors if none at current level,
        then falling back to company_responsables (L0)."""
        rows = self.query_all('''
            WITH RECURSIVE ancestors AS (
                SELECT id, parent_id, 0 AS depth
                FROM structure_nodes WHERE id = %s
                UNION ALL
                SELECT sn.id, sn.parent_id, a.depth + 1
                FROM structure_nodes sn
                JOIN ancestors a ON sn.id = a.parent_id
            ),
            ranked AS (
                SELECT u.id, u.name, u.email, u.phone,
                       u.department, u.subdepartment, u.company, u.brand,
                       u.notify_on_allocation, u.is_active,
                       a.depth,
                       MIN(a.depth) OVER () AS min_depth
                FROM ancestors a
                JOIN structure_node_members snm ON snm.node_id = a.id
                JOIN users u ON u.id = snm.user_id
                WHERE snm.role = 'responsable' AND u.is_active = TRUE
            )
            SELECT DISTINCT id, name, email, phone, department, subdepartment,
                   company, brand, notify_on_allocation, is_active
            FROM ranked WHERE depth = min_depth
        ''', (node_id,))
        if rows:
            return [dict(r) for r in rows]
        # Fall back to company-level responsables
        return self.query_all('''
            SELECT DISTINCT u.id, u.name, u.email, u.phone,
                   u.department, u.subdepartment, u.company, u.brand,
                   u.notify_on_allocation, u.is_active
            FROM company_responsables cr
            JOIN users u ON u.id = cr.user_id
            WHERE cr.company_id = %s AND u.is_active = TRUE
            ORDER BY u.name
        ''', (company_id,))

    def find_responsable_by_path(self, company_name: str, brand: str = None,
                                  department: str = None, subdepartment: str = None) -> str:
        """Find the responsable for a given company/brand/department/subdepartment path.

        Walks the tree to the deepest matched node, then applies fallback:
        if no responsable at that level, walks up ancestors, then company (L0).
        """
        row = self.query_one(
            'SELECT id FROM companies WHERE company = %s', (company_name,)
        )
        if not row:
            return ''
        company_id = row['id']

        path = [n for n in [brand, department, subdepartment] if n]
        if not path:
            # No path — return company-level responsables
            comp_rows = self.query_all('''
                SELECT u.name FROM company_responsables cr
                JOIN users u ON u.id = cr.user_id
                WHERE cr.company_id = %s ORDER BY u.name
            ''', (company_id,))
            return ', '.join(r['name'] for r in comp_rows)

        node = self.find_node_by_path(company_id, path)
        if not node:
            return ''

        return self.get_node_responsable_names_with_fallback(node['id'], company_id)

    def get_responsable_users_by_department(self, company_name: str, department: str) -> list[dict]:
        """Find responsable users for nodes named `department` under a company,
        with fallback: if no responsable at that node, walk up ancestors, then company (L0).
        """
        # Find company_id
        comp_row = self.query_one('SELECT id FROM companies WHERE company = %s', (company_name,))
        if not comp_row:
            return []
        company_id = comp_row['id']

        # Find all nodes matching the department name under this company
        nodes = self.query_all('''
            SELECT sn.id FROM structure_nodes sn
            JOIN companies c ON sn.company_id = c.id
            WHERE c.company = %s AND lower(sn.name) = lower(%s)
        ''', (company_name, department))

        if not nodes:
            # Fall back to company-level responsables
            return self.query_all('''
                SELECT DISTINCT u.id, u.name, u.email, u.phone,
                       u.department, u.subdepartment, u.company, u.brand,
                       u.notify_on_allocation, u.is_active
                FROM company_responsables cr
                JOIN users u ON u.id = cr.user_id
                WHERE cr.company_id = %s AND u.is_active = TRUE
                ORDER BY u.name
            ''', (company_id,))

        # For each matching node, apply fallback up the ancestor chain
        seen_ids: set = set()
        results = []
        for node in nodes:
            users = self.get_node_responsable_users_with_fallback(node['id'], company_id)
            for u in users:
                if u['id'] not in seen_ids:
                    seen_ids.add(u['id'])
                    results.append(u)
        return results

    def get_cascade_responsable_ids(self, node_id: int) -> list[int]:
        """Walk UP the parent chain collecting all responsable user_ids."""
        return [r['user_id'] for r in self.query_all('''
            WITH RECURSIVE ancestors AS (
                SELECT id, parent_id FROM structure_nodes WHERE id = %s
                UNION ALL
                SELECT sn.id, sn.parent_id
                FROM structure_nodes sn
                JOIN ancestors a ON sn.id = a.parent_id
            )
            SELECT DISTINCT snm.user_id
            FROM ancestors a
            JOIN structure_node_members snm ON snm.node_id = a.id
            WHERE snm.role = 'responsable'
        ''', (node_id,))]
