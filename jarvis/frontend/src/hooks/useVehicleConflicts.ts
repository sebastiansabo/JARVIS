import { useState, useCallback } from 'react'
import { foiParcursApi } from '@/api/foiParcurs'
import type { VehicleConflict } from '@/types/foiParcurs'

/** Imperative VIN-conflict check for the "Plan a Driving Session" soft-block:
 *  call `check(vin, from, to, excludeId)` right before creating/planning/
 *  activating a TD. Resolves with the overlapping PLANNED/live sessions
 *  (empty array = clear). Never throws — a failed lookup is treated as "no
 *  conflicts" so it can never hard-block the actual submit. */
export function useVehicleConflicts() {
  const [checking, setChecking] = useState(false)

  const check = useCallback(
    async (vin: string, from: string, to: string, excludeId?: number): Promise<VehicleConflict[]> => {
      setChecking(true)
      try {
        const res = await foiParcursApi.getVehicleConflicts(vin, { from, to, exclude_id: excludeId })
        return res.conflicts ?? []
      } catch {
        return []
      } finally {
        setChecking(false)
      }
    },
    [],
  )

  return { checking, check }
}
