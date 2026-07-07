---
name: linkedin-cli
description: "Operate the linkedin-cli tool that drives LinkedIn through a real authenticated browser session. USE FOR: any task involving LinkedIn — searching people/jobs/posts, reading or messaging profiles, managing connection requests, reading and replying to notifications, creating/editing/scheduling/deleting personal or company page posts, replying to company page inbox threads, saving/applying to jobs. DO NOT USE FOR: anything not related to LinkedIn."
---

# linkedin-cli operator skill

`linkedin-cli` drives LinkedIn through a real, logged-in Chromium session on this
machine. Every command emits one JSON object on stdout with `--json`; logs and
errors go to stderr. There is no API key and no SaaS — it acts as the session
owner's own LinkedIn account.

## How to run every command

Always invoke through the UV-managed checkout, never a global binary or bare
`python`:

```bash
uv run python -m linkedin_cli.cli <verb> [args...] --session work --json
```

Conventions that apply to **every** verb:

- `--session work` (or `$LINKEDIN_CLI_SESSION=work`) selects the authenticated
  browser session on this machine. Prefer the env var so commands stay short.
- `--json` emits the full result dict. Without it you get a short human summary.
  Always use `--json` when consuming output programmatically.
- Commands against the same session are serialized by a local lock. Do **not**
  run parallel live-browser commands against `work` — they queue and can stall.
- stdout carries only the result; everything else (logs, `error: ...` lines) is
  on stderr. A verb that ran is exit 0; failures are non-zero with
  `error: <type>: <message>` on stderr. Stable `type` values to branch on:
  `checkpoint_challenge`, `authentication`, `profile_inaccessible`,
  `skip_profile`, `connection_limit`.
- Thread IDs, activity IDs, job IDs, comment IDs, and notification indexes
  returned by one command are the handles you pass into the next. There is no
  session state between commands — thread explicit IDs between steps.

## Checking the current browser state

These are the only commands you run "directly" to understand session state. Use
them at the start of a task to confirm the session is alive and authenticated
before doing anything else.

- **`whoami`** — confirm who the session is logged in as (no login, no
  checkpoint). Returns `{ "self": { "public_identifier", "urn", "full_name" } }`.

  ```bash
  uv run python -m linkedin_cli.cli whoami --session work --json
  ```

- **`login`** — fill the login form and clear a checkpoint if the session is
  not yet authenticated. Returns the account plus the `self` block.

  ```bash
  uv run python -m linkedin_cli.cli login --session work --json
  ```

- **`session open`** — launch and bind a persistent browser that owns the
  profile, print its websocket endpoint, then **block**. Only needed for the
  legacy/debug bound-browser launcher; normal verbs auto-start a worker.
- **`session close`** — stop the worker (or legacy launcher) for a session.

  ```bash
  uv run python -m linkedin_cli.cli session close --session work --json
  ```

If `whoami` succeeds, the session is healthy. If it fails with
`authentication` or `checkpoint_challenge`, run `login` before retrying.

## Functional command map (retrieve `--help` on demand)

Every verb supports `<verb> --help` for exact arguments, choices, and result
shape. **Do not guess arguments** — when a task matches a category below, run
the listed `--help` command first, then run the verb with `--session work --json`.

The list below is a routing map: pick the category that matches the user's
intent, then retrieve help for the specific verb. Read-only verbs are marked
**(read)**; verbs that change LinkedIn state are marked **(write)**.

### People: discover, inspect, reach out

Use when the task is about finding or engaging individual LinkedIn members.

| Intent | Verb | Mode |
|---|---|---|
| Find members by keyword + facets (network degree, geo, company, school, industry, language, verified, open-to-volunteer, …) | `search --help` | read |
| Read a member's full profile (headline, positions, education, location) | `profile --help` | read |
| Check connection state with a member (Connected / Pending / Qualified) | `status --help` | read |
| Send a connection request (no note; no-op if already Connected/Pending) | `connect --help` | write |
| Send a direct message (optionally with file attachments) | `message --help` | write |
| List recent personal messaging conversations | `inbox --help` | read |
| Read the message thread with a member, or by `inbox` thread id | `thread --help` | read |

Typical loop: `search` → for each handle, `profile` and/or `status` →
`message` and/or `thread`; or `inbox` → `thread --thread-id <id>`.

### Jobs: search, track, apply

Use when the task is about LinkedIn job listings.

| Intent | Verb | Mode |
|---|---|---|
| Search jobs by keyword, location, date, type, remote, easy-apply | `jobs search --help` | read |
| List saved / in-progress / applied / archived job cards | `jobs saved --help` | read |
| Show full structured details for one job (description, apply method, ATS) | `jobs show --help` | read |
| Save a job | `jobs save --help` | write |
| Unsave one or more jobs | `jobs unsave --help` | write |
| Start or submit an Easy Apply application | `jobs apply --help` | write |

Typical loop: `jobs search` → `jobs show <id>` → `jobs save`/`jobs apply`.

### Personal posts: read

