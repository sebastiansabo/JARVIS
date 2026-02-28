import { useState, useMemo } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { RichTextEditor } from '@/components/shared/RichTextEditor'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Checkbox } from '@/components/ui/checkbox'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ChevronDown } from 'lucide-react'
import { marketingApi } from '@/api/marketing'
import { settingsApi } from '@/api/settings'
import { organizationApi } from '@/api/organization'
import { usersApi } from '@/api/users'
import { cn } from '@/lib/utils'
import { useFormValidation } from '@/hooks/useFormValidation'
import { FieldError } from '@/components/shared/FieldError'
import type { MktProject } from '@/types/marketing'
import type { CompanyWithBrands, DepartmentStructure } from '@/types/organization'
import type { UserDetail } from '@/types/users'

interface Props {
  project?: MktProject | null
  onSuccess: () => void
  onCancel: () => void
}

export default function ProjectForm({ project, onSuccess, onCancel }: Props) {
  const isEdit = !!project

  const [form, setForm] = useState({
    name: project?.name ?? '',
    description: project?.description ?? '',
    company_ids: project?.company_ids ?? (project?.company_id ? [project.company_id] : []),
    brand_ids: project?.brand_ids ?? (project?.brand_id ? [project.brand_id] : []),
    department_ids: project?.department_ids ?? (project?.department_structure_id ? [project.department_structure_id] : []),
    project_type: project?.project_type ?? 'campaign',
    channel_mix: project?.channel_mix ?? [],
    start_date: project?.start_date?.slice(0, 10) ?? '',
    end_date: project?.end_date?.slice(0, 10) ?? '',
    total_budget: project?.total_budget ? String(project.total_budget) : '',
    currency: project?.currency ?? 'RON',
    objective: project?.objective ?? '',
    target_audience: project?.target_audience ?? '',
    external_ref: project?.external_ref ?? '',
    approval_mode: project?.approval_mode ?? 'any',
  })

  const [stakeholderIds, setStakeholderIds] = useState<number[]>([])
  const [observerIds, setObserverIds] = useState<number[]>([])
  const [stakeholderSearch, setStakeholderSearch] = useState('')
  const [observerSearch, setObserverSearch] = useState('')
  const [error, setError] = useState<string | null>(null)

  // Inline validation
  const v = useFormValidation(
    { name: form.name, company_ids: form.company_ids },
    {
      name: (val) => (!val.trim() ? 'Project name is required' : undefined),
      company_ids: (val) => (val.length === 0 ? 'At least one company is required' : undefined),
    },
  )

  // Lookups
  const { data: companies } = useQuery({
    queryKey: ['companies-config'],
    queryFn: () => organizationApi.getCompaniesConfig(),
  })

  const { data: structures } = useQuery({
    queryKey: ['department-structures'],
    queryFn: () => organizationApi.getDepartmentStructures(),
  })

  const { data: typeOptions } = useQuery({
    queryKey: ['dropdown-options', 'mkt_project_type'],
    queryFn: () => settingsApi.getDropdownOptions('mkt_project_type'),
  })

  const { data: channelOptions } = useQuery({
    queryKey: ['dropdown-options', 'mkt_channel'],
    queryFn: () => settingsApi.getDropdownOptions('mkt_channel'),
  })

  const { data: allUsers } = useQuery({
    queryKey: ['users-list'],
    queryFn: () => usersApi.getUsers(),
  })

  // Load existing stakeholders/observers on edit
  const { data: existingMembers } = useQuery({
    queryKey: ['mkt-members', project?.id],
    queryFn: () => marketingApi.getMembers(project!.id),
    enabled: isEdit && !!project?.id,
  })

  // Seed stakeholder/observer IDs from existing members (once on load)
  const [membersSeeded, setMembersSeeded] = useState(false)
  if (isEdit && existingMembers && !membersSeeded) {
    const members = existingMembers.members ?? []
    setStakeholderIds(members.filter((m) => m.role === 'stakeholder').map((m) => m.user_id))
    setObserverIds(members.filter((m) => m.role === 'observer').map((m) => m.user_id))
    setMembersSeeded(true)
  }

  // Derived: brands from selected companies
  const availableBrands = useMemo(() => {
    if (!companies) return []
    const selectedCompanies = companies.filter((c: CompanyWithBrands) => form.company_ids.includes(c.id))
    const brands: { brand_id: number; brand: string; company: string }[] = []
    const seen = new Set<number>()
    for (const co of selectedCompanies) {
      for (const b of co.brands_list ?? []) {
        if (!seen.has(b.brand_id)) {
          seen.add(b.brand_id)
          brands.push({ brand_id: b.brand_id, brand: b.brand, company: co.company })
        }
      }
    }
    return brands
  }, [companies, form.company_ids])

  // Derived: departments from selected companies
  const availableDepts = useMemo(() => {
    if (!structures) return []
    return (structures as DepartmentStructure[]).filter((s) => form.company_ids.includes(s.company_id))
  }, [structures, form.company_ids])

  async function addMembersToProject(projectId: number, sIds: number[], oIds: number[]) {
    const adds = [
      ...sIds.map((uid) => marketingApi.addMember(projectId, { user_id: uid, role: 'stakeholder' })),
      ...oIds.map((uid) => marketingApi.addMember(projectId, { user_id: uid, role: 'observer' })),
    ]
    await Promise.all(adds)
  }

  async function syncMembers(projectId: number, sIds: number[], oIds: number[]) {
    const members = existingMembers?.members ?? []
    const existingStakeholders = members.filter((m) => m.role === 'stakeholder')
    const existingObservers = members.filter((m) => m.role === 'observer')
    const removes: Promise<unknown>[] = []
    const adds: Promise<unknown>[] = []
    // Remove stakeholders no longer selected
    for (const m of existingStakeholders) {
      if (!sIds.includes(m.user_id)) removes.push(marketingApi.removeMember(projectId, m.id))
    }
    // Remove observers no longer selected
    for (const m of existingObservers) {
      if (!oIds.includes(m.user_id)) removes.push(marketingApi.removeMember(projectId, m.id))
    }
    // Add new stakeholders
    for (const uid of sIds) {
      if (!existingStakeholders.some((m) => m.user_id === uid)) {
        adds.push(marketingApi.addMember(projectId, { user_id: uid, role: 'stakeholder' }))
      }
    }
    // Add new observers
    for (const uid of oIds) {
      if (!existingObservers.some((m) => m.user_id === uid)) {
        adds.push(marketingApi.addMember(projectId, { user_id: uid, role: 'observer' }))
      }
    }
    await Promise.all([...removes, ...adds])
  }

  const createMutation = useMutation({
    mutationFn: async (data: Record<string, unknown>) => {
      const res = await marketingApi.createProject(data as Partial<MktProject>)
      if (res.id && (stakeholderIds.length > 0 || observerIds.length > 0)) {
        await addMembersToProject(res.id, stakeholderIds, observerIds)
      }
      return res
    },
    onSuccess: () => onSuccess(),
    onError: (err: Error & { data?: { error?: string } }) => {
      setError(err?.data?.error || err.message || 'Failed to create project')
    },
  })

  const updateMutation = useMutation({
    mutationFn: async (data: Record<string, unknown>) => {
      const res = await marketingApi.updateProject(project!.id, data as Partial<MktProject>)
      await syncMembers(project!.id, stakeholderIds, observerIds)
      return res
    },
    onSuccess: () => onSuccess(),
    onError: (err: Error & { data?: { error?: string } }) => {
      setError(err?.data?.error || err.message || 'Failed to update project')
    },
  })

  function toggleArrayItem<T>(arr: T[], item: T): T[] {
    return arr.includes(item) ? arr.filter((x) => x !== item) : [...arr, item]
  }

  function toggleCompany(id: number) {
    setForm((f) => {
      const newCompanyIds = toggleArrayItem(f.company_ids, id)
      // Remove brands/depts that no longer belong to selected companies
      const validCompanySet = new Set(newCompanyIds)
      const validBrandIds = f.brand_ids.filter((bid) => {
        return (companies ?? []).some((c: CompanyWithBrands) =>
          validCompanySet.has(c.id) && (c.brands_list ?? []).some((b) => b.brand_id === bid)
        )
      })
      const validDeptIds = f.department_ids.filter((did) => {
        return (structures as DepartmentStructure[] ?? []).some((s) =>
          validCompanySet.has(s.company_id) && s.id === did
        )
      })
      return { ...f, company_ids: newCompanyIds, brand_ids: validBrandIds, department_ids: validDeptIds }
    })
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    v.touchAll()
    if (!v.isValid) return

    const payload: Record<string, unknown> = {
      name: form.name.trim(),
      company_id: form.company_ids[0],
      company_ids: form.company_ids,
      brand_ids: form.brand_ids,
      department_ids: form.department_ids,
      project_type: form.project_type,
      channel_mix: form.channel_mix,
      currency: form.currency,
      total_budget: Number(form.total_budget) || 0,
      approval_mode: form.approval_mode,
    }
    if (form.description) payload.description = form.description
    if (form.brand_ids.length === 1) payload.brand_id = form.brand_ids[0]
    if (form.department_ids.length === 1) payload.department_structure_id = form.department_ids[0]
    if (form.start_date) payload.start_date = form.start_date
    if (form.end_date) payload.end_date = form.end_date
    if (form.objective) payload.objective = form.objective
    if (form.target_audience) payload.target_audience = form.target_audience
    if (form.external_ref) payload.external_ref = form.external_ref

    if (isEdit) {
      updateMutation.mutate(payload)
    } else {
      createMutation.mutate(payload)
    }
  }

  const isSaving = createMutation.isPending || updateMutation.isPending

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {error && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-3 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      {/* Name */}
      <div className="space-y-1.5">
        <Label htmlFor="name">Project Name *</Label>
        <Input
          id="name"
          value={form.name}
          onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          onBlur={() => v.touch('name')}
          className={cn(v.error('name') && 'border-destructive')}
          placeholder="Q1 2026 Brand Campaign"
        />
        <FieldError message={v.error('name')} />
      </div>

      {/* Companies (dropdown + checkboxes) */}
      <div className="space-y-1.5">
        <Label>Companies *</Label>
        <Popover onOpenChange={(open) => { if (!open) v.touch('company_ids') }}>
          <PopoverTrigger asChild>
            <Button variant="outline" className={cn('w-full justify-between font-normal', v.error('company_ids') && 'border-destructive')}>
              <span className="truncate">
                {form.company_ids.length === 0
                  ? 'Select companies...'
                  : `${form.company_ids.length} compan${form.company_ids.length === 1 ? 'y' : 'ies'} selected`}
              </span>
              <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-[--radix-popover-trigger-width] p-2" align="start">
            <div className="max-h-48 overflow-y-auto space-y-1">
              {(companies ?? []).map((c: CompanyWithBrands) => (
                <label key={c.id} className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-accent cursor-pointer text-sm">
                  <Checkbox
                    checked={form.company_ids.includes(c.id)}
                    onCheckedChange={() => toggleCompany(c.id)}
                  />
                  {c.company}
                </label>
              ))}
            </div>
          </PopoverContent>
        </Popover>
        {form.company_ids.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {form.company_ids.map((id) => {
              const name = (companies ?? []).find((c: CompanyWithBrands) => c.id === id)?.company
              return name ? (
                <Badge key={id} variant="secondary" className="text-xs gap-1">
                  {name}
                  <button type="button" className="ml-0.5 hover:text-destructive" onClick={() => toggleCompany(id)}>&times;</button>
                </Badge>
              ) : null
            })}
          </div>
        )}
        <FieldError message={v.error('company_ids')} />
      </div>

      {/* Brands (dropdown + checkboxes, from selected companies) */}
      {availableBrands.length > 0 && (
        <div className="space-y-1.5">
          <Label>Brands</Label>
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="outline" className="w-full justify-between font-normal">
                <span className="truncate">
                  {form.brand_ids.length === 0
                    ? 'Select brands...'
                    : `${form.brand_ids.length} brand${form.brand_ids.length === 1 ? '' : 's'} selected`}
                </span>
                <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-[--radix-popover-trigger-width] p-2" align="start">
              <div className="max-h-48 overflow-y-auto space-y-1">
                {availableBrands.map((b) => (
                  <label key={b.brand_id} className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-accent cursor-pointer text-sm">
                    <Checkbox
                      checked={form.brand_ids.includes(b.brand_id)}
                      onCheckedChange={() => setForm((f) => ({ ...f, brand_ids: toggleArrayItem(f.brand_ids, b.brand_id) }))}
                    />
                    {form.company_ids.length > 1 ? `${b.company} — ${b.brand}` : b.brand}
                  </label>
                ))}
              </div>
            </PopoverContent>
          </Popover>
          {form.brand_ids.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {form.brand_ids.map((id) => {
                const b = availableBrands.find((x) => x.brand_id === id)
                return b ? (
                  <Badge key={id} variant="secondary" className="text-xs gap-1">
                    {b.brand}
                    <button type="button" className="ml-0.5 hover:text-destructive" onClick={() => setForm((f) => ({ ...f, brand_ids: f.brand_ids.filter((x) => x !== id) }))}>&times;</button>
                  </Badge>
                ) : null
              })}
            </div>
          )}
        </div>
      )}

      {/* Departments (dropdown + checkboxes, from selected companies) */}
      {availableDepts.length > 0 && (
        <div className="space-y-1.5">
          <Label>Departments</Label>
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="outline" className="w-full justify-between font-normal">
                <span className="truncate">
                  {form.department_ids.length === 0
                    ? 'Select departments...'
                    : `${form.department_ids.length} dept${form.department_ids.length === 1 ? '' : 's'} selected`}
                </span>
                <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-[--radix-popover-trigger-width] p-2" align="start">
              <div className="max-h-48 overflow-y-auto space-y-1">
                {availableDepts.map((d) => {
                  const label = d.subdepartment ? `${d.department} / ${d.subdepartment}` : d.department
                  return (
                    <label key={d.id} className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-accent cursor-pointer text-sm">
                      <Checkbox
                        checked={form.department_ids.includes(d.id)}
                        onCheckedChange={() => setForm((f) => ({ ...f, department_ids: toggleArrayItem(f.department_ids, d.id) }))}
                      />
                      {form.company_ids.length > 1 ? `${d.company} — ${label}` : label}
                    </label>
                  )
                })}
              </div>
            </PopoverContent>
          </Popover>
          {form.department_ids.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {form.department_ids.map((id) => {
                const d = availableDepts.find((x) => x.id === id)
                if (!d) return null
                const label = d.subdepartment ? `${d.department} / ${d.subdepartment}` : d.department
                return (
                  <Badge key={id} variant="secondary" className="text-xs gap-1">
                    {form.company_ids.length > 1 ? `${d.company} — ${label}` : label}
                    <button type="button" className="ml-0.5 hover:text-destructive" onClick={() => setForm((f) => ({ ...f, department_ids: f.department_ids.filter((x) => x !== id) }))}>&times;</button>
                  </Badge>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Type + Budget + Currency */}
      <div className="grid grid-cols-3 gap-4">
        <div className="space-y-1.5">
          <Label>Project Type</Label>
          <Select value={form.project_type} onValueChange={(v) => setForm((f) => ({ ...f, project_type: v }))}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {(typeOptions ?? []).map((opt: { value: string; label: string }) => (
                <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="mkt-total-budget">Total Budget</Label>
          <Input
            id="mkt-total-budget"
            type="number"
            value={form.total_budget}
            onChange={(e) => setForm((f) => ({ ...f, total_budget: e.target.value }))}
            placeholder="0"
          />
        </div>
        <div className="space-y-1.5">
          <Label>Currency</Label>
          <Select value={form.currency} onValueChange={(v) => setForm((f) => ({ ...f, currency: v }))}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="RON">RON</SelectItem>
              <SelectItem value="EUR">EUR</SelectItem>
              <SelectItem value="USD">USD</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Channels (dropdown + checkboxes) */}
      <div className="space-y-1.5">
        <Label>Channel Mix</Label>
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" className="w-full justify-between font-normal">
              <span className="truncate">
                {form.channel_mix.length === 0
                  ? 'Select channels...'
                  : `${form.channel_mix.length} selected`}
              </span>
              <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-[--radix-popover-trigger-width] p-2" align="start">
            <div className="max-h-48 overflow-y-auto space-y-1">
              {(channelOptions ?? []).map((opt: { value: string; label: string }) => (
                <label key={opt.value} className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-accent cursor-pointer text-sm">
                  <Checkbox
                    checked={form.channel_mix.includes(opt.value)}
                    onCheckedChange={() => setForm((f) => ({ ...f, channel_mix: toggleArrayItem(f.channel_mix, opt.value) }))}
                  />
                  {opt.label}
                </label>
              ))}
            </div>
          </PopoverContent>
        </Popover>
        {form.channel_mix.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {form.channel_mix.map((ch) => {
              const label = (channelOptions ?? []).find((o: { value: string; label: string }) => o.value === ch)?.label ?? ch
              return (
                <Badge key={ch} variant="secondary" className="text-xs gap-1">
                  {label}
                  <button type="button" className="ml-0.5 hover:text-destructive" onClick={() => setForm((f) => ({ ...f, channel_mix: f.channel_mix.filter((x) => x !== ch) }))}>&times;</button>
                </Badge>
              )
            })}
          </div>
        )}
      </div>

      {/* Dates */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="mkt-start-date">Start Date</Label>
          <Input
            id="mkt-start-date"
            type="date"
            value={form.start_date}
            onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value }))}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="mkt-end-date">End Date</Label>
          <Input
            id="mkt-end-date"
            type="date"
            value={form.end_date}
            onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value }))}
          />
        </div>
      </div>

      {/* Description, Objective, Target Audience, External Ref — edit only */}
      {isEdit && (
        <>
          <div className="space-y-1.5">
            <Label>Description</Label>
            <RichTextEditor
              content={form.description}
              onChange={(html) => setForm((f) => ({ ...f, description: html }))}
              placeholder="Brief project description..."
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="mkt-objective">Objective</Label>
            <Textarea
              id="mkt-objective"
              value={form.objective}
              onChange={(e) => setForm((f) => ({ ...f, objective: e.target.value }))}
              placeholder="What does success look like?"
              rows={2}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="mkt-target-audience">Target Audience</Label>
            <Input
              id="mkt-target-audience"
              value={form.target_audience}
              onChange={(e) => setForm((f) => ({ ...f, target_audience: e.target.value }))}
              placeholder="e.g., Males 25-45, urban, car enthusiasts"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="mkt-external-ref">External Reference</Label>
            <Input
              id="mkt-external-ref"
              value={form.external_ref}
              onChange={(e) => setForm((f) => ({ ...f, external_ref: e.target.value }))}
              placeholder="PO number, agency ref, etc."
            />
          </div>
        </>
      )}

      {/* Approval Settings */}
      <div className="space-y-1.5">
        <Label>Approval Mode</Label>
        <Select value={form.approval_mode} onValueChange={(v) => setForm((f) => ({ ...f, approval_mode: v as 'any' | 'all' }))}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="any">Any one stakeholder</SelectItem>
            <SelectItem value="all">All stakeholders must approve</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Stakeholders (approvers) */}
      <div className="space-y-1.5">
        <Label>Stakeholders (Approvers)</Label>
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" className="w-full justify-between font-normal">
              <span className="truncate">
                {stakeholderIds.length === 0
                  ? 'Select stakeholders...'
                  : `${stakeholderIds.length} stakeholder${stakeholderIds.length === 1 ? '' : 's'} selected`}
              </span>
              <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-[--radix-popover-trigger-width] p-2" align="start">
            <Input
              placeholder="Search users..."
              value={stakeholderSearch}
              onChange={(e) => setStakeholderSearch(e.target.value)}
              className="mb-2 h-8 text-sm"
            />
            <ScrollArea className="h-48">
              <div className="space-y-1 pr-3">
                {(allUsers ?? [])
                  .filter((u: UserDetail) => !observerIds.includes(u.id))
                  .filter((u: UserDetail) => u.name.toLowerCase().includes(stakeholderSearch.toLowerCase()))
                  .map((u: UserDetail) => (
                  <label key={u.id} className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-accent cursor-pointer text-sm">
                    <Checkbox
                      checked={stakeholderIds.includes(u.id)}
                      onCheckedChange={() => setStakeholderIds((prev) => prev.includes(u.id) ? prev.filter((x) => x !== u.id) : [...prev, u.id])}
                    />
                    {u.name}
                  </label>
                ))}
              </div>
            </ScrollArea>
          </PopoverContent>
        </Popover>
        {stakeholderIds.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {stakeholderIds.map((id) => {
              const name = (allUsers ?? []).find((u: UserDetail) => u.id === id)?.name
              return name ? (
                <Badge key={id} variant="secondary" className="text-xs gap-1">
                  {name}
                  <button type="button" className="ml-0.5 hover:text-destructive" onClick={() => setStakeholderIds((prev) => prev.filter((x) => x !== id))}>&times;</button>
                </Badge>
              ) : null
            })}
          </div>
        )}
      </div>

      {/* Observers (view-only) */}
      <div className="space-y-1.5">
        <Label>Observers (View-only)</Label>
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" className="w-full justify-between font-normal">
              <span className="truncate">
                {observerIds.length === 0
                  ? 'Select observers...'
                  : `${observerIds.length} observer${observerIds.length === 1 ? '' : 's'} selected`}
              </span>
              <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-[--radix-popover-trigger-width] p-2" align="start">
            <Input
              placeholder="Search users..."
              value={observerSearch}
              onChange={(e) => setObserverSearch(e.target.value)}
              className="mb-2 h-8 text-sm"
            />
            <ScrollArea className="h-48">
              <div className="space-y-1 pr-3">
                {(allUsers ?? [])
                  .filter((u: UserDetail) => !stakeholderIds.includes(u.id))
                  .filter((u: UserDetail) => u.name.toLowerCase().includes(observerSearch.toLowerCase()))
                  .map((u: UserDetail) => (
                  <label key={u.id} className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-accent cursor-pointer text-sm">
                    <Checkbox
                      checked={observerIds.includes(u.id)}
                      onCheckedChange={() => setObserverIds((prev) => prev.includes(u.id) ? prev.filter((x) => x !== u.id) : [...prev, u.id])}
                    />
                    {u.name}
                  </label>
                ))}
              </div>
            </ScrollArea>
          </PopoverContent>
        </Popover>
        {observerIds.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {observerIds.map((id) => {
              const name = (allUsers ?? []).find((u: UserDetail) => u.id === id)?.name
              return name ? (
                <Badge key={id} variant="secondary" className="text-xs gap-1">
                  {name}
                  <button type="button" className="ml-0.5 hover:text-destructive" onClick={() => setObserverIds((prev) => prev.filter((x) => x !== id))}>&times;</button>
                </Badge>
              ) : null
            })}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-3 pt-2">
        <Button type="button" variant="outline" onClick={onCancel} disabled={isSaving}>
          Cancel
        </Button>
        <Button type="submit" disabled={isSaving}>
          {isSaving ? 'Saving...' : isEdit ? 'Update Project' : 'Create Project'}
        </Button>
      </div>
    </form>
  )
}
