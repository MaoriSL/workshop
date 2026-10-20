// ---------------------------------------------------------------------------
// Colonne gauche : une tuile par service (front, auth, api, db, gateway)
// avec pastille UP/DOWN, latence p95, taux 5xx et débit.
// DOWN → fond rouge ; dégradé (5xx > 5 % ou p95 > 1 s) → fond orange.
// ---------------------------------------------------------------------------
import type { ServiceName, ServiceStatus } from '@/api/types'
import { formatLatency, formatPercent, formatRps } from '@/utils/format'

const ORDER: ServiceName[] = ['front', 'auth', 'api', 'db', 'gateway']

const DESCRIPTION: Record<ServiceName, string> = {
  front: 'site Poupal',
  auth: 'authentification',
  api: 'paiements',
  db: 'base de données',
  gateway: 'passerelle',
}

type Health = 'down' | 'degraded' | 'ok' | 'unknown'

/** Règle d'affichage (simple et lisible, ce n'est pas la détection ML). */
function healthOf(s: ServiceStatus | undefined): Health {
  if (!s) return 'unknown'
  if (!s.up) return 'down'
  if ((s.error_rate_5xx ?? 0) > 0.05 || (s.latency_p95_ms ?? 0) > 1000) return 'degraded'
  return 'ok'
}

const STYLE: Record<Health, { card: string; pill: string; pillText: string }> = {
  down: { card: 'bg-danger border-danger text-white', pill: 'bg-white', pillText: 'DOWN' },
  degraded: { card: 'bg-warning border-warning text-night', pill: 'bg-night', pillText: 'DÉGRADÉ' },
  ok: { card: 'bg-panel border-line text-ink', pill: 'bg-success', pillText: 'UP' },
  unknown: { card: 'bg-panel border-line text-muted', pill: 'bg-muted', pillText: '—' },
}

function Tile({ name, service }: { name: ServiceName; service: ServiceStatus | undefined }) {
  const health = healthOf(service)
  const st = STYLE[health]
  const sub = health === 'ok' ? 'opacity-70' : 'opacity-85'
  return (
    <div className={`card flex min-h-0 flex-1 flex-col justify-center gap-[0.6vh] px-[1.2vw] py-[0.8vh] transition-colors duration-300 ${st.card}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <span className="t-tile block truncate font-extrabold">{name}</span>
          <span className={`t-small block truncate ${sub}`}>{DESCRIPTION[name]}</span>
        </div>
        <span className="t-small flex shrink-0 items-center gap-2 font-bold tracking-wide">
          <span className={`inline-block h-[0.9em] w-[0.9em] rounded-full ${st.pill}`} />
          {st.pillText}
        </span>
      </div>
      <div className="t-body flex items-baseline justify-between gap-2 tabular-nums">
        <Metric label="p95" value={formatLatency(service?.latency_p95_ms ?? null)} />
        <Metric label="5xx" value={formatPercent(service?.error_rate_5xx ?? null)} />
        <Metric label="" value={formatRps(service?.requests_per_s ?? null)} />
      </div>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <span className="whitespace-nowrap">
      {label && <span className="t-small mr-1 opacity-70">{label}</span>}
      <span className="font-semibold">{value}</span>
    </span>
  )
}

export default function ServiceTiles({ services }: { services: ServiceStatus[] }) {
  return (
    <aside className="flex h-full min-h-0 flex-col gap-[1vh]">
      {ORDER.map((name) => (
        <Tile key={name} name={name} service={services.find((s) => s.name === name)} />
      ))}
    </aside>
  )
}
