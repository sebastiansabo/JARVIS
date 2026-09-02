import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { consentsApi } from '@/api/consents'
import { PageHeader } from '@/components/shared/PageHeader'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

/**
 * Read-only re-read view of a signed consent document. Fetches the currently
 * active version by doc_key — same content the user agreed to during
 * onboarding (see consentsApi.getDocument / GET /api/consents/documents/<doc_key>).
 * 404 (unknown or inactive key) falls through to the "not found" state below.
 */
export default function AcordViewer() {
  const { docKey = '' } = useParams()
  const { data, isLoading } = useQuery({
    queryKey: ['consent-doc', docKey],
    queryFn: () => consentsApi.getDocument(docKey),
    enabled: !!docKey,
  })
  const doc = data?.document

  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader
        title={doc?.title ?? 'Acord'}
        breadcrumbs={[
          { label: 'Acordurile mele', href: '/app/acorduri' },
          { label: doc?.title ?? 'Acord' },
        ]}
      />

      <div className="mx-auto max-w-2xl space-y-4">
        <Link to="/app/acorduri" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" />
          Înapoi la acordurile mele
        </Link>

        {isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-6 w-64" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
          </div>
        ) : !doc ? (
          <Card>
            <CardContent className="p-6 text-sm text-muted-foreground">
              Documentul nu a fost găsit sau nu mai este activ.
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardContent className="p-6">
              <p className="mb-4 text-xs text-muted-foreground">Versiunea {doc.version}</p>
              <div className="whitespace-pre-wrap text-sm leading-relaxed">{doc.body}</div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
