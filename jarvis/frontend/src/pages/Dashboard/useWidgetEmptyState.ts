import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { dashboardApi } from '@/api/dashboard'
import { statementsApi } from '@/api/statements'
import { hrApi } from '@/api/hr'
import { marketingApi } from '@/api/marketing'
import { approvalsApi } from '@/api/approvals'
import { notificationsApi } from '@/api/notifications'

/**
 * Runs the same queries as dashboard widgets (React Query deduplicates them)
 * and returns a Set of widget IDs that have no meaningful data to display.
 *
 * Widgets are considered empty when they would only show a placeholder message.
 * Status indicators (efactura, online_users) always count as "has data".
 */
export function useWidgetEmptyState() {
  const year = new Date().getFullYear()

  const invoices = useQuery({
    queryKey: ['dashboard', 'recentInvoices'],
    queryFn: () => dashboardApi.getRecentInvoices(5),
    staleTime: 60_000,
  })

  const statements = useQuery({
    queryKey: ['dashboard', 'statementsSummary'],
    queryFn: () => statementsApi.getSummary(),
    staleTime: 60_000,
  })

  const hr = useQuery({
    queryKey: ['dashboard', 'hrSummary', year],
    queryFn: () => hrApi.getSummary({ year }),
    staleTime: 60_000,
  })

  const marketing = useQuery({
    queryKey: ['dashboard', 'mktSummary'],
    queryFn: () => marketingApi.getDashboardSummary(),
    staleTime: 60_000,
  })

  const approvals = useQuery({
    queryKey: ['dashboard', 'approvalQueue'],
    queryFn: () => approvalsApi.getMyQueue(),
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  const notifications = useQuery({
    queryKey: ['dashboard', 'recentNotifications'],
    queryFn: () => notificationsApi.getNotifications({ limit: 5, unread_only: true }),
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  return useMemo(() => {
    const empty = new Set<string>()

    // List-based widgets: empty when no items
    if (invoices.data && invoices.data.length === 0) empty.add('accounting_invoices')
    if (approvals.data && (approvals.data.queue ?? []).length === 0) empty.add('approvals_queue')
    if (notifications.data && (notifications.data.notifications ?? []).length === 0) empty.add('notifications_recent')

    // Statements: empty when total transactions across all statuses is 0
    if (statements.data) {
      const s = statements.data.by_status
      const total = (s?.pending?.count ?? 0) + (s?.resolved?.count ?? 0) + (s?.ignored?.count ?? 0)
      if (total === 0) empty.add('statements_summary')
    }

    // HR: empty when all metrics are 0
    if (hr.data) {
      const d = hr.data
      if ((d.total_events ?? 0) === 0 && (d.total_employees ?? 0) === 0 &&
          (d.total_bonuses ?? 0) === 0 && (d.total_bonus_amount ?? 0) === 0) {
        empty.add('hr_summary')
      }
    }

    // Marketing: empty when no projects and no budget activity
    if (marketing.data) {
      const s = marketing.data.summary
      if (!s || ((s.active_count ?? 0) === 0 && (s.total_budget ?? 0) === 0 && (s.total_spent ?? 0) === 0)) {
        empty.add('marketing_summary')
      }
    }

    // efactura_status and online_users: always considered "has data" (status indicators)

    return empty
  }, [invoices.data, statements.data, hr.data, marketing.data, approvals.data, notifications.data])
}
