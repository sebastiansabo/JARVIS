import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  Trash2,
  Pencil,
  Building2,
  Tag,
  FolderTree,
  ChevronRight,
  ChevronDown,
  Users,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { hrApi } from '@/api/hr'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import type { StructureCompany, MasterItem, DepartmentStructure } from '@/types/hr'

type Section = 'companies' | 'brands' | 'departments' | 'subdepartments'

export default function StructureTab() {
  const [section, setSection] = useState<Section>('companies')

  const sections: { key: Section; label: string; icon: typeof Building2 }[] = [
    { key: 'companies', label: 'Companies', icon: Building2 },
    { key: 'brands', label: 'Brands', icon: Tag },
    { key: 'departments', label: 'Departments', icon: FolderTree },
    { key: 'subdepartments', label: 'Subdepartments', icon: FolderTree },
  ]

  return (
    <div className="space-y-4">
      <div className="flex gap-1">
        {sections.map((s) => (
          <button
            key={s.key}
            onClick={() => setSection(s.key)}
            className={cn(
              'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
              section === s.key
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground hover:text-foreground',
            )}
          >
            <s.icon className="h-3.5 w-3.5" />
            {s.label}
          </button>
        ))}
      </div>

      {section === 'companies' && <CompaniesSection />}
      {section === 'brands' && <MasterSection type="brands" title="Master Brands" />}
      {section === 'departments' && <MasterSection type="departments" title="Master Departments" />}
      {section === 'subdepartments' && <MasterSection type="subdepartments" title="Master Subdepartments" />}
    </div>
  )
}

/* ──── Companies with cascading dept structure ──── */

interface CompanyTreeNode extends StructureCompany {
  children: CompanyTreeNode[]
  depth: number
}

function buildCompanyTree(companies: StructureCompany[]): CompanyTreeNode[] {
  const map = new Map<number, CompanyTreeNode>()
  const roots: CompanyTreeNode[] = []

  for (const c of companies) {
    map.set(c.id, { ...c, children: [], depth: 0 })
  }

  for (const c of companies) {
    const node = map.get(c.id)!
    if (c.parent_company_id && map.has(c.parent_company_id)) {
      const parent = map.get(c.parent_company_id)!
      node.depth = parent.depth + 1
      parent.children.push(node)
    } else {
      roots.push(node)
    }
  }

  return roots
}

function flattenCompanyTree(nodes: CompanyTreeNode[]): CompanyTreeNode[] {
  const result: CompanyTreeNode[] = []
  function walk(list: CompanyTreeNode[]) {
    for (const node of list) {
      result.push(node)
      walk(node.children)
    }
  }
  walk(nodes)
  return result
}

/* Group dept structures: company → brand → dept → subdept (hierarchical) */
interface SubdeptNode {
  subdepartment: string
  manager: string
  entry: DepartmentStructure
}

interface DeptNode {
  department: string
  manager: string // dept-level manager (when no subdept)
  subdepts: SubdeptNode[]
  entry?: DepartmentStructure // the dept-level entry (no subdept)
}

interface BrandNode {
  brand: string
  departments: DeptNode[]
}

interface CompanyDepts {
  count: number
  brands: BrandNode[]
}

interface DeptsByCompany {
  [company: string]: CompanyDepts
}

function groupDeptsByCompany(structures: DepartmentStructure[]): DeptsByCompany {
  const result: DeptsByCompany = {}
  for (const s of structures) {
    if (!result[s.company]) result[s.company] = { count: 0, brands: [] }
    result[s.company].count++
    const brandName = s.brand || '(No Brand)'
    let brandNode = result[s.company].brands.find((b) => b.brand === brandName)
    if (!brandNode) {
      brandNode = { brand: brandName, departments: [] }
      result[s.company].brands.push(brandNode)
    }
    let deptNode = brandNode.departments.find((d) => d.department === s.department)
    if (!deptNode) {
      deptNode = { department: s.department, manager: '', subdepts: [] }
      brandNode.departments.push(deptNode)
    }
    if (s.subdepartment) {
      deptNode.subdepts.push({ subdepartment: s.subdepartment, manager: s.manager || '', entry: s })
    } else {
      deptNode.manager = s.manager || ''
      deptNode.entry = s
    }
  }
  return result
}

