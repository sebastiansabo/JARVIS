/**
 * Server-side column defaults cache.
 *
 * Fetched once on app startup. Provides:
 * - Default column sets for each page (admin-configured)
 * - Version-based invalidation of user localStorage
 */
import type { DefaultColumnsMap } from '@/types/settings'
import { settingsApi } from '@/api/settings'

let _cache: DefaultColumnsMap = {}

/** Map of pageId → localStorage key used by each page's column store. */
export const PAGE_STORAGE_KEYS: Record<string, string> = {
  accounting: 'accounting-columns',
  crm_deals: 'crm-deals-columns',
  crm_clients: 'crm-clients-columns',
  dms: 'dms-document-columns',
  marketing: 'marketing-project-columns',
  efactura: 'efactura-unallocated-columns',
}

/**
 * Fetch column defaults from server and invalidate stale localStorage.
 * Call once on app startup (e.g. in Layout after auth).
 */
export async function fetchColumnDefaults(): Promise<void> {
  try {
    _cache = await settingsApi.getDefaultColumns()

    for (const [pageId, { version }] of Object.entries(_cache)) {
      const storageKey = PAGE_STORAGE_KEYS[pageId]
      if (!storageKey || !version) continue

      const versionKey = `${storageKey}-version`
      const localVersion = parseInt(localStorage.getItem(versionKey) || '0', 10)

      if (version > localVersion) {
        // Admin bumped version → clear user's custom columns
        localStorage.removeItem(storageKey)
        localStorage.setItem(versionKey, String(version))
      }
    }
  } catch {
    /* non-critical — fall back to hardcoded defaults */
  }
}

/** Get cached server defaults for a page. Returns null if not loaded or not set. */
export function getServerDefaults(pageId: string): string[] | null {
  return _cache[pageId]?.columns ?? null
}

/** Get the full cache (used by Settings > Tables tab). */
export function getColumnDefaultsCache(): DefaultColumnsMap {
  return _cache
}
