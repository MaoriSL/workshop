# Détection d'anomalies par apprentissage automatique — rapport d'ingénierie

Projet Resilience-Alpha, plateforme de paiement **fictive** Poupal. Ce rapport décrit comment le
détecteur apprend le fonctionnement normal de la plateforme et repère ce qui s'en écarte, sans
seuil métier codé en dur, et avec quelle fiabilité. Les chiffres de la section « Résultats » sont
produits par `python -m ml.detection.evaluate` (fichiers `reports/`).

## 1. Données utilisées

- **Source** : règles d'enregistrement Prometheus (`infra/prometheus/rules/recording.yml`), exportées
  en CSV par `scripts/export_metrics.py` (pas de 5 s, une colonne par variable et par service).
- **Période, nombre de points, variables** : voir `models/metadata.json` (`training_period`,
  `holdout_period`, `feature_count`) et le tableau de la section 6.
- **Trafic** : généré par `tools/traffic-gen` (10 utilisateurs fictifs, rythme variable, périodes
  calmes et chargées, erreurs de mot de passe occasionnelles). C'est un trafic **simulé** : voir les
  limites (section 8).
- **Périodes exclues** : `ml/data/labels.csv` liste les pannes contrôlées et attaques (start, end,
  type, description). Elles sont retirées de l'entraînement avec une marge de 60 s de chaque côté.

## 2. Préparation

1. Concaténation des CSV, tri chronologique, suppression des doublons de timestamp.
2. Trous (pas manquants) : signalés dans `metadata.json` (`gaps_detected`) ; valeurs manquantes
   comblées par la dernière valeur connue puis 0 — un service absent de Prometheus (arrêté) apparaît
   ainsi comme une chute brutale, ce qui est voulu.
