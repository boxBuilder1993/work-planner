"""Git worktree isolation for worker agents.

Each worker agent gets its own worktree so agents don't conflict with each other.
Manager agents don't need worktrees — they only coordinate via API.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from config import WorkspaceConfig

logger = logging.getLogger(__name__)


class WorkspaceManager:
    """Manages git worktrees for agent isolation."""

    def __init__(self, config: WorkspaceConfig) -> None:
        self._repo = Path(config.repo_path) if config.repo_path else None
        self._base = config.worktree_base
        self._main_branch = config.main_branch

    @property
    def enabled(self) -> bool:
        return self._repo is not None and self._repo.exists()

    def _worktree_dir(self, task_id: str) -> Path:
        """Get the worktree directory for a task."""
        assert self._repo is not None
        return self._repo / self._base / task_id

    def get_worktree_path(self, task_id: str) -> str | None:
        """Return the worktree path if it exists, else None."""
        if not self.enabled:
            return None
        wt = self._worktree_dir(task_id)
        return str(wt) if wt.exists() else None

    def create_worktree(self, task_id: str) -> str | None:
        """Create a new git worktree for a worker agent.

        Creates a branch `ai/{task_id}` based on the main branch.
        Returns the worktree path, or None if workspace is not configured.
        """
        if not self.enabled:
            logger.debug("Workspace not configured, skipping worktree for %s", task_id)
            return None

        wt_path = self._worktree_dir(task_id)
        if wt_path.exists():
            logger.debug("Worktree already exists for task %s", task_id)
            return str(wt_path)

        branch_name = f"ai/{task_id}"

        try:
            # Ensure parent directory exists
            wt_path.parent.mkdir(parents=True, exist_ok=True)

            # Create worktree with a new branch
            subprocess.run(
                ["git", "worktree", "add", "-b", branch_name, str(wt_path), self._main_branch],
                cwd=str(self._repo),
                capture_output=True,
                text=True,
                check=True,
            )
            logger.info("Created worktree for task %s at %s", task_id, wt_path)
            return str(wt_path)

        except subprocess.CalledProcessError as e:
            logger.error("Failed to create worktree for task %s: %s", task_id, e.stderr)
            return None

    def cleanup_worktree(self, task_id: str) -> bool:
        """Remove a worktree and its branch after agent completes."""
        if not self.enabled:
            return False

        wt_path = self._worktree_dir(task_id)
        branch_name = f"ai/{task_id}"

        try:
            # Remove the worktree
            subprocess.run(
                ["git", "worktree", "remove", str(wt_path), "--force"],
                cwd=str(self._repo),
                capture_output=True,
                text=True,
                check=True,
            )

            # Delete the branch
            subprocess.run(
                ["git", "branch", "-D", branch_name],
                cwd=str(self._repo),
                capture_output=True,
                text=True,
                check=False,  # branch may not exist
            )

            logger.info("Cleaned up worktree for task %s", task_id)
            return True

        except subprocess.CalledProcessError as e:
            logger.error("Failed to cleanup worktree for task %s: %s", task_id, e.stderr)
            return False

    def cleanup_orphaned(self) -> int:
        """Scan for and remove orphaned worktrees on startup.

        Returns the number of cleaned up worktrees.
        """
        if not self.enabled:
            return 0

        assert self._repo is not None
        wt_base = self._repo / self._base
        if not wt_base.exists():
            return 0

        # Prune worktrees that git knows about but are gone
        try:
            subprocess.run(
                ["git", "worktree", "prune"],
                cwd=str(self._repo),
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError:
            pass

        # Clean up directories that shouldn't be there
        cleaned = 0
        for item in wt_base.iterdir():
            if item.is_dir():
                task_id = item.name
                logger.warning("Found orphaned worktree directory: %s", item)
                if self.cleanup_worktree(task_id):
                    cleaned += 1

        return cleaned
