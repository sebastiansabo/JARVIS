import { useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Camera,
  ChevronLeft,
  ChevronRight,
  GripVertical,
  LayoutGrid,
  Loader2,
  Maximize2,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import {
  DndContext,
  PointerSensor,
  TouchSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  closestCenter,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  rectSortingStrategy,
  arrayMove,
  useSortable,
  sortableKeyboardCoordinates,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { toast } from 'sonner'
import { mediaUrl } from '@/lib/media'
import { useDragScroll } from '@/pages/CarPark/useDragScroll'
import { Button } from '@/components/ui/button'
import { buybackApi } from '@/api/buyback'
import type { BuybackPhoto } from '@/types/buyback'

// ── Photo Gallery (BuyBack) ─────────────────────────────────
// Mirrors CarPark's Detail.tsx gallery (hero + filmstrip + fullscreen
// "Toate pozele" grid, drag-to-reorder via @dnd-kit), adapted to buyback's
// simpler single-photo delete (no bulk soft-delete endpoint) and to owning
// its own optimistic photo order locally (this component receives `photos`
// as a prop rather than owning the record query itself).
const GALLERY_MAX_WIDTH = 600 // px — the whole gallery block never exceeds this width

export default function PhotoGallery({
  recordId,
  photos: photosProp,
  canEdit,
}: {
  recordId: number
  photos: BuybackPhoto[]
  canEdit: boolean
}) {
  const queryClient = useQueryClient()
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['buyback-record', recordId] })

  // Local optimistic order, seeded from + kept in sync with the prop (the
  // parent detail page owns the actual query and refetches on invalidation).
  const [photos, setPhotos] = useState(photosProp)
  useEffect(() => setPhotos(photosProp), [photosProp])

  const [active, setActive] = useState(0)
  const [gridOpen, setGridOpen] = useState(false)
  const [initialPreview, setInitialPreview] = useState<number | null>(null)
  const strip = useDragScroll()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const idx = photos.length ? Math.min(active, photos.length - 1) : 0

  useEffect(() => {
    const el = strip.ref.current?.querySelector<HTMLElement>(`[data-i="${idx}"]`)
    el?.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx])

  const uploadMutation = useMutation({
    mutationFn: (files: File[]) => buybackApi.uploadPhotos(recordId, files),
    onSuccess: () => {
      invalidate()
      toast.success('Poze încărcate')
    },
    onError: () => toast.error('Încărcarea pozelor a eșuat'),
  })

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    e.target.value = ''
    if (files.length > 0) uploadMutation.mutate(files)
  }

  const uploadControl = canEdit && (
    <>
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept="image/*"
        className="hidden"
        onChange={handleFileChange}
      />
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={() => fileInputRef.current?.click()}
        disabled={uploadMutation.isPending}
      >
        {uploadMutation.isPending ? (
          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
        ) : (
          <Upload className="mr-1.5 h-3.5 w-3.5" />
        )}
        Adaugă poze
      </Button>
    </>
  )

  if (photos.length === 0) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-3 rounded-lg border border-dashed bg-muted/30">
        <div className="text-center">
          <Camera className="mx-auto h-8 w-8 text-muted-foreground" />
          <p className="mt-2 text-sm text-muted-foreground">Fără poze</p>
        </div>
        {uploadControl}
      </div>
    )
  }

  const go = (i: number) => setActive((i + photos.length) % photos.length)
  const openPreview = (i: number) => {
    setInitialPreview(i)
    setGridOpen(true)
  }

  return (
    <div className="w-full space-y-2" style={{ maxWidth: GALLERY_MAX_WIDTH }}>
      {/* Hero — the main viewing zone */}
      <div
        className="group relative aspect-[3/2] w-full cursor-zoom-in overflow-hidden rounded-xl bg-muted"
        onClick={() => openPreview(idx)}
      >
        <img
          src={mediaUrl(photos[idx].thumbnail_url || photos[idx].url)}
          alt={`Photo ${idx + 1}`}
          className="h-full w-full object-cover"
        />
        <div className="absolute left-3 top-3 rounded-full bg-black/60 px-2.5 py-1 text-xs font-medium tabular-nums text-white backdrop-blur">
          {idx + 1} / {photos.length}
        </div>
        <div className="absolute right-3 top-3 flex gap-2">
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setGridOpen(true) }}
            className="flex items-center gap-1.5 rounded-full bg-black/60 px-3 py-1.5 text-xs font-medium text-white backdrop-blur transition hover:bg-black/80"
          >
            <LayoutGrid className="h-3.5 w-3.5" /> Toate pozele
          </button>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); openPreview(idx) }}
            className="flex items-center gap-1.5 rounded-full bg-black/60 px-3 py-1.5 text-xs font-medium text-white backdrop-blur transition hover:bg-black/80"
          >
            <Maximize2 className="h-3.5 w-3.5" /> Ecran complet
          </button>
        </div>
        {photos.length > 1 && (
          <>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); go(idx - 1) }}
              className="absolute left-3 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-black/50 text-white opacity-0 backdrop-blur transition hover:bg-black/80 group-hover:opacity-100"
              aria-label="Poza anterioară"
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); go(idx + 1) }}
              className="absolute right-3 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-black/50 text-white opacity-0 backdrop-blur transition hover:bg-black/80 group-hover:opacity-100"
              aria-label="Poza următoare"
            >
              <ChevronRight className="h-5 w-5" />
            </button>
          </>
        )}
      </div>

      {/* Filmstrip */}
      {photos.length > 1 && (
        <div
          ref={strip.ref}
          {...strip.dragProps}
          className="flex cursor-grab select-none gap-2 overflow-x-auto overscroll-x-contain pb-1 active:cursor-grabbing"
          style={{ scrollbarWidth: 'thin' }}
        >
          {photos.map((p, i) => (
            <button
              type="button"
              key={p.id}
              data-i={i}
              onClick={() => { if (strip.didDrag()) return; go(i) }}
              className={`h-16 w-[96px] flex-none overflow-hidden rounded-md border-2 transition ${
                i === idx ? 'border-primary opacity-100' : 'border-transparent opacity-60 hover:opacity-100'
              }`}
            >
              <img
                src={mediaUrl(p.thumbnail_url || p.url)}
                alt={`Thumbnail ${i + 1}`}
                draggable={false}
                className="h-full w-full object-cover"
              />
            </button>
          ))}
        </div>
      )}

      {canEdit && <div className="flex items-center gap-2">{uploadControl}</div>}

      {gridOpen && (
        <PhotoGridOverlay
          recordId={recordId}
          photos={photos}
          setPhotos={setPhotos}
          canEdit={canEdit}
          initialPreview={initialPreview}
          onClose={() => { setGridOpen(false); setInitialPreview(null) }}
        />
      )}
    </div>
  )
}

