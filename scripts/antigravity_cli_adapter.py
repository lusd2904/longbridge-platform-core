#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Mapping, NamedTuple, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLI_CANDIDATES = ("agy", "antigravity", "antigravity-cli", "ag")
DEFAULT_MODE_ARGS = {
    "print": ("--print",),
    "interactive": ("--prompt-interactive",),
    "continue": ("--continue",),
}
MODE_ENV_KEYS = {
    "print": "REF_AGENT_CLI_PRINT_ARGS",
    "interactive": "REF_AGENT_CLI_INTERACTIVE_ARGS",
    "continue": "REF_AGENT_CLI_CONTINUE_ARGS",
}
ENV_BIN = "REF_AGENT_CLI_BIN"
ENV_APPEND_ARGS = "REF_AGENT_CLI_APPEND_ARGS"
ENV_MODEL_ARGS_TEMPLATE = "REF_AGENT_CLI_MODEL_ARGS_TEMPLATE"
SUPPORTED_FORWARD_FLAGS = {
    "--add-dir": True,
    "--conversation": True,
    "--dangerously-skip-permissions": False,
    "--log-file": True,
    "--print-timeout": True,
}


class AdapterConfigError(RuntimeError):
    pass


class ResolvedCli(NamedTuple):
    command: str
    path: str


def _split_env_args(value: str | None) -> list[str]:
    return shlex.split(value or "")


