"""Debate-based agent execution.

Every agent invocation is a debate between 2 agents + a judge.
The debate is pure reasoning — no tools, no side effects.
After convergence, a single executor agent carries out the decision with tools.

The caller gets back a single result, as if one agent ran.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import requests

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class DebateConfig:
    agents: int = 2            # number of debaters (2 or 3)
    max_rounds: int = 10       # hard cap on rounds
    target_rounds: int = 0     # 0 = until convergence
    timeout_minutes: int = 30  # force synthesis after this


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_DEBATER_A_SUFFIX = """

You are Agent A in a debate. Propose your best answer independently.
Be thorough, consider alternatives, and justify your reasoning.
You do NOT have access to any tools — reason based on the information provided."""

_DEBATER_B_SUFFIX = """

You are Agent B in a debate. Propose your best answer independently.
Think differently from obvious approaches. Challenge assumptions.
You do NOT have access to any tools — reason based on the information provided."""

_JUDGE_SYSTEM = """\
You are a Judge evaluating two agents debating a question.

Your job:
1. Identify where they agree and disagree
2. Assess which arguments are stronger and why
3. Decide: CONVERGED or NOT_CONVERGED
4. If CONVERGED: write the final synthesized answer combining the best of both
5. If NOT_CONVERGED: give specific, actionable feedback on what they should focus on

Respond in EXACTLY this format (keep the labels):
VERDICT: CONVERGED or NOT_CONVERGED
FEEDBACK: <what to focus on next, or summary of why they converged>
SYNTHESIS: <the final merged answer — ONLY if CONVERGED, otherwise write NONE>"""

_REVISION_PROMPT = """\
{original_prompt}

== Full debate history ==
{debate_history}

== Judge's latest feedback ==
{latest_feedback}

Revise your position. Address the judge's feedback. Engage with the other agent's
strongest arguments. If you now agree with the other agent, say so explicitly.
You do NOT have access to any tools — reason based on the information provided."""

_FORCE_SYNTHESIS_PROMPT = """\
The agents did not reach consensus after {rounds} rounds.

Original question:
{original_prompt}

== Full debate history ==
{debate_history}

Write the best possible synthesis, taking the strongest arguments from both agents.
Note where they disagreed and explain your resolution.

VERDICT: FORCED_SYNTHESIS
FEEDBACK: Agents did not converge after {rounds} rounds.
SYNTHESIS: <your synthesized answer>"""

_EXECUTOR_SYSTEM = """\
You are an executor agent. A debate between multiple agents has produced the
decision below. Your job is to carry out this decision using the tools available
to you. Do exactly what the decision says — do not re-debate or second-guess it.

