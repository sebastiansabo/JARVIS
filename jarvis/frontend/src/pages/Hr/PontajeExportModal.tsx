import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { biostarApi } from '../../api/biostar'

type Mode = 'all' | 'group' | 'employee'

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December']

const pad = (n: number) => String(n).padStart(2, '0')

export default function PontajeExportModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1) // 1-12
  const [mode, setMode] = useState<Mode>('all')
  const [group, setGroup] = useState('')
  const [empIds, setEmpIds] = useState<Set<number>>(new Set())
  const [search, setSearch] = useState('')
  const [groups, setGroups] = useState<string[]>([])
  const [employees, setEmployees] = useState<{ id: number; name: string; group: string }[]>([])
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    if (!open) return
    biostarApi.getGroups()
      .then(r => setGroups((r.groups ?? []).map(g => g.group_name).sort()))
      .catch(() => setGroups([]))
    biostarApi.getEmployees(true)
      .then(list => setEmployees(
        list
          .filter(e => e.mapped_jarvis_user_id != null)
          .map(e => ({ id: e.mapped_jarvis_user_id as number, name: e.name, group: e.user_group_name ?? '' }))
          .sort((a, b) => a.name.localeCompare(b.name)),
      ))
      .catch(() => setEmployees([]))
  }, [open])

  const filteredEmployees = useMemo(() => {
    const q = search.trim().toLowerCase()
    return q ? employees.filter(e => e.name.toLowerCase().includes(q)) : employees
  }, [employees, search])

  const yearOptions = [now.getFullYear(), now.getFullYear() - 1, now.getFullYear() - 2]

  const toggleEmp = (id: number) => setEmpIds(prev => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })

  const canExport = mode === 'all'
    || (mode === 'group' && group)
    || (mode === 'employee' && empIds.size > 0)

  const handleExport = async () => {
    const start = `${year}-${pad(month)}-01`
    const lastDay = new Date(year, month, 0).getDate()
    const end = `${year}-${pad(month)}-${pad(lastDay)}`
    const filters = mode === 'group' ? { group }
      : mode === 'employee' ? { employeeIds: [...empIds] }
      : undefined
    setExporting(true)
    const toastId = toast.loading('Exporting pontaje…')
    try {
      const ok = await biostarApi.exportPontaje(start, end, filters)
      if (ok) { toast.success('Export complete', { id: toastId }); onClose() }
      else toast.error('Export failed', { id: toastId })
    } finally {
      setExporting(false)
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="w-[520px] max-w-[92vw] max-h-[88vh] overflow-y-auto rounded-lg bg-white p-6 shadow-xl dark:bg-neutral-900"
        onClick={e => e.stopPropagation()}
      >
        <h2 className="mb-4 text-lg font-semibold">Export Pontaje</h2>

        <div className="mb-4 flex gap-3">
          <label className="flex-1 text-sm">
            Year
            <select className="mt-1 w-full rounded border px-2 py-1 dark:bg-neutral-800"
              value={year} onChange={e => setYear(Number(e.target.value))}>
              {yearOptions.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
          </label>
          <label className="flex-1 text-sm">
            Month
            <select className="mt-1 w-full rounded border px-2 py-1 dark:bg-neutral-800"
              value={month} onChange={e => setMonth(Number(e.target.value))}>
              {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
            </select>
          </label>
        </div>

        <div className="mb-3 flex gap-4 text-sm">
          {(['all', 'group', 'employee'] as Mode[]).map(m => (
            <label key={m} className="flex items-center gap-1">
              <input type="radio" name="mode" checked={mode === m} onChange={() => setMode(m)} />
              {m === 'all' ? 'All (my scope)' : m === 'group' ? 'By group' : 'By employee'}
            </label>
          ))}
        </div>

        {mode === 'group' && (
          <select className="mb-4 w-full rounded border px-2 py-1 dark:bg-neutral-800"
            value={group} onChange={e => setGroup(e.target.value)}>
            <option value="">Select a group…</option>
            {groups.map(g => <option key={g} value={g}>{g}</option>)}
          </select>
        )}

        {mode === 'employee' && (
          <div className="mb-4">
            <input
              className="mb-2 w-full rounded border px-2 py-1 dark:bg-neutral-800"
              placeholder="Search employees…"
              value={search} onChange={e => setSearch(e.target.value)}
            />
            <div className="max-h-52 overflow-y-auto rounded border p-2 text-sm dark:border-neutral-700">
              {filteredEmployees.map(e => (
                <label key={e.id} className="flex items-center gap-2 py-0.5">
                  <input type="checkbox" checked={empIds.has(e.id)} onChange={() => toggleEmp(e.id)} />
                  <span>{e.name}</span>
                  {e.group && <span className="text-xs text-neutral-500">· {e.group}</span>}
                </label>
              ))}
              {filteredEmployees.length === 0 && <div className="text-neutral-500">No employees</div>}
            </div>
            <div className="mt-1 text-xs text-neutral-500">{empIds.size} selected</div>
          </div>
        )}

        <div className="mt-2 flex justify-end gap-2">
          <button className="rounded px-4 py-1.5 text-sm hover:bg-neutral-100 dark:hover:bg-neutral-800"
            onClick={onClose} disabled={exporting}>Cancel</button>
          <button
            className="rounded bg-[#0F6D63] px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            onClick={handleExport} disabled={!canExport || exporting}>
            {exporting ? 'Exporting…' : 'Export'}
          </button>
        </div>
      </div>
    </div>
  )
}
