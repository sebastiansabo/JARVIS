import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import SignatureCanvas from '@/components/shared/SignatureCanvas'
import { signaturesApi } from '@/api/signatures'
import { AlertTriangle, Loader2 } from 'lucide-react'

interface SignatureModalProps {
  signatureId: number
  documentName: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onComplete: () => void
  onReject: () => void
}

export default function SignatureModal({
  signatureId,
  documentName,
  open,
  onOpenChange,
  onComplete,
  onReject,
}: SignatureModalProps) {
  const [showRejectConfirm, setShowRejectConfirm] = useState(false)

  const signMutation = useMutation({
    mutationFn: (base64: string) => signaturesApi.sign(signatureId, base64),
    onSuccess: () => {
      toast.success('Document signed successfully')
      onOpenChange(false)
      onComplete()
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to sign document')
    },
  })

  const rejectMutation = useMutation({
    mutationFn: () => signaturesApi.reject(signatureId),
    onSuccess: () => {
      toast.success('Signature request rejected')
      onOpenChange(false)
      onReject()
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to reject signature')
    },
  })

  const isLoading = signMutation.isPending || rejectMutation.isPending

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-[600px]">
          <DialogHeader>
            <DialogTitle>Sign Document</DialogTitle>
            <DialogDescription>
              You are signing: <strong>{documentName}</strong>
            </DialogDescription>
          </DialogHeader>

          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 flex items-start gap-2 text-sm text-amber-800">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            <span>
              By signing this document, you confirm that you have reviewed its contents
              and agree to its terms. This action cannot be undone.
            </span>
          </div>

          <SignatureCanvas
            onSave={(base64) => signMutation.mutate(base64)}
            disabled={isLoading}
          />

          <div className="flex justify-between items-center pt-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setShowRejectConfirm(true)}
              disabled={isLoading}
              className="text-destructive hover:text-destructive"
            >
              Reject Signing
            </Button>
            {isLoading && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Processing...
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={showRejectConfirm}
        onOpenChange={setShowRejectConfirm}
        title="Reject Signature Request"
        description="Are you sure you want to reject this signature request? This action cannot be undone."
        confirmLabel="Reject"
        variant="destructive"
        onConfirm={() => {
          setShowRejectConfirm(false)
          rejectMutation.mutate()
        }}
      />
    </>
  )
}
