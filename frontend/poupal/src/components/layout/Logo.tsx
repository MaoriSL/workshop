import { useState } from 'react'
import { Link } from 'react-router-dom'
import { cn } from '@/utils/cn'

interface LogoProps {
  /** "color" sur fond clair, "white" sur fond foncé. */
  variant?: 'color' | 'white'
  /** Taille du pictogramme en pixels. */
  size?: number
  /** Affiche le nom "Poupal" à côté du pictogramme. */
  showWordmark?: boolean
  to?: string
  className?: string
}

/**
 * Logo Poupal : pictogramme (fichiers déposés dans public/) + mot-symbole.
 * Si l'image est absente, seul le mot-symbole textuel est affiché pour ne
 * jamais laisser un lien vide.
 */
export function Logo({ variant = 'color', size = 40, showWordmark = true, to = '/', className }: LogoProps) {
  const [failed, setFailed] = useState(false)
  const src = variant === 'white' ? '/logo-poupal-white.png' : '/logo-poupal.png'
  const isWhite = variant === 'white'

  return (
    <Link to={to} aria-label="Poupal — accueil" className={cn('inline-flex items-center gap-2.5', className)}>
      {!failed && (
        <img
          src={src}
          alt=""
          width={size}
          height={size}
          style={{ width: size, height: size }}
          className="shrink-0 rounded-xl object-contain"
          onError={() => setFailed(true)}
        />
      )}
      {(showWordmark || failed) && (
        <span
          className={cn(
            'text-[1.35rem] font-extrabold tracking-tight',
            isWhite ? 'text-white' : 'text-primary',
          )}
        >
          Pou<span className={isWhite ? 'text-sky' : 'text-accent'}>pal</span>
        </span>
      )}
    </Link>
  )
}
