import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { usersApi } from '@/api/users'
import { buildUserPhoneMap } from './sessionParty'

/**
 * Shared Users directory for the FoiParcurs/Hub cards. Resolves an internal
 * session's driving user (advisor_name) to their profile phone, and feeds the
 * Consilier picker. Cached 5 min and shared across cards via the query key.
 */
export function useUsersDirectory() {
  const { data } = useQuery({
    queryKey: ['users-directory'],
    queryFn: () => usersApi.getUsers(),
    staleTime: 300_000,
  })
  const phoneByName = useMemo(() => buildUserPhoneMap(data ?? []), [data])
  return { users: data ?? [], phoneByName }
}
