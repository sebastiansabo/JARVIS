import { useState, lazy, Suspense } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Ticket, ScanLine } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { FormRenderer } from '@/components/forms/FormRenderer'
import { formsApi } from '@/api/forms'

const VoucherRedeem = lazy(() => import('./VoucherRedeem'))

export default function VoucherPortal() {
  const { code } = useParams<{ code?: string }>()
  const [mode, setMode] = useState<'issue' | 'redeem'>(code ? 'redeem' : 'issue')
  const [submitted, setSubmitted] = useState(false)

  const { data: form, isLoading } = useQuery({
    queryKey: ['public-form', 'voucher-issuance'],
    queryFn: () => formsApi.getPublicForm('voucher-issuance'),
    enabled: mode === 'issue',
  })

  const submitMutation = useMutation({
    mutationFn: (answers: Record<string, unknown>) =>
      formsApi.submitPublicForm('voucher-issuance', {
        answers,
        utm_data: {},
      }),
    onSuccess: (data) => {
      setSubmitted(true)
      toast.success(data.thank_you_message || 'Voucher submitted!')
    },
  })

  return (
    <div className="min-h-screen bg-gray-50 flex items-start justify-center p-4 pt-8">
      <div className="w-full max-w-lg space-y-6">
        {/* Header */}
        <div className="text-center">
          <h1 className="text-2xl font-bold">Voucher Portal</h1>
          <p className="text-sm text-gray-500 mt-1">Issue a new voucher or redeem an existing one</p>
        </div>

        {/* Toggle */}
        <div className="flex rounded-lg border bg-white p-1 gap-1">
          <button
            className={`flex-1 flex items-center justify-center gap-2 rounded-md py-2.5 text-sm font-medium transition-colors ${
              mode === 'issue' ? 'bg-slate-800 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-100'
            }`}
            onClick={() => { setMode('issue'); setSubmitted(false) }}
          >
            <Ticket className="h-4 w-4" />
            Issue Voucher
          </button>
          <button
            className={`flex-1 flex items-center justify-center gap-2 rounded-md py-2.5 text-sm font-medium transition-colors ${
              mode === 'redeem' ? 'bg-slate-800 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-100'
            }`}
            onClick={() => { setMode('redeem'); setSubmitted(false) }}
          >
            <ScanLine className="h-4 w-4" />
            Redeem Voucher
          </button>
        </div>

        {/* Issue mode */}
        {mode === 'issue' && !submitted && (
          <div className="bg-white rounded-xl shadow-sm border p-6 space-y-4">
            <div>
              <h2 className="text-xl font-bold">{form?.name || 'Voucher Issuance'}</h2>
              {form?.description && <p className="text-muted-foreground text-sm mt-1">{form.description}</p>}
            </div>
            {isLoading ? (
              <div className="py-8 text-center text-muted-foreground">Loading form...</div>
            ) : form?.schema ? (
              <>
                <FormRenderer
                  schema={form.schema}
                  onSubmit={(answers) => submitMutation.mutate(answers)}
                  submitting={submitMutation.isPending}
                  submitLabel="Issue Voucher"
                />
                {submitMutation.isError && (
                  <p className="text-sm text-destructive text-center">
                    {(submitMutation.error as any)?.error || 'Failed to submit. Please try again.'}
                  </p>
                )}
              </>
            ) : (
              <div className="py-8 text-center text-muted-foreground">Form not available</div>
            )}
          </div>
        )}

        {/* Issue success */}
        {mode === 'issue' && submitted && (
          <div className="bg-white rounded-xl shadow-sm border p-6 text-center space-y-4">
            <div className="rounded-full bg-green-100 p-4 w-16 h-16 mx-auto flex items-center justify-center">
              <svg className="h-8 w-8 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-xl font-bold">Voucher Submitted!</h2>
            <p className="text-muted-foreground">Your voucher request has been submitted for approval.</p>
            <Button variant="outline" onClick={() => setSubmitted(false)}>Issue Another</Button>
          </div>
        )}

        {/* Redeem mode */}
        {mode === 'redeem' && (
          <Suspense fallback={<div className="py-8 text-center text-muted-foreground">Loading...</div>}>
            <VoucherRedeem />
          </Suspense>
        )}

        <p className="text-center text-xs text-gray-400">Powered by JARVIS</p>
      </div>
    </div>
  )
}
