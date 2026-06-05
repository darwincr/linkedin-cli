# linkedin-cli

**Drive LinkedIn from the command line or any program** — search people and jobs,
scrape profiles, check connection status, send connection requests, save/apply
to jobs, and read or send messages. One small, dependency-light Python tool that talks to LinkedIn's
private **Voyager API** through a **real, logged-in browser** (Playwright), so
it behaves like a human session instead of a cookie-only scraper.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Playwright](https://img.shields.io/badge/browser-Playwright-2EAD33)

> No SaaS, no API key, no database. Your browser, your LinkedIn account, your machine.

---

## ✨ Why linkedin-cli

- **Real browser session, not raw cookies.** A persistent Chromium window is
  launched once and shared; requests ride your live, authenticated session —
  far more resilient than header/cookie replay.
- **Safe concurrent callers.** Commands targeting the same session are serialized
  with a local per-session lock, so agents can invoke tools in parallel without
  corrupting the shared browser page.
- **Structured JSON out of every command.** Pipe it into `jq`, a script, or an
  LLM agent. Human-readable summaries by default; `--json` for the full record.
- **Robust login.** Authentication is a small **page-state machine** that
  understands LinkedIn's login, authwall, and security-checkpoint redirects —
  not a brittle one-shot form fill.
- **Language-agnostic.** Anything that can run a subprocess and parse JSON can
  drive LinkedIn — Python, Node, Go, shell, or an AI agent. No SDK lock-in.
- **Tiny surface.** Eight verbs, four dependencies, zero web framework. It knows
  about *a LinkedIn page and a browser* — nothing else.

## 📦 Install

```bash
pip install linkedin-agent-cli
python -m playwright install chromium
```

This installs the `linkedin-cli` command (equivalent to `python -m linkedin_cli.cli`).
The PyPI package is `linkedin-agent-cli`; the import name is `linkedin_cli`. For the
latest unreleased code, install from git:
`pip install "linkedin-agent-cli @ git+https://github.com/darwincr/linkedin-cli.git@main"`.

## 🚀 Quickstart

linkedin-cli uses a **bind + connect** model: one long-lived process owns the
browser; every command is a short client that connects to it.

```bash
# 1. Open + bind a session once (this process owns the browser window).
linkedin-cli session open --session work

# 2. From any other shell, drive it. Set the session once via env:
export LINKEDIN_CLI_SESSION=work
export LINKEDIN_USERNAME="you@example.com"
export LINKEDIN_PASSWORD="••••••••"

linkedin-cli login                                    # authenticate the session
linkedin-cli search "head of growth" --network first  # discover → handles
linkedin-cli jobs search "software engineer" --location "United States" --remote
linkedin-cli profile alice-smith                      # scrape a profile
linkedin-cli profile alice-smith --json > alice.json  # save the full record
linkedin-cli status  alice-smith                      # Connected / Pending / Qualified
linkedin-cli connect alice-smith                      # send a connection request
linkedin-cli message alice-smith --text "Hi Alice 👋"
linkedin-cli thread  alice-smith                      # read the conversation

linkedin-cli session close
```

Hit a security checkpoint? `playwright-cli attach work` opens the *same* browser
so you can clear it by hand, then carry on.

## 🧰 Commands

`--session <name>` (or `$LINKEDIN_CLI_SESSION`) and `--json` apply to every command.

| Command | What it does | `--json` result |
|---|---|---|
| `login` | Authenticate the session (creds from env), clear checkpoints, discover your own profile | `{account, self}` |
| `whoami` | Who is this session logged in as (no login flow) | `{self}` |
| `search <kw> [--network first/second/third] [--page N]` | People search → matching profile handles | `{query, page, network, profiles[]}` |
| `profile <id>` | Scrape a profile (positions, education, location, …); `--raw` adds the raw Voyager blob | full `LinkedInProfile` |
| `status <id>` | Connection state | `{public_identifier, state}` |
| `connect <id>` | Send a connection request (no note) | `{public_identifier, state}` |
| `message <id> --text …` | Send a direct message | `{public_identifier, sent}` |
| `thread <id>` | Read a conversation's messages | `{public_identifier, messages[]}` |
| `jobs search <kw> [--location L] [--page N] [--easy-apply] [--remote] [--date-posted past-24h/past-week/past-month] [--job-type full-time/part-time/contract/temporary/internship]` | Jobs search → matching job ids | `{query, location, page, filters, jobs[]}` |
| `jobs saved [--page N]` | List saved jobs | `{page, jobs[]}` |
| `jobs show <job>` | Show job details, saved state, and apply method | `{job_id, title, company, description, external_url, ats, ...}` |
| `jobs save <job>` | Save a job by id or URL | `{job_id, url, saved, changed}` |
| `jobs unsave <job>` | Unsave a job by id or URL | `{job_id, url, saved, changed}` |
| `jobs apply <job> [--submit]` | Start an application; submit only if immediately ready | `{job_id, url, method, submitted, manual, ...}` |

An `<id>` is a public handle (`alice-smith`) or a full profile URL. Commands that
need the internal member `urn` (`message`/`thread`/`status`) resolve it for you —
every command is independent and takes only a handle.

A `<job>` is a LinkedIn job id (`4418654174`) or a full `/jobs/view/...` URL.
External-apply jobs return LinkedIn's outbound `apply_url` plus a decoded
`external_url` when the URL is a LinkedIn safety redirect. `ats` is best-effort
from the decoded host (`greenhouse`, `lever`, `workday`, `company_site`, etc.).
Easy Apply jobs open the application flow and only submit when `--submit` is set
and the first dialog is already ready to submit.

## 🤖 Built for AI agents (and any language)

linkedin-cli is designed to be driven by an LLM as a **deterministic tool**. The
properties that make it agent-friendly:

- **Stable, typed JSON contract** — every verb returns one documented dict;
  maps directly onto a function-calling / tool-use schema.
- **id-only, stateless commands** — a public handle is the only argument an agent
  threads between steps; no session tokens, urns, or cursors to carry.
- **Predictable error taxonomy** — failures surface as `error: <type>: <message>`
  on stderr with a non-zero exit, so an agent can branch on `type`
  (`checkpoint_challenge`, `authentication`, `connection_limit`, …).
- **No hidden state or side effects** — stdout is result-only; logs go to stderr.
- **Self-describing** — see [`llms.txt`](llms.txt) for a compact spec an LLM can
  load directly, and `linkedin-cli <verb> --help` for per-verb usage.

Because every command emits JSON on stdout, you can drive LinkedIn from anything —
Python, Node, Go, shell, or an agent loop — no SDK and no Python import required:

```python
import subprocess, json

def li(*args):
    out = subprocess.run(["linkedin-cli", *args, "--json"],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)

for hit in li("search", "head of growth", "--network", "first")["profiles"]:
    handle = hit["public_identifier"]
    if li("status", handle)["state"] == "Qualified":
        li("message", handle, "--text", "Hi — loved your recent post!")
```

The discovery → outreach loop an agent runs: **`search` → `profile` / `status` →
`message` / `thread`.**

## 🧠 How it works

- **bind + connect** — `linkedin-cli session open` launches a persistent Chromium
  with `Browser.bind()` (Playwright ≥ 1.59) and registers a local `ws://`
  endpoint under the session name. Each command `chromium.connect()`s to that same
  browser and drives a *real* page. Auth, cookies, and fingerprint live in the
  owner's on-disk profile; the CLI keeps only a name→endpoint registry — **no
  database**. One session = one LinkedIn account.
- **Voyager API** — reads (`profile`, `thread`, `status`) call LinkedIn's private
  Voyager endpoints from inside the authenticated page (`fetch`), then parse the
  JSON — fast and structured, no DOM scraping where an API exists.
- **Page-state auth machine** — `classify_page()` judges the live page by URL
  *path* only (so a `/login?...redirect=/feed/` URL never reads as the feed), and
  each transition asserts its pre/post state, raising on an illegal jump. Login,
  authwall, and checkpoint flows are modeled explicitly.

## 📤 Output contract

- Every command produces one result **dict** — that dict is both the `--json`
  payload and the source the human summary is rendered from, so the two never drift.
- **Human-readable by default; `--json` for the full dict.**
- **No `--out` flag** — print to stdout, redirect to save (`… --json > out.json`).
- **stdout is result-only; logs and errors go to stderr** as
  `error: <type>: <message>` with a non-zero exit. Error types are stable:
  `checkpoint_challenge`, `authentication`, `profile_inaccessible`,
  `skip_profile`, `connection_limit`.

## 🔖 Releases

Releases are **fully automated** — there is no manual publish step.

- **Every push to `main`** triggers the `publish.yml` GitHub Actions workflow, which builds
  and uploads a stable `0.1.<commit-count>` release to PyPI via
  [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC, no stored token).
  The version is monotonic and unique per commit, so `pip install -U linkedin-agent-cli`
  always picks up the latest push.
- **Deliberate minor/major bumps:** push a `vX.Y.Z` tag — that commit publishes exactly
  `X.Y.Z` (e.g. `git tag v0.2.0 && git push origin v0.2.0`).

The version is injected at build time (`SETUPTOOLS_SCM_PRETEND_VERSION`); `hatch-vcs`
derives the version from git for local/`git+`-installed builds. Re-runs are idempotent
(`skip-existing`).

## ⚠️ Responsible use

This tool automates **your own** LinkedIn account from **your own** machine.
Automating LinkedIn may conflict with its Terms of Service, and aggressive use
can get an account restricted. Respect rate limits, only contact people for
legitimate reasons, follow applicable laws (GDPR/CAN-SPAM), and use it at your
own risk. You are responsible for how you use it.

## 📄 License

[MIT](LICENSE) © eracle

---

linkedin-cli was extracted from [**OpenOutreach**](https://github.com/eracle/OpenOutreach),
an open-source AI outreach tool, where it powers the LinkedIn discovery and
interaction layer. It is fully standalone and reusable on its own.
