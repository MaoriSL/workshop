#!/usr/bin/env python3
"""
Générateur de trafic « normal » Poupal — environnement de démonstration, plateforme FICTIVE.

Simule jusqu'à 10 clients (comptes du seed, @poupal.demo) qui consultent leur solde, leur
historique, le détail d'une transaction et se font de petits virements, en passant par la
gateway exactement comme de vrais navigateurs. Ce trafic de fond sert à deux choses :
  - le modèle de détection apprend à quoi ressemble un comportement normal ;
  - pendant un incident, la reprise se VOIT : les virements s'arrêtent puis repartent.

Contraintes respectées (voir README.md) :
  - auth n'accepte que 5 connexions / min / IP et tous les clients simulés partagent l'IP
    du conteneur : budget global de 3 connexions / min, jetons réutilisés ~25 min ;
  - l'API n'accepte que 10 virements / min / utilisateur : plafond local de 6 ;
  - circuit fermé : les virements restent entre les utilisateurs simulés (soldes stables).

Bibliothèque standard uniquement. Jamais de mot de passe ni de jeton dans les logs.
"""
from __future__ import annotations

import http.client
import json
import logging
import math
import os
import random
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SERVICE_NAME = "traffic-gen"
# Fichier surveillé par le healthcheck compose (surchargeable pour un essai hors Docker)
HEARTBEAT_FILE = Path(os.environ.get("TRAFFIC_HEARTBEAT_FILE", "/tmp/traffic-gen.heartbeat"))
HEARTBEAT_EVERY_S = 5.0
STATS_EVERY_S = 60.0

# Les 10 clients fictifs du seed (services/auth/app/seed.py), activés dans cet ordre
DEMO_USERS = ["alex", "camille", "lea", "nathan", "julie", "hugo", "sophie", "lucas", "emma", "thomas"]
DEMO_DOMAIN = "poupal.demo"

# Budget de connexions partagé par TOUS les threads (auth : 5/min/IP, on garde une marge)
LOGIN_BUDGET_COUNT, LOGIN_BUDGET_WINDOW_S = 3, 60.0
# Un jeton dure 30 min côté auth ; on le renouvelle 5 min avant la fin (reconnexion sinon sur 401)
TOKEN_RENEW_MARGIN_S = 300.0
# L'API plafonne à 10 virements/min/utilisateur : on s'interdit d'en approcher
MAX_TRANSFERS_PER_MINUTE = 6
# Un « mauvais mot de passe » de temps en temps : toutes les 10 à 20 min (bruit réaliste)
BAD_PASSWORD_EVERY_S = (600.0, 1200.0)

# Répartition des actions d'un client (en %)
ACTION_WEIGHTS = {"balance": 40, "history": 35, "detail": 10, "transfer": 15}

# Libellés courts et crédibles pour les virements (tout est fictif)
MESSAGES = [
    "Remboursement restau", "Café d'hier", "Ma part du cadeau", "Courses de la semaine",
    "Billet de ciné", "Essence covoiturage", "Pizza de vendredi", "Merci pour le prêt",
    "Part du taxi", "Boulangerie", "Place de concert", "Apéro de samedi",
    "Cotisation foot", "Livre d'occasion", "Ticket de métro", "Petit-déj",
]


