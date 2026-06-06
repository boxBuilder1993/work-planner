# wp — WorkPlanner CLI

Command-line interface for WorkPlanner. Talks directly to the backend's
internal API using `X-Internal-Key`, so it acts as the system identity
(bypasses per-user JWT scoping). Fine for single-user setups, not safe
to expose to other people as-is.

## Install

```sh
pipx install ./cli
# or for development:
pipx install --editable ./cli
```

This drops a `wp` executable on your `PATH`.

## First-time setup

```sh
wp config init
# Prompts for:
#   Backend base URL    (e.g. http://localhost:8001 or your Railway URL)
#   Internal API key    (same value as INTERNAL_API_KEY in the repo's .env)
```

Stored at `~/.config/workplanner/config.toml` with mode `0600`. Multiple
profiles supported — `wp --profile prod ls` etc.

Override per invocation with env vars:

```sh
WP_BASE_URL=https://workplanner-backend.up.railway.app \
WP_INTERNAL_KEY=$(grep INTERNAL_API_KEY .env | cut -d= -f2) \
  wp ls
```

## Commands

| Command                              | Effect                                                          |
| ------------------------------------ | --------------------------------------------------------------- |
| `wp ls [--status S \| --all]`        | List top-level tasks (default PENDING).                         |
| `wp tree <id> [--depth N]`           | Recursive subtree.                                              |
| `wp show <id> [--no-comments]`       | Task details + comment thread.                                  |
| `wp search [query] [--status …]`     | Search tasks by title/description and metadata filters.         |
| `wp add "title" [--parent …] […]`    | Create a task.                                                  |
| `wp set <id> --title … --status …`   | Patch fields on a task.                                         |
| `wp close <id>` / `wp reopen <id>`   | Status shortcuts.                                               |
| `wp comments <id>`                   | List comments (threaded).                                       |
| `wp comment <id> "text"`             | Post a comment. Text can come from stdin if omitted or `-`.     |
| `wp reply <task> <parent-uuid> "..."`| Reply to a comment.                                             |
| `wp approve <comment-uuid>`          | Approve a PROPOSAL comment.                                     |
| `wp deny <comment-uuid> [-m reason]` | Deny a PROPOSAL comment.                                        |
| `wp ai <persona> <task> "text"`      | Post `@ai-<persona> text` — triggers the chat-poller.           |
| `wp work-items list [--task …] […]`  | List WorkItems (the unit of AI execution). Filter by task/status/persona. |
| `wp work-items show <uuid>`          | Full WorkItem detail: assignment, output, attempts.             |
| `wp work-items cancel <uuid>`        | Cancel a pending or failed WorkItem.                            |
| `wp work-items retry <uuid>`         | Reset retry_count on a failed WorkItem.                         |
| `wp knowledge add <id> [-c … \| @file \| stdin] [--tag …]` | Create a knowledge card.                  |
| `wp knowledge list [--tag …] [--all]`| List cards (valid only unless `--all`).                         |
| `wp knowledge show <id>`             | Show a card's full content.                                     |
| `wp knowledge search "<phrase>" [--tag …]` | Full-text search over card content; filter by tag.        |
| `wp knowledge edit <id> [-c … \| --tag … \| --clear-tags \| --valid/--invalid]` | Edit content/tags/validity. |
| `wp knowledge rm <id>`               | Delete a card.                                                  |
| `wp config init / show`              | Manage the config file.                                         |

### Knowledge cards

The knowledge base is a set of searchable text **cards** the AI personas read
to ground their work (see `docs/KNOWLEDGE_CARDS_DESIGN.md`). Author them here:

```sh
# inline, from a file, or from stdin
wp knowledge add commit-style -c "Conventional commits. Co-Authored-By for AI." --tag convention
wp knowledge add architecture @notes/arch.md --tag architecture --tag backend
some-generator | wp knowledge add gen-notes --tag generated

wp knowledge search "how does auth work"     # full-text search
wp knowledge list --tag backend
wp knowledge edit commit-style --invalid       # retire without deleting
```

`id` is a slug (lowercase, digits, hyphens). Invalid cards are hidden from
search/list unless you pass `--all`.

### ID resolution

Task IDs accept either a full UUID or a unique prefix (>= 4 chars). The CLI
calls the search endpoint to disambiguate. Comment IDs require the full UUID
(no `list all comments` endpoint exists) — use `wp comments <task>` to see them.

### AI dispatch

```sh
wp ai engineer 8b3fa "look into why the dashboard filter is broken"
# posts: "@ai-engineer look into why the dashboard filter is broken"
```

Available personas: `default`, `engineer`, `planner`, `manager`, `reviewer`.
The chat-poller picks up the mention on its next cycle.

## Not yet supported

- Repeating tasks (backend has no internal endpoint for them).
- Task delete (backend has no internal `DELETE /tasks/:id`).
- Comment delete (same).
- Knowledge-base store/query (separate concern; use the MCP server in
  claude-proxy or call the backend KB endpoints directly).

These can be added when the backend's internal mux exposes them.
