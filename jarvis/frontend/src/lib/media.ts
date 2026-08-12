export function mediaUrl(value: string | null | undefined): string {
  if (!value) return ''
  if (value.startsWith('data:') || value.startsWith('http://') || value.startsWith('https://')) {
    return value
  }
  return `/api/media/${value}`
}