# ---------------------------------------------------------------- Configuration (variables d'environnement)
@dataclass(frozen=True)
class Config:
    enabled: bool
    base_url: str
    users: int
    intensity: float
    password: str
    log_level: str

    @classmethod
    def from_env(cls) -> "Config":
        enabled = os.environ.get("TRAFFIC_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
        base_url = os.environ.get("TRAFFIC_BASE_URL", "http://gateway:80").rstrip("/")
        users = _read_int("TRAFFIC_USERS", default=len(DEMO_USERS), low=1, high=len(DEMO_USERS))
        intensity = _read_float("TRAFFIC_INTENSITY", default=1.0, low=0.1, high=5.0)
        return cls(
            enabled=enabled,
            base_url=base_url,
            users=users,
            intensity=intensity,
            password=os.environ.get("TRAFFIC_PASSWORD", ""),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        )


def _read_int(name: str, default: int, low: int, high: int) -> int:
    try:
        return min(high, max(low, int(os.environ.get(name, default))))
    except ValueError:
        return default


def _read_float(name: str, default: float, low: float, high: float) -> float:
    try:
        return min(high, max(low, float(os.environ.get(name, default))))
    except ValueError:
        return default


# ---------------------------------------------------------------- Logs JSON (même forme que les services)
_FORBIDDEN_FIELDS = {"password", "token", "access_token", "authorization"}


class JsonFormatter(logging.Formatter):
    """Une ligne JSON par événement : timestamp, level, service, event + champs libres."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": SERVICE_NAME,
            "message": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            for key, value in fields.items():
                if key.lower() not in _FORBIDDEN_FIELDS:   # ceinture et bretelles
                    payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level if level in ("DEBUG", "INFO", "WARNING", "ERROR") else "INFO")


def log_event(event: str, level: int = logging.INFO, **fields: object) -> None:
    logging.getLogger("traffic").log(level, event, extra={"fields": {"event": event, **fields}})


# ---------------------------------------------------------------- Compteurs (stats toutes les 60 s)
class Counters:
    """Compteurs partagés entre threads : fenêtre courante (remise à zéro) et totaux."""

    KEYS = ("requests", "errors", "rate_limited", "logins", "login_failures", "transfers", "transfers_failed")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.window = dict.fromkeys(self.KEYS, 0)
        self.total = dict.fromkeys(self.KEYS, 0)

    def inc(self, key: str, amount: int = 1) -> None:
        with self._lock:
            self.window[key] += amount
            self.total[key] += amount

    def snapshot_and_reset(self) -> dict[str, int]:
        with self._lock:
            snapshot = dict(self.window)
            self.window = dict.fromkeys(self.KEYS, 0)
            return snapshot


# ---------------------------------------------------------------- Budget de connexions partagé
class LoginBudget:
    """Fenêtre glissante : au plus `count` connexions par `window` secondes, tous threads confondus.
    Un thread qui n'a pas de place attend (au lieu de prendre un 429 côté auth)."""

    def __init__(self, count: int, window: float) -> None:
        self.count, self.window = count, window
        self._hits: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self, stop: threading.Event) -> bool:
        """Bloque jusqu'à obtenir une place. Renvoie False si l'arrêt est demandé entre-temps."""
        while not stop.is_set():
            with self._lock:
                now = time.monotonic()
                while self._hits and now - self._hits[0] >= self.window:
                    self._hits.popleft()
                if len(self._hits) < self.count:
                    self._hits.append(now)
                    return True
                wait = self.window - (now - self._hits[0]) + random.uniform(0.5, 3.0)
            stop.wait(wait)
        return False


# ---------------------------------------------------------------- Profil de charge (calme / chargé)
class LoadProfile:
    """Facteur global qui évolue lentement entre 0,5 (calme) et 1,5 (chargé) :
    une sinusoïde dont la période est retirée au hasard (10 à 20 min) à chaque cycle."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cycle_start = time.monotonic()
        self._period = random.uniform(600.0, 1200.0)
        self._phase = random.uniform(0.0, 2.0 * math.pi)

    def factor(self) -> float:
        with self._lock:
            elapsed = time.monotonic() - self._cycle_start
            if elapsed >= self._period:
                # Nouveau cycle : la sinusoïde repart au même angle, donc sans saut
                self._cycle_start, elapsed = time.monotonic(), 0.0
                self._period = random.uniform(600.0, 1200.0)
            angle = self._phase + 2.0 * math.pi * elapsed / self._period
        return round(1.0 + 0.5 * math.sin(angle), 3)


# ---------------------------------------------------------------- Client HTTP (urllib)
class Unreachable(Exception):
    """La gateway ne répond pas (connexion refusée, délai dépassé...) : typique d'un incident."""


@dataclass(frozen=True)
class Reply:
    status: int
    body: dict
    retry_after: int
    latency_ms: int
    request_id: str


