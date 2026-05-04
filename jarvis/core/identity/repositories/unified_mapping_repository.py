"""Unified mapping repository — cross-connector read queries.

Read-only queries that join `users` with `sincron_employees`,
`biostar_employees`, and `connecteam_users` to produce a per-user unified
view. Writes are still delegated to the per-connector repositories
(SincronRepository, BioStarRepository, ConnecteamRepository) so this module
never touches their underlying tables.
"""

from core.base_repository import BaseRepository


class UnifiedMappingRepository(BaseRepository):
    """Read-only cross-connector queries for the unified mapping UI."""

    def get_unified_view(self):
        """Return one row per active JARVIS user with Sincron + BioStar + Connecteam mappings.

        All sides are JSON arrays because a user may have multiple rows in
        either table (different Sincron companies, or legacy + current BioStar
        cards).

        Output columns:
            user_id, name, email, cnp, company, department, is_active,
            sincron_mappings (JSON array — may be empty),
            biostar_mappings (JSON array — may be empty),
            connecteam_mappings (JSON array — may be empty)
        """
        return self.query_all('''
            WITH sincron_agg AS (
                SELECT
                    se.mapped_jarvis_user_id AS user_id,
                    json_agg(
                        jsonb_build_object(
                            'sincron_employee_id', se.sincron_employee_id,
                            'company_name',        se.company_name,
                            'nume',                se.nume,
                            'prenume',             se.prenume,
                            'mapping_method',      se.mapping_method,
                            'mapping_confidence',  se.mapping_confidence,
                            'is_active',           se.is_active,
                            'last_synced_at',      se.last_synced_at
                        )
                        ORDER BY se.company_name
                    ) AS sincron_mappings
                FROM sincron_employees se
                WHERE se.mapped_jarvis_user_id IS NOT NULL
                  AND se.is_active = TRUE
                GROUP BY se.mapped_jarvis_user_id
            ),
            biostar_agg AS (
                SELECT
                    be.mapped_jarvis_user_id AS user_id,
                    json_agg(
                        jsonb_build_object(
                            'biostar_user_id',     be.biostar_user_id,
                            'name',                be.name,
                            'email',               be.email,
                            'user_group_name',     be.user_group_name,
                            'mapping_method',      be.mapping_method,
                            'mapping_confidence',  be.mapping_confidence,
                            'status',              be.status,
                            'is_blacklisted',      be.is_blacklisted,
                            'last_synced_at',      be.last_synced_at
                        )
                        ORDER BY be.mapping_confidence DESC NULLS LAST, be.biostar_user_id
                    ) AS biostar_mappings
                FROM biostar_employees be
                WHERE be.mapped_jarvis_user_id IS NOT NULL
                  AND be.status = 'active'
                GROUP BY be.mapped_jarvis_user_id
            ),
            connecteam_agg AS (
                SELECT
                    cu.mapped_jarvis_user_id AS user_id,
                    json_agg(
                        jsonb_build_object(
                            'connecteam_user_id',  cu.connecteam_user_id,
                            'connecteam_user_name', cu.connecteam_user_name,
                            'mapping_method',      cu.mapping_method,
                            'mapping_confidence',  cu.mapping_confidence,
                            'is_active',           cu.is_active
                        )
                        ORDER BY cu.connecteam_user_name
                    ) AS connecteam_mappings
                FROM connecteam_users cu
                WHERE cu.mapped_jarvis_user_id IS NOT NULL
                  AND cu.is_active = TRUE
                GROUP BY cu.mapped_jarvis_user_id
            )
            SELECT
                u.id          AS user_id,
                u.name        AS name,
                u.email       AS email,
                u.cnp         AS cnp,
                COALESCE(co.company, u.company) AS company,
                u.department  AS department,
                u.is_active   AS is_active,
                COALESCE(sa.sincron_mappings, '[]'::json) AS sincron_mappings,
                COALESCE(ba.biostar_mappings, '[]'::json) AS biostar_mappings,
                COALESCE(ca.connecteam_mappings, '[]'::json) AS connecteam_mappings
            FROM users u
            LEFT JOIN companies co ON co.id = u.company_id
            LEFT JOIN sincron_agg sa ON sa.user_id = u.id
            LEFT JOIN biostar_agg ba ON ba.user_id = u.id
            LEFT JOIN connecteam_agg ca ON ca.user_id = u.id
            WHERE u.is_active = TRUE
            ORDER BY u.name
        ''')

    def get_orphan_sincron(self):
        """Sincron employees with no JARVIS user mapping."""
        return self.query_all('''
            SELECT se.id, se.sincron_employee_id, se.company_name,
                   se.nume, se.prenume, se.cnp,
                   se.id_contract, se.nr_contract,
                   se.is_active, se.last_synced_at
            FROM sincron_employees se
            WHERE se.mapped_jarvis_user_id IS NULL
              AND se.is_active = TRUE
            ORDER BY se.company_name, se.nume, se.prenume
        ''')

    def get_orphan_biostar(self):
        """BioStar employees with no JARVIS user mapping."""
        return self.query_all('''
            SELECT be.id, be.biostar_user_id, be.name, be.email, be.phone,
                   be.user_group_id, be.user_group_name,
                   be.status, be.is_blacklisted, be.last_synced_at
            FROM biostar_employees be
            WHERE be.mapped_jarvis_user_id IS NULL
              AND be.status = 'active'
            ORDER BY be.name
        ''')

    def get_orphan_connecteam(self):
        """Connecteam users with no JARVIS user mapping."""
        return self.query_all('''
            SELECT cu.id, cu.connecteam_user_id, cu.connecteam_user_name,
                   cu.is_active
            FROM connecteam_users cu
            WHERE cu.mapped_jarvis_user_id IS NULL
              AND cu.is_active = TRUE
            ORDER BY cu.connecteam_user_name
        ''')

    def get_stats(self):
        """Aggregated counts across Sincron, BioStar, and JARVIS users."""
        return self.query_one('''
            SELECT
                (SELECT COUNT(*) FROM users WHERE is_active) AS total_users,
                (
                    SELECT COUNT(DISTINCT u.id)
                    FROM users u
                    WHERE u.is_active
                      AND EXISTS (SELECT 1 FROM sincron_employees se
                                  WHERE se.mapped_jarvis_user_id = u.id
                                    AND se.is_active)
                      AND EXISTS (SELECT 1 FROM biostar_employees be
                                  WHERE be.mapped_jarvis_user_id = u.id
                                    AND be.status = 'active')
                ) AS fully_mapped,
                (
                    SELECT COUNT(DISTINCT u.id)
                    FROM users u
                    WHERE u.is_active
                      AND EXISTS (SELECT 1 FROM sincron_employees se
                                  WHERE se.mapped_jarvis_user_id = u.id
                                    AND se.is_active)
                      AND NOT EXISTS (SELECT 1 FROM biostar_employees be
                                      WHERE be.mapped_jarvis_user_id = u.id
                                        AND be.status = 'active')
                ) AS sincron_only,
                (
                    SELECT COUNT(DISTINCT u.id)
                    FROM users u
                    WHERE u.is_active
                      AND EXISTS (SELECT 1 FROM biostar_employees be
                                  WHERE be.mapped_jarvis_user_id = u.id
                                    AND be.status = 'active')
                      AND NOT EXISTS (SELECT 1 FROM sincron_employees se
                                      WHERE se.mapped_jarvis_user_id = u.id
                                        AND se.is_active)
                ) AS biostar_only,
                (
                    SELECT COUNT(DISTINCT u.id)
                    FROM users u
                    WHERE u.is_active
                      AND NOT EXISTS (SELECT 1 FROM sincron_employees se
                                      WHERE se.mapped_jarvis_user_id = u.id
                                        AND se.is_active)
                      AND NOT EXISTS (SELECT 1 FROM biostar_employees be
                                      WHERE be.mapped_jarvis_user_id = u.id
                                        AND be.status = 'active')
                ) AS unmapped_users,
                (
                    SELECT COUNT(*) FROM sincron_employees
                    WHERE mapped_jarvis_user_id IS NULL AND is_active
                ) AS orphan_sincron,
                (
                    SELECT COUNT(*) FROM biostar_employees
                    WHERE mapped_jarvis_user_id IS NULL AND status = 'active'
                ) AS orphan_biostar,
                (
                    SELECT COUNT(*) FROM connecteam_users
                    WHERE mapped_jarvis_user_id IS NULL AND is_active = TRUE
                ) AS orphan_connecteam
        ''')

    def get_jarvis_users(self):
        """Active JARVIS users for manual mapping dropdowns."""
        return self.query_all('''
            SELECT id, name, email, company, department
            FROM users
            WHERE is_active = TRUE
            ORDER BY name
        ''')
