"""API RAG Poupal : recherche documentaire locale et génération via Ollama."""
from __future__ import annotations

import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import FastAPI, HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

SERVICE_NAME = "poupal-assistant"
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:4b")
DOCUMENT_ROOTS = (
    Path(os.environ.get("DOCUMENT_ROOT", "/app/docs")),
)
MAX_DOCUMENTS = int(os.environ.get("RAG_MAX_DOCUMENTS", "4"))
MAX_CONTEXT_CHARS = int(os.environ.get("RAG_MAX_CONTEXT_CHARS", "12000"))

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger(SERVICE_NAME)


class QueryRequest(BaseModel):
    question: Annotated[str, Field(min_length=3, max_length=2000)]


class Source(BaseModel):
    path: str
    score: int


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source]
    model: str


class IncidentSummaryRequest(BaseModel):
    incident: dict[str, Any]


class Document:
    def __init__(self, path: Path, content: str) -> None:
        self.path = path
        self.content = content
        self.tokens = set(re.findall(r"[a-z0-9àâçéèêëîïôùûüÿœ-]{3,}", content.lower()))


def load_documents() -> list[Document]:
    documents: list[Document] = []
    for root in DOCUMENT_ROOTS:
        if not root.exists():
            logger.warning("document_root_missing path=%s", root)
            continue
        for path in sorted(root.rglob("*.md")):
            try:
                content = path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("document_read_failed path=%s error=%s", path, exc)
                continue
            if content.strip():
                documents.append(Document(path, content))
    if not documents:
        raise RuntimeError("Aucun document RAG disponible.")
    return documents


DOCUMENTS = load_documents()


def retrieve(question: str) -> list[tuple[Document, int]]:
    question_tokens = set(re.findall(r"[a-z0-9àâçéèêëîïôùûüÿœ-]{3,}", question.lower()))
    ranked = [(document, len(question_tokens & document.tokens)) for document in DOCUMENTS]
    return sorted(ranked, key=lambda item: item[1], reverse=True)[:MAX_DOCUMENTS]


def build_context(results: list[tuple[Document, int]]) -> str:
    chunks: list[str] = []
    total = 0
    for document, _ in results:
        remaining = MAX_CONTEXT_CHARS - total
        if remaining <= 0:
            break
        content = document.content[:remaining]
        chunks.append(f"### {document.path.name}\n{content}")
        total += len(content)
    return "\n\n".join(chunks)


def ask_model(question: str, context: str) -> str:
    model = ChatOllama(
        base_url=OLLAMA_BASE_URL,
        model=OLLAMA_MODEL,
        temperature=0,
    )
    messages = [
        SystemMessage(
            content=(
                "Tu es l'assistant technique de Poupal, une plateforme de paiement "
                "entièrement fictive utilisée en démonstration. Réponds en français. "
                "Utilise uniquement le contexte fourni. Si la réponse n'y figure pas, "
                "dis clairement que l'information est absente. Ne prétends jamais "
                "effectuer une opération réelle et rappelle le caractère fictif si "
                "la question concerne un paiement ou une donnée sensible."
            )
        ),
        HumanMessage(content=f"Contexte documentaire :\n{context}\n\nQuestion : {question}"),
    ]
    response = model.invoke(messages)
    return str(response.content).strip()


def incident_context(incident: dict[str, Any]) -> str:
    timeline = incident.get("timeline") or []
    lines = [
        f"Identifiant : {incident.get('incident_id', 'inconnu')}",
        f"Type : {incident.get('incident_type', 'inconnu')}",
        f"Service suspecté : {incident.get('suspected_service', 'inconnu')}",
        f"Détection : {incident.get('detected_at', 'inconnue')}",
        f"Réception par le moteur : {incident.get('received_at', 'inconnue')}",
        f"État final : {incident.get('state', 'inconnu')}",
        f"Fin de remédiation : {incident.get('resolved_at', 'inconnue')}",
        f"Durée détection → preuve : {incident.get('recovery_seconds', 'inconnue')} secondes",
        f"Actions exécutées : {incident.get('actions_done', 0)}",
        "Chronologie exacte :",
    ]
    for entry in timeline:
        lines.append(
            f"- {entry.get('t', 'heure inconnue')} | {entry.get('step', 'étape inconnue')} | "
            f"{entry.get('label', '')} | détails={entry.get('details', {})}"
        )
    lines.append(f"Preuve de reprise : {incident.get('proof') or 'absente'}")
    return "\n".join(lines)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info(
        "assistant_started model=%s ollama=%s documents=%d",
        OLLAMA_MODEL,
        OLLAMA_BASE_URL,
        len(DOCUMENTS),
    )
    yield


app = FastAPI(
    title="Poupal Assistant RAG",
    description="Assistant de démonstration basé sur les documents du projet et Ollama.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME, "documents": len(DOCUMENTS)}


@app.get("/ready")
async def ready() -> dict:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            response.raise_for_status()
    except (httpx.HTTPError, OSError) as exc:
        raise HTTPException(status_code=503, detail="Ollama indisponible.") from exc
    return {"status": "ready", "model": OLLAMA_MODEL, "ollama": OLLAMA_BASE_URL}


@app.post("/query", response_model=QueryResponse)
def query(payload: QueryRequest) -> QueryResponse:
    results = retrieve(payload.question)
    try:
        answer = ask_model(payload.question, build_context(results))
    except Exception as exc:
        logger.error("ollama_query_failed error=%s", exc)
        raise HTTPException(status_code=503, detail="Le modèle Ollama est indisponible.") from exc
    return QueryResponse(
        answer=answer,
        sources=[Source(path=str(document.path), score=score) for document, score in results if score > 0],
        model=OLLAMA_MODEL,
    )


@app.post("/incident-summary", response_model=QueryResponse)
def incident_summary(payload: IncidentSummaryRequest) -> QueryResponse:
    incident = payload.incident
    if not incident.get("incident_id") or not incident.get("timeline"):
        raise HTTPException(status_code=422, detail="Incident incomplet : identifiant ou chronologie absent.")
    question = (
        "Rédige un résumé opérationnel de cet incident en français. Donne explicitement, "
        "dans cet ordre : 1) heure exacte de détection, 2) heure et nature de l'arrêt ou "
        "du confinement de l'attaque si elle apparaît dans la chronologie, 3) actions "
        "automatiques réalisées et leurs heures, 4) heure exacte où les services ont été "
        "rétablis, 5) preuve de reprise et durée totale. Utilise les dates ISO fournies, "
        "ne les invente pas et signale clairement toute information absente. Termine par "
        "une phrase rappelant qu'il s'agit de l'environnement de démonstration fictif."
    )
    try:
        answer = ask_model(question, incident_context(incident))
    except Exception as exc:
        logger.error("incident_summary_failed error=%s", exc)
        raise HTTPException(status_code=503, detail="Le modèle Ollama est indisponible.") from exc
    return QueryResponse(
        answer=answer,
        sources=[Source(path="incident-runtime", score=1)],
        model=OLLAMA_MODEL,
    )
