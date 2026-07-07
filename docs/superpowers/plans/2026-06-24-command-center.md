# Command Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the Profile page header into a Command Center with quick-action buttons and a profile details modal.

**Architecture:** Replace the `PageHeader` + collapsible user info card with a `bg-primary text-primary-foreground` header bar. Extract the inline user details into a new `ProfileDetailsDialog`. Add check-in and new-ticket quick actions to the header. All tab content below remains untouched.

**Tech Stack:** React, TypeScript, Tailwind CSS, shadcn/ui, React Query, lucide-react

## Global Constraints

- Single file modification: `jarvis/frontend/src/pages/Profile/index.tsx`
- No backend changes, no new API endpoints
- Reuse existing `CreateTicketDialog`, `EditProfileDialog`, `ChangePasswordDialog`
- Reuse existing `checkinApi` and `profileApi`
- Must work in both light and dark mode using theme tokens only
- Mobile responsive

---

### Task 1: Add ProfileDetailsDialog and wire new state

**Files:**
- Modify: `jarvis/frontend/src/pages/Profile/index.tsx:100-274` (Profile component + top-level return)

**Interfaces:**
- Consumes: `user` from `profileApi.getSummary()`, `orgPaths` from `usersApi.getUserOrgPath()`, `summary?.sincron?.department`
- Produces: `ProfileDetailsDialog` component (used in Task 2's header bar)

- [ ] **Step 1: Add the ProfileDetailsDialog function**

Add this new component after the existing `SignatureSection` function (after line ~413) and before the `EditProfileDialog` function:

```tsx
// ─── Profile Details Dialog ──────────────────────────────────────

function ProfileDetailsDialog({
  open,
  onOpenChange,
  user,
  orgPaths,
  sincronDepartment,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  user: NonNullable<ReturnType<typeof profileApi.getSummary> extends Promise<infer T> ? T : never>['user']
  orgPaths: any[]
  sincronDepartment?: string
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">
              {user?.name?.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase() || '?'}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span>{user?.name}</span>
                {user?.role && <StatusBadge status={user.role} />}
              </div>
              {user?.position && <p className="text-sm font-normal text-muted-foreground">{user.position}</p>}
            </div>
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 pt-2">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-3 text-sm">
            <InfoField icon={Mail} label="Email" value={user?.email} />
            <InfoField icon={Phone} label="Phone" value={user?.phone} />
            <InfoField icon={Building2} label="Department" value={(() => { const depts = orgPaths.map((o: any) => o.sincron_department || o.department).filter(Boolean); return depts.length > 0 ? depts : (sincronDepartment || user?.department); })()} />
            <InfoField icon={Shield} label="Company" value={(() => { const comps = [...new Set(orgPaths.map((o: any) => o.company).filter(Boolean))]; return comps.length > 0 ? comps : user?.company; })()} />
            <InfoField icon={Hash} label="CNP" value={user?.cnp} />
            <InfoField icon={Calendar} label="Birthdate" value={user?.birthdate ? new Date(user.birthdate).toLocaleDateString('ro-RO') : null} />
            <InfoField icon={Briefcase} label="Position" value={user?.position} />
            <InfoField icon={Calendar} label="Contract Start" value={user?.contract_work_date ? new Date(user.contract_work_date).toLocaleDateString('ro-RO') : null} />
          </div>
          <SignatureSection />
          <AnniversaryBanners birthdate={user?.birthdate} contractDate={user?.contract_work_date} name={user?.name ?? ''} />
        </div>
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 2: Add new state variables in the Profile component**

In `Profile()` (around line 107-109), replace:

```tsx
const [detailsOpen, setDetailsOpen] = useState(false)
```

with:

```tsx
const [profileDetailsOpen, setProfileDetailsOpen] = useState(false)
const [ticketOpen, setTicketOpen] = useState(false)
```

- [ ] **Step 3: Add the CreateTicketDialog import**

Add to the imports at the top of the file (around line 71, after the other lazy/page imports):

```tsx
const CreateTicketDialog = lazy(() => import('@/pages/Ticketing/CreateTicketDialog'))
```

- [ ] **Step 4: Add the Ticket icon import**

The `Ticket` icon is already imported (line 38). Also add `MoreHorizontal` for the mobile overflow menu:

```tsx
import { ..., MoreHorizontal } from 'lucide-react'
```

Also add `DropdownMenu` imports for mobile overflow:

```tsx
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
```

- [ ] **Step 5: Verify the file saves and the dev server doesn't crash**

Run: `cd /Users/sebastiansabo/Documents/Git/jarvis/jarvis/frontend && npx tsc --noEmit --pretty 2>&1 | head -20`

Expected: No new type errors related to ProfileDetailsDialog or state changes.

- [ ] **Step 6: Commit**

```bash
git add jarvis/frontend/src/pages/Profile/index.tsx
git commit -m "feat(profile): add ProfileDetailsDialog and new state for command center"
```

---

### Task 2: Replace header with Command Center bar

**Files:**
- Modify: `jarvis/frontend/src/pages/Profile/index.tsx:127-214` (the return JSX of Profile component)

**Interfaces:**
- Consumes: `ProfileDetailsDialog` from Task 1, `CreateTicketDialog` (lazy import), `checkinApi` queries, all existing state
- Produces: The complete Command Center header bar replacing PageHeader + user info card

- [ ] **Step 1: Add check-in query and mutation inside Profile()**

Add after the `orgPaths` query (around line 125), before the `return`:

```tsx
// Check-in status for header quick action
const { data: checkinStatus } = useQuery({
  queryKey: ['checkin', 'status'],
  queryFn: async () => {
    const res = await checkinApi.getStatus()
    return (res as any).data ?? res
  },
  refetchInterval: 60_000,
})

const punchMut = useMutation({
  mutationFn: async () => {
    const pos = await new Promise<GeolocationPosition | null>((resolve) => {
      if (!navigator.geolocation) return resolve(null)
      navigator.geolocation.getCurrentPosition(resolve, () => resolve(null), {
        enableHighAccuracy: true, timeout: 5000, maximumAge: 0,
      })
    })
    const payload: { lat?: number; lng?: number; direction?: string } = {}
    if (pos) { payload.lat = pos.coords.latitude; payload.lng = pos.coords.longitude }
    payload.direction = checkinStatus?.next_direction ?? 'IN'
    const res = await checkinApi.punch(payload)
    return (res as any).data ?? res
  },
  onSuccess: (res) => {
    if (res.success) {
      queryClient.invalidateQueries({ queryKey: ['checkin', 'status'] })
      queryClient.invalidateQueries({ queryKey: ['profile', 'pontaje'] })
      toast.success(`${res.direction} at ${res.time} — ${res.location}`)
    } else {
      toast.error(res.error || 'Punch failed')
    }
  },
  onError: () => toast.error('Punch failed — try the Check In page'),
})

const checkinDir = checkinStatus?.next_direction ?? 'IN'
const isCheckedIn = checkinDir !== 'IN'
```

- [ ] **Step 2: Replace the PageHeader and user info Card with the Command Center header**

Replace everything from `<PageHeader` (line 129) through the closing of `<ChangePasswordDialog>` (line 214) with:

```tsx
{/* Command Center Header */}
<div className="rounded-lg bg-primary text-primary-foreground p-4">
  <div className="flex items-center gap-4">
    {/* Left: Avatar + Identity */}
    <button
      type="button"
      className="flex items-center gap-3 min-w-0 hover:opacity-80 transition-opacity"
      onClick={() => setProfileDetailsOpen(true)}
    >
      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary-foreground text-primary text-sm font-bold">
        {user?.name?.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase() || '?'}
      </div>
      <div className="min-w-0 text-left">
        <p className="text-xs text-primary-foreground/70 truncate">
          {user?.company || 'Loading...'}
        </p>
        <h1 className="text-lg font-bold leading-tight">Command center</h1>
      </div>
    </button>

    {/* Right: Actions */}
    <div className="ml-auto flex items-center gap-2">
      {user?.role && (
        <Badge variant="outline" className="border-primary-foreground/30 text-primary-foreground text-xs">
          {user.role}
        </Badge>
      )}

      {/* Desktop action buttons */}
      {!isMobile && (
        <>
          {checkinStatus?.mapped && (
            <Button
              size="sm"
              className={cn(
                'shrink-0 font-semibold text-white',
                isCheckedIn
                  ? 'bg-red-600 hover:bg-red-700'
                  : 'bg-green-600 hover:bg-green-700',
              )}
              onClick={() => punchMut.mutate()}
              disabled={punchMut.isPending}
            >
              {isCheckedIn ? <LogOut className="h-3.5 w-3.5 mr-1.5" /> : <LogIn className="h-3.5 w-3.5 mr-1.5" />}
              {punchMut.isPending ? '...' : isCheckedIn ? 'Check Out' : 'Check In'}
            </Button>
          )}
          <Button
            size="sm"
            variant="outline"
            className="border-primary-foreground/30 text-primary-foreground hover:bg-primary-foreground/10"
            onClick={() => setTicketOpen(true)}
          >
            <Ticket className="h-3.5 w-3.5 mr-1.5" />
            Ticket
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="border-primary-foreground/30 text-primary-foreground hover:bg-primary-foreground/10"
            onClick={() => setPasswordOpen(true)}
          >
            <Key className="h-3.5 w-3.5 mr-1.5" />
            Password
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="border-primary-foreground/30 text-primary-foreground hover:bg-primary-foreground/10"
            onClick={() => setEditOpen(true)}
          >
            <Pencil className="h-3.5 w-3.5 mr-1.5" />
            Edit profile
          </Button>
        </>
      )}

      {/* Mobile: overflow menu */}
      {isMobile && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="sm" variant="outline" className="border-primary-foreground/30 text-primary-foreground hover:bg-primary-foreground/10">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {checkinStatus?.mapped && (
              <DropdownMenuItem onClick={() => punchMut.mutate()} disabled={punchMut.isPending}>
                {isCheckedIn ? <LogOut className="h-4 w-4 mr-2" /> : <LogIn className="h-4 w-4 mr-2" />}
                {isCheckedIn ? 'Check Out' : 'Check In'}
              </DropdownMenuItem>
            )}
            <DropdownMenuItem onClick={() => setTicketOpen(true)}>
              <Ticket className="h-4 w-4 mr-2" />
              New Ticket
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setPasswordOpen(true)}>
              <Key className="h-4 w-4 mr-2" />
              Password
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setEditOpen(true)}>
              <Pencil className="h-4 w-4 mr-2" />
              Edit profile
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  </div>
</div>

