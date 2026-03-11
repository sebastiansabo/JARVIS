/**
 * Zustand slice factory for data-table stores.
 *
 * Provides standardised filter, selection, and (optional) column-visibility
 * state that is duplicated across accounting, HR, marketing, etc.
 */
import { getServerDefaults } from '@/lib/columnDefaults'

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface DataTableState<F> {
  filters: F
  setFilters: (filters: F) => void
  updateFilter: <K extends keyof F>(key: K, value: F[K]) => void
  clearFilters: () => void

  selectedIds: number[]
  setSelectedIds: (ids: number[]) => void
  toggleSelected: (id: number) => void
  selectAll: (ids: number[]) => void
  clearSelected: () => void
}

export interface ColumnState {
  visibleColumns: string[]
  setVisibleColumns: (cols: string[]) => void
}

/* ------------------------------------------------------------------ */
/*  Config                                                             */
/* ------------------------------------------------------------------ */

interface ColumnConfig {
  storageKey: string
  defaults: string[]
  locked?: Set<string>
  /** Maps to server-side page key (e.g. 'accounting', 'dms'). */
  pageId?: string
}

interface DataTableConfig<F> {
  defaultFilters: F
  columns?: ColumnConfig
  /** When true, sets `offset: 0` in filters on every updateFilter call. */
  resetOffsetOnFilter?: boolean
}

/* ------------------------------------------------------------------ */
/*  Factory                                                            */
/* ------------------------------------------------------------------ */

// Zustand `set` — generic enough to accept any store's set function
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type SetFn = (...args: any[]) => void

function ensureLocked(cols: string[], locked?: Set<string>): string[] {
  if (!locked) return cols
  for (const lc of locked) {
    if (!cols.includes(lc)) cols.push(lc)
  }
  return cols
}

function loadColumns(cfg: ColumnConfig): string[] {
  try {
    const raw = localStorage.getItem(cfg.storageKey)
    if (raw) {
      const cols: string[] = JSON.parse(raw)
      if (Array.isArray(cols) && cols.length > 0) {
        return ensureLocked(cols, cfg.locked)
      }
    }
  } catch {
    /* ignore */
  }

  // Fall back to server-configured defaults (if loaded)
  if (cfg.pageId) {
    const serverCols = getServerDefaults(cfg.pageId)
    if (serverCols && serverCols.length > 0) {
      return ensureLocked([...serverCols], cfg.locked)
    }
  }

  return cfg.defaults
}

function saveColumns(key: string, cols: string[]) {
  try {
    localStorage.setItem(key, JSON.stringify(cols))
  } catch {
    /* ignore */
  }
}

/**
 * Creates a Zustand state slice with filter, selection, and optional
 * column-visibility management.  Spread the return value into your
 * `create()` initialiser alongside any domain-specific state.
 *
 * @example
 * ```ts
 * const useMyStore = create<MyState>((set) => ({
 *   ...createDataTableSlice<Filters>({ defaultFilters: {} }, set),
 *   // extra domain state…
 * }))
 * ```
 */
export function createDataTableSlice<F>(
  config: DataTableConfig<F>,
  set: SetFn,
): DataTableState<F> & ColumnState {
  const { defaultFilters, columns, resetOffsetOnFilter } = config

  return {
    // ---- Filters ----
    filters: { ...defaultFilters } as F,

    setFilters: (filters: F) => set({ filters }),

    updateFilter: <K extends keyof F>(key: K, value: F[K]) =>
      set((s: { filters: F }) => ({
        filters: {
          ...s.filters,
          [key]: value,
          ...(resetOffsetOnFilter ? { offset: 0 } : {}),
        },
      })),

    clearFilters: () =>
      set({ filters: { ...defaultFilters }, selectedIds: [] }),

    // ---- Selection ----
    selectedIds: [] as number[],

    setSelectedIds: (ids: number[]) => set({ selectedIds: ids }),

    toggleSelected: (id: number) =>
      set((s: { selectedIds: number[] }) => {
        const cur = s.selectedIds
        return {
          selectedIds: cur.includes(id)
            ? cur.filter((i) => i !== id)
            : [...cur, id],
        }
      }),

    selectAll: (ids: number[]) => set({ selectedIds: ids }),

    clearSelected: () => set({ selectedIds: [] }),

    // ---- Columns ----
    visibleColumns: columns ? loadColumns(columns) : [],

    setVisibleColumns: columns
      ? (cols: string[]) => {
          saveColumns(columns.storageKey, cols)
          set({ visibleColumns: cols })
        }
      : (_cols: string[]) => {
          /* no-op when columns not configured */
        },
  }
}