class PoupalClient:
    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self.base_url, self.timeout = base_url, timeout

    def call(self, method: str, path: str, body: dict | None = None, token: str | None = None,
             headers: dict[str, str] | None = None) -> Reply:
        """Requête JSON vers la gateway. Lève Unreachable si aucune réponse HTTP n'est obtenue."""
        request_id = f"traffic-{uuid.uuid4()}"   # corrélation avec les logs gateway / auth / api
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(f"{self.base_url}{path}", data=data, method=method)
        request.add_header("Accept", "application/json")
        request.add_header("User-Agent", "poupal-traffic-gen/0.1 (demo)")
        request.add_header("X-Request-ID", request_id)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        for key, value in (headers or {}).items():
            request.add_header(key, value)

        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status, raw, response_headers = response.status, response.read(), response.headers
        except urllib.error.HTTPError as error:
            status, raw, response_headers = error.code, error.read(), error.headers
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as error:
            raise Unreachable(str(getattr(error, "reason", error))) from error
        latency_ms = int((time.monotonic() - started) * 1000)

        try:
            decoded = json.loads(raw.decode() or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            decoded = {}   # page d'erreur nginx (HTML) par exemple
        try:
            retry_after = int(response_headers.get("Retry-After", "0") or 0)
        except ValueError:
            retry_after = 0
        return Reply(status, decoded if isinstance(decoded, dict) else {}, retry_after, latency_ms, request_id)


# ---------------------------------------------------------------- Un client simulé = un thread
class SimulatedUser(threading.Thread):
    def __init__(self, short_name: str, peers: list[str], config: Config, client: PoupalClient,
                 budget: LoginBudget, profile: LoadProfile, counters: Counters, stop: threading.Event) -> None:
        super().__init__(name=f"user-{short_name}", daemon=True)
        self.short = short_name
        self.email = f"{short_name}@{DEMO_DOMAIN}"
        self.peers = [peer for peer in peers if peer != short_name]   # destinataires possibles
        self.config, self.client, self.budget, self.profile, self.counters, self.stop = (
            config, client, budget, profile, counters, stop,
        )
        # État de session (jamais journalisé)
        self.token: str | None = None
        self.token_deadline = 0.0
        self.balance: int | None = None
        self.known_ids: list[str] = []          # transactions vues dans l'historique (pour « détail »)
        self.transfer_times: deque[float] = deque()
        self.failures = 0                        # erreurs consécutives → attente croissante

    # ---- boucle de vie
    def run(self) -> None:
        self.stop.wait(random.uniform(0.0, 10.0))   # départs décalés
        while not self.stop.is_set():
            try:
                delay = self._step()
            except Exception as error:  # un bug ne doit jamais tuer un utilisateur simulé en silence
                self.counters.inc("errors")
                log_event("user_error", logging.ERROR, user=self.short, kind="crash", detail=f"{type(error).__name__}: {error}"[:200])
                delay = 10.0
            self.stop.wait(delay if delay > 0 else self._pause_seconds())

    def _step(self) -> float:
        """Une itération : connexion si besoin, sinon une action. Renvoie un délai forcé (0 = pause normale)."""
        try:
            if self.token is None or time.monotonic() >= self.token_deadline:
                return self._login()
            return self._act()
        except Unreachable as error:
            return self._on_failure("unreachable", detail=str(error))

    def _pause_seconds(self) -> float:
        """Pause log-normale (médiane 8 s, queue longue), accélérée par l'intensité et le profil de charge."""
        base = random.lognormvariate(math.log(8.0), 0.7)
        speed = self.config.intensity * self.profile.factor()
        return min(90.0, max(1.0, base / speed))

    def _on_failure(self, kind: str, **fields: object) -> float:
        """Erreur d'infrastructure (5xx, injoignable) : on journalise et on attend un peu plus à chaque fois."""
        self.failures += 1
        self.counters.inc("errors")
        fields.pop("user", None)   # évite un doublon du mot-clé user (bug qui tuait le thread)
        log_event("user_error", logging.WARNING, user=self.short, kind=kind, consecutive=self.failures, **fields)
        return min(20.0, 2.0 ** self.failures) + random.uniform(0.0, 2.0)

    # ---- connexion
    def _login(self) -> float:
        if not self.budget.acquire(self.stop):
            return 1.0
        reply = self.client.call("POST", "/auth/login", {"email": self.email, "password": self.config.password})
        self.counters.inc("requests")
        self.counters.inc("logins")
        fields = dict(user=self.short, status=reply.status, latency_ms=reply.latency_ms, request_id=reply.request_id)

        if reply.status == 200 and "access_token" in reply.body:
            self.token = str(reply.body["access_token"])
            expires_in = float(reply.body.get("expires_in", 1800))
            self.token_deadline = time.monotonic() + max(60.0, expires_in - TOKEN_RENEW_MARGIN_S) - random.uniform(0, 60)
            self.failures = 0
            log_event("user_login", result="success", **fields)
            return 0.0
        if reply.status == 401:
            # Mot de passe de démo incorrect ou compte absent : on insiste peu (budget + alerte force brute)
            self.counters.inc("login_failures")
            log_event("user_error", logging.ERROR, kind="login_refused",
                      detail="identifiants de démo refusés : seed auth exécuté ? DEMO_PASSWORD identique ?", **fields)
            return 300.0 + random.uniform(0.0, 60.0)
        if reply.status == 429:
            self.counters.inc("rate_limited")
            log_event("user_error", logging.WARNING, kind="rate_limited", route="/auth/login", retry_after=reply.retry_after, **fields)
            return float(reply.retry_after) + random.uniform(1.0, 5.0)
        return self._on_failure("http_error", route="/auth/login", **fields)

    # ---- actions métier
    def _choose_action(self) -> str:
        weights = dict(ACTION_WEIGHTS)
        now = time.monotonic()
        while self.transfer_times and now - self.transfer_times[0] >= 60.0:
            self.transfer_times.popleft()
        # Pas de virement si : personne à qui envoyer, plafond local atteint, ou solde connu trop bas
        if not self.peers or len(self.transfer_times) >= MAX_TRANSFERS_PER_MINUTE or (self.balance is not None and self.balance < 1000):
            weights["balance"] += weights.pop("transfer")
        if not self.known_ids:
            weights["history"] += weights.pop("detail")   # un détail suppose un historique déjà vu
        return random.choices(list(weights), weights=list(weights.values()), k=1)[0]

    def _act(self) -> float:
        action = self._choose_action()
        if action == "balance":
            reply, route, extra = self._read_balance()
        elif action == "history":
            reply, route, extra = self._read_history()
        elif action == "detail":
            reply, route, extra = self._read_detail()
        else:
            reply, route, extra = self._send_money()
        self.counters.inc("requests")
        fields = dict(user=self.short, action=action, route=route, status=reply.status,
                      latency_ms=reply.latency_ms, request_id=reply.request_id, **extra)

        if reply.status == 401:
            # Jeton expiré ou rejeté : reconnexion au prochain tour (via le budget)
            self.token = None
            log_event("user_action", logging.WARNING, result="token_rejected", **fields)
            return 1.0
        if reply.status == 429:
            self.counters.inc("rate_limited")
            log_event("user_error", logging.WARNING, kind="rate_limited", retry_after=reply.retry_after, **fields)
            return float(reply.retry_after) + random.uniform(1.0, 5.0)
        if reply.status >= 500:
            return self._on_failure("http_error", **fields)
        if action == "transfer" and reply.status == 422 and reply.body.get("code") == "insufficient_funds":
            # Refus métier normal (l'API enregistre une transaction « failed ») : on relira le solde
            self.counters.inc("transfers_failed")
            self.balance = None
            log_event("user_action", result="insufficient_funds", **fields)
            return 0.0
        if reply.status not in (200, 201):
            self.counters.inc("errors")
            log_event("user_error", logging.WARNING, kind="rejected", code=reply.body.get("code"), **fields)
            return 0.0

        self.failures = 0
        log_event("user_action", result="ok", **fields)
        return 0.0

    def _read_balance(self) -> tuple[Reply, str, dict]:
        reply = self.client.call("GET", "/api/accounts/me", token=self.token)
        if reply.status == 200 and "balance_cents" in reply.body:
            self.balance = int(reply.body["balance_cents"])
            return reply, "/api/accounts/me", {"balance_cents": self.balance}
        return reply, "/api/accounts/me", {}

    def _read_history(self) -> tuple[Reply, str, dict]:
        limit = random.choice([5, 10, 20])
        offset = random.choice([0, 0, 0, limit])   # une fois sur quatre, la page suivante
        reply = self.client.call("GET", f"/api/transactions?limit={limit}&offset={offset}", token=self.token)
        if reply.status == 200:
            ids = [str(item.get("id")) for item in reply.body.get("items", []) if item.get("id")]
            if ids:
                self.known_ids = ids[:20]
            return reply, "/api/transactions", {"limit": limit, "offset": offset, "total": reply.body.get("total")}
        return reply, "/api/transactions", {"limit": limit, "offset": offset}

    def _read_detail(self) -> tuple[Reply, str, dict]:
        transaction_id = random.choice(self.known_ids)
        reply = self.client.call("GET", f"/api/transactions/{transaction_id}", token=self.token)
        return reply, "/api/transactions/{id}", {"transaction_id": transaction_id}

    def _send_money(self) -> tuple[Reply, str, dict]:
        recipient = random.choice(self.peers)
        amount = random.randint(100, 999)   # 1,00 € à 9,99 €
        body = {"recipient_email": f"{recipient}@{DEMO_DOMAIN}", "amount_cents": amount, "message": random.choice(MESSAGES)}
        # Une clé par tentative : un rejeu (même clé, même corps) ne créerait pas de second virement
        reply = self.client.call("POST", "/api/transactions", body, token=self.token, headers={"Idempotency-Key": str(uuid.uuid4())})
        extra: dict = {"recipient": recipient, "amount_cents": amount}
        if reply.status in (200, 201):
            self.transfer_times.append(time.monotonic())
            self.counters.inc("transfers")
            if self.balance is not None:
                self.balance -= amount
            extra["reference"] = reply.body.get("reference")
            extra["transaction_status"] = reply.body.get("status")
        return reply, "/api/transactions", extra


# ---------------------------------------------------------------- « Mauvais mot de passe » occasionnel
class BadPasswordProber(threading.Thread):
    """Toutes les 10 à 20 min, une tentative avec un mot de passe faux (erreur de frappe simulée).
    Compte dans le même budget de connexions ; le mot de passe essayé n'a rien à voir avec le vrai."""

    def __init__(self, users: list[str], client: PoupalClient, budget: LoginBudget, counters: Counters, stop: threading.Event) -> None:
        super().__init__(name="bad-password", daemon=True)
        self.users, self.client, self.budget, self.counters, self.stop = users, client, budget, counters, stop

    def run(self) -> None:
        while not self.stop.wait(random.uniform(*BAD_PASSWORD_EVERY_S)):
            if not self.budget.acquire(self.stop):
                return
            user = random.choice(self.users)
            wrong_password = f"faute-de-frappe-{random.randint(1000, 9999)}"
            try:
                reply = self.client.call("POST", "/auth/login", {"email": f"{user}@{DEMO_DOMAIN}", "password": wrong_password})
            except Unreachable as error:
                self.counters.inc("errors")
                log_event("user_error", logging.WARNING, user=user, kind="unreachable", detail=str(error))
                continue
            self.counters.inc("requests")
            self.counters.inc("login_failures")
            log_event("user_login", user=user, result="bad_password", deliberate=True, status=reply.status,
                      expected_status=401, latency_ms=reply.latency_ms, request_id=reply.request_id)


class BruteForceAttacker(threading.Thread):
    """Mode TRAFFIC_MODE=bruteforce (scénario d'évaluation du détecteur, jamais en usage normal) :
    enchaîne les mauvais mots de passe sans respecter le budget de connexions. Le service auth
    répond 401 puis 429 (limitation de débit) : c'est exactement la rafale d'échecs que le
    modèle doit apprendre à reconnaître."""

    def __init__(self, users: list[str], client: PoupalClient, intensity: float, counters: Counters, stop: threading.Event) -> None:
        super().__init__(name="bruteforce", daemon=True)
        self.users, self.client, self.intensity, self.counters, self.stop = users, client, intensity, counters, stop

    def run(self) -> None:
        while not self.stop.is_set():
            user = random.choice(self.users)
            try:
                reply = self.client.call("POST", "/auth/login", {"email": f"{user}@{DEMO_DOMAIN}", "password": f"attaque-{random.randint(0, 99999)}"})
                self.counters.inc("requests")
                self.counters.inc("login_failures")
                log_event("user_login", user=user, result="bruteforce_attempt", deliberate=True, status=reply.status, latency_ms=reply.latency_ms)
            except Unreachable as error:
                self.counters.inc("errors")
                log_event("user_error", logging.WARNING, user=user, kind="unreachable", detail=str(error))
            self.stop.wait(random.uniform(0.2, 0.6) / max(self.intensity, 0.1))


# ---------------------------------------------------------------- Boucle principale
def heartbeat() -> None:
    """Touche le fichier surveillé par le healthcheck (aussi en veille)."""
    try:
        HEARTBEAT_FILE.touch()
    except OSError as error:
        log_event("heartbeat_failed", logging.WARNING, detail=str(error))


def idle(stop: threading.Event, reason: str) -> int:
    """Veille : pas de trafic, mais heartbeat régulier et rappel dans les logs toutes les 10 min."""
    last_notice = -math.inf
    while not stop.is_set():
        if time.monotonic() - last_notice >= 600.0:
            log_event("traffic_paused", reason=reason)
            last_notice = time.monotonic()
        heartbeat()
        stop.wait(HEARTBEAT_EVERY_S)
    log_event("traffic_stopped", reason="signal")
    return 0


def main() -> int:
    config = Config.from_env()
    configure_logging(config.log_level)
    stop = threading.Event()

    def on_signal(signum: int, _frame: object) -> None:
        log_event("traffic_stopping", signal=signal.Signals(signum).name)
        stop.set()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    heartbeat()

    if not config.enabled:
        return idle(stop, reason="TRAFFIC_ENABLED=false")
    if not config.password:
        log_event("traffic_misconfigured", logging.ERROR, detail="TRAFFIC_PASSWORD vide : renseignez DEMO_PASSWORD dans infra/.env")
        return idle(stop, reason="TRAFFIC_PASSWORD manquant")

    users = DEMO_USERS[: config.users]
    client = PoupalClient(config.base_url)
    budget = LoginBudget(LOGIN_BUDGET_COUNT, LOGIN_BUDGET_WINDOW_S)
    profile = LoadProfile()
    counters = Counters()
    mode = os.environ.get("TRAFFIC_MODE", "normal").strip().lower()
    if mode == "bruteforce":
        # Scénario d'évaluation : uniquement la rafale d'échecs, pas de trafic normal
        threads: list[threading.Thread] = [BruteForceAttacker(users, client, config.intensity, counters, stop)]
    else:
        threads = [SimulatedUser(name, users, config, client, budget, profile, counters, stop) for name in users]
        threads.append(BadPasswordProber(users, client, budget, counters, stop))
    for thread in threads:
        thread.start()
    log_event("traffic_started", users=users, base_url=config.base_url, intensity=config.intensity, mode=mode,
              login_budget=f"{LOGIN_BUDGET_COUNT}/{int(LOGIN_BUDGET_WINDOW_S)}s", max_transfers_per_minute=MAX_TRANSFERS_PER_MINUTE)

    last_stats = time.monotonic()
    while not stop.is_set():
        heartbeat()
        if time.monotonic() - last_stats >= STATS_EVERY_S:
            last_stats = time.monotonic()
            window = counters.snapshot_and_reset()
            logged_in = sum(1 for thread in threads if isinstance(thread, SimulatedUser) and thread.token)
            log_event("traffic_stats", window_s=int(STATS_EVERY_S), **window, logged_in=logged_in,
                      users=len(users), load_factor=profile.factor(), intensity=config.intensity,
                      total_requests=counters.total["requests"], total_transfers=counters.total["transfers"])
        stop.wait(HEARTBEAT_EVERY_S)

    # Arrêt propre (SIGTERM de docker stop) : les threads finissent leur pause, puis on résume
    for thread in threads:
        thread.join(timeout=10.0)
    log_event("traffic_stopped", reason="signal", **{f"total_{key}": value for key, value in counters.total.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
