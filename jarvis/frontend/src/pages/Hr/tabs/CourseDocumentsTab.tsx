import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/shared/EmptyState'
import { FolderOpen, Link2, Search, Unlink, Folder } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { dmsApi } from '@/api/dms'
import { toast } from 'sonner'
import { useDebounce } from '@/lib/utils'
import type { DmsModuleLink, DmsFolder } from '@/types/dms'
import { fmtDate } from './utils'

export function CourseDocumentsTab({ courseId }: { courseId: number }) {
  const queryClient = useQueryClient()
  const [linkDialogOpen, setLinkDialogOpen] = useState(false)

  const { data: dmsLinks, isLoading } = useQuery({
    queryKey: ['course-dms-links', courseId],
    queryFn: () => dmsApi.getModuleLinks('hr_course', courseId),
  })
  const documents: DmsModuleLink[] = dmsLinks?.links ?? []

  const unlinkMut = useMutation({
    mutationFn: (doc: DmsModuleLink) => {
      if (doc.link_type === 'folder' && doc.folder_id) {
        return dmsApi.unlinkFolder(doc.folder_id, 'hr_course', courseId)
      }
      // For document links, delete via the link id
      return dmsApi.unlinkFolder(doc.document_id!, 'hr_course', courseId)
    },
    onSuccess: () => {
      toast.success('Document unlinked')
      queryClient.invalidateQueries({ queryKey: ['course-dms-links', courseId] })
    },
    onError: () => toast.error('Failed to unlink'),
  })

  if (isLoading) return <Skeleton className="h-32 w-full" />

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium flex items-center gap-1.5">
          <Link2 className="h-4 w-4" />
          Linked Documents ({documents.length})
        </p>
        <Button variant="outline" size="sm" onClick={() => setLinkDialogOpen(true)}>
          <Link2 className="h-3.5 w-3.5 mr-1" />
          Link Folder
        </Button>
      </div>

      {documents.length === 0 ? (
        <EmptyState
          icon={<FolderOpen className="h-8 w-8" />}
          title="No documents linked"
          description="Search and link DMS folders to this course."
        />
      ) : (
        <div className="space-y-1.5">
          {documents.map((doc) => (
            <div key={doc.id} className="flex items-center justify-between rounded-lg border px-3 py-2">
              <div className="flex items-center gap-2 min-w-0">
                <FolderOpen className="h-4 w-4 text-muted-foreground shrink-0" />
                <div className="min-w-0">
                  <div className="text-sm font-medium truncate">
                    {doc.link_type === 'folder' ? doc.folder_name : doc.document_title}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {doc.link_type === 'folder' ? 'Folder' : 'Document'} — Linked by {doc.linked_by_name ?? 'Unknown'} on {fmtDate(doc.created_at)}
                  </div>
                </div>
              </div>
              <Button variant="ghost" size="icon" className="h-6 w-6 text-destructive shrink-0"
                onClick={() => unlinkMut.mutate(doc)} title="Unlink">
                <Unlink className="h-3 w-3" />
              </Button>
            </div>
          ))}
        </div>
      )}

      {/* Link Folder Dialog */}
      <LinkFolderDialog
        open={linkDialogOpen}
        onOpenChange={setLinkDialogOpen}
        courseId={courseId}
        linkedFolderIds={documents.filter(d => d.link_type === 'folder').map(d => d.folder_id!)}
      />
    </div>
  )
}

function LinkFolderDialog({
  open,
  onOpenChange,
  courseId,
  linkedFolderIds,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  courseId: number
  linkedFolderIds: number[]
}) {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounce(search, 300)

  const { data, isLoading: isSearching } = useQuery({
    queryKey: ['dms-folder-search', debouncedSearch],
    queryFn: () => dmsApi.searchFolders(debouncedSearch),
    enabled: open && debouncedSearch.length >= 2,
  })
  const results: DmsFolder[] = data?.folders ?? []

  const linkMut = useMutation({
    mutationFn: (folderId: number) => dmsApi.linkFolder(folderId, 'hr_course', courseId),
    onSuccess: () => {
      toast.success('Folder linked')
      queryClient.invalidateQueries({ queryKey: ['course-dms-links', courseId] })
      queryClient.invalidateQueries({ queryKey: ['dms-folder-search'] })
    },
    onError: () => toast.error('Failed to link folder'),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" aria-describedby={undefined}>
        <DialogHeader><DialogTitle>Link DMS Folder</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search folders by name..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
              autoFocus
            />
          </div>

          {isSearching && <div className="text-center text-xs text-muted-foreground py-2">Searching...</div>}

          <div className="max-h-[300px] overflow-y-auto space-y-1">
            {results.length === 0 && debouncedSearch.length >= 2 && !isSearching ? (
              <p className="text-sm text-muted-foreground text-center py-4">No folders found</p>
            ) : results.map((folder) => {
              const isLinked = linkedFolderIds.includes(folder.id)
              return (
                <div
                  key={folder.id}
                  className={`flex items-center gap-3 rounded-md border p-2.5 ${isLinked ? 'opacity-50' : 'hover:bg-muted/50'}`}
                >
                  <Folder className="h-4 w-4 text-muted-foreground shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium truncate">{folder.name}</div>
                    <div className="text-xs text-muted-foreground truncate">{folder.path}</div>
                  </div>
                  {isLinked ? (
                    <span className="text-xs text-muted-foreground shrink-0">Linked</span>
                  ) : (
                    <Button variant="ghost" size="sm" className="h-7 shrink-0" disabled={linkMut.isPending}
                      onClick={() => linkMut.mutate(folder.id)}>
                      <Link2 className="h-3.5 w-3.5 mr-1" />Link
                    </Button>
                  )}
                </div>
              )
            })}
          </div>
        </div>
        <div className="flex justify-end">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>Done</Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
