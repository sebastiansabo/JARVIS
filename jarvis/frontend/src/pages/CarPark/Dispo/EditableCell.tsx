import { useMemo, useRef, useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { SearchSelect } from '@/components/shared/SearchSelect'
import { carparkApi } from '@/api/carpark'
import type { DispoRow, Vehicle } from '@/types/carpark'
import { useDispoInlineSave } from './dispoInlineEdit'

// The 19 Dispo summary row fields wired for inline editing (see index.tsx's
// column defs). Restricted to this literal union — rather than a bare
// `keyof DispoRow` — so `{ [field]: value }` is a structurally valid
// Partial<Vehicle> patch for every field this cell can ever be given
// (carparkApi.updateVehicle's payload type); every name here is also in
// VEHICLE_UPDATABLE_FIELDS (vehicle_repository.py) so the PUT always
// persists it.
export type EditableVehicleField =
  | 'brand' | 'model' | 'source' | 'sale_type' | 'location_text' | 'buyer_name' | 'gw_file_number'
  | 'acquisition_date' | 'supplier_payment_date' | 'listing_date' | 'sale_date' | 'delivery_date'
  | 'acquisition_price' | 'sale_price' | 'salesperson_user_id' | 'acquisition_manager_id'
  | 'is_impus' | 'missing_civ' | 'stock_removed'

export type EditableCellType = 'text' | 'number' | 'money' | 'date' | 'select' | 'user' | 'flag'

export type EditableCellValue = string | number | boolean | null

export interface EditableCellOption {
  value: string
  label: string
}

interface EditableCellProps {
  value: EditableCellValue
  row: DispoRow
  field: EditableVehicleField
  type: EditableCellType
  /** Options for 'select' (dropdown_options) and 'user' (users list) types. */
  options?: EditableCellOption[]
  editable: boolean
  /** Renders both the read-only display and the "not editing yet" display in edit-capable cells. */
  display: (value: EditableCellValue) => ReactNode
  onSaved?: (patch: Partial<DispoRow>) => void
}

const SELECT_NONE = '__dispo_none__'
// Sentinel distinguishing "not a number" from a legitimate null/empty commit.
const INVALID = Symbol('invalid')

/**
 * Generic Excel-like inline cell for the Dispo workspace table: click an
 * editable cell to swap its display for the right input; Enter/blur saves
 * that one field via carparkApi.updateVehicle, Escape cancels. Text/number/
 * money/date types show a plain input; select/user types open their picker
 * immediately and save on selection; flag types toggle+save on a single
 * click (no separate edit mode). Save is optimistic against the
 * ['carpark','dispo','summary'] cache with revert+toast on failure (see
 * dispoInlineEdit.ts).
 */
export function EditableCell({ value, row, field, type, options, editable, display, onSaved }: EditableCellProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const cancelledRef = useRef(false)
  const save = useDispoInlineSave(row.id)

  const selectOptions = useMemo(
    () => [{ value: SELECT_NONE, label: '— fără —' }, ...(options ?? [])],
    [options],
  )
  const userOptions = useMemo(
    () => [{ value: '', label: '— niciunul —' }, ...(options ?? [])],
    [options],
  )

  async function runSave(newValue: EditableCellValue) {
    const patch = { [field]: newValue } as Partial<DispoRow>
    const revert = { [field]: value } as Partial<DispoRow>
    const ok = await save({
      patch,
      revert,
      request: () => carparkApi.updateVehicle(row.id, { [field]: newValue } as Partial<Vehicle>),
      errorFallback: 'Eroare la salvare',
    })
    if (ok) onSaved?.(patch)
  }

  // ── flag: no edit mode, click toggles + saves directly ──────────
  if (type === 'flag') {
    const content = display(value)
    if (!editable) return <>{content}</>
    return (
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation()
          void runSave(!value)
        }}
        className="cursor-pointer rounded-sm outline-none transition-opacity hover:opacity-80 focus-visible:ring-1 focus-visible:ring-ring"
        aria-pressed={Boolean(value)}
      >
        {content}
      </button>
    )
  }

  // ── select: opens immediately in edit mode, commits on pick ─────
  if (type === 'select') {
    if (!editable) return <>{display(value)}</>
    if (!editing) {
      return (
        <span
          onClick={(e) => {
            e.stopPropagation()
            setEditing(true)
          }}
          className="block cursor-text rounded-sm px-0.5 -mx-0.5 hover:bg-accent/60"
        >
          {display(value)}
        </span>
      )
    }
    return (
      <div onClick={(e) => e.stopPropagation()}>
        <Select
          open
          value={value == null ? SELECT_NONE : String(value)}
          onOpenChange={(o) => {
            if (!o) setEditing(false)
          }}
          onValueChange={(raw) => {
            setEditing(false)
            const newValue = raw === SELECT_NONE ? null : raw
            if (newValue === (value ?? null)) return
            void runSave(newValue)
          }}
        >
          <SelectTrigger size="sm" className="h-7 w-full text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {selectOptions.map((o) => (
              <SelectItem key={o.value} value={o.value} className="text-xs">
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    )
  }

  // ── user: opens immediately in edit mode, commits on pick ───────
  if (type === 'user') {
    if (!editable) return <>{display(value)}</>
    if (!editing) {
      return (
        <span
          onClick={(e) => {
            e.stopPropagation()
            setEditing(true)
          }}
          className="block cursor-text rounded-sm px-0.5 -mx-0.5 hover:bg-accent/60"
        >
          {display(value)}
        </span>
      )
    }
    return (
      <div onClick={(e) => e.stopPropagation()} className="min-w-[10rem]">
        <SearchSelect
          value={value == null ? '' : String(value)}
          options={userOptions}
          open
          onOpenChange={(o) => {
            if (!o) setEditing(false)
          }}
          onValueChange={(raw) => {
            setEditing(false)
            const newValue = raw === '' ? null : Number(raw)
            if (newValue === (value ?? null)) return
            void runSave(newValue)
          }}
          placeholder="Alege..."
          searchPlaceholder="Caută..."
          emptyMessage="Niciun rezultat"
        />
      </div>
    )
  }

  // ── text / number / money / date: input with Enter/blur=save, Escape=cancel ──
  if (!editable) return <>{display(value)}</>

  if (!editing) {
    return (
      <span
        onClick={(e) => {
          e.stopPropagation()
          setDraft(value == null ? '' : String(value))
          setEditing(true)
          requestAnimationFrame(() => {
            inputRef.current?.focus()
            inputRef.current?.select()
          })
        }}
        className="block cursor-text rounded-sm px-0.5 -mx-0.5 hover:bg-accent/60"
      >
        {display(value)}
      </span>
    )
  }

  function parseDraft(): EditableCellValue | typeof INVALID {
    const trimmed = draft.trim()
    if (type === 'number' || type === 'money') {
      if (trimmed === '') return null
      const n = Number(trimmed)
      return Number.isNaN(n) ? INVALID : n
    }
    if (type === 'date') {
      return trimmed === '' ? null : trimmed
    }
    return trimmed
  }

  function commit() {
    const parsed = parseDraft()
    setEditing(false)
    if (parsed === INVALID) {
      toast.error('Valoare numerică invalidă')
      return
    }
    if (parsed === (value ?? null)) return
    void runSave(parsed)
  }

  return (
    <Input
      ref={inputRef}
      type={type === 'date' ? 'date' : type === 'number' || type === 'money' ? 'number' : 'text'}
      step={type === 'money' ? '0.01' : undefined}
      value={draft}
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => setDraft(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault()
          e.currentTarget.blur()
        } else if (e.key === 'Escape') {
          e.preventDefault()
          cancelledRef.current = true
          e.currentTarget.blur()
        }
      }}
      onBlur={() => {
        if (cancelledRef.current) {
          cancelledRef.current = false
          setEditing(false)
          return
        }
        commit()
      }}
      className="h-7 px-1.5 text-xs tabular-nums"
    />
  )
}
