import { describe, it, expect } from 'vitest'
import { publishedChannelCount, PUBLISH_CHANNEL_TOTAL } from './publishChannels'

describe('publishedChannelCount', () => {
  it('is 0 when live on no channel', () => {
    expect(publishedChannelCount({})).toBe(0)
    expect(publishedChannelCount({ autovit_published: false, shopify_published: false })).toBe(0)
  })

  it('counts Autovit alone', () => {
    expect(publishedChannelCount({ autovit_published: true })).toBe(1)
  })

  it('counts Autoworld alone', () => {
    expect(publishedChannelCount({ shopify_published: true })).toBe(1)
  })

  it('counts both channels', () => {
    expect(publishedChannelCount({ autovit_published: true, shopify_published: true })).toBe(2)
  })

  it('treats null/undefined flags as not published', () => {
    expect(publishedChannelCount({ autovit_published: null, shopify_published: undefined })).toBe(0)
  })

  it('never exceeds the channel total', () => {
    expect(publishedChannelCount({ autovit_published: true, shopify_published: true }))
      .toBeLessThanOrEqual(PUBLISH_CHANNEL_TOTAL)
  })
})
