"""Caminhos do projeto independentes da pasta usada para iniciar o servidor."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = PROJECT_ROOT / "Backend" / "SQL"
FRONTEND_DIR = PROJECT_ROOT / "Frontend"


# As URLs públicas continuam iguais; apenas a organização dos fontes mudou.
def frontend_directory(filename):
    extension = Path(filename).suffix.lower()
    language = {
        ".html": "HTML",
        ".css": "CSS",
        ".js": "JavaScript",
        ".json": "JSON",
        ".webmanifest": "JSON",
    }.get(extension, "Assets")
    return FRONTEND_DIR / language
