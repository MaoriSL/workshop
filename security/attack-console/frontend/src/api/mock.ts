// ---------------------------------------------------------------------------
// Données de démonstration (VITE_USE_MOCK=true) : simule l'orchestrateur sans
// serveur. Permet de vérifier tout le rendu et les actions (Lancer / Stopper /
// Arrêt d'urgence / Export) dans le navigateur. Tout est inventé, aucune
// attaque réelle n'est émise.
//
// Mêmes signatures que client.ts (interface AttackApi) : le reste du code ne
// change pas selon le mode.
//
// Astuce de vérification : ouvrir la console avec `?lab=off` dans l'URL force
// l'état « hors périmètre » (in_lab=false) pour tester l'écran d'alerte rouge.
// ---------------------------------------------------------------------------
import type { AttackApi, SubscribeCallbacks } from './client'
import type { JournalEntry, Run, RunStatus, Scenario, ScenarioId, State, TargetUpdate } from './types'

// --- Catalogue des scénarios (schémas de paramètres BORNÉS) -----------------
const SCENARIOS: Scenario[] = [
  {
    id: 'dos',
    name: 'Déni de service',
    description: 'Rafale de requêtes sur l’API de paiement pour la saturer.',
    incident_type: 'surcharge',
    defense: 'Limitation de débit (429) et montée en charge automatique.',
    params_schema: [
      { key: 'intensite', label: 'Intensité', type: 'int', min: 20, max: 1000, step: 20, default: 300, unit: 'req/s' },
      { key: 'duree', label: 'Durée', type: 'int', min: 10, max: 180, step: 10, default: 45, unit: 's' },
    ],
  },
  {
    id: 'bruteforce',
    name: 'Force brute',
    description: 'Tentatives répétées de connexion sur des comptes ciblés.',
    incident_type: 'bruteforce',
    defense: 'Verrouillage de compte et blocage d’IP par le WAF.',
    params_schema: [
      { key: 'comptes', label: 'Comptes ciblés', type: 'int', min: 1, max: 20, step: 1, default: 5 },
      { key: 'intensite', label: 'Tentatives', type: 'int', min: 2, max: 100, step: 2, default: 30, unit: 'req/s' },
      { key: 'duree', label: 'Durée', type: 'int', min: 10, max: 120, step: 10, default: 40, unit: 's' },
    ],
  },
  {
    id: 'injection',
    name: 'Injection SQL',
    description: 'Envoi de charges malveillantes sur les champs de l’API.',
    incident_type: 'injection',
    defense: 'Filtrage des charges malveillantes par le WAF (403).',
    params_schema: [
      {
        key: 'variante',
        label: 'Variante',
        type: 'select',
        default: 'union',
        options: [
          { value: 'union', label: 'UNION SELECT' },
          { value: 'boolean', label: 'Booléenne aveugle' },
          { value: 'time', label: 'Temporelle (sleep)' },
        ],
      },
      { key: 'intensite', label: 'Intensité', type: 'int', min: 5, max: 100, step: 5, default: 30, unit: 'req/s' },
      { key: 'duree', label: 'Durée', type: 'int', min: 10, max: 180, step: 10, default: 60, unit: 's' },
    ],
  },
  {
    id: 'exfiltration',
    name: 'Exfiltration',
    description: 'Extraction massive de données après un accès obtenu.',
    incident_type: 'exfiltration',
    defense: 'Détection de volumétrie anormale et coupure du flux.',
    params_schema: [
      { key: 'debit', label: 'Débit', type: 'float', min: 0.5, max: 40, step: 0.5, default: 10, unit: 'Mo/s' },
      { key: 'duree', label: 'Durée', type: 'int', min: 10, max: 120, step: 10, default: 50, unit: 's' },
    ],
  },
  {
    id: 'combo',
    name: 'Attaque combinée',
    description: 'Force brute, injection et surcharge menées de front.',
    incident_type: 'combo',
    defense: 'Corrélation multi-signaux (SIEM) et remédiation automatique.',
    params_schema: [
      { key: 'intensite', label: 'Intensité', type: 'int', min: 20, max: 400, step: 20, default: 200, unit: 'req/s' },
      { key: 'duree', label: 'Durée', type: 'int', min: 20, max: 180, step: 10, default: 70, unit: 's' },
    ],
  },
]

