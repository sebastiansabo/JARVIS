import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { settingsApi } from '@/api/settings'
import { toast } from 'sonner'
import type { Theme, ThemeColors } from '@/types/settings'
import { cn } from '@/lib/utils'

export default function ThemesTab() {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [editTheme, setEditTheme] = useState<Theme | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { data: themes = [], isLoading } = useQuery({
    queryKey: ['settings', 'themes'],
    queryFn: settingsApi.getThemes,
    staleTime: 10 * 60_000,
  })

  const createMutation = useMutation({
    mutationFn: (data: Partial<Theme>) => settingsApi.createTheme(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'themes'] })
      setShowAdd(false)
      toast.success('Theme created')
    },
    onError: () => toast.error('Failed to create theme'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Theme> }) => settingsApi.updateTheme(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'themes'] })
      setEditTheme(null)
      toast.success('Theme updated')
    },
    onError: () => toast.error('Failed to update theme'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => settingsApi.deleteTheme(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'themes'] })
      setDeleteId(null)
      toast.success('Theme deleted')
    },
    onError: () => toast.error('Failed to delete theme'),
  })

  const activateMutation = useMutation({
    mutationFn: (id: number) => settingsApi.activateTheme(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'themes'] })
      toast.success('Theme activated')
    },
    onError: () => toast.error('Failed to activate theme'),
  })

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Themes</CardTitle>
          <Button size="sm" onClick={() => setShowAdd(true)}>
            <Plus className="mr-1.5 h-4 w-4" />
            Add Theme
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : themes.length === 0 ? (
          <EmptyState title="No themes" description="Add your first theme." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="w-32">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {themes.map((theme) => (
                <TableRow key={theme.id}>
                  <TableCell className="font-medium">{theme.theme_name}</TableCell>
                  <TableCell>
                    <StatusBadge status={theme.is_active ? 'active' : 'archived'} />
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {theme.created_at ? new Date(theme.created_at).toLocaleDateString() : '-'}
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      {!theme.is_active && (
                        <Button variant="ghost" size="sm" onClick={() => activateMutation.mutate(theme.id)}>
                          <Check className="h-3.5 w-3.5" />
                        </Button>
                      )}
                      <Button variant="ghost" size="sm" onClick={() => setEditTheme(theme)}>
                        Edit
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive"
                        onClick={() => setDeleteId(theme.id)}
                      >
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

      <ThemeFormDialog
        open={showAdd || !!editTheme}
        theme={editTheme}
        onClose={() => {
          setShowAdd(false)
          setEditTheme(null)
        }}
        onSave={(data) => {
          if (editTheme) {
            updateMutation.mutate({ id: editTheme.id, data })
          } else {
            createMutation.mutate(data)
          }
        }}
        isPending={createMutation.isPending || updateMutation.isPending}
      />

      <ConfirmDialog
        open={!!deleteId}
        onOpenChange={() => setDeleteId(null)}
        title="Delete Theme"
        description="This action cannot be undone."
        onConfirm={() => deleteId && deleteMutation.mutate(deleteId)}
        destructive
      />
    </Card>
  )
}

const COLOR_FIELDS: { key: keyof ThemeColors; label: string }[] = [
  { key: 'bgBody', label: 'Background' },
  { key: 'bgCard', label: 'Card' },
  { key: 'bgInput', label: 'Input' },
  { key: 'bgTableHeader', label: 'Table Header' },
  { key: 'accentPrimary', label: 'Primary' },
  { key: 'accentSuccess', label: 'Success' },
  { key: 'accentWarning', label: 'Warning' },
  { key: 'accentDanger', label: 'Danger' },
  { key: 'textPrimary', label: 'Text Primary' },
  { key: 'textSecondary', label: 'Text Secondary' },
  { key: 'borderColor', label: 'Border' },
]

const DEFAULT_COLORS: ThemeColors = {
  bgBody: '#f5f5f5', bgCard: '#ffffff', bgInput: '#ffffff',
  bgTableHeader: '#f8f9fa', bgTableHover: '#e3f2fd',
  accentPrimary: '#0d6efd', accentSuccess: '#198754',
  accentWarning: '#ffc107', accentDanger: '#dc3545',
  textPrimary: '#212529', textSecondary: '#6c757d',
  borderColor: '#dee2e6', navbarBg: '#6c757d',
}

type ColorMode = 'light' | 'dark'

function ThemeFormDialog({
  open,
  theme,
  onClose,
  onSave,
  isPending,
}: {
  open: boolean
  theme: Theme | null
  onClose: () => void
  onSave: (data: Partial<Theme>) => void
  isPending: boolean
}) {
  const [name, setName] = useState('')
  const [mode, setMode] = useState<ColorMode>('light')
  const [light, setLight] = useState<ThemeColors>({ ...DEFAULT_COLORS })
  const [dark, setDark] = useState<ThemeColors>({ ...DEFAULT_COLORS })

  const resetForm = () => {
    if (theme) {
      setName(theme.theme_name)
      setLight(theme.settings?.light || { ...DEFAULT_COLORS })
      setDark(theme.settings?.dark || { ...DEFAULT_COLORS })
    } else {
      setName('')
      setLight({ ...DEFAULT_COLORS })
      setDark({ ...DEFAULT_COLORS })
    }
    setMode('light')
  }

  const colors = mode === 'light' ? light : dark
  const setColors = mode === 'light' ? setLight : setDark
  const updateColor = (key: keyof ThemeColors, value: string) =>
    setColors((prev) => ({ ...prev, [key]: value }))

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) onClose()
        else resetForm()
      }}
    >
      <DialogContent className="sm:max-w-lg max-h-[80vh] overflow-y-auto" onOpenAutoFocus={resetForm}>
        <DialogHeader>
          <DialogTitle>{theme ? 'Edit Theme' : 'Add Theme'}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Theme Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>

          {/* Light / Dark toggle */}
          <div className="flex gap-1 rounded-lg border p-1">
            {(['light', 'dark'] as ColorMode[]).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={cn(
                  'rounded-md px-4 py-1.5 text-sm font-medium capitalize transition-colors',
                  mode === m ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent',
                )}
              >
                {m}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-3 gap-3">
            {COLOR_FIELDS.map((f) => (
              <div key={f.key} className="space-y-1">
                <Label className="text-xs">{f.label}</Label>
                <div className="flex gap-1">
                  <input
                    type="color"
                    value={colors[f.key] || '#000000'}
                    onChange={(e) => updateColor(f.key, e.target.value)}
                    className="h-8 w-8 cursor-pointer rounded border"
                  />
                  <Input
                    value={colors[f.key] || ''}
                    onChange={(e) => updateColor(f.key, e.target.value)}
                    placeholder="#000000"
                    className="h-8 text-xs"
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={isPending || !name}
            onClick={() => onSave({ theme_name: name, settings: { light, dark } })}
          >
            {isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
