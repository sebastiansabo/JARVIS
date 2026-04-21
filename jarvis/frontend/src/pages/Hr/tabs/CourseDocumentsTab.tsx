import { useQuery } from '@tanstack/react-query'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/shared/EmptyState'
import { FolderOpen } from 'lucide-react'
import { dmsApi } from '@/api/dms'
import type { DmsModuleLink } from '@/types/dms'
import { fmtDate } from './utils'

export function CourseDocumentsTab({ courseId }: { courseId: number }) {
  const { data: dmsLinks, isLoading } = useQuery({
    queryKey: ['course-dms-links', courseId],
    queryFn: () => dmsApi.getModuleLinks('hr_course', courseId),
  })
  const documents: DmsModuleLink[] = dmsLinks?.links ?? []

  if (isLoading) return <Skeleton className="h-32 w-full" />

  if (documents.length === 0) {
    return (
      <EmptyState
        icon={<FolderOpen className="h-8 w-8" />}
        title="No documents linked"
        description="Link documents from the DMS module."
      />
    )
  }

  return (
    <div className="space-y-1.5">
      {documents.map((doc) => (
        <div key={doc.id} className="flex items-center justify-between rounded-lg border px-3 py-2">
          <div>
            <div className="text-sm font-medium">
              {doc.link_type === 'folder' ? doc.folder_name : doc.document_title}
            </div>
            <div className="text-xs text-muted-foreground">
              {doc.link_type === 'folder' ? 'Folder' : 'Document'} — Linked by {doc.linked_by_name ?? 'Unknown'} on {fmtDate(doc.created_at)}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