// --- État interne de la simulation ------------------------------------------
let target = 'poupal-gateway:8080  ·  réseau RESILIENCE-G1 (plage privée)'
// Périmètre : forçable à « hors zone » via ?lab=off pour la vérification.
let inLab = !(typeof location !== 'undefined' && /(?:^|[?&])lab=off(?:&|$)/.test(location.search))
let labReason = inLab
  ? ''
  : 'Cible hors de la plage autorisée (10.42.0.0/24). Attaques désactivées par sécurité.'

const runs: Run[] = [] // le plus récent d'abord
const journal: JournalEntry[] = [] // le plus récent d'abord
const sim = new Map<string, { durationS: number; rate: number; intensity: number | null }>()
let emergencyStopped = false
let seq = 1

/** Intensité représentative d'un run (pour le journal), selon ses paramètres. */
function intensityOf(id: ScenarioId, params: Record<string, number | string>): number | null {
  if (id === 'exfiltration') return Number(params.debit) || null
  const v = Number(params.intensite)
  return Number.isFinite(v) ? v : null
}

/** Répartition des réponses d'UNE seconde selon le scénario et l'avancement. */
function breakdown(id: ScenarioId, elapsed: number, duration: number, sent: number): { byStatus: Record<string, number>; blocked: number } {
  const p = duration > 0 ? Math.min(1, elapsed / duration) : 1 // avancement 0→1
  const by: Record<string, number> = {}
  let blocked = 0
  const add = (code: string, n: number) => {
    if (n > 0) by[code] = (by[code] ?? 0) + n
  }
  switch (id) {
    case 'dos': {
      // La limitation de débit monte avec la charge : de plus en plus de 429.
      const limited = Math.round(sent * Math.min(0.78, p * 0.95))
      const errors = Math.round(sent * Math.min(0.06, p * 0.08))
      add('429', limited)
      add('503', errors)
      add('200', sent - limited - errors)
      blocked = limited + errors
      break
    }
    case 'injection': {
      // Le WAF bloque la quasi-totalité des charges malveillantes (403).
      const waf = Math.round(sent * Math.min(0.97, 0.72 + p * 0.25))
      add('403', waf)
      add('200', sent - waf)
      blocked = waf
      break
    }
    case 'bruteforce': {
      if (p < 0.3) {
        add('401', sent) // mauvais mots de passe, pas encore verrouillé
      } else {
        const locked = Math.round(sent * 0.8) // comptes verrouillés / IP bloquée
        add('429', locked)
        add('401', sent - locked)
        blocked = locked
      }
      break
    }
    case 'exfiltration': {
      if (p < 0.4) {
        add('200', sent) // le flux passe encore
      } else {
        add('403', sent) // volumétrie anormale détectée → coupure
        blocked = sent
      }
      break
    }
    case 'combo': {
      const waf = Math.round(sent * Math.min(0.6, 0.3 + p * 0.4))
      const limited = Math.round(sent * Math.min(0.3, p * 0.3))
      add('403', waf)
      add('429', limited)
      add('401', Math.round(sent * 0.1))
      add('200', Math.max(0, sent - waf - limited - Math.round(sent * 0.1)))
      blocked = waf + limited
      break
    }
  }
  return { byStatus: by, blocked }
}

