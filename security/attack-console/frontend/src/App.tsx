// ---------------------------------------------------------------------------
// Console d'attaque Poupal — écran principal.
// Assemble l'en-tête permanent, la grille de scénarios et le journal.
// La console est un PILOTE : lecture de l'état + actions bornées uniquement.
// ---------------------------------------------------------------------------
import { useCallback, useState } from 'react'
import { api } from '@/api'
import { useLiveState } from '@/hooks/useLiveState'
import type { Run } from '@/api/types'
import TopBar from '@/components/TopBar'
import ScenarioCard from '@/components/ScenarioCard'
import JournalPanel from '@/components/JournalPanel'

export default function App() {
  const { state, status, journal, isMock } = useLiveState()
  const [error, setError] = useState<string | null>(null)

  const inLab = state?.in_lab ?? true
  const scenarios = state?.scenarios ?? []
  const runs = state?.runs ?? []

  // Dernier run connu pour un scénario donné (runs triés du plus récent au plus ancien).
  const latestRunFor = (id: string): Run | undefined => runs.find((r) => r.scenario_id === id)

  // --- Actions bornées ------------------------------------------------------
  const flashError = (msg: string) => {
    setError(msg)
    window.setTimeout(() => setError(null), 4000)
  }

  const handleStart = useCallback((id: string, params: Record<string, number | string>) => {
    api.startScenario(id, params).catch((e: unknown) => {
      const msg = e instanceof Error ? e.message : 'Échec du lancement'
      flashError(msg.includes('409') ? 'Un run est déjà en cours pour ce scénario.' : msg.includes('403') ? 'Cible hors périmètre : lancement refusé.' : msg)
    })
  }, [])

  const handleStop = useCallback((id: string) => {
    api.stopScenario(id).catch(() => flashError('Échec de l’arrêt du scénario.'))
  }, [])

  const handleStopAll = useCallback(() => {
    api.stopAll().catch(() => flashError('Échec de l’arrêt d’urgence.'))
  }, [])

  const handleSetTarget = useCallback(async (url: string) => {
    await api.setTarget(url)
  }, [])

  const handleExport = useCallback(() => {
    try {
      api.exportJournalCsv()
    } catch {
      flashError('Échec de l’export du journal.')
    }
  }, [])

  return (
    <div
      className={`flex h-full flex-col gap-[1.2vh] p-[1.4vh] ${
        inLab ? '' : 'ring-4 ring-inset ring-danger'
      }`}
    >
      <TopBar state={state} status={status} isMock={isMock} onStopAll={handleStopAll} onSetTarget={handleSetTarget} />

      {/* Écran d'alerte : cible hors périmètre → tout est verrouillé. */}
      {!inLab && (
        <div className="flex shrink-0 flex-col items-center gap-1 rounded-xl border-2 border-danger bg-danger/15 px-4 py-[1.6vh] text-center animate-card-in">
          <span className="t-hero font-extrabold uppercase tracking-wide text-danger">
            ⛔ Cible hors périmètre — attaques désactivées
          </span>
          <span className="t-body text-ink/90">{state?.lab_reason}</span>
        </div>
      )}

      {/* Message d'erreur transitoire (refus, échec réseau). */}
      {error && (
        <div className="t-body shrink-0 rounded-lg border border-danger bg-danger/20 px-4 py-2 font-semibold text-danger animate-row-in">
          {error}
        </div>
      )}

      {/* Corps : grille de scénarios (défilante) + journal (colonne droite). */}
      <main className="flex min-h-0 flex-1 gap-[1.2vh]">
        <div className="min-w-0 flex-1 overflow-y-auto pr-1">
          {state ? (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-[1.2vh]">
              {scenarios.map((scenario) => (
                <ScenarioCard
                  key={scenario.id}
                  scenario={scenario}
                  run={latestRunFor(scenario.id)}
                  inLab={inLab}
                  onStart={handleStart}
                  onStop={handleStop}
                />
              ))}
            </div>
          ) : (
            <div className="t-title flex h-full items-center justify-center text-muted">
              Connexion à l’orchestrateur…
            </div>
          )}
        </div>

        <aside className="w-[clamp(290px,26vw,440px)] shrink-0">
          <JournalPanel journal={journal} onExport={handleExport} />
        </aside>
      </main>

      {/* Pied de page : mention démonstration permanente. */}
      <footer className="t-small shrink-0 text-center text-muted">
        Environnement de démonstration — plateforme fictive, aucun paiement réel.
      </footer>
    </div>
  )
}
