import { lazy, Suspense } from 'react'
import { PageHeader } from '@/components/shared/PageHeader'
import { Skeleton } from '@/components/ui/skeleton'

const EventsTab = lazy(() => import('../Hr/EventsTab'))

function Loader() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-10 w-full" />
    </div>
  )
}

export default function MarketingEvents() {
  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader
        title="Events"
        breadcrumbs={[
          { label: 'Marketing', href: '/app/marketing' },
          { label: 'Events' },
        ]}
      />
      <Suspense fallback={<Loader />}>
        <EventsTab />
      </Suspense>
    </div>
  )
}
