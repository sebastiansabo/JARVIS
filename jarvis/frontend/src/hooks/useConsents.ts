import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { consentsApi } from '@/api/consents'

export function usePendingConsents(enabled: boolean = true) {
  return useQuery({
    queryKey: ['consents', 'pending'],
    queryFn: () => consentsApi.getPending(),
    enabled,
  })
}

export function useSignConsent() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ documentId, signatureImage }: { documentId: number; signatureImage: string }) =>
      consentsApi.sign(documentId, signatureImage),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['consents', 'pending'] })
      // consents_complete / pending_consents_count live on the current-user payload too.
      queryClient.invalidateQueries({ queryKey: ['currentUser'] })
    },
  })
}
