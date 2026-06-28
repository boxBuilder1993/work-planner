"""wp — WorkPlanner command-line interface.

Commands are grouped to match the web/Android UI surface. Auth uses the
backend's internal API key (X-Internal-Key) — see `wp config init`.
"""

from __future__ import annotations

import re
import sys
from typing import Any

import click

from workplanner_cli import config, render
from workplanner_cli.api import ApiError, Client

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


# ─── Context / client setup ──────────────────────────────────────────


class CliCtx:
    def __init__(self, client: Client, profile_name: str):
        self.client = client
        self.profile_name = profile_name


def _get_client(ctx: click.Context) -> Client:
    obj: CliCtx = ctx.obj
    return obj.client


def _resolve_task_id(client: Client, ref: str) -> str:
    """Accept either a full UUID or a unique prefix (>= 4 chars) and return
    the full ID. Searches via the /search endpoint with no query (returns
    all tasks) and filters in Python."""
    if UUID_RE.match(ref):
        return ref
    if len(ref) < 4:
        raise click.ClickException(f"ID prefix '{ref}' too short (need >= 4 chars).")
    all_tasks = client.search_tasks()
    matches = [t for t in all_tasks if t["id"].startswith(ref)]
    if not matches:
        raise click.ClickException(f"No task matches ID prefix '{ref}'.")
    if len(matches) > 1:
        listing = "\n".join(f"  {t['id']}  {t.get('title','')}" for t in matches[:8])
        raise click.ClickException(f"ID prefix '{ref}' is ambiguous; matches:\n{listing}")
    return matches[0]["id"]


