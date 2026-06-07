"""Unit tests for persona_registry."""

from __future__ import annotations

import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from persona_registry import (
    MENTION_RE,
    load_persona,
    parse_persona_file,
    resolve_includes,
    route_mention,
)


class _Fixture:
    """Temp dir for persona files."""

    def __init__(self) -> None:
        self.tmp = TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "_shared").mkdir()

    def write(self, rel: str, content: str) -> Path:
        path = self.dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).lstrip("\n"))
        return path

    def cleanup(self) -> None:
        self.tmp.cleanup()


class TestParsePersonaFile(unittest.TestCase):
    def setUp(self) -> None:
        self.f = _Fixture()

    def tearDown(self) -> None:
        self.f.cleanup()

    def test_frontmatter_extracted(self) -> None:
        path = self.f.write(
            "test.md",
            """
            ---
            name: test
            model: claude-haiku-4-5
            tools:
              - get_task
              - run_command
            ---

            Body content here.
            """,
        )
        fm, body = parse_persona_file(path)
        self.assertEqual(fm["name"], "test")
        self.assertEqual(fm["model"], "claude-haiku-4-5")
        self.assertEqual(fm["tools"], ["get_task", "run_command"])
        self.assertIn("Body content here.", body)

    def test_no_frontmatter(self) -> None:
        path = self.f.write("bare.md", "Just body.\n")
        fm, body = parse_persona_file(path)
        self.assertEqual(fm, {})
        self.assertEqual(body, "Just body.\n")

    def test_non_mapping_frontmatter_raises(self) -> None:
        path = self.f.write(
            "bad.md",
            """
            ---
            - not
            - a
            - mapping
            ---

            body
            """,
        )
        with self.assertRaises(ValueError):
            parse_persona_file(path)


class TestResolveIncludes(unittest.TestCase):
    def setUp(self) -> None:
        self.f = _Fixture()
        self.f.write("_shared/a.md", "FRAGMENT A\n")
        self.f.write("_shared/b.md", "FRAGMENT B\n")

    def tearDown(self) -> None:
        self.f.cleanup()

    def test_no_includes(self) -> None:
        self.assertEqual(resolve_includes("BODY", [], self.f.dir), "BODY")

    def test_single_include(self) -> None:
        out = resolve_includes("BODY", ["_shared/a.md"], self.f.dir)
        self.assertIn("FRAGMENT A", out)
        self.assertIn("BODY", out)
        self.assertLess(out.index("FRAGMENT A"), out.index("BODY"))

    def test_multiple_includes_in_order(self) -> None:
        out = resolve_includes("BODY", ["_shared/a.md", "_shared/b.md"], self.f.dir)
        self.assertLess(out.index("FRAGMENT A"), out.index("FRAGMENT B"))
        self.assertLess(out.index("FRAGMENT B"), out.index("BODY"))

    def test_missing_include_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            resolve_includes("BODY", ["_shared/missing.md"], self.f.dir)

    def test_include_strips_own_frontmatter(self) -> None:
        self.f.write(
            "_shared/has_fm.md",
            """
            ---
            name: ignored
            ---

            FRAGMENT WITH FM
            """,
        )
        out = resolve_includes("BODY", ["_shared/has_fm.md"], self.f.dir)
        self.assertIn("FRAGMENT WITH FM", out)
        self.assertNotIn("name: ignored", out)


