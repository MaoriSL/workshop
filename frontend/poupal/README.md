# Poupal — site vitrine et espace client

> **Environnement de démonstration — plateforme fictive, aucun paiement réel.**

Poupal est une plateforme de paiement **entièrement fictive**, créée pour le Workshop
Bac+5 EPSI *Resilience-Alpha* (démonstrateur de cyber-résilience). Ce dépôt contient le
**front** : le site vitrine (landing) et l'espace client (tableau de bord, envoi d'argent,
détail des transactions).

Aucune donnée bancaire ou personnelle réelle n'est utilisée : l'utilisateur, les contreparties,
les montants et les références sont inventés. Le site fonctionne aujourd'hui avec des données
factices embarquées (mode *mock*) et se rebranche sur la vraie API REST et le service
d'authentification (JWT) en renseignant une seule variable d'environnement (voir
[Rebrancher la vraie API](#6-rebrancher-la-vraie-api)).

**Stack** : React 18 · Vite 8 · TypeScript (strict) · Tailwind CSS v4 · React Router 7 ·
lucide-react (icônes) · Montserrat (Google Fonts).

---

## Sommaire

1. [Prérequis](#1-prérequis)
2. [Installation et lancement](#2-installation-et-lancement)
3. [Structure du projet](#3-structure-du-projet)
4. [Pages et parcours](#4-pages-et-parcours)
5. [Comptes de démonstration](#5-comptes-de-démonstration)
6. [Rebrancher la vraie API](#6-rebrancher-la-vraie-api)
7. [Docker (image de production)](#7-docker-image-de-production)
8. [Conventions de code](#8-conventions-de-code)
9. [Règles d'or du projet](#9-règles-dor-du-projet)

---

## 1. Prérequis

- **Node.js 20.19 ou plus récent** (Node 22 LTS ou 24 recommandé — exigé par Vite 8) ;
- **npm** (livré avec Node) ;
- *(optionnel)* **Docker** pour construire l'image de production.

> **Note — dépôt sur un partage réseau (NAS).** Le dépôt du Workshop est hébergé sur un
> partage réseau. Pour un développement confortable (installation des dépendances, rechargement
> à chaud), copiez le dossier `frontend/poupal` en local avant de lancer `npm install`, puis
> reportez vos modifications dans le dépôt.

## 2. Installation et lancement

```bash
cd frontend/poupal
npm install          # installe les dépendances (une seule fois)
npm run dev          # serveur de développement → http://localhost:5173
```

Sans configuration supplémentaire, l'application démarre en **mode démonstration** (données
factices, aucun appel réseau). Les autres scripts, tels que définis dans `package.json` :

| Commande            | Rôle                                                                           |
| ------------------- | ------------------------------------------------------------------------------ |
| `npm run dev`       | Serveur de développement Vite avec rechargement à chaud (port 5173).           |
| `npm run build`     | Vérification TypeScript (`tsc -b`) puis build de production dans `dist/`.      |
| `npm run preview`   | Sert le contenu de `dist/` tel qu'il sera déployé (port 4173).                 |
| `npm run typecheck` | Vérification des types uniquement (`tsc -b`), sans produire de build.          |

## 3. Structure du projet

```text
frontend/poupal/
├── public/                      # fichiers servis tels quels (logos, favicon)
│   ├── logo-poupal.png          #   logo sur fond clair (header, pages)
│   └── logo-poupal-white.png    #   logo sur fond foncé (footer) — à déposer
├── src/
│   ├── api/                     # COUCHE RÉSEAU centralisée (seul endroit qui parle à l'API)
│   │   ├── client.ts            #   fetch JSON, base URL (VITE_API_URL), JWT, ApiError
│   │   ├── auth.ts              #   login / signup / getCurrentUser / logout
│   │   ├── transactions.ts      #   getAccount / listTransactions / getTransaction / sendMoney
│   │   ├── index.ts             #   point d'entrée unique : import { ... } from '@/api'
│   │   └── mock/                #   données factices + latence simulée (mode démo)
│   ├── components/
│   │   ├── ui/                  #   briques réutilisables : Button, Input, Card, Badge,
│   │   │                        #   Avatar, Spinner, Skeleton, Alert, EmptyState
│   │   ├── layout/              #   Logo, DemoBanner, Header, Footer + les 3 gabarits
│   │   │                        #   (PublicLayout, AuthLayout, AppLayout)
│   │   ├── landing/             #   sections de la page d'accueil (hero, avantages, étapes…)
│   │   ├── transactions/        #   liste et lignes de transactions, carte de solde
│   │   ├── send/                #   étapes du flux d'envoi d'argent
│   │   ├── ProtectedRoute.tsx   #   garde des routes de l'espace client (redirige vers /login)
│   │   └── ScrollToTop.tsx      #   remonte en haut de page à chaque navigation
│   ├── context/                 # AuthContext : utilisateur connecté, login / signup / logout
│   ├── hooks/                   # useAuth(), usePageTitle()
│   ├── pages/                   # une page par route (Landing, Login, Dashboard, Send…)
│   ├── types/                   # types partagés = contrat de données front ⇄ API
│   ├── utils/                   # format.ts (montants / dates fr-FR via Intl), cn.ts
│   ├── App.tsx                  # routeur : routes publiques, d'authentification, protégées
│   ├── index.css                # Tailwind v4 + design tokens Poupal (@theme) + animations
│   └── main.tsx                 # point d'entrée React
├── .env.example                 # variables d'environnement documentées (à copier en .env)
├── Dockerfile                   # image de production (build Node → nginx)
├── nginx.conf                   # config nginx : SPA, cache, gzip, /healthz, sécurité
├── index.html                   # page HTML racine (police Montserrat, meta)
├── vite.config.ts               # Vite + React + Tailwind + alias "@/" → src/
└── tsconfig*.json               # TypeScript strict
```

Principes : les **pages** composent des **composants** ; les composants n'appellent jamais
`fetch` directement, ils passent par `src/api/` ; les **types** décrivent le contrat de données
avec l'API, qu'elle soit simulée ou réelle.

## 4. Pages et parcours

| Route               | Gabarit      | Contenu                                                                  |
| ------------------- | ------------ | ------------------------------------------------------------------------ |
| `/`                 | PublicLayout | Landing : hero, avantages, « comment ça marche », appel à l'inscription. |
| `/login`            | AuthLayout   | Connexion (email + mot de passe), lien « mot de passe oublié ».          |
| `/signup`           | AuthLayout   | Inscription (nom, email, mot de passe, confirmation).                    |
| `/forgot-password`  | AuthLayout   | Demande de réinitialisation (simulée).                                   |
| `/dashboard`        | AppLayout 🔒 | Solde, bouton « Envoyer de l'argent », dernières transactions.           |
| `/send`             | AppLayout 🔒 | Formulaire d'envoi (destinataire, montant, message).                     |
| `/send/confirm`     | AppLayout 🔒 | Récapitulatif avant validation.                                          |
| `/send/success`     | AppLayout 🔒 | Écran de succès animé.                                                   |
| `/transactions/:id` | AppLayout 🔒 | Détail d'une transaction.                                                |
| `*`                 | —            | Page 404.                                                                |

🔒 = route protégée : sans session, l'utilisateur est redirigé vers `/login` puis ramené sur la
page demandée après connexion. Le bandeau « environnement de démonstration » est affiché sur
toutes les pages.

## 5. Comptes de démonstration

En mode *mock* (configuration par défaut), **aucun compte n'est à créer** :

- sur `/login`, **n'importe quel email valide** (ex. `alex.martin@poupal.demo`) et **un mot de
  passe d'au moins 8 caractères** connectent l'utilisateur de démonstration ;
- sur `/signup`, le nom saisi est repris dans l'espace client ;
- l'utilisateur affiché est **Alex Martin**, solde **2 450,00 €**, avec 10 transactions
  fictives (statuts *réussi*, *en attente*, *échoué*). Les données vivent en mémoire : un envoi
  réussi débite le solde et apparaît dans la liste jusqu'au rechargement de la page.

Le « JWT » du mode mock (`src/api/mock/data.ts`) est un jeton factice sans aucune valeur de
sécurité ; il sert uniquement à exercer le même code que la vraie API.

## 6. Rebrancher la vraie API

### 6.1 Configuration

```bash
cp .env.example .env     # .env est ignoré par Git : il ne doit jamais être commité
```

| Variable        | Exemple                     | Rôle                                                                             |
| --------------- | --------------------------- | -------------------------------------------------------------------------------- |
| `VITE_API_URL`  | `http://localhost:8000/api` | Base URL de l'API REST. **Vide = mode mock** (données factices).                 |
| `VITE_USE_MOCK` | `true` / `false`            | `true` force le mode mock même si `VITE_API_URL` est renseignée (utile en démo). |

La règle, dans `src/api/client.ts`, tient en une ligne :
`USE_MOCK = VITE_USE_MOCK === 'true' || VITE_API_URL === ''`. Les variables `VITE_*` sont lues
**au moment du build** : après modification de `.env`, relancer `npm run dev` ou `npm run build`.

### 6.2 Authentification (JWT)

- `POST /auth/login` et `POST /auth/signup` renvoient `{ token, user }` ; le `token` est stocké
  dans `localStorage` (clé `poupal.token`).
- Toutes les requêtes suivantes portent l'en-tête **`Authorization: Bearer <JWT>`**.
- Au démarrage, le front appelle `GET /auth/me` pour restaurer la session ; une réponse `401`
  ou `403` efface le jeton et ramène l'utilisateur sur l'écran de connexion.
- La déconnexion est locale (suppression du jeton) ; aucun appel réseau n'est nécessaire.

### 6.3 Contrat REST attendu

Toutes les routes échangent du JSON (`Content-Type: application/json`). Les chemins sont
relatifs à `VITE_API_URL`. Les types correspondent à `src/types/index.ts`.

| Méthode | Route               | Corps de la requête               | Réponse (2xx)                              | Auth |
| ------- | ------------------- | --------------------------------- | ------------------------------------------ | :--: |
| `POST`  | `/auth/login`       | `{ email, password }`             | `{ token, user }`                          |  —   |
| `POST`  | `/auth/signup`      | `{ name, email, password }`       | `{ token, user }`                          |  —   |
| `GET`   | `/auth/me`          | —                                 | `User`                                     |  ✓   |
| `GET`   | `/account`          | —                                 | `{ balance, currency }`                    |  ✓   |
| `GET`   | `/transactions`     | —                                 | `Transaction[]` (plus récentes en premier) |  ✓   |
| `GET`   | `/transactions/:id` | —                                 | `Transaction` (`404` si inconnue)          |  ✓   |
| `POST`  | `/transactions`     | `{ recipient, amount, message? }` | `Transaction` créée                        |  ✓   |

**Objets échangés** (exemples) :

```jsonc
// User
{ "id": "usr_demo_0001", "name": "Alex Martin", "email": "alex.martin@poupal.demo",
  "createdAt": "2025-03-12T10:00:00Z" }

// Account
{ "balance": 2450, "currency": "EUR" }

// Transaction — amount est toujours positif, le signe se déduit de "type"
{
  "id": "txn_0010",
  "reference": "PP-2026-0410",          // référence lisible affichée au client
  "type": "received",                   // "sent" | "received"
  "status": "completed",                // "completed" | "pending" | "failed"
  "counterparty": "Camille Dupont",
  "counterpartyEmail": "camille.dupont@exemple.fr",   // optionnel
  "amount": 120,
  "currency": "EUR",
  "date": "2026-10-18T14:32:00Z",       // ISO 8601
  "message": "Remboursement restaurant" // optionnel
}

// Corps de POST /transactions (recipient = email ou nom du destinataire)
{ "recipient": "camille.dupont@exemple.fr", "amount": 45.5, "message": "Merci !" }
```

### 6.4 Gestion des erreurs

- Toute réponse non-2xx est transformée en `ApiError(status, message)`. Le message affiché à
  l'utilisateur est lu dans le corps JSON : **`{ "message": "…" }`** ou, à la manière de
  FastAPI, **`{ "detail": "…" }`** ; à défaut, « Erreur `<status>` ».
- Une panne réseau (service injoignable) donne une `ApiError` de statut `0` avec un message
  explicite : c'est ce que l'utilisateur voit pendant un incident, avant la remédiation.
- Une réponse `204 No Content` est acceptée (résultat `undefined`).
- Côté pages, `getErrorMessage(error)` fournit toujours un texte lisible pour le composant `Alert`.

Pour l'API métier, les cas attendus sont au minimum : `400` montant invalide ou solde insuffisant,
`401` identifiants incorrects / jeton expiré, `404` transaction inconnue.

## 7. Docker (image de production)

Le `Dockerfile` est en deux étapes : build Vite sous Node, puis **nginx** qui sert les fichiers
statiques de `dist/`. Les variables `VITE_*` étant intégrées au build, elles se passent en
`--build-arg` :

```bash
# Build (mode mock par défaut ; indiquer l'URL de l'API pour la version branchée)
docker build -t poupal-front --build-arg VITE_API_URL=http://localhost:8000/api .

# Lancement : le site est disponible sur http://localhost:8080
docker run --rm -p 8080:80 poupal-front
```

Points utiles pour l'atelier (supervision et remédiation automatique) :

- **`GET /healthz`** répond `200 ok` : sonde utilisée par le `HEALTHCHECK` Docker, par la
  supervision et par le moteur de remédiation pour vérifier que le front est vivant ;
- `nginx.conf` gère le routage côté client (toute URL inconnue renvoie `index.html`), la
  compression gzip, un cache long pour `/assets/` (fichiers hachés) et aucun cache pour
  `index.html`, ainsi que des en-têtes de sécurité (`X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`) ;
- `.dockerignore` exclut `node_modules`, `dist`, `.git` et **tous les fichiers `.env`** (hors
  `.env.example`) : aucun secret ne peut se retrouver dans l'image.

Dans la plateforme complète, ce conteneur est orchestré par `infra/docker-compose.yml`.

## 8. Conventions de code

- **TypeScript strict** (`strict`, `noUnusedLocals`, `noUnusedParameters`) : `npm run typecheck`
  doit passer sans erreur avant tout commit.
- **Composants réutilisables** dans `src/components/ui` (variants explicites, props typées) ;
  les pages ne contiennent que de la composition et de la logique d'écran.
- **Couche réseau centralisée** dans `src/api/` ; base URL via `VITE_API_URL` ; jamais de
  `fetch` dans un composant.
- **Formatage français via `Intl`** (`src/utils/format.ts`) : `1 250,00 €`, `14 oct. 2026`.
  Aucun symbole monétaire ni format de date codé en dur dans les pages.
- **Accessibilité de base** : labels sur chaque champ, focus visibles, contrastes respectés,
  icônes décoratives en `aria-hidden`.
- **Imports via l'alias `@/`** (`import { Button } from '@/components/ui'`).
- **Code simple et commenté en français** : le jury lit le code, chaque membre doit pouvoir
  l'expliquer. Pas de dépendance superflue, pas de « magie ».
- **Aucun secret dans le code** : `.env` est ignoré par Git ; seul `.env.example` (sans valeur
  sensible) est versionné.
- Commits conventionnels (`feat:`, `fix:`, `docs:`…), clairs et atomiques.

## 9. Règles d'or du projet

- **Tout est fictif** : marque inventée, données simulées, aucun paiement réel, aucune connexion
  à un vrai service de paiement. La mention « environnement de démonstration » est affichée
  sur chaque page.
- **Aucun secret en clair** : jamais de mot de passe, clé ou jeton dans le code ou dans Git.
- Le front est une brique du démonstrateur *Resilience-Alpha* : il doit rester joignable et
  **une nouvelle transaction doit réussir** après un incident — c'est la preuve attendue de la
  reprise automatique, sans intervention humaine.
