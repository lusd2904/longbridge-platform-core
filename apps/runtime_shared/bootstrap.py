from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REFACTOR_ROOT = Path(__file__).resolve().parents[2]
LEGACY_SRC = REFACTOR_ROOT / "backend-server" / "src"
REFACTOR_ENV = REFACTOR_ROOT / ".env"
REFACTOR_ENV_EXAMPLE = REFACTOR_ROOT / ".env.example"
LEGACY_COMPAT_ENV = "REF_ENABLE_LEGACY_COMPAT"

ENV_MAPPINGS = {
    "REF_DB_HOST": "DB_HOST",
    "REF_DB_PORT": "DB_PORT",
    "REF_DB_USER": "DB_USER",
    "REF_DB_PASSWORD": "DB_PASSWORD",
    "REF_DB_NAME": "DB_NAME",
    "REF_DB_CHARSET": "DB_CHARSET",
    "REF_DB_READ_ENABLED": "DB_READ_ENABLED",
    "REF_DB_READ_HOST": "DB_READ_HOST",
    "REF_DB_READ_PORT": "DB_READ_PORT",
    "REF_DB_READ_USER": "DB_READ_USER",
    "REF_DB_READ_PASSWORD": "DB_READ_PASSWORD",
    "REF_DB_READ_NAME": "DB_READ_NAME",
    "REF_DB_READ_CHARSET": "DB_READ_CHARSET",
    "REF_REDIS_HOST": "REDIS_HOST",
    "REF_REDIS_PORT": "REDIS_PORT",
    "REF_REDIS_PASSWORD": "REDIS_PASSWORD",
    "REF_REDIS_DB": "REDIS_DB",
    "REF_KAFKA_BROKER": "KAFKA_BROKERS",
    "REF_JWT_SECRET_KEY": "JWT_SECRET_KEY",
    "REF_OLLAMA_BASE_URL": "OLLAMA_BASE_URL",
    "REF_OLLAMA_MODEL": "OLLAMA_MODEL",
    "REF_LONGBRIDGE_AI_URL": "LONGBRIDGE_AI_URL",
    "REF_LONGBRIDGE_REGION": "LONGBRIDGE_REGION",
}


def _load_refactor_env() -> None:
    env_path = REFACTOR_ENV if REFACTOR_ENV.exists() else REFACTOR_ENV_EXAMPLE
    if env_path.exists():
        load_dotenv(env_path, override=False)

    for source_key, target_key in ENV_MAPPINGS.items():
        value = os.getenv(source_key)
        if value not in (None, ""):
            os.environ.setdefault(target_key, value)

    region = (
        os.getenv("LONGBRIDGE_REGION")
        or os.getenv("LONGPORT_REGION")
        or os.getenv("REF_LONGBRIDGE_REGION")
        or "cn"
    )
    os.environ.setdefault("LONGBRIDGE_REGION", region)
    os.environ.setdefault("LONGPORT_REGION", region)
    os.environ.setdefault("LONGPORT_PRINT_QUOTE_PACKAGES", "false")


def bootstrap_runtime() -> None:
    """Make refactor-v2 root importable and load runtime environment."""
    os.environ.setdefault("MONITOR_LINK_API_BASE", "disabled")
    _load_refactor_env()
    raw = str(REFACTOR_ROOT)
    if raw not in sys.path:
        sys.path.insert(0, raw)


def service_port(env_var: str, default: int) -> int:
    return int(os.getenv("SERVICE_PORT", os.getenv(env_var, str(default))))


def legacy_compat_enabled() -> bool:
    return str(os.getenv(LEGACY_COMPAT_ENV, "true")).strip().lower() in {"1", "true", "yes", "on"}


def runtime_profile() -> dict:
    return {
        "refactorRoot": str(REFACTOR_ROOT),
        "legacyCompatEnabled": legacy_compat_enabled(),
        "legacyCompatPath": str(LEGACY_SRC),
        "legacyCompatEnv": LEGACY_COMPAT_ENV,
        "legacyImportMode": "explicit-root-packages",
    }
