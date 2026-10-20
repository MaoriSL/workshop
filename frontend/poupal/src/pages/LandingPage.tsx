import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { usePageTitle } from '@/hooks/usePageTitle'
import { CtaSection, FeaturesSection, HeroSection, HowItWorksSection, SecuritySection } from '@/components/landing'

/**
 * Page d'accueil du site vitrine.
 * Chaque section est un composant indépendant (src/components/landing),
 * assemblé ici dans l'ordre : hero → avantages → étapes → sécurité → appel à l'action.
 */
export function LandingPage() {
  usePageTitle('Accueil')
  const { hash } = useLocation()

  // Les liens du header pointent vers /#avantages, /#securite... :
  // on fait défiler jusqu'à la section visée (ScrollToTop remonte sinon en haut de page).
  useEffect(() => {
    if (!hash) return
    document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [hash])

  return (
    <>
      <HeroSection />
      <FeaturesSection />
      <HowItWorksSection />
      <SecuritySection />
      <CtaSection />
    </>
  )
}
