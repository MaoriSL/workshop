import { useContext } from 'react'
import { AuthContext, type AuthContextValue } from '@/context/AuthContext'

/** Accès au contexte d'authentification : const { user, logout } = useAuth() */
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth doit être utilisé à l’intérieur de <AuthProvider>.')
  }
  return context
}
