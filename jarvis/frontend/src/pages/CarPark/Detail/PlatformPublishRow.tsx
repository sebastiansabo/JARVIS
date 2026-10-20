import type { ReactNode } from 'react'
import { ExternalLink, MoreHorizontal, Power, RefreshCw, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { FreshnessBadge, formatListingTime, type Freshness } from './ListingFreshness'
import { publishPrimaryAction } from './publishState'

// Solid background colors for the primary action — tone 'muted' deliberately
// has none here; it rides the Button's own `ghost` variant styling instead,
// so an up-to-date/draft listing stays visually calm (no colored CTA).
const TONE_CLASS: Record<'blue' | 'amber', string> = {
  blue: 'bg-blue-600 text-white hover:bg-blue-700',
  amber: 'bg-amber-600 text-white hover:bg-amber-700',
}

export type PublishRowProps = {
  logo: ReactNode
  name: string
  subtitle?: string
  freshness: Freshness
  lastSync?: string | null
  externalUrl?: string | null
  externalLinkLabel: string // "Vezi anunțul" | "Vezi în magazin"
  autoEnabled: boolean
  busy: boolean
  canEdit: boolean
  onPrimary: () => void
  onVerify: () => void
  onToggleAuto: (on: boolean) => void
  onDeactivate: () => void
  onDelete?: () => void // present => shows "Șterge definitiv"
}

// Platform-agnostic publish row: one state badge, one state-driven primary
// action, everything else (verify / auto-update / deactivate / delete) tucked
// into the "⋯" menu. Driven entirely by props so Autovit/Autoworld/Shopify
// adapters can all render the same row with different data + handlers.
export function PlatformPublishRow({
  logo,
  name,
  subtitle,
  freshness,
  lastSync,
  externalUrl,
  externalLinkLabel,
  autoEnabled,
  busy,
  canEdit,
  onPrimary,
  onVerify,
  onToggleAuto,
  onDeactivate,
  onDelete,
}: PublishRowProps) {
  const primary = publishPrimaryAction(freshness)

  const handleDelete = () => {
    if (window.confirm(`Ștergi definitiv anunțul "${name}"? Această acțiune nu poate fi anulată.`)) {
      onDelete?.()
    }
  }

  return (
    <div className="flex items-center justify-between gap-3 py-2">
      <div className="flex min-w-0 items-center gap-3">
        <div className="shrink-0">{logo}</div>
        <div className="min-w-0">
          <div className="truncate text-sm font-medium">{name}</div>
          {subtitle && <div className="truncate text-xs text-muted-foreground">{subtitle}</div>}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex flex-col items-end gap-0.5">
          <div className="flex items-center gap-1.5">
            <FreshnessBadge freshness={freshness} />
            <Badge
              variant="secondary"
              className={
                autoEnabled
                  ? 'font-normal bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                  : 'font-normal text-muted-foreground'
              }
            >
              Auto
            </Badge>
          </div>
          {lastSync && (
            <span className="text-[11px] text-muted-foreground">
              Ultima sincronizare: {formatListingTime(lastSync)}
            </span>
          )}
          {freshness === 'stale' && autoEnabled && (
            <span className="text-[11px] text-muted-foreground">se actualizează automat</span>
          )}
          {externalUrl && (
            <a
              href={externalUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <ExternalLink className="h-3 w-3" />
              {externalLinkLabel}
            </a>
          )}
        </div>

        {canEdit && primary && (
          <Button
            size="sm"
            variant={primary.variant}
            disabled={busy}
            onClick={onPrimary}
            className={primary.tone === 'muted' ? 'text-muted-foreground' : TONE_CLASS[primary.tone]}
          >
            {busy && <RefreshCw className="h-3.5 w-3.5 animate-spin" />}
            {primary.label}
          </Button>
        )}

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="icon-sm" variant="ghost" aria-label="Mai multe opțiuni">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuItem onSelect={onVerify}>
              <RefreshCw className="h-4 w-4" />
              Verifică status acum
            </DropdownMenuItem>

            {/* Not a DropdownMenuItem: it hosts an interactive Switch, and
                Item's built-in select/close behavior would fight the click. */}
            <div className="flex items-center justify-between gap-2 rounded-sm px-2 py-1.5 text-sm">
              <span>Auto-actualizare</span>
              <Switch
                checked={autoEnabled}
                onCheckedChange={onToggleAuto}
                aria-label="Auto-actualizare"
              />
            </div>

            {/* Nothing to deactivate on an unpublished listing — hiding this also
                stops an adapter from firing a deactivate call with no live ad. */}
            {canEdit && freshness !== 'not_published' && (
              <DropdownMenuItem onSelect={onDeactivate}>
                <Power className="h-4 w-4" />
                Dezactivează anunțul
              </DropdownMenuItem>
            )}

            {canEdit && onDelete && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive" onSelect={handleDelete}>
                  <Trash2 className="h-4 w-4" />
                  Șterge definitiv
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  )
}

export default PlatformPublishRow
