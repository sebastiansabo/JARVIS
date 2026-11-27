import { useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { EmptyState } from '@/components/shared/EmptyState'
import { Button } from '@/components/ui/button'

// Minimal placeholder for /app/logistics/parc/:id -- the real "Fișa
// mașinii" (timeline/history, tasks, checklist, costs/care, documents per
// design spec §4.1) is a later phase. This exists only so a Parc row-click
// doesn't 404; "Back" from here returns to Parc with filters+sort intact
// since the Parc link that brought us here preserved the querystring and
// browser history does the rest.
export default function VehicleDetail() {
  const navigate = useNavigate()

  return (
    <div className="space-y-4">
      <PageHeader title="Fișa mașinii" />
      <EmptyState
        title="Fișa mașinii — în curând"
        description="Detaliul vehiculului (istoric, task-uri, checklist, costuri) vine într-o fază următoare."
        action={
          <Button variant="outline" onClick={() => navigate(-1)}>
            <ArrowLeft className="h-4 w-4" />
            Înapoi la Parc
          </Button>
        }
      />
    </div>
  )
}
