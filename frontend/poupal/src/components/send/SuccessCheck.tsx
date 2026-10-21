/**
 * Coche de succès animée : le cercle vert « pop », puis le trait de la coche
 * se dessine (animate-draw fait passer stroke-dashoffset de 60 à 0).
 * Le tracé mesure environ 60 unités : le dessin occupe toute l'animation.
 * Purement décoratif (aria-hidden) : le titre de la page annonce le succès.
 */
export function SuccessCheck() {
  return (
    <div
      aria-hidden="true"
      className="mx-auto flex h-24 w-24 animate-pop items-center justify-center rounded-full bg-success-soft"
    >
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-success text-white shadow-[0_12px_30px_-10px_rgba(22,163,74,0.7)]">
        <svg viewBox="0 0 72 72" className="h-9 w-9" fill="none" stroke="currentColor" strokeWidth={6} strokeLinecap="round" strokeLinejoin="round">
          <path d="M16 38 L30 52 L56 22" strokeDasharray={60} strokeDashoffset={60} className="animate-draw" />
        </svg>
      </div>
    </div>
  )
}