/** Avance un run d'une seconde (met à jour compteurs et statut). */
function tickRun(run: Run): void {
  if (run.status !== 'running') return
  const cfg = sim.get(run.run_id)
  if (!cfg) return
  run.elapsed_s += 1
  const jitter = 0.9 + Math.random() * 0.2
  const sent = Math.max(0, Math.round(cfg.rate * jitter))
  run.rate_per_s = sent
  const { byStatus, blocked } = breakdown(run.scenario_id, run.elapsed_s, cfg.durationS, sent)
  for (const code of Object.keys(byStatus)) {
    run.responses_by_status[code] = (run.responses_by_status[code] ?? 0) + (byStatus[code] ?? 0)
  }
  run.requests_sent += sent
  run.blocked += blocked
  if (run.elapsed_s >= cfg.durationS) finish(run, 'finished', 'Terminé — attaque encaissée par la plateforme')
}

/** Clôt un run et l'inscrit au journal. */
function finish(run: Run, status: RunStatus, result: string): void {
  run.status = status
  run.ended_at = new Date().toISOString()
  run.rate_per_s = 0
  const cfg = sim.get(run.run_id)
  journal.unshift({
    run_id: run.run_id,
    scenario_id: run.scenario_id,
    type: run.scenario_id,
    status,
    started_at: run.started_at,
    ended_at: run.ended_at,
    duration_s: run.elapsed_s,
    intensity: cfg?.intensity ?? null,
    requests_sent: run.requests_sent,
    blocked: run.blocked,
    result,
  })
}

/** Crée un run pour un scénario avec ses paramètres. */
function createRun(id: ScenarioId, params: Record<string, number | string>): Run {
  const rate = id === 'exfiltration' ? Math.max(2, Math.round(Number(params.debit) * 4)) : Number(params.intensite) || 20
  const durationS = Number(params.duree) || 45
  const run: Run = {
    run_id: `run_${Date.now()}_${seq++}`,
    scenario_id: id,
    status: 'running',
    params,
    started_at: new Date().toISOString(),
    ended_at: null,
    elapsed_s: 0,
    requests_sent: 0,
    responses_by_status: {},
    blocked: 0,
    rate_per_s: rate,
  }
  sim.set(run.run_id, { durationS, rate, intensity: intensityOf(id, params) })
  return run
}

/** Avance un run neuf de N secondes (pour les runs pré-remplis au démarrage). */
function fastForward(run: Run, seconds: number): void {
  for (let i = 0; i < seconds; i++) tickRun(run)
  run.started_at = new Date(Date.now() - run.elapsed_s * 1000).toISOString()
}

// --- Amorçage : deux runs en cours + journal pré-rempli ----------------------
function seed(): void {
  // Un run DOS déjà bien avancé : il « monte en charge » puis se terminera
  // sous les yeux de l'observateur (durée 45 s, déjà à T+34 s).
  const dos = createRun('dos', { intensite: 200, duree: 45 })
  runs.unshift(dos)
  fastForward(dos, 34)

  // Un run INJECTION en cours dont le nombre de requêtes bloquées (WAF) augmente.
  const inj = createRun('injection', { variante: 'union', intensite: 70, duree: 120 })
  runs.unshift(inj)
  fastForward(inj, 22)

  // Journal : quelques attaques passées (fictives) pour illustrer l'historique.
  const past = (minsAgo: number, id: ScenarioId, status: RunStatus, duration: number, intensity: number, sent: number, blocked: number, result: string) => {
    const ended = Date.now() - minsAgo * 60_000
    journal.push({
      run_id: `run_demo_${id}_${minsAgo}`,
      scenario_id: id,
      type: id,
      status,
      started_at: new Date(ended - duration * 1000).toISOString(),
      ended_at: new Date(ended).toISOString(),
      duration_s: duration,
      intensity,
      requests_sent: sent,
      blocked,
      result,
    })
  }
  past(6, 'bruteforce', 'finished', 40, 20, 740, 612, 'Comptes verrouillés, IP bloquée par le WAF')
  past(14, 'dos', 'stopped', 28, 300, 7200, 5400, 'Arrêté — limitation de débit effective')
  past(23, 'injection', 'finished', 60, 80, 4100, 3980, 'Charges bloquées par le WAF (403)')
  past(38, 'exfiltration', 'finished', 50, 6, 410, 240, 'Flux coupé après détection de volumétrie')
}
seed()

