from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "antigravity_cli_adapter.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("antigravity_cli_adapter_test_module", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resolve_cli_prefers_explicit_env_bin() -> None:
    module = _load_module()

    def fake_which(name: str):
        return "/custom/bin/antigravity" if name == "antigravity" else None

    resolved = module.resolve_cli(
        env={module.ENV_BIN: "antigravity"},
        which=fake_which,
    )

    assert resolved.command == "antigravity"
    assert resolved.path == "/custom/bin/antigravity"


def test_build_command_uses_verified_defaults_for_print_mode() -> None:
    module = _load_module()

    def fake_which(name: str):
        return "/usr/local/bin/agy" if name == "agy" else None

    command = module.build_command(
        mode="print",
        prompt="hello",
        passthrough_args=["--print-timeout", "60s"],
        env={},
        which=fake_which,
    )

    assert command == ["/usr/local/bin/agy", "--print", "hello", "--print-timeout", "60s"]


def test_translate_gemini_args_rejects_model_without_explicit_mapping() -> None:
    module = _load_module()

    def fake_which(name: str):
        return "/usr/local/bin/agy" if name == "agy" else None

    with pytest.raises(module.AdapterConfigError) as exc_info:
        module.translate_gemini_args(
            ["-m", "gemini-2.5-pro", "-p", "hello"],
            env={},
            which=fake_which,
        )

    assert module.ENV_MODEL_ARGS_TEMPLATE in str(exc_info.value)


def test_translate_gemini_args_uses_env_model_template_when_provided() -> None:
    module = _load_module()

    def fake_which(name: str):
        return "/usr/local/bin/agy" if name == "agy" else None

    command = module.translate_gemini_args(
        ["-m", "gemini-2.5-pro", "-p", "hello"],
        env={module.ENV_MODEL_ARGS_TEMPLATE: "--model {model}"},
        which=fake_which,
    )

    assert command == ["/usr/local/bin/agy", "--model", "gemini-2.5-pro", "--print", "hello"]


def test_translate_gemini_args_rejects_unknown_flags() -> None:
    module = _load_module()

    def fake_which(name: str):
        return "/usr/local/bin/agy" if name == "agy" else None

    with pytest.raises(module.AdapterConfigError) as exc_info:
        module.translate_gemini_args(
            ["-p", "hello", "--sandbox-mode", "workspace-write"],
            env={},
            which=fake_which,
        )

    assert "Unsupported Gemini/CLI argument '--sandbox-mode'" in str(exc_info.value)


def test_translate_gemini_args_allows_known_passthrough_flags() -> None:
    module = _load_module()

    def fake_which(name: str):
        return "/usr/local/bin/agy" if name == "agy" else None

    command = module.translate_gemini_args(
        ["-p", "hello", "--print-timeout", "90s", "--dangerously-skip-permissions"],
        env={},
        which=fake_which,
    )

    assert command == [
        "/usr/local/bin/agy",
        "--print",
        "hello",
        "--print-timeout",
        "90s",
        "--dangerously-skip-permissions",
    ]
