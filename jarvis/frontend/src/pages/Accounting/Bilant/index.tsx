import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Scale, Plus, Upload, FileSpreadsheet, Trash2, Copy, Eye, Download, Pencil, ChevronRight, ChevronDown, Search, BookOpen, FileUp, X } from 'lucide-react'
import { toast } from 'sonner'

import { bilantApi } from '@/api/bilant'
import { organizationApi } from '@/api/organization'
import { PageHeader } from '@/components/shared/PageHeader'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { StatCard } from '@/components/shared/StatCard'
import { EmptyState } from '@/components/shared/EmptyState'
import { useTabParam } from '@/hooks/useTabParam'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { UploadDialog } from './UploadDialog'
import type { BilantTemplate, BilantGeneration, ChartOfAccount } from '@/types/bilant'

type MainTab = 'generations' | 'templates' | 'plan-conturi'

const statusColors: Record<string, string> = {
  completed: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400',
  processing: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  error: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
}

function fmt(n: number | null | undefined): string {
  if (n == null) return '-'
  return new Intl.NumberFormat('ro-RO').format(n)
}

function fmtDate(s: string | null | undefined): string {
  if (!s) return '-'
  return new Date(s).toLocaleDateString('ro-RO', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

const CLASS_NAMES: [number, string][] = [
  [1, 'Capitaluri'], [2, 'Imobilizari'], [3, 'Stocuri si productie'],
  [4, 'Terti'], [5, 'Trezorerie'], [6, 'Cheltuieli'],
  [7, 'Venituri'], [8, 'Conturi speciale'], [9, 'Conturi de gestiune'],
]

export default function Bilant() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [tab, setTab] = useTabParam<MainTab>('generations')
  const [companyFilter, setCompanyFilter] = useState<string>('')
  const [showUpload, setShowUpload] = useState(false)
  const [showNewTemplate, setShowNewTemplate] = useState(false)
  const [newTemplateName, setNewTemplateName] = useState('')
  const [newTemplateCompany, setNewTemplateCompany] = useState<string>('')
  const [deleteTarget, setDeleteTarget] = useState<{ type: 'generation' | 'template'; id: number; name: string } | null>(null)
  const [coaSearch, setCoaSearch] = useState('')
  const [coaClassFilter, setCoaClassFilter] = useState<string>('')
  const [expandedClasses, setExpandedClasses] = useState<Set<number>>(new Set([1, 2, 3, 4, 5, 6, 7]))
  const [showAddAccount, setShowAddAccount] = useState(false)
  const [editingAccount, setEditingAccount] = useState<ChartOfAccount | null>(null)
  const [newAccount, setNewAccount] = useState({ code: '', name: '', account_class: '', account_type: 'synthetic', parent_code: '' })
  const [showAnafImport, setShowAnafImport] = useState(false)
  const [anafFile, setAnafFile] = useState<File | null>(null)
  const [anafName, setAnafName] = useState('')
  const [anafCompany, setAnafCompany] = useState<string>('')

  // ── Queries ──

  const { data: companiesData } = useQuery({
    queryKey: ['companies-config'],
    queryFn: () => organizationApi.getCompaniesConfig(),
  })
  const companies = companiesData || []

  const { data: generationsData, isLoading: genLoading } = useQuery({
    queryKey: ['bilant-generations', companyFilter],
    queryFn: () => bilantApi.listGenerations({ company_id: companyFilter ? Number(companyFilter) : undefined, limit: 100 }),
  })
  const generations = generationsData?.generations || []
  const genTotal = generationsData?.total || 0

  const { data: templatesData, isLoading: tplLoading } = useQuery({
    queryKey: ['bilant-templates', companyFilter],
    queryFn: () => bilantApi.listTemplates(companyFilter ? Number(companyFilter) : undefined),
  })
  const templates = templatesData?.templates || []

  const { data: coaData } = useQuery({
    queryKey: ['chart-of-accounts', companyFilter, coaClassFilter],
    queryFn: () => bilantApi.listAccounts({
      company_id: companyFilter ? Number(companyFilter) : undefined,
      account_class: coaClassFilter ? Number(coaClassFilter) : undefined,
    }),
    enabled: tab === 'plan-conturi',
  })
  const allAccounts = coaData?.accounts || []

  const filteredAccounts = useMemo(() => {
    if (!coaSearch) return allAccounts
    const q = coaSearch.toLowerCase()
    return allAccounts.filter(a => a.code.startsWith(coaSearch) || a.name.toLowerCase().includes(q))
  }, [allAccounts, coaSearch])

  const accountsByClass = useMemo(() => {
    const map = new Map<number, ChartOfAccount[]>()
    for (const a of filteredAccounts) {
      const list = map.get(a.account_class) || []
      list.push(a)
      map.set(a.account_class, list)
    }
    return map
  }, [filteredAccounts])

  // ── Mutations ──

  const deleteGenMut = useMutation({
    mutationFn: (id: number) => bilantApi.deleteGeneration(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bilant-generations'] }); toast.success('Generation deleted') },
  })

  const deleteTplMut = useMutation({
    mutationFn: (id: number) => bilantApi.deleteTemplate(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bilant-templates'] }); toast.success('Template deleted') },
  })

  const duplicateTplMut = useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) => bilantApi.duplicateTemplate(id, name),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bilant-templates'] }); toast.success('Template duplicated') },
  })

  const createTplMut = useMutation({
    mutationFn: (data: { name: string; company_id?: number }) => bilantApi.createTemplate(data),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['bilant-templates'] })
      toast.success('Template created')
      setShowNewTemplate(false)
      setNewTemplateName('')
      if (res.id) navigate(`/app/accounting/bilant/templates/${res.id}`)
    },
  })

  const anafImportMut = useMutation({
    mutationFn: () => {
      if (!anafFile) throw new Error('No file')
      return bilantApi.importAnafPdf(
        anafFile,
        anafName || 'ANAF Template',
        anafCompany && anafCompany !== 'global' ? Number(anafCompany) : undefined,
      )
    },
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['bilant-templates'] })
      toast.success(`ANAF template imported: ${res.row_count} rows (${res.form_type})`)
      setShowAnafImport(false)
      setAnafFile(null)
      setAnafName('')
      setAnafCompany('')
      if (res.template_id) navigate(`/app/accounting/bilant/templates/${res.template_id}`)
    },
    onError: (err: Error & { data?: { error?: string } }) => {
      toast.error(err.data?.error || err.message || 'ANAF import failed')
    },
  })

  const createAccountMut = useMutation({
    mutationFn: (data: { code: string; name: string; account_class: number; account_type?: string; parent_code?: string }) =>
      bilantApi.createAccount(data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['chart-of-accounts'] }); toast.success('Account added'); setShowAddAccount(false); setNewAccount({ code: '', name: '', account_class: '', account_type: 'synthetic', parent_code: '' }) },
  })

  const updateAccountMut = useMutation({
    mutationFn: ({ id, ...data }: Partial<ChartOfAccount> & { id: number }) => bilantApi.updateAccount(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['chart-of-accounts'] }); toast.success('Account updated'); setEditingAccount(null) },
  })

  const deleteAccountMut = useMutation({
    mutationFn: (id: number) => bilantApi.deleteAccount(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['chart-of-accounts'] }); toast.success('Account deleted') },
  })

  const handleDelete = () => {
    if (!deleteTarget) return
    if (deleteTarget.type === 'generation') deleteGenMut.mutate(deleteTarget.id)
    else deleteTplMut.mutate(deleteTarget.id)
    setDeleteTarget(null)
  }

  // ── Stats ──
  const completedCount = generations.filter(g => g.status === 'completed').length
  const uniqueCompanies = new Set(generations.map(g => g.company_id)).size

  // ── Tabs ──
  const tabs: { key: MainTab; label: string }[] = [
    { key: 'generations', label: 'Generations' },
    { key: 'templates', label: 'Templates' },
    { key: 'plan-conturi', label: 'Plan de Conturi' },
  ]

  return (
    <div className="space-y-4">
      <PageHeader
        title="Bilant"
        description="Balance sheet generator — upload Balanta, generate Bilant with financial ratios"
        breadcrumbs={[
          { label: 'Accounting', href: '/app/accounting' },
          { label: 'Bilant' },
          { label: tabs.find(t => t.key === tab)?.label ?? 'Generations' },
        ]}
        actions={
          <div className="flex items-center gap-2">
            {tab === 'generations' && (
              <Button size="icon" className="md:size-auto md:px-3" onClick={() => setShowUpload(true)}>
                <Upload className="h-4 w-4 md:mr-1.5" />
                <span className="hidden md:inline">New Generation</span>
              </Button>
            )}
            {tab === 'templates' && (
              <>
                <Button size="icon" variant="outline" className="md:size-auto md:px-3" onClick={() => setShowAnafImport(true)}>
                  <FileUp className="h-4 w-4 md:mr-1.5" />
                  <span className="hidden md:inline">Import ANAF PDF</span>
                </Button>
                <Button size="icon" className="md:size-auto md:px-3" onClick={() => setShowNewTemplate(true)}>
                  <Plus className="h-4 w-4 md:mr-1.5" />
                  <span className="hidden md:inline">New Template</span>
                </Button>
              </>
            )}
          </div>
        }
      />

      {/* Tabs */}
      <Tabs value={tab} onValueChange={(v) => setTab(v as MainTab)}>
        <div className="flex flex-col gap-2 md:flex-row md:items-center">
          <div className="-mx-4 overflow-x-auto px-4 md:mx-0 md:overflow-visible md:px-0">
            <TabsList className="w-max md:w-auto">
              {tabs.map(t => (
                <TabsTrigger key={t.key} value={t.key}>{t.label}</TabsTrigger>
              ))}
            </TabsList>
          </div>
          <div className="ml-auto">
            <Select value={companyFilter} onValueChange={setCompanyFilter}>
              <SelectTrigger className="h-8 w-[180px] text-xs">
                <SelectValue placeholder="All companies" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All companies</SelectItem>
                {companies.map(c => (
                  <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </Tabs>

      {/* Generations Tab */}
      {tab === 'generations' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard title="Total Generations" value={fmt(genTotal)} icon={<Scale className="h-4 w-4" />} isLoading={genLoading} />
            <StatCard title="Completed" value={fmt(completedCount)} icon={<FileSpreadsheet className="h-4 w-4" />} isLoading={genLoading} />
            <StatCard title="Companies" value={fmt(uniqueCompanies)} isLoading={genLoading} />
            <StatCard title="Templates" value={fmt(templates.length)} isLoading={tplLoading} />
          </div>

          {generations.length === 0 && !genLoading ? (
            <EmptyState
              icon={<Scale className="h-12 w-12" />}
              title="No generations yet"
              description="Upload a Balanta Excel file to generate your first Bilant"
              action={
                <Button size="sm" onClick={() => setShowUpload(true)}>
                  <Upload className="mr-1.5 h-4 w-4" />
                  Upload Balanta
                </Button>
              }
            />
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Company</TableHead>
                    <TableHead>Period</TableHead>
                    <TableHead>Template</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead>By</TableHead>
                    <TableHead className="w-[100px]">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {generations.map(g => (
                    <GenerationRow
                      key={g.id}
                      gen={g}
                      onView={() => navigate(`/app/accounting/bilant/${g.id}`)}
                      onDownload={() => bilantApi.downloadGeneration(g.id)}
                      onDelete={() => setDeleteTarget({ type: 'generation', id: g.id, name: `${g.company_name} - ${g.period_label || g.id}` })}
                    />
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      )}

      {/* Templates Tab */}
      {tab === 'templates' && (
        <div className="space-y-4">
          {templates.length === 0 && !tplLoading ? (
            <EmptyState
              icon={<FileSpreadsheet className="h-12 w-12" />}
              title="No templates"
              description="Create a template to define the Bilant structure"
              action={
                <Button size="sm" onClick={() => setShowNewTemplate(true)}>
                  <Plus className="mr-1.5 h-4 w-4" />
                  New Template
                </Button>
              }
            />
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Company</TableHead>
                    <TableHead>Rows</TableHead>
                    <TableHead>Default</TableHead>
                    <TableHead>Version</TableHead>
                    <TableHead className="w-[100px]">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {templates.map(t => (
                    <TemplateRow
                      key={t.id}
                      tpl={t}
                      onEdit={() => navigate(`/app/accounting/bilant/templates/${t.id}`)}
                      onDuplicate={() => duplicateTplMut.mutate({ id: t.id, name: `${t.name} (Copy)` })}
                      onDelete={() => setDeleteTarget({ type: 'template', id: t.id, name: t.name })}
                    />
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      )}

      {/* Plan de Conturi Tab */}
      {tab === 'plan-conturi' && (
        <div className="space-y-4">
          {/* Search + Filter bar */}
          <div className="flex items-center gap-3">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                value={coaSearch}
                onChange={e => setCoaSearch(e.target.value)}
                placeholder="Search by code or name..."
                className="h-9 pl-8 text-sm"
              />
            </div>
            <Select value={coaClassFilter} onValueChange={setCoaClassFilter}>
              <SelectTrigger className="h-9 w-[180px] text-xs">
                <SelectValue placeholder="All classes" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All classes</SelectItem>
                {CLASS_NAMES.map(([cls, name]) => (
                  <SelectItem key={cls} value={String(cls)}>{cls} — {name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button size="sm" onClick={() => setShowAddAccount(true)}>
              <Plus className="mr-1.5 h-4 w-4" />
              Add Account
            </Button>
          </div>

          {/* Tree view by class */}
          {filteredAccounts.length === 0 ? (
            <EmptyState
              icon={<BookOpen className="h-12 w-12" />}
              title="No accounts found"
              description={coaSearch ? 'Try a different search term' : 'Seed data will load on first run'}
            />
          ) : (
            <div className="space-y-1">
              {Array.from(accountsByClass.entries())
                .sort(([a], [b]) => a - b)
                .map(([cls, accounts]) => {
                  const isExpanded = expandedClasses.has(cls)
                  const className = CLASS_NAMES.find(([c]) => c === cls)?.[1] || ''
                  const classAccounts = accounts.filter(a => a.account_type === 'class')
                  const groups = accounts.filter(a => a.account_type === 'group')
                  const synthetics = accounts.filter(a => a.account_type === 'synthetic' || a.account_type === 'analytical')

                  return (
                    <div key={cls} className="rounded-md border">
                      {/* Class header */}
                      <button
                        onClick={() => {
                          const next = new Set(expandedClasses)
                          if (isExpanded) next.delete(cls); else next.add(cls)
                          setExpandedClasses(next)
                        }}
                        className="flex w-full items-center gap-2 px-3 py-2 text-sm font-semibold hover:bg-muted/50 transition-colors"
                      >
                        {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                        <span className="font-mono text-primary">{cls}</span>
                        <span>{classAccounts[0]?.name || className}</span>
                        <Badge variant="secondary" className="ml-auto text-[10px]">{accounts.length} accounts</Badge>
                      </button>

                      {/* Expanded content */}
                      {isExpanded && (
                        <div className="border-t">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead className="w-24">Code</TableHead>
                                <TableHead>Name</TableHead>
                                <TableHead className="w-24">Type</TableHead>
                                <TableHead className="w-24">Parent</TableHead>
                                <TableHead className="w-20">Actions</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {[...groups, ...synthetics].map(account => (
                                <TableRow key={account.id}>
                                  <TableCell className="font-mono text-xs font-medium">{account.code}</TableCell>
                                  <TableCell>
                                    <span
                                      className={`text-xs ${account.account_type === 'group' ? 'font-semibold' : ''}`}
                                      style={{ paddingLeft: account.account_type === 'synthetic' ? 16 : account.account_type === 'analytical' ? 32 : 0 }}
                                    >
                                      {account.name}
                                    </span>
                                  </TableCell>
                                  <TableCell>
                                    <Badge variant="outline" className="text-[10px]">{account.account_type}</Badge>
                                  </TableCell>
                                  <TableCell className="font-mono text-xs text-muted-foreground">{account.parent_code || '-'}</TableCell>
                                  <TableCell>
                                    <div className="flex items-center gap-1">
                                      <Button
                                        variant="ghost" size="icon" className="h-6 w-6"
                                        onClick={() => setEditingAccount(account)}
                                      >
                                        <Pencil className="h-3 w-3" />
                                      </Button>
                                      <Button
                                        variant="ghost" size="icon" className="h-6 w-6 text-destructive"
                                        onClick={() => deleteAccountMut.mutate(account.id)}
                                      >
                                        <Trash2 className="h-3 w-3" />
                                      </Button>
                                    </div>
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </div>
                      )}
                    </div>
                  )
                })}
            </div>
          )}
        </div>
      )}

      {/* Add Account Dialog */}
      <Dialog open={showAddAccount || !!editingAccount} onOpenChange={(v) => { if (!v) { setShowAddAccount(false); setEditingAccount(null) } }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editingAccount ? 'Edit Account' : 'Add Account'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs">Code *</Label>
                <Input
                  value={editingAccount ? (editingAccount.code) : newAccount.code}
                  onChange={e => editingAccount ? setEditingAccount({ ...editingAccount, code: e.target.value }) : setNewAccount({ ...newAccount, code: e.target.value })}
                  placeholder="e.g. 411"
                  className="font-mono"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Class *</Label>
                <Select
                  value={editingAccount ? String(editingAccount.account_class) : newAccount.account_class}
                  onValueChange={v => editingAccount ? setEditingAccount({ ...editingAccount, account_class: Number(v) }) : setNewAccount({ ...newAccount, account_class: v })}
                >
                  <SelectTrigger className="text-xs"><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent>
                    {CLASS_NAMES.map(([cls, name]) => (
                      <SelectItem key={cls} value={String(cls)}>{cls} — {name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Name *</Label>
              <Input
                value={editingAccount ? editingAccount.name : newAccount.name}
                onChange={e => editingAccount ? setEditingAccount({ ...editingAccount, name: e.target.value }) : setNewAccount({ ...newAccount, name: e.target.value })}
                placeholder="Account name"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs">Type</Label>
                <Select
                  value={editingAccount ? editingAccount.account_type : newAccount.account_type}
                  onValueChange={v => editingAccount ? setEditingAccount({ ...editingAccount, account_type: v as ChartOfAccount['account_type'] }) : setNewAccount({ ...newAccount, account_type: v })}
                >
                  <SelectTrigger className="text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="class">Class</SelectItem>
                    <SelectItem value="group">Group</SelectItem>
                    <SelectItem value="synthetic">Synthetic</SelectItem>
                    <SelectItem value="analytical">Analytical</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Parent Code</Label>
                <Input
                  value={editingAccount ? (editingAccount.parent_code || '') : newAccount.parent_code}
                  onChange={e => editingAccount ? setEditingAccount({ ...editingAccount, parent_code: e.target.value || null }) : setNewAccount({ ...newAccount, parent_code: e.target.value })}
                  placeholder="e.g. 41"
                  className="font-mono"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => { setShowAddAccount(false); setEditingAccount(null) }}>Cancel</Button>
              <Button
                size="sm"
                disabled={editingAccount ? (!editingAccount.code || !editingAccount.name) : (!newAccount.code || !newAccount.name || !newAccount.account_class)}
                onClick={() => {
                  if (editingAccount) {
                    updateAccountMut.mutate({
                      id: editingAccount.id,
                      code: editingAccount.code,
                      name: editingAccount.name,
                      account_class: editingAccount.account_class,
                      account_type: editingAccount.account_type,
                      parent_code: editingAccount.parent_code,
                    })
                  } else {
                    createAccountMut.mutate({
                      code: newAccount.code.trim(),
                      name: newAccount.name.trim(),
                      account_class: Number(newAccount.account_class),
                      account_type: newAccount.account_type,
                      parent_code: newAccount.parent_code || undefined,
                    })
                  }
                }}
              >
                {editingAccount ? 'Save' : 'Add'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Upload Dialog */}
      <UploadDialog
        open={showUpload}
        onOpenChange={setShowUpload}
        companies={companies}
        templates={templates}
      />

      {/* New Template Dialog */}
      <Dialog open={showNewTemplate} onOpenChange={setShowNewTemplate}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>New Template</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Name</Label>
              <Input value={newTemplateName} onChange={e => setNewTemplateName(e.target.value)} placeholder="e.g. Standard Romanian Bilant" />
            </div>
            <div className="space-y-2">
              <Label>Company (optional)</Label>
              <Select value={newTemplateCompany} onValueChange={setNewTemplateCompany}>
                <SelectTrigger>
                  <SelectValue placeholder="Global (all companies)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="global">Global (all companies)</SelectItem>
                  {companies.map(c => (
                    <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowNewTemplate(false)}>Cancel</Button>
              <Button
                disabled={!newTemplateName.trim() || createTplMut.isPending}
                onClick={() => createTplMut.mutate({
                  name: newTemplateName.trim(),
                  company_id: newTemplateCompany && newTemplateCompany !== 'global' ? Number(newTemplateCompany) : undefined,
                })}
              >
                Create
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={() => setDeleteTarget(null)}
        title={`Delete ${deleteTarget?.type}?`}
        description={`Are you sure you want to delete "${deleteTarget?.name}"? This action cannot be undone.`}
        onConfirm={handleDelete}
        confirmLabel="Delete"
        variant="destructive"
      />

      {/* ANAF PDF Import Dialog */}
      <Dialog open={showAnafImport} onOpenChange={(v) => { if (!v) { setAnafFile(null); setAnafName(''); setAnafCompany('') }; setShowAnafImport(v) }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Import ANAF Template from PDF</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Template Name</Label>
              <Input value={anafName} onChange={e => setAnafName(e.target.value)} placeholder="e.g. ANAF F10 Standard" />
            </div>
            <div className="space-y-2">
              <Label>Company (optional)</Label>
              <Select value={anafCompany} onValueChange={setAnafCompany}>
                <SelectTrigger>
                  <SelectValue placeholder="Global (all companies)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="global">Global (all companies)</SelectItem>
                  {companies.map(c => (
                    <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>ANAF PDF File *</Label>
              <input
                type="file"
                accept=".pdf"
                onChange={e => { const f = e.target.files?.[0]; if (f) setAnafFile(f) }}
                className="hidden"
                id="anaf-pdf-input"
              />
              <div
                onClick={() => document.getElementById('anaf-pdf-input')?.click()}
                className="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 border-muted-foreground/25 hover:border-muted-foreground/50 transition-colors"
              >
                {anafFile ? (
                  <div className="flex items-center gap-2">
                    <FileSpreadsheet className="h-5 w-5 text-red-600" />
                    <span className="text-sm font-medium">{anafFile.name}</span>
                    <span className="text-xs text-muted-foreground">({(anafFile.size / 1024).toFixed(0)} KB)</span>
                    <Button variant="ghost" size="icon" className="h-6 w-6" onClick={(e) => { e.stopPropagation(); setAnafFile(null) }}>
                      <X className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                ) : (
                  <>
                    <FileUp className="mb-2 h-8 w-8 text-muted-foreground" />
                    <p className="text-sm text-muted-foreground">Click to upload ANAF bilant PDF</p>
                    <p className="text-xs text-muted-foreground">Official XFA-based ANAF F10 form</p>
                  </>
                )}
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => { setShowAnafImport(false); setAnafFile(null); setAnafName(''); setAnafCompany('') }}>Cancel</Button>
              <Button
                disabled={!anafFile || anafImportMut.isPending}
                onClick={() => anafImportMut.mutate()}
              >
                {anafImportMut.isPending ? 'Importing...' : 'Import Template'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ── Row Components ──

function GenerationRow({ gen, onView, onDownload, onDelete }: {
  gen: BilantGeneration
  onView: () => void
  onDownload: () => void
  onDelete: () => void
}) {
  return (
    <TableRow className="cursor-pointer hover:bg-muted/50" onClick={onView}>
      <TableCell className="font-medium">{gen.company_name || '-'}</TableCell>
      <TableCell>{gen.period_label || '-'}</TableCell>
      <TableCell className="text-muted-foreground text-xs">{gen.template_name || '-'}</TableCell>
      <TableCell>
        <Badge variant="secondary" className={statusColors[gen.status] || ''}>
          {gen.status}
        </Badge>
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">{fmtDate(gen.created_at)}</TableCell>
      <TableCell className="text-xs text-muted-foreground">{gen.generated_by_name || '-'}</TableCell>
      <TableCell>
        <div className="flex items-center gap-1" onClick={e => e.stopPropagation()}>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onView} title="View">
            <Eye className="h-3.5 w-3.5" />
          </Button>
          {gen.status === 'completed' && (
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onDownload} title="Download">
              <Download className="h-3.5 w-3.5" />
            </Button>
          )}
          <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={onDelete} title="Delete">
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </TableCell>
    </TableRow>
  )
}

function TemplateRow({ tpl, onEdit, onDuplicate, onDelete }: {
  tpl: BilantTemplate
  onEdit: () => void
  onDuplicate: () => void
  onDelete: () => void
}) {
  return (
    <TableRow>
      <TableCell className="font-medium">{tpl.name}</TableCell>
      <TableCell className="text-muted-foreground text-xs">{tpl.company_name || 'Global'}</TableCell>
      <TableCell>{tpl.row_count}</TableCell>
      <TableCell>
        {tpl.is_default && <Badge variant="secondary" className="bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400">Default</Badge>}
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">v{tpl.version}</TableCell>
      <TableCell>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onEdit} title="Edit">
            <Pencil className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onDuplicate} title="Duplicate">
            <Copy className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={onDelete} title="Delete">
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </TableCell>
    </TableRow>
  )
}
