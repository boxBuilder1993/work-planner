"""Unit tests for chat_prompt.build_prompt."""

from __future__ import annotations

import unittest

from chat_prompt import (
    DEFAULT_THREAD_LIMIT,
    PromptPayload,
    build_prompt,
)
from models import CommentEntity, TaskEntity
from persona_registry import CompiledPersona


# ─── Builders ─────────────────────────────────────────────────────────────


def _task(
    id: str = "task-1",
    title: str = "Add user auth",
    description: str = "JWT-based auth for the API.",
) -> TaskEntity:
    return TaskEntity(id=id, title=title, description=description)


def _comment(
    id: str = "c-1",
    text: str = "Hello",
    created_by: str = "user",
    created_at: int = 1_700_000_000_000,
) -> CommentEntity:
    return CommentEntity(
        id=id, text=text, created_by=created_by, created_at=created_at
    )


def _persona(
    name: str = "default",
    body: str = "PERSONA SYSTEM PROMPT",
    model: str = "claude-sonnet-4-6",
    tools: list[str] | None = None,
) -> CompiledPersona:
    return CompiledPersona(
        name=name,
        body=body,
        model=model,
        tools=tools if tools is not None else ["get_task", "add_comment"],
    )


# ─── Tests ────────────────────────────────────────────────────────────────


class TestPromptPayloadShape(unittest.TestCase):
    """Top-level fields on the returned PromptPayload."""

    def setUp(self) -> None:
        self.task = _task()
        self.mention = _comment(id="m-1", text="@ai please help")
        self.persona = _persona(model="claude-opus-4-7", tools=["run_command"])

    def _build(self, **kwargs) -> PromptPayload:
        defaults = dict(
            task=self.task,
            ancestors=[],
            thread=[],
            mention=self.mention,
            persona=self.persona,
            ai_context=None,
        )
        defaults.update(kwargs)
        return build_prompt(**defaults)

    def test_system_is_persona_body_verbatim(self) -> None:
        self.persona = _persona(body="EXACT_PERSONA_BODY")
        p = self._build()
        self.assertEqual(p.system, "EXACT_PERSONA_BODY")

    def test_model_propagated(self) -> None:
        p = self._build()
        self.assertEqual(p.model, "claude-opus-4-7")

    def test_allowed_tools_propagated_as_copy(self) -> None:
        p = self._build()
        self.assertEqual(p.allowed_tools, ["run_command"])
        # confirm it's a copy — mutation shouldn't affect persona.tools
        p.allowed_tools.append("extra")
        self.assertEqual(self.persona.tools, ["run_command"])

    def test_user_message_contains_mention_text(self) -> None:
        p = self._build()
        self.assertIn("@ai please help", p.user)

    def test_user_message_has_your_task_closing(self) -> None:
        p = self._build()
        self.assertIn("<your_task>", p.user)
        self.assertIn("@ai mention", p.user)


class TestTaskRendering(unittest.TestCase):
    def test_task_id_title_description_present(self) -> None:
        p = build_prompt(
            task=_task(id="T-42", title="Refactor auth", description="JWT centralization."),
            ancestors=[],
            thread=[],
            mention=_comment(),
            persona=_persona(),
            ai_context=None,
        )
        self.assertIn("<task>", p.user)
        self.assertIn("T-42", p.user)
        self.assertIn("Refactor auth", p.user)
        self.assertIn("JWT centralization.", p.user)

    def test_xml_special_chars_escaped_in_title(self) -> None:
        p = build_prompt(
            task=_task(title="<script>alert('x')</script> & bug"),
            ancestors=[],
            thread=[],
            mention=_comment(),
            persona=_persona(),
            ai_context=None,
        )
        self.assertNotIn("<script>", p.user)
        self.assertIn("&lt;script&gt;", p.user)
        self.assertIn("&amp;", p.user)


class TestAncestorChain(unittest.TestCase):
    def test_omitted_when_empty(self) -> None:
        p = build_prompt(
            task=_task(),
            ancestors=[],
            thread=[],
            mention=_comment(),
            persona=_persona(),
            ai_context=None,
        )
        self.assertNotIn("<ancestor_chain>", p.user)

    def test_rendered_when_present(self) -> None:
        a1 = _task(id="A1", title="Root project")
        a2 = _task(id="A2", title="Auth subsystem")
        p = build_prompt(
            task=_task(),
            ancestors=[a1, a2],
            thread=[],
            mention=_comment(),
            persona=_persona(),
            ai_context=None,
        )
        self.assertIn("<ancestor_chain>", p.user)
        self.assertIn("Root project", p.user)
        self.assertIn("Auth subsystem", p.user)
        # order preserved (root → parent)
        self.assertLess(p.user.index("Root project"), p.user.index("Auth subsystem"))


class TestWorkspace(unittest.TestCase):
    def test_workspace_block_path_free(self) -> None:
        """Workspace section should describe the convention without leaking
        an absolute path — the proxy owns the actual cwd."""
        p = build_prompt(
            task=_task(),
            ancestors=[],
            thread=[],
            mention=_comment(),
            persona=_persona(),
            ai_context=None,
        )
        self.assertIn("<workspace>", p.user)
        self.assertIn("per-task workspace", p.user)
        # No leaked absolute path
        self.assertNotIn("/Users/", p.user)
        self.assertNotIn("/root/", p.user)
        self.assertNotIn("/tmp/", p.user)


