import { Home, LayoutDashboard } from 'lucide-react'
import { DemoBanner, Logo, SlimFooter } from '@/components/layout'
import { ButtonLink } from '@/components/ui'
import { usePageTitle } from '@/hooks/usePageTitle'

/**
 * Page 404. Le routeur n'applique aucun layout à la route "*" :
 * la page assemble donc elle-même le bandeau démo, le logo et le pied de page.
 */
export function NotFoundPage() {
  usePageTitle('Page introuvable')

  return (
    <div className="flex min-h-screen flex-col bg-surface">
      <DemoBanner />

      <main
        id="contenu"
        className="container-page flex flex-1 animate-fade-up flex-col items-center justify-center py-12 text-center sm:py-16"
      >
        <Logo size={44} />

        {/* Visuel sobre : grand "404" en dégradé de marque, posé sur un halo bleu */}
        <div className="relative mt-10">
          <span
            aria-hidden="true"
            className="absolute inset-0 -z-10 m-auto h-40 w-40 rounded-full bg-accent-soft blur-3xl"
          />
          <p className="text-brand-gradient text-8xl leading-none font-extrabold tracking-tight sm:text-9xl">
            404
          </p>
        </div>

        <h1 className="mt-6 text-2xl font-bold text-ink sm:text-3xl">Cette page n'existe pas (ou plus).</h1>
        <p className="mt-3 max-w-md text-muted">
          Le lien est peut-être erroné ou la page a été déplacée. Rassurez-vous : votre espace client,
          lui, est toujours là.
        </p>

        <div className="mt-8 flex w-full flex-col gap-3 sm:w-auto sm:flex-row">
          <ButtonLink to="/" leftIcon={<Home size={18} aria-hidden="true" />}>
            Retour à l'accueil
          </ButtonLink>
          <ButtonLink to="/dashboard" variant="secondary" leftIcon={<LayoutDashboard size={18} aria-hidden="true" />}>
            Mon espace client
          </ButtonLink>
        </div>
      </main>

      <SlimFooter />
    </div>
  )
}
