import { render, fireEvent } from '@testing-library/react'
import { vi, test, expect } from 'vitest'
import { useDragScroll } from './useDragScroll'

// Renders a strip using the hook and exposes didDrag() to the test.
function Harness({ onReady }: { onReady: (didDrag: () => boolean) => void }) {
  const s = useDragScroll()
  onReady(s.didDrag)
  return (
    <div data-testid="strip" ref={s.ref} {...s.dragProps}>
      <button type="button">thumb</button>
    </div>
  )
}

function renderStrip() {
  let didDrag: () => boolean = () => false
  const { container } = render(<Harness onReady={(fn) => (didDrag = fn)} />)
  const strip = container.querySelector('[data-testid="strip"]') as HTMLElement
  const captureSpy = vi.spyOn(strip, 'setPointerCapture')
  return { strip, captureSpy, didDrag: () => didDrag() }
}

test('a plain click does NOT capture the pointer (so child thumbnail clicks fire)', () => {
  const { strip, captureSpy, didDrag } = renderStrip()
  fireEvent.pointerDown(strip, { pointerType: 'mouse', clientX: 10, pointerId: 1 })
  fireEvent.pointerUp(strip, { pointerType: 'mouse', clientX: 10, pointerId: 1 })
  // Capturing on pointerdown retargets the child's click to this container and
  // swallows the thumbnail tap — so a no-drag press must never capture.
  expect(captureSpy).not.toHaveBeenCalled()
  expect(didDrag()).toBe(false)
})

test('a real drag (>4px) captures the pointer and reports didDrag', () => {
  const { strip, captureSpy, didDrag } = renderStrip()
  fireEvent.pointerDown(strip, { pointerType: 'mouse', clientX: 10, pointerId: 2 })
  fireEvent.pointerMove(strip, { pointerType: 'mouse', clientX: 40, pointerId: 2 })
  expect(captureSpy).toHaveBeenCalled()
  expect(didDrag()).toBe(true)
})

test('releases capture on pointerup after a drag, but never for a plain click', () => {
  const drag = renderStrip()
  const dragRelease = vi.spyOn(drag.strip, 'releasePointerCapture')
  fireEvent.pointerDown(drag.strip, { pointerType: 'mouse', clientX: 10, pointerId: 3 })
  fireEvent.pointerMove(drag.strip, { pointerType: 'mouse', clientX: 40, pointerId: 3 })
  fireEvent.pointerUp(drag.strip, { pointerType: 'mouse', clientX: 40, pointerId: 3 })
  expect(dragRelease).toHaveBeenCalled()

  const click = renderStrip()
  const clickRelease = vi.spyOn(click.strip, 'releasePointerCapture')
  fireEvent.pointerDown(click.strip, { pointerType: 'mouse', clientX: 10, pointerId: 4 })
  fireEvent.pointerUp(click.strip, { pointerType: 'mouse', clientX: 10, pointerId: 4 })
  expect(clickRelease).not.toHaveBeenCalled()
})
