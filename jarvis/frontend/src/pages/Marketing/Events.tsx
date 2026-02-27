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
    <div className="space-y-4">
      <PageHeader title="Events" description="Create and manage events" />
      <Suspense fallback={<Loader />}>
        <EventsTab />
      </Suspense>
    </div>
  )
}
