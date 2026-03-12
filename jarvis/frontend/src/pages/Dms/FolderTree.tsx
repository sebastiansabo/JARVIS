import { useState, useMemo, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ChevronRight, ChevronDown, FolderOpen, Folder, Plus,
  MoreHorizontal, Edit2, Trash2, FileText, RefreshCw,
  Cloud, ExternalLink, ChevronsDownUp, ChevronsUpDown, Shield,
} from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import {
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
} from '@/components/ui/tooltip'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { dmsApi } from '@/api/dms'
import type { DmsFolder } from '@/types/dms'
import FolderACLDialog from './FolderACLDialog'

interface FolderTreeProps {
  selectedFolderId: number | null
  onSelectFolder: (folderId: number | null) => void
  className?: string
}

interface TreeNode extends DmsFolder {
  children: TreeNode[]
}

function buildTree(folders: DmsFolder[]): TreeNode[] {
  const map = new Map<number, TreeNode>()
  const roots: TreeNode[] = []

  for (const f of folders) {
    map.set(f.id, { ...f, children: [] })
  }
  for (const f of folders) {
    const node = map.get(f.id)!
    if (f.parent_id && map.has(f.parent_id)) {
      map.get(f.parent_id)!.children.push(node)
    } else {
      roots.push(node)
    }
  }
  return roots
}

/** Collect all folder IDs that have children (expandable nodes). */
function collectExpandableIds(nodes: TreeNode[]): number[] {
  const ids: number[] = []
  for (const n of nodes) {
    if (n.children.length > 0 || n.subfolder_count > 0) {
      ids.push(n.id)
      ids.push(...collectExpandableIds(n.children))
    }
  }
  return ids
}

function TreeItem({
  node, depth, selectedId, expandedIds, onSelect, onToggle, onCreateSub, onEdit, onDelete, onDriveSync, onManagePerms,
}: {
  node: TreeNode
  depth: number
  selectedId: number | null
  expandedIds: Set<number>
  onSelect: (id: number) => void
  onToggle: (id: number) => void
  onCreateSub: (parentId: number) => void
  onEdit: (folder: DmsFolder) => void
  onDelete: (folder: DmsFolder) => void
  onDriveSync: (folderId: number) => void
  onManagePerms: (folder: DmsFolder) => void
}) {
  const isExpanded = expandedIds.has(node.id)
  const isSelected = selectedId === node.id
  const hasChildren = node.children.length > 0 || node.subfolder_count > 0
  const isRoot = node.depth === 0 && !node.parent_id
  const FolderIcon = isExpanded ? FolderOpen : Folder

  return (
    <>
      <div
        className={cn(
          'group flex items-center gap-1 px-2 py-1 rounded-md cursor-pointer text-sm hover:bg-muted/50 transition-colors',
          isSelected && 'bg-primary/10 text-primary font-medium',
        )}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={() => onSelect(node.id)}
      >
        {/* Expand/collapse toggle */}
        <button
          className="shrink-0 w-4 h-4 flex items-center justify-center"
          onClick={(e) => { e.stopPropagation(); if (hasChildren) onToggle(node.id) }}
        >
          {hasChildren ? (
            isExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />
          ) : <span className="w-3" />}
        </button>

        <FolderIcon
          className="h-4 w-4 shrink-0"
          style={{ color: node.color || '#6c757d' }}
        />

        <span className="truncate flex-1">{node.name}</span>

        {/* Drive synced indicator */}
        {node.drive_folder_url && (
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <a
                  href={node.drive_folder_url!}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0 text-blue-500 hover:text-blue-700"
                  onClick={(e) => e.stopPropagation()}
                >
                  <Cloud className="h-3 w-3" />
                </a>
              </TooltipTrigger>
              <TooltipContent>Open in Google Drive</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}

        {node.document_count > 0 && (
          <Badge variant="secondary" className="h-4 px-1 text-[10px] font-normal">
            {node.document_count}
          </Badge>
        )}

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity h-5 w-5 flex items-center justify-center rounded hover:bg-muted"
              onClick={(e) => e.stopPropagation()}
            >
              <MoreHorizontal className="h-3 w-3" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuItem onClick={() => onCreateSub(node.id)}>
              <Plus className="h-3 w-3 mr-2" /> New Subfolder
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => onDriveSync(node.id)}>
              <Cloud className="h-3 w-3 mr-2" /> Sync to Drive
            </DropdownMenuItem>
            {node.drive_folder_url && (
              <DropdownMenuItem onClick={() => window.open(node.drive_folder_url!, '_blank')}>
                <ExternalLink className="h-3 w-3 mr-2" /> Open in Drive
              </DropdownMenuItem>
            )}
            {!isRoot && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => onEdit(node)}>
                  <Edit2 className="h-3 w-3 mr-2" /> Edit
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => onManagePerms(node)}>
                  <Shield className="h-3 w-3 mr-2" /> Permissions
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem className="text-destructive" onClick={() => onDelete(node)}>
                  <Trash2 className="h-3 w-3 mr-2" /> Delete
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {isExpanded && node.children.map((child) => (
        <TreeItem
          key={child.id}
          node={child}
          depth={depth + 1}
          selectedId={selectedId}
          expandedIds={expandedIds}
          onSelect={onSelect}
          onToggle={onToggle}
          onCreateSub={onCreateSub}
          onEdit={onEdit}
          onDelete={onDelete}
          onDriveSync={onDriveSync}
          onManagePerms={onManagePerms}
        />
      ))}
    </>
  )
}

