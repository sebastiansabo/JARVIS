import { useCallback } from 'react'
import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import type { DispoRow, DispoSummaryResponse } from '@/types/carpark'
import { apiErrorMessage } from './dispoApiError'

// Patches every currently-cached ['carpark','dispo','summary', ...] query
// (one per distinct filters/page/sort combo) in place — used both to apply
// the optimistic edit before the request lands and to revert it if the
// request fails. Matches on the 3-element key prefix so it's agnostic to
// whatever filters/page/sort/dir suffix a given cached query carries.
export function patchDispoRow(queryClient: QueryClient, rowId: number, patch: Partial<DispoRow>) {
  queryClient.setQueriesData<DispoSummaryResponse>(
    { queryKey: ['carpark', 'dispo', 'summary'] },
    (old) => {
      if (!old) return old
      return { ...old, rows: old.rows.map((r) => (r.id === rowId ? { ...r, ...patch } : r)) }
    },
  )
}

interface SaveArgs {
  /** Optimistic patch applied to the cached row immediately. */
  patch: Partial<DispoRow>
  /** Values to restore on the cached row if the request fails. */
  revert: Partial<DispoRow>
  /** The actual persistence call (updateVehicle or changeStatus). */
  request: () => Promise<unknown>
  /** Shown via toast.error if the request fails and the server gives no message. */
  errorFallback: string
}

/**
 * Shared "one field, one save" flow for the Dispo workspace's inline cells:
 * optimistically patch the summary cache, fire the request, and on success
 * invalidate summary+kpis so the server recomputes margin/aging/totals; on
 * failure revert the optimistic patch and toast the server's message (e.g.
 * a 400 "Tranziție interzisă" from the status matrix).
 */
export function useDispoInlineSave(rowId: number) {
  const queryClient = useQueryClient()

  return useCallback(
    async ({ patch, revert, request, errorFallback }: SaveArgs): Promise<boolean> => {
      patchDispoRow(queryClient, rowId, patch)
      try {
        await request()
        queryClient.invalidateQueries({ queryKey: ['carpark', 'dispo', 'summary'] })
        queryClient.invalidateQueries({ queryKey: ['carpark', 'dispo', 'kpis'] })
        return true
      } catch (err) {
        patchDispoRow(queryClient, rowId, revert)
        toast.error(apiErrorMessage(err, errorFallback))
        return false
      }
    },
    [queryClient, rowId],
  )
}
