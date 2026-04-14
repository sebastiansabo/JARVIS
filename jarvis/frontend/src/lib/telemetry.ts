/**
 * Telemetry SDK — lightweight, self-hosted event tracking.
 *
 * Follows the Segment Object-Action spec:
 *   - Event names: Title Case, Object Action (e.g. "Button Clicked", "Page Viewed")
 *   - Properties: snake_case keys
 *   - Context: auto-collected page/device metadata
 *   - Identity: resolved server-side from session (never sent from client)
 *
 * Usage:
 *   telemetry.track('Button Clicked', { button_id: 'save_invoice', button_text: 'Save' })
 */

type Properties = Record<string, unknown>

interface TelemetryEvent {
  event: string
  timestamp: string
  session_id: string
  properties: Properties
  context: {
    page_path: string
    page_title: string
    referrer: string
    screen_width: number
    screen_height: number
    viewport_width: number
    viewport_height: number
    locale: string
    timezone: string
  }
}

// ── Session management ──────────────────────────────────────────

const SESSION_KEY = 'jarvis_telemetry_session'

function getSessionId(): string {
  let id = sessionStorage.getItem(SESSION_KEY)
  if (!id) {
    id = `s_${crypto.randomUUID()}`
    sessionStorage.setItem(SESSION_KEY, id)
  }
  return id
}

// ── Context collection ──────────────────────────────────────────

function getContext() {
  return {
    page_path: window.location.pathname,
    page_title: document.title,
    referrer: document.referrer,
    screen_width: window.screen.width,
    screen_height: window.screen.height,
    viewport_width: window.innerWidth,
    viewport_height: window.innerHeight,
    locale: navigator.language,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  }
}

// ── Event queue and batching ────────────────────────────────────

const FLUSH_INTERVAL_MS = 5_000
const FLUSH_BATCH_SIZE = 20
const HEARTBEAT_INTERVAL_MS = 60_000

let eventQueue: TelemetryEvent[] = []
let flushTimer: ReturnType<typeof setInterval> | null = null
let heartbeatTimer: ReturnType<typeof setInterval> | null = null
let isInitialized = false
let _onVisibilityChange: (() => void) | null = null
let _onBeforeUnload: (() => void) | null = null

function createEvent(eventName: string, properties: Properties = {}): TelemetryEvent {
  return {
    event: eventName,
    timestamp: new Date().toISOString(),
    session_id: getSessionId(),
    properties,
    context: getContext(),
  }
}

function flush() {
  if (eventQueue.length === 0) return

  const batch = eventQueue.splice(0, 50)
  const payload = JSON.stringify({ events: batch })

  // Prefer sendBeacon for reliability (works during page unload)
  if (navigator.sendBeacon) {
    const blob = new Blob([payload], { type: 'application/json' })
    navigator.sendBeacon('/api/telemetry/events', blob)
  } else {
    fetch('/api/telemetry/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: payload,
      keepalive: true,
    }).catch(() => {
      // Silently drop — telemetry should never break the app
    })
  }
}

function sendHeartbeat() {
  if (document.hidden) return
  const payload = JSON.stringify({ session_id: getSessionId() })
  if (navigator.sendBeacon) {
    const blob = new Blob([payload], { type: 'application/json' })
    navigator.sendBeacon('/api/telemetry/heartbeat', blob)
  } else {
    fetch('/api/telemetry/heartbeat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: payload,
      keepalive: true,
    }).catch(() => {})
  }
}

// ── Lifecycle ───────────────────────────────────────────────────

function init() {
  if (isInitialized) return
  isInitialized = true

  // Flush timer
  flushTimer = setInterval(() => {
    if (eventQueue.length > 0) flush()
  }, FLUSH_INTERVAL_MS)

  // Heartbeat timer
  heartbeatTimer = setInterval(sendHeartbeat, HEARTBEAT_INTERVAL_MS)

  // Flush on visibility change (tab hide)
  _onVisibilityChange = () => { if (document.hidden) flush() }
  document.addEventListener('visibilitychange', _onVisibilityChange)

  // Flush + end session on page unload
  _onBeforeUnload = () => {
    track('Session Ended', { exit_page: window.location.pathname })
    flush()
  }
  window.addEventListener('beforeunload', _onBeforeUnload)

  // Session start
  track('Session Started', {
    entry_page: window.location.pathname,
  })
}

function destroy() {
  if (flushTimer) clearInterval(flushTimer)
  if (heartbeatTimer) clearInterval(heartbeatTimer)
  if (_onVisibilityChange) document.removeEventListener('visibilitychange', _onVisibilityChange)
  if (_onBeforeUnload) window.removeEventListener('beforeunload', _onBeforeUnload)
  _onVisibilityChange = null
  _onBeforeUnload = null
  flush()
  isInitialized = false
}

// ── Public API ──────────────────────────────────────────────────

function track(eventName: string, properties: Properties = {}) {
  if (!isInitialized && eventName !== 'Session Started') return

  const event = createEvent(eventName, properties)
  eventQueue.push(event)

  if (eventQueue.length >= FLUSH_BATCH_SIZE) {
    flush()
  }
}

function pageView(pagePath: string, pageTitle: string, previousPage: string | null, durationMs: number | null) {
  const props: Properties = {
    page_path: pagePath,
    page_title: pageTitle,
  }
  if (previousPage) props.previous_page = previousPage
  if (durationMs !== null && durationMs > 0) props.duration_ms = durationMs

  track('Page Viewed', props)
}

export const telemetry = {
  init,
  destroy,
  track,
  pageView,
  flush,
  getSessionId,
}
