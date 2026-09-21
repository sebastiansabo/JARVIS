import { useRef, type PointerEvent as ReactPointerEvent } from 'react'

// Momentum drag-to-scroll for horizontal strips — grab, flick, and it glides to a
// stop with iOS-style inertia (exponential deceleration). Mouse only; touch/pen keep
// the browser's native momentum scrolling.
export function useDragScroll() {
  const ref = useRef<HTMLDivElement>(null)
  const st = useRef({
    down: false, moved: false, captured: false, startX: 0, startLeft: 0,
    lastX: 0, lastT: 0, velocity: 0, amplitude: 0, target: 0, timestamp: 0, raf: 0,
  })

  const stopInertia = () => {
    if (st.current.raf) cancelAnimationFrame(st.current.raf)
    st.current.raf = 0
  }

  // exponential glide toward target; ~325ms time-constant matches the iOS feel
  const glide = () => {
    const el = ref.current
    const s = st.current
    if (!el) return
    const delta = -s.amplitude * Math.exp(-(performance.now() - s.timestamp) / 325)
    if (delta > 0.4 || delta < -0.4) {
      el.scrollLeft = s.target + delta
      s.raf = requestAnimationFrame(glide)
    } else {
      el.scrollLeft = s.target
      s.raf = 0
    }
  }

  const release = (e?: ReactPointerEvent) => {
    const s = st.current
    const el = ref.current
    if (!s.down || !el) return
    s.down = false
    if (e && s.captured) { try { el.releasePointerCapture(e.pointerId) } catch { /* already released */ } }
    s.captured = false
    if (performance.now() - s.lastT > 100) s.velocity = 0 // paused before release → no fling
    s.amplitude = -s.velocity * 600
    s.target = el.scrollLeft + s.amplitude
    s.timestamp = performance.now()
    stopInertia()
    if (Math.abs(s.amplitude) > 1) s.raf = requestAnimationFrame(glide)
  }

  return {
    ref,
    didDrag: () => st.current.moved,
    dragProps: {
      onPointerDown: (e: ReactPointerEvent) => {
        if (e.pointerType !== 'mouse') return
        const el = ref.current
        if (!el) return
        const s = st.current
        stopInertia()
        s.down = true
        s.moved = false
        s.captured = false
        s.startX = e.clientX
        s.startLeft = el.scrollLeft
        s.lastX = e.clientX
        s.lastT = performance.now()
        s.velocity = 0
        // Do NOT capture the pointer here: capturing on pointerdown retargets a
        // child's `click` to this container, swallowing taps on thumbnails/buttons
        // inside the strip. Capture only once a real drag starts (onPointerMove).
      },
      onPointerMove: (e: ReactPointerEvent) => {
        const s = st.current
        const el = ref.current
        if (!s.down || !el) return
        const t = performance.now()
        const dx = e.clientX - s.lastX
        const dt = t - s.lastT
        if (Math.abs(e.clientX - s.startX) > 4) {
          s.moved = true
          // First significant movement → this is a drag, not a click. Capture now
          // so the strip keeps receiving moves even if the pointer leaves it.
          if (!s.captured) {
            try { el.setPointerCapture(e.pointerId) } catch { /* noop */ }
            s.captured = true
          }
        }
        if (dt > 0) s.velocity = 0.8 * (dx / dt) + 0.2 * s.velocity
        el.scrollLeft = s.startLeft - (e.clientX - s.startX)
        s.lastX = e.clientX
        s.lastT = t
      },
      onPointerUp: (e: ReactPointerEvent) => release(e),
      onPointerCancel: (e: ReactPointerEvent) => release(e),
    },
  }
}
