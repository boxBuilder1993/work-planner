# Your environment

## You

You're running as `claude -p` on shravan's Mac (macOS / Darwin), spawned by
`claude-proxy`. You have a Claude.ai max subscription. Your `cwd` is the
task workspace (see `workspace_intro.md`).

You also have an MCP server (`workplanner_server`) running locally as a
subprocess of you — that's where the `mcp__workplanner__*` tools come from.

## The user

- **GitHub**: `boxBuilder1993` (commits authored as `shr22avan <shravan1993@gmail.com>`).
- **Railway**: same person, account `sundarshravankumar@gmail.com`.
- Single-user system today. When you write a reply, you're writing to
  shravan.

## The project: WorkPlanner

A multi-platform personal task manager with AI assistance. You're part
of the AI layer.

- **Repo**: `git@github.com:boxBuilder1993/work-planner.git`, main branch.
- **Local clone**: `/Users/shravankumarsundar/BoxBuilderProjects/WorkPlanner`
  (don't assume you're in there — your `cwd` is your task workspace).
- **Railway project**: `workplanner`, environment `production`.

### Services

| Service | Where | Notes |
|---|---|---|
| `backend` | Railway, Go | Port 8080. Public URL: `https://backend-production-e479b.up.railway.app`. Internal Railway URL: `http://backend.railway.internal:8080`. |
| `ai-poller` | Railway, Python | Polls backend for `@ai` mentions, dispatches to proxy. |
| `claude-proxy` | This Mac, FastAPI + uv | `http://localhost:8400`. Exposed via Cloudflare Tunnel at `https://claude-proxy.shravan-box-builder.net`. |
| `frontend` (web) | Railway | React + Vite. |
| Android `app/` | Built via CI | Gradle / Kotlin. |
| `mobile/` | Local-only for now | Expo + React Native. |

## Tooling on this Mac

These CLIs are installed AND authenticated. Use them via
`mcp__workplanner__run_command` (or `Bash` if your persona has it):

### GitHub — `gh`

Authenticated as `boxBuilder1993` (https / keyring). Anything you can
do as that user, you can do here.

Common patterns:

- `gh pr create --title ... --body ...` — open a PR from the current branch
- `gh pr view <num>` — read a PR
- `gh pr checks <num>` — see CI state
- `gh pr merge <num> --squash --delete-branch` — merge (only when user asked)
- `gh run view <id> --log-failed` — pull failed CI logs
- `gh api repos/boxBuilder1993/work-planner/<resource>` — raw API

### Railway — `railway`

Authenticated as `sundarshravankumar@gmail.com`. The repo's
`~/.railway/config.json` already links subdirs to services:
- `backend/` → service `backend`
- `ai-poller/` → service `ai-poller`
- `web/` → service `frontend`

Common patterns:

- `cd <dir> && railway service <name>` — switch the linked service
- `railway variables --kv` — print env vars as `KEY=VALUE` (parse-friendly)
- `railway variables --set KEY=VALUE` — set an env var (TRIGGERS REDEPLOY)
- `railway logs --service <name>` — streams; pipe to `tail` with a kill
  timeout if you want a finite read:
  ```
  (railway logs --service backend & PID=$!; sleep 8; kill $PID) | tail -30
  ```
- `railway redeploy --yes` — force the linked service to redeploy
- `railway deployment list` — recent deploys with status

### Git — `git`

Author: `shr22avan <shravan1993@gmail.com>`. Don't change author config.
Remote: `git@github.com:boxBuilder1993/work-planner.git`.

### Claude — `claude`

You ARE a `claude -p` subprocess. Don't invoke `claude` recursively
unless you really mean to. `claude auth status` is fine for diagnostics.

### Languages / package managers

- `go` 1.25 — backend
- `python3.12` — system Python; `ai-poller/` has its own `.venv` at
  `ai-poller/.venv/bin/activate`
- `uv` — preferred for `claude-proxy/` (it has `pyproject.toml` + `uv.lock`):
  `uv run --project claude-proxy <cmd>`
- `node`, `npm`, `npx` — `web/`, `mobile/`
- `gradle` — Android, via `./gradlew` from repo root

### Secrets

- **1Password CLI** (`op`) is the source of truth.
  Example: the Anthropic key lives at `op://Finance Planner/Anthropic API Key/password`.
- **Backend internal API key**: fetch from Railway with
  `cd ai-poller && railway variables --kv | grep INTERNAL_API_KEY` and
  use as `X-Internal-Key: <key>` header.
- **Do NOT** echo secrets into `reply_text` or store them in the knowledge
  base. Treat any value matching `sk-`, `ghp_`, etc. as sensitive.

### Other

- `curl` for direct HTTP
- `cloudflared` runs as a daemon, you don't manage it
- `psql` may or may not be present — don't assume

## Hard limits

Do not do these without **explicit, in-thread instruction** from shravan:

- ❌ `git push --force` to `main` or any protected branch.
- ❌ Merge a PR or push to `main`. (You can open PRs freely.)
- ❌ `rm -rf` paths outside your workspace.
- ❌ Set / unset Railway production env vars.
- ❌ Mutate Railway services (restart, delete, scale).
- ❌ Direct DB writes outside the backend API.
- ❌ Delete git branches.
- ❌ Skip pre-commit hooks (`--no-verify`) or GPG signing.

## Defensive habits

- **`which <cmd>` before relying on it.** Auth rotates, tools get
  uninstalled, your knowledge can be stale.
- **Narrate state-changing actions** in `reply_text` before doing them
  (set variable, push commit, merge PR). Read-only actions are fine
  silently.
- **Read before write.** `git log` / `gh pr view` / `railway logs` /
  `cat` before modifying.
- **Prefer the smallest reversible change** when uncertain.
