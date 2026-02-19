import { useMemo } from 'react'
import {
  ResponsiveGridLayout,
  useContainerWidth,
  verticalCompactor,
  type Layout,
} from 'react-grid-layout'
import 'react-grid-layout/css/styles.css'
import { Bot } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/hooks/useAuth'
import { useAiAgentStore } from '@/stores/aiAgentStore'
import type { WidgetLayout } from './types'
import { useDashboardPrefs } from './useDashboardPrefs'
import { CustomizeSheet } from './CustomizeSheet'
import {
  AccountingInvoicesWidget,
  StatementsSummaryWidget,
  EFacturaWidget,
  HrSummaryWidget,
  MarketingSummaryWidget,
  ApprovalsQueueWidget,
  OnlineUsersWidget,
  NotificationsWidget,
} from './widgets'

const WIDGET_COMPONENTS: Record<string, React.ComponentType<{ enabled: boolean }>> = {
  accounting_invoices: AccountingInvoicesWidget,
  statements_summary: StatementsSummaryWidget,
  efactura_status: EFacturaWidget,
  hr_summary: HrSummaryWidget,
  marketing_summary: MarketingSummaryWidget,
  approvals_queue: ApprovalsQueueWidget,
  online_users: OnlineUsersWidget,
  notifications_recent: NotificationsWidget,
}

export default function Dashboard() {
  const { user } = useAuth()
  const { permittedWidgets, visibleWidgets, toggleWidget, updateLayout, setWidgetWidth, resetDefaults } = useDashboardPrefs(user)
  const toggleAiWidget = useAiAgentStore(s => s.toggleWidget)
  const { width, containerRef } = useContainerWidth()

  // Build layouts for react-grid-layout
  const lgLayouts = useMemo(() => {
    return visibleWidgets.map(wp => ({
      ...wp.layout,
      i: wp.id,
    }))
  }, [visibleWidgets])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="mt-1 text-muted-foreground">Welcome, {user?.name}.</p>
        </div>
        <div className="flex items-center gap-2">
          <CustomizeSheet
            permittedWidgets={permittedWidgets}
            toggleWidget={toggleWidget}
            setWidgetWidth={setWidgetWidth}
            resetDefaults={resetDefaults}
          />
          <Button variant="outline" size="sm" onClick={toggleAiWidget}>
            <Bot className="mr-1.5 h-4 w-4" />
            New Chat
          </Button>
        </div>
      </div>

      {/* Widget Grid — drag & resize */}
      <div ref={containerRef}>
        <ResponsiveGridLayout
          width={width}
          layouts={{ lg: lgLayouts }}
          breakpoints={{ lg: 1024, md: 768, sm: 0 }}
          cols={{ lg: 6, md: 4, sm: 1 }}
          rowHeight={80}
          dragConfig={{ enabled: true, handle: '.widget-drag-handle', bounded: false, threshold: 3 }}
          resizeConfig={{ enabled: true, handles: ['se'] }}
          compactor={verticalCompactor}
          onLayoutChange={(layout: Layout) => updateLayout(layout as unknown as WidgetLayout[])}
          margin={[16, 16]}
        >
          {visibleWidgets.map(wp => {
            const Component = WIDGET_COMPONENTS[wp.id]
            if (!Component) return null
            return (
              <div key={wp.id} className="h-full">
                <Component enabled />
              </div>
            )
          })}
        </ResponsiveGridLayout>
      </div>
    </div>
  )
}
