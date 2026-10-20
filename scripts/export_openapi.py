#!/usr/bin/env python3
"""
Exporte les spécifications OpenAPI des deux services Poupal dans docs/api/ :
    services/auth → docs/api/auth-openapi.json
    services/api  → docs/api/api-openapi.json

Usage, avec un interpréteur où les dépendances des services sont installées
(requirements.txt) :
    python scripts/export_openapi.py [--root <racine du dépôt>] [--out-dir <dossier>]

Chaque application est importée dans un SOUS-PROCESSUS séparé : les deux services
ont un paquet « app » du même nom et déclarent les mêmes métriques Prometheus, ce qui
interdit de les charger dans un seul interpréteur. L'environnement du sous-processus
contient des valeurs FACTICES (URL de base, chemins de clés) : rien n'est lu ni
contacté, FastAPI construit le schéma à partir des routes et des modèles Pydantic.
Code de retour : 0 si les deux exports réussissent, 1 sinon.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SERVICES = (("auth", "auth-openapi.json"), ("api", "api-openapi.json"))

# Valeurs factices : SQLAlchemy ne se connecte qu'à la première requête et les clés JWT
# ne sont lues qu'à la première utilisation ; importer app.main ne déclenche ni l'un ni l'autre.
FAKE_ENV = {
    "DATABASE_URL": "postgresql+psycopg://poupal:fake@localhost:5432/poupal",
    "JWT_PRIVATE_KEY_PATH": "/nonexistent/jwt_private.pem",
    "JWT_PUBLIC_KEY_PATH": "/nonexistent/jwt_public.pem",
    "SEED_DEMO_DATA": "false",
    "LOG_LEVEL": "WARNING",
    "PYTHONDONTWRITEBYTECODE": "1",  # pas de __pycache__ laissé dans les services
}

# Programme exécuté dans le sous-processus, depuis le dossier du service : importe
# l'application et écrit son schéma OpenAPI dans le fichier passé en argument.
# (Écriture dans un fichier plutôt que sur stdout : les logs JSON du service y passent.)
EXPORT_SNIPPET = r"""
import json, sys
from app.main import app
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(app.openapi(), handle, indent=2, ensure_ascii=False)
    handle.write("\n")
"""


def export_service(root: Path, service: str, output: Path, python: str) -> tuple[bool, str]:
    """Exporte le schéma d'un service ; renvoie (succès, détail à afficher)."""
    service_dir = root / "services" / service
    if not (service_dir / "app" / "main.py").is_file():
        return False, f"{service_dir / 'app' / 'main.py'} introuvable"

    env = {**os.environ, **FAKE_ENV}
    result = subprocess.run(
        [python, "-c", EXPORT_SNIPPET, str(output)],
        cwd=service_dir,  # « app » est importable depuis le dossier du service
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        # La cause (ImportError, ValidationError...) est toujours dans les dernières lignes
        tail = "\n".join(result.stderr.strip().splitlines()[-8:])
        return False, f"échec de l'import de app.main (code {result.returncode})\n{tail}"

    spec = json.loads(output.read_text(encoding="utf-8"))
    routes = len(spec.get("paths", {}))
    schemas = len(spec.get("components", {}).get("schemas", {}))
    return True, f"{routes} routes, {schemas} schémas"


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # consoles Windows en cp1252
    default_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Exporte les schémas OpenAPI des services auth et api.")
    parser.add_argument("--root", type=Path, default=default_root, help="racine du monorepo (défaut : dossier parent de scripts/)")
    parser.add_argument("--out-dir", type=Path, default=None, help="dossier de sortie (défaut : <root>/docs/api)")
    parser.add_argument("--python", default=sys.executable, help="interpréteur disposant des dépendances des services")
    args = parser.parse_args(argv)

    root: Path = args.root.resolve()
    out_dir: Path = (args.out_dir or root / "docs" / "api").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    exit_code = 0
    for service, filename in SERVICES:
        output = out_dir / filename
        ok, detail = export_service(root, service, output, args.python)
        shown = output.relative_to(root) if output.is_relative_to(root) else output
        if ok:
            print(f"OK  {service:<4} → {shown} ({detail})")
        else:
            print(f"KO  {service:<4} — {detail}")
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
