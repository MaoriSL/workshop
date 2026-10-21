/**
 * Contexte d'authentification.
 * Fournit l'utilisateur connecté et les actions login / signup / logout
 * à toute l'application. Au chargement, on tente de restaurer la session
 * à partir du JWT stocké (getCurrentUser).
 */
import { createContext, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import * as api from '@/api'
import { UNAUTHORIZED_EVENT } from '@/api'
import type { LoginRequest, SignupRequest, User } from '@/types'

export interface AuthContextValue {
  user: User | null
  isAuthenticated: boolean
  /** true tant que la session n'a pas été restaurée au démarrage. */
  isLoading: boolean
  login: (credentials: LoginRequest) => Promise<User>
  signup: (data: SignupRequest) => Promise<User>
  logout: () => void
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  // Restauration de session au démarrage de l'application
  useEffect(() => {
    let cancelled = false
    api
      .getCurrentUser()
      .then((current) => {
        if (!cancelled) setUser(current)
      })
      .catch(() => {
        if (!cancelled) setUser(null)
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Jeton expiré ou rejeté par l'API en cours de session : on repasse en mode déconnecté
  useEffect(() => {
    const onUnauthorized = () => setUser(null)
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
  }, [])

  const login = useCallback(async (credentials: LoginRequest) => {
    const response = await api.login(credentials)
    setUser(response.user)
    return response.user
  }, [])

  const signup = useCallback(async (data: SignupRequest) => {
    const response = await api.signup(data)
    setUser(response.user)
    return response.user
  }, [])

  const logout = useCallback(() => {
    api.logout()
    setUser(null)
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ user, isAuthenticated: user !== null, isLoading, login, signup, logout }),
    [user, isLoading, login, signup, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
