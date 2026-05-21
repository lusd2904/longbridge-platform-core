# Antigravity CLI migration note

Date: 2026-05-20

## Cleanup / migration plan

1. Audit active code paths for executable Gemini CLI, NotebookLM, and Gemini review workflow usage.
2. Leave review business flow untouched unless it actually shells out to Gemini.
3. Centralize Antigravity CLI probing and Gemini-compat translation in one adapter entrypoint.
4. Only bake in command forms verified on this machine; force unknown Gemini flags behind explicit environment configuration.
5. If Antigravity blocks on OAuth/auth in non-interactive review mode, fall back to the already-installed Gemini CLI instead of requiring another authorization code.
6. Verify the adapter with tests and shell-level probe commands.

## Local verification

- `which agy` returned `/Users/lusd/.local/bin/agy`.
- `which gemini` returned `/Users/lusd/.local/bin/gemini`.
- `which antigravity`, `which ag`, `which antigravity-cli` all returned not found on this machine.
- Official installer: `curl -fsSL https://antigravity.google/cli/install.sh | bash`
- The official installer script writes the CLI to `~/.local/bin/agy`.
- A temporary official binary run confirmed:
  - `agy --help` exposes `--print`, `--prompt-interactive`, `--continue`, `install`, `plugin`, `update`
  - `agy --prompt` is an alias for `--print`
  - `agy -p` and `agy -i` are short aliases for `--print` and `--prompt-interactive`
  - `agy` does not accept Gemini's `-m` flag; `agy -m test --print 'ping'` returns `flags provided but not defined: -m`

## Actual usage audit

- No executable Gemini CLI invocations were found in active scripts, Dockerfiles, compose files, CI config, `package.json` scripts, backend Python, or frontend Node utilities.
- No active NotebookLM integration points were found in runtime code.
- The current review workflow is `scheduler-service -> analysis-service -> Agno sidecar -> agent governance tables -> task center review UI`.
- Gemini-related hits in this repository are currently limited to:
  - this migration note;
  - one non-CLI narrative mention in [docs/multi-agent-agno-status.md](./multi-agent-agno-status.md);
  - historical `.omx/artifacts/*` records outside runtime code.

Because the live review path does not shell out to Gemini today, the low-risk migration is an adapter layer for future/manual CLI use, not a business-flow rewrite.

## Adapter entrypoints

- Probe or inspect local CLI:
  - `python3 scripts/antigravity_cli_adapter.py probe`
  - `./scripts/check_antigravity_cli.sh`
- Run verified normalized actions:
  - `python3 scripts/antigravity_cli_adapter.py run --mode print --prompt 'ping' --dry-run`
  - `python3 scripts/antigravity_cli_adapter.py run --mode interactive --prompt 'review this diff' --dry-run`
- Runtime fallback:
  - `run --mode print` first invokes Antigravity.
  - If the Antigravity output contains OAuth/login/auth/credential failure text and exits non-zero, the adapter invokes `gemini --prompt '<same prompt>'`.
  - Set `REF_AGENT_CLI_DISABLE_GEMINI_FALLBACK=true` to disable the fallback for a strict Antigravity-only check.
- Translate a limited Gemini-style command without executing it:
  - `python3 scripts/antigravity_cli_adapter.py gemini-compat --dry-run -- -p 'ping'`

## Verified command mapping

- `gemini -p '...'` -> `agy --print '...'`
- `gemini --prompt '...'` -> `agy --print '...'`
- `gemini -i '...'` -> `agy --prompt-interactive '...'`
- `gemini -c` -> `agy --continue`
- Do not blindly replace `gemini -m ...`; the current Antigravity CLI help does not expose a compatible model flag.
- The adapter rejects unknown Gemini/CLI flags by default. If a missing mapping is truly required, provide it explicitly through environment variables instead of hardcoding a guessed command.

## Environment overrides

- `REF_AGENT_CLI_BIN`
  - Force a specific CLI binary name if the machine does not use `agy`.
- `REF_AGENT_CLI_PRINT_ARGS`
- `REF_AGENT_CLI_INTERACTIVE_ARGS`
- `REF_AGENT_CLI_CONTINUE_ARGS`
  - Override the default Antigravity arguments per mode.
- `REF_AGENT_CLI_MODEL_ARGS_TEMPLATE`
  - Required if an existing Gemini workflow passes `-m` / `--model`.
  - Example only if your local Antigravity build actually supports it: `REF_AGENT_CLI_MODEL_ARGS_TEMPLATE='--model {model}'`
- `REF_AGENT_CLI_APPEND_ARGS`
  - Append extra verified flags after the translated command.
- `REF_AGENT_CLI_GEMINI_BIN`
  - Force the Gemini fallback binary if the machine does not expose it as `gemini`.
- `REF_AGENT_CLI_DISABLE_GEMINI_FALLBACK`
  - Set to `true`/`1` to keep Antigravity auth failures as hard failures.

## Authentication

- `agy --help` does not expose a dedicated `login` or `auth` subcommand.
- Running `agy --print 'Reply exactly: pong' --print-timeout 30s` in this shell triggered browser OAuth instead of returning a model response.
- The CLI prints a Google OAuth URL and waits for either browser completion or a pasted authorization code. The latest generated URL/state is intentionally not committed as a durable secret; regenerate it with the command above when the user is ready to authorize.
- After browser authorization, `agy --print 'Reply exactly: pong' --print-timeout 120s` returned `pong` in this workspace shell.
- If browser sign-in is required outside the CLI flow, use `https://app.antigravity.google/`.
- Current working rule: for README/architecture/code review tasks, use Antigravity when it is already authorized; if it asks for OAuth again, use Gemini CLI fallback and record the fallback in the review artifact.

## Repository audit result

- Because the repo does not execute Gemini CLI inside containers today, no Dockerfile, entrypoint, compose, or Python/Node dependency change is required for this migration.

## Historical files intentionally left unchanged

- `.omx/artifacts/gemini-*.md`, `.omx/artifacts/gemini-*.prompt.txt`, `.omx/artifacts/gemini-*.raw.md`
- `.omx/artifacts/reviews/*.md` entries that quote past `gemini` commands or Gemini capacity errors

These files are evidence of past runs. Rewriting them to say Antigravity would make the audit trail inaccurate.
