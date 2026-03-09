import { useNavigate } from 'react-router-dom'
import { PageHeader } from '@/components/shared/PageHeader'
import { CalendarView } from './index'

export default function CalendarPage() {
  const navigate = useNavigate()

  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader
        title="Calendar"
        breadcrumbs={[
          { label: 'Marketing', shortLabel: 'Mkt.', href: '/app/marketing' },
          { label: 'Calendar' },
        ]}
      />
      <CalendarView onSelect={(p) => navigate(`/app/marketing/projects/${p.id}`)} />
    </div>
  )
}
