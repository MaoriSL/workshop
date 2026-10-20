/**
 * Client HTTP centralisé.
 * - La base URL vient de VITE_API_URL (fichier .env). Vide = même origine que le site
 *   (cas du déploiement derrière la gateway nginx : /auth/... et /api/...).
 * - Mode mock : VITE_USE_MOCK=true, ou aucune URL d'API et VITE_USE_MOCK non défini.
 *   VITE_USE_MOCK=false force les vrais appels réseau (même origine).
 * - Le JWT est stocké dans localStorage et envoyé en en-tête Authorization.
 * - Les erreurs de l'API ont toujours la forme { message, code } (voir docs/api/contract.md).
 */

export const API_URL = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '')

const mockFlag = import.meta.env.VITE_USE_MOCK
export const USE_MOCK = mockFlag === 'true' || (mockFlag !== 'false' && API_URL === '')

const TOKEN_KEY = 'poupal.token'

/** Événement émis quand l'API répond 401 : le contexte d'auth déconnecte l'utilisateur. */
export const UNAUTHORIZED_EVENT = 'poupal:unauthorized'

export const tokenStorage = {
  get(): string | null {
    return localStorage.getItem(TOKEN_KEY)
  },
  set(token: string): void {
    localStorage.setItem(TOKEN_KEY, token)
  },
  clear(): void {
    localStorage.removeItem(TOKEN_KEY)
  },
}

/** Erreur renvoyée par l'API (ou simulée par le mock), avec un message lisible et un code stable. */
export class ApiError extends Error {
  status: number
  code: string

  constructor(status: number, message: string, code = 'http_error') {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

/** Extrait un message d'erreur affichable depuis n'importe quelle exception. */
export function getErrorMessage(error: unknown, fallback = 'Une erreur est survenue.'): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error && error.message) return error.message
  return fallback
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  /** En-têtes supplémentaires (ex. Idempotency-Key). */
  headers?: Record<string, string>
}

/**
 * Effectue une requête JSON vers l'API : request<User>('/auth/me').
 * Lève une ApiError si la réponse n'est pas 2xx.
 */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json', ...options.headers }
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'

  const token = tokenStorage.get()
  if (token) headers.Authorization = `Bearer ${token}`

  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, {
      method: options.method ?? 'GET',
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'Impossible de joindre le service Poupal. Vérifiez votre connexion.', 'network_error')
  }

  if (!response.ok) {
    const { message, code } = await extractError(response)
    // Jeton expiré ou invalide : on repart d'un état déconnecté
    if (response.status === 401 && token) {
      tokenStorage.clear()
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
    }
    throw new ApiError(response.status, message, code)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

async function extractError(response: Response): Promise<{ message: string; code: string }> {
  try {
    const data = (await response.json()) as { message?: string; detail?: string; code?: string }
    return { message: data.message ?? data.detail ?? `Erreur ${response.status}`, code: data.code ?? 'http_error' }
  } catch {
    return { message: `Erreur ${response.status}`, code: 'http_error' }
  }
}
