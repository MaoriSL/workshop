// ---------------------------------------------------------------------------
// Fonctions de mise en forme (français) : heures, durées, débits et libellés
// lisibles des scénarios / statuts renvoyés par l'orchestrateur.
// ---------------------------------------------------------------------------
import type { IncidentType, RunStatus, ScenarioId } from '@/api/types'

/** "14:03:27" en heure locale à partir d'une date ISO. */
export function formatTime(value: string | number | Date): string {
  const d = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(d.getTime())) return '--:--:--'
  return d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

/** "14:03" (sans secondes) pour les listes compactes. */
export function formatShortTime(value: string | number | Date): string {
  const d = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(d.getTime())) return '--:--'
  return d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
}

/** Durée en secondes → "38 s" ou "1 min 12 s". */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return '—'
  const s = Math.round(seconds)
  if (s < 60) return `${s} s`
  const min = Math.floor(s / 60)
  const rest = s % 60
  return rest === 0 ? `${min} min` : `${min} min ${rest} s`
}

/** "T+12 s" : temps écoulé depuis le lancement. */
export function formatElapsed(seconds: number): string {
  return `T+${formatDuration(seconds)}`
}

/** Requêtes par seconde → "42 req/s". */
export function formatRps(rps: number | null | undefined): string {
  if (rps === null || rps === undefined || !Number.isFinite(rps)) return '—'
  return `${rps.toLocaleString('fr-FR', { maximumFractionDigits: rps < 10 ? 1 : 0 })} req/s`
}

/** Grand nombre → "12 345" (espaces fins) ; compact au-delà de 100 000. */
export function formatCount(n: number): string {
  if (!Number.isFinite(n)) return '—'
  if (n >= 100_000) return `${(n / 1000).toLocaleString('fr-FR', { maximumFractionDigits: 0 })} k`
  return n.toLocaleString('fr-FR')
}

/** Libellé lisible d'un type d'incident attendu. */
export function incidentTypeLabel(type: IncidentType | string | null | undefined): string {
  const labels: Record<IncidentType, string> = {
    surcharge: 'Surcharge',
    bruteforce: 'Force brute',
    injection: 'Injection',
    exfiltration: 'Exfiltration',
    combo: 'Combinée',
  }
  if (!type) return 'Anomalie'
  return labels[type as IncidentType] ?? type
}

/** Libellé lisible d'un scénario (secours si l'orchestrateur ne donne pas de nom). */
export function scenarioLabel(id: ScenarioId | string): string {
  const labels: Record<ScenarioId, string> = {
    dos: 'Déni de service',
    bruteforce: 'Force brute',
    injection: 'Injection SQL',
    exfiltration: 'Exfiltration',
    combo: 'Attaque combinée',
  }
  return labels[id as ScenarioId] ?? id
}

/** Libellé + couleur d'un statut de run. */
export function runStatusInfo(status: RunStatus): { label: string; color: string } {
  const map: Record<RunStatus, { label: string; color: string }> = {
    running: { label: 'en cours', color: '#f59e0b' },
    finished: { label: 'terminé', color: '#27b8f5' },
    stopped: { label: 'arrêté', color: '#9aa6c8' },
    error: { label: 'erreur', color: '#dc2626' },
  }
  return map[status] ?? { label: status, color: '#9aa6c8' }
}

/** Couleur associée à une famille de codes HTTP (pour la ventilation). */
export function statusColor(code: string): string {
  const c = Number(code)
  if (c >= 500) return '#dc2626' // erreurs serveur
  if (c === 429) return '#f59e0b' // limitation de débit
  if (c === 403 || c === 401) return '#27b8f5' // bloqué / refusé (WAF, auth)
  if (c >= 200 && c < 300) return '#16a34a' // succès (requête passée)
  return '#9aa6c8'
}
