import { useCallback, useMemo, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { LayoutDashboard, Bot, Calculator, Users, Landmark, FileText, Settings, LogOut, UserCircle, PanelLeftClose, PanelLeft, ChevronDown, ChevronRight, ClipboardCheck, Megaphone, Scale, TrendingUp, Contact, FolderOpen, Fingerprint, Award, CalendarDays, Building2, Network, MapPin, PartyPopper, LifeBuoy, ClipboardList, Newspaper, Car, DollarSign, Tag } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/hooks/useAuth'
import { ThemeToggle } from './ThemeToggle'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ApprovalBadge } from './ApprovalBadge'
import { NotificationBell } from './NotificationBell'
import { settingsApi } from '@/api/settings'
import { checkinApi } from '@/api/checkin'

interface NavItem {
  path: string
  label: string
  icon: React.ElementType
  moduleKey?: string           // maps to module_menu_items.module_key
  permission?: string          // top-level can_access_* flag
  v2Permission?: string        // fine-grained v2 key: "module.entity.action"
  external?: boolean
  children?: NavItem[]
  badge?: React.ComponentType
  action?: () => void
}

const navItemsDef: NavItem[] = [
  { path: '/app/dashboard', label: 'Dashboard', icon: LayoutDashboard, permission: 'can_access_dashboard' },
  { path: '/app/ai-agent', label: 'AI Agent', icon: Bot, moduleKey: 'ai_agent', permission: 'can_access_ai_agent' },
  {
    path: '/app/accounting',
    label: 'Accounting',
    icon: Calculator,
    moduleKey: 'accounting',
    permission: 'can_access_accounting',
    children: [
      { path: '/app/accounting', label: 'Invoices', icon: Calculator, moduleKey: 'accounting_dashboard' },
      { path: '/app/statements', label: 'Statements', icon: Landmark, moduleKey: 'accounting_statements', permission: 'can_access_statements' },
      { path: '/app/efactura', label: 'e-Factura', icon: FileText, moduleKey: 'accounting_efactura', permission: 'can_access_efactura' },
      { path: '/app/accounting/bilant', label: 'Bilant', icon: Scale, moduleKey: 'accounting_bilant', v2Permission: 'bilant.templates.view' },
    ],
  },
  {
    path: '/app/hr',
    label: 'HR',
    icon: Users,
    moduleKey: 'hr',
    permission: 'can_access_hr',
    children: [
      { path: '/app/hr/pontaje', label: 'Pontaje', icon: Fingerprint, moduleKey: 'hr_pontaje', v2Permission: 'hr.pontaje.view_original' },
      { path: '/app/hr/bonuses', label: 'Bonuses', icon: Award, moduleKey: 'hr_bonuses', v2Permission: 'hr.bonuses.view' },
      { path: '/app/hr/organigram', label: 'Organigram', icon: Network, moduleKey: 'hr_organigram', v2Permission: 'hr.structure.view' },
    ],
  },
  { path: '/app/approvals', label: 'Approvals', icon: ClipboardCheck, moduleKey: 'approvals', permission: 'can_access_approvals', badge: ApprovalBadge },
  {
    path: '/app/marketing',
    label: 'Marketing',
    icon: Megaphone,
    moduleKey: 'marketing',
    permission: 'can_access_marketing',
    children: [
      { path: '/app/marketing/dashboard', label: 'Dashboard', icon: TrendingUp, moduleKey: 'marketing_dashboard' },
      { path: '/app/marketing/calendar', label: 'Calendar', icon: CalendarDays, moduleKey: 'marketing_calendar' },
      { path: '/app/marketing', label: 'Projects', icon: Megaphone, moduleKey: 'marketing_projects' },
      { path: '/app/marketing/events', label: 'Events', icon: PartyPopper, moduleKey: 'marketing_events' },
      { path: '/app/marketing/simulator', label: 'Simulator', icon: Calculator, moduleKey: 'marketing_simulator', v2Permission: 'marketing.simulator.view' },
    ],
  },
  { path: '/app/digest', label: 'Digest', icon: Newspaper, moduleKey: 'digest' },
  { path: '/app/forms', label: 'Forms', icon: ClipboardList, moduleKey: 'forms', permission: 'can_access_forms' },
  { path: '/app/dms', label: 'Documents', icon: FolderOpen, moduleKey: 'dms', permission: 'can_access_dms' },
  { path: '/app/dms/suppliers', label: 'Suppliers', icon: Building2, moduleKey: 'dms_suppliers', permission: 'can_access_dms' },
  {
    path: '/app/sales',
    label: 'Sales',
    icon: TrendingUp,
    moduleKey: 'sales',
    permission: 'can_access_crm',
    children: [
      { path: '/app/sales/crm', label: 'CRM Database', icon: Contact, moduleKey: 'crm_database' },
      { path: '/app/sales/field-sales', label: 'Field Sales', icon: MapPin, moduleKey: 'field_sales' },
    ],
  },
  {
    path: '/app/carpark', label: 'CarPark', icon: Car, moduleKey: 'carpark', permission: 'can_access_carpark',
    children: [
      { path: '/app/carpark', label: 'Vehicule', icon: Car, moduleKey: 'carpark_vehicles' },
      { path: '/app/carpark/pricing-rules', label: 'Reguli preț', icon: DollarSign, moduleKey: 'carpark_pricing' },
      { path: '/app/carpark/promotions', label: 'Promoții', icon: Tag, moduleKey: 'carpark_promotions' },
    ],
  },
  { path: '/app/settings', label: 'Settings', icon: Settings, moduleKey: 'settings', permission: 'can_access_settings' },
]

