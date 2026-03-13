import { Eye, EyeOff, Columns3, GripVertical, ChevronUp, ChevronDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { getServerDefaults } from '@/lib/columnDefaults'
import { columnDefs, columnDefMap, defaultColumns, STORAGE_KEY } from './UnallocatedColumns'

export function loadColumns(): string[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      const parsed = JSON.parse(stored) as string[]
      const valid = parsed.filter((k) => columnDefMap.has(k))
      if (valid.length > 0) return valid
    }
  } catch { /* ignore */ }
  // Try server-configured defaults
  const serverCols = getServerDefaults('efactura')
  if (serverCols && serverCols.length > 0) {
    const valid = serverCols.filter((k) => columnDefMap.has(k))
    if (valid.length > 0) return valid
  }
  return defaultColumns
}

export function saveColumns(cols: string[]) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(cols)) } catch { /* ignore */ }
}

// ── Column Toggle Popover ───────────────────────────────────
export function ColumnToggle({
  visibleColumns,
  onChange,
}: {
  visibleColumns: string[]
  onChange: (cols: string[]) => void
}) {
  const hiddenColumns = columnDefs.filter((c) => !visibleColumns.includes(c.key))

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
    if (visibleColumns.includes(key)) {
      onChange(visibleColumns.filter((c) => c !== key))
    } else {
      onChange([...visibleColumns, key])
    }
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="icon" className="h-9 w-9 shrink-0" title="Configure columns">
          <Columns3 className="h-4 w-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-56 p-3">
        <p className="mb-2 text-xs font-medium text-muted-foreground">Columns &amp; Order</p>

        <div className="space-y-0.5">
          {visibleColumns.map((key, idx) => {
            const col = columnDefMap.get(key)
            if (!col) return null
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
                <button onClick={() => toggle(key)} className="rounded p-0.5 text-muted-foreground hover:text-foreground">
                  <EyeOff className="h-3 w-3" />
                </button>
              </div>
            )
          })}
        </div>

        {hiddenColumns.length > 0 && (
          <>
            <div className="my-2 border-t" />
            <p className="mb-1 text-xs font-medium text-muted-foreground">Hidden</p>
            <div className="space-y-0.5">
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

        {visibleColumns.length !== defaultColumns.length ||
          visibleColumns.some((k, i) => k !== defaultColumns[i]) ? (
          <>
            <div className="my-2 border-t" />
            <button
              onClick={() => onChange(defaultColumns)}
              className="w-full rounded px-2 py-1 text-xs text-muted-foreground hover:bg-accent/50 hover:text-foreground"
            >
              Reset to default
            </button>
          </>
        ) : null}
      </PopoverContent>
    </Popover>
  )
}
