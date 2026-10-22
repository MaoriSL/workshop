// ---------------------------------------------------------------------------
// Couche réseau centralisée : dialogue avec l'orchestrateur d'attaques.
//
// Lectures :
//   - fetchState()      : GET {base}/state
//   - fetchJournal()    : GET {base}/journal
//   - subscribeState()  : flux temps réel SSE (GET {base}/events, event `state`)
//                         avec repli automatique en polling si le flux tombe.
// Actions BORNÉES (les seules possibles) :
//   - startScenario()   : POST {base}/scenarios/{id}/start
//   - stopScenario()    : POST {base}/scenarios/{id}/stop
//   - stopAll()         : POST {base}/stop-all
//   - exportJournalCsv(): GET {base}/journal.csv (téléchargement)
//
// Aucune commande libre : les paramètres proviennent des schémas bornés des
// scénarios et sont transmis tels quels.
// ---------------------------------------------------------------------------
import type { ConnectionStatus, JournalEntry, State, TargetUpdate } from './types'

/** Base URL de l'API (même origine ; en dev, proxifiée vers localhost:8099). */
export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) || '/api'

/** Mode démonstration : scénarios embarqués, aucun appel réseau. */
export const USE_MOCK: boolean = import.meta.env.VITE_USE_MOCK === 'true'

// Délais du protocole de repli (voir contrat d'API).
const HEARTBEAT_TIMEOUT_MS = 6_000 // aucun message SSE depuis 6 s → flux mort
const POLL_INTERVAL_MS = 2_000 // polling GET /state toutes les 2 s
const SSE_RETRY_MS = 15_000 // nouvelle tentative SSE toutes les 15 s

/** Callbacks de l'abonnement au flux d'état. */
export interface SubscribeCallbacks {
  onState: (state: State) => void
  onStatus: (status: ConnectionStatus) => void
}

/** Surface commune (identique pour l'API réelle et pour le mock). */
export interface AttackApi {
  subscribe: (cb: SubscribeCallbacks) => () => void
  fetchJournal: () => Promise<JournalEntry[]>
  startScenario: (id: string, params: Record<string, number | string>) => Promise<{ run_id: string }>
  setTarget: (url: string) => Promise<TargetUpdate>
  stopScenario: (id: string) => Promise<void>
  stopAll: () => Promise<void>
  exportJournalCsv: () => void
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(`HTTP ${res.status} sur ${path}`)
  return (await res.json()) as T
}

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    let message = `HTTP ${res.status} sur ${path}`
    try {
      const error = (await res.json()) as { message?: string }
      if (error.message) message = error.message
    } catch {
      // La réponse d'erreur peut être vide ou non JSON.
    }
    throw new Error(message)
  }
  // Certaines réponses (stop, stop-all) n'ont pas de corps JSON.
  const text = await res.text()
  return (text ? JSON.parse(text) : {}) as T
}

export function fetchState(): Promise<State> {
  return getJson<State>('/state')
}

export async function fetchJournal(): Promise<JournalEntry[]> {
  const data = await getJson<{ items: JournalEntry[] }>('/journal')
  return data.items ?? []
}

export function startScenario(id: string, params: Record<string, number | string>): Promise<{ run_id: string }> {
  return postJson<{ run_id: string }>(`/scenarios/${id}/start`, { params })
}

export function setTarget(url: string): Promise<TargetUpdate> {
  return postJson<TargetUpdate>('/target', { url })
}

export async function stopScenario(id: string): Promise<void> {
  await postJson(`/scenarios/${id}/stop`)
}

export async function stopAll(): Promise<void> {
  await postJson('/stop-all')
}

/** Déclenche le téléchargement du journal CSV généré par l'orchestrateur. */
export function exportJournalCsv(): void {
  const a = document.createElement('a')
  a.href = `${API_BASE}/journal.csv`
  a.download = 'poupal-journal-attaques.csv'
  document.body.appendChild(a)
  a.click()
  a.remove()
}

/**
 * S'abonne aux changements d'état.
 * 1. Ouvre un EventSource sur {base}/events (événements `state`).
 * 2. Si aucun message n'arrive pendant 6 s (ou en cas d'erreur), bascule en
 *    polling GET /state toutes les 2 s et retente le SSE toutes les 15 s.
 * 3. Si le polling échoue aussi, l'indicateur passe « hors ligne » mais on
 *    continue d'essayer : la console ne reste jamais figée.
 * Retourne une fonction d'arrêt (à appeler au démontage).
 */
export function subscribeState({ onState, onStatus }: SubscribeCallbacks): () => void {
  let stopped = false
  let source: EventSource | null = null
  let heartbeatTimer: ReturnType<typeof setTimeout> | null = null
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let retryTimer: ReturnType<typeof setTimeout> | null = null

  // --- Flux SSE -------------------------------------------------------------
  function armHeartbeat() {
    if (heartbeatTimer) clearTimeout(heartbeatTimer)
    heartbeatTimer = setTimeout(() => fallbackToPolling(), HEARTBEAT_TIMEOUT_MS)
  }

  function openSse() {
    if (stopped) return
    closeSse()
    source = new EventSource(`${API_BASE}/events`)
    source.addEventListener('state', (ev: MessageEvent<string>) => {
      try {
        onState(JSON.parse(ev.data) as State)
        onStatus('live')
        stopPolling() // le flux est revenu : plus besoin du polling
        armHeartbeat()
      } catch {
        // message illisible : on l'ignore, le battement de cœur suivant tranchera
      }
    })
    source.onopen = () => armHeartbeat()
    source.onerror = () => fallbackToPolling()
    armHeartbeat()
  }

  function closeSse() {
    if (heartbeatTimer) clearTimeout(heartbeatTimer)
    heartbeatTimer = null
    if (source) source.close()
    source = null
  }

  // --- Repli polling --------------------------------------------------------
  async function pollOnce() {
    try {
      onState(await fetchState())
      onStatus('polling')
    } catch {
      onStatus('offline')
    }
  }

  function fallbackToPolling() {
    if (stopped) return
    closeSse()
    if (!pollTimer) {
      void pollOnce()
      pollTimer = setInterval(() => void pollOnce(), POLL_INTERVAL_MS)
    }
    if (!retryTimer) {
      retryTimer = setTimeout(() => {
        retryTimer = null
        openSse()
      }, SSE_RETRY_MS)
    }
  }

  function stopPolling() {
    if (pollTimer) clearInterval(pollTimer)
    pollTimer = null
    if (retryTimer) clearTimeout(retryTimer)
    retryTimer = null
  }

  // Premier état tout de suite via GET (plus rapide que d'attendre le SSE),
  // puis ouverture du flux.
  void fetchState()
    .then((s) => {
      if (!stopped) onState(s)
    })
    .catch(() => onStatus('offline'))
  openSse()

  return () => {
    stopped = true
    closeSse()
    stopPolling()
  }
}

/** Implémentation réseau réelle (utilisée hors mode démonstration). */
export const realApi: AttackApi = {
  subscribe: subscribeState,
  fetchJournal,
  startScenario,
  setTarget,
  stopScenario,
  stopAll,
  exportJournalCsv,
}