3. Colonnes constantes : comptées mais **conservées** (ex. `service_up` vaut 1 en permanence en
   fonctionnement normal : c'est précisément sa chute à 0 qui signale une panne).
4. Variables (`features.py`, un seul module pour l'entraînement et le temps réel) : pour chaque
   règle retenue (requêtes/s, 4xx, 5xx, p50, p95, échecs de connexion/min, transactions/min par
   statut, CPU, mémoire et redémarrages des conteneurs auth/api/db/gateway, connexions à la base,
   disponibilité), 4 colonnes : valeur, moyenne et écart-type glissants sur 1 min (12 pas), variation
   par rapport au pas précédent ; plus deux ratios (transactions échouées / total, somme des taux 5xx).
5. Normalisation `RobustScaler` (médiane / écart interquartile) ajustée **uniquement** sur la partie
   entraînement : les valeurs de la réserve et du temps réel ne l'influencent jamais.

## 3. Modèle

- **Isolation Forest** (scikit-learn), non supervisé, entraîné sur le normal seulement :
  200 arbres, `contamination = 0.01`, graine fixe. Score d'anomalie = opposé de `decision_function`
  (plus haut = plus anormal). Le score retenu est le **maximum** entre la forêt globale (toutes les
  variables) et quatre forêts par service (15 à 40 variables chacune) : une forêt sur 150 dimensions
  isole mal un écart porté par une seule variable, les forêts par service le voient nettement.
- **Variables constantes en normal** (disponibilité = 1, taux de 5xx = 0, échecs de connexion ≈ 0,
  redémarrages, erreurs base) : une forêt ne peut pas les couper (aucune étendue à l'entraînement),
  donc elle ne voit pas leur écart. Deux réponses, documentées dans `model.py` : (1) le RobustScaler
  reçoit un plancher d'échelle (2 % de la médiane, ou un dixième de l'étendue normale) pour que tout
  écart devienne extrême ; (2) un terme explicite de « franchissement » (max de l'écart normalisé sur
  ces variables, ramené entre 0 et 1) s'ajoute au score. Sans lui, l'arrêt d'un service n'était détecté
  qu'à son redémarrage (95 s) ; avec lui, en 10 s.
- **Référence simple** : score z robuste `|x − médiane| / (1,4826 × MAD)`, maximum sur les
  variables ; même procédure de choix de seuil. Elle sert à justifier le choix de l'Isolation Forest
  avec des chiffres (section 6).
- **Choix du seuil** (`threshold.py`) : 25 % du normal, en fin de période, est mis de côté (jamais
  vu à l'entraînement). On rejoue dessus la machine à états du service temps réel pour des seuils
  croissants (quantiles 90 % → 99,99 % des scores normaux) et on retient le **plus bas** qui produit
  moins d'une fausse alerte par heure. La courbe seuil → fausses alertes/h est dans `metadata.json`
  (`threshold_curve`) : c'est le compromis sensibilité / fausses alertes.
- **Sauvegarde** : `models/model.joblib` + `models/metadata.json` (version, date, périodes,
  variables, hyperparamètres, seuil, résultats).

## 4. Explication des alertes

Pour chaque alerte (`GET /status`, incident envoyé au moteur de remédiation) :

- **3 variables les plus anormales** : valeur actuelle, valeur habituelle (médiane d'entraînement),
  écart (z robuste).
- **Service suspecté** : chaque métrique de base vote une fois (son plus grand écart, variantes
  glissantes confondues) pour le service auquel elle appartient ; une disponibilité tombée pèse 4,
  le trafic, les 5xx, la latence p95, les échecs de connexion et les connexions à la base pèsent 2,
  le CPU 0,5 (une panne ailleurs fait baisser le CPU partout).
- **Type d'incident** (`indisponibilite`, `surcharge`, `bruteforce`, `db_lente`, `inconnu`) :
  si au moins 3 exemples étiquetés par type et 2 types existent, un petit `RandomForest` est entraîné
  sur les pas de temps des scénarios (`incident_type_method = random_forest` dans `metadata.json`) ;
  sinon, le type est **déduit par règles** des variables les plus anormales
  (`incident_type_method = regles` : disponibilité à 0 ou trafic disparu avec 5xx → indisponibilité ;
  échecs de connexion → brute force ; connexions base ou p95 sans hausse de trafic → base lente ;
  hausse de trafic / CPU → surcharge). Dans les deux cas, la **détection** elle-même est faite par le
  modèle ML ; le type n'est qu'une étiquette d'aide à la remédiation.

## 5. Service temps réel

Toutes les 5 s : lecture des 3 dernières minutes des règles dans Prometheus, variables identiques
à l'entraînement (test `test_features.py` : égalité stricte entre calcul sur l'historique et calcul
sur le tampon glissant), score, puis machine à états `NORMAL → SUSPECT → ANOMALIE →
RÉTABLISSEMENT → NORMAL` : 2 dépassements sur 3 fenêtres confirment (≈ 10 à 15 s après le premier
dépassement), 6 fenêtres calmes (30 s) rétablissent. Incidents signés HMAC-SHA256 vers le moteur de
remédiation (`docs/api/incident.md`), métriques `poupal_anomaly_*` et dashboard « Poupal — Détection ».

## 6. Résultats

<!-- RESULTS:BEGIN -->
**Modèle `2026.10.20-1351`** — entraîné le 2026-10-20 13:52 UTC.

| Donnée | Valeur |
|---|---|
| Points exportés | 4321 (pas 5.0 s, 0 trou(s)) |
| Points étiquetés exclus (scénarios, démarrage sans trafic, panne du générateur, maintenance) | 3301 |
| Entraînement (normal) | 07:53:05 → 13:29:45 UTC, 765 points |
| Réserve normale (choix du seuil) | 13:29:50 → 13:51:00 UTC, 255 points |
| Variables | 154 (dont 15 « signaux de panne » constants en normal) |
| Hyperparamètres | 200 arbres, contamination 0.01, RobustScaler à plancher, graine 42 |
| Machine à états | 2 sur 3 fenêtres pour confirmer, 6 pour rétablir |
| Seuil retenu | 0.180 (courbe : q0.9 → seuil 0.023 : 11.294 FA/h ; q0.95 → seuil 0.050 : 2.824 FA/h ; q0.975 → seuil 0.160 : 2.824 FA/h ; q0.99 → seuil 0.180 : 0.0 FA/h ; q0.995 → seuil 0.183 : 0.0 FA/h ; q0.999 → seuil 0.213 : 0.0 FA/h ; q0.9999 → seuil 0.222 : 0.0 FA/h) |
| Type d'incident | regles |

Résultats sur les scénarios étiquetés (`reports/evaluation.json`) :

| Scénario | Début (UTC) | Détecté | Délai | Service suspecté | Type trouvé | Type OK | Référence z (détecté / délai) |
|---|---|---|---|---|---|---|---|
| outage | 08:09:52 | oui | 13.0 s | poupal-api | indisponibilite | oui | non / - |
| db_slow | 08:15:34 | oui | 36.0 s | poupal-db | indisponibilite | non | non / - |
| bruteforce | 08:20:50 | oui | 15.0 s | poupal-auth | bruteforce | oui | non / - |
| overload | 08:26:22 | non | - | - | - | - | non / - |
| outage | 08:32:30 | oui | 10.0 s | poupal-auth | indisponibilite | oui | non / - |
| outage | 12:22:33 | oui | 12.0 s | poupal-api | indisponibilite | oui | non / - |
| outage | 12:25:38 | oui | 12.0 s | poupal-api | indisponibilite | oui | non / - |
| bruteforce | 12:29:57 | oui | 13.0 s | poupal-auth | bruteforce | oui | non / - |
| db_slow | 12:34:15 | non | - | - | - | - | non / - |
| overload | 12:38:36 | non | - | - | - | - | non / - |
| db_slow | 12:43:43 | oui | 42.0 s | poupal-auth | bruteforce | non | non / - |

Fausses alertes / heure sur le normal de réserve : Isolation Forest = 0.0 ; référence z robuste = 0.0.

Lecture : 8/11 scénarios détectés, délai moyen 19.1 s (objectif 30 s), 0 fausse alerte
par heure sur la réserve normale. Les arrêts de service et la rafale d'échecs de connexion sont
détectés en 10 à 15 s avec le bon service et le bon type. Le pic de charge (« overload ») n'est pas
détecté : avec dix utilisateurs simulés, le trafic triplé reste dans l'enveloppe des périodes chargées
vues à l'entraînement — c'est la limite « vrai pic vs attaque » (section 8). La base ralentie est détectée
une fois sur deux, tardivement (42 s) et mal typée : les variables propres à la base (connexions actives,
latence) bougent peu tant que les requêtes bloquées ne sont pas terminées ; une métrique « requêtes en
cours » côté API est la piste d'amélioration (section 8). La référence « z robuste », avec la même
contrainte de fausses alertes, ne détecte aucun scénario : un seuil sur une variable isolée est soit trop
sensible, soit aveugle ; la forêt combine les variables.
<!-- RESULTS:END -->

Graphiques : `reports/anomaly_score.png` (score dans le temps, seuil, périodes étiquetées surlignées)
et `reports/detection_delays.png` (délai par scénario, objectif 30 s).

## 7. Réentraîner rapidement

```bash
python scripts/export_metrics.py --since 2h --step 5s && python -m ml.detection.train && python -m ml.detection.evaluate && (cd infra && docker compose restart anomaly-detector)
```

Une attaque réelle s'ajoute avec `python ml/detection/scenarios/inject.py label --type attack --start … --end …`
puis la même commande : la période est exclue de l'entraînement et évaluée comme un scénario.

## 8. Limites (en toute honnêteté)

- **Trafic normal simulé** : dix utilisateurs fictifs au comportement programmé. Le « normal » appris
  est plus régulier qu'un vrai trafic ; de vrais clients produiraient plus de fausses alertes au début.
- **Période d'entraînement courte** (quelques heures) : pas de cycle jour/nuit ni de semaine, donc
  aucune saisonnalité apprise. Un pic d'activité légitime inhabituel ressemblera à une anomalie.
- **Attaques jamais vues à l'entraînement** : le modèle apprend le normal, pas les attaques. Il
  détecte un écart, pas une signature : une attaque qui imite parfaitement le trafic normal (faible
  volume, bons identifiants) passe inaperçue.
- **Vrai pic d'activité vs attaque** : les deux sont des écarts au normal. Le type « surcharge » est
  attribué dans les deux cas ; distinguer les deux demande des signaux supplémentaires (répartition
  par IP, user-agents, provenance), prévus via les logs de la gateway mais non intégrés ici.
- **Dérive dans le temps** : après une mise à jour (nouvelle version, plus d'utilisateurs), le normal
  change et le modèle doit être réentraîné ; aucune détection de dérive automatique n'est en place.
- **Attribution et type** : le service suspecté et le type sont des heuristiques (votes pondérés,
  règles ou petit classifieur sur très peu d'exemples). Ils aident la remédiation mais peuvent se
  tromper, notamment quand une panne en entraîne une autre (api gelée → le trafic disparaît partout).
- **Échantillon d'évaluation réduit** : quelques scénarios de chaque type ; les délais mesurés sont
  indicatifs, pas des garanties statistiques.
- **Base ralentie peu visible** : tant que les requêtes bloquées ne se terminent pas, ni la latence ni
  les erreurs ne sont enregistrées côté API ; seules les connexions actives à la base et la gateway
  réagissent. Ajouter une métrique « requêtes en cours » (jauge) aux services rendrait ce cas net.
- **Dépendance à Prometheus** : si Prometheus tombe, le détecteur est aveugle (`/ready` passe à
  false) ; le filet de sécurité des alertes Prometheus tombe avec lui.
