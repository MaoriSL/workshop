// ---------------------------------------------------------------------------
// En-tête permanent de la console :
//  - titre et bandeau fictif TOUJOURS visibles ;
//  - cible courante avec pastille verte (périmètre OK) / rouge (hors zone) ;
//  - horloge et indicateur de liaison (temps réel / polling / hors ligne) ;
//  - GROS bouton Arrêt d'urgence (rouge, en haut à droite).
// ---------------------------------------------------------------------------
import { useEffect, useState } from 'react'
import type { ConnectionStatus, State } from '@/api/types'
import { formatTime } from '@/utils/format'

interface Props {
  state: State | null
  status: ConnectionStatus
  isMock: boolean
  onStopAll: () => void
}

/** Indicateur de liaison avec l'orchestrateur. */
function ConnectionBadge({ status }: { status: ConnectionStatus }) {
  const map: Record<ConnectionStatus, { label: string; color: string; pulse: boolean }> = {
    live: { label: 'temps réel', color: '#4ade80', pulse: true },
    polling: { label: 'polling', color: '#fbbf24', pulse: true },
    offline: { label: 'hors ligne', color: '#f87171', pulse: false },
  }
  const { label, color, pulse } = map[status]
  return (
    <span className="t-small inline-flex items-center gap-2 rounded-full bg-black/30 px-3 py-1 font-semibold uppercase tracking-wide">
      <span
        className={`inline-block h-[0.7em] w-[0.7em] rounded-full ${pulse ? 'animate-pulse-soft' : ''}`}
        style={{ backgroundColor: color }}
      />
      {label}
    </span>
  )
}

export default function TopBar({ state, status, isMock, onStopAll }: Props) {
  // Horloge : mise à jour chaque seconde.
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  const inLab = state?.in_lab ?? true
  const target = state?.target ?? '—'

  return (
    <header className="flex shrink-0 flex-col gap-[1vh]">
      {/* Ligne 1 : titre + horloge/liaison + arrêt d'urgence */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <img src="./favicon.svg" alt="" className="h-[4vh] w-[4vh] min-h-7 min-w-7" aria-hidden="true" />
          <div className="min-w-0">
            <h1 className="t-hero truncate font-extrabold tracking-tight">
              Poupal — Console d’attaque <span className="text-muted">(laboratoire)</span>
            </h1>
            <p className="t-small font-semibold uppercase tracking-widest text-muted">
              Pilote de résilience · déclenche la chaîne détection → remédiation
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-4">
          <div className="flex flex-col items-end gap-1">
            <span className="t-tile font-bold tabular-nums">{formatTime(now)}</span>
            <div className="flex items-center gap-2">
              {isMock && (
                <span className="t-small rounded-full bg-violet/30 px-3 py-1 font-semibold uppercase tracking-wide text-ink">
                  démo
                </span>
              )}
              <ConnectionBadge status={status} />
            </div>
          </div>

          {/* Arrêt d'urgence global : toujours visible, toujours actif. */}
          <button
            type="button"
            onClick={onStopAll}
            className="flex flex-col items-center justify-center rounded-2xl border-2 border-danger bg-danger px-[1.6vw] py-[1.1vh] font-extrabold uppercase tracking-wide text-white shadow-lg transition hover:brightness-110 focus-visible:brightness-110 active:scale-95"
            title="Arrête immédiatement toutes les attaques (POST /stop-all)"
          >
            <span className="t-title leading-none">■ Arrêt d’urgence</span>
            <span className="t-mini font-semibold tracking-widest text-white/85">stoppe toutes les attaques</span>
          </button>
        </div>
      </div>

      {/* Ligne 2 : bandeau fictif permanent + cible + état d'arrêt d'urgence */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-panel px-[1.2vw] py-[0.9vh]">
        <span className="t-body inline-flex items-center gap-2 font-semibold text-warning">
          <span aria-hidden="true">⚠</span>
          Laboratoire fictif — attaques limitées à notre plateforme.
        </span>

        <div className="flex items-center gap-3">
          {state?.emergency_stopped && (
            <span className="t-small animate-pulse-soft rounded-full bg-danger/20 px-3 py-1 font-bold uppercase tracking-wide text-danger">
              arrêt d’urgence actif
            </span>
          )}
          <span className="t-body inline-flex items-center gap-2 rounded-lg bg-night/60 px-3 py-1 font-medium">
            <span className="t-small uppercase tracking-widest text-muted">cible</span>
            <span className="font-semibold tabular-nums">{target}</span>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 t-small font-bold uppercase tracking-wide ${
                inLab ? 'bg-success/20 text-success' : 'bg-danger/20 text-danger'
              }`}
            >
              <span
                className="inline-block h-[0.7em] w-[0.7em] rounded-full"
                style={{ backgroundColor: inLab ? '#16a34a' : '#dc2626' }}
              />
              {inLab ? 'périmètre OK' : 'hors zone'}
            </span>
          </span>
        </div>
      </div>
    </header>
  )
}
