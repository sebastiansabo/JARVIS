/**
 * Shared hook that enhances a voucher form schema with context fields:
 * Company, Department, Approver (user_select), and Signature (if missing).
 *
 * Used everywhere the voucher form is rendered — keeps it identical.
 */
import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import type { FormField } from '@/types/forms'

const VOUCHER_SLUG = 'voucher-issuance'

interface VoucherSchemaResult {
  schema: FormField[]
  defaultValues: Record<string, unknown> | undefined
  submitLabel: string
  needsSignatureSave: boolean
}

export function useVoucherSchema(
  baseSchema: FormField[],
  slug: string,
): VoucherSchemaResult {
  const user = useAuthStore((s) => s.user)
  const isVoucher = slug === VOUCHER_SLUG

  const { data: sigStatus } = useQuery({
    queryKey: ['voucher-sig-status'],
    queryFn: () => api.get<{ has_signature: boolean }>('/api/vouchers/signature-status'),
    enabled: isVoucher,
    staleTime: 60_000,
  })

  const schema = useMemo(() => {
    if (!isVoucher || !baseSchema.length) return baseSchema
    const contextFields: FormField[] = [
      { id: 'f_company', type: 'company_select' as any, label: 'Company', required: true, order: -2 },
      { id: 'f_department', type: 'department_select' as any, label: 'Department', required: false, order: -1, config: { companyField: 'f_company' } },
    ]
    const startDateField: FormField = {
      id: 'f_start_date', type: 'date' as any, label: 'Starting Date', required: false,
      placeholder: 'Leave empty for today', order: 6.5,
    }
    const approverField: FormField = {
      id: 'f_approver', type: 'user_select' as any, label: 'Send for Approval to', required: false,
      placeholder: 'Leave empty for direct manager', order: 98,
    }
    let enhanced = [...contextFields, ...baseSchema, startDateField, approverField]
    if (sigStatus && !sigStatus.has_signature) {
      enhanced = [...enhanced, { id: 'f_signature', type: 'signature' as const, label: 'Your Signature', required: true, order: 99 }]
    }
    return enhanced
  }, [isVoucher, baseSchema, sigStatus])

  const defaultValues = useMemo(() => {
    if (!isVoucher) return undefined
    return { f_company: user?.company || '', f_department: user?.department || '' }
  }, [isVoucher, user])

  return {
    schema,
    defaultValues,
    submitLabel: isVoucher ? 'Issue Voucher' : 'Submit',
    needsSignatureSave: isVoucher && !!sigStatus && !sigStatus.has_signature,
  }
}
