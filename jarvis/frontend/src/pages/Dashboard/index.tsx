import { useMemo, useState } from 'react'
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
import { useWidgetEmptyState } from './useWidgetEmptyState'
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

const COLS = 6

/**
 * Repack layouts into a compact grid with no gaps.
 * Uses a height-map approach: for each widget (in order), find the first
 * position where it fits by scanning left-to-right across the lowest
 * available row.
 */
function repackLayouts(widgets: WidgetLayout[]): WidgetLayout[] {
  // Height map: for each column, track the lowest occupied row
  const colHeights = new Array(COLS).fill(0)

  return widgets.map(w => {
    const width = w.w
    const height = w.h

    // Find the first x position where this widget fits
    let bestX = 0
    let bestY = Infinity

    for (let x = 0; x <= COLS - width; x++) {
      // The widget spans columns [x, x+width). The top of the slot
      // is the max height across those columns.
      let slotY = 0
      for (let col = x; col < x + width; col++) {
        slotY = Math.max(slotY, colHeights[col])
      }
      if (slotY < bestY) {
        bestY = slotY
        bestX = x
      }
    }

    // Place the widget
    for (let col = bestX; col < bestX + width; col++) {
      colHeights[col] = bestY + height
    }

    return { ...w, x: bestX, y: bestY }
  })
}

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
  const emptyWidgets = useWidgetEmptyState()
  const toggleAiWidget = useAiAgentStore(s => s.toggleWidget)
  const { width, containerRef } = useContainerWidth()

  // Easter egg: special greeting for Sebastian
  const isSeba = user?.name?.toLowerCase().includes('seba') || user?.name?.toLowerCase().includes('sebastian')
  const sebaGreetings = [
    "Welcome back, boss.",
    "Reporting for duty, Seba.",
    "All systems nominal, Creator.",
    "The system you built is running smoothly, Seba.",
    "At your service, as always.",
  ]
  const [greetingIdx] = useState(() => Math.floor(Math.random() * sebaGreetings.length))
  const greeting = isSeba ? sebaGreetings[greetingIdx] : `Welcome, ${user?.name}.`

  // Filter out widgets with no data, then build layouts
  const activeWidgets = useMemo(() => {
    return visibleWidgets.filter(w => !emptyWidgets.has(w.id))
  }, [visibleWidgets, emptyWidgets])

  const lgLayouts = useMemo(() => {
    const raw = activeWidgets.map(wp => ({ ...wp.layout, i: wp.id }))
    return repackLayouts(raw)
  }, [activeWidgets])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="mt-1 text-sm text-muted-foreground">{greeting}</p>
        </div>
        <div className="flex items-center gap-2">
          <CustomizeSheet
            permittedWidgets={permittedWidgets}
            toggleWidget={toggleWidget}
            setWidgetWidth={setWidgetWidth}
            resetDefaults={resetDefaults}
          />
          <Button variant="outline" size="icon" className="md:size-auto md:px-3" onClick={toggleAiWidget}>
            <Bot className="h-4 w-4 md:mr-1.5" />
            <span className="hidden md:inline">New Chat</span>
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
          {activeWidgets.map(wp => {
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
