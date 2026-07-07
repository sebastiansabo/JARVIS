# Command Center — Profile Page Redesign

**Date:** 2026-06-24
**Status:** Approved

## Summary

Transform the Profile page from a traditional "My Profile" layout into a **Command Center** — a hub for quick actions and personal data. The main change is replacing the PageHeader + collapsible user info card with a bold `bg-primary text-primary-foreground` header bar containing identity info and action buttons. Profile details move into a modal.

## Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Header style | `bg-primary text-primary-foreground` | Theme-native, inverts correctly in dark mode, gives Command Center visual authority |
| Title | "Command center" with avatar + name + company inline | Clean, no ambiguity about which company |
| Profile details | Modal on avatar/name click | Declutters header, keeps details accessible |
| Quick actions | Buttons in header row | Check-in and New Ticket always one tap away |
| Tabs below | Unchanged | Invoices, HR, Vouchers stay as-is |

## Header Bar Layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│ [Avatar] Company Name           [Viewer] [Check In] [Ticket] [Pw] [Edit]│
│          Command center                                                  │
└──────────────────────────────────────────────────────────────────────────┘
```

### Left side
- **Avatar**: Initials circle, `bg-primary-foreground text-primary` (inverted from bar)
- **Company name**: `text-primary-foreground/70`, small text (from `user.company`)
- **"Command center"**: Bold title, `text-primary-foreground`

### Right side — action buttons
All buttons use `variant="outline"` with border/text colors adapted for primary background.

1. **Role badge** — e.g. "Viewer", outline style
2. **Check In / Check Out** — green/red accent, only shown if `status?.mapped` (user has BioStar). Uses existing `checkinApi.punch()` logic from `QuickCheckinCard`
3. **New Ticket** — opens existing `CreateTicketDialog` from `@/pages/Ticketing/CreateTicketDialog`
4. **Password** — opens existing `ChangePasswordDialog`
5. **Edit profile** — opens existing `EditProfileDialog`

### Mobile
On mobile (`useIsMobile()`), the action buttons wrap to a second row or collapse into an overflow dropdown menu to prevent crowding.

## Profile Details Modal

New `ProfileDetailsDialog` component. Triggered by clicking the avatar or user name in the header.

### Contents (extracted from current inline code)
- Info grid: Email, Phone, Department, Company, CNP, Birthdate, Position, Contract Start
- Signature section (view/edit/clear)
- Anniversary banners

### Props
```ts
interface ProfileDetailsDialogProps {
  open: boolean
  onOpenChange: (v: boolean) => void
  user: ProfileUser
  orgPaths: OrgTreeNode[]
  sincronDepartment?: string
}
```

## Component Changes

### Modified: `Profile/index.tsx`

1. **Remove** `PageHeader` usage
2. **Remove** the collapsible `Card` (lines ~135-201) containing user info
3. **Add** Command Center header bar (inline JSX, not a shared component)
4. **Add** `ProfileDetailsDialog` component (new function in same file)
5. **Add** state: `profileDetailsOpen`, `ticketOpen`
6. **Import** `CreateTicketDialog` from `@/pages/Ticketing/CreateTicketDialog`
7. **Move** check-in logic from `QuickCheckinCard` into header (reuse the same `useQuery`/`useMutation` pattern)
8. **Keep** `QuickCheckinCard` in PontajePanel as-is (shows detailed punch history)

### Unchanged
- `EditProfileDialog` — no changes
- `ChangePasswordDialog` — no changes
- `VouchersPanel` — no changes
- All tab panels — no changes
- `CreateTicketDialog` — no changes, just imported and used

## Files Touched

| File | Change |
|---|---|
| `jarvis/frontend/src/pages/Profile/index.tsx` | Header bar, ProfileDetailsDialog, remove old card/PageHeader |

## Out of Scope

- No backend changes
- No new API endpoints
- No changes to tab content panels
- No routing changes
