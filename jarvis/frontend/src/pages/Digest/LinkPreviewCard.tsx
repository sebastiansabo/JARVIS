import type { LinkPreview } from '@/types/digest'

interface Props {
  preview: LinkPreview
}

// WhatsApp-style unfurl card rendered below a post's content when the
// backend attached a link_preview snapshot. Text-only (no <img>) when the
// source page had no og:image. Semantic shadcn tokens (bg-muted, border,
// text-muted-foreground) keep it dark-mode aware without extra dark: classes.
export default function LinkPreviewCard({ preview }: Props) {
  return (
    <a
      href={preview.url}
      target="_blank"
      rel="noopener noreferrer"
      className="mt-1.5 block max-w-xs overflow-hidden rounded-lg border bg-background/60 hover:bg-accent/40 transition-colors"
    >
      {preview.image && (
        <img
          src={preview.image}
          alt={preview.title || 'link preview'}
          className="max-h-40 w-full object-cover"
        />
      )}
      <div className="px-2.5 py-2 space-y-0.5">
        {preview.title && (
          <p className="text-xs font-semibold line-clamp-2">{preview.title}</p>
        )}
        {preview.description && (
          <p className="text-[11px] text-muted-foreground line-clamp-2">{preview.description}</p>
        )}
        {preview.site_name && (
          <p className="text-[10px] text-muted-foreground/70 truncate">{preview.site_name}</p>
        )}
      </div>
    </a>
  )
}
