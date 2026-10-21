import { getInitials } from '@/utils/format'
import { cn } from '@/utils/cn'

type AvatarSize = 'sm' | 'md' | 'lg' | 'xl'

const sizes: Record<AvatarSize, string> = {
  sm: 'h-8 w-8 text-xs',
  md: 'h-10 w-10 text-sm',
  lg: 'h-12 w-12 text-base',
  xl: 'h-16 w-16 text-xl',
}

/** Couleurs pastel attribuées de façon stable à partir du nom. */
const palettes = [
  'bg-blue-100 text-blue-800',
  'bg-violet-100 text-violet-800',
  'bg-emerald-100 text-emerald-800',
  'bg-amber-100 text-amber-800',
  'bg-rose-100 text-rose-800',
  'bg-cyan-100 text-cyan-800',
]

function paletteFor(name: string): string {
  let hash = 0
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) % 9973
  return palettes[hash % palettes.length]
}

interface AvatarProps {
  name: string
  size?: AvatarSize
  /** Variante sur fond foncé (header de l'espace client). */
  inverted?: boolean
  className?: string
}

/** Avatar à initiales : <Avatar name="Alex Martin" size="md" /> */
export function Avatar({ name, size = 'md', inverted, className }: AvatarProps) {
  return (
    <span
      role="img"
      aria-label={name}
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-full font-bold tracking-wide select-none',
        sizes[size],
        inverted ? 'bg-white/15 text-white ring-2 ring-white/30' : paletteFor(name),
        className,
      )}
    >
      {getInitials(name)}
    </span>
  )
}
