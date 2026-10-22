// ---------------------------------------------------------------------------
// Pièce maîtresse : la chronologie de l'incident en cours (ou du dernier).
// En-tête : type, service suspecté, plan d'action avec le niveau courant.
// Liste : étapes « T+12 s », icône, libellé ; apparition animée ; la preuve
// (proof_transaction) est mise en évidence par une grande carte verte.
// S'il n'y a pas d'incident : message calme + dernière preuve connue.
// ---------------------------------------------------------------------------
import type { Incident, Proof, TimelineEntry } from '@/api/types'
import { actionLabel, formatElapsed, incidentTypeLabel, stepIcon } from '@/utils/format'
import ProofCard from './ProofCard'

interface Props {
  incident: Incident | null
  lastProof: Proof | null
}

/** Couleur d'une étape selon sa nature. */
function tone(entry: TimelineEntry): { ring: string; text: string } {
  switch (entry.step) {
    case 'detected':
      return { ring: 'bg-danger', text: 'text-ink' }
    case 'failed':
      return { ring: 'bg-danger', text: 'text-red-300' }
    case 'escalated':
      return { ring: 'bg-warning', text: 'text-amber-300' }
    case 'action_started':
    case 'action_done':
      return { ring: 'bg-warning', text: 'text-ink' }
    case 'healthy':
    case 'consistency_ok':
    case 'recovered':
    case 'detector_normal':
      return { ring: 'bg-success', text: 'text-ink' }
    default:
      return { ring: 'bg-accent', text: 'text-ink' }
  }
}

function Row({ entry }: { entry: TimelineEntry }) {
  const { ring, text } = tone(entry)
  return (
    <li className="flex items-center gap-[1vw] py-[0.45vh] animate-row-in">
      <span className="t-small w-[5.5em] shrink-0 text-right font-semibold tabular-nums text-muted">{formatElapsed(entry.elapsed_s)}</span>
      <span className={`t-small flex h-[1.9em] w-[1.9em] shrink-0 items-center justify-center rounded-full font-extrabold text-white ${ring}`}>
        {stepIcon(entry.step)}
      </span>
      <span className={`t-body min-w-0 truncate font-medium ${text}`}>{entry.label}</span>
    </li>
  )
}

export default function IncidentTimeline({ incident, lastProof }: Props) {
  // --- Aucun incident : écran calme ----------------------------------------
  if (!incident) {
    return (
      <div className="flex h-full min-h-0 flex-col items-center justify-center gap-[3vh] px-[2vw]">
        <div className="text-center">
          <div className="t-hero font-extrabold text-success">Aucun incident</div>
          <div className="t-title mt-[1vh] text-muted">Surveillance active — le modèle apprend le comportement normal</div>
        </div>
        {lastProof && (
          <div className="w-full max-w-[60ch]">
            <div className="t-small mb-[0.6vh] font-semibold uppercase tracking-widest text-muted">Dernière preuve de reprise connue</div>
            <ProofCard proof={lastProof} compact />
          </div>
        )}
      </div>
    )
  }

  const ongoing = !['RETABLI', 'ECHEC', 'ESCALADE'].includes(incident.state)
  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* En-tête : type, service, plan d'action */}
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-x-[2vw] gap-y-1 border-b border-line pb-[0.8vh]">
        <div className="min-w-0">
          <div className="t-title truncate font-extrabold">
            {incidentTypeLabel(incident.incident_type)} <span className="text-muted">sur</span>{' '}
            <span className="text-sky">{incident.suspected_service}</span>
            {ongoing && <span className="t-small ml-3 rounded-full bg-warning/20 px-2 py-0.5 font-bold uppercase text-amber-300">en cours</span>}
          </div>
          <div className="t-small text-muted">{incident.incident_id}</div>
        </div>
        <ol className="flex shrink-0 items-center gap-[0.6vw]">
          {incident.plan.map((p) => {
            const current = p.level === incident.current_level
            return (
              <li
                key={p.level}
                className={`t-small rounded-lg border px-2 py-1 font-semibold ${
                  current ? 'border-accent bg-accent text-white' : 'border-line bg-panel-2 text-muted'
                }`}
              >
                N{p.level} · {actionLabel(p.action)}
              </li>
            )
          })}
        </ol>
      </div>

      {/* Liste des étapes : les événements récents restent en bas et les étapes
          précédentes restent accessibles par défilement vertical. */}
      <ol className="fade-top flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain pt-[0.6vh]">
        {incident.timeline.map((entry, i) =>
          entry.step === 'proof_transaction' && incident.proof ? (
            <li key={`${entry.step}-${i}`} className="py-[0.6vh]">
              <ProofCard proof={incident.proof} />
            </li>
          ) : (
            <Row key={`${entry.step}-${i}`} entry={entry} />
          ),
        )}
      </ol>
    </div>
  )
}