{/* Dialogs */}
{user && (
  <ProfileDetailsDialog
    open={profileDetailsOpen}
    onOpenChange={setProfileDetailsOpen}
    user={user}
    orgPaths={orgPaths}
    sincronDepartment={summary?.sincron?.department}
  />
)}
{user && (
  <EditProfileDialog
    open={editOpen}
    onOpenChange={setEditOpen}
    user={user}
    onSaved={() => queryClient.invalidateQueries({ queryKey: ['profile', 'summary'] })}
  />
)}
<ChangePasswordDialog open={passwordOpen} onOpenChange={setPasswordOpen} />
<Suspense fallback={null}>
  <CreateTicketDialog open={ticketOpen} onOpenChange={setTicketOpen} />
</Suspense>
```

- [ ] **Step 3: Remove unused imports**

Remove `PageHeader` import (line 52) since it's no longer used:

```tsx
// DELETE this line:
import { PageHeader } from '@/components/shared/PageHeader'
```

Also remove `SlidersHorizontal` and `ChevronUp` from lucide imports if no longer referenced elsewhere in the file (check first — `ChevronUp` was used for the collapsible card chevron which is now removed).

- [ ] **Step 4: Verify the build compiles**

Run: `cd /Users/sebastiansabo/Documents/Git/jarvis/jarvis/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`

Expected: No new type errors.

- [ ] **Step 5: Test locally on localhost**

Open `http://localhost:5173/app/profile` (or whatever the dev server port is).

