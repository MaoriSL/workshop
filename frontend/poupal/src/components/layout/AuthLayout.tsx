import { Outlet } from 'react-router-dom'
import { DemoBanner } from './DemoBanner'
import { SlimFooter } from './Footer'
import { Logo } from './Logo'

/**
 * Mise en page minimaliste des écrans de connexion / inscription :
 * logo centré, carte au milieu, pied de page compact.
 */
export function AuthLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-surface">
      <DemoBanner />
      <header className="container-page flex h-16 items-center justify-center">
        <Logo size={38} />
      </header>
      <main id="contenu" className="flex flex-1 items-start justify-center px-4 py-6 sm:items-center sm:py-10">
        <div className="w-full max-w-md">
          <Outlet />
        </div>
      </main>
      <SlimFooter />
    </div>
  )
}
