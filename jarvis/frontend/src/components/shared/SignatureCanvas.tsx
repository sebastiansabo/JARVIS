import { useRef, useEffect, useCallback } from 'react'
import SignaturePad from 'signature_pad'
import { Button } from '@/components/ui/button'
import { Eraser, Check } from 'lucide-react'

interface SignatureCanvasProps {
  onSave: (base64: string) => void
  onClear?: () => void
  disabled?: boolean
  width?: number
  height?: number
}

export default function SignatureCanvas({
  onSave,
  onClear,
  disabled = false,
  width = 500,
  height = 200,
}: SignatureCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const padRef = useRef<SignaturePad | null>(null)

  useEffect(() => {
    if (!canvasRef.current) return

    const canvas = canvasRef.current
    const ratio = Math.max(window.devicePixelRatio || 1, 1)
    canvas.width = width * ratio
    canvas.height = height * ratio
    canvas.style.width = `${width}px`
    canvas.style.height = `${height}px`
    const ctx = canvas.getContext('2d')
    if (ctx) ctx.scale(ratio, ratio)

    padRef.current = new SignaturePad(canvas, {
      backgroundColor: 'rgb(255, 255, 255)',
      penColor: 'rgb(0, 0, 0)',
    })

    if (disabled) {
      padRef.current.off()
    }

    return () => {
      padRef.current?.off()
      padRef.current = null
    }
  }, [width, height, disabled])

  const handleClear = useCallback(() => {
    padRef.current?.clear()
    onClear?.()
  }, [onClear])

  const handleSave = useCallback(() => {
    if (!padRef.current) return
    if (padRef.current.isEmpty()) return
    const base64 = padRef.current.toDataURL('image/png')
    onSave(base64)
  }, [onSave])

  return (
    <div className="space-y-3">
      <div className="border rounded-lg overflow-hidden bg-white">
        <canvas
          ref={canvasRef}
          className="cursor-crosshair"
          style={{ width, height, touchAction: 'none' }}
        />
      </div>
      <div className="flex gap-2 justify-end">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleClear}
          disabled={disabled}
        >
          <Eraser className="h-4 w-4 mr-1" />
          Clear
        </Button>
        <Button
          type="button"
          size="sm"
          onClick={handleSave}
          disabled={disabled}
        >
          <Check className="h-4 w-4 mr-1" />
          Save Signature
        </Button>
      </div>
    </div>
  )
}
