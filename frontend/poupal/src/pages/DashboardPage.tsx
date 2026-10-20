import { useEffect, useState, type CSSProperties, type ReactNode } from 'react'
import { ArrowDownLeft, ArrowUpRight, Clock, RefreshCw } from 'lucide-react'
import type { Transaction, TransactionType } from '@/types'
import { getAccount, getErrorMessage, listTransactions } from '@/api'
import { useAuth } from '@/hooks/useAuth'
import { usePageTitle } from '@/hooks/usePageTitle'
import { Alert, Button, Card, CardHeader, Skeleton } from '@/components/ui'
import { BalanceCard, TransactionList } from '@/components/transactions'
import { formatCurrency, formatDate } from '@/utils/format'
import { cn } from '@/utils/cn'

/** Filtre de la liste : tous les mouvements, ou seulement les reçus / envoyés. */
type TransactionFilter = 'all' | TransactionType

const FILTERS: { value: TransactionFilter; label: string }[] = [
  { value: 'all', label: 'Tous' },
  { value: 'received', label: 'Reçus' },
  { value: 'sent', label: 'Envoyés' },
]

/** Nombre de transactions affichées avant de cliquer sur « Voir tout ». */
const PREVIEW_COUNT = 8

const EMPTY_MESSAGES: Record<TransactionFilter, string> = {
  all: 'Vos prochains mouvements apparaîtront ici.',
  received: 'Vous n’avez encore reçu aucun paiement.',
  sent: 'Vous n’avez encore envoyé aucun paiement.',
}

