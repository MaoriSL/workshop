# traffic-gen — trafic « normal » pour Poupal

> Environnement de démonstration : plateforme de paiement **fictive**, comptes `@poupal.demo` inventés,
> aucun paiement réel.

Petit service Python (bibliothèque standard uniquement) qui simule jusqu'à **10 clients** de Poupal
passant par la gateway comme de vrais navigateurs : connexion, solde, historique, détail d'une
transaction, petits virements entre eux. Il tourne en permanence à côté de la plateforme pour :

- donner au **modèle de détection** un comportement normal à apprendre (périodes calmes et chargées) ;
- rendre la **reprise visible** pendant la démo : les virements s'arrêtent avec l'incident et repartent
  d'eux-mêmes (`poupal:transactions_per_minute` dans Grafana, logs `service="traffic-gen"` dans Loki).

## Variables d'environnement (fournies par `infra/docker-compose.yml` depuis `infra/.env`)

| Variable | Défaut | Rôle |
|---|---|---|
| `TRAFFIC_ENABLED` | `true` | `false` : veille (aucune requête, mais heartbeat et log `traffic_paused`) |
| `TRAFFIC_BASE_URL` | `http://gateway:80` | Entrée unique de la plateforme (`/auth`, `/api`) |
| `TRAFFIC_USERS` | `10` | Nombre de clients simulés (1 à 10), pris dans l'ordre alex, camille, léa, nathan, julie, hugo, sophie, lucas, emma, thomas |
| `TRAFFIC_INTENSITY` | `1.0` | Multiplie le rythme : `0.5` calme, `2.0` chargé (borné à 0,1 – 5) |
| `TRAFFIC_PASSWORD` | — | Mot de passe commun des comptes de démo (= `DEMO_PASSWORD`), jamais journalisé |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

## Activer / désactiver

```bash
cd infra
docker compose up -d --build traffic-gen          # démarrer (ou reconstruire)
docker compose logs -f traffic-gen                # suivre les logs JSON
# Mettre en veille sans supprimer le conteneur : TRAFFIC_ENABLED=false dans infra/.env puis
docker compose up -d traffic-gen
```

Le conteneur est `healthy` tant que la boucle principale touche `/tmp/traffic-gen.heartbeat`
(toutes les 5 s, y compris en veille) ; le healthcheck tolère 120 s de silence.

## Pourquoi ces limites ?

- **Connexions : 3 par minute, tous clients confondus.** Le service auth bloque à 5 connexions
  par minute **et par adresse IP**, et les 10 clients simulés sortent tous avec l'IP du conteneur.
  Les connexions sont donc échelonnées (budget partagé entre threads), les jetons JWT réutilisés
  pendant ~25 min (durée de vie 30 min) et renouvelés seulement à l'approche de l'expiration ou
  sur un `401`. Au démarrage, les 10 clients sont connectés en 3 à 4 minutes : c'est voulu.
- **Virements : 6 par minute et par client au maximum** (l'API en refuse plus de 10) ; en pratique
  un client fait ~1 virement par minute à intensité 1.
- **Un « mauvais mot de passe » toutes les 10 à 20 min**, pris sur le même budget : du bruit réaliste
  pour la détection, très loin d'une force brute (alerte à 30 échecs/min).
- **Circuit fermé** : les virements (1,00 € à 9,99 €) ne circulent qu'entre les clients simulés, donc la
  somme des soldes reste constante et `/internal/consistency` reste `ok`.

Comportement : un thread par client, pauses log-normales (médiane 8 s), facteur de charge global
qui ondule lentement entre 0,5 et 1,5 (cycle de 10 à 20 min), actions pondérées
(solde 40 %, historique 35 %, détail 10 %, virement 15 %). Pendant un incident (gateway ou API
injoignable, 5xx), chaque client attend un peu plus à chaque échec (2 s → 20 s) puis réessaie :
la reprise est constatée en moins de 30 s.

## Logs (JSON sur stdout, collectés par Alloy → Loki, labels `service`, `level`, `event`)

`traffic_started`, `traffic_paused`, `traffic_stopping` / `traffic_stopped`, `user_login`
(`result` = `success` ou `bad_password` volontaire), `user_action` (`action`, `route`, `status`,
`latency_ms`, `request_id` corrélable avec la gateway et l'API), `user_error` (`kind` = `unreachable`,
`http_error`, `rate_limited`, `rejected`, `login_refused`) et `traffic_stats` toutes les 60 s
(requêtes, erreurs, 429, connexions, virements, clients connectés, facteur de charge).
Jamais de mot de passe ni de jeton dans les logs.

Exemple de requête Loki : `{service="traffic-gen", event="user_error"} | json`.
