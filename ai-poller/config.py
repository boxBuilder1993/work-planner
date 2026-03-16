"""Project configuration for the AI poller.

Centralizes all settings: API connection, agent limits, workspace paths,
and vector DB connection. Loaded from environment variables with sensible defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class AgentLimits:
    """Caps on concurrent agent activity."""
    max_global_agents: int = 3
    max_tasks_per_agent: int = 3
    max_turns_per_run: int = 20


@dataclass(frozen=True)
class WorkspaceConfig:
    """Git worktree isolation settings."""
    repo_path: str = ""
    worktree_base: str = ".claude/worktrees"
    main_branch: str = "main"


@dataclass(frozen=True)
class VectorDBConfig:
    """ChromaDB connection settings."""
    host: str = "localhost"
    port: int = 8000
    collection: str = "workplanner_knowledge"


@dataclass(frozen=True)
class Config:
    """Root configuration object."""
    # API connection
    api_url: str = ""
    jwt: str = ""
    internal_api_key: str = ""  # Alternative to JWT for Railway internal network
    anthropic_api_key: str = ""

    # Polling
    poll_interval_seconds: int = 60

    # Sub-configs
    agent_limits: AgentLimits = field(default_factory=AgentLimits)
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    vector_db: VectorDBConfig = field(default_factory=VectorDBConfig)

    def validate(self) -> None:
        """Raise ValueError if required fields are missing."""
        missing = []
        if not self.api_url:
            missing.append("WORKPLANNER_API_URL")
        if not self.jwt and not self.internal_api_key:
            missing.append("WORKPLANNER_JWT or INTERNAL_API_KEY")
        if not self.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY")
        if missing:
            raise ValueError(f"Missing required config: {', '.join(missing)}")


def load_config(env_path: str | None = None) -> Config:
    """Load config from environment variables.

    Args:
        env_path: Optional path to .env file. Defaults to .env in the poller directory.
    """
    if env_path is None:
        env_path = os.path.join(os.path.dirname(__file__), ".env")
    load_dotenv(env_path)

    def _env(key: str, default: str = "") -> str:
        return os.environ.get(key, default)

    def _int(key: str, default: int) -> int:
        return int(os.environ.get(key, str(default)))

    return Config(
        api_url=_env("WORKPLANNER_API_URL"),
        jwt=_env("WORKPLANNER_JWT"),
        internal_api_key=_env("INTERNAL_API_KEY"),
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        poll_interval_seconds=_int("POLL_INTERVAL_SECONDS", 60),
        agent_limits=AgentLimits(
            max_global_agents=_int("MAX_GLOBAL_AGENTS", 20),
            max_tasks_per_agent=_int("MAX_TASKS_PER_AGENT", 3),
            max_turns_per_run=_int("MAX_TURNS_PER_RUN", 10),
        ),
        workspace=WorkspaceConfig(
            repo_path=_env("REPO_PATH"),
            worktree_base=_env("WORKTREE_BASE", ".claude/worktrees"),
            main_branch=_env("MAIN_BRANCH", "main"),
        ),
        vector_db=VectorDBConfig(
            host=_env("CHROMADB_HOST", "localhost"),
            port=_int("CHROMADB_PORT", 8000),
            collection=_env("CHROMADB_COLLECTION", "workplanner_knowledge"),
        ),
    )
