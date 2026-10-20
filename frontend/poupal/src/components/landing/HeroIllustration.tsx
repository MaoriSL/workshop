import { CheckCircle2, ShieldCheck, TrendingUp } from 'lucide-react'
import { Avatar, StatusBadge } from '@/components/ui'
import type { Transaction } from '@/types'
import { formatCurrency, formatDate, formatSignedAmount } from '@/utils/format'
import { cn } from '@/utils/cn'

/** Aperçu purement décoratif affiché dans le hero : données inventées, aucune donnée réelle. */
type PreviewTransaction = Pick<Transaction, 'id' | 'counterparty' | 'type' | 'status' | 'amount' | 'date'>

const previewBalance = 2450
const previewMonthly = 1370

const previewTransactions: PreviewTransaction[] = [
  { id: 'demo-1', counterparty: 'Camille Dupont', type: 'received', status: 'completed', amount: 120, date: '2026-10-18T14:32:00Z' },
  { id: 'demo-2', counterparty: 'Nathan Petit', type: 'sent', status: 'pending', amount: 45.5, date: '2026-10-17T18:05:00Z' },
  { id: 'demo-3', counterparty: 'Léa Bernard', type: 'received', status: 'completed', amount: 1250, date: '2026-10-14T09:30:00Z' },
]

/**
 * Illustration du hero construite en CSS/JSX (pas d'image) :
 * une carte de solde flottante, une mini-liste de transactions
 * et deux pastilles "notification". Le tout est masqué aux lecteurs
 * d'écran car purement décoratif.
 */
export function HeroIllustration() {
  return (
    <div aria-hidden="true" className="relative mx-auto w-full max-w-md lg:max-w-lg">
      {/* Carte de solde */}
      <div className="animate-float rounded-3xl bg-brand-gradient p-6 text-white shadow-card motion-reduce:animate-none sm:p-7">
        <div className="flex items-center justify-between gap-3">
          <span className="text-lg font-extrabold tracking-tight">
            Pou<span className="text-sky">pal</span>
          </span>
          <span className="flex items-center gap-2 rounded-full bg-white/15 py-1 pr-3 pl-1 text-xs font-semibold">
            <Avatar name="Alex Martin" size="sm" inverted />
            Alex Martin
          </span>
        </div>

        <p className="mt-8 text-sm font-medium text-white/70">Solde disponible</p>
        <p className="mt-1 text-4xl font-extrabold tracking-tight sm:text-[2.6rem]">{formatCurrency(previewBalance)}</p>

        <div className="mt-6 flex flex-wrap items-center gap-2 text-xs font-semibold">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-2.5 py-1">
            <TrendingUp size={14} />+ {formatCurrency(previewMonthly)} ce mois
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-success/25 px-2.5 py-1 text-green-100">
            <ShieldCheck size={14} />
            Compte vérifié
          </span>
        </div>
      </div>

      {/* Mini-liste de transactions, légèrement décalée pour donner de la profondeur */}
      <div className="relative z-10 -mt-5 ml-5 animate-fade-up rounded-2xl border border-line/80 bg-white p-4 shadow-card [animation-delay:350ms] sm:ml-10">
        <div className="flex items-center justify-between">
          <p className="text-sm font-bold text-ink">Dernières transactions</p>
          <span className="text-xs font-semibold text-accent">Tout voir</span>
        </div>
        <ul className="mt-2 divide-y divide-line/70">
          {previewTransactions.map((transaction) => (
            <li key={transaction.id} className="flex items-center gap-3 py-2.5">
              <Avatar name={transaction.counterparty} size="sm" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-ink">{transaction.counterparty}</p>
                <p className="text-xs text-muted">{formatDate(transaction.date)}</p>
              </div>
              <div className="flex flex-col items-end gap-1">
                <p className={cn('text-sm font-bold', transaction.type === 'received' ? 'text-success' : 'text-ink')}>
                  {formatSignedAmount(transaction.type, transaction.amount)}
                </p>
                <StatusBadge status={transaction.status} />
              </div>
            </li>
          ))}
        </ul>
      </div>

      {/* Pastille "paiement reçu" */}
      <div className="absolute -top-5 right-2 z-20 flex animate-fade-up items-center gap-2 rounded-full bg-white px-3.5 py-2 text-xs font-semibold text-ink shadow-card ring-1 ring-line/80 [animation-delay:700ms] sm:-right-6">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-success-soft text-success">
          <CheckCircle2 size={14} />
        </span>
        Paiement reçu · {formatSignedAmount('received', 120)}
      </div>

      {/* Pastille "surveillance IA" (thème cyber-résilience) */}
      <div className="absolute -bottom-4 left-2 z-20 flex animate-fade-up items-center gap-2 rounded-full bg-ink px-3.5 py-2 text-xs font-semibold text-white shadow-card [animation-delay:900ms] sm:-left-6">
        <span className="relative flex h-2.5 w-2.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-sky opacity-75 motion-reduce:animate-none" />
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-sky" />
        </span>
        Surveillance IA active
      </div>
    </div>
  )
}
