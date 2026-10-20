import { Link, Navigate, useLocation } from 'react-router-dom'
import { LayoutDashboard, Receipt, RotateCcw } from 'lucide-react'
import { ButtonLink, Card, StatusBadge } from '@/components/ui'
import { SendStepper, SuccessCheck } from '@/components/send'
import { usePageTitle } from '@/hooks/usePageTitle'
import { formatCurrency, formatDateTime } from '@/utils/format'
import type { Transaction } from '@/types'

/**
 * Étape 3 du flux d'envoi : confirmation animée de la transaction créée.
 * La transaction arrive via l'état du routeur ; sans elle (accès direct à
 * l'URL ou rechargement), on renvoie vers le tableau de bord.
 */
export function SendSuccessPage() {
  usePageTitle('Envoi réussi')
  const location = useLocation()
  const transaction = (location.state as { transaction?: Transaction } | null)?.transaction

  if (!transaction) return <Navigate to="/dashboard" replace />

  return (
    <div className="mx-auto max-w-lg animate-fade-up">
      <SendStepper current={3} className="mb-6 sm:mb-8" />

      <Card padding="none" className="p-6 text-center sm:p-10">
        <SuccessCheck />

        <h1 className="mt-6 text-2xl font-extrabold text-ink sm:text-3xl">Envoi réussi !</h1>
        <p className="mt-2 text-muted">
          Vous avez envoyé <span className="font-bold text-ink">{formatCurrency(transaction.amount)}</span> à{' '}
          <span className="font-bold text-ink">{transaction.counterparty}</span>.
        </p>

        {/* Récapitulatif de la transaction créée */}
        <dl className="mt-6 divide-y divide-line rounded-xl bg-surface px-4 text-left text-sm">
          <div className="flex items-center justify-between gap-4 py-3">
            <dt className="text-muted">Référence</dt>
            <dd className="font-mono font-semibold text-ink">{transaction.reference}</dd>
          </div>
          <div className="flex items-center justify-between gap-4 py-3">
            <dt className="text-muted">Date</dt>
            <dd className="text-right font-semibold text-ink">{formatDateTime(transaction.date)}</dd>
          </div>
          <div className="flex items-center justify-between gap-4 py-3">
            <dt className="text-muted">Statut</dt>
            <dd>
              <StatusBadge status={transaction.status} />
            </dd>
          </div>
          {transaction.message && (
            <div className="flex items-start justify-between gap-4 py-3">
              <dt className="shrink-0 text-muted">Message</dt>
              <dd className="min-w-0 text-right break-words text-ink">{transaction.message}</dd>
            </div>
          )}
        </dl>

        <div className="mt-6 flex flex-col gap-3 sm:flex-row">
          <ButtonLink
            to="/dashboard"
            variant="primary"
            fullWidth
            className="sm:flex-1"
            leftIcon={<LayoutDashboard size={16} aria-hidden="true" />}
          >
            Retour au tableau de bord
          </ButtonLink>
          <ButtonLink
            to={`/transactions/${transaction.id}`}
            variant="secondary"
            fullWidth
            className="sm:flex-1"
            leftIcon={<Receipt size={16} aria-hidden="true" />}
          >
            Voir la transaction
          </ButtonLink>
        </div>

        <Link
          to="/send"
          className="mt-5 inline-flex items-center gap-1.5 text-sm font-semibold text-accent transition-colors hover:text-accent-hover hover:underline"
        >
          <RotateCcw size={14} aria-hidden="true" />
          Effectuer un autre envoi
        </Link>
      </Card>
    </div>
  )
}
