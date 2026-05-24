"""Build the prompt payload for a chat dispatch.

Pure function — no I/O, no side effects. Takes the static persona (already
compiled with shared fragments inlined) plus the dynamic per-invocation
context (task, ancestors, thread, ai_context, mention, workspace_path) and
returns a `PromptPayload` ready for the proxy to translate into a
`claude -p` invocation.

See: docs/CHAT_DESIGN.md (Per-invocation context section).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from xml.sax.saxutils import escape, quoteattr

import yaml

from models import CommentEntity, TaskEntity
from persona_registry import CompiledPersona


# Default cap on how many thread comments to include (oldest-first).
DEFAULT_THREAD_LIMIT = 20


@dataclass
class PromptPayload:
    """Everything the proxy needs to invoke `claude -p`."""

    system: str                  # → --append-system-prompt
    user: str                    # → final positional prompt argument
    model: str                   # → --model
    allowed_tools: list[str] = field(default_factory=list)   # → --allowed-tools
    cwd: str = ""                # → subprocess cwd (workspace path)


def build_prompt(
    *,
    task: TaskEntity,
    ancestors: list[TaskEntity],
    thread: list[CommentEntity],
    mention: CommentEntity,
    persona: CompiledPersona,
    ai_context: dict[str, Any] | None,
    workspace_path: str,
    thread_limit: int = DEFAULT_THREAD_LIMIT,
) -> PromptPayload:
    """Assemble a complete `PromptPayload` from persona + dynamic context.

    Args:
        task: the task this mention is on
        ancestors: parent chain, root-first (excluding `task` itself)
        thread: all comments on `task`, oldest-first (excluding `mention` itself)
        mention: the @ai-* comment that triggered this dispatch
        persona: the routed `CompiledPersona`
        ai_context: current `task.props.ai_context` (may be None or empty)
        workspace_path: absolute path on the Mac for AI work
        thread_limit: keep at most this many thread comments (oldest first dropped)

    The system prompt is `persona.body` verbatim (already has shared fragments
    inlined). The user message is an XML-tagged context block followed by a
    short `<your_task>` instruction.
    """
    context_xml = _render_context_xml(
        task=task,
        ancestors=ancestors,
        thread=thread[-thread_limit:] if thread_limit else thread,
        mention=mention,
        ai_context=ai_context or {},
        workspace_path=workspace_path,
    )

    user_msg = (
        context_xml
        + "\n\n<your_task>\n"
        + "Respond to the @ai mention above. Follow the persona instructions "
        + "and the output contract. Return a single JSON object as your final "
        + "assistant message.\n"
        + "</your_task>"
    )

    return PromptPayload(
        system=persona.body,
        user=user_msg,
        model=persona.model,
        allowed_tools=list(persona.tools),
        cwd=workspace_path,
    )


# ─── Internal renderers ───────────────────────────────────────────────────


def _render_context_xml(
    *,
    task: TaskEntity,
    ancestors: list[TaskEntity],
    thread: list[CommentEntity],
    mention: CommentEntity,
    ai_context: dict[str, Any],
    workspace_path: str,
) -> str:
    parts = ["<context>"]
    parts.append(_render_task(task))
    if ancestors:
        parts.append(_render_ancestors(ancestors))
    parts.append(_render_workspace(workspace_path))
    if ai_context:
        parts.append(_render_ai_context(ai_context))
    parts.append(_render_thread(thread))
    parts.append(_render_mention(mention))
    parts.append("</context>")
    return "\n\n".join(parts)


def _render_task(task: TaskEntity) -> str:
    return (
        "  <task>\n"
        f"    <id>{escape(task.id)}</id>\n"
        f"    <title>{escape(task.title)}</title>\n"
        f"    <description>{escape(task.description)}</description>\n"
        "  </task>"
    )


def _render_ancestors(ancestors: list[TaskEntity]) -> str:
    lines = ["  <ancestor_chain>"]
    for a in ancestors:
        lines.append(
            f"    <task id={quoteattr(a.id)} title={quoteattr(a.title)} />"
        )
    lines.append("  </ancestor_chain>")
    return "\n".join(lines)


def _render_workspace(workspace_path: str) -> str:
    if not workspace_path:
        return (
            "  <workspace>\n"
            "    <status>not_yet_created</status>\n"
            "  </workspace>"
        )
    return (
        "  <workspace>\n"
        f"    <path>{escape(workspace_path)}</path>\n"
        "  </workspace>"
    )


def _render_ai_context(ai_context: dict[str, Any]) -> str:
    yaml_str = yaml.safe_dump(
        ai_context, sort_keys=False, default_flow_style=False
    ).rstrip()
    indented = "\n".join("      " + line for line in yaml_str.splitlines())
    return (
        "  <ai_context>\n"
        f"{indented}\n"
        "  </ai_context>"
    )


def _render_thread(thread: list[CommentEntity]) -> str:
    if not thread:
        return (
            "  <thread excerpt=\"empty — this mention is the first comment on this task\">\n"
            "  </thread>"
        )
    lines = [
        f"  <thread excerpt=\"last {len(thread)} comments, oldest first\">"
    ]
    for c in thread:
        lines.append(_render_comment_open_tag(c, indent="    "))
        text = escape(c.text)
        for line in text.splitlines() or [""]:
            lines.append(f"      {line}")
        lines.append("    </comment>")
    lines.append("  </thread>")
    return "\n".join(lines)


def _render_mention(mention: CommentEntity) -> str:
    lines = [
        "  <mention triggering=\"true\">",
        _render_comment_open_tag(mention, indent="    "),
    ]
    text = escape(mention.text)
    for line in text.splitlines() or [""]:
        lines.append(f"      {line}")
    lines.append("    </comment>")
    lines.append("  </mention>")
    return "\n".join(lines)


def _render_comment_open_tag(c: CommentEntity, indent: str) -> str:
    return (
        f"{indent}<comment "
        f"id={quoteattr(c.id)} "
        f"created_by={quoteattr(c.created_by)} "
        f"created_at={quoteattr(_iso(c.created_at))}>"
    )


def _iso(epoch_ms: int) -> str:
    """Format an epoch-millis timestamp as ISO-8601 UTC."""
    if not epoch_ms:
        return ""
    dt = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
    # Drop microseconds for compactness; keep `Z` suffix for clarity.
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
