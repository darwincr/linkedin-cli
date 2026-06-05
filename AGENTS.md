# AGENTS.md

## Project Overview

`linkedin-cli` is a small Python CLI for driving LinkedIn through a real authenticated browser session. It uses Playwright to attach to a long-lived Chromium session and performs LinkedIn actions from that browser context.

The project is greenfield. Prefer clean, direct, efficient implementations over compatibility layers or legacy fallbacks. Do not preserve old behavior unless there is an explicit product reason.

Core package:

- `src/linkedin_cli/cli.py` defines the command-line interface and output rendering.
- `src/linkedin_cli/session.py` manages attaching commands to the bound browser session.
- `src/linkedin_cli/actions/` contains command implementations.
- `src/linkedin_cli/browser/` contains browser/navigation helpers.

## Development Principles

- Use the smallest clean change that solves the current problem.
- Keep command behavior deterministic and machine-readable.
- Every command should emit structured JSON with `--json`.
- Avoid broad compatibility shims for previous internal behavior.
- Prefer simple helpers only when they reduce duplication or clarify behavior.
- Test browser automation against the live authenticated LinkedIn session on this machine.
- Do not use destructive LinkedIn actions in tests unless the user explicitly approves them.

## Environment

This project is managed with `uv`. Prefer `uv run` for all development commands.

The active editable checkout is expected to be this repository directory. Avoid relying on globally installed `linkedin-cli` while developing, because it may point at a different checkout or package version.

The browser session on this machine is already authenticated and ready for live LinkedIn testing. The current known session name is:

```bash
work
```

If needed, set:

```bash
export LINKEDIN_CLI_SESSION=work
```

Then commands can omit `--session work`.

## Common Commands

Show CLI help:

```bash
uv run python -m linkedin_cli.cli --help
```

Show jobs command help:

```bash
uv run python -m linkedin_cli.cli jobs --help
```

List saved jobs from the live authenticated browser:

```bash
uv run python -m linkedin_cli.cli jobs saved --session work --json
```

Search jobs:

```bash
uv run python -m linkedin_cli.cli jobs search "software engineer" --session work --json
```

Show a job by ID:

```bash
uv run python -m linkedin_cli.cli jobs show 4380431768 --session work --json
```

Syntax-check a changed file:

```bash
uv run python -m py_compile src/linkedin_cli/actions/jobs.py
```

Check repository status:

```bash
git status --short
```

Review local changes:

```bash
git diff
```

## Live Browser Testing

Use the live browser for tests that depend on LinkedIn DOM structure, navigation, or authenticated APIs.

Safe read-only examples:

```bash
uv run python -m linkedin_cli.cli jobs saved --session work --json
uv run python -m linkedin_cli.cli jobs show 4380431768 --session work --json
```

Potentially destructive commands require explicit user approval before running:

```bash
uv run python -m linkedin_cli.cli jobs save <job-id> --session work --json
uv run python -m linkedin_cli.cli jobs unsave <job-id> --session work --json
uv run python -m linkedin_cli.cli jobs apply <job-id> --session work --json
uv run python -m linkedin_cli.cli connect <profile-id> --session work --json
uv run python -m linkedin_cli.cli message <profile-id> --text "..." --session work --json
```

When testing DOM selectors directly, attach to the recorded session rather than launching a new browser. Use the project session helpers and keep tests read-only unless approved.

## Notes For Agents

- Work from the UV-managed checkout, not a stale copy elsewhere.
- Use `uv run python -m linkedin_cli.cli ...` instead of bare `python` or a global `linkedin-cli`.
- The live LinkedIn pages can change. Verify selectors against the authenticated browser before considering browser automation changes complete.
- The session lock exists to prevent concurrent automation from fighting over the same browser. Avoid parallel live-browser commands against the same session.
- Keep stdout reserved for command results; logs and diagnostics should go to stderr in CLI code.