class TestLoadPersona(unittest.TestCase):
    def setUp(self) -> None:
        self.f = _Fixture()

    def tearDown(self) -> None:
        self.f.cleanup()

    def test_full_persona(self) -> None:
        self.f.write("_shared/intro.md", "INTRO\n")
        self.f.write(
            "engineer.md",
            """
            ---
            name: engineer
            description: implements code
            model: claude-sonnet-4-6
            tools:
              - get_task
              - run_command
            reply_length_cap: 2000
            version: 3
            includes:
              - _shared/intro.md
            ---

            You are a senior engineer.
            """,
        )
        p = load_persona("engineer", self.f.dir)
        self.assertEqual(p.name, "engineer")
        self.assertEqual(p.description, "implements code")
        self.assertEqual(p.model, "claude-sonnet-4-6")
        self.assertEqual(p.tools, ["get_task", "run_command"])
        self.assertEqual(p.reply_length_cap, 2000)
        self.assertEqual(p.version, 3)
        self.assertIn("INTRO", p.body)
        self.assertIn("You are a senior engineer.", p.body)
        self.assertEqual(p.raw_body.strip(), "You are a senior engineer.")

    def test_defaults_when_fields_missing(self) -> None:
        self.f.write(
            "minimal.md",
            """
            ---
            name: minimal
            ---

            Body.
            """,
        )
        p = load_persona("minimal", self.f.dir)
        self.assertEqual(p.name, "minimal")
        self.assertEqual(p.description, "")
        self.assertEqual(p.model, "claude-sonnet-4-6")
        self.assertEqual(p.tools, [])
        self.assertEqual(p.reply_length_cap, 4000)
        self.assertEqual(p.version, 1)

    def test_missing_persona_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_persona("ghost", self.f.dir)

    def test_no_frontmatter_uses_filename_as_name(self) -> None:
        self.f.write("anon.md", "Just body.")
        p = load_persona("anon", self.f.dir)
        self.assertEqual(p.name, "anon")
        self.assertIn("Just body.", p.body)


class TestRouteMention(unittest.TestCase):
    def setUp(self) -> None:
        self.f = _Fixture()
        self.f.write(
            "default.md",
            """
            ---
            name: default
            description: catch-all
            ---

            Default persona.
            """,
        )
        self.f.write(
            "engineer.md",
            """
            ---
            name: engineer
            ---

            Engineer persona.
            """,
        )

    def tearDown(self) -> None:
        self.f.cleanup()

    def test_bare_ai_routes_to_default(self) -> None:
        p = route_mention(None, self.f.dir)
        self.assertEqual(p.name, "default")

    def test_known_persona_routes(self) -> None:
        p = route_mention("engineer", self.f.dir)
        self.assertEqual(p.name, "engineer")

    def test_unknown_persona_falls_back_to_default(self) -> None:
        p = route_mention("ghost", self.f.dir)
        self.assertEqual(p.name, "default")

    def test_uppercase_suffix_normalized(self) -> None:
        p = route_mention("ENGINEER", self.f.dir)
        self.assertEqual(p.name, "engineer")


class TestMentionRegex(unittest.TestCase):
    def _matches(self, text: str) -> bool:
        return MENTION_RE.search(text) is not None

    def _suffix(self, text: str) -> str | None:
        m = MENTION_RE.search(text)
        return None if not m else m.group(1)

    def test_bare_at_ai(self) -> None:
        self.assertTrue(self._matches("Hello @ai please help"))
        self.assertIsNone(self._suffix("Hello @ai please help"))

    def test_named_persona(self) -> None:
        m = MENTION_RE.search("@ai-engineer take this")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "engineer")

    def test_case_insensitive(self) -> None:
        m = MENTION_RE.search("@AI-Manager pls")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1).lower(), "manager")

    def test_at_start_of_text(self) -> None:
        self.assertTrue(self._matches("@ai-planner now"))

    def test_does_not_match_inside_email(self) -> None:
        self.assertFalse(self._matches("user@aibnb.com"))

    def test_does_not_match_within_word(self) -> None:
        self.assertFalse(self._matches("aircraft"))
        self.assertFalse(self._matches("@airbnb"))  # 'r' continues the word

    def test_word_boundary_after_ai_allows_punctuation(self) -> None:
        self.assertTrue(self._matches("@ai!"))
        self.assertTrue(self._matches("(@ai)"))

    def test_first_mention_extraction(self) -> None:
        text = "@ai-planner first then @ai-engineer second"
        m = MENTION_RE.search(text)
        self.assertEqual(m.group(1), "planner")


