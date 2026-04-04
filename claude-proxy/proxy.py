"""Claude Code proxy server.

Accepts requests from the ai-poller on Railway, runs claude -p locally
using your Mac's subscription auth, returns results via async job queue.

Submit: POST /run → {job_id}
Poll:   GET /status/{job_id} → {status, result}

Start with: uv run --project /path/to/claude-proxy proxy.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Claude Proxy")
logger = logging.getLogger("claude-proxy")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

PROXY_DIR = Path(__file__).parent.resolve()
API_KEY = os.environ.get("CLAUDE_PROXY_KEY", "")
JOB_TTL = 300  # keep completed jobs for 5 minutes


# ---------------------------------------------------------------------------
# Job store
# ---------------------------------------------------------------------------

class Job:
    def __init__(self, job_id: str, task_id: str):
        self.id = job_id
        self.task_id = task_id
        self.status = "queued"  # queued → running → done | error
        self.result = ""
        self.error = ""
        self.created_at = time.time()
        self.completed_at: float | None = None


jobs: dict[str, Job] = {}


def _cleanup_old_jobs():
    now = time.time()
    expired = [
        jid for jid, j in jobs.items()
        if j.completed_at and now - j.completed_at > JOB_TTL
    ]
    for jid in expired:
        del jobs[jid]


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    prompt: str
    system_prompt: str = ""
    model: str = "claude-sonnet-4-6"
    max_turns: int = 20
    allowed_tools: list[str] = []
    algo_tools: list[str] = []
    task_id: str = ""
    ai_status: str = ""
    workplanner_api_url: str = ""
    internal_api_key: str = ""


class SubmitResponse(BaseModel):
    job_id: str


class StatusResponse(BaseModel):
    status: str  # queued, running, done, error
    result: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Claude execution
# ---------------------------------------------------------------------------

def _build_mcp_config(req: RunRequest, config_path: Path) -> bool:
    """Build MCP config for algo server only. Workplanner is registered at user level.
    Returns True if a config file was written, False if not needed."""
    if not req.algo_tools:
        return False

    env = {
        "WORKPLANNER_API_URL": req.workplanner_api_url,
        "INTERNAL_API_KEY": req.internal_api_key,
        "ALGO_TASK_ID": req.task_id,
        "ALGO_AI_STATUS": req.ai_status,
        "ALGO_TOOLS": ",".join(req.algo_tools),
    }

    config = {
        "mcpServers": {
            "algo": {
                "command": "uv",
                "args": ["run", "--project", str(PROXY_DIR), str(PROXY_DIR / "algo_server.py")],
                "env": env,
            },
        },
    }
    config_path.write_text(json.dumps(config))
    return True


async def _execute_job(job: Job, req: RunRequest) -> None:
    job.status = "running"
    config_path = Path(tempfile.mktemp(suffix=".json", prefix="mcp-", dir="/tmp"))
    system_prompt_path: str | None = None

    try:
        has_algo_config = _build_mcp_config(req, config_path)

        cmd = [
            "claude", "-p",
            "--model", req.model,
            "--max-turns", str(req.max_turns),
            "--dangerously-skip-permissions",
            "--output-format", "json",
            "--no-session-persistence",
            "--disallowedTools",
            "CronCreate", "CronDelete", "CronList",
            "RemoteTrigger",
            "Agent",
            "AskUserQuestion",
        ]

        if has_algo_config:
            cmd.extend(["--mcp-config", str(config_path)])

        if req.system_prompt:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", prefix="sysprompt-", delete=False, dir="/tmp"
            ) as spf:
                spf.write(req.system_prompt)
                system_prompt_path = spf.name
            cmd.extend(["--system-prompt-file", system_prompt_path])

        if req.allowed_tools:
            cmd.append("--allowedTools")
            cmd.extend(req.allowed_tools)

        logger.info("Job %s: running claude -p for task %s", job.id, job.task_id)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=req.prompt.encode()),
            timeout=600,
        )

        stdout_text = stdout.decode()
        stderr_text = stderr.decode()

        if stderr_text:
            logger.warning("Job %s stderr: %s", job.id, stderr_text[:500])

        if proc.returncode == 0 and stdout_text.strip():
            try:
                output = json.loads(stdout_text)
                job.result = str(output.get("result", stdout_text))
            except json.JSONDecodeError:
                job.result = stdout_text.strip()
            job.status = "done"
            logger.info("Job %s: done — %s", job.id, job.result[:200])
        else:
            job.error = stderr_text or f"Exit code {proc.returncode}"
            job.status = "error"
            logger.error("Job %s: error — %s", job.id, job.error[:500])

    except asyncio.TimeoutError:
        job.error = "Timeout after 600s"
        job.status = "error"
        logger.error("Job %s: timeout", job.id)
    except Exception as e:
        job.error = str(e)
        job.status = "error"
        logger.exception("Job %s: exception", job.id)
    finally:
        job.completed_at = time.time()
        config_path.unlink(missing_ok=True)
        if system_prompt_path:
            Path(system_prompt_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def _check_auth(key: str):
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
    job = Job(job_id=job_id, task_id=req.task_id)
    jobs[job_id] = job

    logger.info("Job %s: submitted for task %s (model=%s)", job_id, req.task_id, req.model)

    # Start execution in background
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
    )


@app.get("/health")
async def health():
    proc = await asyncio.create_subprocess_exec(
        "claude", "auth", "status",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    try:
        status = json.loads(stdout.decode())
        return {"status": "ok", "auth": status, "active_jobs": sum(1 for j in jobs.values() if j.status == "running")}
    except Exception:
        return {"status": "error", "auth": "not logged in"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PROXY_PORT", "8400"))
    uvicorn.run(app, host="0.0.0.0", port=port)
