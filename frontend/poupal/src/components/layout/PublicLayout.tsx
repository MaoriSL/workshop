import { Outlet } from 'react-router-dom'
import { DemoBanner } from './DemoBanner'
import { Header } from './Header'
import { Footer } from './Footer'

/** Mise en page du site vitrine : bandeau démo + header + contenu + footer complet. */
export function PublicLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-white">
      <DemoBanner />
      <Header />
      <main id="contenu" className="flex-1">
        <Outlet />
      </main>
      <Footer />
    </div>
  )
}
