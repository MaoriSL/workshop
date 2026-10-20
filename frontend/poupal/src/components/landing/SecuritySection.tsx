import { BrainCircuit, CheckCircle2, LockKeyhole, Radar, RefreshCw, ShieldAlert } from 'lucide-react'
import { cn } from '@/utils/cn'
import { SectionHeading } from './SectionHeading'

/** Les trois piliers de la cyber-résilience mis en avant. */
const pillars = [
  {
    icon: LockKeyhole,
    title: 'Chiffrement de bout en bout',
    text: 'Vos données et vos transactions sont chiffrées en transit et au repos. Aucun secret ne circule en clair.',
  },
  {
    icon: BrainCircuit,
    title: 'Détection d’anomalies par IA',
    text: 'Un modèle apprend le comportement normal de la plateforme et repère tout écart suspect, sans seuils figés.',
  },
  {
    icon: RefreshCw,
    title: 'Reprise automatique, sans intervention humaine',
    text: 'En cas d’incident, le service se rétablit seul et une nouvelle transaction réussit : c’est notre preuve de résilience.',
  },
]

/** Scénario de démonstration illustré : attaque → détection → remédiation → vérification. */
const timeline = [
  { icon: ShieldAlert, label: 'Attaque détectée', detail: 'Trafic anormal sur l’API de paiement', time: 'T+0 s', tone: 'bg-rose-400/15 text-rose-300' },
  { icon: Radar, label: 'Analyse par l’IA', detail: 'Écart confirmé par le modèle', time: 'T+8 s', tone: 'bg-sky/15 text-sky' },
  { icon: RefreshCw, label: 'Remédiation automatique', detail: 'Service isolé puis redéployé', time: 'T+20 s', tone: 'bg-amber-400/15 text-amber-300' },
  { icon: CheckCircle2, label: 'Service rétabli', detail: 'Nouvelle transaction réussie', time: 'T+45 s', tone: 'bg-green-400/15 text-green-300' },
]

/** Bandeau sombre "Sécurité" : piliers de cyber-résilience + chaîne de reprise. */
export function SecuritySection() {
  return (
    <section id="securite" aria-labelledby="securite-titre" className="relative isolate scroll-mt-20 overflow-hidden bg-ink py-20 text-white sm:py-24">
      {/* Lueurs bleues en arrière-plan */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute -top-32 left-[-10%] h-96 w-96 rounded-full bg-accent/30 blur-3xl" />
        <div className="absolute right-[-10%] -bottom-32 h-96 w-96 rounded-full bg-sky/20 blur-3xl" />
      </div>

      <div className="container-page grid gap-12 lg:grid-cols-[1.1fr_0.9fr] lg:items-center lg:gap-16">
        {/* Colonne texte */}
        <div>
          <SectionHeading
            inverted
            align="left"
            titleId="securite-titre"
            eyebrow="Cyber-résilience"
            title="Conçue pour encaisser une attaque et se relever seule"
            description="Poupal est un démonstrateur de cyber-résilience : la plateforme détecte l’incident, se répare et le prouve en réussissant une nouvelle transaction, sans qu’aucun humain n’intervienne."
          />

          <ul className="mt-10 space-y-6">
            {pillars.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex gap-4">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white/10 text-sky ring-1 ring-white/15">
                  <Icon size={20} aria-hidden="true" />
                </span>
                <div>
                  <h3 className="font-bold text-white">{title}</h3>
                  <p className="mt-1 text-sm leading-relaxed text-white/65">{text}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        {/* Visuel : chaîne de résilience */}
        <div className="rounded-3xl border border-white/10 bg-white/5 p-5 shadow-card backdrop-blur-sm sm:p-7">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm font-bold">Chaîne de résilience</p>
            <span className="inline-flex items-center gap-2 rounded-full bg-success/20 px-2.5 py-1 text-xs font-semibold text-green-300">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-300 opacity-75 motion-reduce:animate-none" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-green-300" />
              </span>
              Services opérationnels
            </span>
          </div>

          <ol className="mt-6">
            {timeline.map(({ icon: Icon, label, detail, time, tone }, index) => (
              <li key={label} className="relative flex gap-4 pb-6 last:pb-0">
                {/* Trait vertical reliant les étapes */}
                {index < timeline.length - 1 && (
                  <span aria-hidden="true" className="absolute top-10 bottom-0 left-5 w-px bg-white/15" />
                )}
                <span className={cn('flex h-10 w-10 shrink-0 items-center justify-center rounded-full', tone)}>
                  <Icon size={18} aria-hidden="true" />
                </span>
                <div className="min-w-0 flex-1 pt-1.5">
                  <p className="text-sm font-bold">{label}</p>
                  <p className="text-xs text-white/60">{detail}</p>
                </div>
                <span className="shrink-0 pt-2 text-xs font-semibold text-white/40 tabular-nums">{time}</span>
              </li>
            ))}
          </ol>

          <p className="mt-6 border-t border-white/10 pt-4 text-xs text-white/50">
            Scénario de démonstration : 60 secondes, aucune action humaine.
          </p>
        </div>
      </div>
    </section>
  )
}
