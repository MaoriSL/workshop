import { startTransition, useEffect, useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { LayoutDashboard, LogOut, Menu, Send, X } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { Avatar, Button, ButtonLink } from '@/components/ui'
import { cn } from '@/utils/cn'
import { Logo } from './Logo'

/** Liens du site vitrine (ancres de la landing). */
const publicLinks = [
  { label: 'Avantages', href: '/#avantages' },
  { label: 'Comment ça marche', href: '/#comment-ca-marche' },
  { label: 'Sécurité', href: '/#securite' },
]

/** Liens de l'espace client. */
const appLinks = [
  { label: 'Tableau de bord', to: '/dashboard', icon: LayoutDashboard },
  { label: 'Envoyer', to: '/send', icon: Send },
]

const navLinkClasses = ({ isActive }: { isActive: boolean }) =>
  cn(
    'rounded-lg px-3 py-2 text-sm font-semibold transition-colors',
    isActive ? 'bg-primary-soft text-primary' : 'text-muted hover:bg-surface hover:text-ink',
  )

/**
 * En-tête commun. Affiche la navigation du site vitrine ou celle de
 * l'espace client selon que l'utilisateur est connecté ou non.
 */
export function Header() {
  const { user, isAuthenticated, logout } = useAuth()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)

  // Ferme le menu mobile avec la touche Échap
  useEffect(() => {
    if (!menuOpen) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setMenuOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [menuOpen])

  const handleLogout = () => {
    setMenuOpen(false)
    // react-router applique la navigation dans une transition React, alors que
    // logout() (setUser(null)) serait appliqué immédiatement : ProtectedRoute
    // verrait l'utilisateur déconnecté encore sur /dashboard et redirigerait vers
    // /login. En groupant les deux dans la même transition, l'accueil est rendu
    // directement avec l'utilisateur déconnecté.
    startTransition(() => {
      logout()
      navigate('/')
    })
  }

  return (
    <header className="sticky top-0 z-40 border-b border-line/80 bg-white/90 backdrop-blur-md">
      <div className="container-page flex h-16 items-center justify-between gap-4">
        <Logo size={38} />

        {/* Navigation desktop */}
        <nav aria-label="Navigation principale" className="hidden items-center gap-1 md:flex">
          {isAuthenticated
            ? appLinks.map(({ label, to }) => (
                <NavLink key={to} to={to} className={navLinkClasses}>
                  {label}
                </NavLink>
              ))
            : publicLinks.map(({ label, href }) => (
                <Link
                  key={href}
                  to={href}
                  className="rounded-lg px-3 py-2 text-sm font-semibold text-muted transition-colors hover:bg-surface hover:text-ink"
                >
                  {label}
                </Link>
              ))}
        </nav>

        {/* Actions desktop */}
        <div className="hidden items-center gap-3 md:flex">
          {isAuthenticated && user ? (
            <>
              <Link
                to="/dashboard"
                className="flex items-center gap-2.5 rounded-full py-1 pr-3 pl-1 transition-colors hover:bg-surface"
              >
                <Avatar name={user.name} size="sm" />
                <span className="text-sm font-semibold text-ink">{user.name}</span>
              </Link>
              <Button variant="ghost" size="sm" onClick={handleLogout} leftIcon={<LogOut size={16} aria-hidden="true" />}>
                Déconnexion
              </Button>
            </>
          ) : (
            <>
              <ButtonLink to="/login" variant="ghost" size="sm">
                Connexion
              </ButtonLink>
              <ButtonLink to="/signup" variant="primary" size="sm">
                Créer un compte
              </ButtonLink>
            </>
          )}
        </div>

        {/* Bouton menu mobile */}
        <button
          type="button"
          className="rounded-lg p-2 text-ink transition-colors hover:bg-surface md:hidden"
          aria-expanded={menuOpen}
          aria-controls="mobile-menu"
          aria-label={menuOpen ? 'Fermer le menu' : 'Ouvrir le menu'}
          onClick={() => setMenuOpen((open) => !open)}
        >
          {menuOpen ? <X size={22} aria-hidden="true" /> : <Menu size={22} aria-hidden="true" />}
        </button>
      </div>

      {/* Menu mobile */}
      {menuOpen && (
        <div id="mobile-menu" className="animate-fade-in border-t border-line bg-white md:hidden">
          <nav aria-label="Navigation mobile" className="container-page flex flex-col gap-1 py-3">
            {isAuthenticated && user ? (
              <>
                <div className="mb-2 flex items-center gap-3 rounded-xl bg-surface px-3 py-3">
                  <Avatar name={user.name} size="md" />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-bold text-ink">{user.name}</p>
                    <p className="truncate text-xs text-muted">{user.email}</p>
                  </div>
                </div>
                {appLinks.map(({ label, to, icon: Icon }) => (
                  <NavLink
                    key={to}
                    to={to}
                    onClick={() => setMenuOpen(false)}
                    className={({ isActive }) => cn(navLinkClasses({ isActive }), 'flex items-center gap-3 py-3')}
                  >
                    <Icon size={18} aria-hidden="true" />
                    {label}
                  </NavLink>
                ))}
                <button
                  type="button"
                  onClick={handleLogout}
                  className="flex items-center gap-3 rounded-lg px-3 py-3 text-left text-sm font-semibold text-danger transition-colors hover:bg-danger-soft"
                >
                  <LogOut size={18} aria-hidden="true" />
                  Déconnexion
                </button>
              </>
            ) : (
              <>
                {publicLinks.map(({ label, href }) => (
                  <Link
                    key={href}
                    to={href}
                    onClick={() => setMenuOpen(false)}
                    className="rounded-lg px-3 py-3 text-sm font-semibold text-ink transition-colors hover:bg-surface"
                  >
                    {label}
                  </Link>
                ))}
                <div className="mt-2 flex flex-col gap-2 border-t border-line pt-3">
                  <ButtonLink to="/login" variant="secondary" fullWidth onClick={() => setMenuOpen(false)}>
                    Connexion
                  </ButtonLink>
                  <ButtonLink to="/signup" variant="primary" fullWidth onClick={() => setMenuOpen(false)}>
                    Créer un compte
                  </ButtonLink>
                </div>
              </>
            )}
          </nav>
        </div>
      )}
    </header>
  )
}
