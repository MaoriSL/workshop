// ---------------------------------------------------------------------------
// Bandeau d'état global (haut de l'écran) : très gros texte coloré selon
// global_state, durée de reprise en géant quand le service est rétabli,
// heure courante et indicateur de liaison (temps réel / polling / hors ligne).
// ---------------------------------------------------------------------------
import { useEffect, useState } from 'react'
import type { ConnectionStatus, State } from '@/api/types'
import { actionLabel, formatDuration, formatTime, incidentTypeLabel } from '@/utils/format'

interface Props {
  state: State | null
  status: ConnectionStatus
  isMock: boolean
}

/** Couleur de fond et textes du bandeau pour chaque état global. */
function describe(state: State | null): { bg: string; title: string; subtitle: string } {
  if (!state) return { bg: '#1b3a8b', title: 'CONNEXION AU MOTEUR…', subtitle: 'En attente du premier état' }
  const inc = state.current_incident ?? state.last_incident
  const type = incidentTypeLabel(inc?.incident_type ?? state.detector.incident_type)
  const service = inc?.suspected_service ?? state.detector.suspected_service ?? '?'
  switch (state.global_state) {
    case 'NORMAL':
      return { bg: '#15803d', title: 'PLATEFORME NORMALE', subtitle: 'Surveillance active — détection par apprentissage automatique' }
    case 'ANOMALIE':
      return { bg: '#dc2626', title: `ANOMALIE DÉTECTÉE — ${type} sur ${service}`, subtitle: 'Le moteur de remédiation prend la main' }
    case 'REMEDIATION': {
      const level = inc?.current_level ?? 1
      const action = inc?.plan.find((p) => p.level === level)?.action ?? 'action en cours'
      return {
        bg: '#d97706',
        title: `REMÉDIATION EN COURS — ${actionLabel(action)} (niveau ${level}/3)`,
        subtitle: `${type} sur ${service} — aucune intervention humaine`,
      }
    }
    case 'RETABLI': {
      const ref = inc?.proof?.reference ?? state.last_proof?.reference
      return {
        bg: '#16a34a',
        title: 'SERVICE RÉTABLI',
        subtitle: ref ? `preuve : transaction ${ref} réussie` : 'preuve : transaction de contrôle réussie',
      }
    }
    case 'ECHEC':
      return { bg: '#7f1d1d', title: 'REMÉDIATION EN ÉCHEC — intervention requise', subtitle: `${type} sur ${service}` }
    case 'SURETE':
      return {
        bg: '#6d28d9',
        title: 'DISJONCTEUR : mode sûreté',
        subtitle: `${state.circuit_breaker.count} remédiations en ${state.circuit_breaker.window_minutes} min (limite ${state.circuit_breaker.limit}) — actions automatiques suspendues`,
      }
  }
}

/** Petit indicateur de liaison avec le moteur. */
function ConnectionBadge({ status }: { status: ConnectionStatus }) {
  const map: Record<ConnectionStatus, { label: string; color: string; pulse: boolean }> = {
    live: { label: 'temps réel', color: '#4ade80', pulse: true },
    polling: { label: 'polling', color: '#fbbf24', pulse: true },
    offline: { label: 'hors ligne', color: '#f87171', pulse: false },
  }
  const { label, color, pulse } = map[status]
  return (
    <span className="t-small inline-flex items-center gap-2 rounded-full bg-black/25 px-3 py-1 font-semibold uppercase tracking-wide">
      <span
        className={`inline-block h-[0.7em] w-[0.7em] rounded-full ${pulse ? 'animate-pulse-soft' : ''}`}
        style={{ backgroundColor: color }}
      />
      {label}
    </span>
  )
}

export default function GlobalBanner({ state, status, isMock }: Props) {
  // Horloge : mise à jour chaque seconde.
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  const { bg, title, subtitle } = describe(state)
  const recovered = state?.global_state === 'RETABLI'
  const recoverySeconds = state?.current_incident?.recovery_seconds ?? state?.last_incident?.recovery_seconds ?? null

  return (
    <header
      className="flex h-full items-stretch justify-between gap-6 rounded-2xl px-[2vw] py-[1.2vh] text-white shadow-lg transition-colors duration-300 ease-in-out"
      style={{ backgroundColor: bg }}
    >
      {/* Texte d'état : le message principal, lisible à distance */}
      <div className="flex min-w-0 flex-1 flex-col justify-center gap-[0.8vh]">
        <div className="t-small flex items-center gap-3 font-semibold uppercase tracking-widest text-white/80">
          <span>Poupal · Supervision</span>
          {state?.dry_run && <span className="rounded bg-black/30 px-2 py-0.5">dry-run</span>}
          {isMock && <span className="rounded bg-black/30 px-2 py-0.5">démo</span>}
        </div>
        {/* Deux lignes maximum : les messages longs (remédiation) restent entiers */}
        <h1 className="t-hero line-clamp-2 font-extrabold tracking-tight" title={title}>
          {title}
        </h1>
        <p className="t-title truncate font-medium text-white/90">{subtitle}</p>
      </div>

      {/* Durée totale de reprise, en géant, uniquement quand le service est rétabli */}
      {recovered && recoverySeconds !== null && (
        <div className="flex shrink-0 flex-col items-center justify-center animate-card-in">
          <span className="t-giant font-extrabold tracking-tight">{formatDuration(recoverySeconds)}</span>
          <span className="t-small font-semibold uppercase tracking-widest text-white/85">détection → preuve</span>
        </div>
      )}

      {/* Heure et liaison */}
      <div className="flex shrink-0 flex-col items-end justify-center gap-[0.8vh]">
        <span className="t-hero font-bold tabular-nums">{formatTime(now)}</span>
        <ConnectionBadge status={status} />
        {state && (
          <span className="t-small text-white/75">
            disjoncteur {state.circuit_breaker.count}/{state.circuit_breaker.limit} · {state.circuit_breaker.window_minutes} min
          </span>
        )}
      </div>
    </header>
  )
}
