/// <reference types="vite/client" />

// Build id stamped by vite.config.ts `define` at build time; compared against
// the polled /version.json to detect a stale tab. See src/lib/versionCheck.ts.
declare const __APP_BUILD__: string
