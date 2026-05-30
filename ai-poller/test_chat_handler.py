"""Unit tests for chat_handler — the WorkItem-enqueueing scanner.

Most of the old dispatch logic moved to work_item_handler; tests for that
live in test_work_item_handler.py. What stays here: the pure dedup helper
and the persona routing helper.
"""

from __future__ import annotations

import unittest

from chat_handler import ChatHandler, _payload_to_prompt_context
from chat_prompt import PromptPayload
from models import CommentEntity
from persona_registry import CompiledPersona


def _comment(
    id: str,
    *,
    task_id: str = "task-1",
    text: str = "hello",
    created_at: int = 0,
    props: dict | None = None,
    created_by: str = "user",
) -> CommentEntity:
    return CommentEntity(
        id=id,
        task_id=task_id,
        text=text,
        created_at=created_at,
        created_by=created_by,
        props=props or {},
    )


# ─── _pick_one_per_task ───────────────────────────────────────────────────


class TestPickOnePerTask(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(ChatHandler._pick_one_per_task([]), [])

    def test_one_per_task_unchanged(self):
        a = _comment("a", task_id="T-1", created_at=10)
        b = _comment("b", task_id="T-2", created_at=20)
        out = ChatHandler._pick_one_per_task([a, b])
        self.assertEqual({c.id for c in out}, {"a", "b"})

    def test_same_task_oldest_wins(self):
        old = _comment("old", task_id="T-1", created_at=5)
        new = _comment("new", task_id="T-1", created_at=50)
        out = ChatHandler._pick_one_per_task([new, old])
        self.assertEqual([c.id for c in out], ["old"])

    def test_mixed_tasks_each_keeps_oldest(self):
        c1_old = _comment("c1_old", task_id="T-1", created_at=1)
        c1_new = _comment("c1_new", task_id="T-1", created_at=100)
        c2_old = _comment("c2_old", task_id="T-2", created_at=2)
        c2_new = _comment("c2_new", task_id="T-2", created_at=200)
        out = ChatHandler._pick_one_per_task([c1_new, c2_new, c1_old, c2_old])
        self.assertEqual({c.id for c in out}, {"c1_old", "c2_old"})
        self.assertEqual([c.id for c in out], ["c1_old", "c2_old"])


# ─── _route_persona ───────────────────────────────────────────────────────


class TestRoutePersona(unittest.TestCase):
    def test_bare_at_ai_routes_to_default(self):
        p = ChatHandler._route_persona("@ai please help")
        self.assertEqual(p.name, "default")

    def test_explicit_engineer_routes_to_engineer(self):
        p = ChatHandler._route_persona("@ai-engineer fix this bug")
        self.assertEqual(p.name, "engineer")

    def test_first_mention_wins(self):
        # The poller routes on the first @ai-* mention in the text. Subsequent
        # mentions are visible to the persona as context but don't dispatch.
        p = ChatHandler._route_persona("@ai-manager review then @ai-engineer fix")
        self.assertEqual(p.name, "manager")

    def test_unknown_persona_falls_back_to_default(self):
        p = ChatHandler._route_persona("@ai-nonexistent help")
        self.assertEqual(p.name, "default")


# ─── _payload_to_prompt_context ───────────────────────────────────────────


class TestPayloadToPromptContext(unittest.TestCase):
    """The shape persisted on work_items.prompt_context. Stable shape so the
    work_item_handler can rebuild the proxy call without re-rendering."""

    def _payload(self) -> PromptPayload:
        return PromptPayload(
            system="SYSTEM_PROMPT_BODY",
            user="USER_PROMPT_BODY",
            model="claude-sonnet-4-6",
            allowed_tools=["Read", "Write"],
        )

    def _persona(self, **overrides) -> CompiledPersona:
        defaults = dict(
            name="engineer", version=2, model="claude-sonnet-4-6",
            tools=["Read"], max_turns=100,
        )
        defaults.update(overrides)
        return CompiledPersona(**defaults)

    def test_contains_all_required_keys(self):
        ctx = _payload_to_prompt_context(self._payload(), self._persona())
        for key in ("system", "user", "model", "allowed_tools",
                    "max_turns", "persona_name", "persona_version"):
            self.assertIn(key, ctx)

    def test_max_turns_from_persona(self):
        ctx = _payload_to_prompt_context(self._payload(), self._persona(max_turns=100))
        self.assertEqual(ctx["max_turns"], 100)

    def test_persona_name_and_version_stamped(self):
        ctx = _payload_to_prompt_context(
            self._payload(), self._persona(name="manager", version=2)
        )
        self.assertEqual(ctx["persona_name"], "manager")
        self.assertEqual(ctx["persona_version"], 2)

    def test_allowed_tools_is_a_copy(self):
        # Mutating the returned list shouldn't affect the source payload.
        ctx = _payload_to_prompt_context(self._payload(), self._persona())
        ctx["allowed_tools"].append("extra")
        # Build a fresh one — extra shouldn't be there.
        fresh = _payload_to_prompt_context(self._payload(), self._persona())
        self.assertNotIn("extra", fresh["allowed_tools"])


if __name__ == "__main__":
    unittest.main()
