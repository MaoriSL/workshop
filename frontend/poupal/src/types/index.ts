/**
 * Types partagés de l'application Poupal.
 * Ils décrivent le contrat de données entre le front et l'API REST
 * (aujourd'hui simulée dans src/api/mock, demain la vraie API).
 */

export interface User {
  id: string
  name: string
  email: string
  /** Date de création du compte (ISO 8601). */
  createdAt: string
}

export interface Account {
  balance: number
  currency: 'EUR'
}

export type TransactionStatus = 'completed' | 'pending' | 'failed'
export type TransactionType = 'sent' | 'received'

export interface Transaction {
  id: string
  /** Référence lisible affichée au client, ex. "PP-2026-0412". */
  reference: string
  type: TransactionType
  status: TransactionStatus
  /** Nom de la contrepartie (personne ou commerçant). */
  counterparty: string
  counterpartyEmail?: string
  /** Montant toujours positif ; le signe est déduit de `type`. */
  amount: number
  currency: 'EUR'
  /** Date de la transaction (ISO 8601). */
  date: string
  message?: string
}

/* ---- Authentification ---- */
export interface LoginRequest {
  email: string
  password: string
}

export interface SignupRequest {
  name: string
  email: string
  password: string
}

export interface AuthResponse {
  /** JWT émis par le service d'authentification. */
  token: string
  user: User
}

/* ---- Envoi d'argent ---- */
export interface SendMoneyRequest {
  /** Email ou nom du destinataire. */
  recipient: string
  amount: number
  message?: string
}

/** Brouillon transporté entre /send et /send/confirm (via l'état du routeur). */
export type SendDraft = SendMoneyRequest