// --- Diffusion de l'état -----------------------------------------------------
const listeners = new Set<(s: State) => void>()
let ticker: ReturnType<typeof setInterval> | null = null

function buildState(): State {
  return {
    target,
    in_lab: inLab,
    lab_reason: labReason,
    updated_at: new Date().toISOString(),
    scenarios: SCENARIOS,
    runs: runs.slice(0, 20), // on garde les plus récents
    emergency_stopped: emergencyStopped,
  }
}

function emit(): void {
  const s = buildState()
  for (const l of listeners) l(s)
}

function startTicker(): void {
  if (ticker) return
  ticker = setInterval(() => {
    for (const run of runs) tickRun(run)
    emit()
  }, 1000)
}

// --- Implémentation de l'interface AttackApi ---------------------------------
function subscribeMock({ onState, onStatus }: SubscribeCallbacks): () => void {
  listeners.add(onState)
  onStatus('live') // en démo, la liaison est toujours « temps réel »
  onState(buildState())
  startTicker()
  return () => {
    listeners.delete(onState)
    if (listeners.size === 0 && ticker) {
      clearInterval(ticker)
      ticker = null
    }
  }
}

function startScenarioMock(id: string, params: Record<string, number | string>): Promise<{ run_id: string }> {
  if (!inLab) return Promise.reject(new Error('HTTP 403 : cible hors périmètre'))
  const already = runs.find((r) => r.scenario_id === id && r.status === 'running')
  if (already) return Promise.reject(new Error('HTTP 409 : un run est déjà en cours'))
  emergencyStopped = false // un lancement lève l'état d'arrêt d'urgence
  const run = createRun(id as ScenarioId, params)
  runs.unshift(run)
  emit()
  return Promise.resolve({ run_id: run.run_id })
}

function setTargetMock(url: string): Promise<TargetUpdate> {
  target = url
  inLab = true
  labReason = ''
  emit()
  return Promise.resolve({ target, in_lab: inLab, lab_reason: labReason })
}

function stopScenarioMock(id: string): Promise<void> {
  for (const run of runs) {
    if (run.scenario_id === id && run.status === 'running') finish(run, 'stopped', 'Arrêté manuellement')
  }
  emit()
  return Promise.resolve()
}

function stopAllMock(): Promise<void> {
  for (const run of runs) {
    if (run.status === 'running') finish(run, 'stopped', 'Arrêt d’urgence global')
  }
  emergencyStopped = true
  emit()
  return Promise.resolve()
}

function fetchJournalMock(): Promise<JournalEntry[]> {
  return Promise.resolve([...journal])
}

/** Export CSV côté client (le vrai orchestrateur renverra un fichier). */
function exportJournalCsvMock(): void {
  const head = ['run_id', 'scenario', 'type', 'statut', 'debut', 'fin', 'duree_s', 'intensite', 'requetes', 'bloquees', 'resultat']
  const rows = journal.map((e) => [
    e.run_id,
    e.scenario_id,
    e.type,
    e.status,
    e.started_at,
    e.ended_at ?? '',
    String(e.duration_s),
    e.intensity === null ? '' : String(e.intensity),
    String(e.requests_sent),
    String(e.blocked),
    e.result,
  ])
  const esc = (v: string) => (/[",;\n]/.test(v) ? `"${v.replaceAll('"', '""')}"` : v)
  const csv = [head, ...rows].map((r) => r.map(esc).join(';')).join('\r\n')
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'poupal-journal-attaques-demo.csv'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export const mockApi: AttackApi = {
  subscribe: subscribeMock,
  fetchJournal: fetchJournalMock,
  startScenario: startScenarioMock,
  setTarget: setTargetMock,
  stopScenario: stopScenarioMock,
  stopAll: stopAllMock,
  exportJournalCsv: exportJournalCsvMock,
}
