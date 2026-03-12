import { useQuery } from '@tanstack/react-query'
import { History, FolderOpen, FileText, Shield } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { dmsApi } from '@/api/dms'
import type { DmsAuditEntry } from '@/types/dms'

interface AuditLogProps {
  folderId?: number
  entityType?: string
  entityId?: number
  limit?: number
  className?: string
}

const ACTION_COLORS: Record<string, string> = {
  created: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  updated: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  deleted: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  moved: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400',
  linked: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-400',
  unlinked: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  permission_granted: 'bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-400',
  permission_revoked: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
  batch_permission_update: 'bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-400',
}

const ENTITY_ICONS: Record<string, typeof FolderOpen> = {
  folder: FolderOpen,
  document: FileText,
  acl: Shield,
}

function formatTime(iso: string) {
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()

  if (diff < 60_000) return 'Just now'
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)}m ago`
  if (diff < 86400_000) return `${Math.floor(diff / 3600_000)}h ago`
  if (diff < 604800_000) return `${Math.floor(diff / 86400_000)}d ago`
  return d.toLocaleDateString('ro-RO', { day: '2-digit', month: 'short' })
}

function ChangesSummary({ changes }: { changes: Record<string, unknown> | null }) {
  if (!changes || Object.keys(changes).length === 0) return null

  const items = Object.entries(changes).slice(0, 3)
  return (
    <div className="mt-1 space-y-0.5">
      {items.map(([key, val]) => {
        if (typeof val === 'object' && val && 'old' in val && 'new' in val) {
          const v = val as { old: unknown; new: unknown }
          return (
            <div key={key} className="text-[11px] text-muted-foreground">
              <span className="font-medium">{key}</span>: <span className="line-through">{String(v.old ?? '—')}</span> → {String(v.new ?? '—')}
            </div>
          )
        }
        return (
          <div key={key} className="text-[11px] text-muted-foreground">
            <span className="font-medium">{key}</span>: {String(val ?? '—')}
          </div>
        )
      })}
    </div>
  )
}

export default function AuditLog({ folderId, entityType, entityId, limit = 50, className }: AuditLogProps) {
  const { data, isLoading } = useQuery({
    queryKey: ['dms-audit', folderId, entityType, entityId],
    queryFn: () => {
      if (folderId) return dmsApi.getFolderActivity(folderId)
      if (entityType && entityId) return dmsApi.getEntityAudit(entityType, entityId)
      return dmsApi.getAuditLog({ limit })
    },
  })

  const entries: DmsAuditEntry[] = data?.entries || []

  if (isLoading) {
    return (
      <div className={cn('space-y-2', className)}>
        {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
      </div>
    )
  }

  if (entries.length === 0) {
    return (
      <div className={cn('text-center py-6 text-sm text-muted-foreground', className)}>
        <History className="h-8 w-8 mx-auto mb-2 opacity-40" />
        No activity recorded yet.
      </div>
    )
  }

  return (
    <div className={cn('space-y-1', className)}>
      {entries.map((entry) => {
        const Icon = ENTITY_ICONS[entry.entity_type] || FileText
        return (
          <div key={entry.id} className="flex gap-2 px-2 py-1.5 rounded hover:bg-muted/30 transition-colors">
            <Icon className="h-4 w-4 mt-0.5 shrink-0 text-muted-foreground" />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-sm font-medium">{entry.user_name || 'System'}</span>
                <Badge variant="secondary" className={cn('text-[10px] px-1 py-0', ACTION_COLORS[entry.action] || '')}>
                  {entry.action.replace(/_/g, ' ')}
                </Badge>
                <span className="text-xs text-muted-foreground">{entry.entity_type} #{entry.entity_id}</span>
              </div>
              <ChangesSummary changes={entry.changes} />
            </div>
            <span className="text-[11px] text-muted-foreground whitespace-nowrap mt-0.5">
              {formatTime(entry.created_at)}
            </span>
          </div>
        )
      })}
    </div>
  )
}
