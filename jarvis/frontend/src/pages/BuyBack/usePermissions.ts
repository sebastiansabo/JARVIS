import { useMemo } from 'react'
import { useAuth } from '@/hooks/useAuth'

/**
 * BuyBack permission helpers, derived from the logged-in user.
 *
 * - `isAdmin`          — role is admin/superadmin (implicitly grants everything).
 * - `isAdminOrManager` — role is admin/superadmin/manager (mirrors the backend's
 *                        role-only `_is_admin()` gate used by reopen; there is NO
 *                        `buyback.record.reopen` permission).
 * - `can(key)`         — admin OR the user holds the explicit `module.entity.action`
 *                        permission.
 *
 * Centralizes the pattern previously duplicated across the BuyBack list, detail,
 * ActionPanel and Hub panel — keep the semantics of each call site identical.
 */
export function usePermissions() {
  const { user } = useAuth()
  return useMemo(() => {
    const role = (user?.role_name ?? '').toLowerCase()
    const isAdmin = ['admin', 'superadmin'].includes(role)
    const isAdminOrManager = ['admin', 'superadmin', 'manager'].includes(role)
    const can = (k: string) => isAdmin || !!user?.permissions?.[k]
    return { isAdmin, isAdminOrManager, can }
  }, [user])
}
