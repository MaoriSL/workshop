// ---------------------------------------------------------------------------
// Carte d'un scénario d'attaque. Pilote STRICTEMENT borné :
//  - les seuls contrôles sont des sliders / listes déroulantes (params_schema),
//    un bouton LANCER et un bouton STOPPER. Aucune saisie de commande libre ;
//  - affiche en direct l'état du run courant (statut, T+, requêtes, réponses
//    par code HTTP, bloquées, débit) ;
//  - liseré orange animé (sobre) quand une attaque est en cours.
// ---------------------------------------------------------------------------
import { useState } from 'react'
import type { ParamField, Run, Scenario } from '@/api/types'
import {
  formatCount,
  formatElapsed,
  formatRps,
  incidentTypeLabel,
  runStatusInfo,
  statusColor,
} from '@/utils/format'

interface Props {
  scenario: Scenario
  run: Run | undefined // dernier run de ce scénario (en cours ou récent)
  inLab: boolean
  onStart: (id: string, params: Record<string, number | string>) => void
  onStop: (id: string) => void
}

/** Valeurs par défaut des paramètres à partir du schéma. */
function defaultsFrom(schema: ParamField[]): Record<string, number | string> {
  const out: Record<string, number | string> = {}
  for (const f of schema) out[f.key] = f.default
  return out
}

/** Un contrôle borné (slider pour int/float, liste déroulante pour select). */
function ParamControl({
  field,
  value,
  disabled,
  onChange,
}: {
  field: ParamField
  value: number | string
  disabled: boolean
  onChange: (v: number | string) => void
}) {
  if (field.type === 'select') {
    return (
      <label className="flex flex-col gap-1">
        <span className="t-small font-semibold text-muted">{field.label}</span>
        <select
          disabled={disabled}
          value={String(value)}
          onChange={(e) => onChange(e.target.value)}
          className="t-body rounded-lg border border-line bg-night px-2 py-1 font-medium text-ink disabled:opacity-50"
        >
          {field.options?.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
    )
  }
  // int / float : slider borné + valeur affichée
  return (
    <label className="flex flex-col gap-1">
      <span className="t-small flex items-center justify-between font-semibold text-muted">
        <span>{field.label}</span>
        <span className="tabular-nums text-ink">
          {value}
          {field.unit ? ` ${field.unit}` : ''}
        </span>
      </span>
      <input
        type="range"
        disabled={disabled}
        min={field.min}
        max={field.max}
        step={field.step ?? (field.type === 'float' ? 0.5 : 1)}
        value={Number(value)}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-accent disabled:opacity-50"
      />
    </label>
  )
}

/** Ventilation des réponses par code HTTP (puces colorées). */
function StatusChips({ run }: { run: Run }) {
  const codes = Object.keys(run.responses_by_status).sort()
  if (codes.length === 0) return <span className="t-small text-muted">—</span>
  return (
    <div className="flex flex-wrap gap-1.5">
      {codes.map((code) => (
        <span
          key={code}
          className="t-small inline-flex items-center gap-1 rounded-md bg-night px-2 py-0.5 font-semibold tabular-nums"
          style={{ color: statusColor(code) }}
        >
          <span className="h-[0.55em] w-[0.55em] rounded-full" style={{ backgroundColor: statusColor(code) }} />
          {code}
          <span className="text-ink">{formatCount(run.responses_by_status[code] ?? 0)}</span>
        </span>
      ))}
    </div>
  )
}

export default function ScenarioCard({ scenario, run, inLab, onStart, onStop }: Props) {
  const [params, setParams] = useState<Record<string, number | string>>(() => defaultsFrom(scenario.params_schema))
  const running = run?.status === 'running'
  const canLaunch = inLab && !running
  const status = run ? runStatusInfo(run.status) : null

  return (
    <article
      className={`card flex flex-col gap-[1vh] p-[1.1vw] ${running ? 'animate-run-glow border-warning' : ''}`}
    >
      {/* En-tête de carte : nom + badge type d'incident */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="t-title font-bold">{scenario.name}</h2>
          <p className="t-small text-muted">{scenario.description}</p>
        </div>
        <span className="t-small shrink-0 rounded-full bg-accent/20 px-2.5 py-1 font-bold uppercase tracking-wide text-sky">
          {incidentTypeLabel(scenario.incident_type)}
        </span>
      </div>

      {/* Défense attendue (pédagogie jury) */}
      <p className="t-small rounded-lg bg-night/60 px-2.5 py-1.5 text-muted">
        <span className="font-semibold text-success">Défense : </span>
        {scenario.defense}
      </p>

      {/* Paramètres bornés */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-2">
        {scenario.params_schema.map((field) => (
          <div key={field.key} className={field.type === 'select' ? 'col-span-2' : ''}>
            <ParamControl
              field={field}
              value={params[field.key] ?? field.default}
              disabled={running}
              onChange={(v) => setParams((p) => ({ ...p, [field.key]: v }))}
            />
          </div>
        ))}
      </div>

      {/* État du run courant */}
      {run && (
        <div className="flex flex-col gap-1.5 rounded-lg border border-line bg-night/40 p-2">
          <div className="flex items-center justify-between">
            <span className="t-small inline-flex items-center gap-1.5 font-bold uppercase tracking-wide" style={{ color: status?.color }}>
              <span className="h-[0.6em] w-[0.6em] rounded-full" style={{ backgroundColor: status?.color }} />
              {status?.label}
            </span>
            <span className="t-small tabular-nums text-muted">{formatElapsed(run.elapsed_s)}</span>
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            <div>
              <div className="t-body font-bold tabular-nums">{formatCount(run.requests_sent)}</div>
              <div className="t-mini uppercase tracking-wide text-muted">requêtes</div>
            </div>
            <div>
              <div className="t-body font-bold tabular-nums text-sky">{formatCount(run.blocked)}</div>
              <div className="t-mini uppercase tracking-wide text-muted">bloquées</div>
            </div>
            <div>
              <div className="t-body font-bold tabular-nums">{formatRps(run.rate_per_s)}</div>
              <div className="t-mini uppercase tracking-wide text-muted">débit</div>
            </div>
          </div>
          <StatusChips run={run} />
          {run.error && <p className="t-small font-semibold text-danger">Erreur : {run.error}</p>}
        </div>
      )}

      {/* Actions : LANCER / STOPPER */}
      <div className="mt-auto flex gap-2 pt-1">
        <button
          type="button"
          disabled={!canLaunch}
          onClick={() => onStart(scenario.id, params)}
          className="t-body flex-1 rounded-lg bg-accent px-3 py-2 font-bold uppercase tracking-wide text-white transition hover:brightness-110 active:scale-95 disabled:cursor-not-allowed disabled:bg-line disabled:text-muted"
          title={!inLab ? 'Cible hors périmètre' : running ? 'Un run est déjà en cours' : 'Lancer le scénario'}
        >
          ▶ Lancer
        </button>
        <button
          type="button"
          disabled={!running}
          onClick={() => onStop(scenario.id)}
          className="t-body flex-1 rounded-lg border border-danger px-3 py-2 font-bold uppercase tracking-wide text-danger transition hover:bg-danger/15 active:scale-95 disabled:cursor-not-allowed disabled:border-line disabled:text-muted"
          title={running ? 'Arrêter le run en cours' : 'Aucun run en cours'}
        >
          ■ Stopper
        </button>
      </div>
    </article>
  )
}
