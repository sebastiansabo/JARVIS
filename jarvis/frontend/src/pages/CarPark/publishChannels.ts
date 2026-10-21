// How many marketplace channels a vehicle is live on right now (Autovit +
// Autoworld), out of PUBLISH_CHANNEL_TOTAL. Drives the "(n/2)" suffix on the
// status badge, read from the same autovit_published/shopify_published flags
// that render the list's "Publicat" icons so the two always agree.

export const PUBLISH_CHANNEL_TOTAL = 2

export function publishedChannelCount(
  v: { autovit_published?: boolean | null; shopify_published?: boolean | null },
): number {
  return (v.autovit_published ? 1 : 0) + (v.shopify_published ? 1 : 0)
}
