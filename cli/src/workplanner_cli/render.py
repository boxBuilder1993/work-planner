"""Rendering helpers — tables, trees, comment threads.

All the printing logic lives here so cli.py reads as a thin orchestration
layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from rich.console import Console
from rich.table import Table
from rich.tree import Tree

console = Console()


STATUS_COLORS = {
    "PENDING": "yellow",
    "IN_PROGRESS": "cyan",
    "COMPLETED": "green",
    "CLOSED": "green",
    "BLOCKED": "red",
    "CANCELLED": "dim",
    "DELETED": "dim red",
}


def _short_id(task_id: str) -> str:
    return task_id[:8]


def _fmt_ts(value: int | None) -> str:
    if not value:
        return "-"
    # Backend ts are millis.
    secs = value / 1000 if value > 10_000_000_000 else value
    return datetime.fromtimestamp(secs, tz=timezone.utc).astimezone().strftime("%Y-%m-%d")


def _status_cell(status: str) -> str:
    color = STATUS_COLORS.get(status, "white")
    return f"[{color}]{status}[/{color}]"


def task_table(tasks: Iterable[dict], title: str | None = None) -> None:
    table = Table(title=title, show_lines=False, header_style="bold")
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Title")
    table.add_column("Status", no_wrap=True)
    table.add_column("Pri", justify="right", no_wrap=True)
    table.add_column("Due", no_wrap=True)
    table.add_column("AI", no_wrap=True)

    for t in tasks:
        ai_marker = ""
        if t.get("aiEnabled"):
            algo = (t.get("props") or {}).get("algorithm", "")
            ai_marker = f"[magenta]✓[/magenta] {algo}" if algo else "[magenta]✓[/magenta]"
        table.add_row(
            _short_id(t["id"]),
            t.get("title", ""),
            _status_cell(t.get("status", "")),
            str(t.get("priority", "")),
            _fmt_ts(t.get("dueDate")),
            ai_marker,
        )
    console.print(table)


def task_detail(task: dict) -> None:
    console.rule(f"[bold]{task.get('title','(no title)')}[/bold]")
    fields = [
        ("ID", task["id"]),
        ("Status", _status_cell(task.get("status", ""))),
        ("Priority", str(task.get("priority", ""))),
        ("Parent", task.get("parentId") or "-"),
        ("Due", _fmt_ts(task.get("dueDate"))),
        ("Planned", _fmt_ts(task.get("plannedTime"))),
        ("Duration", str(task.get("duration") or "-")),
        ("AI", "yes" if task.get("aiEnabled") else "no"),
        ("Created", _fmt_ts(task.get("createdAt"))),
        ("Updated", _fmt_ts(task.get("updatedAt"))),
    ]
    for label, value in fields:
        console.print(f"  [bold]{label:9}[/bold] {value}")
    desc = task.get("description") or ""
    if desc.strip():
        console.print()
        console.print("[bold]Description[/bold]")
        console.print(desc)
    props = task.get("props") or {}
    if props:
        console.print()
        console.print(f"[bold]Props[/bold] [dim]{props}[/dim]")


def build_tree(root: dict, children_fn) -> Tree:
    """Recursively build a rich.Tree starting from `root`. `children_fn(id)`
    returns the direct children dicts. Caller controls depth limiting by
    short-circuiting children_fn if needed."""
    label = f"[dim]{_short_id(root['id'])}[/dim] {root.get('title','')} {_status_cell(root.get('status',''))}"
    node = Tree(label)
    for child in children_fn(root["id"]):
        node.add(_subtree(child, children_fn))
    return node


def _subtree(task: dict, children_fn) -> Tree:
    label = f"[dim]{_short_id(task['id'])}[/dim] {task.get('title','')} {_status_cell(task.get('status',''))}"
    sub = Tree(label)
    for child in children_fn(task["id"]):
        sub.add(_subtree(child, children_fn))
    return sub


def comment_thread(comments: list[dict]) -> None:
    """Render comments as a threaded tree based on parentCommentId."""
    by_parent: dict[str | None, list[dict]] = {}
    for c in comments:
        by_parent.setdefault(c.get("parentCommentId"), []).append(c)

    roots = by_parent.get(None, [])
    if not roots:
        console.print("[dim]No comments.[/dim]")
        return

    for root in roots:
        _print_comment(root, by_parent, depth=0)


def _print_comment(c: dict, by_parent: dict, depth: int) -> None:
    indent = "  " * depth
    short = _short_id(c["id"])
    author = c.get("createdBy", "user")
    author_style = "magenta" if author != "user" else "cyan"
    ts = _fmt_ts(c.get("createdAt"))
    ctype = c.get("commentType", "COMMENT")
    badge = ""
    if ctype == "PROPOSAL":
        status = c.get("proposalStatus") or "PENDING"
        color = {"PENDING": "yellow", "APPROVED": "green", "DENIED": "red"}.get(status, "white")
        badge = f" [{color}][PROPOSAL/{status}][/{color}]"
    console.print(
        f"{indent}[dim]{short}[/dim] [{author_style}]{author}[/{author_style}] [dim]{ts}[/dim]{badge}"
    )
    text = c.get("text", "").rstrip()
    for line in text.splitlines() or [""]:
        console.print(f"{indent}  {line}")
    for child in by_parent.get(c["id"], []):
        _print_comment(child, by_parent, depth + 1)


WORK_ITEM_STATUS_COLORS = {
    "pending": "yellow",
    "dispatched": "cyan",
    "completed": "green",
    "failed": "red",
    "cancelled": "dim",
}


def work_item_table(items: list[dict], title: str | None = None) -> None:
    table = Table(title=title, show_lines=False, header_style="bold")
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Task", style="dim", no_wrap=True)
    table.add_column("Persona", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Retries", justify="right", no_wrap=True)
    table.add_column("Created", no_wrap=True)
    for w in items:
        status = w.get("status", "")
        color = WORK_ITEM_STATUS_COLORS.get(status, "white")
        table.add_row(
            _short_id(w["id"]),
            _short_id(w.get("taskId", "") or ""),
            w.get("targetPersona", "") or "-",
            f"[{color}]{status}[/{color}]",
            f"{w.get('retryCount', 0)}/{w.get('maxRetries', 5)}",
            _fmt_ts(w.get("createdAt")),
        )
    console.print(table)


def work_item_detail(w: dict) -> None:
    status = w.get("status", "")
    color = WORK_ITEM_STATUS_COLORS.get(status, "white")
    console.rule(
        f"[bold]WorkItem {_short_id(w['id'])}[/bold]  [{color}]{status}[/{color}]"
    )
    fields = [
        ("ID", w["id"]),
        ("Task", w.get("taskId", "")),
        ("Trigger", w.get("triggeringCommentId") or "-"),
        ("Persona", w.get("targetPersona", "")),
        ("Retries", f"{w.get('retryCount', 0)}/{w.get('maxRetries', 5)}"),
        ("Created", _fmt_ts(w.get("createdAt"))),
        ("Dispatched", _fmt_ts(w.get("dispatchedAt"))),
        ("Completed", _fmt_ts(w.get("completedAt"))),
    ]
    for label, value in fields:
        console.print(f"  [bold]{label:11}[/bold] {value}")
    if w.get("lastError"):
        console.print()
        console.print("[bold red]Last error[/bold red]")
        console.print(f"  {w['lastError'][:500]}")
    attempts = w.get("attempts") or []
    if attempts:
        console.print()
        console.print(f"[bold]Attempts ({len(attempts)})[/bold]")
        for i, a in enumerate(attempts, 1):
            err = a.get("error") or ""
            err_lines = err.splitlines()
            console.print(
                f"  [bold]{i}.[/bold] {_fmt_ts(a.get('at'))}  "
                f"cost={a.get('costUsd', '-')}  "
                f"duration={a.get('durationMs', '-')}ms"
            )
            if err_lines:
                console.print(f"     [red]{err_lines[0][:200]}[/red]")
                # Print remaining lines indented; full content (no truncation)
                # so raw model output embedded in the error is readable.
                for line in err_lines[1:]:
                    console.print(f"     [dim]{line}[/dim]")
    output = w.get("output") or {}
    if output:
        console.print()
        console.print("[bold]Output[/bold]")
        reply = (output.get("reply_text") or "").strip()
        if reply:
            console.print("  [dim]reply_text[/dim]")
            for line in reply.splitlines()[:20]:
                console.print(f"    {line}")
        artifacts = output.get("artifacts") or {}
        if artifacts:
            console.print("  [dim]artifacts[/dim]")
            import json as _json
            for line in _json.dumps(artifacts, indent=2).splitlines()[:30]:
                console.print(f"    {line}")


def knowledge_card_table(cards: Iterable[dict], title: str | None = None) -> None:
    cards = list(cards)
    # When the output is piped (an AI persona running `wp knowledge search`
    # via its shell, or any non-interactive caller), render FULL card content
    # — a truncated table would hide the answer and force a second `show`
    # call. Interactive terminals get the compact table.
    if not console.is_terminal:
        if not cards:
            print("(no matching cards)")
            return
        for c in cards:
            tags = " ".join(c.get("tags") or [])
            flag = "" if c.get("isValid", True) else " [INVALID]"
            print(f"# {c['id']}{flag}  [tags: {tags}]")
            print(c.get("content") or "")
            print()
        return

    table = Table(title=title, show_lines=False, header_style="bold")
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Valid", no_wrap=True)
    table.add_column("Tags", no_wrap=True)
    table.add_column("Content")
    for c in cards:
        valid = "[green]✓[/green]" if c.get("isValid", True) else "[red]✗[/red]"
        tags = " ".join(c.get("tags") or [])
        # Single-line preview of content.
        content = (c.get("content") or "").replace("\n", " ")
        preview = content[:80] + ("…" if len(content) > 80 else "")
        table.add_row(c["id"], valid, f"[cyan]{tags}[/cyan]", preview)
    console.print(table)


def knowledge_card_detail(c: dict) -> None:
    valid = "[green]valid[/green]" if c.get("isValid", True) else "[red]invalid[/red]"
    console.rule(f"[bold]{c['id']}[/bold]  {valid}")
    tags = c.get("tags") or []
    if tags:
        console.print(f"  [bold]Tags[/bold]     [cyan]{' '.join(tags)}[/cyan]")
    console.print(f"  [bold]Created[/bold]  {_fmt_ts(c.get('createdAt'))}")
    console.print(f"  [bold]Updated[/bold]  {_fmt_ts(c.get('updatedAt'))}")
    console.print()
    console.print(c.get("content") or "")


def info(msg: str) -> None:
    console.print(f"[green]✓[/green] {msg}")


def warn(msg: str) -> None:
    console.print(f"[yellow]![/yellow] {msg}")


def err(msg: str) -> None:
    console.print(f"[red]✗[/red] {msg}", style="bold")
