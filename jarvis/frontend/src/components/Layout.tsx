import { Outlet, Link } from 'react-router-dom'
import { Menu, MapPin, UserCircle, Bot } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { fetchColumnDefaults } from '@/lib/columnDefaults'
import { Sidebar } from './Sidebar'
import { ThemeToggle } from './ThemeToggle'
import { AiAgentWidget, AiAgentPanel } from './AiAgentWidget'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { Toaster } from '@/components/ui/sonner'
import { cn } from '@/lib/utils'

export default function Layout() {
  const { user, isLoading } = useAuth()
  const isViewer = user?.role_name === 'Viewer'
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(() => {
    try { const v = localStorage.getItem('sidebar-collapsed'); return v === null ? true : v === 'true' } catch { return true }
  })
  const effectiveCollapsed = isViewer || collapsed

  // Heartbeat: keep server warm while user is active
  useEffect(() => {
    if (!user) return

    let timer: ReturnType<typeof setTimeout>
    let interval = 30_000 // ~30s base — keep DO proxy connection alive
    const MAX_INTERVAL = 5 * 60_000

    const ping = () => {
      if (document.hidden) return // skip when tab not visible
      fetch('/api/heartbeat', { method: 'POST', credentials: 'same-origin' })
        .then(r => { if (r.ok) interval = 30_000 }) // reset on success
        .catch(() => { interval = Math.min(interval * 2, MAX_INTERVAL) }) // backoff on failure
        .finally(() => { timer = setTimeout(ping, interval) })
    }

    // ping immediately, then schedule
    ping()

    // when tab becomes visible, ping right away to wake server
    const onVisible = () => { if (!document.hidden) { clearTimeout(timer); ping() } }
    document.addEventListener('visibilitychange', onVisible)

    return () => { clearTimeout(timer); document.removeEventListener('visibilitychange', onVisible) }
  }, [user])

  // Fetch server column defaults (invalidates stale localStorage)
  useEffect(() => {
    if (user) fetchColumnDefaults()
  }, [user])

  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      const next = !prev
      try { localStorage.setItem('sidebar-collapsed', String(next)) } catch {}
      return next
    })
  }

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="space-y-3">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-4 w-32" />
        </div>
      </div>
    )
  }

  if (!user) {
    window.location.href = '/login'
    return null
  }

  return (
    <div className="flex h-screen bg-background">
      {/* Desktop sidebar */}
      <aside
        className={cn(
          'hidden border-r transition-[width] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)] md:block overflow-hidden',
          effectiveCollapsed ? 'w-16' : 'w-64',
        )}
      >
        <Sidebar collapsed={effectiveCollapsed} onToggle={isViewer ? undefined : toggleCollapsed} />
      </aside>

      {/* Mobile sidebar */}
      <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
        <SheetContent side="left" className="w-64 p-0">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <Sidebar />
        </SheetContent>
      </Sheet>

      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Mobile header — iOS 44pt nav bar */}
        <header className="flex h-[44px] items-center justify-between border-b px-2 md:hidden">
          <div className="flex items-center gap-1">
            {!isViewer ? (
              <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
                <SheetTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-[44px] w-[44px]">
                    <Menu className="h-[22px] w-[22px]" />
                  </Button>
                </SheetTrigger>
              </Sheet>
            ) : (
              <div className="h-[44px] w-[44px] flex items-center justify-center">
                <Bot className="h-[22px] w-[22px] text-primary translate-y-[1px]" />
              </div>
            )}
            <Link
              to="/app"
              className="text-[17px] font-semibold tracking-tight leading-none transition-opacity hover:opacity-80"
              title="Just AutoWorld's Real Very Intelligent System — crafted by Seba"
            >
              JARVIS
            </Link>
          </div>
          <div className="flex items-center">
            {isViewer && (
              <>
                <Link to="/app/mobile-checkin" className="h-[44px] w-[44px] flex items-center justify-center text-muted-foreground">
                  <MapPin className="h-[22px] w-[22px]" />
                </Link>
                <div className="h-[44px] w-[44px] flex items-center justify-center">
                  <ThemeToggle />
                </div>
              </>
            )}
            {/* My Account (logout lives inside the account page). */}
            <Link to="/app/profile" className="h-[44px] w-[44px] flex items-center justify-center text-muted-foreground">
              <UserCircle className="h-[22px] w-[22px]" />
            </Link>
          </div>
        </header>

        <main className="flex-1 overflow-auto p-4 pb-16 md:p-6 md:pb-6">
          <Outlet />
        </main>
      </div>

      {/* AI Agent panel — pushes main content when open */}
      <AiAgentPanel />

      {/* Floating trigger button (hidden on mobile) */}
      <div className="hidden md:block">
        <AiAgentWidget />
      </div>

      <Toaster />
    </div>
  )
}
