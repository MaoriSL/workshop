import { useId, useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { Mail, ShieldCheck, User } from 'lucide-react'
import { getErrorMessage } from '@/api'
import { Alert, Button, Card, Input, PasswordInput, Spinner } from '@/components/ui'
import { useAuth } from '@/hooks/useAuth'
import { usePageTitle } from '@/hooks/usePageTitle'
import { cn } from '@/utils/cn'
import { isValidEmail } from '@/utils/format'

interface FormValues {
  name: string
  email: string
  password: string
  confirm: string
  terms: boolean
}

/** Une erreur (optionnelle) par champ du formulaire. */
type FieldErrors = Partial<Record<keyof FormValues, string>>

/** Validation côté client, en français. Renvoie un objet vide si tout est correct. */
function validate(values: FormValues): FieldErrors {
  const errors: FieldErrors = {}
  if (values.name.trim().length < 2) errors.name = 'Indiquez votre nom complet.'
  if (!isValidEmail(values.email)) errors.email = 'Saisissez une adresse email valide.'
  if (values.password.length < 8) {
    errors.password = 'Le mot de passe doit contenir au moins 8 caractères.'
  }
  if (values.confirm !== values.password) errors.confirm = 'Les mots de passe ne correspondent pas.'
  if (!values.terms) errors.terms = 'Vous devez accepter les conditions générales pour continuer.'
  return errors
}

/**
 * Place le focus sur le premier champ en erreur (accessibilité clavier / lecteur d'écran).
 * Les champs portent le même attribut `name` que les clés de FormValues.
 */
function focusFirstInvalid(form: HTMLFormElement, errors: FieldErrors) {
  const firstKey = Object.keys(errors)[0]
  const field = firstKey ? form.elements.namedItem(firstKey) : null
  if (field instanceof HTMLElement) field.focus()
}

/* ---- Indicateur de robustesse du mot de passe ---- */
type StrengthLevel = 'weak' | 'medium' | 'strong'

/**
 * Libellé, couleur des barres et nombre de barres remplies par niveau.
 * Les couleurs de texte sont volontairement plus foncées que les jetons
 * warning / success pour garder un contraste lisible en petite taille.
 */
const strengthStyles: Record<StrengthLevel, { label: string; bar: string; text: string; filled: number }> = {
  weak: { label: 'faible', bar: 'bg-danger', text: 'text-danger', filled: 1 },
  medium: { label: 'moyenne', bar: 'bg-warning', text: 'text-amber-700', filled: 2 },
  strong: { label: 'forte', bar: 'bg-success', text: 'text-green-700', filled: 3 },
}

/**
 * Robustesse simple et lisible : longueur + variété de caractères
 * (minuscules, majuscules, chiffres, symboles).
 */
function getPasswordStrength(password: string): StrengthLevel {
  const variety = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((rule) => rule.test(password)).length
  if (password.length < 8 || variety <= 1) return 'weak'
  if (password.length >= 12 && variety >= 3) return 'strong'
  return 'medium'
}

function PasswordStrength({ password }: { password: string }) {
  if (password.length === 0) return null
  const level = getPasswordStrength(password)
  const { label, bar, text, filled } = strengthStyles[level]

  return (
    <div className="flex items-center gap-3">
      <div className="flex flex-1 gap-1" aria-hidden="true">
        {[1, 2, 3].map((segment) => (
          <span
            key={segment}
            className={cn('h-1.5 flex-1 rounded-full transition-colors duration-300', segment <= filled ? bar : 'bg-line')}
          />
        ))}
      </div>
      <p className="text-xs text-muted" aria-live="polite">
        Robustesse : <span className={cn('font-semibold', text)}>{label}</span>
      </p>
    </div>
  )
}

/** Page d'inscription : création d'un compte Poupal (fictif). */
export function SignupPage() {
  usePageTitle('Inscription')
  const { isAuthenticated, isLoading, signup } = useAuth()
  const navigate = useNavigate()
  const termsId = useId()

  const [values, setValues] = useState<FormValues>({ name: '', email: '', password: '', confirm: '', terms: false })
  const [errors, setErrors] = useState<FieldErrors>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Pendant la restauration de session, on évite d'afficher le formulaire pour rien.
  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size="lg" />
      </div>
    )
  }

  // Déjà connecté : direction l'espace client.
  if (isAuthenticated) return <Navigate to="/dashboard" replace />

  /** Met à jour un champ et efface son erreur dès que l'utilisateur corrige. */
  const update = <K extends keyof FormValues>(field: K, value: FormValues[K]) => {
    setValues((current) => ({ ...current, [field]: value }))
    setErrors((current) => {
      const next = { ...current, [field]: undefined }
      // Modifier le mot de passe peut aussi résoudre l'erreur de confirmation.
      if (field === 'password') next.confirm = undefined
      return next
    })
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const nextErrors = validate(values)
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length > 0) {
      focusFirstInvalid(event.currentTarget, nextErrors)
      return
    }

    setSubmitting(true)
    setSubmitError(null)
    try {
      await signup({ name: values.name.trim(), email: values.email.trim(), password: values.password })
      navigate('/dashboard', { replace: true })
    } catch (error) {
      setSubmitError(getErrorMessage(error, 'Inscription impossible. Veuillez réessayer.'))
      setSubmitting(false)
    }
  }

  return (
    <div className="animate-fade-up">
      <Card padding="none" className="p-6 sm:p-8">
        <div className="mb-6">
          <h1 className="text-2xl font-extrabold tracking-tight text-ink">Créer votre compte Poupal</h1>
          <p className="mt-1.5 text-sm text-muted">Quelques secondes suffisent pour envoyer et recevoir de l’argent.</p>
        </div>

        <form onSubmit={handleSubmit} noValidate className="space-y-5">
          {submitError && <Alert tone="error">{submitError}</Alert>}

          <Input
            label="Nom complet"
            type="text"
            name="name"
            autoComplete="name"
            placeholder="Alex Martin"
            leftIcon={<User size={18} aria-hidden="true" />}
            value={values.name}
            error={errors.name}
            onChange={(e) => update('name', e.target.value)}
          />

          <Input
            label="Adresse email"
            type="email"
            name="email"
            autoComplete="email"
            placeholder="vous@exemple.fr"
            leftIcon={<Mail size={18} aria-hidden="true" />}
            value={values.email}
            error={errors.email}
            onChange={(e) => update('email', e.target.value)}
          />

          <div className="space-y-2.5">
            <PasswordInput
              label="Mot de passe"
              name="password"
              autoComplete="new-password"
              hint="8 caractères minimum"
              value={values.password}
              error={errors.password}
              onChange={(e) => update('password', e.target.value)}
            />
            <PasswordStrength password={values.password} />
          </div>

          <PasswordInput
            label="Confirmer le mot de passe"
            name="confirm"
            autoComplete="new-password"
            value={values.confirm}
            error={errors.confirm}
            onChange={(e) => update('confirm', e.target.value)}
          />

          {/* Case à cocher : les conditions générales sont fictives (démonstration) */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor={termsId} className="flex cursor-pointer items-start gap-3 text-sm text-ink">
              <input
                id={termsId}
                type="checkbox"
                name="terms"
                checked={values.terms}
                aria-invalid={errors.terms ? true : undefined}
                aria-describedby={errors.terms ? `${termsId}-error` : undefined}
                onChange={(e) => update('terms', e.target.checked)}
                className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer rounded accent-accent"
              />
              <span>J’accepte les conditions générales (fictives) de Poupal.</span>
            </label>
            {errors.terms && (
              <p id={`${termsId}-error`} role="alert" className="text-sm font-medium text-danger">
                {errors.terms}
              </p>
            )}
          </div>

          <Button type="submit" size="lg" fullWidth loading={submitting}>
            Créer mon compte
          </Button>
        </form>

        <p className="mt-6 flex items-center justify-center gap-1.5 text-xs text-muted">
          <ShieldCheck size={14} aria-hidden="true" className="shrink-0 text-success" />
          Inscription fictive · aucune donnée réelle
        </p>
      </Card>

      <p className="mt-6 text-center text-sm text-muted">
        Déjà un compte ?{' '}
        <Link to="/login" className="font-semibold text-accent transition-colors hover:text-accent-hover hover:underline">
          Se connecter
        </Link>
      </p>
    </div>
  )
}
