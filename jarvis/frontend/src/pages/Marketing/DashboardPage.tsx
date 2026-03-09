import { PageHeader } from '@/components/shared/PageHeader'
import { DashboardView, useDashboardWidgets } from './index'

export default function DashboardPage() {
  const { visibleWidgets, customizeButton } = useDashboardWidgets()

  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader
        title="Dashboard"
        breadcrumbs={[
          { label: 'Marketing', shortLabel: 'Mkt.', href: '/app/marketing' },
          { label: 'Dashboard' },
        ]}
        actions={customizeButton}
      />
      <DashboardView showStats widgetVisibility={visibleWidgets} />
    </div>
  )
}
