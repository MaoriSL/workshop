// ---------------------------------------------------------------------------
// Couche réseau centralisée : lecture de l'état du moteur de remédiation.
//
//  - fetchState()      : GET {base}/state
//  - fetchIncidents()  : GET {base}/incidents
//  - subscribeState()  : flux temps réel SSE (GET {base}/events) avec repli
//                        automatique en polling si le flux tombe.
//
// Le dashboard est en lecture seule : aucune requête autre que GET.
// ---------------------------------------------------------------------------
import type { ConnectionStatus, Incident, State } from './types'

/** Base URL de l'API (même origine, proxifiée par la gateway). */
export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) || '/supervision/api'

/** Mode démonstration : données embarquées, aucun appel réseau. */
export const USE_MOCK: boolean = import.meta.env.VITE_USE_MOCK === 'true'

export interface AssistantSource {
  path: string
  score: number
}

export interface AssistantResponse {
  answer: string
  sources: AssistantSource[]
  model: string
}

export async function askAssistant(question: string): Promise<AssistantResponse> {
  const res = await fetch('/assistant/query', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status} sur /assistant/query`
    try {
      const payload = (await res.json()) as { detail?: string }
      if (payload.detail) detail = payload.detail
    } catch {
      // Keep the HTTP error when the gateway does not return JSON.
    }
    throw new Error(detail)
  }
  return (await res.json()) as AssistantResponse
}

export async function summarizeIncident(incident: Incident): Promise<AssistantResponse> {
  const res = await fetch('/assistant/incident-summary', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ incident }),
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status} sur /assistant/incident-summary`
    try {
      const payload = (await res.json()) as { detail?: string }
      if (payload.detail) detail = payload.detail
    } catch {
      // Keep the HTTP error when the gateway does not return JSON.
    }
    throw new Error(detail)
  }
  return (await res.json()) as AssistantResponse
}

// Délais du protocole de repli (voir contrat d'API).
const HEARTBEAT_TIMEOUT_MS = 6_000 // aucun message SSE depuis 6 s → flux considéré mort
const POLL_INTERVAL_MS = 2_000 // polling GET state toutes les 2 s
const SSE_RETRY_MS = 15_000 // nouvelle tentative SSE toutes les 15 s

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(`HTTP ${res.status} sur ${path}`)
  return (await res.json()) as T
}

export function fetchState(): Promise<State> {
  return getJson<State>('/state')
}

export async function fetchIncidents(): Promise<Incident[]> {
  const data = await getJson<{ items: Incident[] }>('/incidents')
  return data.items ?? []
}

export interface SubscribeCallbacks {
  onState: (state: State) => void
  onStatus: (status: ConnectionStatus) => void
}

/**
 * S'abonne aux changements d'état.
 * 1. Ouvre un EventSource sur {base}/events (événements `state`).
 * 2. Si aucun message n'arrive pendant 6 s (ou en cas d'erreur), bascule en
 *    polling GET /state toutes les 2 s et retente le SSE toutes les 15 s.
 * 3. Si le polling échoue aussi, l'indicateur passe « hors ligne » mais on
 *    continue d'essayer : le dashboard ne reste jamais figé.
 * Retourne une fonction d'arrêt (à appeler au démontage du composant).
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
