import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Mail, MailCheck } from 'lucide-react'
import { Button, ButtonLink, Card, Input } from '@/components/ui'
import { usePageTitle } from '@/hooks/usePageTitle'
import { isValidEmail } from '@/utils/format'

/** Durée de la soumission simulée (aucun appel API : simple délai). */
const FAKE_SEND_DELAY_MS = 800

/** Page "Mot de passe oublié" : demande de lien de réinitialisation (simulée). */
export function ForgotPasswordPage() {
  usePageTitle('Mot de passe oublié')

  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | undefined>()
  const [submitting, setSubmitting] = useState(false)
  const [sent, setSent] = useState(false)
  const timer = useRef<number | undefined>(undefined)
  const confirmationTitle = useRef<HTMLHeadingElement>(null)

  // Si l'utilisateur quitte la page pendant le délai, on annule le minuteur.
  useEffect(() => () => window.clearTimeout(timer.current), [])

  // À l'affichage de la confirmation, le focus va sur son titre (lecteurs d'écran).
  useEffect(() => {
    if (sent) confirmationTitle.current?.focus()
  }, [sent])

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!isValidEmail(email)) {
      setError('Saisissez une adresse email valide.')
      // Le focus revient sur le champ pour corriger immédiatement.
      const field = event.currentTarget.elements.namedItem('email')
      if (field instanceof HTMLElement) field.focus()
      return
    }
    setSubmitting(true)
    timer.current = window.setTimeout(() => {
      setSubmitting(false)
      setSent(true)
    }, FAKE_SEND_DELAY_MS)
  }

  /** Permet de recommencer avec une autre adresse. */
  const reset = () => {
    setSent(false)
    setEmail('')
  }

  // --- Écran de confirmation ---
  if (sent) {
    return (
      <div className="animate-fade-up">
        <Card padding="none" className="p-6 text-center sm:p-8">
          <span className="mx-auto flex h-16 w-16 animate-pop items-center justify-center rounded-full bg-success-soft text-success">
            <MailCheck size={30} aria-hidden="true" />
          </span>
          <h1 ref={confirmationTitle} tabIndex={-1} className="mt-5 text-2xl font-extrabold tracking-tight text-ink">
            Vérifiez votre boîte mail
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-muted" role="status">
            Si un compte existe pour cet email, un lien de réinitialisation a été envoyé.
          </p>
          <p className="mt-3 inline-block max-w-full truncate rounded-full bg-surface px-3 py-1 text-sm font-semibold text-ink">
            {email.trim()}
          </p>

          <div className="mt-8 space-y-3">
            <ButtonLink to="/login" variant="primary" size="lg" fullWidth leftIcon={<ArrowLeft size={18} aria-hidden="true" />}>
              Retour à la connexion
            </ButtonLink>
            <Button variant="ghost" fullWidth onClick={reset}>
              Essayer une autre adresse
            </Button>
          </div>
        </Card>
      </div>
    )
  }

  // --- Formulaire ---
  return (
    <div className="animate-fade-up">
      <Card padding="none" className="p-6 sm:p-8">
        <div className="mb-6">
          <h1 className="text-2xl font-extrabold tracking-tight text-ink">Mot de passe oublié</h1>
          <p className="mt-1.5 text-sm text-muted">
            Indiquez votre adresse email : nous vous enverrons un lien pour choisir un nouveau mot de passe.
          </p>
        </div>

        <form onSubmit={handleSubmit} noValidate className="space-y-5">
          <Input
            label="Adresse email"
            type="email"
            name="email"
            autoComplete="email"
            placeholder="vous@exemple.fr"
            leftIcon={<Mail size={18} aria-hidden="true" />}
            value={email}
            error={error}
            onChange={(e) => {
              setEmail(e.target.value)
              // L'erreur disparaît dès que l'utilisateur corrige le champ.
              if (error) setError(undefined)
            }}
          />

          <Button type="submit" size="lg" fullWidth loading={submitting}>
            Envoyer le lien
          </Button>
        </form>

        <Link
          to="/login"
          className="mt-6 inline-flex items-center gap-1.5 text-sm font-semibold text-primary transition-colors hover:text-accent"
        >
          <ArrowLeft size={16} aria-hidden="true" />
          Retour à la connexion
        </Link>
      </Card>
    </div>
  )
}
