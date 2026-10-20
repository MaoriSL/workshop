import { ArrowRight, FlaskConical, LockKeyhole, ShieldCheck, Sparkles } from 'lucide-react'
import { ButtonLink, Skeleton } from '@/components/ui'
import { useAuth } from '@/hooks/useAuth'
import { HeroIllustration } from './HeroIllustration'

/** Ligne de réassurance affichée sous les boutons. */
const trustItems = [
  { icon: LockKeyhole, label: 'Chiffrement de bout en bout' },
  { icon: ShieldCheck, label: 'Reprise automatique' },
  { icon: FlaskConical, label: 'Aucune donnée réelle — environnement de démonstration' },
]

/** Section d'accroche : titre, boutons d'action et illustration. */
export function HeroSection() {
  const { isAuthenticated, isLoading } = useAuth()

  return (
    <section aria-labelledby="hero-titre" className="relative isolate overflow-hidden">
      {/* Taches de couleur floutées en arrière-plan */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute -top-24 right-[-10%] h-72 w-72 rounded-full bg-sky/25 blur-3xl sm:h-96 sm:w-96" />
        <div className="absolute top-1/3 left-[-15%] h-72 w-72 rounded-full bg-accent/15 blur-3xl sm:h-[28rem] sm:w-[28rem]" />
        <div className="absolute right-[20%] bottom-0 h-56 w-56 rounded-full bg-primary/10 blur-3xl" />
      </div>

      <div className="container-page grid gap-14 py-16 sm:py-20 lg:grid-cols-2 lg:items-center lg:gap-12 lg:py-28">
        {/* Colonne texte */}
        <div className="animate-fade-up">
          <span className="inline-flex items-center gap-2 rounded-full border border-line bg-white/80 px-3.5 py-1.5 text-xs font-semibold text-primary shadow-soft">
            <Sparkles size={14} className="text-accent" aria-hidden="true" />
            Paiements entre particuliers, simplifiés
          </span>

          <h1 id="hero-titre" className="mt-6 text-4xl font-extrabold tracking-tight text-ink sm:text-5xl lg:text-[3.5rem] lg:leading-[1.08]">
            Envoyez et recevez de l’argent <span className="text-brand-gradient">en toute sécurité</span>
          </h1>

          <p className="mt-5 max-w-xl text-base leading-relaxed text-muted sm:text-lg">
            Transférez de l’argent en quelques secondes sur une plateforme conçue pour rester disponible,
            même en cas d’attaque. Simple, transparent, rassurant.
          </p>

          {/* Boutons d'action : adaptés selon que l'utilisateur est connecté */}
          <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
            {isLoading ? (
              <>
                <Skeleton className="h-13 w-full rounded-xl sm:w-72" />
                <Skeleton className="h-13 w-full rounded-xl sm:w-40" />
              </>
            ) : isAuthenticated ? (
              <ButtonLink to="/dashboard" size="lg" rightIcon={<ArrowRight size={18} aria-hidden="true" />}>
                Accéder à mon espace
              </ButtonLink>
            ) : (
              <>
                <ButtonLink to="/signup" size="lg" rightIcon={<ArrowRight size={18} aria-hidden="true" />}>
                  Créer un compte gratuitement
                </ButtonLink>
                <ButtonLink to="/login" variant="secondary" size="lg">
                  Se connecter
                </ButtonLink>
              </>
            )}
          </div>

          <ul className="mt-8 flex flex-wrap gap-x-6 gap-y-2.5 text-sm text-muted">
            {trustItems.map(({ icon: Icon, label }) => (
              <li key={label} className="flex items-center gap-2">
                <Icon size={16} className="shrink-0 text-success" aria-hidden="true" />
                {label}
              </li>
            ))}
          </ul>
        </div>

        {/* Colonne illustration (en dessous sur mobile) */}
        <div className="animate-fade-up pt-6 pb-4 [animation-delay:150ms]">
          <HeroIllustration />
        </div>
      </div>
    </section>
  )
}
