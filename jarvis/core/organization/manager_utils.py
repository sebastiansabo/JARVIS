"""Organigram query functions — manager visibility.

Lives in core/ so that core.organization.hr_utils can import without
crossing the core→hr layer boundary.
"""
from database import get_db, get_cursor, release_db


def get_managed_employee_ids(manager_user_id, node_id=None):
    """Get all user IDs that are team members under this user in the organigram.

    Hierarchical cascading visibility:
      - L0 (company_responsables): sees ALL users in that company
      - L1 responsable: sees team members on L1 and all descendant nodes (L2-L5)
      - L2 responsable: sees team on L2 and descendants (L3-L5)
      - ...and so on

    If node_id is given, only returns team members under that specific node
    (must be within the user's visibility scope).

    Uses recursive CTE to walk DOWN the tree from the responsable's node(s).
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        if node_id:
            # Filter to a specific node and its descendants
            cursor.execute("""
                WITH RECURSIVE descendants AS (
                    SELECT id FROM structure_nodes WHERE id = %s
                    UNION ALL
                    SELECT sn.id FROM structure_nodes sn JOIN descendants d ON sn.parent_id = d.id
                )
                SELECT DISTINCT snm.user_id
                FROM descendants d
                JOIN structure_node_members snm ON snm.node_id = d.id AND snm.role = 'team'
                WHERE snm.user_id != %s
            """, (node_id, manager_user_id))
            ids = [r['user_id'] for r in cursor.fetchall()]
            return ids

        # No filter — return all visible employees

        # 1) Check L0: company_responsables → all users in that company
        #    PLUS all structure tree members (L1-L5) under those companies
        l0_ids = []
        try:
            cursor.execute("""
                WITH RECURSIVE l0_companies AS (
                    SELECT cr.company_id
                    FROM company_responsables cr
                    WHERE cr.user_id = %s
                ),
                -- Users matched by company name
                company_users AS (
                    SELECT DISTINCT u.id AS user_id
                    FROM l0_companies lc
                    JOIN companies c ON c.id = lc.company_id
                    JOIN users u ON u.company_id = c.id AND u.is_active = TRUE
                    WHERE u.id != %s
                ),
                -- Structure tree members under L0 companies (L1→L5 cascade)
                company_nodes AS (
                    SELECT sn.id
                    FROM l0_companies lc
                    JOIN structure_nodes sn ON sn.company_id = lc.company_id
                ),
                tree_descendants AS (
                    SELECT id FROM company_nodes
                    UNION ALL
                    SELECT sn.id FROM structure_nodes sn JOIN tree_descendants td ON sn.parent_id = td.id
                ),
                structure_users AS (
                    SELECT DISTINCT snm.user_id
                    FROM tree_descendants td
                    JOIN structure_node_members snm ON snm.node_id = td.id AND snm.role = 'team'
                    WHERE snm.user_id != %s
                )
                SELECT user_id FROM company_users
                UNION
                SELECT user_id FROM structure_users
            """, (manager_user_id, manager_user_id, manager_user_id))
            l0_ids = [r['user_id'] for r in cursor.fetchall()]
        except Exception:
            # Table may not exist yet — skip L0
            conn.rollback()

        # 2) Recursive descent from responsable nodes → all descendant team members
        cursor.execute("""
            WITH RECURSIVE resp_nodes AS (
                SELECT sn.id
                FROM structure_node_members snm
                JOIN structure_nodes sn ON sn.id = snm.node_id
                WHERE snm.user_id = %s AND snm.role = 'responsable'
            ),
            descendants AS (
                SELECT id FROM resp_nodes
                UNION ALL
                SELECT sn.id FROM structure_nodes sn JOIN descendants d ON sn.parent_id = d.id
            )
            SELECT DISTINCT snm.user_id
            FROM descendants d
            JOIN structure_node_members snm ON snm.node_id = d.id AND snm.role = 'team'
            WHERE snm.user_id != %s
        """, (manager_user_id, manager_user_id))
        tree_ids = [r['user_id'] for r in cursor.fetchall()]

        return list(set(l0_ids + tree_ids))


    finally:
        release_db(conn)


def get_visible_tree(manager_user_id):
    """Get the organigram tree visible to this manager for filtering.

    Returns a flat list of nodes (with parent_id for building the tree in the frontend).
    Includes:
      - L0: companies (if user is in company_responsables)
      - All nodes where user is responsable + their descendants
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        # L0 companies
        l0_companies = []
        try:
            cursor.execute("""
                SELECT c.id, c.company as name, 0 as level
                FROM company_responsables cr
                JOIN companies c ON c.id = cr.company_id
                WHERE cr.user_id = %s
            """, (manager_user_id,))
            l0_companies = [{'id': f'company-{r["id"]}', 'name': r['name'], 'level': 0,
                             'parent_id': None, 'company_id': r['id']}
                            for r in cursor.fetchall()]
        except Exception:
            conn.rollback()

        # Get all visible nodes via recursive descent
        cursor.execute("""
            WITH RECURSIVE resp_nodes AS (
                SELECT sn.id
                FROM structure_node_members snm
                JOIN structure_nodes sn ON sn.id = snm.node_id
                WHERE snm.user_id = %s AND snm.role = 'responsable'
            ),
            descendants AS (
                SELECT id FROM resp_nodes
                UNION ALL
                SELECT sn.id FROM structure_nodes sn JOIN descendants d ON sn.parent_id = d.id
            )
            SELECT DISTINCT sn.id, sn.name, sn.level, sn.parent_id, sn.company_id
            FROM descendants d
            JOIN structure_nodes sn ON sn.id = d.id
            ORDER BY sn.level, sn.name
        """, (manager_user_id,))
        nodes = [{'id': r['id'], 'name': r['name'], 'level': r['level'],
                  'parent_id': r['parent_id'], 'company_id': r['company_id']}
                 for r in cursor.fetchall()]

        return {'companies': l0_companies, 'nodes': nodes}


    finally:
        release_db(conn)


def is_manager(user_id):
    """True if the user is a Sincron organigram responsable or a company_responsables (L0)."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        # (a) Sincron responsable via mapped user
        cursor.execute("""
            SELECT 1
            FROM sincron_org_members som
            JOIN sincron_employees se
              ON se.sincron_employee_id = som.sincron_employee_id
             AND se.company_name = som.company_name
            WHERE se.mapped_jarvis_user_id = %s AND se.is_active = TRUE
              AND som.role = 'responsable'
            LIMIT 1
        """, (user_id,))
        if cursor.fetchone():
            return True
        # (b) L0 (unchanged)
        try:
            cursor.execute("SELECT 1 FROM company_responsables WHERE user_id = %s LIMIT 1", (user_id,))
            return cursor.fetchone() is not None
        except Exception:
            conn.rollback()
            return False
    finally:
        release_db(conn)
