/**
 * Conversion entre les objets JSON de l'API (snake_case, montants en centimes)
 * et les types du front (camelCase, montants en euros).
 */
import type { Transaction, TransactionStatus, TransactionType, User } from '@/types'

export interface ApiUser {
  id: string
  email: string
  name: string
  created_at: string
}

export interface ApiAccount {
  account_id: string
  user_id: string
  balance_cents: number
  currency: 'EUR'
  opening_balance_cents: number
  created_at: string
}

export interface ApiTransaction {
  id: string
  reference: string
  type: TransactionType
  status: TransactionStatus
  amount_cents: number
  currency: 'EUR'
  message: string | null
  failure_reason: string | null
  counterparty: { user_id: string | null; email: string | null; name: string }
  created_at: string
}

export interface ApiPage<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

/** 245000 centimes → 2450 euros */
export function centsToEuros(cents: number): number {
  return cents / 100
}

/** 12.3 euros → 1230 centimes (arrondi pour éviter les erreurs de flottants) */
export function eurosToCents(euros: number): number {
  return Math.round(euros * 100)
}

export function toUser(api: ApiUser): User {
  return { id: api.id, name: api.name, email: api.email, createdAt: api.created_at }
}

export function toTransaction(api: ApiTransaction): Transaction {
  return {
    id: api.id,
    reference: api.reference,
    type: api.type,
    status: api.status,
    counterparty: api.counterparty.name,
    counterpartyEmail: api.counterparty.email ?? undefined,
    amount: centsToEuros(api.amount_cents),
    currency: api.currency,
    date: api.created_at,
    message: api.message ?? undefined,
  }
}
