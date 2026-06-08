from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
import re
import secrets
import subprocess
from typing import Dict

from dotenv import dotenv_values


ROOT_DIR = Path(__file__).resolve().parents[1]
EXAMPLE_ENV = ROOT_DIR / ".env.example"
TARGET_ENV = ROOT_DIR / ".env"

REF_PORT_DEFAULTS = OrderedDict(
    [
        ("REF_WEB_PORTAL_PORT", "3100"),
        ("REF_GATEWAY_PORT", "5101"),
        ("REF_USER_CENTER_PORT", "8101"),
        ("REF_MARKET_SERVICE_PORT", "8102"),
        ("REF_ANALYSIS_SERVICE_PORT", "8103"),
        ("REF_STRATEGY_SERVICE_PORT", "8104"),
        ("REF_TRADE_SERVICE_PORT", "8105"),
        ("REF_SENTIMENT_SERVICE_PORT", "8106"),
        ("REF_SCHEDULER_SERVICE_PORT", "8107"),
        ("REF_RISK_SERVICE_PORT", "8108"),
    ]
)

PASSTHROUGH_KEYS = [
    "APP_ENV",
    "APP_DEBUG",
    "APP_HOST",
    "APP_PORT",
    "DB_CHARSET",
    "REDIS_PASSWORD",
    "REDIS_DB",
    "LONGBRIDGE_REGION",
    "LONGPORT_REGION",
    "JWT_EXPIRE_HOURS",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "OLLAMA_TIMEOUT",
    "OLLAMA_NUM_THREAD",
    "OLLAMA_TEMPERATURE",
    "SKSHARE_BASE_URL",
    "SKSHARE_TIMEOUT",
    "LONGBRIDGE_AI_PROVIDER",
    "LONGBRIDGE_AI_FALLBACK_PROVIDER",
    "LONGBRIDGE_AI_BASE_URL",
    "LONGBRIDGE_AI_URL",
    "LONGBRIDGE_AI_API_STYLE",
    "LONGBRIDGE_AI_API_KEY",
    "LONGBRIDGE_AI_MODEL",
    "LONGBRIDGE_AI_MODEL_SCAN_PULSE",
    "LONGBRIDGE_AI_MODEL_SCAN_FAST",
    "LONGBRIDGE_AI_MODEL_SCAN_RISK",
    "LONGBRIDGE_AI_MODEL_SCAN_FINAL",
    "LONGBRIDGE_AI_MODEL_TREND_BATCH",
    "LONGBRIDGE_AI_MODEL_RECOMMEND_BRIEF",
    "LONGBRIDGE_AI_MODEL_RECOMMEND_SUMMARY",
    "LONGBRIDGE_AI_MODEL_VISION",
    "LOG_LEVEL",
    "LOG_FILE",
    "INFLUXDB_URL",
    "INFLUXDB_TOKEN",
    "INFLUXDB_ORG",
    "INFLUXDB_BUCKET",
    "KAFKA_MARKET_TOPIC",
    "KAFKA_TRADE_COMMAND_TOPIC",
    "KAFKA_TRADE_EVENT_TOPIC",
    "KAFKA_CONSUMER_GROUP",
    "WEBSOCKET_ENABLED",
    "WEBSOCKET_QUOTE_INTERVAL",
]