function CompaniesSection() {
  const queryClient = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<StructureCompany | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [vat, setVat] = useState('')
  const [parentId, setParentId] = useState<number | null>(null)
  const [expandedCompanies, setExpandedCompanies] = useState<Set<number>>(new Set())

  // Dept structure dialog
  const [deptDialogOpen, setDeptDialogOpen] = useState(false)
  const [editingDept, setEditingDept] = useState<DepartmentStructure | null>(null)
  const [deptCompany, setDeptCompany] = useState('')
  const [deptBrand, setDeptBrand] = useState('')
  const [deptDepartment, setDeptDepartment] = useState('')
  const [deptSubdepartment, setDeptSubdepartment] = useState('')
  const [deptManager, setDeptManager] = useState('')
  const [deleteDeptId, setDeleteDeptId] = useState<number | null>(null)

  const { data: companies = [] } = useQuery({
    queryKey: ['hr-companies-full'],
    queryFn: () => hrApi.getCompaniesFull(),
  })

  const { data: structures = [] } = useQuery({
    queryKey: ['hr-dept-structure'],
    queryFn: () => hrApi.getDepartmentsFull(),
  })

  // Master lists for dropdowns
  const { data: masterBrands = [] } = useQuery({
    queryKey: ['hr-master-brands'],
    queryFn: () => hrApi.getMasterBrands(),
    enabled: deptDialogOpen,
  })
  const { data: masterDepts = [] } = useQuery({
    queryKey: ['hr-master-departments'],
    queryFn: () => hrApi.getMasterDepartments(),
    enabled: deptDialogOpen,
  })
  const { data: masterSubdepts = [] } = useQuery({
    queryKey: ['hr-master-subdepartments'],
    queryFn: () => hrApi.getMasterSubdepartments(),
    enabled: deptDialogOpen,
  })

  const flatList = useMemo(() => {
    const tree = buildCompanyTree(companies)
    return flattenCompanyTree(tree)
  }, [companies])

  const deptsByCompany = useMemo(() => groupDeptsByCompany(structures), [structures])

  const toggleCompany = (id: number) => {
    setExpandedCompanies((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // Company CRUD
  const createMutation = useMutation({
    mutationFn: (data: { company: string; vat?: string; parent_company_id?: number | null }) => hrApi.createCompany(data),
    onSuccess: () => { toast.success('Created'); queryClient.invalidateQueries({ queryKey: ['hr-companies-full'] }); setDialogOpen(false) },
    onError: () => toast.error('Failed'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: { company: string; vat?: string; parent_company_id?: number | null } }) => hrApi.updateCompany(id, data),
    onSuccess: () => { toast.success('Updated'); queryClient.invalidateQueries({ queryKey: ['hr-companies-full'] }); setDialogOpen(false) },
    onError: () => toast.error('Failed to update. Possible circular reference.'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => hrApi.deleteCompany(id),
    onSuccess: () => { toast.success('Deleted'); queryClient.invalidateQueries({ queryKey: ['hr-companies-full'] }) },
    onError: () => toast.error('Failed'),
  })

  // Dept structure CRUD
  const createDeptMutation = useMutation({
    mutationFn: (data: Partial<DepartmentStructure>) => hrApi.createDepartment(data),
    onSuccess: () => { toast.success('Created'); queryClient.invalidateQueries({ queryKey: ['hr-dept-structure'] }); setDeptDialogOpen(false) },
    onError: () => toast.error('Failed'),
  })

  const updateDeptMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<DepartmentStructure> }) => hrApi.updateDepartment(id, data),
    onSuccess: () => { toast.success('Updated'); queryClient.invalidateQueries({ queryKey: ['hr-dept-structure'] }); setDeptDialogOpen(false) },
    onError: () => toast.error('Failed'),
  })

  const deleteDeptMutation = useMutation({
    mutationFn: (id: number) => hrApi.deleteDepartment(id),
    onSuccess: () => { toast.success('Deleted'); queryClient.invalidateQueries({ queryKey: ['hr-dept-structure'] }) },
    onError: () => toast.error('Failed'),
  })

  const openAdd = () => { setEditing(null); setName(''); setVat(''); setParentId(null); setDialogOpen(true) }
  const openEdit = (c: StructureCompany) => { setEditing(c); setName(c.company); setVat(c.vat ?? ''); setParentId(c.parent_company_id); setDialogOpen(true) }

  const handleSave = () => {
    if (!name.trim()) return toast.error('Name required')
    const data = { company: name.trim(), vat: vat || undefined, parent_company_id: parentId }
    if (editing) updateMutation.mutate({ id: editing.id, data })
    else createMutation.mutate(data)
  }

  const openAddDept = (companyName: string) => {
    setEditingDept(null)
    setDeptCompany(companyName)
    setDeptBrand('')
    setDeptDepartment('')
    setDeptSubdepartment('')
    setDeptManager('')
    setDeptDialogOpen(true)
  }

  const openEditDept = (d: DepartmentStructure) => {
    setEditingDept(d)
    setDeptCompany(d.company)
    setDeptBrand(d.brand || '')
    setDeptDepartment(d.department)
    setDeptSubdepartment(d.subdepartment || '')
    setDeptManager(d.manager || '')
    setDeptDialogOpen(true)
  }

  const handleSaveDept = () => {
    if (!deptDepartment.trim()) return toast.error('Department required')
    if (!deptBrand.trim()) return toast.error('Brand required')
    const data = {
      company: deptCompany,
      brand: deptBrand.trim(),
      department: deptDepartment.trim(),
      subdepartment: deptSubdepartment.trim() || undefined,
      manager: deptManager.trim() || undefined,
    }
    if (editingDept) updateDeptMutation.mutate({ id: editingDept.id, data })
    else createDeptMutation.mutate(data)
  }

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <CardTitle className="text-sm">Companies ({companies.length})</CardTitle>
          <Button size="sm" onClick={openAdd}><Plus className="mr-1 h-3.5 w-3.5" />Add</Button>
        </CardHeader>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Company</TableHead>
                <TableHead>VAT</TableHead>
                <TableHead>Brands</TableHead>
                <TableHead className="w-16 text-center">Depts</TableHead>
                <TableHead className="w-20">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {flatList.map((c) => {
                const isExpanded = expandedCompanies.has(c.id)
                const companyDepts = deptsByCompany[c.company]
                const deptCount = companyDepts?.count ?? 0
                const hasChildren = c.children.length > 0

                return (
                  <>
                    <TableRow key={c.id} className={cn(isExpanded && 'bg-muted/40')}>
                      <TableCell className="text-sm font-medium" style={{ paddingLeft: `${8 + c.depth * 24}px` }}>
                        <span className="flex items-center gap-1.5">
                          {deptCount > 0 ? (
                            <button onClick={() => toggleCompany(c.id)} className="p-0.5 -ml-1 hover:bg-muted rounded">
                              {isExpanded
                                ? <ChevronDown className="h-4 w-4 text-muted-foreground" />
                                : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                            </button>
                          ) : (
                            <span className="w-5" />
                          )}
                          {c.depth > 0 && <span className="text-muted-foreground text-xs">└</span>}
                          {hasChildren && <Badge variant="secondary" className="text-[10px] px-1 py-0">Holding</Badge>}
                          {c.company}
                        </span>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">{c.vat ?? '—'}</TableCell>
                      <TableCell>
                        <span className="text-sm text-muted-foreground">
                          {c.brands_list?.length
                            ? c.brands_list.map((b) => b.brand).join(', ')
                            : '—'}
                        </span>
                      </TableCell>
                      <TableCell className="text-center">
                        {deptCount > 0 ? (
                          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                            <Users className="h-3 w-3" />{deptCount}
                          </span>
                        ) : '—'}
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openEdit(c)}>
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => setDeleteId(c.id)}>
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>

                    {/* Cascading: Brand → Dept → Subdept */}
                    {isExpanded && companyDepts && companyDepts.brands.map((brandNode) => (
                      <>
                        {/* Brand header */}
                        <TableRow key={`brand-${c.id}-${brandNode.brand}`} className="bg-muted/30">
                          <TableCell colSpan={5} style={{ paddingLeft: `${28 + c.depth * 24}px` }}>
                            <span className="flex items-center gap-1.5 text-sm font-medium">
                              <Tag className="h-3.5 w-3.5 text-amber-500" />
                              {brandNode.brand}
                              <span className="text-xs text-muted-foreground font-normal">({brandNode.departments.length} dept)</span>
                            </span>
                          </TableCell>
                        </TableRow>

                        {brandNode.departments.map((deptNode) => (
                          <>
                            {/* Department row */}
                            <TableRow key={`dept-hdr-${c.id}-${brandNode.brand}-${deptNode.department}`} className="bg-muted/15 hover:bg-muted/30">
                              <TableCell className="text-sm" style={{ paddingLeft: `${48 + c.depth * 24}px` }}>
                                <span className="flex items-center gap-1.5">
                                  <FolderTree className="h-3.5 w-3.5 text-green-500 shrink-0" />
                                  <span className="font-medium">{deptNode.department}</span>
                                  {deptNode.subdepts.length > 0 && (
                                    <span className="text-xs text-muted-foreground">({deptNode.subdepts.length})</span>
                                  )}
                                </span>
                              </TableCell>
                              <TableCell />
                              <TableCell className="text-sm text-muted-foreground">
                                {deptNode.subdepts.length === 0 ? (deptNode.manager || '—') : ''}
                              </TableCell>
                              <TableCell />
                              <TableCell>
                                {deptNode.entry && (
                                  <div className="flex gap-1">
                                    <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => openEditDept(deptNode.entry!)}>
                                      <Pencil className="h-3 w-3" />
                                    </Button>
                                    <Button variant="ghost" size="icon" className="h-6 w-6 text-destructive" onClick={() => setDeleteDeptId(deptNode.entry!.id)}>
                                      <Trash2 className="h-3 w-3" />
                                    </Button>
                                  </div>
                                )}
                              </TableCell>
                            </TableRow>

                            {/* Subdepartment rows */}
                            {deptNode.subdepts.map((sub) => (
                              <TableRow key={`subdept-${sub.entry.id}`} className="bg-muted/5 hover:bg-muted/20">
                                <TableCell className="text-sm text-muted-foreground" style={{ paddingLeft: `${68 + c.depth * 24}px` }}>
                                  <span className="flex items-center gap-1.5">
                                    <span className="text-xs">└</span>
                                    {sub.subdepartment}
                                  </span>
                                </TableCell>
                                <TableCell />
                                <TableCell className="text-sm text-muted-foreground">{sub.manager || '—'}</TableCell>
                                <TableCell />
                                <TableCell>
                                  <div className="flex gap-1">
                                    <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => openEditDept(sub.entry)}>
                                      <Pencil className="h-3 w-3" />
                                    </Button>
                                    <Button variant="ghost" size="icon" className="h-6 w-6 text-destructive" onClick={() => setDeleteDeptId(sub.entry.id)}>
                                      <Trash2 className="h-3 w-3" />
                                    </Button>
                                  </div>
                                </TableCell>
                              </TableRow>
                            ))}
                          </>
                        ))}
                      </>
                    ))}

                    {/* Add dept button row */}
                    {isExpanded && (
                      <TableRow key={`add-dept-${c.id}`} className="bg-muted/10">
                        <TableCell colSpan={5} style={{ paddingLeft: `${28 + c.depth * 24}px` }}>
                          <Button variant="ghost" size="sm" className="h-7 text-xs text-muted-foreground" onClick={() => openAddDept(c.company)}>
                            <Plus className="mr-1 h-3 w-3" />Add department entry
                          </Button>
                        </TableCell>
                      </TableRow>
                    )}
                  </>
                )
              })}
            </TableBody>
          </Table>
        </div>
      </Card>

      {/* Company dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit Company' : 'Add Company'}</DialogTitle>
            <DialogDescription>Company name, parent, and VAT number.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Company Name *</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Parent Company</Label>
              <Select value={parentId ? String(parentId) : 'none'} onValueChange={(v) => setParentId(v === 'none' ? null : Number(v))}>
                <SelectTrigger><SelectValue placeholder="None (root level)" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None (root level)</SelectItem>
                  {companies
                    .filter((c) => c.id !== editing?.id)
                    .map((c) => (
                      <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
                    ))
                  }
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">VAT Number</Label>
              <Input value={vat} onChange={(e) => setVat(e.target.value)} />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSave}>{editing ? 'Update' : 'Create'}</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Department structure dialog */}
      <Dialog open={deptDialogOpen} onOpenChange={setDeptDialogOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{editingDept ? 'Edit' : 'Add'} Department Entry</DialogTitle>
            <DialogDescription>{deptCompany}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Brand *</Label>
              <Select value={deptBrand} onValueChange={setDeptBrand}>
                <SelectTrigger><SelectValue placeholder="Select brand" /></SelectTrigger>
                <SelectContent>
                  {masterBrands.filter((b) => b.is_active).map((b) => (
                    <SelectItem key={b.id} value={b.name}>{b.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Department *</Label>
              <Select value={deptDepartment} onValueChange={setDeptDepartment}>
                <SelectTrigger><SelectValue placeholder="Select department" /></SelectTrigger>
                <SelectContent>
                  {masterDepts.filter((d) => d.is_active).map((d) => (
                    <SelectItem key={d.id} value={d.name}>{d.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Subdepartment</Label>
              <Select value={deptSubdepartment || 'none'} onValueChange={(v) => setDeptSubdepartment(v === 'none' ? '' : v)}>
                <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {masterSubdepts.filter((s) => s.is_active).map((s) => (
                    <SelectItem key={s.id} value={s.name}>{s.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Manager</Label>
              <Input value={deptManager} onChange={(e) => setDeptManager(e.target.value)} placeholder="Manager name" />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => setDeptDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSaveDept}>{editingDept ? 'Update' : 'Create'}</Button>
          </div>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteId !== null}
        title="Delete Company"
        description="This will delete the company. Any subsidiaries will be promoted to root level."
        onOpenChange={() => setDeleteId(null)}
        onConfirm={() => deleteId !== null && deleteMutation.mutate(deleteId)}
        destructive
      />

      <ConfirmDialog
        open={deleteDeptId !== null}
        title="Delete Department Entry"
        description="This will remove the department structure entry."
        onOpenChange={() => setDeleteDeptId(null)}
        onConfirm={() => deleteDeptId !== null && deleteDeptMutation.mutate(deleteDeptId)}
        destructive
      />
    </>
  )
}

/* ──── Master Brands/Departments/Subdepartments (generic) ──── */

function MasterSection({ type, title }: { type: 'brands' | 'departments' | 'subdepartments'; title: string }) {
  const queryClient = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<MasterItem | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [name, setName] = useState('')

  const queryKey = [`hr-master-${type}`]

  const getFn = type === 'brands' ? hrApi.getMasterBrands : type === 'departments' ? hrApi.getMasterDepartments : hrApi.getMasterSubdepartments
  const createFn = type === 'brands' ? hrApi.createMasterBrand : type === 'departments' ? hrApi.createMasterDepartment : hrApi.createMasterSubdepartment
  const updateFn = type === 'brands' ? hrApi.updateMasterBrand : type === 'departments' ? hrApi.updateMasterDepartment : hrApi.updateMasterSubdepartment
  const deleteFn = type === 'brands' ? hrApi.deleteMasterBrand : type === 'departments' ? hrApi.deleteMasterDepartment : hrApi.deleteMasterSubdepartment

  const { data: items = [] } = useQuery({ queryKey, queryFn: getFn })

  const createMutation = useMutation({
    mutationFn: (data: { name: string }) => createFn(data),
    onSuccess: () => { toast.success('Created'); queryClient.invalidateQueries({ queryKey }); setDialogOpen(false) },
    onError: () => toast.error('Failed'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: { name: string; is_active: boolean } }) => updateFn(id, data),
    onSuccess: () => { toast.success('Updated'); queryClient.invalidateQueries({ queryKey }); setDialogOpen(false) },
    onError: () => toast.error('Failed'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteFn(id),
    onSuccess: () => { toast.success('Deleted'); queryClient.invalidateQueries({ queryKey }) },
    onError: () => toast.error('Failed'),
  })

  const openAdd = () => { setEditing(null); setName(''); setDialogOpen(true) }
  const openEdit = (item: MasterItem) => { setEditing(item); setName(item.name); setDialogOpen(true) }

  const handleSave = () => {
    if (!name.trim()) return toast.error('Name required')
    if (editing) updateMutation.mutate({ id: editing.id, data: { name: name.trim(), is_active: editing.is_active } })
    else createMutation.mutate({ name: name.trim() })
  }

  const active = items.filter((i) => i.is_active)
  const inactive = items.filter((i) => !i.is_active)

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <CardTitle className="text-sm">{title} ({active.length} active, {inactive.length} inactive)</CardTitle>
          <Button size="sm" onClick={openAdd}><Plus className="mr-1 h-3.5 w-3.5" />Add</Button>
        </CardHeader>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-20">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => (
                <TableRow key={item.id} className={cn(!item.is_active && 'opacity-50')}>
                  <TableCell className="text-sm font-medium">{item.name}</TableCell>
                  <TableCell>
                    <Badge variant={item.is_active ? 'default' : 'secondary'} className="text-xs">
                      {item.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openEdit(item)}>
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => setDeleteId(item.id)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit' : 'Add'} {type.slice(0, -1)}</DialogTitle>
            <DialogDescription>Enter the name.</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label className="text-xs">Name *</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSave}>{editing ? 'Update' : 'Create'}</Button>
          </div>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteId !== null}
        title="Delete Item"
        description="This will deactivate the item."
        onOpenChange={() => setDeleteId(null)}
        onConfirm={() => deleteId !== null && deleteMutation.mutate(deleteId)}
        destructive
      />
    </>
  )
}

