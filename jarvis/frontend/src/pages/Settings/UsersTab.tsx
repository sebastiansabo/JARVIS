import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Checkbox } from '@/components/ui/checkbox'
import { SearchInput } from '@/components/shared/SearchInput'
import { SearchSelect } from '@/components/shared/SearchSelect'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { usersApi } from '@/api/users'
import { rolesApi } from '@/api/roles'
import { hrApi } from '@/api/hr'
import { toast } from 'sonner'
import type { UserDetail, CreateUserInput, UpdateUserInput } from '@/types/users'

export default function UsersTab() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [editUser, setEditUser] = useState<UserDetail | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [showBulkDelete, setShowBulkDelete] = useState(false)

  const { data: users = [], isLoading } = useQuery({
    queryKey: ['settings', 'users'],
    queryFn: usersApi.getUsers,
  })

  const { data: roles = [] } = useQuery({
    queryKey: ['settings', 'roles'],
    queryFn: rolesApi.getRoles,
  })

  const createMutation = useMutation({
    mutationFn: (data: CreateUserInput) => usersApi.createUser(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'users'] })
      setShowAdd(false)
      toast.success('User created')
    },
    onError: () => toast.error('Failed to create user'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateUserInput }) => usersApi.updateUser(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'users'] })
      setEditUser(null)
      toast.success('User updated')
    },
    onError: () => toast.error('Failed to update user'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => usersApi.deleteUser(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'users'] })
      setDeleteId(null)
      toast.success('User deleted')
    },
    onError: () => toast.error('Failed to delete user'),
  })

  const bulkDeleteMutation = useMutation({
    mutationFn: () => usersApi.bulkDeleteUsers(selectedIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'users'] })
      setSelectedIds([])
      setShowBulkDelete(false)
      toast.success('Users deleted')
    },
    onError: () => toast.error('Failed to delete users'),
  })

  const filtered = users.filter(
    (u) =>
      !search ||
      u.name.toLowerCase().includes(search.toLowerCase()) ||
      u.email.toLowerCase().includes(search.toLowerCase()),
  )

  const toggleSelect = (id: number) =>
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]))

  const toggleAll = () =>
    setSelectedIds((prev) => (prev.length === filtered.length ? [] : filtered.map((u) => u.id)))

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Users</CardTitle>
          <div className="flex gap-2">
            {selectedIds.length > 0 && (
              <Button variant="destructive" size="sm" onClick={() => setShowBulkDelete(true)}>
                <Trash2 className="mr-1.5 h-4 w-4" />
                Delete ({selectedIds.length})
              </Button>
            )}
            <Button size="sm" onClick={() => setShowAdd(true)}>
              <Plus className="mr-1.5 h-4 w-4" />
              Add User
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <SearchInput value={search} onChange={setSearch} placeholder="Search users..." className="mb-4" />

        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState title="No users found" description={search ? 'Try a different search term.' : 'Add your first user.'} />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">
                  <Checkbox
                    checked={selectedIds.length === filtered.length && filtered.length > 0}
                    onCheckedChange={toggleAll}
                  />
                </TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Company</TableHead>
                <TableHead>Brand</TableHead>
                <TableHead>Department</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-20">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((user) => (
                <TableRow key={user.id}>
                  <TableCell>
                    <Checkbox
                      checked={selectedIds.includes(user.id)}
                      onCheckedChange={() => toggleSelect(user.id)}
                    />
                  </TableCell>
                  <TableCell className="font-medium">{user.name}</TableCell>
                  <TableCell className="text-muted-foreground">{user.email}</TableCell>
                  <TableCell>{user.role_name}</TableCell>
                  <TableCell className="text-muted-foreground">{user.company || '-'}</TableCell>
                  <TableCell className="text-muted-foreground">{user.brand || '-'}</TableCell>
                  <TableCell className="text-muted-foreground">{user.department || '-'}</TableCell>
                  <TableCell>
                    <StatusBadge status={user.is_active ? 'active' : 'archived'} />
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="sm" onClick={() => setEditUser(user)}>
                        Edit
                      </Button>
                      <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setDeleteId(user.id)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>

      {/* Add/Edit Dialog */}
      <UserFormDialog
        open={showAdd || !!editUser}
        user={editUser}
        roles={roles}
        onClose={() => {
          setShowAdd(false)
          setEditUser(null)
        }}
        onSave={(data) => {
          if (editUser) {
            updateMutation.mutate({ id: editUser.id, data: data as UpdateUserInput })
          } else {
            createMutation.mutate(data as CreateUserInput)
          }
        }}
        isPending={createMutation.isPending || updateMutation.isPending}
      />

      {/* Delete Confirm */}
      <ConfirmDialog
        open={!!deleteId}
        onOpenChange={() => setDeleteId(null)}
        title="Delete User"
        description="This action cannot be undone."
        onConfirm={() => deleteId && deleteMutation.mutate(deleteId)}
        destructive
      />

      {/* Bulk Delete Confirm */}
      <ConfirmDialog
        open={showBulkDelete}
        onOpenChange={setShowBulkDelete}
        title={`Delete ${selectedIds.length} users?`}
        description="This action cannot be undone."
        onConfirm={() => bulkDeleteMutation.mutate()}
        destructive
      />
    </Card>
  )
}

