// Stale-tab detection: compare the build id baked into THIS bundle
// (`__APP_BUILD__`, stamped by vite.config.ts) against the one the server
// currently serves at /version.json. A difference means a newer frontend was
// deployed while this tab stayed open — the UpdateBanner then offers a reload.
//
// `__APP_BUILD__` is replaced at build time by Vite's `define`. The `typeof`
// guard keeps the module safe if it's ever evaluated without that replacement
// (an odd build/test env) — it falls back to 'dev' rather than throwing.
export const CURRENT_BUILD: string =
  typeof __APP_BUILD__ !== 'undefined' ? __APP_BUILD__ : 'dev'

// Pull the build id out of a parsed /version.json body. Returns null for
// anything that isn't a non-empty string build — a missing field, an HTML body
// (expired-session redirect), the dev route's {build: null}, or a non-object.
// Null means "can't tell" → never treated as a new version.
export function parseVersionPayload(body: unknown): string | null {
  if (typeof body !== 'object' || body === null) return null
  const build = (body as Record<string, unknown>).build
  return typeof build === 'string' && build !== '' ? build : null
}

// A reload is warranted only when we have a real current id, a real server id,
// and they differ. Any null/empty → false, so network blips and bad responses
// never surface the banner.
export function isNewerBuild(current: string, server: string | null): boolean {
  return current !== '' && server !== null && server !== '' && current !== server
}

// Fetch the server's current build id. Returns null on any failure (non-OK
// status, network error, non-JSON body) so the caller simply treats it as
// "no change" — never a false positive.
export async function fetchServerBuild(): Promise<string | null> {
  try {
    const res = await fetch('/version.json', { cache: 'no-store' })
    if (!res.ok) return null
    return parseVersionPayload(await res.json())
  } catch {
    return null
  }
}
