import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Filter, Search } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { tagsApi } from '@/api/tags'
import type { Tag } from '@/types/tags'

interface TagFilterProps {
  selectedTagIds: number[]
  onChange: (ids: number[]) => void
}

export function TagFilter({ selectedTagIds, onChange }: TagFilterProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')

  const { data: allTags = [] } = useQuery({
    queryKey: ['tags'],
    queryFn: () => tagsApi.getTags(),
    enabled: open,
    staleTime: 30_000,
  })

  const filtered = useMemo(() => {
    if (!search) return allTags
    const q = search.toLowerCase()
    return allTags.filter(
      (t) => t.name.toLowerCase().includes(q) || t.group_name?.toLowerCase().includes(q),
    )
  }, [allTags, search])

  const grouped = useMemo(() => {
    const map = new Map<string, Tag[]>()
    for (const tag of filtered) {
      const group = tag.group_name ?? 'Other'
      if (!map.has(group)) map.set(group, [])
      map.get(group)!.push(tag)
    }
    return map
  }, [filtered])

  const toggle = (tagId: number) => {
    if (selectedTagIds.includes(tagId)) {
      onChange(selectedTagIds.filter((id) => id !== tagId))
    } else {
      onChange([...selectedTagIds, tagId])
    }
  }

  const activeCount = selectedTagIds.length

  return (
    <Popover open={open} onOpenChange={(v) => { setOpen(v); if (!v) setSearch('') }}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-8 gap-1.5">
          <Filter className="h-3.5 w-3.5" />
          Tags
          {activeCount > 0 && (
            <span className="ml-0.5 rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-medium leading-none text-primary-foreground">
              {activeCount}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-56 p-0">
        <div className="flex items-center gap-1.5 border-b px-2 py-1.5">
          <Search className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search tags..."
            className="h-7 border-none bg-transparent px-0 text-sm shadow-none focus-visible:ring-0"
          />
        </div>
        <div className="max-h-60 overflow-y-auto p-1">
          {allTags.length === 0 ? (
            <div className="py-4 text-center text-xs text-muted-foreground">No tags yet</div>
          ) : filtered.length === 0 ? (
            <div className="py-4 text-center text-xs text-muted-foreground">No matching tags</div>
          ) : (
            Array.from(grouped.entries()).map(([group, tags]) => (
              <div key={group}>
                <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {group}
                </p>
                {tags.map((tag) => {
                  const isActive = selectedTagIds.includes(tag.id)
                  return (
                    <button
                      key={tag.id}
                      onClick={() => toggle(tag.id)}
                      className="flex w-full items-center gap-2 rounded px-2 py-1 text-sm hover:bg-accent/50"
                    >
                      <Checkbox checked={isActive} className="pointer-events-none" tabIndex={-1} />
                      <span
                        className="h-2.5 w-2.5 rounded-full shrink-0"
                        style={{ backgroundColor: tag.color ?? '#6c757d' }}
                      />
                      <span className="truncate">{tag.name}</span>
                    </button>
                  )
                })}
              </div>
            ))
          )}
        </div>
        {activeCount > 0 && (
          <div className="border-t p-1">
            <button
              onClick={() => onChange([])}
              className="w-full rounded px-2 py-1 text-xs text-muted-foreground hover:bg-accent/50"
            >
              Clear all filters
            </button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  )
}