export default function FolderTree({ selectedFolderId, onSelectFolder, className }: FolderTreeProps) {
  const queryClient = useQueryClient()
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set())
  const [createOpen, setCreateOpen] = useState(false)
  const [createParentId, setCreateParentId] = useState<number | null>(null)
  const [editFolder, setEditFolder] = useState<DmsFolder | null>(null)
  const [deleteFolder, setDeleteFolder] = useState<DmsFolder | null>(null)
  const [aclFolder, setAclFolder] = useState<DmsFolder | null>(null)
  const [folderName, setFolderName] = useState('')
  const [folderDesc, setFolderDesc] = useState('')
  const [folderInherit, setFolderInherit] = useState(true)

  const { data, isLoading } = useQuery({
    queryKey: ['dms-folder-tree'],
    queryFn: () => dmsApi.getFolderTree(),
  })

  const tree = useMemo(() => buildTree(data?.folders || []), [data])
  const allExpandableIds = useMemo(() => collectExpandableIds(tree), [tree])
  const isAllExpanded = allExpandableIds.length > 0 && allExpandableIds.every((id) => expandedIds.has(id))

  // Auto-expand root company folders on first load
  useEffect(() => {
    if (tree.length > 0 && expandedIds.size === 0) {
      setExpandedIds(new Set(tree.map((n) => n.id)))
    }
  }, [tree]) // eslint-disable-line react-hooks/exhaustive-deps

  const expandAll = () => setExpandedIds(new Set(allExpandableIds))
  const collapseAll = () => setExpandedIds(new Set())

  const createMutation = useMutation({
    mutationFn: (d: { name: string; parent_id?: number; description?: string; inherit_permissions: boolean }) =>
      dmsApi.createFolder(d),
    onSuccess: () => {
      toast.success('Folder created')
      queryClient.invalidateQueries({ queryKey: ['dms-folder-tree'] })
      setCreateOpen(false)
      setFolderName('')
      setFolderDesc('')
    },
    onError: () => toast.error('Failed to create folder'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, ...d }: { id: number; name?: string; description?: string; inherit_permissions?: boolean }) =>
      dmsApi.updateFolder(id, d),
    onSuccess: () => {
      toast.success('Folder updated')
      queryClient.invalidateQueries({ queryKey: ['dms-folder-tree'] })
      setEditFolder(null)
    },
    onError: () => toast.error('Failed to update folder'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => dmsApi.deleteFolder(id),
    onSuccess: () => {
      toast.success('Folder deleted')
      queryClient.invalidateQueries({ queryKey: ['dms-folder-tree'] })
      if (selectedFolderId === deleteFolder?.id) onSelectFolder(null)
      setDeleteFolder(null)
    },
    onError: () => toast.error('Failed to delete folder'),
  })

  const syncStructureMutation = useMutation({
    mutationFn: () => dmsApi.syncFolderStructure(),
    onSuccess: (res) => {
      const c = res.created
      toast.success(`Synced: ${c.roots} roots, ${c.year_folders} years, ${c.category_folders} categories`)
      queryClient.invalidateQueries({ queryKey: ['dms-folder-tree'] })
    },
    onError: () => toast.error('Failed to sync structure'),
  })

  const driveSyncMutation = useMutation({
    mutationFn: (folderId: number) => dmsApi.syncFolderToDrive(folderId),
    onSuccess: (res) => {
      if (res.drive_folder_url) {
        toast.success('Synced to Google Drive')
      } else {
        toast.info('Already synced')
      }
      queryClient.invalidateQueries({ queryKey: ['dms-folder-tree'] })
    },
    onError: () => toast.error('Failed to sync to Drive'),
  })

  const driveFullSyncMutation = useMutation({
    mutationFn: () => dmsApi.syncAllFoldersToDrive(),
    onSuccess: (res) => {
      if (res.synced != null) {
        toast.success(`Drive sync: ${res.synced} synced, ${res.skipped} already synced${res.errors ? `, ${res.errors} errors` : ''}`)
      } else {
        toast.error((res as Record<string, unknown>).error as string || 'Drive sync failed')
      }
      queryClient.invalidateQueries({ queryKey: ['dms-folder-tree'] })
    },
    onError: () => toast.error('Failed to sync to Drive'),
  })

  const toggleExpand = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  const handleCreateSub = (parentId: number) => {
    setCreateParentId(parentId)
    setFolderName('')
    setFolderDesc('')
    setFolderInherit(true)
    setCreateOpen(true)
    // Auto-expand parent
    setExpandedIds((prev) => new Set(prev).add(parentId))
  }

  const handleEdit = (folder: DmsFolder) => {
    setEditFolder(folder)
    setFolderName(folder.name)
    setFolderDesc(folder.description || '')
    setFolderInherit(folder.inherit_permissions)
  }

  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b">
        <span className="text-sm font-medium text-muted-foreground">Folders</span>
        <TooltipProvider delayDuration={200}>
          <div className="flex items-center gap-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost" size="icon" className="h-6 w-6"
                  onClick={isAllExpanded ? collapseAll : expandAll}
                >
                  {isAllExpanded
                    ? <ChevronsDownUp className="h-3 w-3" />
                    : <ChevronsUpDown className="h-3 w-3" />}
                </Button>
              </TooltipTrigger>
              <TooltipContent>{isAllExpanded ? 'Collapse all' : 'Expand all'}</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost" size="icon" className="h-6 w-6"
                  onClick={() => syncStructureMutation.mutate()}
                  disabled={syncStructureMutation.isPending}
                >
                  <RefreshCw className={cn('h-3 w-3', syncStructureMutation.isPending && 'animate-spin')} />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Sync Year + Category folders</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost" size="icon" className="h-6 w-6"
                  onClick={() => driveFullSyncMutation.mutate()}
                  disabled={driveFullSyncMutation.isPending}
                >
                  <Cloud className={cn('h-3 w-3', driveFullSyncMutation.isPending && 'animate-spin')} />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Sync all folders to Google Drive</TooltipContent>
            </Tooltip>
          </div>
        </TooltipProvider>
      </div>

      {/* "All Documents" option */}
      <div
        className={cn(
          'flex items-center gap-2 px-3 py-1.5 cursor-pointer text-sm hover:bg-muted/50 transition-colors',
          selectedFolderId === null && 'bg-primary/10 text-primary font-medium',
        )}
        onClick={() => onSelectFolder(null)}
      >
        <FileText className="h-4 w-4 text-muted-foreground" />
        <span>All Documents</span>
      </div>

      {/* Tree */}
      <div className="flex-1 overflow-y-auto py-1">
        {isLoading ? (
          <div className="space-y-1 px-2">
            {[1, 2, 3].map((i) => <Skeleton key={i} className="h-6 w-full" />)}
          </div>
        ) : tree.length === 0 ? (
          <div className="px-3 py-4 text-xs text-muted-foreground text-center">
            No folders yet. Click sync to create structure.
          </div>
        ) : (
          tree.map((node) => (
            <TreeItem
              key={node.id}
              node={node}
              depth={0}
              selectedId={selectedFolderId}
              expandedIds={expandedIds}
              onSelect={onSelectFolder}
              onToggle={toggleExpand}
              onCreateSub={handleCreateSub}
              onEdit={handleEdit}
              onDelete={setDeleteFolder}
              onDriveSync={(id) => driveSyncMutation.mutate(id)}
              onManagePerms={setAclFolder}
            />
          ))
        )}
      </div>

      {/* Create/Edit Dialog */}
      <Dialog open={createOpen || !!editFolder} onOpenChange={(open) => { if (!open) { setCreateOpen(false); setEditFolder(null) } }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{editFolder ? 'Edit Folder' : 'New Folder'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Name</Label>
              <Input value={folderName} onChange={(e) => setFolderName(e.target.value)} placeholder="Folder name" autoFocus />
            </div>
            <div>
              <Label>Description</Label>
              <Input value={folderDesc} onChange={(e) => setFolderDesc(e.target.value)} placeholder="Optional description" />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="inherit"
                checked={folderInherit}
                onCheckedChange={(v) => setFolderInherit(v === true)}
              />
              <Label htmlFor="inherit" className="text-sm font-normal">
                Inherit permissions from parent
              </Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setCreateOpen(false); setEditFolder(null) }}>Cancel</Button>
            <Button
              disabled={!folderName.trim()}
              onClick={() => {
                if (editFolder) {
                  updateMutation.mutate({
                    id: editFolder.id,
                    name: folderName.trim(),
                    description: folderDesc.trim() || undefined,
                    inherit_permissions: folderInherit,
                  })
                } else {
                  createMutation.mutate({
                    name: folderName.trim(),
                    parent_id: createParentId || undefined,
                    description: folderDesc.trim() || undefined,
                    inherit_permissions: folderInherit,
                  })
                }
              }}
            >
              {editFolder ? 'Save' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Permissions Dialog */}
      <FolderACLDialog folder={aclFolder} open={!!aclFolder} onOpenChange={(open) => { if (!open) setAclFolder(null) }} />

      {/* Delete Confirm */}
      <Dialog open={!!deleteFolder} onOpenChange={(open) => { if (!open) setDeleteFolder(null) }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete Folder</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Delete <strong>{deleteFolder?.name}</strong> and all subfolders? Documents inside will be unlinked but not deleted.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteFolder(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => deleteFolder && deleteMutation.mutate(deleteFolder.id)}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
