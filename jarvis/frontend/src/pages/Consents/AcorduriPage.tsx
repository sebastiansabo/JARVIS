import { Link } from 'react-router-dom'
import { FileText, ChevronRight } from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { Card, CardContent } from '@/components/ui/card'

// The three consent documents every user signs during onboarding (see
// core/consents/repositories/consent_repository.py seed data). This is a
// read-only re-read list, not a management screen — hardcoding the keys
// avoids an extra admin-only /api/consents/documents call.
const DOCS = [
  { key: 'data_usage', label: 'Acord privind utilizarea datelor de contact' },
  { key: 'gdpr', label: 'Notă de informare și acord GDPR' },
  { key: 'nda', label: 'Acord de confidențialitate (NDA)' },
]

export default function AcorduriPage() {
  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader title="Acordurile mele" description="Documentele legale pe care le-ai semnat" />

      <div className="mx-auto max-w-2xl space-y-2">
        {DOCS.map((doc) => (
          <Link key={doc.key} to={`/app/acord/${doc.key}`} className="block">
            <Card className="transition-colors hover:bg-muted/50">
              <CardContent className="flex items-center gap-3 p-4">
                <FileText className="h-5 w-5 shrink-0 text-muted-foreground" />
                <span className="flex-1 text-sm font-medium">{doc.label}</span>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}
