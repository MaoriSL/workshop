import { useEffect, useState, type ReactNode } from 'react'
import { useParams } from 'react-router-dom'
import { ArrowLeft, Check, Clock, Copy, Download, RefreshCw, SearchX, Send, X } from 'lucide-react'
import { ApiError, getErrorMessage, getTransaction } from '@/api'
import {
  Alert,
  Avatar,
  Button,
  ButtonLink,
  Card,
  CardHeader,
  EmptyState,
  Skeleton,
  StatusBadge,
} from '@/components/ui'
import { usePageTitle } from '@/hooks/usePageTitle'
import type { SendDraft, Transaction, TransactionStatus } from '@/types'
import { cn } from '@/utils/cn'
import { formatCurrency, formatDateTime, formatSignedAmount } from '@/utils/format'

/**
 * État de chargement de la page, décrit par un seul objet :
 * impossible d'être à la fois "en chargement" et "en erreur".
 */
type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; transaction: Transaction }
  | { kind: 'not-found' }
  | { kind: 'error'; message: string }

/** Page "Détail d'une transaction" : /transactions/:id (rendue dans AppLayout). */
export function TransactionDetailPage() {
  const { id = '' } = useParams<{ id: string }>()
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  // Incrémenté par le bouton "Réessayer" pour relancer le chargement.
  const [attempt, setAttempt] = useState(0)

  usePageTitle(
    state.kind === 'ready' ? `Transaction ${state.transaction.reference}` : 'Détail de la transaction',
  )

  useEffect(() => {
    let cancelled = false // évite une mise à jour d'état après avoir quitté la page
    setState({ kind: 'loading' })

    getTransaction(id)
      .then((transaction) => {
        if (!cancelled) setState({ kind: 'ready', transaction })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        if (error instanceof ApiError && error.status === 404) {
          setState({ kind: 'not-found' })
        } else {
          setState({ kind: 'error', message: getErrorMessage(error) })
        }
      })

    return () => {
      cancelled = true
    }
  }, [id, attempt])

  return (
    <div className="mx-auto max-w-2xl animate-fade-up">
      <ButtonLink
        to="/dashboard"
        variant="ghost"
        size="sm"
        leftIcon={<ArrowLeft size={16} aria-hidden="true" />}
        className="-ml-3"
      >
        Tableau de bord
      </ButtonLink>

      <h1 className="mt-4 text-2xl font-bold text-ink sm:text-3xl">Détail de la transaction</h1>

      <div className="mt-6 space-y-5">
        {state.kind === 'loading' && <DetailSkeleton />}
        {state.kind === 'not-found' && <NotFound />}
        {state.kind === 'error' && (
          <LoadError message={state.message} onRetry={() => setAttempt((n) => n + 1)} />
        )}
        {state.kind === 'ready' && <TransactionDetail transaction={state.transaction} />}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Contenu principal                                                   */
/* ------------------------------------------------------------------ */

function TransactionDetail({ transaction }: { transaction: Transaction }) {
  const [showReceiptInfo, setShowReceiptInfo] = useState(false)
  const isReceived = transaction.type === 'received'
  const isFailed = transaction.status === 'failed'
  const isPending = transaction.status === 'pending'

  // Brouillon pré-rempli pour renvoyer de l'argent à la même personne (page /send).
  const draft: SendDraft = {
    recipient: transaction.counterpartyEmail ?? transaction.counterparty,
    amount: transaction.amount,
  }

  return (
    <>
      {isFailed && (
        <Alert tone="error" title="Ce paiement n'a pas abouti">
          <p>
            L'envoi vers {transaction.counterparty} a été refusé et aucun montant n'a été débité de
            votre compte. Vous pouvez relancer l'envoi avec les mêmes informations.
          </p>
          <ButtonLink
            to="/send"
            state={{ draft }}
            variant="danger"
            size="sm"
            className="mt-3"
            leftIcon={<RefreshCw size={14} aria-hidden="true" />}
          >
            Réessayer l'envoi
          </ButtonLink>
        </Alert>
      )}

      {/* Carte principale : contrepartie, montant, statut et frise d'avancement */}
      <Card padding="lg">
        <div className="flex flex-col items-center gap-5 text-center sm:flex-row sm:text-left">
          <Avatar name={transaction.counterparty} size="xl" />
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold tracking-wide text-muted uppercase">
              {isReceived ? 'Reçu de' : 'Envoyé à'}
            </p>
            <h2 className="mt-0.5 truncate text-xl font-bold text-ink">{transaction.counterparty}</h2>
            {transaction.counterpartyEmail && (
              <p className="truncate text-sm text-muted">{transaction.counterpartyEmail}</p>
            )}
          </div>
          <div className="flex flex-col items-center gap-2 sm:items-end">
            <p
              className={cn(
                'text-4xl font-extrabold tracking-tight',
                isFailed ? 'text-muted' : isReceived ? 'text-success' : 'text-ink',
              )}
            >
              {formatSignedAmount(transaction.type, transaction.amount)}
            </p>
            <StatusBadge status={transaction.status} />
          </div>
        </div>

        <hr className="my-6 border-line" />

        <StatusTimeline status={transaction.status} />
      </Card>

      {/* Carte "Détails" : liste de définitions */}
      <Card>
        <CardHeader title="Détails" description="Informations de la transaction" />
        <dl className="divide-y divide-line">
          <DetailRow label="Référence">
            <span className="font-mono">{transaction.reference}</span>
            <CopyButton value={transaction.reference} />
          </DetailRow>
          <DetailRow label="Date et heure">{formatDateTime(transaction.date)}</DetailRow>
          <DetailRow label="Type">{isReceived ? 'Réception' : 'Envoi'}</DetailRow>
          <DetailRow label="Montant">{formatCurrency(transaction.amount)}</DetailRow>
          <DetailRow label="Frais">{formatCurrency(0)}</DetailRow>
          {transaction.message && (
            <DetailRow label="Message">
              <span className="font-normal text-ink">« {transaction.message} »</span>
            </DetailRow>
          )}
        </dl>
      </Card>

      {/* Actions : pour un paiement échoué, le bouton "Réessayer" se trouve dans l'alerte */}
      {!isFailed && (
        <div className="flex flex-col gap-3 sm:flex-row">
          {transaction.type === 'sent' && (
            <ButtonLink to="/send" state={{ draft }} leftIcon={<Send size={16} aria-hidden="true" />}>
              Renvoyer de l'argent
            </ButtonLink>
          )}
          <Button
            variant="secondary"
            leftIcon={<Download size={16} aria-hidden="true" />}
            disabled={isPending}
            title={isPending ? 'Disponible une fois la transaction terminée' : undefined}
            onClick={() => setShowReceiptInfo(true)}
          >
            Télécharger le reçu
          </Button>
        </div>
      )}

      {showReceiptInfo && (
        <Alert tone="info" className="animate-fade-in">
          Le reçu PDF sera disponible dans la version complète de Poupal.
        </Alert>
      )}
    </>
  )
}

/* ------------------------------------------------------------------ */
/* Frise d'avancement : Initiée → Traitée → Terminée                   */
/* ------------------------------------------------------------------ */

type StepState = 'done' | 'pending' | 'failed' | 'upcoming'

/** Les 3 étapes de la frise, adaptées au statut de la transaction. */
function timelineSteps(status: TransactionStatus): { label: string; state: StepState }[] {
  switch (status) {
    case 'completed':
      return [
        { label: 'Initiée', state: 'done' },
        { label: 'Traitée', state: 'done' },
        { label: 'Terminée', state: 'done' },
      ]
    case 'pending':
      return [
        { label: 'Initiée', state: 'done' },
        { label: 'En attente', state: 'pending' },
        { label: 'Terminée', state: 'upcoming' },
      ]
    case 'failed':
      return [
        { label: 'Initiée', state: 'done' },
        { label: 'Échouée', state: 'failed' },
        { label: 'Terminée', state: 'upcoming' },
      ]
  }
}

/** Couleurs du point, du trait qui le précède et du libellé, par état d'étape. */
const stepStyles: Record<StepState, { dot: string; line: string; text: string; icon: ReactNode }> = {
  done: {
    dot: 'bg-success text-white',
    line: 'bg-success',
    text: 'text-ink',
    icon: <Check size={14} strokeWidth={3} aria-hidden="true" />,
  },
  pending: {
    dot: 'bg-warning text-white animate-pulse',
    line: 'bg-warning',
    text: 'text-amber-800',
    icon: <Clock size={14} aria-hidden="true" />,
  },
  failed: {
    dot: 'bg-danger text-white',
    line: 'bg-danger',
    text: 'text-red-800',
    icon: <X size={14} strokeWidth={3} aria-hidden="true" />,
  },
  upcoming: {
    dot: 'border-2 border-line bg-white',
    line: 'bg-line',
    text: 'text-muted',
    icon: null,
  },
}

function StatusTimeline({ status }: { status: TransactionStatus }) {
  const steps = timelineSteps(status)

  return (
    <ol className="flex" aria-label="Avancement de la transaction">
      {steps.map((step, index) => {
        const style = stepStyles[step.state]
        const isCurrent = step.state === 'pending' || step.state === 'failed'
        return (
          <li
            key={step.label}
            aria-current={isCurrent ? 'step' : undefined}
            className="relative flex flex-1 flex-col items-center gap-2 text-center"
          >
            {/* Trait reliant ce point au précédent (du centre précédent au centre courant) */}
            {index > 0 && (
              <span aria-hidden="true" className={cn('absolute top-3.5 right-1/2 -left-1/2 h-0.5', style.line)} />
            )}
            <span className={cn('relative z-10 flex h-7 w-7 items-center justify-center rounded-full', style.dot)}>
              {style.icon}
            </span>
            <span className={cn('text-xs font-semibold', style.text)}>{step.label}</span>
          </li>
        )
      })}
    </ol>
  )
}

/* ------------------------------------------------------------------ */
/* Petits composants de la carte "Détails"                             */
/* ------------------------------------------------------------------ */

function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1 py-3.5 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
      <dt className="shrink-0 text-sm text-muted">{label}</dt>
      <dd className="flex min-w-0 flex-wrap items-center gap-2 text-sm font-semibold break-words text-ink sm:justify-end sm:text-right">
        {children}
      </dd>
    </div>
  )
}

