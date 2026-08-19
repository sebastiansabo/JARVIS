/** Resolve a stored notification `link` to an in-app SPA route.
 *
 *  The approval "new request" notification carries the backend deep-link
 *  `/go/approval/<id>` (used for full-page navigation from email/push, where the
 *  server redirects). The in-app bell navigates with React Router, which has no
 *  `/go/*` route — so map it to the leave-approvals view, since form-submission
 *  approvals are Bilet de Învoire permits. Other links pass through unchanged. */
export function resolveNotificationRoute(link: string | null | undefined): string | null {
  if (!link) return null
  if (/^\/go\/approval\/\d+/.test(link)) return '/app/hub?module=hr&hrtab=leave-approvals'
  return link
}
