// ---------------------------------------------------------------------------
// Données de démonstration (VITE_USE_MOCK=true) : rejoue en boucle un incident
// complet NORMAL → ANOMALIE → REMEDIATION → RETABLI (avec preuve), sans moteur.
// Mêmes signatures que client.ts pour que le reste du code ne change pas.
// Aucune donnée réelle : tout est inventé.
// ---------------------------------------------------------------------------
import type {
  Incident,
  IncidentState,
  Marker,
  Proof,
  ScorePoint,
  ServiceStatus,
  State,
  TimelineEntry,
  TimelineStep,
} from './types'
import type { SubscribeCallbacks } from './client'

// --- Scénario (en secondes, relatif à l'instant de détection T+0) -----------
const CYCLE_S = 95 // durée d'une boucle complète
const CALM_BEFORE_S = 20 // calme en début de boucle avant la détection
const THRESHOLD = 0.6 // seuil du détecteur
const HISTORY_STEP_S = 5 // pas de la courbe du score
const HISTORY_POINTS = 120 // 10 minutes

/** Étapes de la chronologie, dans l'ordre, avec leur instant d'apparition. */
const STEPS: { elapsed: number; step: TimelineStep; label: string }[] = [
  { elapsed: 0, step: 'detected', label: 'Anomalie détectée par le modèle : latence et erreurs anormales sur api' },
  { elapsed: 1, step: 'received', label: 'Alerte reçue par le moteur de remédiation' },
  { elapsed: 3, step: 'decided', label: 'Plan décidé : niveau 1 — redémarrage du conteneur api' },
  { elapsed: 5, step: 'action_started', label: 'Redémarrage du conteneur api lancé' },
  { elapsed: 14, step: 'action_done', label: 'Conteneur api redémarré, image saine' },
  { elapsed: 15, step: 'verification_started', label: 'Vérification de la reprise (sonde + transaction de preuve)' },
  { elapsed: 21, step: 'healthy', label: 'api répond : /healthz OK, latence normale' },
  { elapsed: 30, step: 'proof_transaction', label: 'Nouvelle transaction de preuve réussie' },
  { elapsed: 33, step: 'consistency_ok', label: 'Soldes cohérents avant / après' },
  { elapsed: 34, step: 'recovered', label: 'Service rétabli — aucune intervention humaine' },
  { elapsed: 46, step: 'detector_normal', label: 'Détecteur revenu à la normale' },
]
const RECOVERED_AT = 34 // elapsed de l'étape "recovered"
const NORMAL_AGAIN_AT = 70 // retour au bandeau NORMAL

/** Score d'anomalie simulé en fonction du temps écoulé depuis la détection. */
function scoreAt(elapsed: number, noiseSeed: number): number {
  const noise = Math.sin(noiseSeed * 1.7) * 0.03 + Math.cos(noiseSeed * 0.9) * 0.02
  let base = 0.18
  if (elapsed >= -12 && elapsed < 0) base = 0.18 + (0.82 - 0.18) * ((elapsed + 12) / 12) // montée
  else if (elapsed >= 0 && elapsed < 14) base = 0.86 // plateau pendant l'anomalie
  else if (elapsed >= 14 && elapsed < 46) base = 0.18 + 0.68 * Math.exp(-(elapsed - 14) / 7) // décroissance
  return Math.max(0.02, Math.min(0.99, base + noise))
}

/** Mesures des cinq services selon la phase de l'incident. */
function servicesAt(elapsed: number, seed: number): ServiceStatus[] {
  const j = (k: number) => 1 + Math.sin(seed * 0.8 + k) * 0.08 // petite variation ±8 %
  const apiAnomaly = elapsed >= -8 && elapsed < 5 // dégradé avant/pendant la décision
  const apiDown = elapsed >= 5 && elapsed < 14 // conteneur en cours de redémarrage
  const apiRecovering = elapsed >= 14 && elapsed < 21
  const api: ServiceStatus = apiDown
    ? { name: 'api', up: false, latency_p95_ms: null, error_rate_5xx: null, requests_per_s: 0 }
    : apiAnomaly
      ? { name: 'api', up: true, latency_p95_ms: 2400 * j(1), error_rate_5xx: 0.18 * j(2), requests_per_s: 9 * j(3) }
      : apiRecovering
        ? { name: 'api', up: true, latency_p95_ms: 420 * j(1), error_rate_5xx: 0.01 * j(2), requests_per_s: 18 * j(3) }
        : { name: 'api', up: true, latency_p95_ms: 160 * j(1), error_rate_5xx: 0.002 * j(2), requests_per_s: 24 * j(3) }
  const gatewayErrors = apiAnomaly ? 0.12 : apiDown ? 0.3 : 0.003
  return [
    { name: 'front', up: true, latency_p95_ms: 95 * j(4), error_rate_5xx: 0.001, requests_per_s: 31 * j(5) },
    { name: 'auth', up: true, latency_p95_ms: 140 * j(6), error_rate_5xx: 0.002, requests_per_s: 7 * j(7) },
    api,
    { name: 'db', up: true, latency_p95_ms: 9 * j(8), error_rate_5xx: 0, requests_per_s: 52 * j(9) },
    { name: 'gateway', up: true, latency_p95_ms: 35 * j(10), error_rate_5xx: gatewayErrors * j(11), requests_per_s: 60 * j(12) },
  ]
}