// ── Sortable Photo Tile ─────────────────────────────────────
// One draggable tile in the "Toate pozele" grid. Tap the image to open the
// preview; drag the grip handle (top-right) to reorder; trash (bottom-right)
// deletes. Separate handles keep tap-to-open clean on touch devices.
function SortablePhotoTile({
  photo,
  index,
  canEdit,
  onSelect,
  onDelete,
}: {
  photo: BuybackPhoto
  index: number
  canEdit: boolean
  onSelect: (index: number) => void
  onDelete: (photoId: number) => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: photo.id,
  })
  const style = { transform: CSS.Transform.toString(transform), transition }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`group relative aspect-[3/2] overflow-hidden rounded-lg border bg-muted ${
        isDragging ? 'z-10 opacity-80 shadow-xl ring-2 ring-primary' : ''
      }`}
    >
      <button
        type="button"
        onClick={() => onSelect(index)}
        className="block h-full w-full"
        aria-label={`Deschide poza ${index + 1}`}
      >
        <img
          src={mediaUrl(photo.thumbnail_url || photo.url)}
          alt={`Photo ${index + 1}`}
          draggable={false}
          className="h-full w-full object-cover transition group-hover:scale-105"
        />
      </button>
      {/* Position badge — makes the first → last order visible (1 = cover) */}
      <div className="pointer-events-none absolute left-1.5 top-1.5 rounded-full bg-black/60 px-1.5 py-0.5 text-[11px] font-semibold tabular-nums text-white backdrop-blur">
        {index + 1}
      </div>
      {/* Drag handle */}
      <button
        type="button"
        {...attributes}
        {...listeners}
        aria-label="Trage pentru a reordona"
        className="absolute right-1.5 top-1.5 flex touch-none cursor-grab items-center justify-center rounded-md bg-black/60 p-1.5 text-white opacity-0 backdrop-blur transition hover:bg-black/80 focus:opacity-100 group-hover:opacity-100 active:cursor-grabbing"
      >
        <GripVertical className="h-4 w-4" />
      </button>
      {canEdit && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onDelete(photo.id) }}
          aria-label="Șterge poza"
          className="absolute right-1.5 bottom-1.5 flex items-center justify-center rounded-md bg-black/60 p-1.5 text-white opacity-0 backdrop-blur transition hover:bg-red-600/90 focus:opacity-100 group-hover:opacity-100"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      )}
    </div>
  )
}

