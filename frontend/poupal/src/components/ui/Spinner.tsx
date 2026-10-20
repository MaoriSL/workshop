import { cn } from '@/utils/cn'

const sizes = { sm: 'h-4 w-4 border-2', md: 'h-6 w-6 border-2', lg: 'h-10 w-10 border-[3px]' }

/** Indicateur de chargement circulaire. */
export function Spinner({ size = 'md', className }: { size?: keyof typeof sizes; className?: string }) {
  return (
    <span
      role="status"
      aria-label="Chargement"
      className={cn(
        'inline-block animate-spin rounded-full border-current border-t-transparent text-accent',
        sizes[size],
        className,
      )}
    />
  )
}
