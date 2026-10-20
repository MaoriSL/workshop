// ---------------------------------------------------------------------------
// Hook React : fournit l'état vivant de la plateforme aux composants.
//  - state     : dernier objet State reçu (SSE ou polling)
//  - status    : 'live' | 'polling' | 'offline' (qualité de la liaison)
//  - incidents : historique des incidents (rechargé quand un incident se termine)
//  - isMock    : true en mode démonstration (badge « démo »)
// ---------------------------------------------------------------------------
import { useEffect, useState } from 'react'
import { USE_MOCK, fetchIncidents, subscribeState } from '@/api/client'
import { fetchMockIncidents, subscribeMockState } from '@/api/mock'
import type { ConnectionStatus, Incident, State } from '@/api/types'

// Sélection de l'implémentation : vraie API ou données de démonstration.
const api = USE_MOCK
  ? { subscribe: subscribeMockState, incidents: fetchMockIncidents }
  : { subscribe: subscribeState, incidents: fetchIncidents }

export interface LiveState {
  state: State | null
  status: ConnectionStatus
  incidents: Incident[]
  isMock: boolean
}

export function useLiveState(): LiveState {
  const [state, setState] = useState<State | null>(null)
  const [status, setStatus] = useState<ConnectionStatus>('offline')
  const [incidents, setIncidents] = useState<Incident[]>([])

  // Abonnement au flux d'état (SSE avec repli polling, ou simulation).
  useEffect(() => api.subscribe({ onState: setState, onStatus: setStatus }), [])

  // Historique : chargé au montage puis à chaque changement du dernier incident
  // (nouvel incident, changement d'état final). Clé volontairement simple.
  const lastKey = state ? `${state.last_incident?.incident_id ?? ''}:${state.last_incident?.state ?? ''}` : ''
  useEffect(() => {
    let cancelled = false
    api
      .incidents()
      .then((items) => {
        if (!cancelled) setIncidents(items)
      })
      .catch(() => {
        /* l'historique n'est pas critique : on garde la dernière liste connue */
      })
    return () => {
      cancelled = true
    }
  }, [lastKey])

  return { state, status, incidents, isMock: USE_MOCK }
}
