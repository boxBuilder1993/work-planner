"""AI Poller entry point.

Polls the WorkPlanner backend API for ai_enabled tasks (hierarchy mode)
and @ai comments (legacy mode), spawns Claude agents, and posts results back.

Usage:
    python main.py          # Continuous polling (default 5 min interval)
    python main.py --once   # Single poll cycle then exit
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from api_client import ApiClient
from config import load_config
from processor import PollCycleProcessor
from spawner import AgentSpawner

logger = logging.getLogger("ai_poller")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def run_once(processor: PollCycleProcessor, spawner: AgentSpawner) -> None:
    count = await processor.run_cycle()
    logger.info("Cycle complete: %d action(s) taken", count)
    # Wait for any spawned agents to finish
    await spawner.wait_for_all(timeout=300)


async def run_loop(processor: PollCycleProcessor, spawner: AgentSpawner, interval: int) -> None:
    logger.info("Starting poll loop (interval=%ds)", interval)
    while True:
        try:
            count = await processor.run_cycle()
            logger.info("Cycle complete: %d action(s) taken", count)
        except Exception:
            logger.exception("Error during poll cycle, will retry next cycle")
        await asyncio.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="WorkPlanner AI Poller")
    parser.add_argument(
        "--once", action="store_true", help="Run a single poll cycle then exit"
    )
    args = parser.parse_args()

    setup_logging()

    try:
        cfg = load_config()
        cfg.validate()
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    logger.info("Connecting to WorkPlanner API at %s", cfg.api_url)
    api = ApiClient(cfg.api_url, jwt=cfg.jwt, internal_api_key=cfg.internal_api_key)

    spawner = AgentSpawner(api, cfg)

    processor = PollCycleProcessor(
        api=api,
        config=cfg,
        spawner=spawner,
    )

    if args.once:
        asyncio.run(run_once(processor, spawner))
    else:
        asyncio.run(run_loop(processor, spawner, cfg.poll_interval_seconds))


if __name__ == "__main__":
    main()
