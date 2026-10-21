import { Inbox, RefreshCw } from 'lucide-react'
import type { Transaction } from '@/types'
import { Alert, Button, EmptyState, Skeleton } from '@/components/ui'
import { TransactionRow } from './TransactionRow'

interface TransactionListProps {
  transactions: Transaction[]
  loading?: boolean
  error?: string | null
  /** Appelé par le bouton « Réessayer » de l'état d'erreur. */
  onRetry?: () => void
  /** Texte affiché quand la liste est vide. */
  emptyMessage?: string
}

/** Nombre de lignes fantômes affichées pendant le chargement. */
const SKELETON_ROWS = 5

/**
 * Liste de transactions réutilisable, avec ses quatre états :
 * chargement (lignes fantômes), erreur (alerte + relance), vide, et liste.
 */
export function TransactionList({
  transactions,
  loading = false,
  error = null,
  onRetry,
  emptyMessage = 'Vos prochains mouvements apparaîtront ici.',
}: TransactionListProps) {
  if (loading) {
    return (
      <div role="status" aria-label="Chargement des transactions" className="divide-y divide-line">
        {Array.from({ length: SKELETON_ROWS }, (_, index) => (
          <div key={index} className="flex items-center gap-3 px-4 py-3.5 sm:gap-4 sm:px-6">
            <Skeleton className="h-10 w-10 shrink-0 rounded-full" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-3.5 w-2/5 max-w-40" />
              <Skeleton className="h-3 w-3/5 max-w-56" />
            </div>
            <div className="flex flex-col items-end gap-2">
              <Skeleton className="h-3.5 w-20" />
              <Skeleton className="h-5 w-16 rounded-full" />
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 sm:p-6">
        <Alert tone="error" title="Impossible de charger les transactions">
          <p>{error}</p>
          {onRetry && (
            <Button
              variant="secondary"
              size="sm"
              className="mt-3"
              onClick={onRetry}
              leftIcon={<RefreshCw size={16} aria-hidden="true" />}
            >
              Réessayer
            </Button>
          )}
        </Alert>
      </div>
    )
  }

  if (transactions.length === 0) {
    return (
      <EmptyState
        icon={<Inbox size={26} aria-hidden="true" />}
        title="Aucune transaction"
        description={emptyMessage}
      />
    )
  }

  return (
    <ul className="divide-y divide-line">
      {transactions.map((transaction, index) => (
        // Entrée en cascade : chaque ligne apparaît avec un léger décalage
        <li key={transaction.id} className="animate-fade-up" style={{ animationDelay: `${index * 40}ms` }}>
          <TransactionRow transaction={transaction} />
        </li>
      ))}
    </ul>
  )
}
