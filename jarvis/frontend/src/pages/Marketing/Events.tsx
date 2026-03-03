import { lazy, Suspense } from 'react'
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
    <Suspense fallback={<Loader />}>
      <EventsTab />
    </Suspense>
  )
}