/**
 * Copie un texte dans le presse-papiers et renvoie true en cas de succès.
 * L'API Clipboard peut être refusée (iframe, navigateur restreint) : on
 * retombe alors sur la méthode historique (sélection + commande "copy").
 */
async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.setAttribute('readonly', '')
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    const copied = document.execCommand('copy')
    textarea.remove()
    return copied
  }
}

/** Copie une valeur dans le presse-papiers avec un retour visuel « Copié ! ». */
function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)

  // Le message « Copié ! » disparaît après 2 secondes.
  useEffect(() => {
    if (!copied) return
    const timer = setTimeout(() => setCopied(false), 2000)
    return () => clearTimeout(timer)
  }, [copied])

  async function copy() {
    if (await copyToClipboard(value)) setCopied(true)
  }

  return (
    <button
      type="button"
      onClick={copy}
      aria-label={copied ? 'Référence copiée' : 'Copier la référence'}
      className={cn(
        'inline-flex h-7 items-center gap-1 rounded-lg px-2 text-xs font-semibold transition-colors duration-200',
        copied ? 'bg-success-soft text-green-800' : 'bg-surface text-primary hover:bg-primary-soft',
      )}
    >
      {copied ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
      <span aria-live="polite">{copied ? 'Copié !' : 'Copier'}</span>
    </button>
  )
}

