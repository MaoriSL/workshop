/**
 * Fonctions de formatage en français (montants, dates, initiales).
 * On s'appuie sur l'API Intl du navigateur : pas de dépendance externe.
 */

const currencyFormatter = new Intl.NumberFormat('fr-FR', {
  style: 'currency',
  currency: 'EUR',
  minimumFractionDigits: 2,
})

/** Symbole de la devise affichée (« € »), dérivé du formateur pour rester cohérent. */
export const CURRENCY_SYMBOL = currencyFormatter.formatToParts(0).find((part) => part.type === 'currency')?.value ?? '€'

/** 1250 → "1 250,00 €" */
export function formatCurrency(amount: number): string {
  return currencyFormatter.format(amount)
}

/**
 * Montant signé selon le sens de la transaction.
 * ("received", 120) → "+ 120,00 €"   ("sent", 45.5) → "− 45,50 €"
 */
export function formatSignedAmount(type: 'sent' | 'received', amount: number): string {
  const sign = type === 'received' ? '+' : '−'
  return `${sign} ${currencyFormatter.format(Math.abs(amount))}`
}

const dateFormatter = new Intl.DateTimeFormat('fr-FR', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
})

/** "2026-10-14T09:30:00Z" (ou un objet Date) → "14 oct. 2026" */
export function formatDate(date: string | Date): string {
  return dateFormatter.format(new Date(date))
}

const dateTimeFormatter = new Intl.DateTimeFormat('fr-FR', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

/** "2026-10-14T09:30:00Z" (ou un objet Date) → "14 octobre 2026 à 11:30" */
export function formatDateTime(date: string | Date): string {
  return dateTimeFormatter.format(new Date(date))
}

/** "Camille Dupont" → "CD" */
export function getInitials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('')
}

/** Inverse de parseAmount : 25.5 → "25,50" (valeur d'un champ de saisie). */
export function formatAmountInput(amount: number): string {
  return amount.toFixed(2).replace('.', ',')
}

/** Convertit une saisie utilisateur ("1 250,50") en nombre (1250.5). NaN si invalide. */
export function parseAmount(input: string): number {
  const normalized = input.replace(/\s/g, '').replace(',', '.')
  if (normalized === '' || !/^\d+(\.\d{0,2})?$/.test(normalized)) return NaN
  return Number(normalized)
}

/** Vérification simple du format d'un email. */
export function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value.trim())
}
