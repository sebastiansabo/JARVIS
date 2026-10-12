import { describe, it, expect } from 'vitest'
import { publishedGallerySrc } from '../Detail'
import type { VehiclePhoto } from '@/types/carpark'

const base = (over: Partial<VehiclePhoto>): VehiclePhoto =>
  ({ id: 1, url: 'orig.jpg', thumbnail_url: 'orig_thumb.jpg', sort_order: 0, ...over } as VehiclePhoto)

describe('publishedGallerySrc — published studio variant wins in the gallery', () => {
  it('uses the enhanced image when the variant is published', () => {
    const p = base({ enhanced_url: 'enh.jpg', enhanced_thumbnail_url: 'enh_thumb.jpg', enhanced_published: true })
    expect(publishedGallerySrc(p, false)).toContain('enh.jpg')
    expect(publishedGallerySrc(p, true)).toContain('enh_thumb.jpg')
  })

  it('falls back to the original when the variant exists but is NOT published', () => {
    const p = base({ enhanced_url: 'enh.jpg', enhanced_thumbnail_url: 'enh_thumb.jpg', enhanced_published: false })
    expect(publishedGallerySrc(p, false)).toContain('orig.jpg')
    expect(publishedGallerySrc(p, true)).toContain('orig_thumb.jpg')
  })

  it('falls back to the original when published is set but there is no enhanced variant', () => {
    const p = base({ enhanced_url: null, enhanced_published: true })
    expect(publishedGallerySrc(p, false)).toContain('orig.jpg')
  })

  it('full-size path ignores the thumbnail even when published', () => {
    const p = base({ enhanced_url: 'enh.jpg', enhanced_thumbnail_url: 'enh_thumb.jpg', enhanced_published: true })
    expect(publishedGallerySrc(p, false)).toContain('enh.jpg')
    expect(publishedGallerySrc(p, false)).not.toContain('enh_thumb.jpg')
  })
})
