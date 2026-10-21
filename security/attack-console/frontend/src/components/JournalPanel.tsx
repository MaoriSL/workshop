// ---------------------------------------------------------------------------
// Panneau JOURNAL : liste horodatée des attaques lancées / arrêtées
// (type, intensité, durée, résultat) + bouton d'export CSV.
// ---------------------------------------------------------------------------
import type { JournalEntry } from '@/api/types'
import { formatCount, formatDuration, formatShortTime, runStatusInfo, scenarioLabel } from '@/utils/format'

interface Props {
  journal: JournalEntry[]
  onExport: () => void
}

/** Une ligne du journal. */
function JournalRow({ entry }: { entry: JournalEntry }) {
  const status = runStatusInfo(entry.status)
  const when = entry.ended_at ?? entry.started_at
  return (
    <li className="animate-row-in flex flex-col gap-1 border-b border-line/60 py-2 last:border-0">
      <div className="flex items-center justify-between gap-2">
        <span className="t-body truncate font-semibold">{scenarioLabel(entry.scenario_id)}</span>
        <span className="t-small shrink-0 tabular-nums text-muted">{formatShortTime(when)}</span>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
        <span className="t-small inline-flex items-center gap-1.5 font-bold uppercase tracking-wide" style={{ color: status.color }}>
          <span className="h-[0.55em] w-[0.55em] rounded-full" style={{ backgroundColor: status.color }} />
          {status.label}
        </span>
        {entry.intensity !== null && (
          <span className="t-small tabular-nums text-muted">intensité {entry.intensity}</span>
        )}
        <span className="t-small tabular-nums text-muted">{formatDuration(entry.duration_s)}</span>
        <span className="t-small tabular-nums text-muted">
          {formatCount(entry.requests_sent)} req · {formatCount(entry.blocked)} bloquées
        </span>
      </div>
      <p className="t-small text-muted">{entry.result}</p>
    </li>
  )
}

export default function JournalPanel({ journal, onExport }: Props) {
  return (
    <section className="card flex h-full min-h-0 flex-col p-[1.1vw]">
      <div className="flex shrink-0 items-center justify-between gap-2 pb-2">
        <h2 className="t-title font-bold">Journal des attaques</h2>
        <button
          type="button"
          onClick={onExport}
          disabled={journal.length === 0}
          className="t-small rounded-lg border border-line px-3 py-1.5 font-bold uppercase tracking-wide text-ink transition hover:bg-panel-2 active:scale-95 disabled:cursor-not-allowed disabled:text-muted"
          title="Télécharge le journal au format CSV"
        >
          ⬇ Exporter CSV
        </button>
      </div>
      {/* Liste défilante : aucune requête ne fait déborder la page. */}
      <ol className="fade-top min-h-0 flex-1 overflow-y-auto pr-1">
        {journal.length === 0 ? (
          <li className="t-body py-6 text-center text-muted">Aucune attaque enregistrée.</li>
        ) : (
          journal.map((entry) => <JournalRow key={entry.run_id} entry={entry} />)
        )}
      </ol>
    </section>
  )
}
