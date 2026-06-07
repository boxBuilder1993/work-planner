"""Agent proxy server with runtime failover.

Accepts requests from the ai-poller on Railway, runs a local coding agent
runtime on your Mac, and returns results via an async job queue.

Primary runtime order defaults to Claude Code, then Codex.
The proxy keeps ai-poller's request schema unchanged and handles runtime
selection, model mapping, and retryable-failure failover internally.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Agent Proxy")
logger = logging.getLogger("agent-proxy")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

PROXY_DIR = Path(__file__).parent.resolve()
REPO_ROOT = PROXY_DIR.parent
API_KEY = os.environ.get("CLAUDE_PROXY_KEY", "")
# Per-task workspace base. Each chat dispatch gets `WORKSPACE_BASE / task_id`
# as its cwd. The poller never sees this path — filesystem layout is a proxy
# concern. Override via env if you want workspaces somewhere other than the
# user's home.
WORKSPACE_BASE = Path(
    os.environ.get("WORKSPACE_BASE", str(Path.home() / ".workplanner" / "workspaces"))
)
# Make the proxy self-sufficient regardless of how it was launched (`make dev`,
# `make dev-proxy`, or a bare `uv run python proxy.py`): pull the backend URL +
# key from the repo-root .env when they aren't already exported. Anything
# already in the environment wins, so a prod-pointed proxy — which exports its
# own WORKPLANNER_API_URL — is never overridden.
def _load_repo_env(env_path: Path | None = None) -> None:
    env_path = env_path or (REPO_ROOT / ".env")
    if not env_path.exists():
        return
    try:
        for raw in env_path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if key in ("WORKPLANNER_API_URL", "INTERNAL_API_KEY") and key not in os.environ:
                os.environ[key] = val.strip().strip('"').strip("'")
    except OSError:
        pass


_load_repo_env()

# Backend URL + auth key used by MCP servers / the `wp` CLI spawned on this
# host. The poller also sends these in the request body, but its values reflect
# *its* network view (Railway's `backend.railway.internal` etc.) which doesn't
# resolve from the Mac. Proxy-side env wins so the MCP/CLI always talks to a
# reachable URL. Defaults to the host-published local backend so a fresh
# local/office checkout works without exporting anything.
WORKPLANNER_API_URL = os.environ.get("WORKPLANNER_API_URL", "http://localhost:8080")
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")
JOB_TTL = 300
RUN_TIMEOUT_SECONDS = int(os.environ.get("PROXY_RUN_TIMEOUT_SECONDS", "600"))
RUNTIME_DEGRADED_TTL = int(os.environ.get("PROXY_RUNTIME_DEGRADED_TTL", "300"))
RUNTIME_ORDER = tuple(
    name.strip()
    for name in os.environ.get("PROXY_RUNTIME_ORDER", "claude,codex").split(",")
    if name.strip()
)

# Cheap defaults. Requests can still override them via explicit env vars, but the
# proxy maps the poller's old expensive defaults to these cheaper models.
CLAUDE_DEFAULT_MODEL = os.environ.get("CLAUDE_DEFAULT_MODEL", "claude-haiku-4-5")
CODEX_DEFAULT_MODEL = os.environ.get("CODEX_DEFAULT_MODEL", "gpt-5-codex-mini")

# ai-poller still sends Claude-specific models today; remap those to the cheaper
# runtime defaults until the poller becomes runtime-aware.
CLAUDE_EXPENSIVE_DEFAULTS = {"claude-sonnet-4-6", "claude-sonnet-4", "sonnet"}


class RunRequest(BaseModel):
    prompt: str
    system_prompt: str = ""
    model: str = "claude-sonnet-4-6"
    preferred_runtime: str = ""
    fallback_runtimes: list[dict[str, str]] = []
    max_turns: int = 20
    allowed_tools: list[str] = []
    disallowed_tools: list[str] = []
    algo_tools: list[str] = []
    task_id: str = ""
    ai_status: str = ""
    # Set by the work_item_handler so the MCP server can expose
    # get_my_work_item() without the AI knowing its own id. Empty for legacy
    # dispatches that don't flow through WorkItems.
    work_item_id: str = ""


class SubmitResponse(BaseModel):
    job_id: str


class StatusResponse(BaseModel):
    status: str
    result: str = ""
    error: str = ""
    runtime: str = ""
    # Full claude -p --output-format json envelope (for the Claude runtime):
    # {type, duration_ms, total_cost_usd, stop_reason, usage, modelUsage, ...}.
    # Empty dict for Codex (which does not emit a comparable envelope) and on
    # error. Lets the poller stamp ai-duration-ms, ai-cost-usd, ai-stop-reason,
    # and ai-tokens into comments.props without re-parsing the result string.
    metadata: dict = {}


@dataclass
class RuntimeSuccess:
    runtime: str
    model: str
    result: str
    metadata: dict = field(default_factory=dict)


@dataclass
class RuntimeFailure:
    runtime: str
    model: str
    error_type: str
    message: str
    retryable: bool


RuntimeOutcome = RuntimeSuccess | RuntimeFailure


@dataclass
class RuntimeHealth:
    degraded_until: float = 0.0
    last_error_type: str = ""
    last_message: str = ""

    @property
    def degraded(self) -> bool:
        return time.time() < self.degraded_until


@dataclass
class Job:
    id: str
    task_id: str
    status: str = "queued"
    result: str = ""
    error: str = ""
    runtime: str = ""
    metadata: dict = field(default_factory=dict)
    attempts: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None


jobs: dict[str, Job] = {}
runtime_health: dict[str, RuntimeHealth] = {}


def _cleanup_old_jobs() -> None:
    now = time.time()
    expired = [
        jid for jid, j in jobs.items()
        if j.completed_at and now - j.completed_at > JOB_TTL
    ]
    for jid in expired:
        del jobs[jid]


def _degrade_runtime(runtime: str, error_type: str, message: str) -> None:
    runtime_health[runtime] = RuntimeHealth(
        degraded_until=time.time() + RUNTIME_DEGRADED_TTL,
        last_error_type=error_type,
        last_message=message[:500],
    )


def _runtime_is_degraded(runtime: str) -> bool:
    health = runtime_health.get(runtime)
    return bool(health and health.degraded)


def _resolve_workspace_path(req: RunRequest) -> Path | None:
    """Return the per-task workspace dir, or None for legacy (no task_id)
    requests that should run in REPO_ROOT."""
    if not req.task_id:
        return None
    return WORKSPACE_BASE / req.task_id


def _workplanner_env(req: RunRequest) -> dict[str, str]:
    env = {
        "WORKPLANNER_API_URL": WORKPLANNER_API_URL,
        "INTERNAL_API_KEY": INTERNAL_API_KEY,
    }
    workspace = _resolve_workspace_path(req)
    if workspace is not None:
        # Consumed by workplanner_server.py's run_command tool to confine
        # shell commands to the per-task workspace directory.
        env["WORKPLANNER_WORKSPACE_PATH"] = str(workspace)
    if req.work_item_id:
        # Consumed by workplanner_server.py's get_my_work_item / default
        # task scope on list_work_items.
        env["WORK_ITEM_ID"] = req.work_item_id
    return env


def _claude_subprocess_env() -> dict[str, str]:
    """Environment for the `claude -p` process itself (distinct from the MCP
    server env). Carries WP_BASE_URL / WP_INTERNAL_KEY so a persona running
    `wp knowledge search ...` via its Bash tool authenticates without a
    config file. Mapped from the proxy's own backend config; empty values are
    omitted so `wp` falls back to its config file if the proxy wasn't given a
    backend URL/key."""
    env = os.environ.copy()
    if WORKPLANNER_API_URL:
        env["WP_BASE_URL"] = WORKPLANNER_API_URL
    if INTERNAL_API_KEY:
        env["WP_INTERNAL_KEY"] = INTERNAL_API_KEY
    return env


def _algo_env(req: RunRequest) -> dict[str, str]:
    return {
        "WORKPLANNER_API_URL": WORKPLANNER_API_URL,
        "INTERNAL_API_KEY": INTERNAL_API_KEY,
        "ALGO_TASK_ID": req.task_id,
        "ALGO_AI_STATUS": req.ai_status,
        "ALGO_TOOLS": ",".join(req.algo_tools),
    }


def _classify_failure(message: str) -> tuple[str, bool]:
    text = message.lower()
    if any(token in text for token in ("rate limit", "too many requests", "429", "overloaded", "retry later")):
        return "rate_limit", True
    if any(token in text for token in ("quota", "exhaust", "usage limit", "subscription")):
        return "quota_exhausted", True
    if any(token in text for token in ("not logged in", "invalid api key", "authentication", "auth")):
        return "auth", True
    if any(token in text for token in ("timeout", "timed out")):
        return "timeout", True
    if any(token in text for token in ("lookup address information", "connection", "temporarily unavailable", "reconnecting")):
        return "unavailable", True
    if any(token in text for token in ("unknown option", "unsupported", "unknown model", "invalid model")):
        return "bad_request", False
    return "internal", False


def _resolve_claude_model(req_model: str) -> str:
    forced = os.environ.get("CLAUDE_FORCE_MODEL")
    if forced:
        return forced
    if not req_model or req_model in CLAUDE_EXPENSIVE_DEFAULTS:
        return CLAUDE_DEFAULT_MODEL
    return req_model


def _resolve_codex_model(req_model: str) -> str:
    forced = os.environ.get("CODEX_FORCE_MODEL")
    if forced:
        return forced
    if not req_model or req_model.startswith("claude-") or req_model in {"sonnet", "opus"}:
        return CODEX_DEFAULT_MODEL
    return req_model


async def _run_subprocess(
    cmd: list[str],
    *,
    stdin_text: str = "",
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    timeout: int = RUN_TIMEOUT_SECONDS,
) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=str(cwd) if cwd else None,
    )
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(input=stdin_text.encode() if stdin_text else None),
        timeout=timeout,
    )
    return proc.returncode, stdout.decode(), stderr.decode()


def _build_claude_mcp_config(req: RunRequest, config_path: Path) -> None:
    mcp_servers: dict[str, dict[str, object]] = {
        "workplanner": {
            "command": "uv",
            "args": ["run", "--project", str(PROXY_DIR), str(PROXY_DIR / "workplanner_server.py")],
            "env": _workplanner_env(req),
        }
    }
    if req.algo_tools:
        mcp_servers["algo"] = {
            "command": "uv",
            "args": ["run", "--project", str(PROXY_DIR), str(PROXY_DIR / "algo_server.py")],
            "env": _algo_env(req),
        }
    config_path.write_text(json.dumps({"mcpServers": mcp_servers}))


def _copy_if_exists(src: Path, dest: Path) -> None:
    if src.exists():
        shutil.copy2(src, dest)


async def _prepare_codex_home(req: RunRequest) -> Path:
    home_dir = Path(tempfile.mkdtemp(prefix="codex-home-", dir="/tmp"))
    codex_dir = home_dir / ".codex"
    codex_dir.mkdir(parents=True, exist_ok=True)

    user_codex_dir = Path.home() / ".codex"
    _copy_if_exists(user_codex_dir / "auth.json", codex_dir / "auth.json")
    _copy_if_exists(user_codex_dir / "config.toml", codex_dir / "config.toml")

    env = os.environ.copy()
    env["HOME"] = str(home_dir)

    workplanner_cmd = [
        "codex", "mcp", "add", "workplanner",
        "--env", f"WORKPLANNER_API_URL={WORKPLANNER_API_URL}",
        "--env", f"INTERNAL_API_KEY={INTERNAL_API_KEY}",
        "--", "uv", "run", "--project", str(PROXY_DIR), str(PROXY_DIR / "workplanner_server.py"),
    ]
    code, stdout, stderr = await _run_subprocess(workplanner_cmd, env=env, cwd=PROXY_DIR)
    if code != 0:
        raise RuntimeError(f"codex mcp add workplanner failed: {(stderr or stdout).strip()}")

    if req.algo_tools:
        algo_cmd = [
            "codex", "mcp", "add", "algo",
            "--env", f"WORKPLANNER_API_URL={WORKPLANNER_API_URL}",
            "--env", f"INTERNAL_API_KEY={INTERNAL_API_KEY}",
            "--env", f"ALGO_TASK_ID={req.task_id}",
            "--env", f"ALGO_AI_STATUS={req.ai_status}",
            "--env", f"ALGO_TOOLS={','.join(req.algo_tools)}",
            "--", "uv", "run", "--project", str(PROXY_DIR), str(PROXY_DIR / "algo_server.py"),
        ]
        code, stdout, stderr = await _run_subprocess(algo_cmd, env=env, cwd=PROXY_DIR)
        if code != 0:
            raise RuntimeError(f"codex mcp add algo failed: {(stderr or stdout).strip()}")

    return home_dir


class RuntimeAdapter(Protocol):
    name: str

    async def run(self, req: RunRequest) -> RuntimeOutcome:
        ...


class ClaudeRuntime:
    name = "claude"

    async def run(self, req: RunRequest) -> RuntimeOutcome:
        model = _resolve_claude_model(req.model) if not req.preferred_runtime else req.model
        config_path = Path(tempfile.mktemp(suffix=".json", prefix="claude-mcp-", dir="/tmp"))
        system_prompt_path: str | None = None

        try:
            _build_claude_mcp_config(req, config_path)

            cmd = [
                "claude", "-p",
                "--model", model,
                "--max-turns", str(req.max_turns),
                "--dangerously-skip-permissions",
                "--output-format", "json",
                "--no-session-persistence",
                "--strict-mcp-config",
                "--mcp-config", str(config_path),
                "--disallowedTools",
                "CronCreate", "CronDelete", "CronList",
                "RemoteTrigger",
                "Agent",
                "AskUserQuestion",
                *req.disallowed_tools,
            ]

            if req.system_prompt:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", prefix="claude-sysprompt-", delete=False, dir="/tmp"
                ) as spf:
                    spf.write(req.system_prompt)
                    system_prompt_path = spf.name
                cmd.extend(["--system-prompt-file", system_prompt_path])

            if req.allowed_tools:
                cmd.append("--allowedTools")
                cmd.extend(req.allowed_tools)

            # Chat-dispatch: confine claude -p to a per-task workspace dir.
            # Legacy callers that don't send task_id fall back to REPO_ROOT.
            workspace = _resolve_workspace_path(req)
            if workspace is not None:
                workspace.mkdir(parents=True, exist_ok=True)
                cmd.extend(["--add-dir", str(workspace)])
                run_cwd: Path = workspace
            else:
                run_cwd = REPO_ROOT

            logger.info("Running Claude runtime for task %s with model %s", req.task_id, model)
            code, stdout_text, stderr_text = await _run_subprocess(
                cmd,
                stdin_text=req.prompt,
                cwd=run_cwd,
                env=_claude_subprocess_env(),
            )
            if stderr_text:
                logger.warning("Claude stderr: %s", stderr_text[:500])

            # Forensic trail: always log the result string the AI produced,
            # win or lose. Without this, the only copy lives on the in-memory
            # job for JOB_TTL (5 min) — then it's gone. Cap so the log file
            # doesn't balloon for long runs.
            if stdout_text:
                logger.info(
                    "Claude stdout (task=%s, first 4000 chars): %s",
                    req.task_id, stdout_text[:4000],
                )

            if code == 0 and stdout_text.strip():
                metadata: dict = {}
                try:
                    output = json.loads(stdout_text)
                    if isinstance(output, dict):
                        metadata = output
                        result = str(output.get("result", stdout_text))
                    else:
                        result = stdout_text.strip()
                except json.JSONDecodeError:
                    result = stdout_text.strip()
                return RuntimeSuccess(
                    runtime=self.name, model=model, result=result, metadata=metadata,
                )

            message = (stderr_text or stdout_text or f"Exit code {code}").strip()
            error_type, retryable = _classify_failure(message)
            return RuntimeFailure(
                runtime=self.name,
                model=model,
                error_type=error_type,
                message=message,
                retryable=retryable,
            )
        except asyncio.TimeoutError:
            return RuntimeFailure(
                runtime=self.name,
                model=model,
                error_type="timeout",
                message=f"Claude runtime timed out after {RUN_TIMEOUT_SECONDS}s",
                retryable=True,
            )
        except Exception as exc:
            message = str(exc)
            error_type, retryable = _classify_failure(message)
            return RuntimeFailure(
                runtime=self.name,
                model=model,
                error_type=error_type,
                message=message,
                retryable=retryable,
            )
        finally:
            config_path.unlink(missing_ok=True)
            if system_prompt_path:
                Path(system_prompt_path).unlink(missing_ok=True)


class CodexRuntime:
    name = "codex"

    async def run(self, req: RunRequest) -> RuntimeOutcome:
        model = _resolve_codex_model(req.model) if not req.preferred_runtime else req.model
        codex_home: Path | None = None
        output_path = Path(tempfile.mktemp(suffix=".txt", prefix="codex-last-", dir="/tmp"))

        try:
            codex_home = await _prepare_codex_home(req)
            env = os.environ.copy()
            env["HOME"] = str(codex_home)

            cmd = [
                "codex", "exec",
                "--model", model,
                "--dangerously-bypass-approvals-and-sandbox",
                "--skip-git-repo-check",
                "--ephemeral",
                "--cd", str(REPO_ROOT),
                "--output-last-message", str(output_path),
            ]

            logger.info("Running Codex runtime for task %s with model %s", req.task_id, model)
            code, stdout_text, stderr_text = await _run_subprocess(
                cmd,
                stdin_text=req.prompt if not req.system_prompt else f"{req.system_prompt}\n\n{req.prompt}",
                env=env,
                cwd=REPO_ROOT,
            )

            output_text = output_path.read_text().strip() if output_path.exists() else ""
            if code == 0 and output_text:
                return RuntimeSuccess(runtime=self.name, model=model, result=output_text)

            message = "\n".join(part for part in (stderr_text.strip(), stdout_text.strip()) if part).strip()
            if not message and output_text:
                message = output_text
            if not message:
                message = f"Exit code {code}"
            error_type, retryable = _classify_failure(message)
            return RuntimeFailure(
                runtime=self.name,
                model=model,
                error_type=error_type,
                message=message,
                retryable=retryable,
            )
        except asyncio.TimeoutError:
            return RuntimeFailure(
                runtime=self.name,
                model=model,
                error_type="timeout",
                message=f"Codex runtime timed out after {RUN_TIMEOUT_SECONDS}s",
                retryable=True,
            )
        except Exception as exc:
            message = str(exc)
            error_type, retryable = _classify_failure(message)
            return RuntimeFailure(
                runtime=self.name,
                model=model,
                error_type=error_type,
                message=message,
                retryable=retryable,
            )
        finally:
            output_path.unlink(missing_ok=True)
            if codex_home:
                shutil.rmtree(codex_home, ignore_errors=True)


class RuntimeRouter:
    def __init__(self, runtimes: dict[str, RuntimeAdapter]) -> None:
        self._runtimes = runtimes

    def candidates(self, req: RunRequest) -> list[tuple[RuntimeAdapter, RunRequest]]:
        if req.preferred_runtime:
            ordered = [{"runtime": req.preferred_runtime, "model": req.model}, *req.fallback_runtimes]
            selected_recommended: list[tuple[RuntimeAdapter, RunRequest]] = []
            for candidate in ordered:
                name = candidate.get("runtime", "").strip()
                if not name:
                    continue
                runtime = self._runtimes.get(name)
                if runtime is None:
                    continue
                if _runtime_is_degraded(name):
                    logger.warning("Skipping degraded runtime %s", name)
                    continue
                selected_recommended.append((
                    runtime,
                    req.model_copy(update={
                        "preferred_runtime": name,
                        "model": candidate.get("model", req.model),
                        "fallback_runtimes": [],
                    }),
                ))
            return selected_recommended

        selected: list[RuntimeAdapter] = []
        for name in RUNTIME_ORDER:
            runtime = self._runtimes.get(name)
            if runtime is None:
                continue
            if _runtime_is_degraded(name):
                logger.warning("Skipping degraded runtime %s", name)
                continue
            selected.append(runtime)
        return [(runtime, req) for runtime in selected]

    async def run(self, req: RunRequest, job: Job) -> RuntimeOutcome:
        failures: list[RuntimeFailure] = []
        for runtime, runtime_req in self.candidates(req):
            outcome = await runtime.run(runtime_req)
            job.attempts.append(f"{outcome.runtime}:{outcome.model}")
            if isinstance(outcome, RuntimeSuccess):
                return outcome
            failures.append(outcome)
            logger.warning(
                "Runtime %s failed for task %s (%s, retryable=%s): %s",
                outcome.runtime,
                req.task_id,
                outcome.error_type,
                outcome.retryable,
                outcome.message[:300],
            )
            if outcome.retryable:
                _degrade_runtime(outcome.runtime, outcome.error_type, outcome.message)
                continue
            return outcome

        if failures:
            last = failures[-1]
            return RuntimeFailure(
                runtime=last.runtime,
                model=last.model,
                error_type="all_runtimes_failed",
                message=" | ".join(
                    f"{failure.runtime}:{failure.error_type}:{failure.message[:160]}"
                    for failure in failures
                ),
                retryable=False,
            )

        return RuntimeFailure(
            runtime="router",
            model="",
            error_type="no_runtime_available",
            message="No healthy runtimes available",
            retryable=False,
        )


ROUTER = RuntimeRouter(
    runtimes={
        "claude": ClaudeRuntime(),
        "codex": CodexRuntime(),
    }
)


async def _execute_job(job: Job, req: RunRequest) -> None:
    job.status = "running"
    try:
        outcome = await ROUTER.run(req, job)
        job.runtime = outcome.runtime
        if isinstance(outcome, RuntimeSuccess):
            job.result = outcome.result
            job.metadata = outcome.metadata
            job.status = "done"
            logger.info(
                "Job %s done via %s (%s)",
                job.id,
                outcome.runtime,
                outcome.model,
            )
            return

        job.error = outcome.message
        job.status = "error"
        logger.error(
            "Job %s failed via %s (%s): %s",
            job.id,
            outcome.runtime,
            outcome.error_type,
            outcome.message[:500],
        )
    except Exception as exc:
        job.error = str(exc)
        job.status = "error"
        logger.exception("Job %s: unexpected proxy exception", job.id)
    finally:
        job.completed_at = time.time()


def _check_auth(key: str) -> None:
    if API_KEY and key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid proxy key")


@app.post("/run", response_model=SubmitResponse)
async def submit_job(
    req: RunRequest,
    x_proxy_key: str = Header("", alias="X-Proxy-Key"),
):
    _check_auth(x_proxy_key)
    _cleanup_old_jobs()

    job_id = str(uuid.uuid4())[:8]
    job = Job(id=job_id, task_id=req.task_id)
    jobs[job_id] = job

    logger.info("Job %s submitted for task %s (requested model=%s)", job_id, req.task_id, req.model)
    asyncio.create_task(_execute_job(job, req))
    return SubmitResponse(job_id=job_id)


@app.get("/status/{job_id}", response_model=StatusResponse)
async def get_status(
    job_id: str,
    x_proxy_key: str = Header("", alias="X-Proxy-Key"),
):
    _check_auth(x_proxy_key)
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return StatusResponse(
        status=job.status,
        result=job.result,
        error=job.error,
        runtime=job.runtime,
        metadata=job.metadata,
    )


@app.get("/health")
async def health():
    runtimes: dict[str, object] = {}

    claude_cmd = await asyncio.create_subprocess_exec(
        "claude", "auth", "status",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    claude_stdout, claude_stderr = await claude_cmd.communicate()
    try:
        runtimes["claude"] = {
            "auth": json.loads(claude_stdout.decode()),
            "degraded": _runtime_is_degraded("claude"),
        }
    except Exception:
        runtimes["claude"] = {
            "auth": (claude_stderr.decode() or "not logged in").strip(),
            "degraded": _runtime_is_degraded("claude"),
        }

    codex_auth_path = Path.home() / ".codex" / "auth.json"
    runtimes["codex"] = {
        "auth": "configured" if codex_auth_path.exists() else "missing auth.json",
        "degraded": _runtime_is_degraded("codex"),
    }

    return {
        "status": "ok",
        "active_jobs": sum(1 for j in jobs.values() if j.status == "running"),
        "runtime_order": list(RUNTIME_ORDER),
        "runtime_health": {
            name: {
                "degraded": health.degraded,
                "last_error_type": health.last_error_type,
                "last_message": health.last_message,
            }
            for name, health in runtime_health.items()
        },
        "runtimes": runtimes,
    }


if not WORKPLANNER_API_URL or not INTERNAL_API_KEY:
    logger.warning(
        "WORKPLANNER_API_URL or INTERNAL_API_KEY not set on the proxy — "
        "MCP tool calls (create_task, add_comment, etc.) will fail. "
        "Export both before starting the proxy."
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PROXY_PORT", "8400"))
    uvicorn.run(app, host="0.0.0.0", port=port)