Verify:
- Dark header bar appears with company name + "Command center" title
- Clicking avatar/name opens the profile details modal with all info fields + signature
- "Check In" button shows (if user has BioStar mapping) and works
- "Ticket" button opens the Create Ticket dialog
- "Password" button opens the Change Password dialog
- "Edit profile" button opens the Edit Profile dialog
- Role badge shows correctly
- Tabs below (Invoices, HR, Vouchers) still work
- On mobile viewport: buttons collapse into `...` overflow menu

- [ ] **Step 6: Commit**

```bash
git add jarvis/frontend/src/pages/Profile/index.tsx
git commit -m "feat(profile): replace header with Command Center bar + quick actions"
```

---

### Task 3: Clean up — remove dead code from old collapsible card

**Files:**
- Modify: `jarvis/frontend/src/pages/Profile/index.tsx`

**Interfaces:**
- Consumes: Nothing new
- Produces: Cleaner file with no dead code

- [ ] **Step 1: Check if `detailsOpen` state is still referenced**

Search the file for `detailsOpen`. It was used for the collapsible card. If Task 2 properly replaced it with `profileDetailsOpen`, remove the old `detailsOpen` state declaration if it's still present.

- [ ] **Step 2: Check if `ChevronUp`, `ChevronDown` are still used elsewhere**

`ChevronDown` may be used in other panels (check `PontajePanel`, `TeamPontajePanel`). Only remove from imports if truly unused. `ChevronUp` was only used in the collapsible card — likely safe to remove.

- [ ] **Step 3: Verify no unused imports remain**

Run: `cd /Users/sebastiansabo/Documents/Git/jarvis/jarvis/frontend && npx tsc --noEmit --pretty 2>&1 | head -20`

Expected: Clean compile, no errors.

- [ ] **Step 4: Final visual check on localhost**

Open `http://localhost:5173/app/profile`. Walk through all tabs and dialogs. Everything should work identically to before except the header is now the Command Center bar.

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/pages/Profile/index.tsx
git commit -m "refactor(profile): remove dead code from old collapsible card"
```