# ─── Root group ──────────────────────────────────────────────────────


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--profile", "profile_name", help="Config profile name (defaults to file's default_profile).")
@click.option("--base-url", help="Override backend base URL.")
@click.option("--internal-key", help="Override internal API key.")
@click.pass_context
def main(ctx: click.Context, profile_name: str | None, base_url: str | None, internal_key: str | None) -> None:
    """WorkPlanner CLI. Run `wp config init` to set up."""
    # `wp config init` / `wp config show` don't need an authenticated client.
    if ctx.invoked_subcommand == "config":
        ctx.obj = None
        return
    try:
        profile = config.load(profile_name, base_url, internal_key)
    except FileNotFoundError as e:
        render.err(str(e))
        sys.exit(2)
    ctx.obj = CliCtx(Client(profile.base_url, profile.internal_key), profile.name)


# ─── config ──────────────────────────────────────────────────────────


@main.group(name="config")
def config_cmd() -> None:
    """Manage the CLI's config file (~/.config/workplanner/config.toml)."""


@config_cmd.command("init")
@click.option("--profile", "name", default="default", show_default=True, help="Profile name.")
@click.option("--base-url", prompt="Backend base URL (e.g. http://localhost:8001)")
@click.option("--internal-key", prompt="Internal API key", hide_input=True)
@click.option("--default/--no-default", "make_default", default=True, show_default=True)
def config_init(name: str, base_url: str, internal_key: str, make_default: bool) -> None:
    """Create or update a config profile."""
    path = config.save_profile(name, base_url, internal_key, make_default)
    render.info(f"Saved profile '{name}' to {path} (mode 0600).")


@config_cmd.command("show")
def config_show() -> None:
    """List configured profiles."""
    default, profiles = config.list_profiles()
    if not profiles:
        render.warn("No profiles configured. Run `wp config init`.")
        return
    for name, fields in profiles.items():
        marker = " [bold green](default)[/bold green]" if name == default else ""
        render.console.print(f"[bold]{name}[/bold]{marker}")
        render.console.print(f"  base_url     {fields.get('base_url', '')}")
        # Mask the key.
        key = fields.get("internal_key", "")
        masked = f"{key[:4]}…{key[-4:]}" if len(key) > 8 else "***"
        render.console.print(f"  internal_key {masked}")


# ─── ls / tree / show / search ───────────────────────────────────────


@main.command("ls")
@click.option("--status", "-s", help="Filter by status (e.g. PENDING, COMPLETED).")
@click.option("--all", "show_all", is_flag=True, help="Include all statuses, not just PENDING.")
@click.pass_context
def cmd_ls(ctx: click.Context, status: str | None, show_all: bool) -> None:
    """List top-level tasks (default: PENDING)."""
    client = _get_client(ctx)
    effective_status = None if show_all else (status or "PENDING")
    tasks = client.list_root_tasks(status=effective_status)
    title = f"Root tasks ({effective_status or 'all'})"
    render.task_table(tasks, title=title)


@main.command("tree")
@click.argument("task_ref")
@click.option("--depth", type=int, default=None, help="Maximum depth to traverse.")
@click.pass_context
def cmd_tree(ctx: click.Context, task_ref: str, depth: int | None) -> None:
    """Print the subtree rooted at the given task."""
    client = _get_client(ctx)
    task_id = _resolve_task_id(client, task_ref)
    root = client.get_task(task_id)

    # Cap recursion using a tracked depth via closure.
    seen = {root["id"]: 0}

    def children_fn(parent_id: str):
        current = seen[parent_id]
        if depth is not None and current >= depth:
            return []
        kids = client.list_children(parent_id)
        for k in kids:
            seen[k["id"]] = current + 1
        return kids

    tree = render.build_tree(root, children_fn)
    render.console.print(tree)


@main.command("show")
@click.argument("task_ref")
@click.option("--comments/--no-comments", default=True, show_default=True)
@click.pass_context
def cmd_show(ctx: click.Context, task_ref: str, comments: bool) -> None:
    """Show task details (and comments by default)."""
    client = _get_client(ctx)
    task_id = _resolve_task_id(client, task_ref)
    task = client.get_task(task_id)
    render.task_detail(task)
    if comments:
        render.console.print()
        render.console.rule("[bold]Comments[/bold]")
        cs = client.list_comments(task_id)
        render.comment_thread(cs)


@main.command("search")
@click.argument("query", required=False)
@click.option("--status", help="Filter by status.")
@click.option("--ai-status", help="Filter by AI status.")
@click.option("--algorithm", help="Filter by AI algorithm.")
@click.option("--ai/--no-ai", "ai_enabled", default=None, help="Filter by aiEnabled true/false.")
@click.pass_context
def cmd_search(
    ctx: click.Context,
    query: str | None,
    status: str | None,
    ai_status: str | None,
    algorithm: str | None,
    ai_enabled: bool | None,
) -> None:
    """Search tasks by title/description and/or filter by metadata."""
    client = _get_client(ctx)
    results = client.search_tasks(
        query=query,
        status=status,
        ai_status=ai_status,
        algorithm=algorithm,
        ai_enabled=ai_enabled,
    )
    render.task_table(results, title=f"Search: {query or '(all)'}")


# ─── add / set / close / reopen / rm ─────────────────────────────────


def _parse_due(value: str | None) -> int | None:
    if not value:
        return None
    from datetime import datetime
    try:
        dt = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise click.BadParameter(f"due date must be YYYY-MM-DD, got '{value}'")
    return int(dt.timestamp() * 1000)


@main.command("add")
@click.argument("title")
@click.option("--parent", "parent_ref", help="Parent task ID or prefix.")
@click.option("--description", "-d", default="", help="Task description.")
@click.option("--priority", "-p", type=int, default=0, show_default=True)
@click.option("--due", help="Due date (YYYY-MM-DD).")
@click.option("--ai/--no-ai", "ai_enabled", default=False, show_default=True)
@click.option("--algorithm", help="AI algorithm (sets props.algorithm; implies --ai).")
@click.pass_context
def cmd_add(
    ctx: click.Context,
    title: str,
    parent_ref: str | None,
    description: str,
    priority: int,
    due: str | None,
    ai_enabled: bool,
    algorithm: str | None,
) -> None:
    """Create a new task."""
    client = _get_client(ctx)
    body: dict[str, Any] = {
        "title": title,
        "description": description,
        "priority": priority,
        "aiEnabled": ai_enabled or bool(algorithm),
    }
    if parent_ref:
        body["parentId"] = _resolve_task_id(client, parent_ref)
    due_ts = _parse_due(due)
    if due_ts is not None:
        body["dueDate"] = due_ts
    if algorithm:
        body["props"] = {"algorithm": algorithm}
    task = client.create_task(body)
    render.info(f"Created {task['id']} — {task.get('title')}")


@main.command("set")
@click.argument("task_ref")
@click.option("--title")
@click.option("--description", "-d")
@click.option("--status")
@click.option("--priority", type=int)
@click.option("--due", help="Due date (YYYY-MM-DD); pass empty string to clear.")
@click.option("--parent", "parent_ref", help="New parent (or 'none' to detach).")
@click.option("--ai/--no-ai", "ai_enabled", default=None)
@click.option("--algorithm")
@click.pass_context
def cmd_set(
    ctx: click.Context,
    task_ref: str,
    title: str | None,
    description: str | None,
    status: str | None,
    priority: int | None,
    due: str | None,
    parent_ref: str | None,
    ai_enabled: bool | None,
    algorithm: str | None,
) -> None:
    """Patch fields on an existing task."""
    client = _get_client(ctx)
    task_id = _resolve_task_id(client, task_ref)
    fields: dict[str, Any] = {}
    if title is not None:
        fields["title"] = title
    if description is not None:
        fields["description"] = description
    if status is not None:
        fields["status"] = status.upper()
    if priority is not None:
        fields["priority"] = priority
    if due is not None:
        fields["dueDate"] = _parse_due(due) if due else None
    if parent_ref is not None:
        fields["parentId"] = None if parent_ref.lower() == "none" else _resolve_task_id(client, parent_ref)
    if ai_enabled is not None:
        fields["aiEnabled"] = ai_enabled
    if algorithm is not None:
        fields["props"] = {"algorithm": algorithm}

    if not fields:
        raise click.UsageError("Nothing to set — pass at least one --field.")

    task = client.update_task(task_id, fields)
    render.info(f"Updated {task['id']}.")


@main.command("close")
@click.argument("task_ref")
@click.pass_context
def cmd_close(ctx: click.Context, task_ref: str) -> None:
    """Close a task (status=CLOSED)."""
    client = _get_client(ctx)
    task_id = _resolve_task_id(client, task_ref)
    client.update_task(task_id, {"status": "CLOSED"})
    render.info(f"Closed {task_id}.")


@main.command("reopen")
@click.argument("task_ref")
@click.pass_context
def cmd_reopen(ctx: click.Context, task_ref: str) -> None:
    """Re-open a task (status=PENDING)."""
    client = _get_client(ctx)
    task_id = _resolve_task_id(client, task_ref)
    client.update_task(task_id, {"status": "PENDING"})
    render.info(f"Reopened {task_id}.")


# ─── comments ────────────────────────────────────────────────────────


def _read_text_arg(value: str | None) -> str:
    """If value is None or '-', read from stdin. Otherwise return as-is."""
    if value is None or value == "-":
        text = sys.stdin.read()
    else:
        text = value
    text = text.strip()
    if not text:
        raise click.UsageError("Empty comment text.")
    return text


@main.command("comments")
@click.argument("task_ref")
@click.pass_context
def cmd_comments(ctx: click.Context, task_ref: str) -> None:
    """List comments on a task (threaded)."""
    client = _get_client(ctx)
    task_id = _resolve_task_id(client, task_ref)
    cs = client.list_comments(task_id)
    render.comment_thread(cs)


@main.command("comment")
@click.argument("task_ref")
@click.argument("text", required=False)
@click.pass_context
def cmd_comment(ctx: click.Context, task_ref: str, text: str | None) -> None:
    """Add a comment to a task. Pass text as arg or pipe via stdin."""
    client = _get_client(ctx)
    task_id = _resolve_task_id(client, task_ref)
    body = _read_text_arg(text)
    c = client.create_comment(task_id, body)
    render.info(f"Posted {c['id']}.")


@main.command("reply")
@click.argument("task_ref")
@click.argument("parent_comment_id")
@click.argument("text", required=False)
@click.pass_context
def cmd_reply(ctx: click.Context, task_ref: str, parent_comment_id: str, text: str | None) -> None:
    """Reply to a comment under TASK_REF. PARENT_COMMENT_ID must be a full UUID
    (use `wp comments <task>` to see full IDs)."""
    if not UUID_RE.match(parent_comment_id):
        raise click.UsageError("PARENT_COMMENT_ID must be a full UUID.")
    client = _get_client(ctx)
    task_id = _resolve_task_id(client, task_ref)
    body = _read_text_arg(text)
    c = client.create_comment(task_id, body, parent_comment_id=parent_comment_id)
    render.info(f"Posted reply {c['id']}.")


@main.command("approve")
@click.argument("comment_id")
@click.pass_context
def cmd_approve(ctx: click.Context, comment_id: str) -> None:
    """Approve a PROPOSAL comment."""
    if not UUID_RE.match(comment_id):
        raise click.UsageError("Comment ID must be a full UUID.")
    client = _get_client(ctx)
    c = client.approve_proposal(comment_id)
    render.info(f"Approved {c['id']}.")


@main.command("deny")
@click.argument("comment_id")
@click.option("--feedback", "-m", default="", help="Optional reason/feedback.")
@click.pass_context
def cmd_deny(ctx: click.Context, comment_id: str, feedback: str) -> None:
    """Deny a PROPOSAL comment."""
    if not UUID_RE.match(comment_id):
        raise click.UsageError("Comment ID must be a full UUID.")
    client = _get_client(ctx)
    c = client.deny_proposal(comment_id, feedback=feedback)
    render.info(f"Denied {c['id']}.")


# ─── AI dispatch (mention helper) ────────────────────────────────────


VALID_PERSONAS = {"default", "engineer", "planner", "manager", "reviewer"}


@main.command("ai")
@click.argument("persona")
@click.argument("task_ref")
@click.argument("text", required=False)
@click.pass_context
def cmd_ai(ctx: click.Context, persona: str, task_ref: str, text: str | None) -> None:
    """Post an @ai-PERSONA mention comment to trigger the chat-poller.

    Example: wp ai engineer 8b3f… "fix the broken filter on the dashboard"

    Personas: default, engineer, planner, manager, reviewer.
    """
    persona = persona.lower()
    if persona not in VALID_PERSONAS:
        raise click.UsageError(f"Unknown persona '{persona}'. Choose from: {sorted(VALID_PERSONAS)}")
    client = _get_client(ctx)
    task_id = _resolve_task_id(client, task_ref)
    body = _read_text_arg(text)
    mention = f"@ai-{persona}" if persona != "default" else "@ai"
    c = client.create_comment(task_id, f"{mention} {body}")
    render.info(f"Posted {c['id']} with mention {mention} — poller will pick it up.")


# ─── work-items ──────────────────────────────────────────────────────


@main.group(name="work-items")
def work_items_cmd() -> None:
    """Inspect and manage WorkItems (the unit of AI execution).

    Every @ai-* mention becomes a WorkItem in the queue; the dispatcher
    picks it up, runs the AI, and writes the output back. See
    docs/WORK_ITEMS_DESIGN.md.
    """


@work_items_cmd.command("list")
@click.option("--task", "task_ref", help="Filter to one task (id or prefix).")
@click.option("--status", help="pending | dispatched | completed | failed | cancelled")
@click.option("--persona", help="engineer | planner | manager | reviewer | default")
@click.pass_context
def cmd_wi_list(
    ctx: click.Context,
    task_ref: str | None,
    status: str | None,
    persona: str | None,
) -> None:
    """List WorkItems, optionally filtered by task / status / persona."""
    client = _get_client(ctx)
    task_id = _resolve_task_id(client, task_ref) if task_ref else None
    items = client.list_work_items(task_id=task_id, status=status, persona=persona)
    title_bits: list[str] = []
    if task_id:
        title_bits.append(f"task={task_id[:8]}")
    if status:
        title_bits.append(f"status={status}")
    if persona:
        title_bits.append(f"persona={persona}")
    render.work_item_table(items, title=" ".join(title_bits) or "WorkItems")


@work_items_cmd.command("show")
@click.argument("work_item_id")
@click.pass_context
def cmd_wi_show(ctx: click.Context, work_item_id: str) -> None:
    """Show full WorkItem detail (assignment, output, attempts)."""
    if not UUID_RE.match(work_item_id):
        raise click.UsageError("WorkItem ID must be a full UUID.")
    client = _get_client(ctx)
    w = client.get_work_item(work_item_id)
    render.work_item_detail(w)


@work_items_cmd.command("cancel")
@click.argument("work_item_id")
@click.pass_context
def cmd_wi_cancel(ctx: click.Context, work_item_id: str) -> None:
    """Cancel a pending or failed WorkItem (terminal state)."""
    if not UUID_RE.match(work_item_id):
        raise click.UsageError("WorkItem ID must be a full UUID.")
    client = _get_client(ctx)
    w = client.update_work_item(work_item_id, {"status": "cancelled"})
    render.info(f"Cancelled WorkItem {w['id']}.")


@work_items_cmd.command("retry")
@click.argument("work_item_id")
@click.pass_context
def cmd_wi_retry(ctx: click.Context, work_item_id: str) -> None:
    """Reset retry_count to 0 on a failed WorkItem so the poller picks
    it up again. Only meaningful when status='failed' AND retry_count had
    hit max_retries."""
    if not UUID_RE.match(work_item_id):
        raise click.UsageError("WorkItem ID must be a full UUID.")
    client = _get_client(ctx)
    w = client.update_work_item(work_item_id, {"retryCount": 0})
    render.info(
        f"Reset retry_count on {w['id']} (status={w['status']}, "
        f"retries={w['retryCount']}/{w['maxRetries']})."
    )


# ─── knowledge ───────────────────────────────────────────────────────

CARD_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")


@main.group(name="knowledge")
def knowledge_cmd() -> None:
    """Manage the company knowledge base — searchable cards the AI personas
    read to ground their work. See docs/KNOWLEDGE_CARDS_DESIGN.md."""


def _read_content_arg(content: str | None) -> str:
    """Resolve card content from --content, an @file path, or stdin ('-')."""
    if content is None or content == "-":
        text = sys.stdin.read()
    elif content.startswith("@"):
        path = content[1:]
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            raise click.UsageError(f"cannot read {path}: {e}")
    else:
        text = content
    text = text.strip()
    if not text:
        raise click.UsageError("Empty card content.")
    return text


@knowledge_cmd.command("add")
@click.argument("card_id")
@click.option("--content", "-c", help="Card text, an @file path, or '-' for stdin (default).")
@click.option("--tag", "tags", multiple=True, help="Tag (repeatable).")
@click.pass_context
def cmd_kn_add(ctx: click.Context, card_id: str, content: str | None, tags: tuple[str, ...]) -> None:
    """Create a knowledge card. CARD_ID is a slug (lowercase, digits, hyphens)."""
    if not CARD_SLUG_RE.match(card_id):
        raise click.UsageError("CARD_ID must be a slug: lowercase letters, digits, hyphens (2-64 chars).")
    body = _read_content_arg(content)
    client = _get_client(ctx)
    card = client.create_knowledge_card(card_id, body, list(tags))
    render.info(f"Created card {card['id']} ({len(card.get('tags') or [])} tags).")


@knowledge_cmd.command("list")
@click.option("--tag", help="Filter by tag.")
@click.option("--all", "show_all", is_flag=True, help="Include invalid cards.")
@click.pass_context
def cmd_kn_list(ctx: click.Context, tag: str | None, show_all: bool) -> None:
    """List knowledge cards (valid only unless --all)."""
    client = _get_client(ctx)
    cards = client.list_knowledge_cards(tag=tag, include_invalid=show_all)
    title = f"Knowledge cards{f' (tag={tag})' if tag else ''}"
    render.knowledge_card_table(cards, title=title)


@knowledge_cmd.command("show")
@click.argument("card_id")
@click.pass_context
def cmd_kn_show(ctx: click.Context, card_id: str) -> None:
    """Show a card's full content."""
    client = _get_client(ctx)
    render.knowledge_card_detail(client.get_knowledge_card(card_id))


@knowledge_cmd.command("search")
@click.argument("query", required=False)
@click.option("--tag", help="Filter by tag.")
@click.option("--all", "show_all", is_flag=True, help="Include invalid cards.")
@click.option("--limit", type=int, help="Max results (default 10).")
@click.pass_context
def cmd_kn_search(ctx: click.Context, query: str | None, tag: str | None, show_all: bool, limit: int | None) -> None:
    """Full-text search over card content; filter by tag. Either or both."""
    client = _get_client(ctx)
    cards = client.search_knowledge_cards(query=query, tag=tag, include_invalid=show_all, limit=limit)
    render.knowledge_card_table(cards, title=f"Search: {query or '(tag-only)'}")


@knowledge_cmd.command("edit")
@click.argument("card_id")
@click.option("--content", "-c", help="New content, an @file path, or '-' for stdin.")
@click.option("--tag", "tags", multiple=True, help="Replace tags (repeatable). Pass none with --clear-tags to empty.")
@click.option("--clear-tags", is_flag=True, help="Set tags to empty.")
@click.option("--valid/--invalid", "is_valid", default=None, help="Mark the card valid or invalid.")
@click.pass_context
def cmd_kn_edit(
    ctx: click.Context,
    card_id: str,
    content: str | None,
    tags: tuple[str, ...],
    clear_tags: bool,
    is_valid: bool | None,
) -> None:
    """Edit a card's content, tags, or validity."""
    fields: dict[str, Any] = {}
    if content is not None:
        fields["content"] = _read_content_arg(content)
    if clear_tags:
        fields["tags"] = []
    elif tags:
        fields["tags"] = list(tags)
    if is_valid is not None:
        fields["isValid"] = is_valid
    if not fields:
        raise click.UsageError("Nothing to edit — pass --content, --tag/--clear-tags, or --valid/--invalid.")
    client = _get_client(ctx)
    card = client.update_knowledge_card(card_id, fields)
    render.info(f"Updated card {card['id']}.")


@knowledge_cmd.command("rm")
@click.argument("card_id")
@click.pass_context
def cmd_kn_rm(ctx: click.Context, card_id: str) -> None:
    """Delete a knowledge card."""
    client = _get_client(ctx)
    client.delete_knowledge_card(card_id)
    render.info(f"Deleted card {card_id}.")


# ─── Entry point ─────────────────────────────────────────────────────

# The click group is `main` while commands register below; the script
# entry-point wrapper is defined at the very end of this file (after all
# planner commands) so it doesn't shadow the group during decoration.


# ─── Planner: people ─────────────────────────────────────────────────


def _resolve_person_id(client: Client, ref: str) -> str:
    """Accept a UUID, an ID prefix, or an exact name."""
    if UUID_RE.match(ref):
        return ref
    people = client.list_people()
    matches = [p for p in people if p["id"].startswith(ref)]
    if not matches:
        matches = [p for p in people if p.get("name", "").lower() == ref.lower()]
    if not matches:
        raise click.ClickException(f"No person matches '{ref}'.")
    if len(matches) > 1:
        raise click.ClickException(f"'{ref}' is ambiguous.")
    return matches[0]["id"]


@main.group(name="person")
def person_cmd() -> None:
    """Manage the people pool (scheduling resources)."""


@person_cmd.command("add")
@click.argument("name")
@click.option("--hours", "hours_per_day", type=float, default=None, help="Working hours/day (default 8).")
@click.option("--email", default=None)
@click.pass_context
def person_add(ctx: click.Context, name: str, hours_per_day: float | None, email: str | None) -> None:
    """Add a person."""
    p = _get_client(ctx).create_person(name, hours_per_day, email)
    render.info(f"✓ Added {p['id'][:8]} — {p['name']} ({p['hoursPerDay']}h/day)")


@person_cmd.command("ls")
@click.pass_context
def person_ls(ctx: click.Context) -> None:
    """List people."""
    people = _get_client(ctx).list_people()
    if not people:
        render.warn("No people. Add one with `wp person add <name>`.")
        return
    for p in people:
        flag = "" if p.get("active", True) else " [inactive]"
        render.console.print(f"{p['id'][:8]}  {p['name']:<20} {p['hoursPerDay']}h/day{flag}")


@person_cmd.command("rm")
@click.argument("person_ref")
@click.pass_context
def person_rm(ctx: click.Context, person_ref: str) -> None:
    """Remove a person."""
    client = _get_client(ctx)
    pid = _resolve_person_id(client, person_ref)
    client.delete_person(pid)
    render.info(f"✓ Removed person {pid[:8]}")


@person_cmd.command("set-hours")
@click.argument("person_ref")
@click.argument("hours", type=float)
@click.pass_context
def person_set_hours(ctx: click.Context, person_ref: str, hours: float) -> None:
    """Set a person's working hours/day."""
    client = _get_client(ctx)
    pid = _resolve_person_id(client, person_ref)
    client.update_person(pid, {"hoursPerDay": hours})
    render.info(f"✓ {pid[:8]} now {hours}h/day")


@person_cmd.command("off")
@click.argument("person_ref")
@click.argument("start")
@click.argument("end")
@click.option("--hours", "hours_off", type=float, default=None, help="Hours off/day (omit = full day off).")
@click.option("--note", default=None)
@click.pass_context
def person_off(ctx: click.Context, person_ref: str, start: str, end: str,
               hours_off: float | None, note: str | None) -> None:
    """Add time off: PERSON START END (YYYY-MM-DD, inclusive)."""
    client = _get_client(ctx)
    pid = _resolve_person_id(client, person_ref)
    client.create_time_off(pid, start, end, hours_off, note)
    kind = f"{hours_off}h/day" if hours_off else "full days"
    render.info(f"✓ Time off {pid[:8]}: {start}..{end} ({kind})")


# ─── Planner: calendar + holidays ────────────────────────────────────


@main.group(name="calendar")
def calendar_cmd() -> None:
    """View/configure the shared calendar."""


@calendar_cmd.command("show")
@click.pass_context
def calendar_show(ctx: click.Context) -> None:
    """Show the calendar + holidays."""
    client = _get_client(ctx)
    c = client.get_calendar()
    render.console.print(f"Calendar {c['id'][:8]}  weekend bitmask={c['weekendDays']} (Mon=1..Sun=64; Sat+Sun=96)")
    hols = client.list_holidays(c["id"])
    if hols:
        render.console.print("Holidays:")
        for h in hols:
            render.console.print(f"  {h['day']}  {h.get('name') or ''}  ({h['id'][:8]})")


@calendar_cmd.command("weekends")
@click.argument("bitmask", type=int)
@click.pass_context
def calendar_weekends(ctx: click.Context, bitmask: int) -> None:
    """Set weekend bitmask (Mon=1..Sun=64; Sat+Sun=96)."""
    c = _get_client(ctx).upsert_calendar(bitmask)
    render.info(f"✓ weekend_days = {c['weekendDays']}")


@calendar_cmd.group("holiday")
def holiday_cmd() -> None:
    """Manage company holidays."""


@holiday_cmd.command("add")
@click.argument("day")
@click.option("--name", default=None)
@click.pass_context
def holiday_add(ctx: click.Context, day: str, name: str | None) -> None:
    """Add a holiday (YYYY-MM-DD)."""
    client = _get_client(ctx)
    c = client.get_calendar()
    h = client.create_holiday(c["id"], day, name)
    render.info(f"✓ Holiday {day} added ({h['id'][:8]})")


@holiday_cmd.command("rm")
@click.argument("holiday_id")
@click.pass_context
def holiday_rm(ctx: click.Context, holiday_id: str) -> None:
    """Remove a holiday by id."""
    _get_client(ctx).delete_holiday(holiday_id)
    render.info(f"✓ Removed holiday {holiday_id[:8]}")


# ─── Planner: dependencies ───────────────────────────────────────────


@main.group(name="dep")
def dep_cmd() -> None:
    """Manage task dependencies (blocked-by)."""


@dep_cmd.command("add")
@click.argument("task_ref")
@click.argument("blocker_ref")
@click.pass_context
def dep_add(ctx: click.Context, task_ref: str, blocker_ref: str) -> None:
    """Make TASK blocked-by BLOCKER."""
    client = _get_client(ctx)
    tid = _resolve_task_id(client, task_ref)
    bid = _resolve_task_id(client, blocker_ref)
    try:
        client.create_dependency(tid, bid)
    except ApiError as e:
        if e.status == 409:
            raise click.ClickException("That dependency would create a cycle.")
        raise
    render.info(f"✓ {tid[:8]} blocked by {bid[:8]}")


@dep_cmd.command("ls")
@click.argument("task_ref")
@click.pass_context
def dep_ls(ctx: click.Context, task_ref: str) -> None:
    """List a task's dependencies."""
    client = _get_client(ctx)
    tid = _resolve_task_id(client, task_ref)
    deps = client.list_dependencies(tid)
    if not deps:
        render.console.print("(no dependencies)")
        return
    for d in deps:
        render.console.print(f"  blocked by {d['dependsOnId'][:8]}  (dep {d['id'][:8]})")


@dep_cmd.command("rm")
@click.argument("dependency_id")
@click.pass_context
def dep_rm(ctx: click.Context, dependency_id: str) -> None:
    """Remove a dependency by id."""
    _get_client(ctx).delete_dependency(dependency_id)
    render.info(f"✓ Removed dependency {dependency_id[:8]}")


# ─── Planner: plan inputs + schedule ─────────────────────────────────


@main.command("plan")
@click.argument("task_ref")
@click.option("--estimate", type=float, default=None, help="Estimate hours (sets duration).")
@click.option("--assignee", default=None, help="Person ref; '' to clear.")
@click.option("--buffer", "buffer_hours", type=float, default=None, help="Buffer hours (parent reserve).")
@click.pass_context
def cmd_plan(ctx: click.Context, task_ref: str, estimate: float | None,
             assignee: str | None, buffer_hours: float | None) -> None:
    """Set planner inputs on a task: --estimate / --assignee / --buffer."""
    client = _get_client(ctx)
    tid = _resolve_task_id(client, task_ref)
    if estimate is not None:
        client.update_task(tid, {"duration": estimate})
    fields: dict[str, Any] = {}
    if assignee is not None:
        fields["assigneeId"] = "" if assignee == "" else _resolve_person_id(client, assignee)
    if buffer_hours is not None:
        fields["bufferHours"] = buffer_hours
    if fields:
        client.update_task_planner(tid, fields)
    render.info(f"✓ Updated plan for {tid[:8]}")


@main.command("schedule")
@click.option("--start", default=None, help="Project start YYYY-MM-DD (default today).")
@click.option("--csv", "as_csv", is_flag=True, help="Output CSV (Google-Sheets-import-ready).")
@click.pass_context
def cmd_schedule(ctx: click.Context, start: str | None, as_csv: bool) -> None:
    """Generate and show the execution schedule."""
    rows = _get_client(ctx).get_schedule(start)
    if as_csv:
        import csv
        w = csv.writer(sys.stdout)
        w.writerow(["task_id", "title", "assignee", "estimate_hours", "start", "end", "on_critical_path", "status"])
        for r in rows:
            w.writerow([r["taskId"], r["title"], r.get("assigneeName") or "",
                        r.get("estimateHours") or "", r.get("start") or "", r.get("end") or "",
                        r.get("onCriticalPath"), r.get("status")])
        return
    if not rows:
        render.warn("Nothing to schedule. Add tasks with estimates + assignees.")
        return
    for r in rows:
        star = "★" if r.get("onCriticalPath") else " "
        sched = f"{r.get('start') or '—'} → {r.get('end') or '—'}"
        who = r.get("assigneeName") or "-"
        render.console.print(f"{star} {sched:<24} {who:<16} {r['title']}")


# ─── Entry point (defined last so it doesn't shadow the group above) ──

_cli_group = main  # the click.Group with all commands registered


def main() -> None:  # type: ignore[no-redef]
    """Console-script entry point (resolves to `wp` via pyproject)."""
    try:
        _cli_group()
    except ApiError as e:
        render.err(f"{e}")
        if e.body:
            render.console.print(f"[dim]{e.body}[/dim]")
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