class TestAIContext(unittest.TestCase):
    def test_omitted_when_none_or_empty(self) -> None:
        p_none = build_prompt(
            task=_task(),
            ancestors=[],
            thread=[],
            mention=_comment(),
            persona=_persona(),
            ai_context=None,
        )
        p_empty = build_prompt(
            task=_task(),
            ancestors=[],
            thread=[],
            mention=_comment(),
            persona=_persona(),
            ai_context={},
        )
        self.assertNotIn("<ai_context>", p_none.user)
        self.assertNotIn("<ai_context>", p_empty.user)

    def test_rendered_as_yaml_when_present(self) -> None:
        ctx = {
            "goal": "Centralize JWT validation",
            "scope": {"in": ["middleware"], "out": ["oauth"]},
            "open_questions": ["session expiry policy?"],
        }
        p = build_prompt(
            task=_task(),
            ancestors=[],
            thread=[],
            mention=_comment(),
            persona=_persona(),
            ai_context=ctx,
        )
        self.assertIn("<ai_context>", p.user)
        self.assertIn("goal: Centralize JWT validation", p.user)
        self.assertIn("session expiry policy?", p.user)
        # nested scope dict rendered
        self.assertIn("scope:", p.user)
        self.assertIn("middleware", p.user)
        self.assertIn("oauth", p.user)


class TestThread(unittest.TestCase):
    def test_empty_thread_yields_explicit_note(self) -> None:
        p = build_prompt(
            task=_task(),
            ancestors=[],
            thread=[],
            mention=_comment(),
            persona=_persona(),
            ai_context=None,
        )
        self.assertIn("first comment on this task", p.user)

    def test_thread_rendered_oldest_first(self) -> None:
        c1 = _comment(id="c-1", text="First message", created_at=1_700_000_000_000)
        c2 = _comment(id="c-2", text="Second message", created_at=1_700_000_001_000)
        p = build_prompt(
            task=_task(),
            ancestors=[],
            thread=[c1, c2],
            mention=_comment(id="m-1", text="@ai now"),
            persona=_persona(),
            ai_context=None,
        )
        self.assertLess(p.user.index("First message"), p.user.index("Second message"))

    def test_thread_capped_at_limit(self) -> None:
        comments = [
            _comment(id=f"c-{i}", text=f"msg{i}", created_at=1_700_000_000_000 + i)
            for i in range(50)
        ]
        p = build_prompt(
            task=_task(),
            ancestors=[],
            thread=comments,
            mention=_comment(id="m-1", text="@ai"),
            persona=_persona(),
            ai_context=None,
            thread_limit=5,
        )
        # last 5 should be present
        for i in range(45, 50):
            self.assertIn(f"msg{i}", p.user)
        # earlier ones dropped
        self.assertNotIn("msg0", p.user)
        self.assertNotIn("msg44", p.user)

    def test_thread_comment_metadata_in_open_tag(self) -> None:
        c = _comment(
            id="c-99", text="hi", created_by="ai-engineer", created_at=1_700_000_000_000
        )
        p = build_prompt(
            task=_task(),
            ancestors=[],
            thread=[c],
            mention=_comment(),
            persona=_persona(),
            ai_context=None,
        )
        self.assertIn('id="c-99"', p.user)
        self.assertIn('created_by="ai-engineer"', p.user)
        # ISO timestamp format (Z suffix, T separator)
        self.assertRegex(p.user, r'created_at="20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ"')

    def test_xml_escaping_in_comment_text(self) -> None:
        c = _comment(text='<bad>tag</bad> & "stuff"')
        p = build_prompt(
            task=_task(),
            ancestors=[],
            thread=[c],
            mention=_comment(),
            persona=_persona(),
            ai_context=None,
        )
        self.assertNotIn("<bad>", p.user)
        self.assertIn("&lt;bad&gt;", p.user)
        self.assertIn("&amp;", p.user)


class TestMentionBlock(unittest.TestCase):
    def test_mention_rendered_separately(self) -> None:
        m = _comment(id="m-1", text="@ai-engineer please review", created_by="user")
        p = build_prompt(
            task=_task(),
            ancestors=[],
            thread=[_comment(id="c-1", text="earlier note")],
            mention=m,
            persona=_persona(),
            ai_context=None,
        )
        self.assertIn('<mention triggering="true">', p.user)
        self.assertIn("@ai-engineer please review", p.user)
        # mention block comes after thread block
        self.assertGreater(p.user.index("<mention"), p.user.index("</thread>"))

    def test_mention_includes_metadata(self) -> None:
        m = _comment(id="m-1", text="@ai", created_by="user", created_at=1_700_000_000_000)
        p = build_prompt(
            task=_task(),
            ancestors=[],
            thread=[],
            mention=m,
            persona=_persona(),
            ai_context=None,
        )
        self.assertIn('id="m-1"', p.user)
        self.assertIn('created_by="user"', p.user)


class TestDefaultThreadLimit(unittest.TestCase):
    def test_default_constant_exposed(self) -> None:
        # Sanity: the default cap is a sensible positive integer.
        self.assertIsInstance(DEFAULT_THREAD_LIMIT, int)
        self.assertGreater(DEFAULT_THREAD_LIMIT, 0)


if __name__ == "__main__":
    unittest.main()
