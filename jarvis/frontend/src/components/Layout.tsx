import { Outlet } from 'react-router-dom'
import { Menu } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { fetchColumnDefaults } from '@/lib/columnDefaults'
import { Sidebar } from './Sidebar'
import { AiAgentWidget, AiAgentPanel } from './AiAgentWidget'
import { NotificationBell } from './NotificationBell'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { Toaster } from '@/components/ui/sonner'
import { cn } from '@/lib/utils'

export default function Layout() {
  const { user, isLoading } = useAuth()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(() => {
    try { const v = localStorage.getItem('sidebar-collapsed'); return v === null ? true : v === 'true' } catch { return true }
  })

  // Heartbeat: keep server warm while user is active
  useEffect(() => {
    if (!user) return

    let timer: ReturnType<typeof setTimeout>
    let interval = 55_000 // ~55s base
    const MAX_INTERVAL = 5 * 60_000

    const ping = () => {
      if (document.hidden) return // skip when tab not visible
      fetch('/api/heartbeat', { method: 'POST', credentials: 'same-origin' })
        .then(r => { if (r.ok) interval = 55_000 }) // reset on success
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
          'hidden border-r transition-[width] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)] md:block',
          collapsed ? 'w-16' : 'w-64',
        )}
      >
        <Sidebar collapsed={collapsed} onToggle={toggleCollapsed} />
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
        {/* Mobile header */}
        <header className="flex h-14 items-center justify-between border-b px-4 md:hidden">
          <div className="flex items-center">
            <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
              <SheetTrigger asChild>
                <Button variant="ghost" size="icon">
                  <Menu className="h-5 w-5" />
                </Button>
              </SheetTrigger>
            </Sheet>
            <span className="ml-2 text-lg font-semibold">JARVIS</span>
          </div>
          <NotificationBell />
        </header>

        <main className="flex-1 overflow-auto p-4 pb-16 md:p-6 md:pb-6">
          <Outlet />
        </main>
      </div>

      {/* AI Agent panel — pushes main content when open */}
      <AiAgentPanel />

      {/* Floating trigger button (only visible when panel is closed) */}
      <AiAgentWidget />

      <Toaster />
    </div>
  )
}
