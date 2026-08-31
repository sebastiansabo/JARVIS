"""Organigram query functions — manager visibility.

Lives in core/ so that core.organization.hr_utils can import without
crossing the core→hr layer boundary.
"""
from database import get_db, get_cursor, release_db
from core.organization.ghost import hidden_ghost_ids


def _node_in_scope(cursor, manager_user_id, node_id):
    """True if node_id is within the caller's visibility: a descendant of one of
    their Sincron responsable nodes, OR any node in a company they are L0
    (company_responsables) for."""
    cursor.execute("""
        WITH RECURSIVE resp_nodes AS (
            SELECT som.node_id AS id
            FROM sincron_org_members som
            JOIN sincron_employees se
              ON se.sincron_employee_id = som.sincron_employee_id AND se.company_name = som.company_name
            WHERE se.mapped_jarvis_user_id = %s AND se.is_active = TRUE AND som.role = 'responsable'
        ),
        descendants AS (
            SELECT id FROM resp_nodes
            UNION ALL
            SELECT sn.id FROM sincron_org_nodes sn JOIN descendants d ON sn.parent_id = d.id
        )
        SELECT 1 FROM descendants WHERE id = %s LIMIT 1
    """, (manager_user_id, node_id))
    if cursor.fetchone():
        return True
    try:
        cursor.execute("""
            SELECT 1 FROM sincron_org_nodes n
            JOIN company_responsables cr ON cr.company_id = n.company_id
            WHERE n.id = %s AND cr.user_id = %s LIMIT 1
        """, (node_id, manager_user_id))
        return cursor.fetchone() is not None
    except Exception:
        return False


def get_managed_employee_ids(manager_user_id, node_id=None):
    """User IDs of team members under this user in the SINCRON organigram.

    L0 (company_responsables) sees the whole company; a Sincron responsable
    sees `member`s on their node + all descendants (via mapped_jarvis_user_id).
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        if node_id:
            if not _node_in_scope(cursor, manager_user_id, node_id):
                return []
            cursor.execute("""
                WITH RECURSIVE descendants AS (
                    SELECT id FROM sincron_org_nodes WHERE id = %s
                    UNION ALL
                    SELECT sn.id FROM sincron_org_nodes sn JOIN descendants d ON sn.parent_id = d.id
                )
                SELECT DISTINCT se.mapped_jarvis_user_id AS user_id
                FROM descendants d
                JOIN sincron_org_members m ON m.node_id = d.id AND m.role = 'member'
                JOIN sincron_employees se
                  ON se.sincron_employee_id = m.sincron_employee_id AND se.company_name = m.company_name
                WHERE se.mapped_jarvis_user_id IS NOT NULL AND se.is_active = TRUE
                  AND se.mapped_jarvis_user_id <> %s
            """, (node_id, manager_user_id))
            rows = [r['user_id'] for r in cursor.fetchall()]
            hidden = hidden_ghost_ids(manager_user_id)
            return [uid for uid in rows if uid not in hidden] if hidden else rows

        # 1) L0 (unchanged): whole company
        l0_ids = []
        try:
            cursor.execute("""
                SELECT DISTINCT u.id AS user_id
                FROM company_responsables cr
                JOIN users u ON u.company_id = cr.company_id AND u.is_active = TRUE
                WHERE cr.user_id = %s AND u.id <> %s
            """, (manager_user_id, manager_user_id))
            l0_ids = [r['user_id'] for r in cursor.fetchall()]
        except Exception:
            conn.rollback()

        # 2) Sincron tree descent from the caller's responsable nodes
        cursor.execute("""
            WITH RECURSIVE resp_nodes AS (
                SELECT som.node_id AS id
                FROM sincron_org_members som
                JOIN sincron_employees se
                  ON se.sincron_employee_id = som.sincron_employee_id AND se.company_name = som.company_name
                WHERE se.mapped_jarvis_user_id = %s AND se.is_active = TRUE AND som.role = 'responsable'
            ),
            descendants AS (
                SELECT id FROM resp_nodes
                UNION ALL
                SELECT sn.id FROM sincron_org_nodes sn JOIN descendants d ON sn.parent_id = d.id
            )
            SELECT DISTINCT se.mapped_jarvis_user_id AS user_id
            FROM descendants d
            JOIN sincron_org_members m ON m.node_id = d.id AND m.role = 'member'
            JOIN sincron_employees se
              ON se.sincron_employee_id = m.sincron_employee_id AND se.company_name = m.company_name
            WHERE se.mapped_jarvis_user_id IS NOT NULL AND se.is_active = TRUE
              AND se.mapped_jarvis_user_id <> %s
        """, (manager_user_id, manager_user_id))
        tree_ids = [r['user_id'] for r in cursor.fetchall()]

        result = list(set(l0_ids + tree_ids))
        hidden = hidden_ghost_ids(manager_user_id)
        if hidden:
            result = [uid for uid in result if uid not in hidden]
        return result
    finally:
        release_db(conn)


def get_visible_tree(manager_user_id):
    """Organigram tree visible to this manager (for filtering), from the Sincron organigram.

    Returns L0 companies (company_responsables, unchanged) + the caller's Sincron
    responsable node(s) and their descendants as a flat node list.
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        # L0 companies (UNCHANGED)
        l0_companies = []
        try:
            cursor.execute("""
                SELECT c.id, c.company AS name, 0 AS level
                FROM company_responsables cr
                JOIN companies c ON c.id = cr.company_id
                WHERE cr.user_id = %s
            """, (manager_user_id,))
            l0_companies = [{'id': f'company-{r["id"]}', 'name': r['name'], 'level': 0,
                             'parent_id': None, 'company_id': r['id']}
                            for r in cursor.fetchall()]
        except Exception:
            conn.rollback()

        # Sincron nodes: caller's responsable node(s) + descendants
        cursor.execute("""
            WITH RECURSIVE resp_nodes AS (
                SELECT som.node_id AS id
                FROM sincron_org_members som
                JOIN sincron_employees se
                  ON se.sincron_employee_id = som.sincron_employee_id AND se.company_name = som.company_name
                WHERE se.mapped_jarvis_user_id = %s AND se.is_active = TRUE AND som.role = 'responsable'
            ),
            descendants AS (
                SELECT id FROM resp_nodes
                UNION ALL
                SELECT sn.id FROM sincron_org_nodes sn JOIN descendants d ON sn.parent_id = d.id
            )
            SELECT DISTINCT n.id, n.name, n.level, n.parent_id, n.company_id
            FROM descendants d JOIN sincron_org_nodes n ON n.id = d.id
            ORDER BY n.level, n.name
        """, (manager_user_id,))
        nodes = [{'id': r['id'], 'name': r['name'], 'level': r['level'],
                  'parent_id': r['parent_id'], 'company_id': r['company_id']}
                 for r in cursor.fetchall()]

        return {'companies': l0_companies, 'nodes': nodes}
    finally:
        release_db(conn)


