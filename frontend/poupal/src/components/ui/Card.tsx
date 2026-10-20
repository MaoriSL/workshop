import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '@/utils/cn'

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  padding?: 'none' | 'sm' | 'md' | 'lg'
  /** Légère élévation au survol (cartes cliquables). */
  hoverable?: boolean
  children: ReactNode
}

const paddings = { none: '', sm: 'p-4', md: 'p-6', lg: 'p-8' }

/** Conteneur blanc arrondi avec ombre douce : la brique de base des écrans. */
export function Card({ padding = 'md', hoverable, className, children, ...rest }: CardProps) {
  return (
    <div
      className={cn(
        'rounded-2xl border border-line/80 bg-white shadow-soft',
        hoverable && 'transition-all duration-200 hover:-translate-y-0.5 hover:shadow-card',
        paddings[padding],
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  )
}

interface CardHeaderProps {
  title: string
  description?: string
  /** Bouton ou lien aligné à droite du titre. */
  action?: ReactNode
  className?: string
}

export function CardHeader({ title, description, action, className }: CardHeaderProps) {
  return (
    <div className={cn('mb-5 flex items-start justify-between gap-4', className)}>
      <div>
        <h2 className="text-lg font-bold text-ink">{title}</h2>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      </div>
      {action}
    </div>
  )
}
