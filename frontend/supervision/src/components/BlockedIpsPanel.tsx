import { useCallback, useEffect, useState } from 'react'
import { fetchBlockedIps, unblockIp } from '@/api/client'
import type { BlockedIp } from '@/api/types'

export default function BlockedIpsPanel() {
  const [items, setItems] = useState<BlockedIp[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setError(null)
      setItems(await fetchBlockedIps())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Impossible de lire la liste de blocage.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => void refresh(), 5000)
    return () => window.clearInterval(timer)
  }, [refresh])

  const handleUnblock = async (ip: string) => {
    setBusy(ip)
    try {
      await unblockIp(ip)
      await refresh()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Déblocage impossible.')
    } finally {
      setBusy(null)
    }
  }

  if (loading) return <div className="t-title flex h-full items-center justify-center text-muted">Chargement des IP bannies…</div>

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex shrink-0 items-center justify-between">
        <p className="t-small text-muted">Blocages actifs appliqués par la gateway après une détection ou une remédiation ML.</p>
        <button type="button" onClick={() => void refresh()} className="t-small rounded-lg border border-line px-3 py-1 font-semibold text-muted hover:text-ink">
          Actualiser
        </button>
      </div>
      {error && <div className="t-small rounded-lg border border-danger bg-danger/15 px-3 py-2 font-semibold text-danger">{error}</div>}
      {items.length === 0 ? (
        <div className="t-title flex min-h-0 flex-1 items-center justify-center text-muted">Aucune adresse IP bannie</div>
      ) : (
        <ol className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
          {items.map(({ ip }) => (
            <li key={ip} className="flex items-center justify-between rounded-lg border border-line bg-panel-2 px-3 py-2">
              <span className="t-body font-semibold tabular-nums">{ip}</span>
              <button
                type="button"
                disabled={busy === ip}
                onClick={() => void handleUnblock(ip)}
                className="t-small rounded-lg border border-warning px-3 py-1 font-bold uppercase text-amber-300 hover:bg-warning/15 disabled:opacity-50"
              >
                {busy === ip ? 'Déblocage…' : 'Débannir'}
              </button>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
