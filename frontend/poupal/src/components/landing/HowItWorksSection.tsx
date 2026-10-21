import { Send, UserRoundPlus, Users } from 'lucide-react'
import { SectionHeading } from './SectionHeading'

const steps = [
  {
    icon: UserRoundPlus,
    title: 'Créez votre compte',
    text: 'Une adresse email, un mot de passe : votre espace Poupal est prêt en moins d’une minute.',
  },
  {
    icon: Users,
    title: 'Ajoutez un destinataire',
    text: 'Saisissez simplement l’email de la personne à qui vous souhaitez envoyer de l’argent.',
  },
  {
    icon: Send,
    title: 'Envoyez en un clic',
    text: 'Indiquez le montant, vérifiez le récapitulatif, confirmez : le transfert part instantanément.',
  },
]

/** Section "Comment ça marche" : 3 étapes numérotées reliées par une ligne pointillée (desktop). */
export function HowItWorksSection() {
  return (
    <section id="comment-ca-marche" aria-labelledby="etapes-titre" className="scroll-mt-20 bg-surface py-20 sm:py-24">
      <div className="container-page">
        <SectionHeading
          titleId="etapes-titre"
          eyebrow="Comment ça marche"
          title="Trois étapes, et c’est envoyé"
          description="Pas de RIB à recopier, pas d’attente : Poupal rend l’envoi d’argent aussi simple qu’un message."
        />

        <div className="relative mt-14">
          {/* Ligne pointillée reliant les trois étapes (masquée sur mobile) */}
          <div
            aria-hidden="true"
            className="absolute top-7 right-[16.67%] left-[16.67%] hidden border-t-2 border-dashed border-primary/20 md:block"
          />

          <ol className="grid gap-10 md:grid-cols-3 md:gap-8">
            {steps.map(({ icon: Icon, title, text }, index) => (
              <li key={title} className="flex flex-col items-center text-center">
                <span className="relative flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-gradient text-white shadow-glow">
                  <Icon size={24} aria-hidden="true" />
                  <span className="absolute -top-2 -right-2 flex h-6 w-6 items-center justify-center rounded-full bg-white text-xs font-extrabold text-primary shadow-soft ring-1 ring-line">
                    {index + 1}
                  </span>
                </span>
                <h3 className="mt-6 text-lg font-bold text-ink">{title}</h3>
                <p className="mt-2 max-w-xs text-sm leading-relaxed text-muted">{text}</p>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  )
}
