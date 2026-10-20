import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '@/context/AuthContext'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { ScrollToTop } from '@/components/ScrollToTop'
import { AppLayout, AuthLayout, PublicLayout } from '@/components/layout'
import { LandingPage } from '@/pages/LandingPage'
import { LoginPage } from '@/pages/LoginPage'
import { SignupPage } from '@/pages/SignupPage'
import { ForgotPasswordPage } from '@/pages/ForgotPasswordPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { SendPage } from '@/pages/SendPage'
import { SendConfirmPage } from '@/pages/SendConfirmPage'
import { SendSuccessPage } from '@/pages/SendSuccessPage'
import { TransactionDetailPage } from '@/pages/TransactionDetailPage'
import { NotFoundPage } from '@/pages/NotFoundPage'

/**
 * Routeur de l'application.
 * - Site vitrine (PublicLayout) : accueil.
 * - Authentification (AuthLayout) : connexion, inscription, mot de passe oublié.
 * - Espace client (AppLayout, protégé par ProtectedRoute) : tableau de bord,
 *   envoi d'argent (3 étapes) et détail d'une transaction.
 */
export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ScrollToTop />
        <Routes>
          <Route element={<PublicLayout />}>
            <Route path="/" element={<LandingPage />} />
          </Route>

          <Route element={<AuthLayout />}>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          </Route>

          <Route element={<ProtectedRoute />}>
            <Route element={<AppLayout />}>
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/send" element={<SendPage />} />
              <Route path="/send/confirm" element={<SendConfirmPage />} />
              <Route path="/send/success" element={<SendSuccessPage />} />
              <Route path="/transactions/:id" element={<TransactionDetailPage />} />
            </Route>
          </Route>

          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
