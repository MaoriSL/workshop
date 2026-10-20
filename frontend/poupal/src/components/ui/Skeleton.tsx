import { cn } from '@/utils/cn'

/** Bloc gris animé utilisé pendant le chargement : <Skeleton className="h-4 w-40" /> */
export function Skeleton({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'block animate-shimmer rounded-lg bg-[length:200%_100%]',
        'bg-[linear-gradient(90deg,#eef1f7_0%,#f7f9fc_50%,#eef1f7_100%)]',
        className,
      )}
    />
  )
}
