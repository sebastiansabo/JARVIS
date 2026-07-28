"""HR Department Pulse repository — all SQL for the backend-aggregated 360.

Owns Sincron-org department resolution, eligibility (recursive CTE over
sincron_org_nodes.parent_id), the anonymous aggregate, and vote upsert/delete.
Routes hold NO SQL (arch validator).
"""
from typing import Optional

from core.base_repository import BaseRepository

# A user's eligible-node set is: their own member/responsable nodes, plus every
# descendant of any node where they are a responsable (manager-sees-down).
_ELIGIBLE_SQL = """
    WITH RECURSIVE my_nodes AS (
        SELECT som.node_id, som.role
        FROM sincron_org_members som
        JOIN sincron_employees se
          ON se.sincron_employee_id = som.sincron_employee_id
         AND se.company_name = som.company_name
        WHERE se.mapped_jarvis_user_id = %s AND se.is_active = TRUE
    ),
    resp_tree AS (
        SELECT node_id AS id FROM my_nodes WHERE role = 'responsable'
        UNION
        SELECT n.id
        FROM sincron_org_nodes n
        JOIN resp_tree rt ON n.parent_id = rt.id
    ),
    eligible AS (
        SELECT node_id AS id FROM my_nodes
        UNION
        SELECT id FROM resp_tree
    )
"""


class DeptPulseRepository(BaseRepository):
    """All SQL behind /profile/api/dept-pulse."""

    MIN_VOTERS = 3

    # ── Resolution ──

    def resolve_department(self, user_id: int) -> Optional[dict]:
        """The caller's default department node: prefer a node where they are a
        member, else one where they are a responsable; ties broken by level, id."""
        return self.query_one(
            """
            SELECT n.id AS node_id, n.name, n.company_id
            FROM sincron_org_members som
            JOIN sincron_org_nodes n ON n.id = som.node_id
            JOIN sincron_employees se
              ON se.sincron_employee_id = som.sincron_employee_id
             AND se.company_name = som.company_name
            WHERE se.mapped_jarvis_user_id = %s AND se.is_active = TRUE
            ORDER BY (som.role = 'member') DESC, n.level ASC, n.id ASC
            LIMIT 1
            """,
            (user_id,),
        )

    def get_department(self, node_id: int) -> Optional[dict]:
        return self.query_one(
            "SELECT id AS node_id, name, company_id FROM sincron_org_nodes WHERE id = %s",
            (node_id,),
        )

    # ── Eligibility ──

    def eligible_node_ids(self, user_id: int) -> set[int]:
        rows = self.query_all(_ELIGIBLE_SQL + " SELECT id FROM eligible", (user_id,))
        return {r['id'] for r in rows}

    def available_departments(self, user_id: int) -> list[dict]:
        return self.query_all(
            _ELIGIBLE_SQL + """
            SELECT n.id AS node_id, n.name
            FROM sincron_org_nodes n
            JOIN eligible e ON e.id = n.id
            ORDER BY n.level, n.name
            """,
            (user_id,),
        )

    def is_eligible(self, user_id: int, node_id: int) -> bool:
        return node_id in self.eligible_node_ids(user_id)

    # ── Aggregate (anonymous) ──

    def get_voter_count(self, node_id: int) -> int:
        row = self.query_one(
            "SELECT COUNT(DISTINCT voter_user_id) AS n FROM hr_dept_pulse_votes WHERE department_node_id = %s",
            (node_id,),
        )
        return int(row['n']) if row else 0

    def get_aggregate(self, node_id: int) -> list[dict]:
        """Anonymous per-perspective × competency average + distinct voter count.
        voter_user_id never leaves the server. avg comes back as float via
        dict_from_row's Decimal coercion."""
        return self.query_all(
            """
            SELECT perspective, competency_key,
                   ROUND(AVG(rating)::numeric, 2) AS avg,
                   COUNT(DISTINCT voter_user_id)  AS voters
            FROM hr_dept_pulse_votes
            WHERE department_node_id = %s
            GROUP BY perspective, competency_key
            """,
            (node_id,),
        )

    # ── Caller's own votes ──

    def get_my_votes(self, user_id: int, node_id: int) -> list[dict]:
        return self.query_all(
            """
            SELECT perspective, competency_key, rating
            FROM hr_dept_pulse_votes
            WHERE voter_user_id = %s AND department_node_id = %s
            ORDER BY perspective, competency_key
            """,
            (user_id, node_id),
        )

    # ── Write ──

    def upsert_vote(self, user_id: int, node_id: int, perspective: str,
                    competency_key: str, rating: int) -> None:
        self.execute(
            """
            INSERT INTO hr_dept_pulse_votes
                (voter_user_id, department_node_id, perspective, competency_key, rating, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (voter_user_id, department_node_id, perspective, competency_key)
            DO UPDATE SET rating = EXCLUDED.rating, updated_at = NOW()
            """,
            (user_id, node_id, perspective, competency_key, rating),
        )

    def delete_vote(self, user_id: int, node_id: int, perspective: str,
                    competency_key: str) -> None:
        self.execute(
            """
            DELETE FROM hr_dept_pulse_votes
            WHERE voter_user_id = %s AND department_node_id = %s
              AND perspective = %s AND competency_key = %s
            """,
            (user_id, node_id, perspective, competency_key),
        )