// ── Photo Grid Overlay ("Toate pozele") ────────────────────
// Fullscreen photo grid. For editors it's drag-and-drop sortable: drop
// auto-saves the new order via reorderPhotos (optimistic, rolled back on
// error). Delete is per-photo (buyback has no bulk-delete endpoint).
function PhotoGridOverlay({
  recordId,
  photos,
  setPhotos,
  canEdit,
  initialPreview,
  onClose,
}: {
  recordId: number
  photos: BuybackPhoto[]
  setPhotos: React.Dispatch<React.SetStateAction<BuybackPhoto[]>>
  canEdit: boolean
  initialPreview: number | null
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['buyback-record', recordId] })
  // Clicking a photo opens a simple single-photo preview (not a full lightbox).
  const [preview, setPreview] = useState<number | null>(initialPreview)
  const previewRef = useRef<number | null>(null)
  useEffect(() => { previewRef.current = preview }, [preview])
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 180, tolerance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const reorderMutation = useMutation({
    mutationFn: (orderedIds: number[]) => buybackApi.reorderPhotos(recordId, orderedIds),
  })

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIndex = photos.findIndex((p) => p.id === active.id)
    const newIndex = photos.findIndex((p) => p.id === over.id)
    if (oldIndex < 0 || newIndex < 0) return
    const prev = photos
    const newPhotos = arrayMove(photos, oldIndex, newIndex)
    // Optimistic: reorder locally so the grid updates instantly.
    setPhotos(newPhotos)
    reorderMutation.mutate(newPhotos.map((p) => p.id), {
      onSuccess: () => invalidate(),
      onError: () => {
        // Roll back to the last known-good order and tell the user it didn't stick.
        setPhotos(prev)
        toast.error('Reordonarea pozelor a eșuat')
      },
    })
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // While the single-photo preview is open, keys drive it (not the grid).
      if (previewRef.current !== null) {
        if (e.key === 'Escape') setPreview(null)
        else if (e.key === 'ArrowRight') setPreview((i) => (i === null ? null : (i + 1) % photos.length))
        else if (e.key === 'ArrowLeft') setPreview((i) => (i === null ? null : (i - 1 + photos.length) % photos.length))
        return
      }
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose, photos.length])

  const deleteMutation = useMutation({
    mutationFn: (photoId: number) => buybackApi.deletePhoto(recordId, photoId),
    onSuccess: (_data, photoId) => {
      setPhotos((prevPhotos) => prevPhotos.filter((p) => p.id !== photoId))
      invalidate()
      toast.success('Poză ștearsă')
    },
    onError: () => toast.error('Ștergerea pozei a eșuat'),
  })

  const handleDelete = (photoId: number) => {
    if (!window.confirm('Ștergi această poză?')) return
    deleteMutation.mutate(photoId)
  }

  // Drag-to-reorder is available to editors whenever there's more than one photo.
  const sortable = canEdit && photos.length > 1

  if (photos.length === 0) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-background">
        <div className="text-center">
          <p className="text-sm text-muted-foreground">Nu mai sunt poze.</p>
          <Button className="mt-3" size="sm" variant="outline" onClick={onClose}>Închide</Button>
        </div>
      </div>
    )
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-background">
      <div className="sticky top-0 z-10 flex items-center justify-between gap-2 border-b bg-background/85 px-6 py-4 backdrop-blur">
        <div className="flex min-w-0 items-baseline gap-3">
          <h2 className="text-base font-semibold">Toate pozele · {photos.length}</h2>
          {sortable && (
            <span className="hidden truncate text-xs text-muted-foreground sm:inline">
              Trage de <GripVertical className="mx-0.5 inline h-3 w-3 align-text-bottom" /> pentru a reordona · prima poză = coperta
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md p-1.5 text-muted-foreground transition hover:bg-muted hover:text-foreground"
          aria-label="Închide"
        >
          <X className="h-5 w-5" />
        </button>
      </div>
      {sortable ? (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={photos.map((p) => p.id)} strategy={rectSortingStrategy}>
            <div className="mx-auto grid max-w-5xl grid-cols-2 gap-2 p-6 sm:grid-cols-3">
              {photos.map((p, i) => (
                <SortablePhotoTile
                  key={p.id}
                  photo={p}
                  index={i}
                  canEdit={canEdit}
                  onSelect={setPreview}
                  onDelete={handleDelete}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      ) : (
        <div className="mx-auto grid max-w-5xl grid-cols-2 gap-2 p-6 sm:grid-cols-3">
          {photos.map((p, i) => (
            <div key={p.id} className="group relative aspect-[3/2] overflow-hidden rounded-lg border bg-muted">
              <button
                type="button"
                onClick={() => setPreview(i)}
                className="block h-full w-full"
                aria-label={`Deschide poza ${i + 1}`}
              >
                <img
                  src={mediaUrl(p.thumbnail_url || p.url)}
                  alt={`Photo ${i + 1}`}
                  className="h-full w-full object-cover transition group-hover:scale-105"
                />
              </button>
              <div className="pointer-events-none absolute left-1.5 top-1.5 rounded-full bg-black/60 px-1.5 py-0.5 text-[11px] font-semibold tabular-nums text-white backdrop-blur">
                {i + 1}
              </div>
              {canEdit && (
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); handleDelete(p.id) }}
                  aria-label="Șterge poza"
                  className="absolute right-1.5 top-1.5 flex items-center justify-center rounded-md bg-black/60 p-1.5 text-white opacity-0 backdrop-blur transition hover:bg-red-600/90 focus:opacity-100 group-hover:opacity-100"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      {/* Single-photo preview — simple viewer with prev/next, NOT the full lightbox. */}
      {preview !== null && photos[preview] && (
        <div className="fixed inset-0 z-[60] flex flex-col bg-black/95" onClick={() => setPreview(null)}>
          <div className="flex items-center justify-between px-5 py-3" onClick={(e) => e.stopPropagation()}>
            <span className="text-sm tabular-nums text-white/70">{preview + 1} / {photos.length}</span>
            <div className="flex items-center gap-2">
              {canEdit && (
                <button
                  type="button"
                  onClick={() => handleDelete(photos[preview].id)}
                  className="rounded-md bg-white/10 p-2 text-white transition hover:bg-red-600/80"
                  aria-label="Șterge poza"
                >
                  <Trash2 className="h-5 w-5" />
                </button>
              )}
              <button
                type="button"
                onClick={() => setPreview(null)}
                className="rounded-md bg-white/10 p-2 text-white transition hover:bg-white/20"
                aria-label="Închide"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>
          <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden p-4" onClick={(e) => e.stopPropagation()}>
            {photos.length > 1 && (
              <button
                type="button"
                onClick={() => setPreview((i) => (i === null ? null : (i - 1 + photos.length) % photos.length))}
                className="absolute left-4 z-10 flex h-11 w-11 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/25"
                aria-label="Poza anterioară"
              >
                <ChevronLeft className="h-6 w-6" />
              </button>
            )}
            <img
              src={mediaUrl(photos[preview].url)}
              alt={`Photo ${preview + 1}`}
              className="max-h-full max-w-full object-contain"
            />
            {photos.length > 1 && (
              <button
                type="button"
                onClick={() => setPreview((i) => (i === null ? null : (i + 1) % photos.length))}
                className="absolute right-4 z-10 flex h-11 w-11 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/25"
                aria-label="Poza următoare"
              >
                <ChevronRight className="h-6 w-6" />
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
