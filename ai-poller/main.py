"""AI Poller entry point.

Polls Google Drive for @ai comments in WorkPlanner tasks,
generates AI responses via Claude Agent SDK, and writes them back.

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

from google_auth import authenticate
from drive_client import DriveClient
from encryption import derive_key
from processor import PollCycleProcessor

logger = logging.getLogger("ai_poller")

DRIVE_FILE_SALT = "workplanner_salt.bin"
DEFAULT_POLL_INTERVAL = 300  # 5 minutes


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def load_config() -> tuple[str, int]:
    """Load configuration from .env. Returns (passphrase, poll_interval)."""
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

    passphrase = os.environ.get("WORKPLANNER_PASSPHRASE")
    if not passphrase:
        logger.error("WORKPLANNER_PASSPHRASE not set in .env")
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    poll_interval = int(
        os.environ.get("POLL_INTERVAL_SECONDS", str(DEFAULT_POLL_INTERVAL))
    )
    return passphrase, poll_interval


async def run_once(processor: PollCycleProcessor) -> None:
    """Run a single poll cycle."""
    count = await processor.run_cycle()
    logger.info("Cycle complete: %d comment(s) processed", count)


async def run_loop(processor: PollCycleProcessor, interval: int) -> None:
    """Run the poll loop continuously."""
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
    passphrase, poll_interval = load_config()

    # Authenticate with Google Drive
    logger.info("Authenticating with Google Drive...")
    creds = authenticate()
    drive = DriveClient(creds)

    # Download salt and derive encryption key
    logger.info("Downloading salt and deriving encryption key...")
    salt = drive.download_file_by_name(DRIVE_FILE_SALT)
    if salt is None:
        logger.error(
            "Salt file not found on Drive. WorkPlanner must be set up with a "
            "passphrase and synced at least once before running the AI poller."
        )
        sys.exit(1)

    key = derive_key(passphrase, salt)
    processor = PollCycleProcessor(drive, key)

    # Run
    if args.once:
        asyncio.run(run_once(processor))
    else:
        asyncio.run(run_loop(processor, poll_interval))


if __name__ == "__main__":
    main()
