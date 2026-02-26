import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import { Skeleton } from '@/components/ui/skeleton'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Settings = lazy(() => import('./pages/Settings'))
const Profile = lazy(() => import('./pages/Profile'))
const Accounting = lazy(() => import('./pages/Accounting'))
const AddInvoice = lazy(() => import('./pages/Accounting/AddInvoice'))
const Hr = lazy(() => import('./pages/Hr'))
const Statements = lazy(() => import('./pages/Statements'))
const EFactura = lazy(() => import('./pages/EFactura'))
const Approvals = lazy(() => import('./pages/Approvals'))
const Marketing = lazy(() => import('./pages/Marketing'))
const ProjectDetail = lazy(() => import('./pages/Marketing/ProjectDetail'))
const Bilant = lazy(() => import('./pages/Accounting/Bilant'))
const BilantDetail = lazy(() => import('./pages/Accounting/Bilant/BilantDetail'))
const TemplateEditor = lazy(() => import('./pages/Accounting/Bilant/TemplateEditor'))
const AiAgent = lazy(() => import('./pages/AiAgent/AiAgent'))
const Crm = lazy(() => import('./pages/Crm'))
const Dms = lazy(() => import('./pages/Dms'))
const DmsDocumentDetail = lazy(() => import('./pages/Dms/DocumentDetail'))

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

export default function App() {
  return (
    <Routes>
      <Route path="/app" element={<Layout />}>
        <Route index element={<Navigate to="dashboard" replace />} />
        <Route path="dashboard" element={<SuspensePage><Dashboard /></SuspensePage>} />
        <Route path="settings/*" element={<SuspensePage><Settings /></SuspensePage>} />
        <Route path="profile" element={<SuspensePage><Profile /></SuspensePage>} />
        <Route path="accounting" element={<SuspensePage><Accounting /></SuspensePage>} />
        <Route path="accounting/add" element={<SuspensePage><AddInvoice /></SuspensePage>} />
        <Route path="accounting/bilant" element={<SuspensePage><Bilant /></SuspensePage>} />
        <Route path="accounting/bilant/:generationId" element={<SuspensePage><BilantDetail /></SuspensePage>} />
        <Route path="accounting/bilant/templates/:templateId" element={<SuspensePage><TemplateEditor /></SuspensePage>} />
        <Route path="hr/*" element={<SuspensePage><Hr /></SuspensePage>} />
        <Route path="statements/*" element={<SuspensePage><Statements /></SuspensePage>} />
        <Route path="efactura/*" element={<SuspensePage><EFactura /></SuspensePage>} />
        <Route path="approvals" element={<SuspensePage><Approvals /></SuspensePage>} />
        <Route path="marketing" element={<SuspensePage><Marketing /></SuspensePage>} />
        <Route path="marketing/projects/:projectId" element={<SuspensePage><ProjectDetail /></SuspensePage>} />
        <Route path="ai-agent" element={<SuspensePage><AiAgent /></SuspensePage>} />
        <Route path="sales/crm" element={<SuspensePage><Crm /></SuspensePage>} />
        <Route path="dms" element={<SuspensePage><Dms /></SuspensePage>} />
        <Route path="dms/documents/:documentId" element={<SuspensePage><DmsDocumentDetail /></SuspensePage>} />
        <Route path="*" element={<Navigate to="dashboard" replace />} />
      </Route>
    </Routes>
  )
}