Use to inspect content on the member's own feed.

| Intent | Verb | Mode |
|---|---|---|
| List recent posts by a member | `posts profile --help` | read |
| Search posts by keyword, sort, date, content type, author facets | `posts search --help` | read |
| Show one post's content + aggregate engagement | `posts show --help` | read |
| Show engagement + visible comments for a post | `posts engagement --help` | read |
| List visible comments on a post | `posts comments --help` | read |

### Personal posts: write, edit, delete

Use to publish or modify the session owner's own posts. These change LinkedIn
state — confirm with the user before running destructive verbs.

| Intent | Verb | Mode |
|---|---|---|
| Create a post (text + optional images, documents, or poll) | `posts create --help` | write |
| Edit the text of an already-published post | `posts edit --help` | write |
| Delete a post by id, URN, or URL | `posts delete --help` | write |

### Personal posts: scheduling

Use to schedule posts for a future local datetime, or to manage the scheduled
list. Posts are addressed by a **1-based index** from `posts scheduled`.

| Intent | Verb | Mode |
|---|---|---|
| Save LinkedIn's draft prompt (write text, close composer) | `posts draft --help` | write |
| Schedule a text post for a specific local ISO datetime | `posts schedule --help` | write |
| Update scheduled time and/or text by 1-based index | `posts update-schedule --help` | write |
| List scheduled posts | `posts scheduled --help` | read |
| Cancel a scheduled post by 1-based index | `posts cancel --help` | write |

### Personal posts & comments: engagement

Use to react to, or reply to, posts and comments.

| Intent | Verb | Mode |
|---|---|---|
| React to a post (like/celebrate/support/love/insightful/funny) | `posts react --help` | write |
| Reply to a visible comment on a post | `posts comment-reply --help` | write |
| React to a visible comment on a post | `posts comment-react --help` | write |

### Notifications

Use to read and act on the session owner's LinkedIn notifications. Replies and
reactions target a **1-based index** from the `notifications` list.

| Intent | Verb | Mode |
|---|---|---|
| List visible notifications (with activity/comment ids) | `notifications --help` | read |
| Reply to the comment referenced by a notification | `notifications reply --help` | write |
| React to the post/comment referenced by a notification | `notifications react --help` | write |

Typical loop: `notifications` → `notifications reply/react --index N`.

### Company pages: discovery & content (read)

`<company-id>` is the numeric id from a company admin URL (e.g.
`https://www.linkedin.com/company/112454418/admin/`). Discover it with
`page list` first.

| Intent | Verb | Mode |
|---|---|---|
| List company pages this session can administer | `page list --help` | read |
| List published company page posts | `page posts --help` | read |
| Show one company page post by activity id or URL | `page post --help` | read |
| List scheduled company page posts | `page post-scheduled --help` | read |

### Company pages: content management (write)

Use to publish, edit, schedule, or delete posts as the page admin. Scheduled
posts are addressed by a **1-based index** from `page post-scheduled`. Confirm
with the user before destructive verbs.

| Intent | Verb | Mode |
|---|---|---|
| Create a text post as the page (optional images/documents/poll) | `page post-create --help` | write |
| Edit the text of a published page post | `page post-edit --help` | write |
| Schedule a page text post for a local datetime | `page post-schedule --help` | write |
| Update scheduled page post time and/or text by index | `page post-update-schedule --help` | write |
| Cancel a scheduled page post by index | `page post-cancel --help` | write |
| Delete a page post by activity id or URL | `page post-delete --help` | write |

### Company pages: inbox

Use to read and reply to messages in a company page's inbox (DOM-based,
scrolls up to `--limit`).

| Intent | Verb | Mode |
|---|---|---|
| List visible page inbox threads | `page inbox --help` | read |
| Read messages in a page inbox thread | `page thread --help` | read |
| Reply to a page inbox thread (optionally with attachments) | `page reply --help` | write |

Typical loop: `page list` → choose `company_id` → `page posts`/`page post`/
`page post-scheduled` for inspection, or `page inbox` → `page thread` →
`page reply` for inbox workflows.

## Safety rules

- **Read-only verbs are safe** to run for inspection at any time: `whoami`,
  `search`, `profile`, `status`, `inbox`, `thread`, `notifications`,
  `jobs search`, `jobs saved`, `jobs show`, `posts profile`, `posts search`,
  `posts show`, `posts engagement`, `posts comments`, `posts scheduled`,
  `page list`, `page posts`, `page post`, `page post-scheduled`,
  `page inbox`, `page thread`.
- **Write verbs change LinkedIn state.** Before running any `(write)` verb,
  confirm the specific action with the user — especially `posts delete`,
  `page post-delete`, `posts cancel`, `page post-cancel`, `connect`,
  `message`, `page reply`, and `jobs apply --submit`. For temporary
  create/delete tests, use clearly marked temporary content and delete it
  immediately after verification.
- Never run two live-browser commands against `work` in parallel; the session
  lock exists to keep the shared browser page consistent.
