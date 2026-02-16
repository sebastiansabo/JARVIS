import { lazy, Suspense } from 'react'
import { NavLink, Routes, Route, Navigate, useParams, useLocation } from 'react-router-dom'
import {
  Users,
  Shield,
  Palette,
  Menu,
  Calculator,
  Bell,
  Building2,
  Activity,
  Tags,
  Briefcase,
  Bot,
  Plug,
  ClipboardCheck,
} from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader } from '@/components/shared/PageHeader'
import { cn } from '@/lib/utils'

const UsersTab = lazy(() => import('./UsersTab'))
const RolesTab = lazy(() => import('./RolesTab'))
const ThemesTab = lazy(() => import('./ThemesTab'))
const MenusTab = lazy(() => import('./MenusTab'))
const AccountingTab = lazy(() => import('./AccountingTab'))
const NotificationsTab = lazy(() => import('./NotificationsTab'))
const StructureTab = lazy(() => import('./StructureTab'))
const ActivityTab = lazy(() => import('./ActivityTab'))
const TagsTab = lazy(() => import('./TagsTab'))
const HrTab = lazy(() => import('./HrTab'))
const AiTab = lazy(() => import('./AiTab'))
const ConnectorsTab = lazy(() => import('./ConnectorsTab'))
const ApprovalsTab = lazy(() => import('./ApprovalsTab'))

const tabs = [
  // Access
  { path: 'users', label: 'Users', icon: Users },
  { path: 'roles', label: 'Roles', icon: Shield },
  // Organization
  { path: 'structure', label: 'Structure', icon: Building2 },
  // Domain config
  { path: 'accounting', label: 'Accounting', icon: Calculator },
  { path: 'hr', label: 'HR', icon: Briefcase },
  // Appearance
  { path: 'themes', label: 'Themes', icon: Palette },
  { path: 'menus', label: 'Menus', icon: Menu },
  { path: 'tags', label: 'Tags', icon: Tags },
  // Monitoring
  { path: 'notifications', label: 'Notifications', icon: Bell },
  { path: 'activity', label: 'Activity', icon: Activity },
  // Workflows
  { path: 'approvals', label: 'Approvals', icon: ClipboardCheck },
  // Connectors
  { path: 'connectors', label: 'Connectors', icon: Plug },
  // AI
  { path: 'ai', label: 'AI Agent', icon: Bot },
]

function TabSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-64 w-full" />
    </div>
  )
}

export default function Settings() {
  const { '*': splat } = useParams()
  const { pathname } = useLocation()
  const basePath = splat ? pathname.replace(new RegExp(`/${splat}$`), '') : pathname
  return (
    <div>
      <PageHeader title="Settings" description="Manage users, roles, themes, and system configuration." />

      <div className="mt-6 flex flex-col gap-6 lg:flex-row">
        {/* Tab Navigation */}
        <nav className="flex gap-1 overflow-x-auto lg:w-48 lg:shrink-0 lg:flex-col">
          {tabs.map((tab) => {
            const Icon = tab.icon
            return (
              <NavLink
                key={tab.path}
                to={`${basePath}/${tab.path}`}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-2 whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                  )
                }
              >
                <Icon className="h-4 w-4" />
                {tab.label}
              </NavLink>
            )
          })}
        </nav>

        {/* Tab Content */}
        <div className="min-w-0 flex-1">
          <Suspense fallback={<TabSkeleton />}>
            <Routes>
              <Route index element={<Navigate to="users" replace />} />
              <Route path="users" element={<UsersTab />} />
              <Route path="roles" element={<RolesTab />} />
              <Route path="themes" element={<ThemesTab />} />
              <Route path="menus" element={<MenusTab />} />
              <Route path="accounting" element={<AccountingTab />} />
              <Route path="notifications" element={<NotificationsTab />} />
              <Route path="structure" element={<StructureTab />} />
              <Route path="activity" element={<ActivityTab />} />
              <Route path="tags" element={<TagsTab />} />
              <Route path="hr" element={<HrTab />} />
              <Route path="approvals" element={<ApprovalsTab />} />
              <Route path="connectors" element={<ConnectorsTab />} />
              <Route path="ai" element={<AiTab />} />
              <Route path="*" element={<Navigate to="users" replace />} />
            </Routes>
          </Suspense>
        </div>
      </div>
    </div>
  )
}
