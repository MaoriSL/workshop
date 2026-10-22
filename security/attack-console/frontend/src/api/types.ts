// ---------------------------------------------------------------------------
// Types du contrat d'API de l'orchestrateur d'attaques (figé par le brief).
// La console est un simple pilote : elle LIT l'état et déclenche des actions
// bornées (Lancer / Stopper / Arrêt d'urgence / Export). Aucune commande libre.
// ---------------------------------------------------------------------------

/** Qualité de la liaison temps réel avec l'orchestrateur. */
export type ConnectionStatus = 'live' | 'polling' | 'offline'

/** Identifiants des scénarios proposés par l'orchestrateur. */
export type ScenarioId = 'dos' | 'bruteforce' | 'injection' | 'exfiltration' | 'combo'

/** Type d'incident que le scénario doit provoquer (côté détection). */
export type IncidentType = 'surcharge' | 'bruteforce' | 'injection' | 'exfiltration' | 'combo'

/** État d'un run (instance d'exécution d'un scénario). */
export type RunStatus = 'running' | 'finished' | 'stopped' | 'error'

/**
 * Champ de paramètre BORNÉ décrivant une entrée autorisée pour un scénario.
 * L'interface n'affiche que des sliders / listes déroulantes à partir de ce
 * schéma : il n'existe aucun champ de saisie de commande libre.
 */
export interface ParamField {
  key: string
  label: string
  type: 'int' | 'float' | 'select'
  min?: number
  max?: number
  step?: number
  default: number | string
  options?: { value: string; label: string }[]
  unit?: string
}

/** Description d'un scénario d'attaque. */
export interface Scenario {
  id: ScenarioId
  name: string
  description: string
  incident_type: IncidentType
  /** Phrase courte : la défense attendue côté plateforme (pédagogie jury). */
  defense: string
  params_schema: ParamField[]
}

/** Instance d'exécution d'un scénario (en cours ou récente). */
export interface Run {
  run_id: string
  scenario_id: ScenarioId
  status: RunStatus
  params: Record<string, number | string>
  started_at: string
  ended_at: string | null
  elapsed_s: number
  requests_sent: number
  /** Répartition des réponses par code HTTP, ex. { "200": 120, "429": 40 }. */
  responses_by_status: Record<string, number>
  blocked: number
  rate_per_s: number
  error?: string
}

/** Entrée du journal horodaté des attaques lancées / arrêtées. */
export interface JournalEntry {
  run_id: string
  scenario_id: ScenarioId
  type: string
  status: RunStatus
  started_at: string
  ended_at: string | null
  duration_s: number
  intensity: number | null
  requests_sent: number
  blocked: number
  result: string
}

/** État global renvoyé par GET /state et poussé par le flux SSE. */
export interface State {
  /** Cible des attaques (hôte/plage) affichée dans l'en-tête. */
  target: string
  /** true = cible dans le périmètre autorisé ; false = tout est verrouillé. */
  in_lab: boolean
  /** Explication affichée quand in_lab=false. */
  lab_reason: string
  updated_at: string
  scenarios: Scenario[]
  /** Runs en cours + récents, le plus récent d'abord. */
  runs: Run[]
  /** true après un Arrêt d'urgence : tous les scénarios sont à l'arrêt. */
  emergency_stopped: boolean
}

export interface TargetUpdate {
  target: string
  in_lab: boolean
  lab_reason: string
}