function proofFor(cycle: number, detectedAt: number): Proof {
  return {
    transaction_id: `txn_demo_${cycle}`,
    reference: `PP-2026-${String(120 + cycle).padStart(6, '0')}`,
    amount_cents: 100,
    status: 'completed',
    created_at: new Date(detectedAt + 30_000).toISOString(),
    sender: 'alex@poupal.demo',
    recipient: 'camille@poupal.demo',
    balance_before_cents: 125_000,
    balance_after_cents: 124_900,
    consistency: 'ok',
  }
}

/** Construit l'incident du cycle courant à l'instant `elapsed` (s depuis la détection). */
function incidentAt(cycle: number, detectedAt: number, elapsed: number): Incident {
  const timeline: TimelineEntry[] = STEPS.filter((s) => s.elapsed <= elapsed).map((s) => ({
    t: new Date(detectedAt + s.elapsed * 1000).toISOString(),
    elapsed_s: s.elapsed,
    step: s.step,
    label: s.label,
    details: {},
  }))
  let state: IncidentState = 'RECU'
  if (elapsed >= 3) state = 'DECIDE'
  if (elapsed >= 5) state = 'ACTION_EN_COURS'
  if (elapsed >= 15) state = 'VERIFICATION'
  if (elapsed >= RECOVERED_AT) state = 'RETABLI'
  const recovered = elapsed >= RECOVERED_AT
  return {
    incident_id: `INC-2026-${String(cycle + 1).padStart(4, '0')}`,
    state,
    incident_type: 'surcharge',
    suspected_service: 'api',
    detected_at: new Date(detectedAt).toISOString(),
    received_at: new Date(detectedAt + 1000).toISOString(),
    resolved_at: recovered ? new Date(detectedAt + RECOVERED_AT * 1000).toISOString() : null,
    recovery_seconds: recovered ? RECOVERED_AT : null,
    plan: [
      { level: 1, action: 'restart_container', params: { service: 'api' } },
      { level: 2, action: 'recreate_container', params: { service: 'api', image: 'poupal/api:stable' } },
      { level: 3, action: 'isolate_service', params: { service: 'api' } },
    ],
    current_level: 1,
    timeline,
    proof: elapsed >= 30 ? proofFor(cycle, detectedAt) : null,
  }
}

/** Incidents passés (fictifs) pour remplir l'historique dès le démarrage. */
function pastIncidents(now: number): Incident[] {
  const mk = (
    minutesAgo: number,
    type: Incident['incident_type'],
    service: string,
    state: IncidentState,
    duration: number | null,
  ): Incident => {
    const detectedAt = now - minutesAgo * 60_000
    return {
      incident_id: `INC-2026-${String(1000 - minutesAgo).padStart(4, '0')}`,
      state,
      incident_type: type,
      suspected_service: service,
      detected_at: new Date(detectedAt).toISOString(),
      received_at: new Date(detectedAt + 1000).toISOString(),
      resolved_at: duration ? new Date(detectedAt + duration * 1000).toISOString() : null,
      recovery_seconds: duration,
      plan: [],
      current_level: state === 'ECHEC' ? 3 : 1,
      timeline: [],
      proof: null,
    }
  }
  return [
    mk(18, 'bruteforce', 'auth', 'RETABLI', 27),
    mk(41, 'db_lente', 'db', 'RETABLI', 52),
    mk(73, 'indisponibilite', 'front', 'RETABLI', 19),
    mk(128, 'compromission', 'api', 'ECHEC', null),
  ]
}

