import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'

/** Encart final d'appel à l'action, sur fond dégradé de marque. */
export function CtaSection() {
  const { isAuthenticated } = useAuth()

  return (
    <section aria-labelledby="cta-titre" className="py-20 sm:py-24">
      <div className="container-page">
        <div className="relative isolate overflow-hidden rounded-3xl bg-brand-gradient px-6 py-14 text-center text-white shadow-card sm:px-12 sm:py-20">
          {/* Lueurs décoratives */}
          <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
            <div className="absolute -top-20 -right-10 h-64 w-64 rounded-full bg-white/10 blur-3xl" />
            <div className="absolute -bottom-24 -left-10 h-64 w-64 rounded-full bg-sky/30 blur-3xl" />
          </div>

          <h2 id="cta-titre" className="text-3xl font-extrabold tracking-tight sm:text-4xl">Prêt à essayer Poupal ?</h2>
          <p className="mx-auto mt-4 max-w-xl text-base text-white/75 sm:text-lg">
            Créez votre compte de démonstration en une minute et envoyez votre premier transfert fictif.
          </p>

          <div className="mt-8 flex justify-center">
            {/* Bouton blanc sur fond bleu : on sort des variantes standard pour garder le contraste */}
            <Link
              to={isAuthenticated ? '/dashboard' : '/signup'}
              className="inline-flex h-13 items-center justify-center gap-2 rounded-xl bg-white px-7 text-base font-semibold text-primary shadow-card transition-all duration-200 hover:-translate-y-px hover:bg-surface hover:shadow-glow active:scale-[0.98]"
            >
              <span>{isAuthenticated ? 'Accéder à mon espace' : 'Créer un compte gratuitement'}</span>
              <ArrowRight size={18} aria-hidden="true" />
            </Link>
          </div>

          <p className="mt-5 text-xs text-white/60">
            Environnement de démonstration — aucune donnée bancaire réelle n’est demandée.
          </p>
        </div>
      </div>
    </section>
  )
}
