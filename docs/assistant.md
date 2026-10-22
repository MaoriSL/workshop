# Assistant RAG Poupal

L'assistant est une fonctionnalité de démonstration : il répond à partir des
documents fictifs du dépôt et utilise un modèle Ollama hébergé sur le PC
Windows du groupe. Aucune donnée bancaire ou personnelle réelle ne doit être
ajoutée aux documents.

## Configuration

Dans `infra/.env`, renseigner l'adresse du PC qui héberge Ollama :

```env
OLLAMA_BASE_URL=http://10.60.12.66:11434
OLLAMA_MODEL=qwen3:4b
```

Le modèle `qwen3:4b` respecte la limite de 8 milliards de paramètres du sujet.
Le port Ollama doit rester limité au réseau privé de la démonstration.

## Lancement et vérification

```bash
cd infra
docker compose up -d --build assistant
curl http://localhost:${GATEWAY_PORT:-8080}/assistant/health
curl http://localhost:${GATEWAY_PORT:-8080}/assistant/ready
curl -X POST http://localhost:${GATEWAY_PORT:-8080}/assistant/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"Comment fonctionne la remédiation automatique ?"}'
```

`/health` vérifie que le service est lancé. `/ready` vérifie en plus l'accès
réseau à Ollama. La réponse de `/query` contient les sources documentaires
utilisées.
