"""Unit tests for the `wp knowledge` command group.

Uses click's CliRunner with a mocked api.Client, so no backend is needed.
Tests verify: arg/flag parsing, the right client method is called with the
right arguments, content resolution (inline / @file / stdin), validation,
and that output renders. The backend behavior itself is covered by the Go
integration suite (backend/tests/integration).
"""

from __future__ import annotations

import unittest
from unittest import mock

from click.testing import CliRunner

# `_cli_group` is the click.Group; `main` (same module) is the entry-point
# wrapper function that calls it. CliRunner needs the group.
from workplanner_cli.cli import _cli_group as main


CARD = {
    "id": "auth-jwt",
    "content": "Auth is JWT-based.",
    "tags": ["auth", "backend"],
    "isValid": True,
    "createdAt": 1700000000000,
    "updatedAt": 1700000000000,
}


class KnowledgeCLITest(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()
        # WP_BASE_URL/WP_INTERNAL_KEY let config.load() resolve a profile
        # without a config file. Client is patched so no HTTP happens.
        self.env = {"WP_BASE_URL": "http://test", "WP_INTERNAL_KEY": "k"}

    def _invoke(self, args, client_mock):
        with mock.patch("workplanner_cli.cli.Client", return_value=client_mock):
            return self.runner.invoke(main, args, env=self.env)

    # ── add ──────────────────────────────────────────────────────────

    def test_add_inline_content_and_tags(self):
        client = mock.MagicMock()
        client.create_knowledge_card.return_value = CARD
        res = self._invoke(
            ["knowledge", "add", "auth-jwt", "-c", "Auth is JWT-based.", "--tag", "auth", "--tag", "backend"],
            client,
        )
        self.assertEqual(res.exit_code, 0, res.output)
        client.create_knowledge_card.assert_called_once_with(
            "auth-jwt", "Auth is JWT-based.", ["auth", "backend"]
        )
        self.assertIn("Created card auth-jwt", res.output)

    def test_add_content_from_stdin(self):
        client = mock.MagicMock()
        client.create_knowledge_card.return_value = CARD
        with mock.patch("workplanner_cli.cli.Client", return_value=client):
            res = self.runner.invoke(
                main, ["knowledge", "add", "auth-jwt"], input="from stdin\n", env=self.env
            )
        self.assertEqual(res.exit_code, 0, res.output)
        args = client.create_knowledge_card.call_args.args
        self.assertEqual(args[0], "auth-jwt")
        self.assertEqual(args[1], "from stdin")

    def test_add_rejects_bad_slug(self):
        client = mock.MagicMock()
        res = self._invoke(["knowledge", "add", "Bad Slug", "-c", "x"], client)
        self.assertNotEqual(res.exit_code, 0)
        self.assertIn("slug", res.output.lower())
        client.create_knowledge_card.assert_not_called()

    def test_add_rejects_empty_content(self):
        client = mock.MagicMock()
        res = self._invoke(["knowledge", "add", "ok-slug", "-c", "   "], client)
        self.assertNotEqual(res.exit_code, 0)
        client.create_knowledge_card.assert_not_called()

    # ── list ─────────────────────────────────────────────────────────

    def test_list_default_excludes_invalid(self):
        client = mock.MagicMock()
        client.list_knowledge_cards.return_value = [CARD]
        res = self._invoke(["knowledge", "list"], client)
        self.assertEqual(res.exit_code, 0, res.output)
        client.list_knowledge_cards.assert_called_once_with(tag=None, include_invalid=False)
        self.assertIn("auth-jwt", res.output)

    def test_list_tag_and_all(self):
        client = mock.MagicMock()
        client.list_knowledge_cards.return_value = []
        res = self._invoke(["knowledge", "list", "--tag", "backend", "--all"], client)
        self.assertEqual(res.exit_code, 0, res.output)
        client.list_knowledge_cards.assert_called_once_with(tag="backend", include_invalid=True)

    # ── show ─────────────────────────────────────────────────────────

    def test_show_renders_content(self):
        client = mock.MagicMock()
        client.get_knowledge_card.return_value = CARD
        res = self._invoke(["knowledge", "show", "auth-jwt"], client)
        self.assertEqual(res.exit_code, 0, res.output)
        client.get_knowledge_card.assert_called_once_with("auth-jwt")
        self.assertIn("Auth is JWT-based.", res.output)

    # ── search ───────────────────────────────────────────────────────

    def test_search_query_and_tag(self):
        client = mock.MagicMock()
        client.search_knowledge_cards.return_value = [CARD]
        res = self._invoke(["knowledge", "search", "jwt", "--tag", "auth", "--limit", "5"], client)
        self.assertEqual(res.exit_code, 0, res.output)
        client.search_knowledge_cards.assert_called_once_with(
            query="jwt", tag="auth", include_invalid=False, limit=5
        )

    def test_search_tag_only(self):
        client = mock.MagicMock()
        client.search_knowledge_cards.return_value = []
        res = self._invoke(["knowledge", "search", "--tag", "auth"], client)
        self.assertEqual(res.exit_code, 0, res.output)
        client.search_knowledge_cards.assert_called_once_with(
            query=None, tag="auth", include_invalid=False, limit=None
        )

    # ── edit ─────────────────────────────────────────────────────────

    def test_edit_content_and_invalid(self):
        client = mock.MagicMock()
        client.update_knowledge_card.return_value = CARD
        res = self._invoke(
            ["knowledge", "edit", "auth-jwt", "-c", "new text", "--invalid"], client
        )
        self.assertEqual(res.exit_code, 0, res.output)
        client.update_knowledge_card.assert_called_once_with(
            "auth-jwt", {"content": "new text", "isValid": False}
        )

    def test_edit_replace_tags(self):
        client = mock.MagicMock()
        client.update_knowledge_card.return_value = CARD
        res = self._invoke(["knowledge", "edit", "auth-jwt", "--tag", "x", "--tag", "y"], client)
        self.assertEqual(res.exit_code, 0, res.output)
        client.update_knowledge_card.assert_called_once_with("auth-jwt", {"tags": ["x", "y"]})

    def test_edit_clear_tags(self):
        client = mock.MagicMock()
        client.update_knowledge_card.return_value = CARD
        res = self._invoke(["knowledge", "edit", "auth-jwt", "--clear-tags"], client)
        self.assertEqual(res.exit_code, 0, res.output)
        client.update_knowledge_card.assert_called_once_with("auth-jwt", {"tags": []})

    def test_edit_nothing_errors(self):
        client = mock.MagicMock()
        res = self._invoke(["knowledge", "edit", "auth-jwt"], client)
        self.assertNotEqual(res.exit_code, 0)
        client.update_knowledge_card.assert_not_called()

    # ── rm ───────────────────────────────────────────────────────────

    def test_rm(self):
        client = mock.MagicMock()
        client.delete_knowledge_card.return_value = None
        res = self._invoke(["knowledge", "rm", "auth-jwt"], client)
        self.assertEqual(res.exit_code, 0, res.output)
        client.delete_knowledge_card.assert_called_once_with("auth-jwt")
        self.assertIn("Deleted card auth-jwt", res.output)


if __name__ == "__main__":
    unittest.main()
