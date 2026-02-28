import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { Columns3, GripVertical, ChevronUp, ChevronDown, EyeOff, Eye } from 'lucide-react'
import { usePersistedState } from '@/lib/utils'
import { useIsMobile } from '@/hooks/useMediaQuery'

export interface ColumnDef<T = unknown> {
  key: string
  label: string
  className?: string
  render: (row: T) => React.ReactNode
}

export function useColumnState(
  storageKey: string,
  defaultColumns: string[],
  allColumnKeys: string[],
) {
  const [visibleColumns, setVisibleColumns] = usePersistedState<string[]>(storageKey, defaultColumns)

  // Filter out any stale keys that no longer exist
  const validVisible = visibleColumns.filter((k) => allColumnKeys.includes(k))
  const safeVisible = validVisible.length > 0 ? validVisible : defaultColumns

  return {
    visibleColumns: safeVisible,
    setVisibleColumns,
    defaultColumns,
  }
}

export function ColumnToggle({
  visibleColumns,
  defaultColumns,
  columnDefs,
  lockedColumns,
  onChange,
}: {
  visibleColumns: string[]
  defaultColumns: string[]
  columnDefs: ColumnDef<never>[]
  lockedColumns?: Set<string>
  onChange: (cols: string[]) => void
}) {
  const isMobile = useIsMobile()
  const locked = lockedColumns ?? new Set<string>()
  const columnDefMap = new Map(columnDefs.map((c) => [c.key, c]))

  if (isMobile) return null
  const hiddenColumns = columnDefs.filter((c) => !visibleColumns.includes(c.key) && !locked.has(c.key))

  const moveUp = (idx: number) => {
    if (idx <= 0) return
    const next = [...visibleColumns]
    ;[next[idx - 1], next[idx]] = [next[idx], next[idx - 1]]
    onChange(next)
  }

  const moveDown = (idx: number) => {
    if (idx >= visibleColumns.length - 1) return
    const next = [...visibleColumns]
    ;[next[idx], next[idx + 1]] = [next[idx + 1], next[idx]]
    onChange(next)
  }

  const toggle = (key: string) => {
    if (locked.has(key)) return
    if (visibleColumns.includes(key)) {
      onChange(visibleColumns.filter((c) => c !== key))
    } else {
      onChange([...visibleColumns, key])
    }
  }

  const isDefault =
    visibleColumns.length === defaultColumns.length &&
    visibleColumns.every((k, i) => k === defaultColumns[i])

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="icon" className="h-9 w-9 shrink-0" title="Configure columns">
          <Columns3 className="h-4 w-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-56 p-3">
        <p className="mb-2 text-xs font-medium text-muted-foreground">Columns &amp; Order</p>

        <div className="space-y-0.5 max-h-[300px] overflow-y-auto">
          {visibleColumns.map((key, idx) => {
            const col = columnDefMap.get(key)
            if (!col) return null
            const isLocked = locked.has(key)
            return (
              <div key={key} className="flex items-center gap-1 rounded px-1 py-0.5 hover:bg-accent/50">
                <GripVertical className="h-3 w-3 text-muted-foreground/50 shrink-0" />
                <span className="flex-1 text-sm">{col.label}</span>
                <button
                  onClick={() => moveUp(idx)}
                  disabled={idx === 0}
                  className="rounded p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-25"
                >
                  <ChevronUp className="h-3 w-3" />
                </button>
                <button
                  onClick={() => moveDown(idx)}
                  disabled={idx === visibleColumns.length - 1}
                  className="rounded p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-25"
                >
                  <ChevronDown className="h-3 w-3" />
                </button>
                {isLocked ? (
                  <span className="p-0.5 text-muted-foreground/40" title="Always visible">
                    <EyeOff className="h-3 w-3" />
                  </span>
                ) : (
                  <button onClick={() => toggle(key)} className="rounded p-0.5 text-muted-foreground hover:text-foreground">
                    <EyeOff className="h-3 w-3" />
                  </button>
                )}
              </div>
            )
          })}
        </div>

        {hiddenColumns.length > 0 && (
          <>
            <div className="my-2 border-t" />
            <p className="mb-1 text-xs font-medium text-muted-foreground">Hidden</p>
            <div className="space-y-0.5 max-h-[200px] overflow-y-auto">
              {hiddenColumns.map((col) => (
                <div key={col.key} className="flex items-center gap-1 rounded px-1 py-0.5 hover:bg-accent/50">
                  <span className="flex-1 text-sm text-muted-foreground">{col.label}</span>
                  <button onClick={() => toggle(col.key)} className="rounded p-0.5 text-muted-foreground hover:text-foreground">
                    <Eye className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          </>
        )}

        {!isDefault && (
          <>
            <div className="my-2 border-t" />
            <button
              onClick={() => onChange(defaultColumns)}
              className="w-full rounded px-2 py-1 text-xs text-muted-foreground hover:bg-accent/50 hover:text-foreground"
            >
              Reset to default
            </button>
          </>
        )}
      </PopoverContent>
    </Popover>
  )
}
