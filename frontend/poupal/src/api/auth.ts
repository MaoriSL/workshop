/**
 * API d'authentification.
 * Contrat REST du service auth (JWT RS256) — voir docs/api/contract.md :
 *   POST /auth/register { name, email, password } → 201 { id, email, name, created_at }
 *   POST /auth/login    { email, password }       → 200 { access_token, token_type, expires_in }
 *   GET  /auth/me                                  → 200 { id, email, name, created_at }
 * En mode mock, n'importe quel email valide + mot de passe (8 caractères min.)
 * connecte l'utilisateur de démonstration "Alex Martin".
 */
import type { AuthResponse, LoginRequest, SignupRequest, User } from '@/types'
import { ApiError, request, tokenStorage, USE_MOCK } from './client'
import { toUser, type ApiUser } from './mappers'
import { demoToken, demoUser } from './mock/data'
import { wait } from './mock/delay'
import { isValidEmail } from '@/utils/format'

interface ApiTokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export async function login(credentials: LoginRequest): Promise<AuthResponse> {
  if (USE_MOCK) {
    await wait(700)
    if (!isValidEmail(credentials.email) || credentials.password.length < 8) {
      throw new ApiError(401, 'Email ou mot de passe incorrect.', 'invalid_credentials')
    }
    const response: AuthResponse = { token: demoToken, user: demoUser }
    tokenStorage.set(response.token)
    return response
  }

  // 1) jeton, 2) profil (le service auth ne renvoie pas l'utilisateur avec le jeton)
  const tokenResponse = await request<ApiTokenResponse>('/auth/login', { method: 'POST', body: credentials })
  tokenStorage.set(tokenResponse.access_token)
  const user = toUser(await request<ApiUser>('/auth/me'))
  return { token: tokenResponse.access_token, user }
}

export async function signup(data: SignupRequest): Promise<AuthResponse> {
  if (USE_MOCK) {
    await wait(900)
    if (!isValidEmail(data.email)) throw new ApiError(400, 'Adresse email invalide.', 'validation_error')
    if (data.password.length < 8) {
      throw new ApiError(400, 'Le mot de passe doit contenir au moins 8 caractères.', 'validation_error')
    }
    // Le compte créé reprend le nom saisi, pour une démo plus crédible.
    const user: User = { ...demoUser, name: data.name.trim(), email: data.email.trim() }
    tokenStorage.set(demoToken)
    return { token: demoToken, user }
  }

  // Inscription puis connexion automatique
  await request<ApiUser>('/auth/register', { method: 'POST', body: data })
  return login({ email: data.email, password: data.password })
}

/** Récupère l'utilisateur courant à partir du JWT stocké (null si non connecté). */
export async function getCurrentUser(): Promise<User | null> {
  const token = tokenStorage.get()
  if (!token) return null

  if (USE_MOCK) {
    await wait(300)
    return demoUser
  }

  try {
    return toUser(await request<ApiUser>('/auth/me'))
  } catch (error) {
    // Jeton expiré ou invalide : on repart d'un état déconnecté.
    if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
      tokenStorage.clear()
      return null
    }
    throw error
  }
}

export function logout(): void {
  tokenStorage.clear()
}
