import { useState, useMemo, useCallback } from 'react'

/**
 * Per-field validator: returns an error message string or undefined if valid.
 */
type Validator<V> = (value: V) => string | undefined

/**
 * Lightweight inline form validation hook.
 *
 * Tracks which fields have been "touched" (blurred) and returns error
 * messages only for touched + invalid fields.  Call `touchAll()` before
 * submit to reveal all errors at once.
 *
 * @example
 * ```tsx
 * const v = useFormValidation(
 *   { name, email },
 *   { name: (v) => !v.trim() ? 'Required' : undefined }
 * )
 * <Input
 *   onBlur={() => v.touch('name')}
 *   className={cn(v.error('name') && 'border-destructive')}
 * />
 * {v.error('name') && <FieldError message={v.error('name')} />}
 * ```
 */
export function useFormValidation<
  T extends Record<string, unknown>,
>(
  values: T,
  rules: { [K in keyof T]?: Validator<T[K]> },
) {
  const [touched, setTouched] = useState<Set<keyof T>>(new Set())

  /** All current errors (touched or not). */
  const errors = useMemo(() => {
    const errs: Partial<Record<keyof T, string>> = {}
    for (const key of Object.keys(rules) as (keyof T)[]) {
      const validate = rules[key]
      if (!validate) continue
      const msg = validate(values[key])
      if (msg) errs[key] = msg
    }
    return errs
  }, [values, rules])

  /** Mark a field as touched (call on blur). */
  const touch = useCallback((field: keyof T) => {
    setTouched((prev) => {
      if (prev.has(field)) return prev
      const next = new Set(prev)
      next.add(field)
      return next
    })
  }, [])

  /** Mark all validated fields as touched (call before submit). */
  const touchAll = useCallback(() => {
    setTouched(new Set(Object.keys(rules) as (keyof T)[]))
  }, [rules])

  /** Error message for a field, only if touched. */
  const error = useCallback(
    (field: keyof T): string | undefined =>
      touched.has(field) ? errors[field] : undefined,
    [touched, errors],
  )

  /** True when no validation errors exist. */
  const isValid = Object.keys(errors).length === 0

  return { touch, touchAll, error, isValid, errors }
}
