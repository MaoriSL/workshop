// ---------------------------------------------------------------------------
// Hook React : fournit l'état vivant de la console aux composants.
//  - state   : dernier objet State reçu (SSE ou polling, ou simulation en démo)
//  - status  : 'live' | 'polling' | 'offline' (qualité de la liaison)
//  - journal : historique des attaques (rechargé quand l'état change)
//  - isMock  : true en mode démonstration (badge « démo »)
// ---------------------------------------------------------------------------
import { useEffect, useState } from 'react'
import { api, USE_MOCK } from '@/api'
import type { ConnectionStatus, JournalEntry, State } from '@/api/types'

export interface LiveState {
  state: State | null
  status: ConnectionStatus
  journal: JournalEntry[]
  isMock: boolean
}

export function useLiveState(): LiveState {
  const [state, setState] = useState<State | null>(null)
  const [status, setStatus] = useState<ConnectionStatus>('offline')
  const [journal, setJournal] = useState<JournalEntry[]>([])

  // Abonnement au flux d'état (SSE avec repli polling, ou simulation en démo).
  useEffect(() => api.subscribe({ onState: setState, onStatus: setStatus }), [])

  // Journal : rechargé au montage puis à chaque fois que le nombre de runs ou
  // le dernier run change (nouveau lancement / arrêt). Clé volontairement simple.
  const topRun = state?.runs[0]
  const key = `${state?.runs.length ?? 0}:${topRun?.run_id ?? ''}:${topRun?.status ?? ''}`
  useEffect(() => {
    let cancelled = false
    api
      .fetchJournal()
      .then((items) => {
        if (!cancelled) setJournal(items)
      })
      .catch(() => {
        /* le journal n'est pas critique : on garde la dernière liste connue */
      })
    return () => {
      cancelled = true
    }
  }, [key])

  return { state, status, journal, isMock: USE_MOCK }
}
