import { Check } from 'lucide-react'
import { cn } from '@/utils/cn'

/** Les trois étapes du flux d'envoi, dans l'ordre. */
const STEPS = ['Montant', 'Confirmation', 'Terminé'] as const

interface SendStepperProps {
  /** Étape en cours : 1 = montant, 2 = confirmation, 3 = terminé. */
  current: 1 | 2 | 3
  className?: string
}

/**
 * Indicateur de progression « Montant → Confirmation → Terminé ».
 * Les étapes passées affichent une coche verte, l'étape courante est mise en
 * avant et signalée aux lecteurs d'écran via aria-current="step".
 * Les libellés sont placés sous les pastilles : le composant reste compact
 * sur mobile (375 px) sans changer de disposition.
 */
export function SendStepper({ current, className }: SendStepperProps) {
  return (
    <nav aria-label="Étapes de l'envoi" className={className}>
      <ol className="grid grid-cols-3">
        {STEPS.map((label, index) => {
          const number = index + 1
          const done = number < current
          const active = number === current
          const isLast = index === STEPS.length - 1

          return (
            <li
              key={label}
              aria-current={active ? 'step' : undefined}
              className="relative flex flex-col items-center gap-2 text-center"
            >
              {/* Trait de liaison vers l'étape suivante (derrière la pastille). */}
              {!isLast && (
                <span
                  aria-hidden="true"
                  className={cn(
                    'absolute top-3.5 left-1/2 h-0.5 w-full transition-colors duration-500 sm:top-4',
                    done ? 'bg-success' : 'bg-line',
                  )}
                />
              )}

              {/* Pastille : numéro de l'étape ou coche quand elle est passée. */}
              <span
                className={cn(
                  'relative z-10 flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold',
                  'transition-all duration-300 sm:h-8 sm:w-8 sm:text-sm',
                  done && 'bg-success text-white',
                  active && 'bg-accent text-white shadow-glow ring-4 ring-accent/15',
                  !done && !active && 'border-2 border-line bg-white text-muted',
                )}
              >
                {done ? <Check size={14} strokeWidth={3} aria-hidden="true" /> : number}
                {done && <span className="sr-only">Étape terminée :</span>}
              </span>

              <span
                className={cn(
                  'text-[11px] font-semibold whitespace-nowrap sm:text-sm',
                  active ? 'text-ink' : done ? 'text-success' : 'text-muted',
                )}
              >
                {label}
              </span>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
