from __future__ import annotations

from pathlib import Path


_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_LEGACY_DIR = _PACKAGE_ROOT / "backend-server" / "src" / "config"
__path__ = [str(_LEGACY_DIR)]

_legacy_init = _LEGACY_DIR / "__init__.py"
if _legacy_init.exists():
    exec(compile(_legacy_init.read_text(encoding="utf-8"), str(_legacy_init), "exec"), globals())

