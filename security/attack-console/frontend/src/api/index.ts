// ---------------------------------------------------------------------------
// Point d'entrée de la couche API : choisit l'implémentation réelle
// (orchestrateur) ou le mock de démonstration selon VITE_USE_MOCK.
// Le reste de l'application importe toujours `api` et `USE_MOCK` d'ici.
// ---------------------------------------------------------------------------
import { USE_MOCK, realApi, type AttackApi } from './client'
import { mockApi } from './mock'

export const api: AttackApi = USE_MOCK ? mockApi : realApi
export { USE_MOCK }
