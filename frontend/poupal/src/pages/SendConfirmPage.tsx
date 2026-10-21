import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { MessageSquare, Pencil, Send } from 'lucide-react'
import { getErrorMessage, sendMoney } from '@/api'
import { Alert, Avatar, Button, Card } from '@/components/ui'
import { SendStepper } from '@/components/send'
import { usePageTitle } from '@/hooks/usePageTitle'
import { formatCurrency, isValidEmail } from '@/utils/format'
import type { SendDraft } from '@/types'

/**
 * Étape 2 du flux d'envoi : récapitulatif avant validation.
 * Le brouillon arrive via l'état du routeur ; sans brouillon (accès direct à
 * l'URL), on renvoie vers /send. « Modifier » renvoie le brouillon au formulaire,
 * « Confirmer » appelle l'API puis passe à l'écran de succès avec la transaction.
 */
export function SendConfirmPage() {
  usePageTitle("Confirmer l'envoi")
  const navigate = useNavigate()
  const location = useLocation()
  const draft = (location.state as { draft?: SendDraft } | null)?.draft

  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!draft) return <Navigate to="/send" replace />

  const recipientIsEmail = isValidEmail(draft.recipient)

  async function handleConfirm() {
    if (!draft) return
    setSubmitting(true)
    setError(null)
    try {
      const transaction = await sendMoney(draft)
      navigate('/send/success', { replace: true, state: { transaction } })
    } catch (err) {
      setError(getErrorMessage(err, "L'envoi n'a pas pu être effectué. Veuillez réessayer."))
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-lg animate-fade-up">
      <SendStepper current={2} className="mb-6 sm:mb-8" />

      <Card padding="none" className="p-5 sm:p-8">
        <header>
          <h1 className="text-2xl font-bold text-ink">Confirmez votre envoi</h1>
          <p className="mt-1.5 text-sm text-muted">Vérifiez les informations avant de valider.</p>
        </header>

        {/* Destinataire et montant, mis en avant */}
        <div className="mt-6 flex flex-col items-center text-center">
          <Avatar name={draft.recipient} size="xl" />
          <p className="mt-3 text-lg font-bold break-all text-ink">{draft.recipient}</p>
          {recipientIsEmail && (
            <p className="mt-0.5 text-sm text-muted">Compte Poupal associé à cette adresse</p>
          )}
          <p className="mt-5 text-4xl font-extrabold tracking-tight text-ink sm:text-5xl">
            {formatCurrency(draft.amount)}
          </p>
        </div>

        {/* Détail des frais et du total */}
        <dl className="mt-6 divide-y divide-line rounded-xl bg-surface px-4 text-sm">
          <div className="flex items-center justify-between gap-4 py-3">
            <dt className="text-muted">Montant envoyé</dt>
            <dd className="font-semibold text-ink">{formatCurrency(draft.amount)}</dd>
          </div>
          <div className="flex items-center justify-between gap-4 py-3">
            <dt className="text-muted">Frais</dt>
            <dd className="font-semibold text-ink">
              {formatCurrency(0)} <span className="font-medium text-success">(gratuit)</span>
            </dd>
          </div>
          <div className="flex items-center justify-between gap-4 py-3">
            <dt className="font-semibold text-ink">Total débité</dt>
            <dd className="text-base font-bold text-ink">{formatCurrency(draft.amount)}</dd>
          </div>
        </dl>

        {draft.message && (
          <div className="mt-4 flex gap-3 rounded-xl border border-line px-4 py-3 text-sm">
            <MessageSquare size={18} className="mt-0.5 shrink-0 text-muted" aria-hidden="true" />
            <div className="min-w-0">
              <p className="text-xs font-semibold tracking-wide text-muted uppercase">Message</p>
              <p className="mt-0.5 break-words text-ink">{draft.message}</p>
            </div>
          </div>
        )}

        <Alert tone="info" className="mt-4">
          Environnement de démonstration : aucun paiement réel ne sera effectué.
        </Alert>

        {error && (
          <Alert tone="error" title="Envoi impossible" className="mt-4">
            {error}
          </Alert>
        )}

        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row">
          <Button
            variant="secondary"
            fullWidth
            className="sm:flex-1"
            disabled={submitting}
            leftIcon={<Pencil size={16} aria-hidden="true" />}
            onClick={() => navigate('/send', { state: { draft } })}
          >
            Modifier
          </Button>
          <Button
            variant="primary"
            fullWidth
            className="sm:flex-1"
            loading={submitting}
            rightIcon={<Send size={16} aria-hidden="true" />}
            onClick={handleConfirm}
          >
            Confirmer l'envoi
          </Button>
        </div>
      </Card>
    </div>
  )
}
