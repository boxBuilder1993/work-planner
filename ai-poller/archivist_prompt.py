"""Build the prompt payload for an archivist dispatch.

The archivist is a knowledge-base maintenance agent. Unlike a chat dispatch,
it is not replying to anyone — it is triggered by a *new comment* and its job
is to decide whether the company knowledge cards need updating in light of
everything that has happened on the task.

This reuses `chat_prompt`'s context renderer (task + ancestors + thread +
the triggering comment + ai_context) and swaps in an archivist-specific
`<your_task>` instruction. Pure function — no I/O.
"""

from __future__ import annotations

from typing import Any

from chat_prompt import PromptPayload, _render_context_xml
from models import CommentEntity, TaskEntity
from persona_registry import CompiledPersona

DEFAULT_THREAD_LIMIT = 40


_ARCHIVIST_TASK = """\
<your_task>
A new comment (the one tagged triggering="true" above) was just added to this
task. Your job is to keep the company knowledge base correct and current.

Read the ENTIRE task context and thread above — not just the triggering
comment. Then decide whether any durable, reusable knowledge has been settled,
changed, or invalidated that the knowledge base should reflect.

Work in this order:
1. Identify candidate knowledge — a settled decision, a convention, a domain
   rule, a non-obvious gotcha, an architectural fact. Ignore task-specific
   status, chit-chat, and anything ephemeral.
2. SEARCH the existing cards (`wp knowledge search`, `wp knowledge list`)
   before writing anything. Determine whether a card already covers it.
3. Then do exactly one of:
   - CREATE a new card (`wp knowledge add`) if the knowledge is durable and
     nothing covers it.
   - UPDATE an existing card (`wp knowledge edit`) if a card covers it but is
     now incomplete, out of date, or contradicted.
   - DO NOTHING — this is the common case. Most comments contain no durable
     knowledge, or it is already captured. Adding low-value or duplicate cards
     pollutes the base; when in doubt, do nothing.

When you create or update a card:
- Cite sources INLINE in the card content: the source task id and the key
  comment id(s) this knowledge came from (e.g. "Source: task <id>, comment
  <id>"). Cross-link related cards by their slug so personas can follow the
  trail.
- Tag every card you touch with `archivist` plus topical tags.
- Keep the content tight and self-contained — a reader should get the fact
  without chasing the references, but the references let them dig deeper.

You are the only writer to the knowledge base. Be a careful curator, not a
prolific one. Return a short JSON summary of what you did (created / updated /
nothing, with card ids and why).
</your_task>"""


def build_archivist_prompt(
    *,
    task: TaskEntity,
    ancestors: list[TaskEntity],
    thread: list[CommentEntity],
    trigger: CommentEntity,
    persona: CompiledPersona,
    ai_context: dict[str, Any] | None,
    thread_limit: int = DEFAULT_THREAD_LIMIT,
) -> PromptPayload:
    """Assemble the archivist's prompt from the persona + task context.

    `trigger` is the comment that fired this review; it is rendered as the
    `triggering="true"` mention so the agent knows what's new, but the
    instruction makes clear the whole thread is in scope.
    """
    context_xml = _render_context_xml(
        task=task,
        ancestors=ancestors,
        thread=thread[-thread_limit:] if thread_limit else thread,
        mention=trigger,
        ai_context=ai_context or {},
    )
    return PromptPayload(
        system=persona.body,
        user=context_xml + "\n\n" + _ARCHIVIST_TASK,
        model=persona.model,
        allowed_tools=list(persona.tools),
    )
