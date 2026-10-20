import type { ReactNode } from 'react'
import { AlertCircle, CheckCircle2, Info } from 'lucide-react'
import { cn } from '@/utils/cn'

type AlertTone = 'error' | 'success' | 'info'

const styles: Record<AlertTone, { box: string; icon: ReactNode }> = {
  error: { box: 'border-danger/20 bg-danger-soft text-red-900', icon: <AlertCircle size={18} aria-hidden="true" /> },
  success: { box: 'border-success/20 bg-success-soft text-green-900', icon: <CheckCircle2 size={18} aria-hidden="true" /> },
  info: { box: 'border-accent/20 bg-accent-soft text-primary-dark', icon: <Info size={18} aria-hidden="true" /> },
}

interface AlertProps {
  tone?: AlertTone
  title?: string
  className?: string
  children: ReactNode
}

/** Message contextuel (erreur de formulaire, info de démo...). */
export function Alert({ tone = 'info', title, className, children }: AlertProps) {
  const { box, icon } = styles[tone]
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={cn('flex gap-3 rounded-xl border px-4 py-3 text-sm', box, className)}
    >
      <span className="mt-0.5 shrink-0">{icon}</span>
      <div className="min-w-0">
        {title && <p className="font-semibold">{title}</p>}
        <div className={cn(title && 'mt-0.5')}>{children}</div>
      </div>
    </div>
  )
}
