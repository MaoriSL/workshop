/**
 * API des transactions et du compte.
 * Contrat REST de l'API métier — voir docs/api/contract.md :
 *   GET  /api/accounts/me            → { account_id, balance_cents, currency, ... }
 *   GET  /api/transactions?limit=    → { items: [...], total, limit, offset }
 *   GET  /api/transactions/:id       → transaction
 *   POST /api/transactions           { recipient_email, amount_cents, message } + en-tête Idempotency-Key
 * Les montants transitent en CENTIMES ; le front les convertit en euros (mappers.ts).
 * En mode mock, l'état vit en mémoire : un envoi réussi apparaît dans la liste
 * et débite le solde jusqu'au prochain rechargement de la page.
 */
import type { Account, SendMoneyRequest, Transaction } from '@/types'
import { ApiError, request, USE_MOCK } from './client'
import { centsToEuros, eurosToCents, toTransaction, type ApiAccount, type ApiPage, type ApiTransaction } from './mappers'
import { demoAccount, demoTransactions } from './mock/data'
import { wait } from './mock/delay'
import { isValidEmail } from '@/utils/format'

// --- État du mock (copie des données de démo, modifiable pendant la session) ---
let mockAccount: Account = { ...demoAccount }
let mockTransactions: Transaction[] = [...demoTransactions]
let mockCounter = demoTransactions.length

export async function getAccount(): Promise<Account> {
  if (USE_MOCK) {
    await wait(500)
    return { ...mockAccount }
  }
  const account = await request<ApiAccount>('/api/accounts/me')
  return { balance: centsToEuros(account.balance_cents), currency: account.currency }
}

export async function listTransactions(): Promise<Transaction[]> {
  if (USE_MOCK) {
    await wait(700)
    return [...mockTransactions]
  }
  const page = await request<ApiPage<ApiTransaction>>('/api/transactions?limit=100&offset=0')
  return page.items.map(toTransaction)
}

export async function getTransaction(id: string): Promise<Transaction> {
  if (USE_MOCK) {
    await wait(400)
    const found = mockTransactions.find((t) => t.id === id)
    if (!found) throw new ApiError(404, 'Transaction introuvable.', 'transaction_not_found')
    return { ...found }
  }
  return toTransaction(await request<ApiTransaction>(`/api/transactions/${encodeURIComponent(id)}`))
}

export async function sendMoney(data: SendMoneyRequest): Promise<Transaction> {
  if (USE_MOCK) {
    await wait(1200)
    if (data.amount <= 0) throw new ApiError(400, 'Le montant doit être supérieur à 0.', 'validation_error')
    if (data.amount > mockAccount.balance) {
      throw new ApiError(400, 'Solde insuffisant pour effectuer cet envoi.', 'insufficient_funds')
    }

    mockCounter += 1
    const transaction: Transaction = {
      id: `txn_${String(mockCounter).padStart(4, '0')}`,
      reference: `PP-2026-${String(400 + mockCounter).padStart(4, '0')}`,
      type: 'sent',
      status: 'completed',
      counterparty: data.recipient.trim(),
      counterpartyEmail: data.recipient.includes('@') ? data.recipient.trim() : undefined,
      amount: data.amount,
      currency: 'EUR',
      date: new Date().toISOString(),
      message: data.message?.trim() || undefined,
    }
    mockTransactions = [transaction, ...mockTransactions]
    mockAccount = { ...mockAccount, balance: mockAccount.balance - data.amount }
    return transaction
  }

  // L'API identifie le destinataire par son email uniquement
  const recipientEmail = data.recipient.trim().toLowerCase()
  if (!isValidEmail(recipientEmail)) {
    throw new ApiError(422, 'Indiquez l’adresse email du destinataire.', 'validation_error')
  }

  const created = await request<ApiTransaction>('/api/transactions', {
    method: 'POST',
    body: {
      recipient_email: recipientEmail,
      amount_cents: eurosToCents(data.amount),
      message: data.message?.trim() || null,
    },
    // Une même clé = une seule transaction, même si la requête est rejouée (double clic, réseau)
    headers: { 'Idempotency-Key': crypto.randomUUID() },
  })
  return toTransaction(created)
}
