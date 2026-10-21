/**
 * Données factices de démonstration.
 * Tout est inventé : utilisateur, contreparties, montants, références.
 * Aucune donnée réelle n'est utilisée dans Poupal.
 */
import type { Account, Transaction, User } from '@/types'

export const demoUser: User = {
  id: 'usr_demo_0001',
  name: 'Alex Martin',
  email: 'alex.martin@poupal.demo',
  createdAt: '2025-03-12T10:00:00Z',
}

export const demoAccount: Account = {
  balance: 2450,
  currency: 'EUR',
}

/** Jeton JWT factice (payload lisible, signature fictive) : aucune valeur de sécurité. */
export const demoToken =
  'demo.eyJzdWIiOiJ1c3JfZGVtb18wMDAxIiwibmFtZSI6IkFsZXggTWFydGluIn0.signature-fictive'

export const demoTransactions: Transaction[] = [
  {
    id: 'txn_0010',
    reference: 'PP-2026-0410',
    type: 'received',
    status: 'completed',
    counterparty: 'Camille Dupont',
    counterpartyEmail: 'camille.dupont@exemple.fr',
    amount: 120,
    currency: 'EUR',
    date: '2026-10-18T14:32:00Z',
    message: 'Remboursement restaurant',
  },
  {
    id: 'txn_0009',
    reference: 'PP-2026-0409',
    type: 'sent',
    status: 'pending',
    counterparty: 'Nathan Petit',
    counterpartyEmail: 'nathan.petit@exemple.fr',
    amount: 45.5,
    currency: 'EUR',
    date: '2026-10-17T18:05:00Z',
    message: 'Place de concert',
  },
  {
    id: 'txn_0008',
    reference: 'PP-2026-0408',
    type: 'sent',
    status: 'completed',
    counterparty: 'Boulangerie Rivière',
    amount: 12.8,
    currency: 'EUR',
    date: '2026-10-16T07:48:00Z',
  },
  {
    id: 'txn_0007',
    reference: 'PP-2026-0407',
    type: 'received',
    status: 'completed',
    counterparty: 'Léa Bernard',
    counterpartyEmail: 'lea.bernard@exemple.fr',
    amount: 1250,
    currency: 'EUR',
    date: '2026-10-14T09:30:00Z',
    message: 'Loyer octobre - colocation',
  },
  {
    id: 'txn_0006',
    reference: 'PP-2026-0406',
    type: 'sent',
    status: 'failed',
    counterparty: 'Hugo Garnier',
    counterpartyEmail: 'hugo.garnier@exemple.fr',
    amount: 300,
    currency: 'EUR',
    date: '2026-10-12T20:15:00Z',
    message: 'Vélo d\u2019occasion',
  },
  {
    id: 'txn_0005',
    reference: 'PP-2026-0405',
    type: 'sent',
    status: 'completed',
    counterparty: 'Streamly Abonnement',
    amount: 9.99,
    currency: 'EUR',
    date: '2026-10-10T06:00:00Z',
    message: 'Abonnement mensuel',
  },
  {
    id: 'txn_0004',
    reference: 'PP-2026-0404',
    type: 'received',
    status: 'completed',
    counterparty: 'Julie Moreau',
    counterpartyEmail: 'julie.moreau@exemple.fr',
    amount: 68.4,
    currency: 'EUR',
    date: '2026-10-08T12:10:00Z',
    message: 'Cadeau commun pour Sam',
  },
  {
    id: 'txn_0003',
    reference: 'PP-2026-0403',
    type: 'sent',
    status: 'completed',
    counterparty: 'Lucas Fontaine',
    counterpartyEmail: 'lucas.fontaine@exemple.fr',
    amount: 210,
    currency: 'EUR',
    date: '2026-10-05T16:45:00Z',
    message: 'Week-end à Lyon',
  },
  {
    id: 'txn_0002',
    reference: 'PP-2026-0402',
    type: 'received',
    status: 'pending',
    counterparty: 'Emma Lefèvre',
    counterpartyEmail: 'emma.lefevre@exemple.fr',
    amount: 35,
    currency: 'EUR',
    date: '2026-10-02T08:20:00Z',
    message: 'Billets de train',
  },
  {
    id: 'txn_0001',
    reference: 'PP-2026-0401',
    type: 'sent',
    status: 'completed',
    counterparty: 'Sophie Lambert',
    counterpartyEmail: 'sophie.lambert@exemple.fr',
    amount: 80,
    currency: 'EUR',
    date: '2026-09-28T11:00:00Z',
    message: 'Cours de yoga',
  },
]
