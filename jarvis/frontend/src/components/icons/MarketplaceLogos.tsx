import { useId } from 'react'

/**
 * Brand marks for the marketplaces a CarPark vehicle can be published to,
 * used in the catalog "Publicat" column. Inline SVG (no binary assets) so they
 * stay crisp at any size and render identically in light/dark.
 */

type LogoProps = { className?: string; title?: string }

// Autovit — navy/red diagonally-split square with a bold white "A".
export function AutovitLogo({ className, title = 'Autovit' }: LogoProps) {
  const clip = useId()
  return (
    <svg viewBox="0 0 32 32" className={className} role="img" aria-label={title}>
      <title>{title}</title>
      <defs>
        <clipPath id={clip}>
          <rect width="32" height="32" rx="6" />
        </clipPath>
      </defs>
      <g clipPath={`url(#${clip})`}>
        <rect width="32" height="32" fill="#17284d" />
        {/* red lower-right triangle (navy stays upper-left) */}
        <path d="M32 0 L32 32 L0 32 Z" fill="#e12a2f" />
        <text
          x="16" y="23.5" textAnchor="middle"
          fontSize="20" fontWeight="800" fill="#ffffff"
          fontFamily="ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
        >
          A
        </text>
      </g>
    </svg>
  )
}

// Autoworld.ro — navy square with a white lowercase "a" and an orange dot.
export function AutoworldLogo({ className, title = 'Autoworld.ro' }: LogoProps) {
  return (
    <svg viewBox="0 0 32 32" className={className} role="img" aria-label={title}>
      <title>{title}</title>
      <rect width="32" height="32" rx="6" fill="#17284d" />
      <text
        x="13.5" y="24" textAnchor="middle"
        fontSize="23" fontWeight="800" fill="#ffffff"
        fontFamily="ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
      >
        a
      </text>
      <circle cx="24" cy="23" r="3.4" fill="#f26a21" />
    </svg>
  )
}
