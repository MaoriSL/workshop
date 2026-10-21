import { FlaskConical } from 'lucide-react'

/** Bandeau obligatoire rappelant que Poupal est un environnement fictif. */
export function DemoBanner() {
  return (
    <div className="bg-primary-dark text-white">
      <p className="container-page flex items-center justify-center gap-2 py-1.5 text-center text-xs font-medium tracking-wide">
        <FlaskConical size={14} aria-hidden="true" className="shrink-0 text-sky" />
        <span>Environnement de démonstration — plateforme fictive, aucun paiement réel.</span>
      </p>
    </div>
  )
}
