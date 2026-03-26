import { useState, useMemo } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { formsApi } from '@/api/forms'
import { FormRenderer } from '@/components/forms/FormRenderer'
import { Skeleton } from '@/components/ui/skeleton'

export default function PublicForm() {
  const { slug } = useParams<{ slug: string }>()
  const [searchParams] = useSearchParams()
  const [submitted, setSubmitted] = useState(false)
  const [thankYou, setThankYou] = useState('')

  const { data: form, isLoading, isError } = useQuery({
    queryKey: ['public-form', slug],
    queryFn: () => formsApi.getPublicForm(slug!),
    enabled: !!slug,
  })

  // Capture UTM params from URL
  const utmData = useMemo(() => {
    const utms: Record<string, string> = {}
    const tracked = form?.utm_config?.track ?? [
      'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    ]
    for (const param of tracked) {
      const val = searchParams.get(param)
      if (val) utms[param] = val
    }
    return utms
  }, [searchParams, form])

  // Pre-populate hidden fields from URL params
  const schema = useMemo(() => {
    if (!form?.schema) return []
    return form.schema.map((field) => {
      if (field.type === 'hidden') {
        const urlVal = searchParams.get(field.label) || searchParams.get(field.id)
        if (urlVal) return { ...field, config: { ...field.config, defaultValue: urlVal } }
      }
      return field
    })
  }, [form, searchParams])

  const submitMutation = useMutation({
    mutationFn: (answers: Record<string, unknown>) =>
      formsApi.submitPublicForm(slug!, {
        answers,
        utm_data: utmData,
        respondent_name: (answers._respondent_name as string) || undefined,
        respondent_email: (answers._respondent_email as string) || undefined,
        respondent_phone: (answers._respondent_phone as string) || undefined,
      }),
    onSuccess: (data) => {
      setSubmitted(true)
      setThankYou(data.thank_you_message || 'Thank you for your submission!')
      if (data.redirect_url) {
        setTimeout(() => { window.location.href = data.redirect_url! }, 2000)
      }
    },
  })

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
        <div className="w-full max-w-xl space-y-4">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-4 w-96" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      </div>
    )
  }

  if (isError || !form) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
        <div className="text-center space-y-2">
          <h1 className="text-2xl font-bold">Form Not Found</h1>
          <p className="text-muted-foreground">This form may have been disabled or deleted.</p>
        </div>
      </div>
    )
  }

  if (submitted) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
        <div className="w-full max-w-xl text-center space-y-4">
          <div className="rounded-full bg-green-100 p-4 w-16 h-16 mx-auto flex items-center justify-center">
            <svg className="h-8 w-8 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold">Submitted!</h1>
          <p className="text-muted-foreground">{thankYou}</p>
        </div>
      </div>
    )
  }

  const branding = form.branding || {}

  return (
    <div
      className="min-h-screen flex items-start justify-center p-4 pt-12"
      style={{ backgroundColor: branding.background_color || '#f9fafb' }}
    >
      <div className="w-full max-w-xl">
        <div className="bg-white rounded-xl shadow-sm border p-6 space-y-4">
          {branding.logo_url && (
            <img src={branding.logo_url} alt="Logo" className="h-10 object-contain" />
          )}
          <div>
            <h1
              className="text-2xl font-bold"
              style={{ color: branding.primary_color || undefined }}
            >
              {form.name}
            </h1>
            {form.description && (
              <p className="text-muted-foreground mt-1">{form.description}</p>
            )}
          </div>

          <FormRenderer
            schema={schema}
            onSubmit={(answers) => submitMutation.mutate(answers)}
            submitting={submitMutation.isPending}
          />

          {submitMutation.isError && (
            <p className="text-sm text-destructive text-center">
              {(submitMutation.error as any)?.error || 'Failed to submit. Please try again.'}
            </p>
          )}
        </div>

        <p className="text-center text-xs text-muted-foreground mt-4">
          Powered by {form.company_name}
        </p>
      </div>
    </div>
  )
}
