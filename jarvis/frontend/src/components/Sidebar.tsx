import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { LayoutDashboard, Bot, Calculator, Users, Landmark, FileText, Settings, LogOut, UserCircle, PanelLeftClose, PanelLeft, ChevronDown, ChevronRight, ClipboardCheck, Megaphone } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/hooks/useAuth'
import { useAiAgentStore } from '@/stores/aiAgentStore'
import { ThemeToggle } from './ThemeToggle'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ApprovalBadge } from './ApprovalBadge'
import { NotificationBell } from './NotificationBell'

interface NavItem {
  path: string
  label: string
  icon: React.ElementType
  permission?: string
  external?: boolean
  children?: NavItem[]
  badge?: React.ComponentType
  action?: () => void
}

const AI_AGENT_ITEM_LABEL = 'AI Agent'

const navItemsDef: Omit<NavItem, 'action'>[] = [
  { path: '/app/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '', label: AI_AGENT_ITEM_LABEL, icon: Bot },
  {
    path: '/app/accounting',
    label: 'Accounting',
    icon: Calculator,
    permission: 'can_access_accounting',
    children: [
      { path: '/app/accounting', label: 'Invoices', icon: Calculator },
      { path: '/app/statements', label: 'Statements', icon: Landmark },
      { path: '/app/efactura', label: 'e-Factura', icon: FileText },
    ],
  },
  { path: '/app/hr', label: 'HR', icon: Users, permission: 'can_access_hr' },
  { path: '/app/approvals', label: 'Approvals', icon: ClipboardCheck, badge: ApprovalBadge },
  { path: '/app/marketing', label: 'Marketing', icon: Megaphone },
  { path: '/app/settings', label: 'Settings', icon: Settings, permission: 'can_access_settings' },
]

interface SidebarProps {
  collapsed?: boolean
  onToggle?: () => void
}

export function Sidebar({ collapsed = false, onToggle }: SidebarProps) {
  const { user } = useAuth()
  const location = useLocation()
  const toggleWidget = useAiAgentStore((s) => s.toggleWidget)

  // Wire up AI Agent action
  const navItems: NavItem[] = navItemsDef.map((item) =>
    item.label === AI_AGENT_ITEM_LABEL ? { ...item, action: toggleWidget } : item,
  )

  const visibleItems = navItems.filter((item) => {
    if (!item.permission) return true
    return user?.[item.permission as keyof typeof user]
  })

  // Auto-open groups whose children match current path
  const [openGroups, setOpenGroups] = useState<Set<string>>(() => {
    const initial = new Set<string>()
    navItems.forEach((item) => {
      if (item.children?.some((c) => location.pathname.startsWith(c.path))) {
        initial.add(item.label)
      }
    })
    return initial
  })

  const toggleGroup = (label: string) => {
    setOpenGroups((prev) => {
      const next = new Set(prev)
      if (next.has(label)) next.delete(label)
      else next.add(label)
      return next
    })
  }

  const isChildActive = (item: NavItem) =>
    item.children?.some((c) => {
      // For /app/accounting child, only match exact (not /app/accounting/add etc handled by parent)
      if (c.path === '/app/accounting') {
        return location.pathname === '/app/accounting' || location.pathname.startsWith('/app/accounting/')
      }
      return location.pathname.startsWith(c.path)
    }) ?? false

  const renderNavItem = (item: NavItem) => {
    const Icon = item.icon

    // --- Group with children ---
    if (item.children) {
      const isOpen = openGroups.has(item.label)
      const anyChildActive = isChildActive(item)

      if (collapsed) {
        // Collapsed: popover flyout with children on click
        return (
          <Popover key={item.label}>
            <PopoverTrigger asChild>
              <button
                aria-label={item.label}
                className={cn(
                  'flex w-full items-center justify-center rounded-md px-2 py-2 text-sm font-medium transition-colors',
                  anyChildActive
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
              </button>
            </PopoverTrigger>
            <PopoverContent side="right" align="start" className="w-44 p-1">
              <div className="space-y-0.5">
                <div className="px-2 py-1 text-xs font-semibold text-muted-foreground">{item.label}</div>
                {item.children.map((child) => {
                  const ChildIcon = child.icon
                  const childActive = location.pathname.startsWith(child.path)
                  return (
                    <Link
                      key={child.path}
                      to={child.path}
                      className={cn(
                        'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors',
                        childActive
                          ? 'bg-primary text-primary-foreground'
                          : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                      )}
                    >
                      <ChildIcon className="h-3.5 w-3.5 shrink-0" />
                      <span>{child.label}</span>
                    </Link>
                  )
                })}
              </div>
            </PopoverContent>
          </Popover>
        )
      }

      // Expanded: parent button + collapsible children
      return (
        <div key={item.label}>
          <button
            onClick={() => toggleGroup(item.label)}
            className={cn(
              'flex w-full items-center justify-between rounded-md px-3 py-2 text-sm font-medium transition-colors',
              anyChildActive
                ? 'bg-accent text-accent-foreground'
                : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
            )}
          >
            <span className="flex items-center gap-3">
              <Icon className="h-4 w-4 shrink-0" />
              <span>{item.label}</span>
            </span>
            {isOpen ? (
              <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
            )}
          </button>
          {isOpen && (
            <div className="mt-0.5 space-y-0.5">
              {item.children.map((child) => {
                const ChildIcon = child.icon
                const childActive = location.pathname.startsWith(child.path)

                return (
                  <Link
                    key={child.path}
                    to={child.path}
                    className={cn(
                      'flex items-center gap-3 rounded-md pl-9 pr-3 py-1.5 text-sm transition-colors',
                      childActive
                        ? 'bg-primary text-primary-foreground'
                        : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                    )}
                  >
                    <ChildIcon className="h-3.5 w-3.5 shrink-0" />
                    <span>{child.label}</span>
                  </Link>
                )
              })}
            </div>
          )}
        </div>
      )
    }

    // --- Regular item (no children) ---
    const isActive = item.path ? location.pathname.startsWith(item.path) : false
    const classes = cn(
      'flex items-center rounded-md text-sm font-medium transition-colors',
      collapsed ? 'justify-center px-2 py-2' : 'gap-3 px-3 py-2',
      isActive
        ? 'bg-primary text-primary-foreground'
        : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
    )

    const BadgeComp = item.badge
    const linkContent = (
      <>
        <Icon className="h-4 w-4 shrink-0" />
        {!collapsed && <span className="flex-1">{item.label}</span>}
        {!collapsed && BadgeComp && <BadgeComp />}
      </>
    )

    // Action items render as buttons (e.g. AI Agent toggle)
    if (item.action) {
      const btn = (
        <button key={item.label} onClick={item.action} className={cn(classes, 'w-full text-left')}>
          {linkContent}
        </button>
      )
      if (collapsed) {
        return (
          <Tooltip key={item.label}>
            <TooltipTrigger asChild>{btn}</TooltipTrigger>
            <TooltipContent side="right">{item.label}</TooltipContent>
          </Tooltip>
        )
      }
      return btn
    }

    const link = item.external ? (
      <a key={item.path} href={item.path} className={classes}>
        {linkContent}
      </a>
    ) : (
      <Link key={item.path} to={item.path} className={classes}>
        {linkContent}
      </Link>
    )

    if (collapsed) {
      return (
        <Tooltip key={item.path}>
          <TooltipTrigger asChild>{link}</TooltipTrigger>
          <TooltipContent side="right">{item.label}</TooltipContent>
        </Tooltip>
      )
    }

    return link
  }

  return (
    <TooltipProvider delayDuration={collapsed ? 100 : 400}>
      <div className="flex h-full flex-col">
        {/* Header */}
        <div className={cn('flex h-14 items-center border-b', collapsed ? 'justify-center px-2' : 'justify-between px-4')}>
          <Link to="/app/dashboard" className="flex items-center gap-2 text-lg font-semibold">
            <Bot className="h-5 w-5 shrink-0 text-primary" />
            {!collapsed && <span>JARVIS</span>}
          </Link>
          {!collapsed && <NotificationBell />}
        </div>

        {/* Navigation */}
        <nav className={cn('flex-1 space-y-1', collapsed ? 'p-2' : 'p-3')}>
          {visibleItems.map((item) => renderNavItem(item))}
        </nav>

        {/* Footer */}
        <div className={cn('border-t', collapsed ? 'p-2' : 'p-3')}>
          {collapsed ? (
            <>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Link
                    to="/app/profile"
                    className={cn(
                      'flex items-center justify-center rounded-md p-2 transition-colors',
                      location.pathname === '/app/profile'
                        ? 'bg-primary text-primary-foreground'
                        : 'hover:bg-accent',
                    )}
                  >
                    <UserCircle className="h-5 w-5 shrink-0" />
                  </Link>
                </TooltipTrigger>
                <TooltipContent side="right">{user?.name}</TooltipContent>
              </Tooltip>
              <div className="my-2 flex justify-center">
                <ThemeToggle />
              </div>
              <Separator className="my-2" />
              <Tooltip>
                <TooltipTrigger asChild>
                  <a
                    href="/logout"
                    className="flex items-center justify-center rounded-md p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                  >
                    <LogOut className="h-4 w-4" />
                  </a>
                </TooltipTrigger>
                <TooltipContent side="right">Logout</TooltipContent>
              </Tooltip>
            </>
          ) : (
            <>
              <Link
                to="/app/profile"
                className={cn(
                  'flex items-center gap-3 rounded-md px-3 py-2 transition-colors',
                  location.pathname === '/app/profile'
                    ? 'bg-primary text-primary-foreground'
                    : 'hover:bg-accent',
                )}
              >
                <UserCircle className="h-5 w-5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{user?.name}</div>
                  <div className="truncate text-xs text-muted-foreground">{user?.role_name}</div>
                </div>
                <ThemeToggle />
              </Link>
              <Separator className="my-2" />
              <a
                href="/logout"
                className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
              >
                <LogOut className="h-4 w-4" />
                Logout
              </a>
            </>
          )}

          {/* Collapse toggle — desktop only */}
          {onToggle && (
            <>
              <Separator className="my-2" />
              <button
                onClick={onToggle}
                aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
                className={cn(
                  'flex w-full items-center rounded-md text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground',
                  collapsed ? 'justify-center p-2' : 'gap-2 px-3 py-2',
                )}
              >
                {collapsed ? (
                  <PanelLeft className="h-4 w-4" />
                ) : (
                  <>
                    <PanelLeftClose className="h-4 w-4" />
                    <span>Collapse</span>
                  </>
                )}
              </button>
            </>
          )}
        </div>
      </div>
    </TooltipProvider>
  )
}
