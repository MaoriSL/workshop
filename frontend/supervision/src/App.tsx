// ---------------------------------------------------------------------------
// Écran unique du dashboard de supervision (lecture seule, sans défilement) :
//   1. bandeau d'état global      (haut)
//   2. état des services          (colonne gauche)
//   3. chronologie de l'incident  (centre) — ou l'historique, via la bascule
//   4. courbe du score d'anomalie (bas, pleine largeur)
// Le seul contrôle autorisé est la bascule Chronologie / Historique.
// ---------------------------------------------------------------------------
import { useState } from 'react'
import { API_BASE } from '@/api/client'
import GlobalBanner from '@/components/GlobalBanner'
import HistoryPanel from '@/components/HistoryPanel'
import IncidentTimeline from '@/components/IncidentTimeline'
import ScoreChart from '@/components/ScoreChart'
import ServiceTiles from '@/components/ServiceTiles'
import { useLiveState } from '@/hooks/useLiveState'

type View = 'timeline' | 'history'

export default function App() {
  const { state, status, incidents, isMock } = useLiveState()
  const [view, setView] = useState<View>('timeline')

  // Incident affiché : celui en cours ; sinon le dernier connu tant que la
  // plateforme n'est pas revenue à NORMAL (RETABLI, ECHEC, SURETE racontent
  // encore l'incident). En NORMAL : écran calme + dernière preuve connue.
  const incident = state?.current_incident ?? (state && state.global_state !== 'NORMAL' ? state.last_incident : null)

  return (
    <div className="flex h-full flex-col gap-[1.2vh] p-[1.2vh]">
      {/* 1. Bandeau d'état global (~18 % de la hauteur) */}
      <div className="h-[17vh] shrink-0">
        <GlobalBanner state={state} status={status} isMock={isMock} />
      </div>

      {/* 2 + 3. Services (gauche) et chronologie (centre) */}
      <main className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_minmax(0,2.6fr)] gap-[1.2vh]">
        <ServiceTiles services={state?.services ?? []} />

        <section className="card flex min-h-0 flex-col px-[1.2vw] py-[1vh]">
          <div className="flex shrink-0 items-center justify-between gap-4 pb-[0.6vh]">
            <h2 className="t-title font-extrabold">
              {view === 'timeline' ? "Chronologie de l'incident" : 'Historique des incidents'}
            </h2>
            {/* Bascule d'affichage : lecture seule, ne déclenche rien côté moteur */}
            <div className="t-small flex rounded-lg border border-line bg-panel-2 p-0.5 font-semibold" role="tablist" aria-label="Affichage">
              <TabButton active={view === 'timeline'} onClick={() => setView('timeline')}>
                Chronologie
              </TabButton>
              <TabButton active={view === 'history'} onClick={() => setView('history')}>
                Historique ({incidents.length})
              </TabButton>
            </div>
          </div>
          <div className="min-h-0 flex-1">
            {view === 'timeline' ? (
              <IncidentTimeline incident={incident} lastProof={state?.last_proof ?? null} />
            ) : (
              <HistoryPanel incidents={incidents} />
            )}
          </div>
        </section>
      </main>

      {/* 4. Courbe du score d'anomalie (~25 % de la hauteur) */}
      <div className="h-[24vh] shrink-0">
        <ScoreChart history={state?.score_history ?? []} markers={state?.markers ?? []} />
      </div>

      {/* Pied de page discret */}
      <footer className="t-small flex shrink-0 items-center justify-between gap-4 px-1 text-muted">
        <span>Environnement de démonstration — plateforme fictive, aucun paiement réel.</span>
        <span className="tabular-nums">
          lecture seule · {isMock ? 'données de démonstration' : `API ${API_BASE}`}
          {state && ` · mis à jour ${new Date(state.updated_at).toLocaleTimeString('fr-FR')}`}
        </span>
      </footer>
    </div>
  )
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`rounded-md px-3 py-1 transition-colors ${active ? 'bg-accent text-white' : 'text-muted hover:text-ink'}`}
    >
      {children}
    </button>
  )
}
