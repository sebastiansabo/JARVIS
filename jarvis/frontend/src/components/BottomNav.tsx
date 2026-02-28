import { useMemo } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { LayoutDashboard, Calculator, FolderOpen, Bot, MoreHorizontal } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/hooks/useAuth'
import { settingsApi } from '@/api/settings'

interface BottomNavItem {
  path: string
  label: string
  icon: React.ElementType
  moduleKey?: string
  permission?: string
  /** If true, fires onMore instead of navigating */
  isMore?: boolean
}

const bottomNavDef: BottomNavItem[] = [
  { path: '/app/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/app/accounting', label: 'Accounting', icon: Calculator, moduleKey: 'accounting', permission: 'can_access_accounting' },
  { path: '/app/dms', label: 'Documents', icon: FolderOpen, moduleKey: 'dms' },
  { path: '/app/ai-agent', label: 'AI Agent', icon: Bot, moduleKey: 'ai_agent' },
  { path: '', label: 'More', icon: MoreHorizontal, isMore: true },
]

interface BottomNavProps {
  onMore: () => void
}

export function BottomNav({ onMore }: BottomNavProps) {
  const { user } = useAuth()
  const location = useLocation()

  const { data: menuData } = useQuery({
    queryKey: ['module-menu'],
    queryFn: settingsApi.getModuleMenu,
    staleTime: 5 * 60 * 1000,
  })

  const visibleItems = useMemo(() => {
    const dbModuleMap = menuData?.items
      ? new Map(menuData.items.map((i: { module_key: string }) => [i.module_key, true]))
      : null

    return bottomNavDef.filter((item) => {
      if (item.isMore) return true
      if (item.permission && !user?.[item.permission as keyof typeof user]) return false
      if (item.moduleKey && dbModuleMap !== null) return dbModuleMap.has(item.moduleKey)
      return true
    })
  }, [user, menuData])

  return (
    <nav className="fixed inset-x-0 bottom-0 z-50 flex h-14 items-center justify-around border-t bg-background pb-safe md:hidden">
      {visibleItems.map((item) => {
        const Icon = item.icon
        const isActive = item.path
          ? item.path === '/app/accounting'
            ? location.pathname.startsWith('/app/accounting') || location.pathname.startsWith('/app/statements') || location.pathname.startsWith('/app/efactura')
            : location.pathname.startsWith(item.path)
          : false

        if (item.isMore) {
          return (
            <button
              key="more"
              onClick={onMore}
              className="flex flex-1 flex-col items-center justify-center gap-0.5 py-1 text-muted-foreground transition-colors active:text-foreground"
            >
              <Icon className="h-5 w-5" />
              <span className="text-[10px] font-medium">{item.label}</span>
            </button>
          )
        }

        return (
          <Link
            key={item.path}
            to={item.path}
            className={cn(
              'flex flex-1 flex-col items-center justify-center gap-0.5 py-1 transition-colors',
              isActive
                ? 'text-primary'
                : 'text-muted-foreground active:text-foreground',
            )}
          >
            <Icon className={cn('h-5 w-5', isActive && 'text-primary')} />
            <span className={cn('text-[10px] font-medium', isActive && 'text-primary')}>{item.label}</span>
          </Link>
        )
      })}
    </nav>
  )
}
