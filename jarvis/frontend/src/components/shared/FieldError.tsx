/**
 * Inline field-level error message shown below form inputs.
 * Renders nothing when message is undefined/empty.
 */
export function FieldError({ message }: { message?: string }) {
  if (!message) return null
  return (
    <p className="text-[0.8rem] text-destructive mt-0.5" role="alert">
      {message}
    </p>
  )
}
