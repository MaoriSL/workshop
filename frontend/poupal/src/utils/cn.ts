/**
 * Concatène des classes CSS en ignorant les valeurs vides / fausses.
 * Exemple : cn("btn", isActive && "btn-active", undefined) → "btn btn-active"
 */
export function cn(...classes: unknown[]): string {
  return classes.filter((value): value is string => typeof value === 'string' && value !== '').join(' ')
}
