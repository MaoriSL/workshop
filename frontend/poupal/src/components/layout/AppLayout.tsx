import { Outlet } from 'react-router-dom'
import { DemoBanner } from './DemoBanner'
import { Header } from './Header'
import { SlimFooter } from './Footer'

/** Mise en page de l'espace client connecté : fond gris clair, footer compact. */
export function AppLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-surface">
      <DemoBanner />
      <Header />
      <main id="contenu" className="container-page flex-1 py-6 sm:py-10">
        <Outlet />
      </main>
      <SlimFooter />
    </div>
  )
}
