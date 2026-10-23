import { useMemo } from 'react'
import { useAuth } from '@/hooks/useAuth'

/**
 * BuyBack permission helpers, derived from the logged-in user.
 *
 * - `isAdmin`  — role is admin/superadmin (implicitly grants everything).
 * - `can(key)` — admin OR the user holds the explicit `module.entity.action`
 *                matrix permission. Status change / reopen are gated on
 *                `can('buyback.record.edit')`, so they're assignable to any role.
 *
 * Centralizes the pattern previously duplicated across the BuyBack list, detail,
 * ActionPanel and Hub panel — keep the semantics of each call site identical.
 */
export function usePermissions() {
  const { user } = useAuth()
  return useMemo(() => {
    const role = (user?.role_name ?? '').toLowerCase()
    const isAdmin = ['admin', 'superadmin'].includes(role)
    const can = (k: string) => isAdmin || !!user?.permissions?.[k]
    return { isAdmin, can }
  }, [user])
}
