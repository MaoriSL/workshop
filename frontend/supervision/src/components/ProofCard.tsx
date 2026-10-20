// ---------------------------------------------------------------------------
// Carte de preuve de reprise : une NOUVELLE transaction qui réussit après
// l'incident. C'est l'élément clé de la démonstration, donc très visible.
// ---------------------------------------------------------------------------
import type { Proof } from '@/api/types'
import { formatEuro, formatTime } from '@/utils/format'

interface Props {
  proof: Proof
  /** Variante compacte (« dernière preuve connue » quand il n'y a pas d'incident). */
  compact?: boolean
}

export default function ProofCard({ proof, compact = false }: Props) {
  const ok = proof.status === 'completed' && proof.consistency === 'ok'
  const bg = ok ? 'bg-success border-success' : 'bg-danger border-danger'
  return (
    <div className={`card flex items-center gap-[1.2vw] px-[1.2vw] py-[1vh] text-white animate-card-in ${bg} ${compact ? '' : 'shadow-lg'}`}>
      <div className="flex shrink-0 flex-col items-center leading-none">
        <span className={`${compact ? 't-tile' : 't-giant'} font-extrabold tracking-tight`}>{formatEuro(proof.amount_cents)}</span>
      </div>
      <div className="min-w-0 flex-1">
        <div className={`${compact ? 't-body' : 't-title'} truncate font-extrabold uppercase tracking-wide`}>
          {ok ? 'Nouvelle transaction réussie' : 'Transaction de preuve en échec'}
        </div>
        <div className="t-body truncate font-semibold tabular-nums">
          {proof.reference} · {formatTime(proof.created_at)}
        </div>
        {!compact && (
          <div className="t-small truncate text-white/85">
            {proof.sender} → {proof.recipient} · solde {formatEuro(proof.balance_before_cents)} → {formatEuro(proof.balance_after_cents)} · cohérence{' '}
            {proof.consistency === 'ok' ? 'OK' : 'KO'}
          </div>
        )}
      </div>
    </div>
  )
}
