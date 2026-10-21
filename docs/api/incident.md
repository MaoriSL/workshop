# Contrat « incident » — détecteur d'anomalies → moteur de remédiation

Le détecteur (`ml/detection/service`, conteneur `anomaly-detector`) **détecte mais n'agit pas**.
À chaque passage en **ANOMALIE** puis en **NORMAL**, il envoie un incident au moteur de
remédiation par `POST` JSON sur `REMEDIATION_URL`. Tant que cette variable est vide, l'incident
est seulement journalisé (`event=anomaly_detected` / `anomaly_resolved` dans Loki).

## Transport et signature

| Élément | Valeur |
|---|---|
| Méthode | `POST {REMEDIATION_URL}` (ex. `http://remediation:8002/incidents`) |
| En-tête | `Content-Type: application/json` |
| Signature | `X-Poupal-Signature: sha256=<hex>` = HMAC-SHA256(secret partagé, corps brut) |
| Secret | variable d'environnement `REMEDIATION_HMAC_SECRET`, identique des deux côtés (jamais dans le code) |
| Corps | JSON **canonique** : clés triées, séparateurs `,` et `:` sans espace, UTF-8 (`json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`) |
| Reprise | 3 tentatives (1 s, 2 s, 4 s) si le moteur ne répond pas ou renvoie ≠ 2xx |
| Réponse attendue | `2xx` (corps libre) ; `401` si la signature est absente ou invalide |

Le moteur **refuse tout incident non signé** : il recalcule le HMAC sur les octets reçus et
compare en temps constant (`hmac.compare_digest`). Personne d'autre ne peut déclencher une réparation.

## Corps de l'incident

```json
{
  "incident_id": "inc-20261020T081530Z-3f9a",
  "state": "ANOMALIE",
  "detected_at": "2026-10-20T08:15:30.412+00:00",
  "resolved_at": null,
  "score": 0.812,
  "threshold": 0.471,
  "suspected_service": "poupal-api",
  "incident_type": "indisponibilite",
  "top_features": [
    { "name": "service_up__api", "value": 0.0, "baseline": 1.0, "deviation": -14.2 },
    { "name": "http_requests_per_second_rate1m__poupal-api", "value": 0.0, "baseline": 4.8, "deviation": -6.9 },
    { "name": "http_error_ratio_5xx_rate1m__poupal-gateway", "value": 0.97, "baseline": 0.0, "deviation": 12.5 }
  ],
  "model_version": "2026.10.20-1"
}
```

| Champ | Type | Sens |
|---|---|---|
| `incident_id` | string | identifiant stable de l'incident (même valeur à la détection et à la résolution) |
| `state` | `"ANOMALIE"` \| `"NORMAL"` | passage en anomalie confirmée, ou retour à la normale |
| `detected_at` | ISO 8601 UTC | début de l'anomalie confirmée |
| `resolved_at` | ISO 8601 UTC ou `null` | renseigné quand `state = "NORMAL"` |
| `score` | nombre | score d'anomalie courant (plus haut = plus anormal) |
| `threshold` | nombre | seuil du modèle (choisi à l'entraînement, voir `models/metadata.json`) |
| `suspected_service` | string | `poupal-auth`, `poupal-api`, `poupal-gateway`, `poupal-db` ou `inconnu` |
| `incident_type` | string | `indisponibilite`, `surcharge`, `bruteforce`, `db_lente`, `inconnu` |
| `top_features` | liste | les 3 variables les plus anormales : valeur actuelle, valeur habituelle (médiane d'entraînement), écart (score z robuste) |
| `model_version` | string | version du modèle qui a produit l'alerte |

Le même JSON est disponible à tout moment sur `GET /status` du détecteur, et l'historique sur `GET /incidents`.