The debated decision:
{synthesis}"""


# ---------------------------------------------------------------------------
# Debate history
# ---------------------------------------------------------------------------

@dataclass
class DebateRound:
    round_num: int
    position_a: str
    position_b: str
    judge_verdict: str = ""
    judge_feedback: str = ""
    judge_synthesis: str = ""


def _format_history(rounds: list[DebateRound]) -> str:
    lines = []
    for r in rounds:
        lines.append(f"== Round {r.round_num} ==")
        lines.append(f"Agent A:\n{r.position_a}\n")
        lines.append(f"Agent B:\n{r.position_b}\n")
        if r.judge_verdict:
            lines.append(f"Judge: {r.judge_verdict}")
            if r.judge_feedback:
                lines.append(f"Feedback: {r.judge_feedback}")
            lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Verdict parsing
# ---------------------------------------------------------------------------

@dataclass
class JudgeVerdict:
    converged: bool
    feedback: str
    synthesis: str


def _parse_verdict(text: str) -> JudgeVerdict:
    verdict_line = ""
    feedback_line = ""
    synthesis_lines = []
    current_section = None

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("VERDICT:"):
            verdict_line = stripped[len("VERDICT:"):].strip()
            current_section = "verdict"
        elif stripped.startswith("FEEDBACK:"):
            feedback_line = stripped[len("FEEDBACK:"):].strip()
            current_section = "feedback"
        elif stripped.startswith("SYNTHESIS:"):
            syn = stripped[len("SYNTHESIS:"):].strip()
            if syn and syn != "NONE":
                synthesis_lines.append(syn)
            current_section = "synthesis"
        elif current_section == "synthesis" and stripped:
            synthesis_lines.append(stripped)
        elif current_section == "feedback" and stripped:
            feedback_line += " " + stripped

    converged = "CONVERGED" in verdict_line and "NOT_CONVERGED" not in verdict_line
    synthesis = "\n".join(synthesis_lines).strip()

    return JudgeVerdict(
        converged=converged,
        feedback=feedback_line,
        synthesis=synthesis if synthesis else text,
    )


# ---------------------------------------------------------------------------
# Agent Runner
# ---------------------------------------------------------------------------

class AgentRunner:
    """Every prompt() call runs a debate (no tools) then an executor (with tools)."""

    def __init__(
        self,
        proxy_url: str,
        proxy_key: str,
        config: DebateConfig | None = None,
    ):
        self._proxy_url = proxy_url
        self._proxy_key = proxy_key
        self._config = config or DebateConfig()

    async def prompt(
        self,
        prompt: str,
        system_prompt: str,
        tools: tuple[dict, list[str]],
        model: str = "claude-sonnet-4-6",
        task_id: str = "",
        ai_status: str = "",
        workplanner_api_url: str = "",
        internal_api_key: str = "",
        algo_tools: list[str] | None = None,
        max_turns: int = 20,
    ) -> str:
        """Run a debate then execute the decision. Returns the execution result."""

        if self._config.agents <= 1:
            # Single agent — no debate, just execute directly
            return await self._call_agent(
                system_prompt, prompt, tools, model,
                task_id, ai_status, workplanner_api_url, internal_api_key,
                algo_tools, max_turns,
            )

        # Step 1: DEBATE (no tools — pure reasoning)
        synthesis = await self._debate(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            task_id=task_id,
        )

        logger.info("Debate synthesis for task %s: %s", task_id, synthesis[:300])

        # Step 2: EXECUTE the debated decision (with tools)
        executor_system = _EXECUTOR_SYSTEM.format(synthesis=synthesis)
        result = await self._call_agent(
            system_prompt=executor_system,
            prompt=prompt,
            tools=tools,
            model=model,
            task_id=task_id,
            ai_status=ai_status,
            workplanner_api_url=workplanner_api_url,
            internal_api_key=internal_api_key,
            algo_tools=algo_tools,
            max_turns=max_turns,
        )

        return result

    async def _debate(
        self,
        prompt: str,
        system_prompt: str,
        model: str,
        task_id: str,
    ) -> str:
        """Run the debate rounds. No tools. Returns the judge's synthesis."""

        no_tools: tuple[dict, list[str]] = ({}, [])
        start_time = time.time()
        rounds: list[DebateRound] = []
        max_rounds = self._config.max_rounds

        # Round 1: independent proposals
        logger.info("Debate round 1 for task %s: agents proposing independently", task_id)
        result_a, result_b = await asyncio.gather(
            self._call_agent(
                system_prompt + _DEBATER_A_SUFFIX, prompt,
                no_tools, model, task_id,
            ),
            self._call_agent(
                system_prompt + _DEBATER_B_SUFFIX, prompt,
                no_tools, model, task_id,
            ),
        )

        # Judge round 1
        judge_result = await self._call_agent(
            _JUDGE_SYSTEM,
            f"Original question:\n{prompt}\n\nAgent A's position:\n{result_a}\n\nAgent B's position:\n{result_b}",
            no_tools, model, task_id,
        )
        verdict = _parse_verdict(judge_result)
        rounds.append(DebateRound(
            round_num=1,
            position_a=result_a,
            position_b=result_b,
            judge_verdict="CONVERGED" if verdict.converged else "NOT_CONVERGED",
            judge_feedback=verdict.feedback,
            judge_synthesis=verdict.synthesis if verdict.converged else "",
        ))

        if verdict.converged:
            logger.info("Debate converged in round 1 for task %s", task_id)
            return verdict.synthesis

        # Rounds 2-N
        for round_num in range(2, max_rounds + 1):
            elapsed = (time.time() - start_time) / 60
            if elapsed > self._config.timeout_minutes:
                logger.warning("Debate timed out after %.1f minutes for task %s", elapsed, task_id)
                break

            logger.info("Debate round %d for task %s", round_num, task_id)
            history = _format_history(rounds)

            # Both agents revise with full history
            result_a, result_b = await asyncio.gather(
                self._call_agent(
                    system_prompt + _DEBATER_A_SUFFIX,
                    _REVISION_PROMPT.format(
                        original_prompt=prompt,
                        debate_history=history,
                        latest_feedback=verdict.feedback,
                    ),
                    no_tools, model, task_id,
                ),
                self._call_agent(
                    system_prompt + _DEBATER_B_SUFFIX,
                    _REVISION_PROMPT.format(
                        original_prompt=prompt,
                        debate_history=history,
                        latest_feedback=verdict.feedback,
                    ),
                    no_tools, model, task_id,
                ),
            )

            # Judge evaluates
            history_with_latest = history + f"\n== Round {round_num} ==\nAgent A:\n{result_a}\n\nAgent B:\n{result_b}\n"
            judge_result = await self._call_agent(
                _JUDGE_SYSTEM,
                f"Original question:\n{prompt}\n\n{history_with_latest}",
                no_tools, model, task_id,
            )
            verdict = _parse_verdict(judge_result)
            rounds.append(DebateRound(
                round_num=round_num,
                position_a=result_a,
                position_b=result_b,
                judge_verdict="CONVERGED" if verdict.converged else "NOT_CONVERGED",
                judge_feedback=verdict.feedback,
                judge_synthesis=verdict.synthesis if verdict.converged else "",
            ))

            if verdict.converged:
                logger.info("Debate converged in round %d for task %s", round_num, task_id)
                return verdict.synthesis

            if self._config.target_rounds > 0 and round_num >= self._config.target_rounds:
                logger.info("Debate hit target rounds (%d) for task %s",
                            self._config.target_rounds, task_id)
                break

        # Force synthesis
        logger.info("Forcing synthesis after %d rounds for task %s", len(rounds), task_id)
        history = _format_history(rounds)
        force_result = await self._call_agent(
            _JUDGE_SYSTEM,
            _FORCE_SYNTHESIS_PROMPT.format(
                original_prompt=prompt,
                debate_history=history,
                rounds=len(rounds),
            ),
            no_tools, model, task_id,
        )
        return _parse_verdict(force_result).synthesis

    async def _call_agent(
        self,
        system_prompt: str,
        prompt: str,
        tools: tuple[dict, list[str]],
        model: str,
        task_id: str = "",
        ai_status: str = "",
        workplanner_api_url: str = "",
        internal_api_key: str = "",
        algo_tools: list[str] | None = None,
        max_turns: int = 20,
    ) -> str:
        """Single agent call via the proxy."""
        _, allowed_tools = tools if tools else ({}, [])

        request_body = {
            "prompt": prompt,
            "system_prompt": system_prompt,
            "model": model,
            "max_turns": max_turns,
            "allowed_tools": allowed_tools if allowed_tools else [],
            "algo_tools": algo_tools or [],
            "task_id": task_id,
            "ai_status": ai_status,
            "workplanner_api_url": workplanner_api_url,
            "internal_api_key": internal_api_key,
        }

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._proxy_key:
            headers["X-Proxy-Key"] = self._proxy_key

        loop = asyncio.get_event_loop()

        # Submit job
        submit_resp = await loop.run_in_executor(
            None,
            lambda: requests.post(
                f"{self._proxy_url}/run",
                json=request_body,
                headers=headers,
                timeout=30,
            ),
        )
        if submit_resp.status_code != 200:
            return f"Error: proxy returned {submit_resp.status_code}"

        job_id = submit_resp.json().get("job_id")
        if not job_id:
            return "Error: no job_id returned"

        # Poll for result
        for _ in range(120):  # 10 minutes max
            await asyncio.sleep(5)
            status_resp = await loop.run_in_executor(
                None,
                lambda: requests.get(
                    f"{self._proxy_url}/status/{job_id}",
                    headers=headers,
                    timeout=15,
                ),
            )
            if status_resp.status_code != 200:
                continue
            data = status_resp.json()
            if data["status"] == "done":
                return data.get("result", "")
            if data["status"] == "error":
                return f"Error: {data.get('error', 'unknown')}"

        return "Error: timeout waiting for agent"