function UserFormDialog({
  open,
  user,
  roles,
  onClose,
  onSave,
  isPending,
}: {
  open: boolean
  user: UserDetail | null
  roles: { id: number; name: string }[]
  onClose: () => void
  onSave: (data: CreateUserInput & Record<string, unknown>) => void
  isPending: boolean
}) {
  const [form, setForm] = useState({
    name: '',
    email: '',
    phone: '',
    role_id: '',
    company: '',
    brand: '',
    department: '',
    is_active: true,
    password: '',
  })

  // Structure queries
  const { data: companies = [] } = useQuery({
    queryKey: ['hr-structure-companies'],
    queryFn: () => hrApi.getStructureCompanies(),
    enabled: open,
  })

  const { data: brands = [] } = useQuery({
    queryKey: ['hr-structure-brands', form.company],
    queryFn: () => hrApi.getStructureBrands(form.company),
    enabled: open && !!form.company,
  })

  const { data: departments = [] } = useQuery({
    queryKey: ['hr-structure-departments', form.company],
    queryFn: () => hrApi.getStructureDepartments(form.company),
    enabled: open && !!form.company,
  })

  const resetForm = () =>
    setForm(
      user
        ? {
            name: user.name,
            email: user.email,
            phone: user.phone || '',
            role_id: String(user.role_id),
            company: user.company || '',
            brand: user.brand || '',
            department: user.department || '',
            is_active: user.is_active,
            password: '',
          }
        : { name: '', email: '', phone: '', role_id: '', company: '', brand: '', department: '', is_active: true, password: '' },
    )

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) onClose()
        else resetForm()
      }}
    >
      <DialogContent className="sm:max-w-md" onOpenAutoFocus={resetForm}>
        <DialogHeader>
          <DialogTitle>{user ? 'Edit User' : 'Add User'}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Name</Label>
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div className="grid gap-2">
            <Label>Email</Label>
            <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </div>
          <div className="grid gap-2">
            <Label>Phone</Label>
            <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          </div>
          <div className="grid gap-2">
            <Label>Role</Label>
            <Select value={form.role_id} onValueChange={(v) => setForm({ ...form, role_id: v })}>
              <SelectTrigger>
                <SelectValue placeholder="Select role" />
              </SelectTrigger>
              <SelectContent>
                {roles.map((r) => (
                  <SelectItem key={r.id} value={String(r.id)}>
                    {r.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label>Company</Label>
            <SearchSelect
              value={form.company}
              onValueChange={(v) => setForm({ ...form, company: v, brand: '', department: '' })}
              options={companies.map((c) => ({ value: c, label: c }))}
              placeholder="Select company..."
              searchPlaceholder="Search company..."
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Brand</Label>
              <SearchSelect
                value={form.brand}
                onValueChange={(v) => setForm({ ...form, brand: v })}
                options={brands.map((b) => ({ value: b, label: b }))}
                placeholder={form.company ? 'Select brand...' : 'Select company first'}
                searchPlaceholder="Search brand..."
                emptyMessage={form.company ? 'No brands found.' : 'Select a company first.'}
              />
            </div>
            <div className="grid gap-2">
              <Label>Department</Label>
              <SearchSelect
                value={form.department}
                onValueChange={(v) => setForm({ ...form, department: v })}
                options={departments.map((d) => ({ value: d, label: d }))}
                placeholder={form.company ? 'Select department...' : 'Select company first'}
                searchPlaceholder="Search department..."
                emptyMessage={form.company ? 'No departments found.' : 'Select a company first.'}
              />
            </div>
          </div>
          {!user && (
            <div className="grid gap-2">
              <Label>Password</Label>
              <Input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            </div>
          )}
          <div className="flex items-center gap-2">
            <Switch checked={form.is_active} onCheckedChange={(v) => setForm({ ...form, is_active: v })} />
            <Label>Active</Label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={isPending || !form.name || !form.email}
            onClick={() =>
              onSave({
                ...form,
                role_id: form.role_id ? Number(form.role_id) : undefined,
                password: form.password || undefined,
              })
            }
          >
            {isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
