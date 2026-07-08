import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { biostarApi } from '../../api/biostar'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

type Mode = 'all' | 'company' | 'group' | 'employee'

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December']

const MODE_OPTIONS: [Mode, string][] = [
  ['all', 'All (my scope)'],
  ['company', 'By company'],
  ['group', 'By group'],
  ['employee', 'By employee'],
]

const pad = (n: number) => String(n).padStart(2, '0')

export default function PontajeExportModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1) // 1-12
  const [mode, setMode] = useState<Mode>('all')
  const [group, setGroup] = useState('')
  const [companyId, setCompanyId] = useState('')
  const [empIds, setEmpIds] = useState<Set<number>>(new Set())
  const [search, setSearch] = useState('')
  const [groups, setGroups] = useState<string[]>([])
  const [companies, setCompanies] = useState<{ id: number; name: string }[]>([])
  const [employees, setEmployees] = useState<{ id: number; name: string }[]>([])
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    if (!open) return
    biostarApi.getGroups()
      .then(r => {
        setGroups((r.groups ?? []).map(g => g.group_name).sort())
        setCompanies((r.companies ?? []).slice().sort((a, b) => a.name.localeCompare(b.name)))
      })
      .catch(() => { setGroups([]); setCompanies([]) })
    biostarApi.getEmployees(true)
      .then(list => {
        // One JARVIS user maps to many BioStar rows (one per company); dedupe by
        // jarvis id so the checklist has unique keys and one entry per person.
        const seen = new Set<number>()
        const deduped: { id: number; name: string }[] = []
        for (const e of list) {
          const id = e.mapped_jarvis_user_id
          if (id == null || seen.has(id)) continue
          seen.add(id)
          deduped.push({ id, name: e.name })
        }
        deduped.sort((a, b) => a.name.localeCompare(b.name))
        setEmployees(deduped)
      })
      .catch(() => setEmployees([]))
  }, [open])

  const filteredEmployees = useMemo(() => {
    const q = search.trim().toLowerCase()
    return q ? employees.filter(e => e.name.toLowerCase().includes(q)) : employees
  }, [employees, search])

  const yearOptions = [now.getFullYear(), now.getFullYear() - 1, now.getFullYear() - 2]

  const toggleEmp = (id: number) => setEmpIds(prev => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })

  const canExport = mode === 'all'
    || (mode === 'company' && !!companyId)
    || (mode === 'group' && !!group)
    || (mode === 'employee' && empIds.size > 0)

  const handleExport = async () => {
    const start = `${year}-${pad(month)}-01`
    const lastDay = new Date(year, month, 0).getDate()
    const end = `${year}-${pad(month)}-${pad(lastDay)}`
    const filters = mode === 'group' ? { group }
      : mode === 'company' ? { companyId: Number(companyId) }
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

  return (
    <Dialog open={open} onOpenChange={o => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Export Pontaje</DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label>Year</Label>
            <Select value={String(year)} onValueChange={v => setYear(Number(v))}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {yearOptions.map(y => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Month</Label>
            <Select value={String(month)} onValueChange={v => setMonth(Number(v))}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {MONTHS.map((m, i) => <SelectItem key={m} value={String(i + 1)}>{m}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>

        <RadioGroup
          value={mode}
          onValueChange={v => setMode(v as Mode)}
          className="grid grid-cols-2 gap-2"
        >
          {MODE_OPTIONS.map(([val, label]) => (
            <div key={val} className="flex items-center space-x-2">
              <RadioGroupItem value={val} id={`mode-${val}`} />
              <Label htmlFor={`mode-${val}`} className="font-normal">{label}</Label>
            </div>
          ))}
        </RadioGroup>

        {mode === 'company' && (
          <Select value={companyId} onValueChange={setCompanyId}>
            <SelectTrigger><SelectValue placeholder="Select a company…" /></SelectTrigger>
            <SelectContent>
              {companies.map(c => <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>)}
            </SelectContent>
          </Select>
        )}

        {mode === 'group' && (
          <Select value={group} onValueChange={setGroup}>
            <SelectTrigger><SelectValue placeholder="Select a group…" /></SelectTrigger>
            <SelectContent>
              {groups.map(g => <SelectItem key={g} value={g}>{g}</SelectItem>)}
            </SelectContent>
          </Select>
        )}

        {mode === 'employee' && (
          <div className="space-y-2">
            <Input
              placeholder="Search employees…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            <div className="max-h-52 overflow-y-auto rounded-md border p-1">
              {filteredEmployees.map(e => (
                <label
                  key={e.id}
                  htmlFor={`emp-${e.id}`}
                  className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-muted"
                >
                  <Checkbox id={`emp-${e.id}`} checked={empIds.has(e.id)} onCheckedChange={() => toggleEmp(e.id)} />
                  <span>{e.name}</span>
                </label>
              ))}
              {filteredEmployees.length === 0 && (
                <div className="px-2 py-2 text-sm text-muted-foreground">No employees</div>
              )}
            </div>
            <div className="text-xs text-muted-foreground">{empIds.size} selected</div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={exporting}>Cancel</Button>
          <Button onClick={handleExport} disabled={!canExport || exporting}>
            {exporting ? 'Exporting…' : 'Export'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
