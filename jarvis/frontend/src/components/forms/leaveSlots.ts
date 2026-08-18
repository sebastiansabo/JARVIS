function parseHM(v: string): number | null {
  const m = v.match(/^(\d{1,2}):(\d{2})$/)
  if (!m) return null
  const h = +m[1], mi = +m[2]
  return h > 23 || mi > 59 ? null : h * 60 + mi
}

function toHM(mins: number): string {
  const t = Math.max(0, Math.min(1439, Math.round(mins)))
  return `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`
}

export function buildStartSlots(startHM: string, endHM: string): string[] {
  const s = parseHM(startHM), e = parseHM(endHM)
  if (s === null || e === null) return []
  const out: string[] = []
  for (let t = s; t <= e - 30; t += 30) out.push(toHM(t))
  return out
}

export function fmtDurationLabel(hours: number): string {
  const mins = Math.round(hours * 60)
  const h = Math.floor(mins / 60), m = mins % 60
  if (h === 0) return `${m} min`
  if (m === 0) return `${h} h`
  return `${h}:${String(m).padStart(2, '0')} h`
}

export function buildDurationOptions(
  startHM: string, endHM: string, dayCapHours: number,
): { value: number; label: string }[] {
  const s = parseHM(startHM), e = parseHM(endHM)
  if (s === null || e === null) return []
  const windowHours = (e - s) / 60
  const maxHours = Math.min(dayCapHours, windowHours)
  const out: { value: number; label: string }[] = []
  for (let v = 0.5; v <= maxHours + 1e-9; v += 0.5) out.push({ value: v, label: fmtDurationLabel(v) })
  return out
}

export function computeReturn(startHM: string, durationHours: number): string {
  const s = parseHM(startHM)
  if (s === null) return ''
  return toHM(s + Math.round(durationHours * 60))
}
