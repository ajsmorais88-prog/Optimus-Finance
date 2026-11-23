"""Gera public/ com as mesmas URLs, a partir dos fontes separados por linguagem."""

from pathlib import Path
import shutil
from project_paths import PROJECT_ROOT, FRONTEND_DIR


# BLOCO — Copia somente recursos públicos e preserva a associação do site com o APK.
def build_public():
    public = PROJECT_ROOT / "public"
    # Nunca copia o projeto Android, arquivos .env ou chaves privadas.
    for language in ("HTML", "CSS", "JavaScript", "JSON", "Assets"):
        source = FRONTEND_DIR / language
        for asset in source.rglob("*"):
            if not asset.is_file():
                continue
            relative = asset.relative_to(source)
            target = public / "static" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(asset, target)
    for name in (
        "index.html",
        "app.js",
        "apk-intro.js",
        "banks.js",
        "style.css",
        "mobile.css",
        "favicon.png",
        "manifest.webmanifest",
        "service-worker.js",
        "offline.html",
    ):
        shutil.copy2(public / "static" / name, public / name)
    shutil.copytree(
        FRONTEND_DIR / "JSON" / ".well-known", public / ".well-known", dirs_exist_ok=True
    )


if __name__ == "__main__":
    build_public()
