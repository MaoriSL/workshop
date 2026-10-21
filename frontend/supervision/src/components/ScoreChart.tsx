// ---------------------------------------------------------------------------
// Courbe du score d'anomalie (bas de l'écran) : score (cyan) + seuil (rouge
// pointillé) sur les 10 dernières minutes, aire rouge quand le score dépasse
// le seuil, repères verticaux pour détection / action / rétabli / échec.
// ---------------------------------------------------------------------------
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Marker, ScorePoint } from '@/api/types'
import { formatTime } from '@/utils/format'

interface Props {
  history: ScorePoint[]
  markers: Marker[]
}

const MARKER_COLOR: Record<Marker['kind'], string> = {
  detected: '#dc2626',
  action: '#f59e0b',
  recovered: '#16a34a',
  failed: '#dc2626',
}

/** Point prêt pour Recharts : l'axe X est un timestamp numérique. */
interface Point {
  t: number
  score: number
  threshold: number
  over: [number, number] // bande [seuil, score] quand le score dépasse le seuil
}

function toPoints(history: ScorePoint[]): Point[] {
  return history.map((p) => ({
    t: Date.parse(p.t),
    score: p.score,
    threshold: p.threshold,
    over: [p.threshold, Math.max(p.score, p.threshold)],
  }))
}

/** Hauteur de l'étiquette selon le type de repère : les repères d'un même
 *  incident sont proches (quelques secondes sur 10 minutes), on les étage
 *  verticalement pour qu'ils ne se chevauchent pas. */
const MARKER_DY: Record<Marker['kind'], number> = { detected: 12, action: 27, recovered: 42, failed: 42 }

/** Étiquette d'un repère : à gauche de la ligne (les repères naissent au bord droit). */
function MarkerLabel({ marker, x, y, fontSize }: { marker: Marker; x: number; y: number; fontSize: number }) {
  return (
    <text x={x - 5} y={y + MARKER_DY[marker.kind]} textAnchor="end" fill={MARKER_COLOR[marker.kind]} fontSize={fontSize} fontWeight={700}>
      {marker.label}
    </text>
  )
}

/** Infobulle en français, valeurs à deux décimales. */
function ScoreTooltip({ active, payload }: { active?: boolean; payload?: { payload: Point }[] }) {
  if (!active || !payload?.length) return null
  const p = payload[0]!.payload
  return (
    <div className="t-small rounded-lg border border-line bg-night/95 px-3 py-2 tabular-nums shadow-lg">
      <div className="font-semibold">{formatTime(p.t)}</div>
      <div>
        score <span className="font-bold text-sky">{p.score.toFixed(2)}</span> · seuil{' '}
        <span className="font-bold text-red-400">{p.threshold.toFixed(2)}</span>
      </div>
    </div>
  )
}

export default function ScoreChart({ history, markers }: Props) {
  const data = toPoints(history)
  const latest = data[data.length - 1]
  const above = latest ? latest.score > latest.threshold : false
  // Taille des textes SVG proportionnelle à la hauteur d'écran (12 px en 768p,
  // 17 px en 1080p) : Recharts attend un nombre, pas une valeur CSS.
  const fontSize = Math.round(Math.max(11, Math.min(18, window.innerHeight * 0.016)))

  return (
    <section className="card flex h-full min-h-0 flex-col px-[1vw] pt-[0.8vh] pb-[0.4vh]">
      <div className="flex shrink-0 items-center justify-between gap-4">
        <h2 className="t-title font-extrabold">
          Score d'anomalie <span className="font-medium text-muted">— 10 dernières minutes</span>
        </h2>
        <div className="t-small flex items-center gap-4 tabular-nums text-muted">
          <span>
            <span className="mr-1 inline-block h-[0.8em] w-[1.6em] rounded-sm bg-sky align-middle" /> score{' '}
            <span className={`font-bold ${above ? 'text-red-400' : 'text-ink'}`}>{latest ? latest.score.toFixed(2) : '—'}</span>
          </span>
          <span>
            <span className="mr-1 inline-block h-0 w-[1.6em] border-t-2 border-dashed border-red-500 align-middle" /> seuil{' '}
            <span className="font-bold text-ink">{latest ? latest.threshold.toFixed(2) : '—'}</span>
          </span>
        </div>
      </div>

      {/* Le conteneur doit avoir une hauteur explicite pour ResponsiveContainer */}
      <div className="min-h-0 flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 18, right: 28, bottom: 0, left: -18 }}>
            <CartesianGrid stroke="#263257" vertical={false} />
            <XAxis
              dataKey="t"
              type="number"
              domain={['dataMin', 'dataMax']}
              scale="time"
              tickFormatter={(v: number) => formatTime(v)}
              tick={{ fill: '#9aa6c8', fontSize }}
              stroke="#263257"
              minTickGap={60}
            />
            <YAxis domain={[0, 1]} ticks={[0, 0.5, 1]} tick={{ fill: '#9aa6c8', fontSize }} stroke="#263257" />
            <Tooltip content={<ScoreTooltip />} cursor={{ stroke: '#9aa6c8', strokeWidth: 1 }} />

            {/* Aire rouge translucide entre le seuil et le score quand il le dépasse */}
            <Area dataKey="over" stroke="none" fill="#dc2626" fillOpacity={0.28} isAnimationActive={false} />
            <Line dataKey="threshold" stroke="#dc2626" strokeWidth={2} strokeDasharray="6 4" dot={false} isAnimationActive={false} />
            <Line dataKey="score" stroke="#27b8f5" strokeWidth={2.5} dot={false} isAnimationActive={false} />

            {/* Repères verticaux : détection, action, rétabli, échec */}
            {markers.map((m) => (
              <ReferenceLine
                key={`${m.kind}-${m.t}`}
                x={Date.parse(m.t)}
                stroke={MARKER_COLOR[m.kind]}
                strokeWidth={2}
                label={(props: { viewBox: { x: number; y: number } }) => <MarkerLabel marker={m} x={props.viewBox.x} y={props.viewBox.y} fontSize={fontSize} />}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
