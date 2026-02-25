import { Outlet } from 'react-router-dom'
import { Menu } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { api } from '@/api/client'
import { Sidebar } from './Sidebar'
import { AiAgentWidget, AiAgentPanel } from './AiAgentWidget'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { Toaster } from '@/components/ui/sonner'
import { cn } from '@/lib/utils'

export default function Layout() {
  const { user, isLoading } = useAuth()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem('sidebar-collapsed') === 'true' } catch { return false }
  })

  // Heartbeat: update last_seen every 60s so online-users widget works
  useEffect(() => {
    if (!user) return
    api.post('/api/heartbeat').catch(() => {})
    const id = setInterval(() => { api.post('/api/heartbeat').catch(() => {}) }, 60_000)
    return () => clearInterval(id)
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
        <header className="flex h-14 items-center border-b px-4 md:hidden">
          <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon">
                <Menu className="h-5 w-5" />
              </Button>
            </SheetTrigger>
          </Sheet>
          <span className="ml-2 text-lg font-semibold">JARVIS</span>
        </header>

        <main className="flex-1 overflow-auto p-6 pb-20">
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
