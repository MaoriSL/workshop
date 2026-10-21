import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Mail, ShieldCheck, Sparkles } from 'lucide-react'
import { getErrorMessage, USE_MOCK } from '@/api'
import { Alert, Button, Card, Input, PasswordInput, Spinner } from '@/components/ui'
import { useAuth } from '@/hooks/useAuth'
import { usePageTitle } from '@/hooks/usePageTitle'
import { isValidEmail } from '@/utils/format'

/**
 * Compte de démonstration (Alex Martin), proposé uniquement en mode mock :
 * n'importe quel email valide accompagné d'un mot de passe de 8 caractères
 * minimum connecte l'utilisateur de démonstration. Ce n'est pas un secret.
 */
const DEMO_EMAIL = 'alex.martin@poupal.demo'
const DEMO_PASSWORD = 'x'.repeat(8)

interface FieldErrors {
  email?: string
  password?: string
}

/** Validation côté client, en français. Renvoie un objet vide si tout est correct. */
function validate(email: string, password: string): FieldErrors {
  const errors: FieldErrors = {}
  if (!isValidEmail(email)) errors.email = 'Saisissez une adresse email valide.'
  if (password.length < 8) errors.password = 'Le mot de passe doit contenir au moins 8 caractères.'
  return errors
}

/**
 * Place le focus sur le premier champ en erreur (accessibilité clavier / lecteur d'écran).
 * Les champs portent le même attribut `name` que les clés de FieldErrors.
 */
function focusFirstInvalid(form: HTMLFormElement, errors: FieldErrors) {
  const firstKey = Object.keys(errors)[0]
  const field = firstKey ? form.elements.namedItem(firstKey) : null
  if (field instanceof HTMLElement) field.focus()
}

/** Page de connexion à l'espace client. */
export function LoginPage() {
  usePageTitle('Connexion')
  const { isAuthenticated, isLoading, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<FieldErrors>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Page demandée avant la redirection vers /login (mémorisée par ProtectedRoute).
  // Sert à la fois au garde « déjà connecté » et à la navigation après login : si
  // la session se met à jour avant que navigate() ne soit appliqué, les deux
  // chemins visent la même destination (sinon /dashboard gagnait toujours).
  const from = (location.state as { from?: string } | null)?.from
  const redirectTo = from ?? '/dashboard'

  // Pendant la restauration de session, on évite d'afficher le formulaire pour rien.
  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size="lg" />
      </div>
    )
  }

  // Déjà connecté : direction la page demandée (ou l'espace client).
  if (isAuthenticated) return <Navigate to={redirectTo} replace />

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const nextErrors = validate(email, password)
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length > 0) {
      focusFirstInvalid(event.currentTarget, nextErrors)
      return
    }

    setSubmitting(true)
    setSubmitError(null)
    try {
      await login({ email: email.trim(), password })
      navigate(redirectTo, { replace: true })
    } catch (error) {
      setSubmitError(getErrorMessage(error, 'Connexion impossible. Veuillez réessayer.'))
      setSubmitting(false)
    }
  }

  /** Pré-remplit le formulaire avec le compte de démonstration. */
  const fillDemoAccount = () => {
    setEmail(DEMO_EMAIL)
    setPassword(DEMO_PASSWORD)
    setErrors({})
    setSubmitError(null)
  }

  return (
    <div className="animate-fade-up">
      <Card padding="none" className="p-6 sm:p-8">
        <div className="mb-6">
          <h1 className="text-2xl font-extrabold tracking-tight text-ink">Bon retour !</h1>
          <p className="mt-1.5 text-sm text-muted">Connectez-vous pour accéder à votre espace Poupal.</p>
        </div>

        <form onSubmit={handleSubmit} noValidate className="space-y-5">
          {submitError && <Alert tone="error">{submitError}</Alert>}

          <Input
            label="Adresse email"
            type="email"
            name="email"
            autoComplete="email"
            placeholder="vous@exemple.fr"
            leftIcon={<Mail size={18} aria-hidden="true" />}
            value={email}
            error={errors.email}
            onChange={(e) => {
              setEmail(e.target.value)
              // L'erreur disparaît dès que l'utilisateur corrige le champ.
              if (errors.email) setErrors({ ...errors, email: undefined })
            }}
          />

          <div className="space-y-2">
            <PasswordInput
              label="Mot de passe"
              name="password"
              autoComplete="current-password"
              placeholder="8 caractères minimum"
              value={password}
              error={errors.password}
              onChange={(e) => {
                setPassword(e.target.value)
                if (errors.password) setErrors({ ...errors, password: undefined })
              }}
            />
            <div className="flex justify-end">
              <Link
                to="/forgot-password"
                className="text-sm font-semibold text-primary transition-colors hover:text-accent"
              >
                Mot de passe oublié ?
              </Link>
            </div>
          </div>

          <Button type="submit" size="lg" fullWidth loading={submitting}>
            Se connecter
          </Button>
        </form>

        {/* Raccourci pour la démo (mode mock uniquement) : pré-remplit les identifiants fictifs */}
        {USE_MOCK && (
          <>
        <div className="mt-6 flex items-center gap-3 text-xs text-muted">
          <span className="h-px flex-1 bg-line" aria-hidden="true" />
          ou
          <span className="h-px flex-1 bg-line" aria-hidden="true" />
        </div>
        <button
          type="button"
          onClick={fillDemoAccount}
          className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-line px-4 py-3 text-sm font-semibold text-primary transition-all hover:border-accent/50 hover:bg-accent-soft/60"
        >
          <Sparkles size={16} aria-hidden="true" className="text-accent" />
          Utiliser le compte de démonstration
        </button>
          </>
        )}

        <p className="mt-6 flex items-center justify-center gap-1.5 text-xs text-muted">
          <ShieldCheck size={14} aria-hidden="true" className="shrink-0 text-success" />
          Connexion sécurisée · aucune donnée réelle
        </p>
      </Card>

      <p className="mt-6 text-center text-sm text-muted">
        Pas encore de compte ?{' '}
        <Link to="/signup" className="font-semibold text-accent transition-colors hover:text-accent-hover hover:underline">
          Créer un compte
        </Link>
      </p>
    </div>
  )
}