/* ------------------------------------------------------------------ */
/* États : chargement, introuvable, erreur                             */
/* ------------------------------------------------------------------ */

function DetailSkeleton() {
  return (
    <div aria-busy="true" aria-label="Chargement de la transaction" className="space-y-5">
      <Card padding="lg">
        <div className="flex flex-col items-center gap-5 sm:flex-row">
          <Skeleton className="h-16 w-16 rounded-full" />
          <div className="flex flex-1 flex-col items-center gap-2 sm:items-start">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-3 w-48" />
          </div>
          <div className="flex flex-col items-center gap-2 sm:items-end">
            <Skeleton className="h-9 w-36" />
            <Skeleton className="h-6 w-20 rounded-full" />
          </div>
        </div>
        <hr className="my-6 border-line" />
        <div className="flex">
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex flex-1 flex-col items-center gap-2">
              <Skeleton className="h-7 w-7 rounded-full" />
              <Skeleton className="h-3 w-14" />
            </div>
          ))}
        </div>
      </Card>
      <Card>
        <Skeleton className="h-5 w-24" />
        <div className="mt-6 space-y-5">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="flex items-center justify-between gap-6">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-36" />
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}

function NotFound() {
  return (
    <Card padding="none">
      <EmptyState
        icon={<SearchX size={26} aria-hidden="true" />}
        title="Transaction introuvable"
        description="Cette transaction n'existe pas ou n'est plus disponible dans votre historique."
        action={
          <ButtonLink to="/dashboard" leftIcon={<ArrowLeft size={16} aria-hidden="true" />}>
            Retour au tableau de bord
          </ButtonLink>
        }
      />
    </Card>
  )
}

function LoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Alert tone="error" title="Impossible de charger la transaction">
      <p>{message}</p>
      <Button
        variant="secondary"
        size="sm"
        className="mt-3"
        leftIcon={<RefreshCw size={14} aria-hidden="true" />}
        onClick={onRetry}
      >
        Réessayer
      </Button>
    </Alert>
  )
}