class RealPersonaKnowledgeCardsTest(unittest.TestCase):
    """Phase C wiring: every working persona must include the knowledge-card
    due-diligence fragment, run the fixer (so it can reply naturally), and have
    a way to run `wp knowledge` — via an unrestricted `Bash` tool (engineer/
    reviewer) or a scoped `Bash(wp knowledge …)` grant. These load the actual
    on-disk persona files."""

    PERSONAS = ["engineer", "manager", "planner", "reviewer", "default", "pm"]

    def _load(self, name):
        return load_persona(name)

    def test_all_include_knowledge_cards_fragment(self) -> None:
        for name in self.PERSONAS:
            p = self._load(name)
            self.assertIn(
                "Company knowledge cards", p.body,
                f"{name} is missing the knowledge_cards fragment",
            )

    def test_all_have_fixer(self) -> None:
        for name in self.PERSONAS:
            p = self._load(name)
            self.assertTrue(
                p.fixer_model,
                f"{name} should have a fixer_model so it can reply naturally",
            )

    def test_each_persona_can_run_wp_knowledge(self) -> None:
        # Unrestricted `Bash` (engineer/reviewer) or a scoped `Bash(wp knowledge …)`
        # grant — every persona needs a path to execute `wp knowledge`.
        for name in self.PERSONAS:
            p = self._load(name)
            has_general_bash = "Bash" in p.tools
            has_scoped_bash = any(t.startswith("Bash(wp knowledge") for t in p.tools)
            self.assertTrue(
                has_general_bash or has_scoped_bash,
                f"{name} has no way to run wp knowledge (no Bash, no scoped wp-knowledge grant)",
            )

    def test_no_persona_uses_mcp(self) -> None:
        # The whole AI layer is MCP-free so it runs on locked-down machines.
        # This guards every shipped persona, not just the ones above.
        from persona_registry import DEFAULT_PERSONAS_DIR
        for path in sorted(DEFAULT_PERSONAS_DIR.glob("*.md")):
            p = load_persona(path.stem)
            mcp = [t for t in p.tools if t.startswith("mcp__")]
            self.assertEqual(mcp, [], f"{path.stem} still has MCP tools: {mcp}")

    def test_max_turns_affords_lookups(self) -> None:
        # Personas that default to 20 were bumped to >= 40 so KB lookups fit.
        for name in self.PERSONAS:
            p = self._load(name)
            self.assertGreaterEqual(
                p.max_turns, 40, f"{name} max_turns too low for due-diligence lookups"
            )


class PMPersonaTest(unittest.TestCase):
    """The PM is advisory and read-only: it frames requirements + scope, but it
    does not write code, create tasks, write knowledge cards, or run arbitrary
    shell — and (being non-manager) its replies can't dispatch other personas."""

    def test_pm_loads_and_routes(self):
        p = route_mention("pm")
        self.assertEqual(p.name, "pm")
        self.assertTrue(p.body.strip())

    def test_pm_is_read_only_and_advisory(self):
        p = load_persona("pm")
        # KB read only — no full write grant.
        self.assertNotIn("Bash(wp knowledge:*)", p.tools)
        self.assertTrue(
            any(t.startswith("Bash(wp knowledge search") for t in p.tools),
            "pm needs scoped read access to wp knowledge",
        )
        # Advisory — no task creation, no arbitrary command execution.
        self.assertNotIn("mcp__workplanner__create_task", p.tools)
        self.assertNotIn("mcp__workplanner__run_command", p.tools)


class PlannerCLITest(unittest.TestCase):
    """The planner must work without MCP (e.g. a locked-down office machine
    where custom MCP servers can't be loaded) — so all task + KB operations go
    through the `wp` CLI via scoped Bash, and it has no mcp__ tools at all."""

    def test_planner_is_mcp_free(self):
        p = load_persona("planner")
        mcp = [t for t in p.tools if t.startswith("mcp__")]
        self.assertEqual(mcp, [], f"planner must be MCP-free for portability; got {mcp}")

    def test_planner_does_tasks_via_cli(self):
        p = load_persona("planner")
        for needed in ("Bash(wp add:", "Bash(wp set:", "Bash(wp show:", "Bash(wp tree:"):
            self.assertTrue(
                any(t.startswith(needed) for t in p.tools),
                f"planner missing CLI task grant {needed}*",
            )
        # And still reads knowledge cards via the CLI.
        self.assertTrue(any(t.startswith("Bash(wp knowledge search:") for t in p.tools))


if __name__ == "__main__":
    unittest.main()
