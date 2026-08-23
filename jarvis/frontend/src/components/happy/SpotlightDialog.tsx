import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Clock, Megaphone } from 'lucide-react'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { cn } from '@/lib/utils'
import type { HappySurfaceItem } from '@/types/happy'

const remarkPlugins = [remarkGfm]

/** Absolute deadline formatted for a Romanian audience, e.g. "25 august, 21:00". */
function formatDeadline(iso: string): string {
  return new Date(iso).toLocaleString('ro-RO', {
    day: 'numeric',
    month: 'long',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** Coarse relative deadline + whether it falls inside the <24h urgency window. */
function relativeDeadline(iso: string): { text: string; urgent: boolean } {
  const diffMs = new Date(iso).getTime() - Date.now()
  const urgent = diffMs < 24 * 3_600_000
  const hours = Math.round(Math.abs(diffMs) / 3_600_000)
  if (hours < 24) {
    return { text: diffMs >= 0 ? `în ${hours} h` : `acum ${hours} h`, urgent }
  }
  const days = Math.round(hours / 24)
  const unit = days === 1 ? 'zi' : 'zile'
  return { text: diffMs >= 0 ? `în ${days} ${unit}` : `acum ${days} ${unit}`, urgent }
}

type TitleWrapper = React.ComponentType<{ className?: string; children?: React.ReactNode }>

interface SpotlightContentProps {
  item: HappySurfaceItem
  TitleWrapper: TitleWrapper
  onCta: () => void
  onAck: () => void
  onSnooze: () => void
}

function SpotlightContent({ item, TitleWrapper, onCta, onAck, onSnooze }: SpotlightContentProps) {
  const [ackChecked, setAckChecked] = useState(false)
  const isClickAck = item.ack?.mode === 'click'
  const showSnooze = item.dismissible && item.snooze_remaining > 0
  const deadline = item.ack?.deadline_at ? relativeDeadline(item.ack.deadline_at) : null

  return (
    <>
      {item.media && (
        <img
          src={item.media.url}
          alt={item.media.alt}
          className="aspect-[3/1] w-full rounded-t-2xl object-cover"
        />
      )}

      <div className="space-y-3 px-6 py-5">
        {/* Kicker + tier chip */}
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <Megaphone className="h-3.5 w-3.5" />
            {item.kicker}
          </span>
          {item.tier === 'critical' && <Badge variant="destructive">Obligatoriu</Badge>}
          {item.tier === 'important' && <Badge variant="secondary">Important</Badge>}
        </div>

        {/* Title (also the accessible dialog/sheet title) */}
        <TitleWrapper className="text-lg font-semibold leading-snug">{item.title}</TitleWrapper>

        {/* Body — markdown */}
        {item.body_md && (
          <div className="prose prose-sm dark:prose-invert max-w-none text-sm text-muted-foreground">
            <ReactMarkdown remarkPlugins={remarkPlugins}>{item.body_md}</ReactMarkdown>
          </div>
        )}

        {/* Deadline strip */}
        {item.ack?.deadline_at && deadline && (
          <div
            className={cn(
              'flex items-center gap-1.5 text-xs',
              deadline.urgent ? 'text-destructive' : 'text-muted-foreground',
            )}
          >
            <Clock className="h-3.5 w-3.5" />
            <span>
              Termen: {formatDeadline(item.ack.deadline_at)} ({deadline.text})
            </span>
          </div>
        )}

        {/* Ack gate (click mode) */}
        {isClickAck && (
          <label className="flex items-start gap-2 pt-1 text-sm">
            <Checkbox
              checked={ackChecked}
              onCheckedChange={(v) => setAckChecked(v === true)}
              className="mt-0.5"
            />
            <span>Am citit și am înțeles</span>
          </label>
        )}

        {/* Actions */}
        <div className="flex flex-col-reverse gap-2 pt-1 sm:flex-row sm:justify-end">
          {showSnooze && (
            <Button variant="ghost" onClick={onSnooze}>
              Mai târziu
            </Button>
          )}
          {isClickAck ? (
            <Button disabled={!ackChecked} onClick={onAck}>
              {item.cta?.label ?? 'Confirmă'}
            </Button>
          ) : (
            <Button onClick={onCta}>{item.cta?.label ?? 'Am înțeles'}</Button>
          )}
        </div>
      </div>
    </>
  )
}

export interface SpotlightDialogProps {
  item: HappySurfaceItem
  open: boolean
  onOpenChange: (open: boolean) => void
  onCta: () => void
  onAck: () => void
  onSnooze: () => void
}

/**
 * The Spotlight interstitial. Desktop/tablet = centered shadcn Dialog;
 * mobile = bottom Sheet. Content-styled, no gradient, no animation beyond the
 * component defaults. See HAPPY_MODULE_SPEC.md §5.3.
 */
export function SpotlightDialog({ item, open, onOpenChange, onCta, onAck, onSnooze }: SpotlightDialogProps) {
  const isMobile = useIsMobile()
  const isCritical = item.tier === 'critical'
  const blockClose = !item.dismissible

  const content = (Wrapper: TitleWrapper) => (
    <SpotlightContent
      item={item}
      TitleWrapper={Wrapper}
      onCta={onCta}
      onAck={onAck}
      onSnooze={onSnooze}
    />
  )

  if (isMobile) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent
          side="bottom"
          showCloseButton={item.dismissible}
          role={isCritical ? 'alertdialog' : 'dialog'}
          className="max-h-[88vh] gap-0 overflow-y-auto rounded-t-3xl bg-card p-0 pb-[env(safe-area-inset-bottom)]"
          onEscapeKeyDown={(e) => { if (blockClose) e.preventDefault() }}
          onInteractOutside={(e) => { if (blockClose) e.preventDefault() }}
        >
          {content(SheetTitle)}
        </SheetContent>
      </Sheet>
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={item.dismissible}
        role={isCritical ? 'alertdialog' : 'dialog'}
        className="max-w-[560px] gap-0 overflow-hidden rounded-2xl border bg-card p-0 shadow-lg sm:max-w-[560px]"
        onEscapeKeyDown={(e) => { if (blockClose) e.preventDefault() }}
        onInteractOutside={(e) => { if (blockClose) e.preventDefault() }}
      >
        {content(DialogTitle)}
      </DialogContent>
    </Dialog>
  )
}

export default SpotlightDialog
