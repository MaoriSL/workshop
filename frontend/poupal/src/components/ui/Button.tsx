import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { Link, type LinkProps } from 'react-router-dom'
import { cn } from '@/utils/cn'
import { Spinner } from './Spinner'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 'sm' | 'md' | 'lg'

interface ButtonStyleOptions {
  variant?: ButtonVariant
  size?: ButtonSize
  fullWidth?: boolean
}

const base =
  'inline-flex items-center justify-center gap-2 rounded-xl font-semibold whitespace-nowrap ' +
  'transition-all duration-200 ease-out select-none ' +
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ' +
  'disabled:cursor-not-allowed disabled:opacity-60 active:scale-[0.98]'

const variants: Record<ButtonVariant, string> = {
  primary:
    'bg-accent text-white shadow-glow hover:bg-accent-hover hover:shadow-card hover:-translate-y-px',
  secondary:
    'bg-white text-primary border border-line shadow-soft hover:border-accent/40 hover:bg-accent-soft/60',
  ghost: 'bg-transparent text-primary hover:bg-primary-soft',
  danger: 'bg-danger text-white hover:bg-red-700 shadow-soft',
}

const sizes: Record<ButtonSize, string> = {
  sm: 'h-9 px-3.5 text-sm',
  md: 'h-11 px-5 text-sm',
  lg: 'h-13 px-7 text-base',
}

/** Classes partagées entre <Button> et <ButtonLink>. */
export function buttonClasses({ variant = 'primary', size = 'md', fullWidth }: ButtonStyleOptions) {
  return cn(base, variants[variant], sizes[size], fullWidth && 'w-full')
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, ButtonStyleOptions {
  /** Affiche un spinner et désactive le bouton. */
  loading?: boolean
  leftIcon?: ReactNode
  rightIcon?: ReactNode
}

/**
 * Bouton principal de l'interface.
 * <Button variant="primary" loading={isSubmitting}>Envoyer</Button>
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant, size, fullWidth, loading, leftIcon, rightIcon, className, children, disabled, type = 'button', ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(buttonClasses({ variant, size, fullWidth }), className)}
      {...rest}
    >
      {loading ? <Spinner size="sm" className="text-current" /> : leftIcon}
      <span>{children}</span>
      {!loading && rightIcon}
    </button>
  )
})

export interface ButtonLinkProps extends LinkProps, ButtonStyleOptions {
  leftIcon?: ReactNode
  rightIcon?: ReactNode
}

/** Lien de navigation stylé comme un bouton : <ButtonLink to="/signup">Créer un compte</ButtonLink> */
export function ButtonLink({ variant, size, fullWidth, leftIcon, rightIcon, className, children, ...rest }: ButtonLinkProps) {
  return (
    <Link className={cn(buttonClasses({ variant, size, fullWidth }), className)} {...rest}>
      {leftIcon}
      <span>{children}</span>
      {rightIcon}
    </Link>
  )
}
