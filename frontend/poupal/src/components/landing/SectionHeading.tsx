import { cn } from '@/utils/cn'

interface SectionHeadingProps {
  /** Petit libellé coloré au-dessus du titre (ex. "Avantages"). */
  eyebrow: string
  title: string
  description?: string
  align?: 'left' | 'center'
  /** Variante pour les sections à fond foncé. */
  inverted?: boolean
  className?: string
  /** id donné au titre, pour relier la section via aria-labelledby. */
  titleId?: string
}

/** En-tête commun aux sections de la landing : libellé, titre, description. */
export function SectionHeading({
  eyebrow,
  title,
  description,
  align = 'center',
  inverted,
  className,
  titleId,
}: SectionHeadingProps) {
  return (
    <div className={cn('max-w-2xl', align === 'center' && 'mx-auto text-center', className)}>
      <p className={cn('text-xs font-bold tracking-[0.18em] uppercase', inverted ? 'text-sky' : 'text-accent')}>
        {eyebrow}
      </p>
      <h2
        id={titleId}
        className={cn(
          'mt-3 text-3xl font-extrabold tracking-tight sm:text-4xl',
          inverted ? 'text-white' : 'text-ink',
        )}
      >
        {title}
      </h2>
      {description && (
        <p className={cn('mt-4 text-base leading-relaxed sm:text-lg', inverted ? 'text-white/70' : 'text-muted')}>
          {description}
        </p>
      )}
    </div>
  )
}
