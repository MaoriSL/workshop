import { Link } from 'react-router-dom'
import { ShieldCheck } from 'lucide-react'
import { Logo } from './Logo'

/** Liens factices du pied de page (aucune page réelle derrière). */
const columns = [
  { title: 'Produit', links: ['Envoyer de l’argent', 'Recevoir un paiement', 'Tarifs', 'Application mobile'] },
  { title: 'Entreprise', links: ['À propos', 'Carrières', 'Presse', 'Contact'] },
  { title: 'Ressources', links: ['Centre d’aide', 'Sécurité', 'Statut des services', 'Développeurs'] },
  { title: 'Légal', links: ['Conditions générales', 'Confidentialité', 'Cookies', 'Mentions légales'] },
]

/** Pied de page complet du site vitrine. */
export function Footer() {
  return (
    <footer className="bg-ink text-white">
      <div className="container-page py-12 lg:py-16">
        <div className="grid gap-10 lg:grid-cols-[1.4fr_repeat(4,1fr)]">
          <div className="max-w-xs">
            <div className="inline-flex rounded-2xl bg-white/95 px-3 py-2">
              <Logo variant="color" size={32} />
            </div>
            <p className="mt-4 text-sm leading-relaxed text-white/70">
              Poupal simplifie les paiements entre particuliers : rapide, transparent et sécurisé.
            </p>
            <p className="mt-4 inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1.5 text-xs font-semibold text-sky">
              <ShieldCheck size={14} aria-hidden="true" />
              Démonstrateur cyber-résilience
            </p>
          </div>

          {columns.map((column) => (
            <nav key={column.title} aria-label={column.title}>
              <h3 className="text-sm font-bold tracking-wide text-white/90 uppercase">{column.title}</h3>
              <ul className="mt-4 space-y-2.5">
                {column.links.map((label) => (
                  <li key={label}>
                    <a href="#" className="text-sm text-white/65 transition-colors hover:text-white">
                      {label}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        <div className="mt-12 flex flex-col gap-3 border-t border-white/10 pt-6 text-xs text-white/55 sm:flex-row sm:items-center sm:justify-between">
          <p>© 2026 Poupal — marque fictive créée pour le Workshop Resilience-Alpha (EPSI).</p>
          <p className="font-medium text-white/70">
            Environnement de démonstration — plateforme fictive, aucun paiement réel.
          </p>
        </div>
      </div>
    </footer>
  )
}

/** Version compacte du pied de page pour l'espace client et les pages d'auth. */
export function SlimFooter() {
  return (
    <footer className="border-t border-line bg-white">
      <div className="container-page flex flex-col gap-2 py-5 text-xs text-muted sm:flex-row sm:items-center sm:justify-between">
        <p>© 2026 Poupal — Environnement de démonstration, aucun paiement réel.</p>
        <nav aria-label="Liens secondaires" className="flex gap-4">
          <Link to="/" className="transition-colors hover:text-ink">
            Accueil
          </Link>
          <a href="#" className="transition-colors hover:text-ink">
            Aide
          </a>
          <a href="#" className="transition-colors hover:text-ink">
            Confidentialité
          </a>
        </nav>
      </div>
    </footer>
  )
}
