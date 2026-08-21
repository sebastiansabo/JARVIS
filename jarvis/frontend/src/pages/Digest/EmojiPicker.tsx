import { useMemo, useState } from 'react'
import { Input } from '@/components/ui/input'

// Curated set for a work chat — [emoji, search keywords (ro/en)].
const EMOJI: [string, string][] = [
  ['👍', 'thumbs up like yes approve bine ok'], ['🙏', 'thanks please pray multumesc rog'],
  ['👏', 'clap bravo applause aplauze'], ['🙌', 'celebrate praise raise hands'],
  ['💪', 'strong muscle power putere'], ['🤝', 'handshake deal agree acord'],
  ['👌', 'ok perfect okay'], ['✌️', 'peace victory'], ['🤞', 'fingers crossed luck noroc'],
  ['👋', 'wave hi bye salut pa'], ['🤙', 'call shaka'], ['✍️', 'write sign semna'],
  ['❤️', 'heart love red inima'], ['🧡', 'heart orange'], ['💛', 'heart yellow'],
  ['💚', 'heart green'], ['💙', 'heart blue'], ['💜', 'heart purple'], ['🖤', 'heart black'],
  ['🤍', 'heart white'], ['💯', 'hundred perfect 100 suta'], ['🔥', 'fire hot lit tare'],
  ['⭐', 'star favorite stea'], ['✨', 'sparkles shiny new'], ['🎉', 'party tada celebrate petrecere'],
  ['🎊', 'confetti party'], ['🥳', 'party face celebrate'], ['😀', 'smile happy grin zambet'],
  ['😃', 'smile happy'], ['😄', 'smile laugh happy'], ['😁', 'grin smile'], ['😆', 'laugh haha'],
  ['😅', 'sweat smile relief'], ['😂', 'laugh cry joy haha lol ras'], ['🤣', 'rofl laugh floor'],
  ['🙂', 'slight smile'], ['🙃', 'upside down'], ['😉', 'wink'], ['😊', 'blush happy smile'],
  ['😇', 'angel innocent'], ['😍', 'heart eyes love'], ['🥰', 'love hearts adore'],
  ['😘', 'kiss blow'], ['😋', 'yum tasty delicious gustos'], ['😜', 'wink tongue silly'],
  ['🤪', 'crazy zany goofy'], ['🤨', 'raised eyebrow suspicious'], ['🧐', 'monocle inspect'],
  ['🤓', 'nerd glasses'], ['😎', 'cool sunglasses'], ['🤩', 'star struck wow'],
  ['🤔', 'thinking hmm ganditor'], ['🤗', 'hug imbratisare'], ['🤭', 'giggle oops'],
  ['🤫', 'shush quiet secret'], ['😐', 'neutral meh'], ['😬', 'grimace awkward'],
  ['🙄', 'eye roll'], ['😮', 'wow open mouth'], ['😲', 'astonished shocked'],
  ['🥱', 'yawn tired bored'], ['😴', 'sleep zzz somn'], ['😷', 'mask sick'],
  ['😢', 'cry sad trist'], ['😭', 'sob cry loud plans'], ['😔', 'pensive sad'],
  ['😟', 'worried ingrijorat'], ['😕', 'confused'], ['🥺', 'pleading puppy eyes'],
  ['😤', 'triumph steam'], ['😠', 'angry suparat'], ['😡', 'rage mad furios'],
  ['🤬', 'swear curse'], ['😳', 'flushed embarrassed'], ['🥵', 'hot heat cald'],
  ['🥶', 'cold freeze frig'], ['😱', 'scream fear'], ['😨', 'fearful'], ['🤯', 'mind blown'],
  ['👀', 'eyes look watching'], ['🚀', 'rocket launch fast rapid'], ['✅', 'check done yes bifat'],
  ['❌', 'cross no wrong gresit'], ['⚠️', 'warning attention atentie'], ['❓', 'question intrebare'],
  ['❗', 'exclamation'], ['💡', 'idea lightbulb idee'], ['📌', 'pin'], ['📎', 'clip attach'],
  ['📅', 'calendar date data'], ['⏰', 'alarm clock time ora'], ['💰', 'money bani'],
  ['📈', 'chart up growth crestere'], ['📉', 'chart down scadere'], ['💻', 'laptop computer'],
  ['📱', 'phone mobile telefon'], ['📷', 'camera photo poza'], ['🎯', 'target goal tinta'],
  ['🏆', 'trophy win cupa'], ['☕', 'coffee cafea'], ['🍕', 'pizza food mancare'],
  ['🍺', 'beer bere'], ['🎂', 'cake birthday tort'], ['🚗', 'car masina'], ['🏠', 'house home casa'],
]

const RECENT_KEY = 'chat-emoji-recent'

export default function EmojiPicker({ onPick }: { onPick: (emoji: string) => void }) {
  const [q, setQ] = useState('')
  const [recent, setRecent] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]') } catch { return [] }
  })

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase()
    return s ? EMOJI.filter(([, kw]) => kw.includes(s)).map(e => e[0]) : EMOJI.map(e => e[0])
  }, [q])

  const pick = (e: string) => {
    onPick(e)
    const next = [e, ...recent.filter(r => r !== e)].slice(0, 24)
    setRecent(next)
    try { localStorage.setItem(RECENT_KEY, JSON.stringify(next)) } catch { /* ignore */ }
  }

  return (
    <div className="w-72">
      <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Caută emoji…" className="mb-2 h-8" autoFocus />
      {!q && recent.length > 0 && (
        <>
          <p className="px-1 pb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Recente</p>
          <div className="mb-2 grid grid-cols-8 gap-0.5">
            {recent.map((e) => (
              <button key={`r-${e}`} type="button" onClick={() => pick(e)} className="rounded p-1 text-xl leading-none hover:bg-accent">{e}</button>
            ))}
          </div>
        </>
      )}
      <div className="grid max-h-56 grid-cols-8 gap-0.5 overflow-y-auto">
        {filtered.map((e) => (
          <button key={e} type="button" onClick={() => pick(e)} className="rounded p-1 text-xl leading-none hover:bg-accent">{e}</button>
        ))}
        {filtered.length === 0 && <p className="col-span-8 py-6 text-center text-xs text-muted-foreground">Niciun emoji găsit</p>}
      </div>
    </div>
  )
}
