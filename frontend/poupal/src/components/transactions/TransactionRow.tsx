import { Link } from 'react-router-dom'
import { ArrowDownLeft, ArrowUpRight, ChevronRight } from 'lucide-react'
import type { Transaction } from '@/types'
import { Avatar, StatusBadge } from '@/components/ui'
import { formatDate, formatSignedAmount } from '@/utils/format'
import { cn } from '@/utils/cn'

interface TransactionRowProps {
  transaction: Transaction
}

/**
 * Ligne d'une transaction : avatar, contrepartie, date (+ message), montant signé
 * et statut. Toute la ligne est un lien vers le détail (/transactions/:id).
 */
export function TransactionRow({ transaction }: TransactionRowProps) {
  const { id, type, status, counterparty, amount, date, message } = transaction
  const isReceived = type === 'received'
  const isFailed = status === 'failed'

  return (
    <Link
      to={`/transactions/${id}`}
      className={cn(
        'group flex items-center gap-3 px-4 py-3.5 transition-colors sm:gap-4 sm:px-6',
        'hover:bg-surface focus-visible:bg-surface focus-visible:-outline-offset-2',
      )}
    >
      {/* Avatar + petite pastille indiquant le sens du mouvement (reçu / envoyé) */}
      <span aria-hidden="true" className="relative shrink-0">
        <Avatar name={counterparty} size="md" />
        <span
          className={cn(
            'absolute -right-0.5 -bottom-0.5 flex h-4.5 w-4.5 items-center justify-center rounded-full bg-white shadow-soft',
            isReceived ? 'text-success' : 'text-primary',
          )}
        >
          {isReceived ? <ArrowDownLeft size={12} strokeWidth={2.5} /> : <ArrowUpRight size={12} strokeWidth={2.5} />}
        </span>
      </span>

      {/* Contrepartie + date (et message tronqué s'il existe) */}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-ink">{counterparty}</p>
        <p className="truncate text-xs text-muted">
          <time dateTime={date}>{formatDate(date)}</time>
          {message && <span> · {message}</span>}
        </p>
      </div>

      {/* Mobile : montant au-dessus du badge. Desktop : badge à gauche du montant (row-reverse). */}
      <div className="flex shrink-0 flex-col items-end gap-1 sm:flex-row-reverse sm:items-center sm:gap-4">
        <span
          className={cn(
            'text-sm font-bold whitespace-nowrap sm:text-base',
            isFailed ? 'text-muted line-through' : isReceived ? 'text-success' : 'text-ink',
          )}
        >
          {formatSignedAmount(type, amount)}
        </span>
        <StatusBadge status={status} />
      </div>

      <ChevronRight
        size={18}
        aria-hidden="true"
        className="hidden shrink-0 text-line transition-colors group-hover:text-accent sm:block"
      />
    </Link>
  )
}
