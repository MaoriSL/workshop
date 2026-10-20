import { BadgeEuro, Globe, ShieldCheck, Zap } from 'lucide-react'
import { Card } from '@/components/ui'
import { SectionHeading } from './SectionHeading'

const features = [
  {
    icon: Zap,
    title: 'Instantané',
    text: 'Vos transferts arrivent en quelques secondes, à toute heure, sans délai bancaire.',
  },
  {
    icon: ShieldCheck,
    title: 'Sécurisé',
    text: 'Chiffrement, authentification forte et surveillance continue : votre argent est protégé.',
  },
  {
    icon: BadgeEuro,
    title: 'Sans frais cachés',
    text: 'Ce que vous voyez est ce que vous payez. Aucun frais surprise, jamais.',
  },
  {
    icon: Globe,
    title: 'Disponible partout',
    text: 'Sur mobile comme sur ordinateur, envoyez et recevez de l’argent où que vous soyez.',
  },
]

/** Section "Avantages" : 4 cartes avec icône. */
export function FeaturesSection() {
  return (
    <section id="avantages" aria-labelledby="avantages-titre" className="scroll-mt-20 py-20 sm:py-24">
      <div className="container-page">
        <SectionHeading
          titleId="avantages-titre"
          eyebrow="Avantages"
          title="Tout ce qu’il faut pour payer sereinement"
          description="Poupal réunit la simplicité d’une application de paiement et la robustesse d’une infrastructure pensée pour résister aux incidents."
        />

        <ul className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {features.map(({ icon: Icon, title, text }) => (
            <li key={title}>
              <Card hoverable className="group h-full">
                <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-accent-soft text-accent transition-colors duration-200 group-hover:bg-accent group-hover:text-white">
                  <Icon size={22} aria-hidden="true" />
                </span>
                <h3 className="mt-5 text-lg font-bold text-ink">{title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted">{text}</p>
              </Card>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
