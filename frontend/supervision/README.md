# Poupal — Dashboard de supervision (`frontend/supervision`)

Écran unique, **en lecture seule**, qui raconte l'incident tout seul : état global de la
plateforme, santé des cinq services, chronologie de la remédiation automatique (avec la
**preuve de reprise** : une nouvelle transaction qui réussit) et courbe du score d'anomalie.
Conçu pour être filmé / projeté : gros textes, fond sombre, aucun défilement en 1366×768
comme en 1920×1080.

> Environnement de démonstration — plateforme fictive, aucun paiement réel.

## Stack

React 18 · Vite · TypeScript · Tailwind CSS v4 (`@tailwindcss/vite`) · Recharts.

## Lancement

```bash
cd frontend/supervision
npm install
npm run dev            # http://localhost:5174/supervision/
```

Variables (fichier `.env`, voir `.env.example`, lues **au build**) :

| Variable        | Défaut             | Rôle                                                             |
| --------------- | ------------------ | ---------------------------------------------------------------- |
| `VITE_API_BASE` | `/supervision/api` | Base URL de l'API du moteur de remédiation (même origine).       |
| `VITE_USE_MOCK` | *(vide)*           | `true` : données de démonstration embarquées, badge « démo ».    |

Sans moteur disponible : `VITE_USE_MOCK=true` rejoue en boucle un incident complet
(NORMAL → ANOMALIE → REMÉDIATION → RÉTABLI avec preuve, ~95 s par cycle).

Vérifications : `npx tsc -b` (typage) et `npm run build` (bundle dans `dist/`).

## Interfaces consommées (GET uniquement)

| Route                   | Usage                                                                  |
| ----------------------- | ---------------------------------------------------------------------- |
| `GET {base}/state`      | Objet `State` complet (voir `src/api/types.ts`).                       |
| `GET {base}/incidents`  | `{ items: Incident[] }`, plus récents d'abord (panneau Historique).    |
| `GET {base}/events`     | Server-Sent Events, événement `state` à chaque changement + toutes les 2 s. |

Protocole de repli (`src/api/client.ts`) : si le flux SSE tombe ou reste muet 6 s, le
dashboard passe en **polling** `GET state` toutes les 2 s et retente le SSE toutes les 15 s.
L'indicateur du bandeau affiche « temps réel », « polling » ou « hors ligne » ; l'écran
ne reste jamais figé.

## Zones de l'écran

1. **Bandeau d'état global** (`GlobalBanner`) : texte géant coloré selon `global_state`
   (NORMAL vert, ANOMALIE rouge, REMEDIATION orange, RETABLI vert + durée totale,
   ECHEC rouge sombre, SURETE violet), heure courante, indicateur de liaison, disjoncteur.
2. **État des services** (`ServiceTiles`) : front, auth, api, db, gateway — UP/DOWN,
   latence p95, taux 5xx, req/s. DOWN → rouge ; dégradé (5xx > 5 % ou p95 > 1 s) → orange.
3. **Chronologie de l'incident** (`IncidentTimeline` + `ProofCard`) : étapes « T+12 s »,
   plan d'action avec le niveau courant, carte verte pour la transaction de preuve.
   Bascule **Chronologie / Historique** (`HistoryPanel`) : seul contrôle de l'écran,
   purement visuel.
4. **Score d'anomalie** (`ScoreChart`) : score, seuil (rouge pointillé), aire rouge au-dessus
   du seuil, repères détection / action / rétabli.

## Production (Docker)

Image multi-étapes (`Dockerfile`) : build Node 24 → nginx 1.27.5 qui sert `dist/`.
`nginx.conf` : fallback SPA, assets hachés en cache long, `/healthz` → 200, accepte les
URL avec ou sans préfixe `/supervision/`. La gateway publie le conteneur sous
`/supervision/` et proxifie `/supervision/api/{state,incidents,events}` (GET) vers le
moteur de remédiation.

```bash
docker build -t poupal-supervision .                      # production (API réelle)
docker build -t poupal-supervision --build-arg VITE_USE_MOCK=true .   # démo autonome
```

## Structure

```
src/
  api/        types.ts (contrat), client.ts (fetch + SSE/polling), mock.ts (démo)
  hooks/      useLiveState.ts (état vivant partagé par l'écran)
  components/ GlobalBanner, ServiceTiles, IncidentTimeline, ProofCard, ScoreChart, HistoryPanel
  utils/      format.ts (heures, durées, %, €, libellés français)
  App.tsx     disposition de l'écran unique
```
