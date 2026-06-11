"""Build Dora-windows.zip for GitHub Releases (no venv, models, or tools)."""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_ZIP = ROOT / "Dora-windows.zip"

SKIP_DIR_NAMES = {
    ".git",
    ".release-stage",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "dora_assistant.egg-info",
    "models",
    "tools",
    "venv",
}

SKIP_FILE_NAMES = {
    "Dora-windows.zip",
}


def _skip_path(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in SKIP_DIR_NAMES for part in rel.parts):
        return True
    if path.is_file() and path.name in SKIP_FILE_NAMES:
        return True
    if path.suffix.lower() in {".pyc", ".pyo"}:
        return True
    return False


def main() -> int:
    if OUT_ZIP.exists():
        OUT_ZIP.unlink()
    file_count = 0
    with zipfile.ZipFile(OUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file() or _skip_path(path):
                continue
            archive.write(path, path.relative_to(ROOT).as_posix())
            file_count += 1
    if file_count == 0:
        raise SystemExit(f"No files packaged from {ROOT}")
    print(f"Created {OUT_ZIP} ({OUT_ZIP.stat().st_size} bytes, {file_count} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