def resolve_cli(
    env: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> ResolvedCli:
    active_env = dict(os.environ if env is None else env)
    configured = active_env.get(ENV_BIN, "").strip()
    if configured:
        resolved = which(configured)
        if not resolved:
            raise AdapterConfigError(
                f"{ENV_BIN} points to '{configured}', but that command is not available in PATH."
            )
        return ResolvedCli(command=configured, path=resolved)
    for candidate in DEFAULT_CLI_CANDIDATES:
        resolved = which(candidate)
        if resolved:
            return ResolvedCli(command=candidate, path=resolved)
    raise AdapterConfigError(
        "Antigravity CLI not found. Install with: curl -fsSL https://antigravity.google/cli/install.sh | bash"
    )


def _resolve_mode_args(mode: str, env: Mapping[str, str]) -> list[str]:
    configured = env.get(MODE_ENV_KEYS[mode], "").strip()
    if configured:
        return _split_env_args(configured)
    return list(DEFAULT_MODE_ARGS[mode])


def _resolve_model_args(model: str | None, env: Mapping[str, str]) -> list[str]:
    if not model:
        return []
    template = env.get(ENV_MODEL_ARGS_TEMPLATE, "").strip()
    if not template:
        raise AdapterConfigError(
            "A Gemini model flag was requested, but Antigravity model mapping is unknown. "
            f"Set {ENV_MODEL_ARGS_TEMPLATE} with a template such as '--flag {{model}}'."
        )
    parts = _split_env_args(template)
    return [part.replace("{model}", model) for part in parts]


def build_command(
    *,
    mode: str,
    prompt: str | None = None,
    model: str | None = None,
    passthrough_args: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> list[str]:
    active_env = dict(os.environ if env is None else env)
    resolved = resolve_cli(active_env, which=which)
    command = [resolved.path]
    command.extend(_resolve_model_args(model, active_env))
    command.extend(_resolve_mode_args(mode, active_env))
    if prompt is not None:
        command.append(prompt)
    if passthrough_args:
        command.extend(passthrough_args)
    command.extend(_split_env_args(active_env.get(ENV_APPEND_ARGS)))
    return command


def translate_gemini_args(
    args: Sequence[str],
    env: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> list[str]:
    active_env = dict(os.environ if env is None else env)
    mode: str | None = None
    prompt: str | None = None
    model: str | None = None
    passthrough: list[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        if token in {"-p", "--prompt"}:
            if index + 1 >= len(args):
                raise AdapterConfigError(f"{token} requires a prompt string.")
            if mode and mode != "print":
                raise AdapterConfigError("Conflicting Gemini prompt flags were provided.")
            mode = "print"
            prompt = args[index + 1]
            index += 2
            continue
        if token in {"-i", "--prompt-interactive"}:
            if index + 1 >= len(args):
                raise AdapterConfigError(f"{token} requires a prompt string.")
            if mode and mode != "interactive":
                raise AdapterConfigError("Conflicting Gemini prompt flags were provided.")
            mode = "interactive"
            prompt = args[index + 1]
            index += 2
            continue
        if token in {"-c", "--continue"}:
            if mode and mode != "continue":
                raise AdapterConfigError("Conflicting Gemini prompt flags were provided.")
            mode = "continue"
            index += 1
            continue
        if token in {"-m", "--model"}:
            if index + 1 >= len(args):
                raise AdapterConfigError(f"{token} requires a model name.")
            model = args[index + 1]
            index += 2
            continue
        needs_value = SUPPORTED_FORWARD_FLAGS.get(token)
        if needs_value is True:
            if index + 1 >= len(args):
                raise AdapterConfigError(f"{token} requires a value.")
            passthrough.extend([token, args[index + 1]])
            index += 2
            continue
        if needs_value is False:
            passthrough.append(token)
            index += 1
            continue
        if token == "--":
            index += 1
            continue
        raise AdapterConfigError(
            f"Unsupported Gemini/CLI argument '{token}'. "
            "Only verified Antigravity-compatible flags are built in; use environment overrides for anything else."
        )
    if not mode:
        raise AdapterConfigError("No supported Gemini action was provided. Use -p, -i, or -c.")
    if mode in {"print", "interactive"} and prompt is None:
        raise AdapterConfigError(f"Mode '{mode}' requires a prompt string.")
    if mode == "continue" and prompt is not None:
        raise AdapterConfigError("Continue mode must not include a prompt string.")
    return build_command(
        mode=mode,
        prompt=prompt,
        model=model,
        passthrough_args=passthrough,
        env=active_env,
        which=which,
    )


def _command_payload(command: Sequence[str]) -> str:
    return json.dumps(
        {
            "cwd": str(ROOT),
            "command": list(command),
            "shell": shlex.join(command),
        },
        ensure_ascii=False,
        indent=2,
    )


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Antigravity CLI adapter for Gemini migration.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    probe_parser = subparsers.add_parser("probe", help="Resolve and inspect the local Antigravity CLI.")
    probe_parser.add_argument("--format", choices=("text", "json"), default="text")

    run_parser = subparsers.add_parser("run", help="Run a normalized Antigravity CLI action.")
    run_parser.add_argument("--mode", choices=("print", "interactive", "continue"), required=True)
    run_parser.add_argument("--prompt")
    run_parser.add_argument("--model")
    run_parser.add_argument("--pass-arg", action="append", default=[])
    run_parser.add_argument("--dry-run", action="store_true")

    compat_parser = subparsers.add_parser(
        "gemini-compat",
        help="Translate a limited Gemini-style invocation into verified Antigravity CLI arguments.",
    )
    compat_parser.add_argument("--dry-run", action="store_true")
    compat_parser.add_argument("args", nargs=argparse.REMAINDER)
    return parser.parse_args(argv)


def _run_subprocess(command: Sequence[str]) -> int:
    completed = subprocess.run(command, cwd=ROOT)
    return int(completed.returncode)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        if args.command == "probe":
            resolved = resolve_cli()
            if args.format == "json":
                print(json.dumps({"command": resolved.command, "path": resolved.path}, ensure_ascii=False, indent=2))
                return 0
            print(f"[antigravity] using {resolved.command} at {resolved.path}")
            help_result = subprocess.run([resolved.path, "--help"], cwd=ROOT, capture_output=True, text=True, check=False)
            output = help_result.stdout or help_result.stderr
            print(output.rstrip())
            return 0 if help_result.returncode == 0 else int(help_result.returncode)

        if args.command == "run":
            command = build_command(
                mode=args.mode,
                prompt=args.prompt,
                model=args.model,
                passthrough_args=args.pass_arg,
            )
            if args.dry_run:
                print(_command_payload(command))
                return 0
            return _run_subprocess(command)

        compat_args = list(args.args)
        if compat_args and compat_args[0] == "--":
            compat_args = compat_args[1:]
        command = translate_gemini_args(compat_args)
        if args.dry_run:
            print(_command_payload(command))
            return 0
        return _run_subprocess(command)
    except AdapterConfigError as exc:
        print(f"[antigravity] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
