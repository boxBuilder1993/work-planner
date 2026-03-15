"""AI Poller entry point.

Polls the WorkPlanner backend API for @ai comments,
generates AI responses via Claude Agent SDK, and posts them back.

Usage:
    python main.py          # Continuous polling (default 5 min interval)
    python main.py --once   # Single poll cycle then exit
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import os

from dotenv import load_dotenv

from api_client import ApiClient
from processor import PollCycleProcessor

logger = logging.getLogger("ai_poller")

DEFAULT_POLL_INTERVAL = 300  # 5 minutes


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def load_config() -> tuple[str, str, int]:
    """Load configuration from .env. Returns (api_url, jwt, poll_interval)."""
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

    api_url = os.environ.get("WORKPLANNER_API_URL")
    if not api_url:
        logger.error("WORKPLANNER_API_URL not set in .env")
        sys.exit(1)

    jwt = os.environ.get("WORKPLANNER_JWT")
    if not jwt:
        logger.error("WORKPLANNER_JWT not set in .env")
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    poll_interval = int(
        os.environ.get("POLL_INTERVAL_SECONDS", str(DEFAULT_POLL_INTERVAL))
    )
    return api_url, jwt, poll_interval


async def run_once(processor: PollCycleProcessor) -> None:
    count = await processor.run_cycle()
    logger.info("Cycle complete: %d comment(s) processed", count)


async def run_loop(processor: PollCycleProcessor, interval: int) -> None:
    logger.info("Starting poll loop (interval=%ds)", interval)
    while True:
        try:
            count = await processor.run_cycle()
            logger.info("Cycle complete: %d comment(s) processed", count)
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
    api_url, jwt, poll_interval = load_config()

    # Initialize API client
    logger.info("Connecting to WorkPlanner API at %s", api_url)
    api = ApiClient(api_url, jwt)

    processor = PollCycleProcessor(api)

    if args.once:
        asyncio.run(run_once(processor))
    else:
        asyncio.run(run_loop(processor, poll_interval))


if __name__ == "__main__":
    main()
