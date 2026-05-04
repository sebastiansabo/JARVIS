/**
 * Telemetry hooks for React components.
 *
 * Usage:
 *   const trackClick = useTrackClick()
 *   <Button onClick={() => { trackClick('save_invoice', 'Save Invoice', 'invoice_form'); handleSave() }}>
 *
 *   const trackEvent = useTrackEvent()
 *   trackEvent('Filter Applied', { filter_type: 'date_range', module: 'accounting' })
 */

import { useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import { telemetry } from '@/lib/telemetry'

/**
 * Hook for tracking button clicks with automatic page context.
 *
 * @returns trackClick(buttonId, buttonText?, pageSection?)
 */
export function useTrackClick() {
  const location = useLocation()

  return useCallback(
    (buttonId: string, buttonText?: string, pageSection?: string) => {
      telemetry.track('Button Clicked', {
        button_id: buttonId,
        ...(buttonText && { button_text: buttonText }),
        ...(pageSection && { page_section: pageSection }),
        page_path: location.pathname,
      })
    },
    [location.pathname],
  )
}

/**
 * Hook for tracking arbitrary events with automatic page context.
 *
 * @returns trackEvent(eventName, properties?)
 */
export function useTrackEvent() {
  const location = useLocation()

  return useCallback(
    (eventName: string, properties: Record<string, unknown> = {}) => {
      telemetry.track(eventName, {
        ...properties,
        page_path: location.pathname,
      })
    },
    [location.pathname],
  )
}