// --- Flux simulé --------------------------------------------------------------
const startedAt = Date.now()
const history: ScorePoint[] = []
const markers: Marker[] = []
const resolved: Incident[] = pastIncidents(startedAt) // plus récents d'abord
let lastHistoryBucket = -1
let lastClosedCycle = -1

// Courbe initiale : 10 minutes de calme.
for (let i = HISTORY_POINTS; i > 0; i--) {
  const t = startedAt - i * HISTORY_STEP_S * 1000
  history.push({ t: new Date(t).toISOString(), score: scoreAt(-999, t / 1000), threshold: THRESHOLD })
}

function buildState(now: number): State {
  const sinceStart = (now - startedAt) / 1000
  const cycle = Math.floor(sinceStart / CYCLE_S)
  const elapsed = (sinceStart % CYCLE_S) - CALM_BEFORE_S // de -20 à +75
  const detectedAt = startedAt + (cycle * CYCLE_S + CALM_BEFORE_S) * 1000
  const seed = now / 1000

  // Courbe : un point toutes les 5 s, 120 points max.
  const bucket = Math.floor(sinceStart / HISTORY_STEP_S)
  if (bucket !== lastHistoryBucket) {
    lastHistoryBucket = bucket
    history.push({ t: new Date(now).toISOString(), score: scoreAt(elapsed, seed), threshold: THRESHOLD })
    while (history.length > HISTORY_POINTS) history.shift()
  }

  // Repères : ajoutés une fois par cycle, purgés au-delà de 10 minutes.
  const addMarker = (atElapsed: number, kind: Marker['kind'], label: string) => {
    const t = new Date(detectedAt + atElapsed * 1000).toISOString()
    if (elapsed >= atElapsed && !markers.some((m) => m.t === t && m.kind === kind)) markers.push({ t, kind, label })
  }
  addMarker(0, 'detected', 'Détection')
  addMarker(5, 'action', 'Redémarrage')
  addMarker(RECOVERED_AT, 'recovered', 'Rétabli')
  while (markers.length && Date.parse(markers[0]!.t) < now - HISTORY_POINTS * HISTORY_STEP_S * 1000) markers.shift()

  // Incident en cours / dernier incident.
  const incident = elapsed >= 0 ? incidentAt(cycle, detectedAt, elapsed) : null
  if (incident && incident.state === 'RETABLI' && lastClosedCycle !== cycle) {
    lastClosedCycle = cycle
    resolved.unshift(incident) // alimente l'historique
  }
  const previous = resolved[0] ?? null
  const lastIncident = incident ?? previous

  let global: State['global_state'] = 'NORMAL'
  if (elapsed >= 0 && elapsed < 5) global = 'ANOMALIE'
  else if (elapsed >= 5 && elapsed < RECOVERED_AT) global = 'REMEDIATION'
  else if (elapsed >= RECOVERED_AT && elapsed < NORMAL_AGAIN_AT) global = 'RETABLI'

  const score = scoreAt(elapsed, seed)
  return {
    global_state: global,
    updated_at: new Date(now).toISOString(),
    services: servicesAt(elapsed, seed),
    detector: {
      available: true,
      state: score > THRESHOLD ? 'ANOMALIE' : elapsed >= 14 && elapsed < 46 ? 'RETABLISSEMENT' : 'NORMAL',
      score,
      threshold: THRESHOLD,
      suspected_service: score > THRESHOLD ? 'api' : null,
      incident_type: score > THRESHOLD ? 'surcharge' : null,
    },
    current_incident: incident && incident.state !== 'RETABLI' ? incident : null,
    last_incident: lastIncident,
    last_proof: lastIncident?.proof ?? previous?.proof ?? proofFor(-1, startedAt - 18 * 60_000),
    circuit_breaker: { open: false, count: Math.min(cycle, 2), limit: 3, window_minutes: 60 },
    dry_run: false,
    score_history: [...history],
    markers: [...markers],
  }
}

/** Équivalent de fetchState() en mode démo. */
export function fetchMockState(): Promise<State> {
  return Promise.resolve(buildState(Date.now()))
}

/** Équivalent de fetchIncidents() en mode démo (plus récents d'abord). */
export function fetchMockIncidents(): Promise<Incident[]> {
  buildState(Date.now())
  return Promise.resolve([...resolved])
}

/** Équivalent de subscribeState() : un nouvel état chaque seconde. */
export function subscribeMockState({ onState, onStatus }: SubscribeCallbacks): () => void {
  onStatus('live')
  onState(buildState(Date.now()))
  const timer = setInterval(() => onState(buildState(Date.now())), 1000)
  return () => clearInterval(timer)
}
