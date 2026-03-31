import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuthStore } from '@/stores/authStore'
import type { User } from './types'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Settings = lazy(() => import('./pages/Settings'))
const Profile = lazy(() => import('./pages/Profile'))
const Accounting = lazy(() => import('./pages/Accounting'))
const AddInvoice = lazy(() => import('./pages/Accounting/AddInvoice'))
const BulkUpload = lazy(() => import('./pages/Accounting/BulkUpload'))
const Hr = lazy(() => import('./pages/Hr'))
const Statements = lazy(() => import('./pages/Statements'))
const EFactura = lazy(() => import('./pages/EFactura'))
const Approvals = lazy(() => import('./pages/Approvals'))
const Marketing = lazy(() => import('./pages/Marketing'))
const MarketingEvents = lazy(() => import('./pages/Marketing/Events'))
const MarketingSimulator = lazy(() => import('./pages/Marketing/CampaignSimulator'))
const MarketingCalendar = lazy(() => import('./pages/Marketing/CalendarPage'))
const MarketingDashboard = lazy(() => import('./pages/Marketing/DashboardPage'))
const ProjectDetail = lazy(() => import('./pages/Marketing/ProjectDetail'))
const Bilant = lazy(() => import('./pages/Accounting/Bilant'))
const BilantDetail = lazy(() => import('./pages/Accounting/Bilant/BilantDetail'))
const TemplateEditor = lazy(() => import('./pages/Accounting/Bilant/TemplateEditor'))
const AiAgent = lazy(() => import('./pages/AiAgent/AiAgent'))
const Crm = lazy(() => import('./pages/Crm'))
const Forms = lazy(() => import('./pages/Forms'))
const FormDetail = lazy(() => import('./pages/Forms/FormDetail'))
const FormBuilder = lazy(() => import('./pages/Forms/FormBuilder'))
const PublicForm = lazy(() => import('./pages/Public/PublicForm'))
const Dms = lazy(() => import('./pages/Dms'))
const DmsDocumentDetail = lazy(() => import('./pages/Dms/DocumentDetail'))
const SuppliersPage = lazy(() => import('./pages/Dms/SuppliersPage'))
const SupplierProfile = lazy(() => import('./pages/Dms/SupplierProfile'))
const MobileCheckin = lazy(() => import('./pages/MobileCheckin'))
const DownloadApp = lazy(() => import('./pages/DownloadApp'))
const Digest = lazy(() => import('./pages/Digest'))

function PageLoader() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-4 w-96" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 mt-6">
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
      </div>
    </div>
  )
}

function SuspensePage({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<PageLoader />}>{children}</Suspense>
}

/** Route-level permission guard. Checks a boolean flag on the User object.
 *  If the user doesn't have the flag, renders an access-denied message.
 *  If the user object hasn't loaded yet (isLoading), renders a skeleton. */
const AccessDenied = () => (
  <div className="flex flex-col items-center justify-center h-[60vh] gap-3 text-center px-4">
    <div className="rounded-full bg-muted p-4">
      <svg className="h-8 w-8 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
      </svg>
    </div>
    <div className="space-y-1">
      <p className="font-semibold text-foreground">Access Denied</p>
      <p className="text-sm text-muted-foreground max-w-xs">
        You don't have permission to access this module. Contact your administrator to request access.
      </p>
    </div>
  </div>
)

function Guard({ flag, children }: { flag: keyof User; children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user)
  const isLoading = useAuthStore((s) => s.isLoading)

  if (isLoading) return <PageLoader />
  if (!user?.[flag]) return <AccessDenied />

  return <>{children}</>
}

/** Gate by a V2 permission key ("module.entity.action") from the user.permissions map. */
function V2Guard({ permKey, children }: { permKey: string; children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user)
  const isLoading = useAuthStore((s) => s.isLoading)

  if (isLoading) return <PageLoader />
  // If permissions map not yet loaded, allow (will refresh on auth); any falsy value = deny
  if (user?.permissions && !user.permissions[permKey]) return <AccessDenied />

  return <>{children}</>
}

/** Redirect /app to profile for users without dashboard access (e.g. Viewer role). */
function DefaultRedirect() {
  const user = useAuthStore((s) => s.user)
  const isLoading = useAuthStore((s) => s.isLoading)
  if (isLoading) return <PageLoader />
  if (user && !user.can_access_dashboard) {
    return <Navigate to="profile" replace />
  }
  return <Navigate to="dashboard" replace />
}

/** Show Dashboard if user has access, otherwise redirect to profile (not Access Denied). */
function DashboardOrRedirect() {
  const user = useAuthStore((s) => s.user)
  const isLoading = useAuthStore((s) => s.isLoading)
  if (isLoading) return <PageLoader />
  if (user && !user.can_access_dashboard) {
    return <Navigate to="/app/profile" replace />
  }
  return <SuspensePage><Dashboard /></SuspensePage>
}

