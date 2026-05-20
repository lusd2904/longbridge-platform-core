# Antigravity CLI migration note

Date: 2026-05-20

## Local verification

- `which agy` returned `/Users/lusd/.local/bin/agy`.
- `which antigravity`, `which ag`, `which antigravity-cli` all returned not found on this machine.
- Official installer: `curl -fsSL https://antigravity.google/cli/install.sh | bash`
- The official installer script writes the CLI to `~/.local/bin/agy`.
- A temporary official binary run confirmed:
  - `agy --help` exposes `--print`, `--prompt-interactive`, `--continue`, `install`, `plugin`, `update`
  - `agy --print 'ping'` works on this machine
  - `agy` does not accept Gemini's `-m` flag; `agy -m test --print 'ping'` returns `flags provided but not defined: -m`

## Minimal command mapping

- `gemini -p '...'` -> `agy --print '...'`
- `gemini --prompt '...'` -> `agy --prompt '...'`
- `gemini -i '...'` -> `agy --prompt-interactive '...'`
- `gemini -c` -> `agy --continue`
- Do not blindly replace `gemini -m ...`; the current Antigravity CLI help does not expose a compatible model flag.

## Authentication

- `agy --help` does not expose a dedicated `login` or `auth` subcommand.
- Running `agy --print 'Reply exactly: pong' --print-timeout 30s` in this shell triggered browser OAuth instead of returning a model response.
- The CLI prints a Google OAuth URL and waits for either browser completion or a pasted authorization code. The latest generated URL/state is intentionally not committed as a durable secret; regenerate it with the command above when the user is ready to authorize.
- After browser authorization, `agy --print 'Reply exactly: pong' --print-timeout 120s` returned `pong` in this workspace shell.
- If browser sign-in is required outside the CLI flow, use `https://app.antigravity.google/`.

## Repository audit result

- No executable Gemini CLI invocations were found in active scripts, Dockerfiles, compose files, CI config, or `package.json` scripts.
- Gemini-related hits in this repository are currently limited to historical `.omx/artifacts/*` review records and one non-CLI narrative mention in `docs/multi-agent-agno-status.md`.
- Because the repo does not execute Gemini CLI inside containers today, no Dockerfile, entrypoint, compose, or Python/Node dependency change is required for this migration.

## Historical files intentionally left unchanged

- `.omx/artifacts/gemini-*.md`, `.omx/artifacts/gemini-*.prompt.txt`, `.omx/artifacts/gemini-*.raw.md`
- `.omx/artifacts/reviews/*.md` entries that quote past `gemini` commands or Gemini capacity errors

These files are evidence of past runs. Rewriting them to say Antigravity would make the audit trail inaccurate.
