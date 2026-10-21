import { useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ArrowRight, AtSign, ShieldCheck } from 'lucide-react'
import { getAccount } from '@/api'
import { Button, Card, Input, Textarea } from '@/components/ui'
import { RecentRecipients, SendStepper } from '@/components/send'
import { usePageTitle } from '@/hooks/usePageTitle'
import { CURRENCY_SYMBOL, formatAmountInput, formatCurrency, parseAmount } from '@/utils/format'
import { cn } from '@/utils/cn'
import type { Account, SendDraft } from '@/types'

/** Montants proposés en un clic, en euros. */
const QUICK_AMOUNTS = [10, 20, 50, 100]
const MESSAGE_MAX_LENGTH = 140

interface FormErrors {
  recipient?: string
  amount?: string
}

/** 25.5 → "25,50" : affichage français d'un montant dans le champ de saisie. */
/**
 * Étape 1 du flux d'envoi : saisie du destinataire, du montant et d'un message.
 * Le formulaire est validé au submit, puis le brouillon (SendDraft) est transmis
 * à /send/confirm via l'état du routeur. Si l'utilisateur revient depuis la
 * confirmation (« Modifier »), les champs sont pré-remplis depuis location.state.
 */
export function SendPage() {
  usePageTitle("Envoyer de l'argent")
  const navigate = useNavigate()
  const location = useLocation()
  const draft = (location.state as { draft?: SendDraft } | null)?.draft

  const [recipient, setRecipient] = useState(draft?.recipient ?? '')
  const [amount, setAmount] = useState(draft ? formatAmountInput(draft.amount) : '')
  const [message, setMessage] = useState(draft?.message ?? '')
  const [errors, setErrors] = useState<FormErrors>({})
  // Solde : en cours de chargement (undefined), indisponible (null) ou connu
  const [account, setAccount] = useState<Account | null | undefined>(undefined)

  // Solde disponible, affiché sous le champ montant et utilisé pour la validation.
  useEffect(() => {
    let cancelled = false
    getAccount()
      .then((data) => {
        if (!cancelled) setAccount(data)
      })
      .catch(() => {
        // Solde indisponible (API injoignable) : l'API vérifiera elle-même le solde à l'envoi.
        if (!cancelled) setAccount(null)
      })
    return () => {
      cancelled = true
    }
  }, [])

  function validate(): FormErrors {
    const next: FormErrors = {}
    if (recipient.trim().length < 2) {
      next.recipient = 'Indiquez un destinataire (2 caractères minimum).'
    }
    const value = parseAmount(amount)
    if (Number.isNaN(value)) {
      next.amount = 'Saisissez un montant valide, avec 2 décimales maximum (ex. 25,50).'
    } else if (value <= 0) {
      next.amount = 'Le montant doit être supérieur à zéro.'
    } else if (account && value > account.balance) {
      next.amount = `Montant supérieur à votre solde disponible (${formatCurrency(account.balance)}).`
    }
    return next
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const nextErrors = validate()
    setErrors(nextErrors)
    if (nextErrors.recipient || nextErrors.amount) return

    const nextDraft: SendDraft = {
      recipient: recipient.trim(),
      amount: parseAmount(amount),
      message: message.trim() || undefined,
    }
    navigate('/send/confirm', { state: { draft: nextDraft } })
  }

  function handleRecipientChange(value: string) {
    setRecipient(value)
    setErrors((prev) => ({ ...prev, recipient: undefined }))
  }

  function handleAmountChange(value: string) {
    setAmount(value)
    setErrors((prev) => ({ ...prev, amount: undefined }))
  }

  const balanceHint =
    account === undefined
      ? 'Chargement du solde…'
      : account === null
        ? 'Solde indisponible pour le moment : le montant sera vérifié à l’envoi.'
        : `Solde disponible : ${formatCurrency(account.balance)}`

  return (
    <div className="mx-auto max-w-lg animate-fade-up">
      <SendStepper current={1} className="mb-6 sm:mb-8" />

      <Card padding="none" className="p-5 sm:p-8">
        <header>
          <h1 className="text-2xl font-bold text-ink">Envoyer de l'argent</h1>
          <p className="mt-1.5 flex items-center gap-1.5 text-sm text-muted">
            <ShieldCheck size={16} className="shrink-0 text-success" aria-hidden="true" />
            Transfert instantané, gratuit et sécurisé.
          </p>
        </header>

        <form noValidate onSubmit={handleSubmit} className="mt-6 space-y-6">
          {/* Destinataire + suggestions issues des dernières transactions */}
          <div>
            <Input
              label="Destinataire"
              type="text"
              autoComplete="off"
              placeholder="Email ou nom du destinataire"
              leftIcon={<AtSign size={18} aria-hidden="true" />}
              value={recipient}
              onChange={(event) => handleRecipientChange(event.target.value)}
              error={errors.recipient}
            />
            <RecentRecipients selected={recipient} onSelect={handleRecipientChange} />
          </div>

          {/* Montant + raccourcis */}
          <div>
            <Input
              label="Montant"
              type="text"
              inputMode="decimal"
              autoComplete="off"
              placeholder="0,00"
              rightElement={
                <span className="px-2 text-sm font-semibold text-muted" aria-hidden="true">
                  {CURRENCY_SYMBOL}
                </span>
              }
              value={amount}
              onChange={(event) => handleAmountChange(event.target.value)}
              error={errors.amount}
              hint={balanceHint}
            />
            <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Montants rapides">
              {QUICK_AMOUNTS.map((value) => {
                const isSelected = parseAmount(amount) === value
                return (
                  <button
                    key={value}
                    type="button"
                    onClick={() => handleAmountChange(formatAmountInput(value))}
                    aria-pressed={isSelected}
                    className={cn(
                      'rounded-full border bg-white px-3.5 py-1.5 text-sm font-semibold text-primary',
                      'transition-all duration-200 hover:-translate-y-px hover:border-accent/40 hover:bg-accent-soft/60',
                      isSelected ? 'border-accent bg-accent-soft ring-2 ring-accent/15' : 'border-line',
                    )}
                  >
                    {formatCurrency(value)}
                  </button>
                )
              })}
            </div>
          </div>

          <Textarea
            label="Message (optionnel)"
            placeholder="Ex. : Remboursement du restaurant"
            rows={3}
            maxLength={MESSAGE_MAX_LENGTH}
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            hint={`${message.length}/${MESSAGE_MAX_LENGTH} caractères`}
          />

          <div className="flex flex-col-reverse gap-3 pt-2 sm:flex-row sm:items-center sm:justify-between">
            <Link
              to="/dashboard"
              className="text-center text-sm font-semibold text-muted transition-colors hover:text-ink"
            >
              Annuler
            </Link>
            <Button type="submit" fullWidth className="sm:w-auto" rightIcon={<ArrowRight size={18} aria-hidden="true" />}>
              Continuer
            </Button>
          </div>
        </form>
      </Card>
    </div>
  )
}
