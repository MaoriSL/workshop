// ---------------------------------------------------------------------------
// Fonctions de mise en forme (français) : heures, durées, pourcentages,
// montants et libellés lisibles des codes renvoyés par le moteur.
// ---------------------------------------------------------------------------
import type { IncidentState, IncidentType, TimelineStep } from '@/api/types'

/** "14:03:27" en heure locale à partir d'une date ISO (ou d'un timestamp). */
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

/** "T+12 s" pour la chronologie. */
export function formatElapsed(seconds: number): string {
  return `T+${formatDuration(seconds)}`
}

/** Taux (0–1) → "7,0 %". */
export function formatPercent(rate: number | null): string {
  if (rate === null || !Number.isFinite(rate)) return '—'
  return `${(rate * 100).toLocaleString('fr-FR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} %`
}

/** Latence en ms → "120 ms" ou "1,4 s". */
export function formatLatency(ms: number | null): string {
  if (ms === null || !Number.isFinite(ms)) return '—'
  if (ms >= 1000) return `${(ms / 1000).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} s`
  return `${Math.round(ms)} ms`
}

/** Requêtes par seconde → "42 req/s". */
export function formatRps(rps: number | null): string {
  if (rps === null || !Number.isFinite(rps)) return '—'
  return `${rps.toLocaleString('fr-FR', { maximumFractionDigits: rps < 10 ? 1 : 0 })} req/s`
}

/** Montant en centimes → "1,00 €". */
export function formatEuro(cents: number): string {
  return (cents / 100).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' })
}

/** Libellé lisible d'un type d'incident. */
export function incidentTypeLabel(type: IncidentType | string | null): string {
  const labels: Record<IncidentType, string> = {
    indisponibilite: 'Indisponibilité',
    surcharge: 'Surcharge',
    bruteforce: 'Force brute',
    db_lente: 'Base de données lente',
    compromission: 'Compromission',
    incoherence: 'Incohérence des données',
    inconnu: 'Anomalie inconnue',
  }
  if (!type) return 'Anomalie'
  return labels[type as IncidentType] ?? type
}

/** Libellé lisible d'un état d'incident (pour l'historique). */
export function incidentStateLabel(state: IncidentState): string {
  const labels: Record<IncidentState, string> = {
    RECU: 'Reçu',
    DECIDE: 'Décidé',
    ACTION_EN_COURS: 'Action en cours',
    VERIFICATION: 'Vérification',
    RETABLI: 'Rétabli',
    ESCALADE: 'Escaladé',
    ECHEC: 'Échec',
  }
  return labels[state] ?? state
}

/** Libellé lisible d'une action de remédiation ("restart_container" → "Redémarrage du conteneur"). */
export function actionLabel(action: string): string {
  const labels: Record<string, string> = {
    restart_container: 'Redémarrage du conteneur',
    restart_service: 'Redémarrage du service',
    recreate_container: 'Recréation du conteneur',
    scale_up: 'Montée en charge',
    block_ip: 'Blocage des adresses IP',
    rate_limit: 'Limitation de débit',
    rollback: 'Retour à la version précédente',
    failover_db: 'Bascule base de données',
    restore_backup: 'Restauration de sauvegarde',
    isolate_service: 'Isolation du service',
    escalate: 'Escalade',
  }
  return labels[action] ?? action.replaceAll('_', ' ')
}

/** Icône (caractère) associée à chaque étape de la chronologie. */
export function stepIcon(step: TimelineStep): string {
  const icons: Record<TimelineStep, string> = {
    detected: '!',
    received: '↓',
    decided: '≡',
    action_started: '▶',
    action_done: '✓',
    verification_started: '?',
    healthy: '♥',
    proof_transaction: '€',
    consistency_ok: '=',
    recovered: '★',
    escalated: '↑',
    failed: '✕',
    detector_normal: '~',
  }
  return icons[step] ?? '•'
}
