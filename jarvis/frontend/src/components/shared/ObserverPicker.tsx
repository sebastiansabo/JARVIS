import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Eye, X, Search } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { usersApi } from '@/api/users'
import { cn } from '@/lib/utils'

interface ObserverPickerProps {
  value: number[]
  onChange: (userIds: number[]) => void
  disabled?: boolean
  placeholder?: string
  label?: string
  className?: string
}

/**
 * Multi-select picker for invoice observers (view-only access).
 * Uses the global users list; selected users become observers.
 */
export function ObserverPicker({
  value,
  onChange,
  disabled = false,
  placeholder = 'Select observers…',
  label,
  className,
}: ObserverPickerProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')

  const { data: users = [], isLoading } = useQuery({
    queryKey: ['users-list'],
    queryFn: () => usersApi.getUsers(),
    staleTime: 5 * 60 * 1000,
  })

  const activeUsers = useMemo(
    () => users.filter((u) => u.is_active),
    [users],
  )

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return activeUsers
    return activeUsers.filter(
      (u) =>
        u.name.toLowerCase().includes(q) ||
        u.email.toLowerCase().includes(q),
    )
  }, [activeUsers, search])

  const selectedUsers = useMemo(
    () => activeUsers.filter((u) => value.includes(u.id)),
    [activeUsers, value],
  )

  const toggle = (userId: number) => {
    if (value.includes(userId)) {
      onChange(value.filter((id) => id !== userId))
    } else {
      onChange([...value, userId])
    }
  }

  const removeOne = (userId: number) => {
    onChange(value.filter((id) => id !== userId))
  }

  const clearAll = () => onChange([])

  return (
    <div className={cn('space-y-2', className)}>
      {label && (
        <div className="flex items-center gap-2 text-sm font-medium">
          <Eye className="h-4 w-4 text-muted-foreground" />
          {label}
        </div>
      )}

      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            className="w-full justify-start font-normal"
            disabled={disabled}
          >
            <Eye className="mr-2 h-4 w-4 text-muted-foreground" />
            {value.length === 0 ? (
              <span className="text-muted-foreground">{placeholder}</span>
            ) : (
              <span>
                {value.length} observer{value.length === 1 ? '' : 's'} selected
              </span>
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-80 p-0" align="start">
          <div className="p-2 border-b">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search users…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-8 h-9"
              />
            </div>
          </div>
          <div className="max-h-64 overflow-y-auto p-1">
            {isLoading ? (
              <div className="p-3 text-sm text-muted-foreground">Loading users…</div>
            ) : filtered.length === 0 ? (
              <div className="p-3 text-sm text-muted-foreground">No users found</div>
            ) : (
              filtered.map((u) => {
                const checked = value.includes(u.id)
                return (
                  <div
                    key={u.id}
                    className={cn(
                      'flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer hover:bg-accent',
                      checked && 'bg-accent/40',
                    )}
                    onClick={() => toggle(u.id)}
                  >
                    <Checkbox checked={checked} onCheckedChange={() => toggle(u.id)} />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">{u.name}</div>
                      <div className="text-xs text-muted-foreground truncate">{u.email}</div>
                    </div>
                  </div>
                )
              })
            )}
          </div>
          {value.length > 0 && (
            <div className="border-t p-2 flex justify-end">
              <Button type="button" variant="ghost" size="sm" onClick={clearAll}>
                Clear all
              </Button>
            </div>
          )}
        </PopoverContent>
      </Popover>

      {selectedUsers.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {selectedUsers.map((u) => (
            <Badge key={u.id} variant="secondary" className="gap-1 pr-1">
              <Eye className="h-3 w-3" />
              {u.name}
              {!disabled && (
                <button
                  type="button"
                  onClick={() => removeOne(u.id)}
                  className="ml-1 rounded-full hover:bg-background/40 p-0.5"
                  aria-label={`Remove ${u.name}`}
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </Badge>
          ))}
        </div>
      )}
    </div>
  )
}
