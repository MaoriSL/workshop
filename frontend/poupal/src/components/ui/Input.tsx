import { forwardRef, useId, useState, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { cn } from '@/utils/cn'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  /** Message d'erreur : passe le champ en rouge et l'annonce aux lecteurs d'écran. */
  error?: string
  /** Texte d'aide affiché sous le champ. */
  hint?: string
  leftIcon?: ReactNode
  /** Élément placé à droite dans le champ (bouton, suffixe "€", ...). */
  rightElement?: ReactNode
}

const fieldBase =
  'w-full rounded-xl border bg-white text-ink placeholder:text-muted/70 ' +
  'transition-all duration-200 outline-none ' +
  'focus:border-accent focus:ring-4 focus:ring-accent/15 ' +
  'disabled:bg-surface disabled:text-muted'

/**
 * Champ de saisie avec label, aide et erreur.
 * <Input label="Email" type="email" error={errors.email} />
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, hint, leftIcon, rightElement, className, id, ...rest },
  ref,
) {
  const generatedId = useId()
  const inputId = id ?? generatedId
  const describedBy = error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined

  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <label htmlFor={inputId} className="text-sm font-semibold text-ink">
        {label}
      </label>
      <div className="relative">
        {leftIcon && (
          <span className="pointer-events-none absolute inset-y-0 left-3.5 flex items-center text-muted">
            {leftIcon}
          </span>
        )}
        <input
          ref={ref}
          id={inputId}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={cn(
            fieldBase,
            'h-12 px-4',
            leftIcon && 'pl-11',
            rightElement && 'pr-12',
            error ? 'border-danger focus:border-danger focus:ring-danger/15' : 'border-line hover:border-muted/50',
          )}
          {...rest}
        />
        {rightElement && (
          <span className="absolute inset-y-0 right-2 flex items-center">{rightElement}</span>
        )}
      </div>
      {error ? (
        <p id={`${inputId}-error`} role="alert" className="text-sm font-medium text-danger">
          {error}
        </p>
      ) : hint ? (
        <p id={`${inputId}-hint`} className="text-sm text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  )
})

/** Champ mot de passe avec bouton afficher / masquer. */
export const PasswordInput = forwardRef<HTMLInputElement, Omit<InputProps, 'type' | 'rightElement'>>(
  function PasswordInput(props, ref) {
    const [visible, setVisible] = useState(false)
    return (
      <Input
        ref={ref}
        type={visible ? 'text' : 'password'}
        rightElement={
          <button
            type="button"
            onClick={() => setVisible((v) => !v)}
            aria-label={visible ? 'Masquer le mot de passe' : 'Afficher le mot de passe'}
            aria-pressed={visible}
            className="rounded-lg p-2 text-muted transition-colors hover:bg-surface hover:text-ink"
          >
            {visible ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
          </button>
        }
        {...props}
      />
    )
  },
)

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string
  error?: string
  hint?: string
}

/** Zone de texte multi-lignes (message d'un envoi, par exemple). */
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, error, hint, className, id, rows = 3, ...rest },
  ref,
) {
  const generatedId = useId()
  const textareaId = id ?? generatedId
  const describedBy = error ? `${textareaId}-error` : hint ? `${textareaId}-hint` : undefined

  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <label htmlFor={textareaId} className="text-sm font-semibold text-ink">
        {label}
      </label>
      <textarea
        ref={ref}
        id={textareaId}
        rows={rows}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={cn(
          fieldBase,
          'resize-none px-4 py-3',
          error ? 'border-danger focus:border-danger focus:ring-danger/15' : 'border-line hover:border-muted/50',
        )}
        {...rest}
      />
      {error ? (
        <p id={`${textareaId}-error`} role="alert" className="text-sm font-medium text-danger">
          {error}
        </p>
      ) : hint ? (
        <p id={`${textareaId}-hint`} className="text-sm text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  )
})
