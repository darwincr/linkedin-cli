# linkedin-cli

**Drive LinkedIn from the command line or any program** — search people, scrape
profiles, check connection status, send connection requests, and read or send
messages. One small, dependency-light Python tool that talks to LinkedIn's
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
pip install linkedincli
python -m playwright install chromium
```

This installs the `linkedin-cli` command (equivalent to `python -m linkedin_cli.cli`).
The PyPI package is `linkedincli`; the import name is `linkedin_cli`. For the
latest unreleased code, install from git:
`pip install "linkedincli @ git+https://github.com/eracle/linkedin-cli.git@main"`.

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

An `<id>` is a public handle (`alice-smith`) or a full profile URL. Commands that
need the internal member `urn` (`message`/`thread`/`status`) resolve it for you —
every command is independent and takes only a handle.

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
