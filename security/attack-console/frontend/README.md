# Poupal — Console d'attaque (laboratoire)

Front React + Vite + TypeScript + Tailwind v4. **Pilote** de scénarios
d'attaque **fictifs et confinés** contre notre propre plateforme Poupal : il
déclenche la chaîne détection → remédiation, et sera filmé/projeté le jour du
jury. Aucune attaque réelle, aucun paiement réel.

> Environnement de démonstration — plateforme fictive. Les attaques sont
> limitées à notre plateforme sur le réseau RESILIENCE-G<n> (plage privée).

## Nature du composant
C'est un **pilote en lecture / contrôle simple** : les seules actions sont
**Lancer / Stopper** par scénario, **Arrêt d'urgence** global et **Export** du
journal. Aucune saisie de commande libre — les paramètres sont des champs
bornés (sliders / listes déroulantes) décrits par le schéma de l'orchestrateur.

## Lancement en développement
```bash
npm install
npm run dev        # http://localhost:5175
```
- **Mode démonstration** (défaut via `.env`, `VITE_USE_MOCK=true`) : scénarios
  et runs simulés, aucun réseau, badge « démo ». Idéal pour la mise au point.
- **Mode réel** : `VITE_USE_MOCK=` (vide) + orchestrateur sur
  `http://localhost:8099`. Le proxy Vite transmet `/api` (et le flux SSE
  `/api/events`) vers lui.
- **Test hors périmètre** : ouvrir `http://localhost:5175/?lab=off` → l'écran
  passe en alerte rouge et tous les boutons Lancer sont désactivés (simule
  `in_lab=false`).

## Build & vérifications
```bash
npm run typecheck  # tsc -b
npm run build      # tsc -b && vite build  → dist/
```

## Variables d'environnement (lues AU BUILD)
| Variable        | Défaut | Rôle                                                        |
|-----------------|--------|-------------------------------------------------------------|
| `VITE_API_BASE` | `/api` | Base de l'API de l'orchestrateur (même origine).            |
| `VITE_USE_MOCK` | *(vide)* | `true` = données de démonstration embarquées, aucun réseau. |

## Image de production
```bash
docker build -t poupal-attack-console .
docker run --rm -p 8090:80 poupal-attack-console   # http://localhost:8090/
```
nginx sert la SPA à la racine (Vite `base: './'`), avec repli SPA et sonde
`/healthz`. L'orchestrateur est appelé en **même origine** sous `/api` : c'est
la gateway de l'intégrateur qui proxifie `/api/` (voir le bloc commenté dans
`nginx.conf` pour un déploiement autonome ; `proxy_buffering off` requis pour le
SSE).

## Contrat d'API attendu (orchestrateur)
Voir `src/api/types.ts`. Résumé :
- `GET {base}/state` → `State` ; `GET {base}/events` → SSE `event: state`.
- `POST {base}/scenarios/{id}/start` `{ params }` → `202 { run_id }` / `409` / `403`.
- `POST {base}/scenarios/{id}/stop`, `POST {base}/stop-all` → `200`.
- `GET {base}/journal` → `{ items }` ; `GET {base}/journal.csv` → fichier CSV.

## Structure
```
src/
  api/      types.ts (contrat), client.ts (réel + SSE/polling), mock.ts (démo), index.ts (sélecteur)
  hooks/    useLiveState.ts (état vivant)
  utils/    format.ts (fr : heures, durées, libellés)
  components/ TopBar, ScenarioCard, JournalPanel
  App.tsx   assemblage
```