export default function App() {
  return (
    <Routes>
      {/* Public form — no auth, no layout */}
      <Route path="/f/:slug" element={<SuspensePage><PublicForm /></SuspensePage>} />

      <Route path="/app" element={<Layout />}>
        <Route index element={<DefaultRedirect />} />
        <Route path="dashboard" element={<DashboardOrRedirect />} />
        <Route path="profile" element={<SuspensePage><Profile /></SuspensePage>} />

        {/* Accounting — requires can_access_accounting */}
        <Route path="accounting" element={<Guard flag="can_access_accounting"><SuspensePage><Accounting /></SuspensePage></Guard>} />
        <Route path="accounting/add" element={<Guard flag="can_access_accounting"><SuspensePage><AddInvoice /></SuspensePage></Guard>} />
        <Route path="accounting/bulk-upload" element={<Guard flag="can_access_accounting"><SuspensePage><BulkUpload /></SuspensePage></Guard>} />
        <Route path="accounting/bilant" element={<Guard flag="can_access_accounting"><SuspensePage><Bilant /></SuspensePage></Guard>} />
        <Route path="accounting/bilant/:generationId" element={<Guard flag="can_access_accounting"><SuspensePage><BilantDetail /></SuspensePage></Guard>} />
        <Route path="accounting/bilant/templates/:templateId" element={<Guard flag="can_access_accounting"><SuspensePage><TemplateEditor /></SuspensePage></Guard>} />

        {/* HR — requires can_access_hr */}
        <Route path="hr/*" element={<Guard flag="can_access_hr"><SuspensePage><Hr /></SuspensePage></Guard>} />

        {/* Statements — requires can_access_statements */}
        <Route path="statements/*" element={<Guard flag="can_access_statements"><SuspensePage><Statements /></SuspensePage></Guard>} />

        {/* e-Factura — requires can_access_efactura */}
        <Route path="efactura/*" element={<Guard flag="can_access_efactura"><SuspensePage><EFactura /></SuspensePage></Guard>} />

        {/* Settings — requires can_access_settings */}
        <Route path="settings/*" element={<Guard flag="can_access_settings"><SuspensePage><Settings /></SuspensePage></Guard>} />

        {/* CRM — requires can_access_crm */}
        <Route path="sales/crm" element={<Guard flag="can_access_crm"><SuspensePage><Crm /></SuspensePage></Guard>} />

        {/* Approvals — requires can_access_approvals */}
        <Route path="approvals" element={<Guard flag="can_access_approvals"><SuspensePage><Approvals /></SuspensePage></Guard>} />

        {/* Marketing — requires can_access_marketing */}
        <Route path="marketing" element={<Guard flag="can_access_marketing"><SuspensePage><Marketing /></SuspensePage></Guard>} />
        <Route path="marketing/dashboard" element={<Guard flag="can_access_marketing"><SuspensePage><MarketingDashboard /></SuspensePage></Guard>} />
        <Route path="marketing/calendar" element={<Guard flag="can_access_marketing"><SuspensePage><MarketingCalendar /></SuspensePage></Guard>} />
        <Route path="marketing/simulator" element={<Guard flag="can_access_marketing"><V2Guard permKey="marketing.simulator.view"><SuspensePage><MarketingSimulator /></SuspensePage></V2Guard></Guard>} />
        <Route path="marketing/events/*" element={<Guard flag="can_access_marketing"><SuspensePage><MarketingEvents /></SuspensePage></Guard>} />
        <Route path="marketing/projects/:projectId" element={<Guard flag="can_access_marketing"><SuspensePage><ProjectDetail /></SuspensePage></Guard>} />

        {/* Forms — requires can_access_forms */}
        <Route path="forms" element={<Guard flag="can_access_forms"><SuspensePage><Forms /></SuspensePage></Guard>} />
        <Route path="forms/:formId" element={<Guard flag="can_access_forms"><SuspensePage><FormDetail /></SuspensePage></Guard>} />
        <Route path="forms/builder" element={<Guard flag="can_access_forms"><SuspensePage><FormBuilder /></SuspensePage></Guard>} />
        <Route path="forms/builder/:formId" element={<Guard flag="can_access_forms"><SuspensePage><FormBuilder /></SuspensePage></Guard>} />

        {/* DMS — requires can_access_dms */}
        <Route path="dms" element={<Guard flag="can_access_dms"><SuspensePage><Dms /></SuspensePage></Guard>} />
        <Route path="dms/documents/:documentId" element={<Guard flag="can_access_dms"><SuspensePage><DmsDocumentDetail /></SuspensePage></Guard>} />
        <Route path="dms/suppliers" element={<Guard flag="can_access_dms"><SuspensePage><SuppliersPage /></SuspensePage></Guard>} />
        <Route path="dms/suppliers/:supplierId" element={<Guard flag="can_access_dms"><SuspensePage><SupplierProfile /></SuspensePage></Guard>} />

        {/* AI Agent — requires can_access_ai_agent */}
        <Route path="ai-agent" element={<Guard flag="can_access_ai_agent"><SuspensePage><AiAgent /></SuspensePage></Guard>} />

        {/* Digest — open to all authenticated users */}
        <Route path="digest" element={<SuspensePage><Digest /></SuspensePage>} />

        {/* Open-access modules — all authenticated users */}
        <Route path="mobile-checkin" element={<SuspensePage><MobileCheckin /></SuspensePage>} />
        <Route path="download" element={<SuspensePage><DownloadApp /></SuspensePage>} />

        <Route path="*" element={<DefaultRedirect />} />
      </Route>
    </Routes>
  )
}
