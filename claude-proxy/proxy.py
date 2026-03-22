"""Claude Code proxy server.

Accepts requests from the ai-poller on Railway, runs claude -p locally
using your Mac's subscription auth, returns results.

Start with: uv run --project /path/to/claude-proxy proxy.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Claude Proxy")
logger = logging.getLogger("claude-proxy")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

PROXY_DIR = Path(__file__).parent.resolve()
API_KEY = os.environ.get("CLAUDE_PROXY_KEY", "")
SEMAPHORE = asyncio.Semaphore(3)  # max 3 concurrent runs


class RunRequest(BaseModel):
    prompt: str
    system_prompt: str = ""
    model: str = "claude-haiku-4-5"
    max_turns: int = 20
    allowed_tools: list[str] = []
    algo_tools: list[str] = []  # which algo tools to enable
    task_id: str = ""
    ai_status: str = ""
    # Backend connection info for MCP servers
    workplanner_api_url: str = ""
    internal_api_key: str = ""


class RunResponse(BaseModel):
    success: bool
    result: str = ""
    error: str = ""


def _build_mcp_config(req: RunRequest, config_path: Path) -> None:
    """Write a temporary MCP config JSON for this run."""
    env = {
        "WORKPLANNER_API_URL": req.workplanner_api_url,
        "INTERNAL_API_KEY": req.internal_api_key,
    }

    mcp_servers: dict[str, Any] = {
        "workplanner": {
            "command": "uv",
            "args": ["run", "--project", str(PROXY_DIR), str(PROXY_DIR / "workplanner_server.py")],
            "env": env,
        },
    }

    # Only add algo server if algo tools are needed
    if req.algo_tools:
        algo_env = {
            **env,
            "ALGO_TASK_ID": req.task_id,
            "ALGO_AI_STATUS": req.ai_status,
            "ALGO_TOOLS": ",".join(req.algo_tools),
        }
        mcp_servers["algo"] = {
            "command": "uv",
            "args": ["run", "--project", str(PROXY_DIR), str(PROXY_DIR / "algo_server.py")],
            "env": algo_env,
        }

    config = {"mcpServers": mcp_servers}
    config_path.write_text(json.dumps(config))


@app.post("/run", response_model=RunResponse)
async def run_agent(
    req: RunRequest,
    x_proxy_key: str = Header("", alias="X-Proxy-Key"),
):
    # Auth check
    if API_KEY and x_proxy_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid proxy key")

    logger.info("Run request: task=%s model=%s max_turns=%d", req.task_id, req.model, req.max_turns)

    async with SEMAPHORE:
        # Write temp MCP config
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", prefix="mcp-", delete=False, dir="/tmp"
        ) as f:
            config_path = Path(f.name)

        try:
            _build_mcp_config(req, config_path)

            # Build claude command
            cmd = [
                "claude", "-p",
                "--model", req.model,
                "--max-turns", str(req.max_turns),
                "--dangerously-skip-permissions",
                "--output-format", "json",
                "--mcp-config", str(config_path),
                "--no-session-persistence",
            ]

            if req.system_prompt:
                # Write system prompt to temp file to avoid shell escaping issues
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", prefix="sysprompt-", delete=False, dir="/tmp"
                ) as spf:
                    spf.write(req.system_prompt)
                    system_prompt_path = spf.name
                cmd.extend(["--system-prompt-file", system_prompt_path])
            else:
                system_prompt_path = None

            if req.allowed_tools:
                cmd.append("--allowedTools")
                cmd.extend(req.allowed_tools)

            logger.info("Running: %s", " ".join(cmd[:10]) + "...")

            # Run claude -p
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=req.prompt.encode()),
                timeout=600,  # 10 minute max
            )

            stdout_text = stdout.decode()
            stderr_text = stderr.decode()

            if stderr_text:
                logger.warning("stderr: %s", stderr_text[:500])

            # Parse JSON output
            if proc.returncode == 0 and stdout_text.strip():
                try:
                    output = json.loads(stdout_text)
                    # claude -p --output-format json returns {"result": "...", ...}
                    result_text = output.get("result", stdout_text)
                    logger.info("Success: %s", str(result_text)[:200])
                    return RunResponse(success=True, result=str(result_text))
                except json.JSONDecodeError:
                    logger.info("Raw output: %s", stdout_text[:200])
                    return RunResponse(success=True, result=stdout_text.strip())
            else:
                error = stderr_text or f"Exit code {proc.returncode}"
                logger.error("Failed: %s", error[:500])
                return RunResponse(success=False, error=error[:2000])

        except asyncio.TimeoutError:
            logger.error("Timeout for task %s", req.task_id)
            return RunResponse(success=False, error="Timeout after 600s")
        except Exception as e:
            logger.exception("Error running claude for task %s", req.task_id)
            return RunResponse(success=False, error=str(e))
        finally:
            config_path.unlink(missing_ok=True)
            if system_prompt_path:
                Path(system_prompt_path).unlink(missing_ok=True)


@app.get("/health")
async def health():
    # Check claude is installed and authed
    proc = await asyncio.create_subprocess_exec(
        "claude", "auth", "status",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    try:
        status = json.loads(stdout.decode())
        return {"status": "ok", "auth": status}
    except Exception:
        return {"status": "error", "auth": "not logged in"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PROXY_PORT", "8400"))
    uvicorn.run(app, host="0.0.0.0", port=port)
