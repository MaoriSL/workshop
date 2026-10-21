// ---------------------------------------------------------------------------
// Types du contrat d'API du moteur de remédiation (contrat figé, voir
// docs/api). Le dashboard est en LECTURE SEULE : il ne fait que lire ces objets.
// ---------------------------------------------------------------------------

/** État global de la plateforme, tel que décidé par le moteur de remédiation. */
export type GlobalState = 'NORMAL' | 'ANOMALIE' | 'REMEDIATION' | 'RETABLI' | 'ECHEC' | 'SURETE'

/** Noms des cinq services supervisés. */
export type ServiceName = 'front' | 'auth' | 'api' | 'db' | 'gateway'

/** Mesures d'un service (null = mesure indisponible). */
export interface ServiceStatus {
  name: ServiceName
  up: boolean
  latency_p95_ms: number | null
  error_rate_5xx: number | null // taux entre 0 et 1
  requests_per_s: number | null
}

/** État du détecteur d'anomalies (ML). */
export interface DetectorStatus {
  available: boolean
  state: 'NORMAL' | 'SUSPECT' | 'ANOMALIE' | 'RETABLISSEMENT' | null
  score: number | null
  threshold: number | null
  suspected_service: string | null
  incident_type: string | null
}

/** Types d'incident reconnus par le moteur. */
export type IncidentType =
  | 'indisponibilite'
  | 'surcharge'
  | 'bruteforce'
  | 'db_lente'
  | 'compromission'
  | 'incoherence'
  | 'inconnu'

/** Étapes possibles de la chronologie d'un incident. */
export type TimelineStep =
  | 'detected'
  | 'received'
  | 'decided'
  | 'action_started'
  | 'action_done'
  | 'verification_started'
  | 'healthy'
  | 'proof_transaction'
  | 'consistency_ok'
  | 'recovered'
  | 'escalated'
  | 'failed'
  | 'detector_normal'

export interface TimelineEntry {
  t: string // ISO
  elapsed_s: number // secondes écoulées depuis la détection
  step: TimelineStep
  label: string // phrase française courte
  details: Record<string, unknown>
}

/** Action planifiée à un niveau d'escalade (1 → 3). */
export interface PlanLevel {
  level: 1 | 2 | 3
  action: string
  params: Record<string, unknown>
}

/** Preuve de reprise : une NOUVELLE transaction qui réussit après l'incident. */
export interface Proof {
  transaction_id: string
  reference: string // ex. "PP-2026-000042"
  amount_cents: number
  status: string // "completed"
  created_at: string
  sender: string
  recipient: string
  balance_before_cents: number
  balance_after_cents: number
  consistency: 'ok' | 'ko'
}

export type IncidentState =
  | 'RECU'
  | 'DECIDE'
  | 'ACTION_EN_COURS'
  | 'VERIFICATION'
  | 'RETABLI'
  | 'ESCALADE'
  | 'ECHEC'

export interface Incident {
  incident_id: string
  state: IncidentState
  incident_type: IncidentType
  suspected_service: string
  detected_at: string
  received_at: string
  resolved_at: string | null
  recovery_seconds: number | null // durée totale détection → preuve
  plan: PlanLevel[]
  current_level: number
  timeline: TimelineEntry[]
  proof: Proof | null
}

/** Point de la courbe du score d'anomalie (10 dernières minutes, pas de 5 s). */
export interface ScorePoint {
  t: string
  score: number
  threshold: number
}

/** Repère vertical sur la courbe (détection, action, rétabli, échec). */
export interface Marker {
  t: string
  kind: 'detected' | 'action' | 'recovered' | 'failed'
  label: string
}

/** Objet State complet : GET {base}/state et événements SSE `state`. */
export interface State {
  global_state: GlobalState
  updated_at: string
  services: ServiceStatus[]
  detector: DetectorStatus
  current_incident: Incident | null
  last_incident: Incident | null
  last_proof: Proof | null
  circuit_breaker: { open: boolean; count: number; limit: number; window_minutes: number }
  dry_run: boolean
  score_history: ScorePoint[]
  markers: Marker[]
}

/** Qualité de la liaison avec le moteur, affichée dans le bandeau. */
export type ConnectionStatus = 'live' | 'polling' | 'offline'
