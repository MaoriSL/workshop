// ---------------------------------------------------------------------------
// Historique des incidents précédents (liste compacte, lecture seule) :
// heure, type, service, durée, résultat.
// ---------------------------------------------------------------------------
import type { Incident } from '@/api/types'
import { formatDuration, formatShortTime, incidentStateLabel, incidentTypeLabel } from '@/utils/format'

/** Couleur du résultat final. */
function resultClass(state: Incident['state']): string {
  if (state === 'RETABLI') return 'bg-success/20 text-green-300'
  if (state === 'ECHEC') return 'bg-danger/25 text-red-300'
  if (state === 'ESCALADE') return 'bg-warning/20 text-amber-300'
  return 'bg-accent/20 text-sky'
}

export default function HistoryPanel({ incidents }: { incidents: Incident[] }) {
  if (incidents.length === 0) {
    return <div className="t-title flex h-full items-center justify-center text-muted">Aucun incident enregistré</div>
  }
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="t-small grid shrink-0 grid-cols-[6em_1fr_7em_6em_8em] gap-x-3 border-b border-line pb-[0.6vh] font-semibold uppercase tracking-wider text-muted">
        <span>Heure</span>
        <span>Type</span>
        <span>Service</span>
        <span>Durée</span>
        <span>Résultat</span>
      </div>
      <ol className="min-h-0 flex-1 overflow-hidden">
        {incidents.map((inc) => (
          <li
            key={inc.incident_id}
            className="t-body grid grid-cols-[6em_1fr_7em_6em_8em] items-center gap-x-3 border-b border-line/60 py-[0.7vh] tabular-nums"
          >
            <span className="font-semibold">{formatShortTime(inc.detected_at)}</span>
            <span className="truncate">{incidentTypeLabel(inc.incident_type)}</span>
            <span className="truncate text-sky">{inc.suspected_service}</span>
            <span>{formatDuration(inc.recovery_seconds)}</span>
            <span className={`t-small w-fit rounded-full px-2 py-0.5 font-bold ${resultClass(inc.state)}`}>{incidentStateLabel(inc.state)}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}
