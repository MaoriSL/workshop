import { useEffect, useState } from 'react'
import { listTransactions } from '@/api'
import { Avatar, Skeleton } from '@/components/ui'
import type { Transaction } from '@/types'
import { cn } from '@/utils/cn'

/** Nombre maximum de puces affichées. */
const MAX_RECIPIENTS = 5

interface Recipient {
  /** Nom affiché sur la puce. */
  label: string
  /** Valeur mise dans le champ : l'email quand il est connu (l'API identifie un destinataire par son email). */
  value: string
}

/** Contreparties uniques, de la plus récente à la plus ancienne. */
function uniqueCounterparties(transactions: Transaction[]): Recipient[] {
  const recipients: Recipient[] = []
  for (const transaction of transactions) {
    const value = transaction.counterpartyEmail ?? transaction.counterparty
    if (!recipients.some((r) => r.value === value)) recipients.push({ label: transaction.counterparty, value })
    if (recipients.length === MAX_RECIPIENTS) break
  }
  return recipients
}

interface RecentRecipientsProps {
  /** Valeur actuelle du champ destinataire (pour mettre en avant la puce choisie). */
  selected: string
  onSelect: (value: string) => void
}

/**
 * « Destinataires récents » : puces (avatar + nom) construites à partir des
 * dernières transactions. Un clic remplit le champ destinataire.
 */
export function RecentRecipients({ selected, onSelect }: RecentRecipientsProps) {
  // null = chargement en cours ; [] = rien à proposer (la section disparaît).
  const [recipients, setRecipients] = useState<Recipient[] | null>(null)

  useEffect(() => {
    let cancelled = false
    listTransactions()
      .then((transactions) => {
        if (!cancelled) setRecipients(uniqueCounterparties(transactions))
      })
      .catch(() => {
        // Suggestion facultative : en cas d'erreur, on masque simplement la section.
        if (!cancelled) setRecipients([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (recipients !== null && recipients.length === 0) return null

  return (
    <div className="mt-3">
      <p className="text-xs font-semibold tracking-wide text-muted uppercase">Destinataires récents</p>
      {/*
        Sur mobile, la rangée défile horizontalement (et déborde jusqu'aux bords
        de la carte) pour ne pas empiler cinq puces ; à partir de sm, elle passe à la ligne.
      */}
      <ul
        className={cn(
          '-mx-5 mt-1 flex gap-2 overflow-x-auto px-5 py-1 [scrollbar-width:none]',
          'sm:mx-0 sm:mt-2 sm:flex-wrap sm:overflow-visible sm:px-0 sm:py-0',
        )}
      >
        {recipients === null
          ? Array.from({ length: 4 }, (_, index) => (
              <li key={index} className="shrink-0">
                <Skeleton className="h-10 w-32 rounded-full" />
              </li>
            ))
          : recipients.map(({ label, value }) => {
              const isSelected = selected.trim() === value
              return (
                <li key={value} className="shrink-0">
                  <button
                    type="button"
                    onClick={() => onSelect(value)}
                    aria-pressed={isSelected}
                    className={cn(
                      'inline-flex items-center gap-2 rounded-full border bg-white py-1 pr-3.5 pl-1 text-sm font-medium text-ink',
                      'transition-all duration-200 hover:-translate-y-px hover:border-accent/40 hover:bg-accent-soft/60',
                      isSelected ? 'border-accent bg-accent-soft ring-2 ring-accent/15' : 'border-line',
                    )}
                  >
                    <Avatar name={label} size="sm" />
                    <span>{label}</span>
                  </button>
                </li>
              )
            })}
      </ul>
    </div>
  )
}
