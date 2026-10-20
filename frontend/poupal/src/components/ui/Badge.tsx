import type { ReactNode } from 'react'
import { CheckCircle2, Clock, XCircle } from 'lucide-react'
import type { TransactionStatus } from '@/types'
import { cn } from '@/utils/cn'

type BadgeTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

const tones: Record<BadgeTone, string> = {
  success: 'bg-success-soft text-green-800',
  warning: 'bg-warning-soft text-amber-800',
  danger: 'bg-danger-soft text-red-800',
  info: 'bg-accent-soft text-primary',
  neutral: 'bg-surface text-muted',
}

interface BadgeProps {
  tone?: BadgeTone
  icon?: ReactNode
  className?: string
  children: ReactNode
}

/** Pastille générique : <Badge tone="info">Nouveau</Badge> */
export function Badge({ tone = 'neutral', icon, className, children }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold whitespace-nowrap',
        tones[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  )
}

/** Libellés et couleurs associés à chaque statut de transaction. */
export const statusConfig: Record<TransactionStatus, { label: string; tone: BadgeTone; icon: ReactNode }> = {
  completed: { label: 'Réussi', tone: 'success', icon: <CheckCircle2 size={14} aria-hidden="true" /> },
  pending: { label: 'En attente', tone: 'warning', icon: <Clock size={14} aria-hidden="true" /> },
  failed: { label: 'Échoué', tone: 'danger', icon: <XCircle size={14} aria-hidden="true" /> },
}

/** Badge de statut d'une transaction : <StatusBadge status="pending" /> */
export function StatusBadge({ status, className }: { status: TransactionStatus; className?: string }) {
  const { label, tone, icon } = statusConfig[status]
  return (
    <Badge tone={tone} icon={icon} className={className}>
      {label}
    </Badge>
  )
}
