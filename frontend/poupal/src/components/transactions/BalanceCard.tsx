import { ArrowDownToLine, Send, Wallet } from 'lucide-react'
import { ButtonLink, Skeleton } from '@/components/ui'
import { formatCurrency } from '@/utils/format'

interface BalanceCardProps {
  balance: number
  /** Affiche un bloc fantôme à la place du montant. */
  loading?: boolean
}

/**
 * Carte « Solde disponible » du tableau de bord : dégradé de marque,
 * montant en grand et actions principales (envoyer / demander).
 */
export function BalanceCard({ balance, loading = false }: BalanceCardProps) {
  return (
    <section
      aria-labelledby="balance-label"
      className="relative flex h-full flex-col overflow-hidden rounded-2xl bg-brand-gradient p-6 text-white shadow-card sm:p-8"
    >
      {/* Décor : deux halos flous, purement visuels */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -top-20 -right-12 h-64 w-64 rounded-full bg-sky/40 blur-3xl"
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -bottom-24 -left-12 h-56 w-56 rounded-full bg-white/10 blur-3xl"
      />

      <div className="relative flex flex-wrap items-start justify-between gap-3">
        <p id="balance-label" className="text-sm font-medium text-white/80">
          Solde disponible
        </p>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 text-xs font-semibold ring-1 ring-white/25 ring-inset">
          <Wallet size={14} aria-hidden="true" />
          Compte courant · EUR
        </span>
      </div>

      {loading ? (
        <Skeleton className="relative mt-3 h-10 w-52 opacity-30 sm:h-12" />
      ) : (
        <p className="relative mt-2 text-4xl font-extrabold tracking-tight sm:text-5xl">{formatCurrency(balance)}</p>
      )}

      <div className="relative mt-auto flex flex-col gap-3 pt-7 sm:flex-row">
        <ButtonLink to="/send" variant="secondary" leftIcon={<Send size={18} aria-hidden="true" />}>
          Envoyer de l'argent
        </ButtonLink>
        {/* Fonction absente de la démo : bouton désactivé, stylé à la main
            car aucune variante de <Button> n'est prévue pour un fond foncé. */}
        <button
          type="button"
          disabled
          title="Bientôt disponible"
          className="inline-flex h-11 cursor-not-allowed items-center justify-center gap-2 rounded-xl px-5 text-sm font-semibold text-white opacity-70 ring-1 ring-white/35 ring-inset"
        >
          <ArrowDownToLine size={18} aria-hidden="true" />
          Demander
          <span className="rounded-full bg-white/20 px-2 py-0.5 text-[10px] font-bold tracking-wide uppercase">
            Bientôt
          </span>
        </button>
      </div>
    </section>
  )
}