interface SidebarProps {
  collapsed?: boolean
  onToggle?: () => void
}

export function Sidebar({ collapsed = false, onToggle }: SidebarProps) {
  const { user } = useAuth()
  const location = useLocation()

  // Fetch menu config from DB — drives visibility & ordering
  const { data: menuData } = useQuery({
    queryKey: ['module-menu'],
    queryFn: settingsApi.getModuleMenu,
    staleTime: 5 * 60 * 1000, // 5 min — matches backend cache TTL
  })

  // Check-in direction for sidebar footer label
  const { data: checkinStatus } = useQuery({
    queryKey: ['checkin', 'status'],
    queryFn: async () => {
      const res = await checkinApi.getStatus()
      return (res as any).data ?? res
    },
    staleTime: 60_000,
    refetchInterval: 60_000,
  })
  const checkinLabel = checkinStatus?.next_direction === 'OUT' ? 'Check Out' : 'Check In'

  // Easter egg: 7-click logo reveal
  const clickCount = useRef(0)
  const clickTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const [logoText, setLogoText] = useState('JARVIS')
  const handleLogoClick = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    clickCount.current++
    clearTimeout(clickTimer.current)
    if (clickCount.current >= 7) {
      clickCount.current = 0
      setLogoText("Seba's System")
      setTimeout(() => setLogoText('JARVIS'), 3000)
    } else {
      clickTimer.current = setTimeout(() => { clickCount.current = 0 }, 800)
    }
  }, [])

  // Build flat map of all DB module items (parents + children) → { name, sort_order }
  const dbModuleMap = useMemo(() => {
    if (!menuData?.items) return null // null = not loaded yet, show all
    const map = new Map<string, { name: string; sort_order: number }>()
    for (const item of menuData.items) {
      map.set(item.module_key, { name: item.name, sort_order: item.sort_order })
      for (const child of item.children ?? []) {
        map.set(child.module_key, { name: child.name, sort_order: child.sort_order })
      }
    }
    return map
  }, [menuData])

  const visibleItems = useMemo(() => {
    const userPerms = user?.permissions

    const isItemVisible = (item: NavItem): boolean => {
      // Module-level flag (can_access_*)
      if (item.permission && !user?.[item.permission as keyof typeof user]) return false
      // Fine-grained v2 permission — default true if map not loaded yet
      if (item.v2Permission && userPerms) {
        if (!(userPerms[item.v2Permission] ?? true)) return false
      }
      // DB menu visibility
      if (item.moduleKey && dbModuleMap !== null) {
        return dbModuleMap.has(item.moduleKey)
      }
      return true
    }

    const filtered = navItemsDef.filter(isItemVisible)

    // Sort by DB order where available
    if (dbModuleMap !== null) {
      filtered.sort((a, b) => {
        const orderA = a.moduleKey ? (dbModuleMap.get(a.moduleKey)?.sort_order ?? 99) : navItemsDef.indexOf(a)
        const orderB = b.moduleKey ? (dbModuleMap.get(b.moduleKey)?.sort_order ?? 99) : navItemsDef.indexOf(b)
        return orderA - orderB
      })
    }
    // Override labels with DB names; filter children by their own permissions
    return filtered.map(item => ({
      ...item,
      label: (item.moduleKey && dbModuleMap?.get(item.moduleKey)?.name) || item.label,
      children: item.children
        ?.filter(isItemVisible)
        .map(child => ({
          ...child,
          label: (child.moduleKey && dbModuleMap?.get(child.moduleKey)?.name) || child.label,
        })),
    }))
  }, [user, dbModuleMap])

  // Auto-open groups whose children match current path
  const [openGroups, setOpenGroups] = useState<Set<string>>(() => {
    const initial = new Set<string>()
    navItemsDef.forEach((item) => {
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
                  const hasLongerSibling = item.children!.some(
                    (s) => s.path !== child.path && s.path.startsWith(child.path)
                  )
                  const childActive = hasLongerSibling
                    ? location.pathname === child.path
                    : location.pathname.startsWith(child.path)
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
                const hasLongerSibling = item.children!.some(
                  (s) => s.path !== child.path && s.path.startsWith(child.path)
                )
                const childActive = hasLongerSibling
                  ? location.pathname === child.path
                  : location.pathname.startsWith(child.path)

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
    // Use exact match when a sibling has a longer path starting with this one (e.g. /app/dms vs /app/dms/suppliers)
    const hasLongerSibling = visibleItems.some(
      (s) => s.path !== item.path && s.path.startsWith(item.path)
    )
    const isActive = item.path
      ? hasLongerSibling
        ? location.pathname === item.path
        : location.pathname.startsWith(item.path)
      : false
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
      <div
        className="flex h-full flex-col"
        onClick={(e) => {
          if (!onToggle) return
          const target = e.target as HTMLElement
          // Only toggle if clicking empty space (not buttons, links, inputs, switches)
          if (target.closest('a, button, input, [role="switch"], [role="combobox"], [role="menuitem"]')) return
          onToggle()
        }}
      >
        {/* Header */}
        <div className={cn('flex h-14 items-center border-b', collapsed ? 'justify-center px-2' : 'justify-between px-4')}>
          <Link to="/app/dashboard" className="flex items-center gap-2 text-lg font-semibold" onClick={handleLogoClick}>
            <Bot className="h-5 w-5 shrink-0 text-primary" />
            {!collapsed && (
              <span className={logoText !== 'JARVIS' ? 'bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 bg-clip-text text-transparent transition-all duration-500' : ''}>
                {logoText}
              </span>
            )}
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
                  <a
                    href="https://autoworldro.atlassian.net/jira/core/projects/JAR/form/36"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-center rounded-md p-2 transition-colors hover:bg-accent"
                  >
                    <LifeBuoy className="h-5 w-5 shrink-0" />
                  </a>
                </TooltipTrigger>
                <TooltipContent side="right">Support</TooltipContent>
              </Tooltip>
              <Separator className="my-2" />
              <Tooltip>
                <TooltipTrigger asChild>
                  <Link
                    to="/app/mobile-checkin"
                    className={cn(
                      'flex items-center justify-center rounded-md p-2 transition-colors',
                      location.pathname === '/app/mobile-checkin'
                        ? 'bg-primary text-primary-foreground'
                        : 'hover:bg-accent',
                    )}
                  >
                    <MapPin className="h-5 w-5 shrink-0" />
                  </Link>
                </TooltipTrigger>
                <TooltipContent side="right">{checkinLabel}</TooltipContent>
              </Tooltip>
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
              <a
                href="https://autoworldro.atlassian.net/jira/core/projects/JAR/form/36"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-3 rounded-md px-3 py-2 transition-colors hover:bg-accent"
              >
                <LifeBuoy className="h-5 w-5 shrink-0" />
                <span className="text-sm font-medium">Support</span>
              </a>
              <Separator className="my-2" />
              <Link
                to="/app/mobile-checkin"
                className={cn(
                  'flex items-center gap-3 rounded-md px-3 py-2 transition-colors',
                  location.pathname === '/app/mobile-checkin'
                    ? 'bg-primary text-primary-foreground'
                    : 'hover:bg-accent',
                )}
              >
                <MapPin className="h-5 w-5 shrink-0" />
                <span className="text-sm font-medium">{checkinLabel}</span>
              </Link>
              <Separator className="my-2" />
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
                  'flex w-full items-center rounded-md text-sm transition-colors',
                  collapsed
                    ? 'justify-center p-2 bg-accent text-accent-foreground hover:bg-accent/80'
                    : 'gap-2 px-3 py-2 text-muted-foreground hover:bg-accent hover:text-accent-foreground',
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
