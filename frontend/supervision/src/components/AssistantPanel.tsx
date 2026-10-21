import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { askAssistant, summarizeIncident, type AssistantResponse } from '@/api/client'
import type { Incident } from '@/api/types'

const DEFAULT_QUESTION = 'Comment fonctionne la remédiation automatique ?'

export default function AssistantPanel({ incident }: { incident: Incident | null }) {
  const [question, setQuestion] = useState('')
  const [response, setResponse] = useState<AssistantResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!incident) return
    let cancelled = false
    setLoading(true)
    setError(null)
    void summarizeIncident(incident)
      .then((result) => {
        if (!cancelled) {
          setResponse(result)
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Résumé indisponible.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [incident?.incident_id])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = question.trim()
    if (trimmed.length < 3 || loading) return

    setLoading(true)
    setError(null)
    try {
      setResponse(await askAssistant(trimmed))
    } catch (err) {
      setResponse(null)
      setError(err instanceof Error ? err.message : 'Impossible de contacter l’assistant.')
    } finally {
      setLoading(false)
    }
  }

  function useExample() {
    setQuestion(DEFAULT_QUESTION)
    setError(null)
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-[1.2vh]">
      <div className="shrink-0">
        <p className="t-body text-muted">
          Posez une question sur la plateforme. Lorsqu’un incident est détecté, l’assistant
          génère automatiquement son résumé à partir de la chronologie réelle de la remédiation.
        </p>
      </div>

      <form className="flex shrink-0 flex-col gap-[0.8vh]" onSubmit={submit}>
        <label className="t-small font-semibold uppercase tracking-wider text-muted" htmlFor="assistant-question">
          Votre question
        </label>
        <div className="flex gap-2">
          <textarea
            id="assistant-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            className="t-body min-h-[5.5em] min-w-0 flex-1 resize-none rounded-xl border border-line bg-panel-2 px-3 py-2 text-ink placeholder:text-muted focus:border-sky focus:outline-none"
            placeholder="Ex. Comment prouve-t-on la reprise après une attaque ?"
            maxLength={2000}
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || question.trim().length < 3}
            className="t-small self-stretch rounded-xl bg-accent px-4 font-bold text-white transition-colors hover:bg-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? 'Réflexion…' : 'Demander'}
          </button>
        </div>
        <div className="flex items-center justify-between gap-3">
          <button type="button" onClick={useExample} className="t-small text-sky underline underline-offset-2 hover:text-white">
            Utiliser une question exemple
          </button>
          <span className="t-small text-muted">{question.length}/2000</span>
        </div>
      </form>

      {error && (
        <div className="t-body shrink-0 rounded-xl border border-danger/50 bg-danger-dark/40 px-4 py-3 text-red-200" role="alert">
          {error}
        </div>
      )}

      <section className="min-h-0 flex-1 overflow-y-auto rounded-xl border border-line bg-panel-2 px-4 py-3">
        {response ? (
          <div className="flex flex-col gap-3">
            <div>
              <h3 className="t-small mb-1 font-semibold uppercase tracking-wider text-muted">
                {incident ? 'Résumé de l’incident' : 'Réponse'}
              </h3>
              <p className="t-body whitespace-pre-wrap leading-relaxed">{response.answer}</p>
            </div>
            <div className="border-t border-line pt-3">
              <h3 className="t-small mb-2 font-semibold uppercase tracking-wider text-muted">
                Sources · modèle {response.model}
              </h3>
              {response.sources.length > 0 ? (
                <ul className="t-small grid gap-1 text-muted">
                  {response.sources.map((source) => (
                    <li key={source.path}>
                      <span className="text-sky">{source.path.replace('/app/docs/', '')}</span>
                      <span> · pertinence {source.score}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="t-small text-muted">Aucune source correspondante détectée.</p>
              )}
            </div>
          </div>
        ) : (
          <div className="t-body flex h-full items-center justify-center text-center text-muted">
            {incident ? 'Génération du résumé de l’incident…' : 'La réponse de l’assistant apparaîtra ici.'}
          </div>
        )}
      </section>
    </div>
  )
}