/** Page « Tableau de bord » de l'espace client : solde, synthèse du mois et dernières transactions. */
export function DashboardPage() {
  usePageTitle('Tableau de bord')
  const { user } = useAuth()

  // Deux chargements indépendants : si un service est dégradé, l'autre bloc reste utilisable.
  const account = useRequest(getAccount)
  const transactions = useRequest(listTransactions)

  const [filter, setFilter] = useState<TransactionFilter>('all')
  const [showAll, setShowAll] = useState(false)

  const firstName = user?.name.split(' ')[0] ?? ''
  const now = new Date() // date du jour, affichée sous le titre

  const allTransactions = transactions.data ?? []
  const filtered = filter === 'all' ? allTransactions : allTransactions.filter((t) => t.type === filter)
  const visible = showAll ? filtered : filtered.slice(0, PREVIEW_COUNT)
  const summary = summarizeMonth(allTransactions)

  const stats = [
    {
      label: 'Reçu ce mois',
      value: formatCurrency(summary.received),
      icon: <ArrowDownLeft size={20} aria-hidden="true" />,
      iconClasses: 'bg-success-soft text-success',
    },
    {
      label: 'Envoyé ce mois',
      value: formatCurrency(summary.sent),
      icon: <ArrowUpRight size={20} aria-hidden="true" />,
      iconClasses: 'bg-accent-soft text-accent',
    },
    {
      label: 'En attente',
      value: formatCurrency(summary.pending),
      hint: `${summary.pendingCount} transaction${summary.pendingCount > 1 ? 's' : ''}`,
      icon: <Clock size={20} aria-hidden="true" />,
      iconClasses: 'bg-warning-soft text-warning',
    },
  ]

  return (
    <div className="space-y-6 sm:space-y-8">
      {/* En-tête de page */}
      <header className="animate-fade-up">
        <h1 className="text-2xl font-extrabold tracking-tight text-ink sm:text-3xl">
          Bonjour, {firstName} <span aria-hidden="true">👋</span>
        </h1>
        <p className="mt-1 text-sm text-muted sm:text-base">
          Voici un aperçu de votre compte · <time dateTime={now.toISOString()}>{formatDate(now.toISOString())}</time>
        </p>
      </header>

      {/* Solde + synthèse du mois */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="animate-fade-up" style={{ animationDelay: '60ms' }}>
          {account.error ? (
            <Card className="flex h-full flex-col gap-4">
              <Alert tone="error" title="Impossible de charger votre solde">
                {account.error}
              </Alert>
              <Button
                variant="secondary"
                size="sm"
                className="self-start"
                onClick={account.reload}
                leftIcon={<RefreshCw size={16} aria-hidden="true" />}
              >
                Réessayer
              </Button>
            </Card>
          ) : (
            <BalanceCard balance={account.data?.balance ?? 0} loading={account.loading} />
          )}
        </div>

        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
          {stats.map((stat, index) => (
            <StatCard
              key={stat.label}
              label={stat.label}
              value={transactions.error ? '—' : stat.value}
              hint={transactions.error ? undefined : stat.hint}
              icon={stat.icon}
              iconClasses={stat.iconClasses}
              loading={transactions.loading}
              style={{ animationDelay: `${120 + index * 60}ms` }}
            />
          ))}
        </div>
      </div>

      {/* Dernières transactions */}
      <Card padding="none" className="animate-fade-up overflow-hidden" style={{ animationDelay: '300ms' }}>
        <div className="border-b border-line px-4 pt-5 sm:px-6 sm:pt-6">
          <CardHeader
            title="Dernières transactions"
            description="Vos mouvements les plus récents."
            className="flex-wrap"
            action={
              <FilterTabs
                value={filter}
                onChange={(next) => {
                  setFilter(next)
                  setShowAll(false)
                }}
              />
            }
          />
        </div>

        <TransactionList
          transactions={visible}
          loading={transactions.loading}
          error={transactions.error}
          onRetry={transactions.reload}
          emptyMessage={EMPTY_MESSAGES[filter]}
        />

        {filtered.length > PREVIEW_COUNT && (
          <div className="border-t border-line px-4 py-3 text-center">
            <button
              type="button"
              aria-expanded={showAll}
              onClick={() => setShowAll((value) => !value)}
              className="rounded-lg px-3 py-1.5 text-sm font-semibold text-accent transition-colors hover:bg-accent-soft"
            >
              {showAll ? 'Voir moins' : `Voir tout (${filtered.length})`}
            </button>
          </div>
        )}
      </Card>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Sous-composants et utilitaires propres à la page                     */
/* ------------------------------------------------------------------ */

interface StatCardProps {
  label: string
  value: string
  hint?: string
  icon: ReactNode
  /** Couleurs du pictogramme (fond + icône). */
  iconClasses: string
  loading?: boolean
  style?: CSSProperties
}

/** Petite carte de synthèse : pictogramme coloré, libellé et montant. */
function StatCard({ label, value, hint, icon, iconClasses, loading, style }: StatCardProps) {
  return (
    <Card padding="sm" className="flex animate-fade-up items-center gap-3" style={style}>
      <span className={cn('flex h-11 w-11 shrink-0 items-center justify-center rounded-xl', iconClasses)}>
        {icon}
      </span>
      <div className="min-w-0">
        <p className="text-xs font-medium text-muted">{label}</p>
        {loading ? (
          <Skeleton className="mt-1.5 h-5 w-24" />
        ) : (
          <p className="truncate text-lg font-bold text-ink">{value}</p>
        )}
        {!loading && hint && <p className="text-xs text-muted">{hint}</p>}
      </div>
    </Card>
  )
}

interface FilterTabsProps {
  value: TransactionFilter
  onChange: (value: TransactionFilter) => void
}

/** Boutons segmentés « Tous / Reçus / Envoyés » (pleine largeur sur mobile). */
function FilterTabs({ value, onChange }: FilterTabsProps) {
  return (
    <div role="group" aria-label="Filtrer les transactions" className="flex w-full rounded-xl bg-surface p-1 sm:w-auto">
      {FILTERS.map((option) => {
        const active = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(option.value)}
            className={cn(
              'flex-1 rounded-lg px-3 py-1.5 text-xs font-semibold whitespace-nowrap transition-all sm:flex-none',
              active ? 'bg-white text-primary shadow-soft' : 'text-muted hover:text-ink',
            )}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

/**
 * Totaux affichés dans les cartes de synthèse :
 * - reçu / envoyé : transactions réussies du mois courant ;
 * - en attente : toutes les transactions encore en attente (quel que soit le mois).
 */
function summarizeMonth(transactions: Transaction[], now = new Date()) {
  const summary = { received: 0, sent: 0, pending: 0, pendingCount: 0 }

  for (const transaction of transactions) {
    if (transaction.status === 'pending') {
      summary.pending += transaction.amount
      summary.pendingCount += 1
      continue
    }
    if (transaction.status !== 'completed') continue

    const date = new Date(transaction.date)
    const sameMonth = date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth()
    if (!sameMonth) continue

    if (transaction.type === 'received') summary.received += transaction.amount
    else summary.sent += transaction.amount
  }

  return summary
}

/**
 * Charge une ressource asynchrone et expose son état : données, chargement,
 * message d'erreur et fonction de relance (utilisée par « Réessayer »).
 * `fetcher` doit être une référence stable (fonction de `@/api`, pas une
 * fonction fléchée créée dans le rendu), sinon la requête serait relancée en boucle.
 */
function useRequest<T>(fetcher: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0) // incrémenté pour relancer la requête

  useEffect(() => {
    let cancelled = false // ignore la réponse si la page a été quittée entre-temps
    setLoading(true)
    setError(null)

    fetcher()
      .then((result) => {
        if (!cancelled) setData(result)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(getErrorMessage(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [fetcher, attempt])

  const reload = () => setAttempt((count) => count + 1)

  return { data, loading, error, reload }
}