def _read_env(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    raw = dotenv_values(path)
    return {key: str(value) for key, value in raw.items() if value is not None}


def _coalesce(*values: str | None, default: str = "") -> str:
    for value in values:
        if value not in (None, ""):
            return str(value)
    return default


def _render_env(payload: "OrderedDict[str, str]") -> str:
    lines = [
        "# Refactor V2 runtime environment",
        "# This file is auto-generated and safe to edit for local overrides.",
        "",
        "# Refactor-specific ports",
    ]
    for key in REF_PORT_DEFAULTS:
        lines.append(f"{key}={payload[key]}")

    lines.extend(
        [
            "",
            "# Refactor database bootstrap",
            f"REF_SOURCE_DB_NAME={payload['REF_SOURCE_DB_NAME']}",
            f"REF_DB_HOST={payload['REF_DB_HOST']}",
            f"REF_DB_PORT={payload['REF_DB_PORT']}",
            f"REF_DB_USER={payload['REF_DB_USER']}",
            f"REF_DB_PASSWORD={payload['REF_DB_PASSWORD']}",
            f"REF_DB_NAME={payload['REF_DB_NAME']}",
            f"REF_DB_CHARSET={payload['REF_DB_CHARSET']}",
            f"REF_DB_READ_ENABLED={payload['REF_DB_READ_ENABLED']}",
            f"REF_DB_READ_HOST={payload['REF_DB_READ_HOST']}",
            f"REF_DB_READ_PORT={payload['REF_DB_READ_PORT']}",
            f"REF_DB_READ_USER={payload['REF_DB_READ_USER']}",
            f"REF_DB_READ_PASSWORD={payload['REF_DB_READ_PASSWORD']}",
            f"REF_DB_READ_NAME={payload['REF_DB_READ_NAME']}",
            f"REF_DB_READ_CHARSET={payload['REF_DB_READ_CHARSET']}",
            "",
            "# Refactor infrastructure mirrors",
            f"REF_REDIS_HOST={payload['REF_REDIS_HOST']}",
            f"REF_REDIS_PORT={payload['REF_REDIS_PORT']}",
            f"REF_REDIS_PASSWORD={payload['REF_REDIS_PASSWORD']}",
            f"REF_REDIS_DB={payload['REF_REDIS_DB']}",
            f"REF_KAFKA_ENABLED={payload['REF_KAFKA_ENABLED']}",
            f"REF_KAFKA_BROKER={payload['REF_KAFKA_BROKER']}",
            f"REF_JWT_SECRET_KEY={payload['REF_JWT_SECRET_KEY']}",
            f"REF_OLLAMA_BASE_URL={payload['REF_OLLAMA_BASE_URL']}",
            f"REF_OLLAMA_MODEL={payload['REF_OLLAMA_MODEL']}",
            f"REF_LONGBRIDGE_AI_URL={payload['REF_LONGBRIDGE_AI_URL']}",
            f"REF_LONGBRIDGE_REGION={payload['REF_LONGBRIDGE_REGION']}",
            f"REF_SKSHARE_BASE_URL={payload['REF_SKSHARE_BASE_URL']}",
            f"REF_SKSHARE_TIMEOUT={payload['REF_SKSHARE_TIMEOUT']}",
            "",
            "# Legacy-compatible keys used by copied modules inside refactor-v2",
            f"DB_HOST={payload['DB_HOST']}",
            f"DB_PORT={payload['DB_PORT']}",
            f"DB_USER={payload['DB_USER']}",
            f"DB_PASSWORD={payload['DB_PASSWORD']}",
            f"DB_NAME={payload['DB_NAME']}",
            f"DB_CHARSET={payload['DB_CHARSET']}",
            f"DB_READ_ENABLED={payload['DB_READ_ENABLED']}",
            f"DB_READ_HOST={payload['DB_READ_HOST']}",
            f"DB_READ_PORT={payload['DB_READ_PORT']}",
            f"DB_READ_USER={payload['DB_READ_USER']}",
            f"DB_READ_PASSWORD={payload['DB_READ_PASSWORD']}",
            f"DB_READ_NAME={payload['DB_READ_NAME']}",
            f"DB_READ_CHARSET={payload['DB_READ_CHARSET']}",
            f"REDIS_HOST={payload['REDIS_HOST']}",
            f"REDIS_PORT={payload['REDIS_PORT']}",
            f"REDIS_PASSWORD={payload['REDIS_PASSWORD']}",
            f"REDIS_DB={payload['REDIS_DB']}",
            f"JWT_SECRET_KEY={payload['JWT_SECRET_KEY']}",
            f"KAFKA_BROKERS={payload['KAFKA_BROKERS']}",
            f"TRADE_SERVICE_ENABLED={payload['TRADE_SERVICE_ENABLED']}",
            f"TRADE_SERVICE_URL={payload['TRADE_SERVICE_URL']}",
            f"MONITOR_LINK_API_BASE={payload['MONITOR_LINK_API_BASE']}",
        ]
    )

    passthrough_rendered = [
        f"{key}={payload[key]}"
        for key in PASSTHROUGH_KEYS
        if key in payload and payload[key] not in (None, "")
    ]
    if passthrough_rendered:
        lines.extend(["", "# Additional local passthrough settings", *passthrough_rendered])

    lines.extend(["", "# Sentiment reservation", f"REF_SENTIMENT_ENABLED={payload['REF_SENTIMENT_ENABLED']}", ""])
    return "\n".join(lines)


def ensure_longbridge_cli_auth_alias(home_dir: Path | None = None) -> Path | None:
    longbridge_home = (home_dir or Path.home()) / ".longbridge" / "openapi"
    alias_path = longbridge_home / "cli-auth"
    tokens_dir = longbridge_home / "tokens"

    if alias_path.exists():
        return alias_path
    if alias_path.is_symlink():
        alias_path.unlink()
    if not tokens_dir.exists():
        return None

    token_files = [path for path in tokens_dir.iterdir() if path.is_file()]
    if not token_files:
        return None

    latest_token = max(token_files, key=lambda path: path.stat().st_mtime)
    alias_path.symlink_to(Path("tokens") / latest_token.name)
    return alias_path


def _detect_longbridge_cli_version() -> str:
    try:
        completed = subprocess.run(
            ["longbridge", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return ""

    match = re.search(r"(\d+\.\d+\.\d+)", f"{completed.stdout}\n{completed.stderr}")
    return match.group(1) if match else ""


def ensure_longbridge_cli_runtime_files(
    home_dir: Path | None = None,
    *,
    cli_version: str | None = None,
) -> Path | None:
    alias_path = ensure_longbridge_cli_auth_alias(home_dir)
    version = (cli_version or _detect_longbridge_cli_version()).strip()
    if not version:
        return alias_path

    longbridge_home = (home_dir or Path.home()) / ".longbridge"
    if not longbridge_home.exists():
        return alias_path
    for filename in (".terminal-last-run-version", ".terminal-latest-version"):
        version_path = longbridge_home / filename
        if not version_path.exists() or version_path.read_text(encoding="utf-8").strip() != version:
            version_path.write_text(version, encoding="utf-8")
    return alias_path


def ensure_refactor_env() -> Dict[str, str]:
    example = _read_env(EXAMPLE_ENV)
    current = _read_env(TARGET_ENV)

    payload: "OrderedDict[str, str]" = OrderedDict()
    for key, default in REF_PORT_DEFAULTS.items():
        payload[key] = _coalesce(current.get(key), example.get(key), default=default)

    source_db_name = _coalesce(current.get("REF_SOURCE_DB_NAME"), example.get("REF_SOURCE_DB_NAME"), default="quant_trade")
    target_db_name = _coalesce(current.get("REF_DB_NAME"), example.get("REF_DB_NAME"), default=f"{source_db_name}_refactor")
    db_host = _coalesce(current.get("REF_DB_HOST"), example.get("REF_DB_HOST"), default="127.0.0.1")
    db_port = _coalesce(current.get("REF_DB_PORT"), example.get("REF_DB_PORT"), default="3306")
    db_user = _coalesce(current.get("REF_DB_USER"), example.get("REF_DB_USER"), default="root")
    db_password = _coalesce(current.get("REF_DB_PASSWORD"), example.get("REF_DB_PASSWORD"), default="")
    db_charset = _coalesce(current.get("REF_DB_CHARSET"), example.get("REF_DB_CHARSET"), default="utf8mb4")
    db_read_enabled = _coalesce(current.get("REF_DB_READ_ENABLED"), example.get("REF_DB_READ_ENABLED"), default="false").lower()
    if db_read_enabled not in {"true", "false"}:
        db_read_enabled = "false"
    db_read_host = _coalesce(current.get("REF_DB_READ_HOST"), example.get("REF_DB_READ_HOST"), db_host, default=db_host)
    db_read_port = _coalesce(current.get("REF_DB_READ_PORT"), example.get("REF_DB_READ_PORT"), db_port, default=db_port)
    db_read_user = _coalesce(current.get("REF_DB_READ_USER"), example.get("REF_DB_READ_USER"), db_user, default=db_user)
    db_read_password = _coalesce(current.get("REF_DB_READ_PASSWORD"), example.get("REF_DB_READ_PASSWORD"), db_password, default=db_password)
    db_read_name = _coalesce(current.get("REF_DB_READ_NAME"), example.get("REF_DB_READ_NAME"), target_db_name, default=target_db_name)
    db_read_charset = _coalesce(current.get("REF_DB_READ_CHARSET"), example.get("REF_DB_READ_CHARSET"), db_charset, default=db_charset)

    redis_host = _coalesce(current.get("REF_REDIS_HOST"), example.get("REF_REDIS_HOST"), default="127.0.0.1")
    redis_port = _coalesce(current.get("REF_REDIS_PORT"), example.get("REF_REDIS_PORT"), default="6379")
    redis_password = _coalesce(current.get("REF_REDIS_PASSWORD"), example.get("REF_REDIS_PASSWORD"), default="")
    redis_db = _coalesce(current.get("REF_REDIS_DB"), example.get("REF_REDIS_DB"), default="0")
    kafka_broker = _coalesce(current.get("REF_KAFKA_BROKER"), example.get("REF_KAFKA_BROKER"), default="127.0.0.1:9092")
    jwt_secret = _coalesce(current.get("REF_JWT_SECRET_KEY"), default="your-secret-key-here")
    if len(jwt_secret) < 32:
        jwt_secret = secrets.token_urlsafe(48)
    ollama_base = _coalesce(current.get("REF_OLLAMA_BASE_URL"), example.get("REF_OLLAMA_BASE_URL"), default="http://127.0.0.1:11434")
    ollama_model = _coalesce(current.get("REF_OLLAMA_MODEL"), example.get("REF_OLLAMA_MODEL"), default="gemma3:12b")
    ai_url = _coalesce(
        current.get("REF_LONGBRIDGE_AI_URL"),
        example.get("REF_LONGBRIDGE_AI_URL"),
        default="https://lucen.cc/v1/chat/completions",
    )
    if "localhost:5005" in ai_url.lower():
        ai_url = "https://lucen.cc/v1/chat/completions"
    skshare_base = _coalesce(
        current.get("REF_SKSHARE_BASE_URL"),
        current.get("SKSHARE_BASE_URL"),
        example.get("REF_SKSHARE_BASE_URL"),
        example.get("SKSHARE_BASE_URL"),
        default="http://host.docker.internal:18081",
    )
    skshare_timeout = _coalesce(
        current.get("REF_SKSHARE_TIMEOUT"),
        current.get("SKSHARE_TIMEOUT"),
        example.get("REF_SKSHARE_TIMEOUT"),
        example.get("SKSHARE_TIMEOUT"),
        default="30",
    )
    kafka_enabled = _coalesce(current.get("REF_KAFKA_ENABLED"), default="false").lower()
    if kafka_enabled not in {"true", "false"}:
        kafka_enabled = "false"

    payload.update(
        {
            "REF_SOURCE_DB_NAME": source_db_name,
            "REF_DB_HOST": db_host,
            "REF_DB_PORT": db_port,
            "REF_DB_USER": db_user,
            "REF_DB_PASSWORD": db_password,
            "REF_DB_NAME": target_db_name,
            "REF_DB_CHARSET": db_charset,
            "REF_DB_READ_ENABLED": db_read_enabled,
            "REF_DB_READ_HOST": db_read_host,
            "REF_DB_READ_PORT": db_read_port,
            "REF_DB_READ_USER": db_read_user,
            "REF_DB_READ_PASSWORD": db_read_password,
            "REF_DB_READ_NAME": db_read_name,
            "REF_DB_READ_CHARSET": db_read_charset,
            "REF_REDIS_HOST": redis_host,
            "REF_REDIS_PORT": redis_port,
            "REF_REDIS_PASSWORD": redis_password,
            "REF_REDIS_DB": redis_db,
            "REF_KAFKA_ENABLED": kafka_enabled,
            "REF_KAFKA_BROKER": kafka_broker,
            "REF_JWT_SECRET_KEY": jwt_secret,
            "REF_OLLAMA_BASE_URL": ollama_base,
            "REF_OLLAMA_MODEL": ollama_model,
            "REF_LONGBRIDGE_AI_URL": ai_url,
            "REF_SKSHARE_BASE_URL": skshare_base,
            "REF_SKSHARE_TIMEOUT": skshare_timeout,
            "REF_LONGBRIDGE_REGION": _coalesce(
                current.get("REF_LONGBRIDGE_REGION"),
                current.get("LONGBRIDGE_REGION"),
                current.get("LONGPORT_REGION"),
                example.get("REF_LONGBRIDGE_REGION"),
                default="cn",
            ).strip().lower()
            or "cn",
            "DB_HOST": db_host,
            "DB_PORT": db_port,
            "DB_USER": db_user,
            "DB_PASSWORD": db_password,
            "DB_NAME": target_db_name,
            "DB_CHARSET": db_charset,
            "DB_READ_ENABLED": db_read_enabled,
            "DB_READ_HOST": db_read_host,
            "DB_READ_PORT": db_read_port,
            "DB_READ_USER": db_read_user,
            "DB_READ_PASSWORD": db_read_password,
            "DB_READ_NAME": db_read_name,
            "DB_READ_CHARSET": db_read_charset,
            "REDIS_HOST": redis_host,
            "REDIS_PORT": redis_port,
            "REDIS_PASSWORD": redis_password,
            "REDIS_DB": redis_db,
            "JWT_SECRET_KEY": jwt_secret,
            "KAFKA_BROKERS": kafka_broker,
            "LONGBRIDGE_REGION": _coalesce(
                current.get("LONGBRIDGE_REGION"),
                current.get("LONGPORT_REGION"),
                current.get("REF_LONGBRIDGE_REGION"),
                example.get("REF_LONGBRIDGE_REGION"),
                default="cn",
            ).strip().lower()
            or "cn",
            "LONGPORT_REGION": _coalesce(
                current.get("LONGPORT_REGION"),
                current.get("LONGBRIDGE_REGION"),
                current.get("REF_LONGBRIDGE_REGION"),
                example.get("REF_LONGBRIDGE_REGION"),
                default="cn",
            ).strip().lower()
            or "cn",
            "TRADE_SERVICE_ENABLED": "true",
            "TRADE_SERVICE_URL": f"http://127.0.0.1:{payload['REF_TRADE_SERVICE_PORT']}",
            "MONITOR_LINK_API_BASE": "disabled",
            "KAFKA_ENABLED": kafka_enabled,
            "SKSHARE_BASE_URL": skshare_base,
            "SKSHARE_TIMEOUT": skshare_timeout,
            "LONGBRIDGE_AI_PROVIDER": _coalesce(current.get("LONGBRIDGE_AI_PROVIDER"), example.get("LONGBRIDGE_AI_PROVIDER"), default="nvidia"),
            "LONGBRIDGE_AI_FALLBACK_PROVIDER": _coalesce(current.get("LONGBRIDGE_AI_FALLBACK_PROVIDER"), example.get("LONGBRIDGE_AI_FALLBACK_PROVIDER"), default=""),
            "LONGBRIDGE_AI_BASE_URL": _coalesce(current.get("LONGBRIDGE_AI_BASE_URL"), example.get("LONGBRIDGE_AI_BASE_URL"), default="https://lucen.cc/v1"),
            "LONGBRIDGE_AI_URL": _coalesce(current.get("LONGBRIDGE_AI_URL"), example.get("LONGBRIDGE_AI_URL"), ai_url, default=ai_url),
            "LONGBRIDGE_AI_API_STYLE": _coalesce(current.get("LONGBRIDGE_AI_API_STYLE"), example.get("LONGBRIDGE_AI_API_STYLE"), default="openai-chat-completions"),
            "LONGBRIDGE_AI_API_KEY": _coalesce(current.get("LONGBRIDGE_AI_API_KEY"), example.get("LONGBRIDGE_AI_API_KEY"), default=""),
            "LONGBRIDGE_AI_MODEL": _coalesce(current.get("LONGBRIDGE_AI_MODEL"), example.get("LONGBRIDGE_AI_MODEL"), default="gpt-5.5"),
            "LONGBRIDGE_AI_MODEL_SCAN_PULSE": _coalesce(current.get("LONGBRIDGE_AI_MODEL_SCAN_PULSE"), example.get("LONGBRIDGE_AI_MODEL_SCAN_PULSE"), default="gpt-5.4"),
            "LONGBRIDGE_AI_MODEL_SCAN_FAST": _coalesce(current.get("LONGBRIDGE_AI_MODEL_SCAN_FAST"), example.get("LONGBRIDGE_AI_MODEL_SCAN_FAST"), default="gpt-5.4"),
            "LONGBRIDGE_AI_MODEL_SCAN_RISK": _coalesce(current.get("LONGBRIDGE_AI_MODEL_SCAN_RISK"), example.get("LONGBRIDGE_AI_MODEL_SCAN_RISK"), default="gpt-5.4"),
            "LONGBRIDGE_AI_MODEL_SCAN_FINAL": _coalesce(current.get("LONGBRIDGE_AI_MODEL_SCAN_FINAL"), example.get("LONGBRIDGE_AI_MODEL_SCAN_FINAL"), default="gpt-5.5"),
            "LONGBRIDGE_AI_MODEL_TREND_BATCH": _coalesce(current.get("LONGBRIDGE_AI_MODEL_TREND_BATCH"), example.get("LONGBRIDGE_AI_MODEL_TREND_BATCH"), default="gpt-5.4"),
            "LONGBRIDGE_AI_MODEL_RECOMMEND_BRIEF": _coalesce(current.get("LONGBRIDGE_AI_MODEL_RECOMMEND_BRIEF"), example.get("LONGBRIDGE_AI_MODEL_RECOMMEND_BRIEF"), default="gpt-5.4"),
            "LONGBRIDGE_AI_MODEL_RECOMMEND_SUMMARY": _coalesce(current.get("LONGBRIDGE_AI_MODEL_RECOMMEND_SUMMARY"), example.get("LONGBRIDGE_AI_MODEL_RECOMMEND_SUMMARY"), default="gpt-5.5"),
            "LONGBRIDGE_AI_MODEL_VISION": _coalesce(current.get("LONGBRIDGE_AI_MODEL_VISION"), example.get("LONGBRIDGE_AI_MODEL_VISION"), default="gpt-5.4"),
            "LONGBRIDGE_AI_REASONING_EFFORT": _coalesce(current.get("LONGBRIDGE_AI_REASONING_EFFORT"), example.get("LONGBRIDGE_AI_REASONING_EFFORT"), default="medium"),
            "LONGBRIDGE_AI_SCAN_REASONING_EFFORT": _coalesce(current.get("LONGBRIDGE_AI_SCAN_REASONING_EFFORT"), example.get("LONGBRIDGE_AI_SCAN_REASONING_EFFORT"), default="high"),
            "REF_SENTIMENT_ENABLED": _coalesce(current.get("REF_SENTIMENT_ENABLED"), example.get("REF_SENTIMENT_ENABLED"), default="false"),
        }
    )

    for key in PASSTHROUGH_KEYS:
        value = _coalesce(current.get(key), default="")
        if value:
            payload[key] = value

    ensure_longbridge_cli_runtime_files()
    TARGET_ENV.write_text(_render_env(payload), encoding="utf-8")
    return dict(payload)


if __name__ == "__main__":
    env = ensure_refactor_env()
    print(f"已写入 {TARGET_ENV}")
    print(f"目标数据库: {env['REF_DB_NAME']}")
    print(f"源数据库: {env['REF_SOURCE_DB_NAME']}")
