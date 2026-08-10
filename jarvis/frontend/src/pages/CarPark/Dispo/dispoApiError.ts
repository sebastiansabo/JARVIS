import { ApiError } from '@/api/client'

// Every Dispo guard/transition route surfaces a ValueError verbatim as
// `{ error: "..." }` on a 400 (see carpark/routes/dispo.py's module
// docstring) — this pulls that message out of an ApiError thrown by
// src/api/client.ts, falling back to a Romanian default for anything else
// (network failure, unexpected 500, etc).
export function apiErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    const data = err.data as { error?: unknown } | null
    if (data && typeof data.error === 'string' && data.error) return data.error
  }
  if (err instanceof Error && err.message) return err.message
  return fallback
}