def get_direct_manager(user_id):
    """The user's DIRECT manager from the Sincron organigram, or None.

    The inverse of get_managed_employee_ids: a responsable of node N manages the
    members of N + its descendants, so a person's direct manager is the responsable
    of the nearest node at-or-above the node(s) they sit in — themselves excluded
    (so a responsable resolves up to their parent's responsable). Sincron-only, no
    fallback: returns {'id','name','email'} or None when the user has no Sincron
    manager (unmapped, or no responsable above them). Aligns the leave approver with
    the HR/360 hierarchy, which reads the same tables.
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        try:
            cursor.execute("""
                WITH RECURSIVE my_nodes AS (
                    SELECT som.node_id AS id
                    FROM sincron_org_members som
                    JOIN sincron_employees se
                      ON se.sincron_employee_id = som.sincron_employee_id
                     AND se.company_name = som.company_name
                    WHERE se.mapped_jarvis_user_id = %s AND se.is_active = TRUE
                ),
                ancestors AS (
                    SELECT n.id, n.parent_id, 0 AS depth
                    FROM sincron_org_nodes n JOIN my_nodes mn ON mn.id = n.id
                    UNION ALL
                    SELECT p.id, p.parent_id, a.depth + 1
                    FROM sincron_org_nodes p JOIN ancestors a ON p.id = a.parent_id
                )
                SELECT u.id, u.name, u.email
                FROM ancestors a
                JOIN sincron_org_members r ON r.node_id = a.id AND r.role = 'responsable'
                JOIN sincron_employees rse
                  ON rse.sincron_employee_id = r.sincron_employee_id
                 AND rse.company_name = r.company_name
                 AND rse.is_active = TRUE
                JOIN users u ON u.id = rse.mapped_jarvis_user_id
                WHERE rse.mapped_jarvis_user_id <> %s
                ORDER BY a.depth ASC
                LIMIT 1
            """, (user_id, user_id))
            row = cursor.fetchone()
        except Exception:
            conn.rollback()
            return None
        if row:
            return {'id': row['id'], 'name': row['name'], 'email': row['email']}
        return None
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
