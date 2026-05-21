from __future__ import annotations

import importlib.util
import subprocess
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


def test_probe_json_includes_gemini_fallback(monkeypatch, capsys) -> None:
    module = _load_module()

    monkeypatch.setattr(
        module,
        "resolve_cli",
        lambda: module.ResolvedCli("agy", "/usr/local/bin/agy"),
    )
    monkeypatch.setattr(
        module,
        "resolve_gemini_cli",
        lambda: module.ResolvedCli("gemini", "/usr/local/bin/gemini"),
    )

    assert module.main(["probe", "--format", "json"]) == 0

    payload = module.json.loads(capsys.readouterr().out)
    assert payload["path"] == "/usr/local/bin/agy"
    assert payload["geminiFallback"]["path"] == "/usr/local/bin/gemini"


def test_run_with_gemini_auth_fallback_uses_gemini_on_oauth_failure() -> None:
    module = _load_module()
    calls = []

    def fake_which(name: str):
        return {
            "agy": "/usr/local/bin/agy",
            "gemini": "/usr/local/bin/gemini",
        }.get(name)

    def fake_runner(command, **kwargs):
        calls.append(list(command))
        if command[0].endswith("agy"):
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="OAuth login required")
        return subprocess.CompletedProcess(command, 0, stdout="gemini ok", stderr="")

    code = module.run_with_gemini_auth_fallback(
        mode="print",
        prompt="review docs",
        model=None,
        env={},
        which=fake_which,
        runner=fake_runner,
    )

    assert code == 0
    assert calls == [
        ["/usr/local/bin/agy", "--print", "review docs"],
        ["/usr/local/bin/gemini", "--prompt", "review docs"],
    ]


def test_run_with_gemini_auth_fallback_handles_zero_exit_auth_prompt() -> None:
    module = _load_module()
    calls = []

    def fake_which(name: str):
        return {
            "agy": "/usr/local/bin/agy",
            "gemini": "/usr/local/bin/gemini",
        }.get(name)

    def fake_runner(command, **kwargs):
        calls.append(list(command))
        if command[0].endswith("agy"):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=(
                    "Authentication required. Please visit the URL to log in:\n"
                    "Waiting for authentication (timeout 30s)...\n"
                    "Or, paste the authorization code here and press Enter:\n"
                    "Error: authentication timed out.\n"
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(command, 0, stdout="gemini ok", stderr="")

    code = module.run_with_gemini_auth_fallback(
        mode="print",
        prompt="review docs",
        model=None,
        env={},
        which=fake_which,
        runner=fake_runner,
    )

    assert code == 0
    assert calls == [
        ["/usr/local/bin/agy", "--print", "review docs"],
        ["/usr/local/bin/gemini", "--prompt", "review docs"],
    ]


def test_run_with_gemini_auth_fallback_does_not_mask_non_auth_failure() -> None:
    module = _load_module()
    calls = []

    def fake_which(name: str):
        return {
            "agy": "/usr/local/bin/agy",
            "gemini": "/usr/local/bin/gemini",
        }.get(name)

    def fake_runner(command, **kwargs):
        calls.append(list(command))
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="unknown flag")

    code = module.run_with_gemini_auth_fallback(
        mode="print",
        prompt="review docs",
        model=None,
        env={},
        which=fake_which,
        runner=fake_runner,
    )

    assert code == 2
    assert calls == [["/usr/local/bin/agy", "--print", "review docs"]]


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
