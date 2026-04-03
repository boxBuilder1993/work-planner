#!/usr/bin/env python3
"""One-off script to cancel duplicate task 287e5ab1.

Context
-------
Task 82d54371 ("Add financial instruments to finance-scripts") had its plan
executor run multiple times due to a STATUS_ALIASES bug. This produced two
near-identical PENDING children:

  a9796100 — "Implement Credit Card financial instrument in finance-scripts"  (KEEP)
  287e5ab1 — "Implement Credit Card financial instrument"                     (CANCEL — duplicate)

This script closes 287e5ab1 with a comment explaining it is a duplicate.

Usage
-----
Run from the ai-poller directory with environment variables configured:

    WORKPLANNER_API_URL=https://... WORKPLANNER_JWT=... python scripts/cancel_duplicate_task.py

Or rely on the .env file:

    python scripts/cancel_duplicate_task.py
"""
from __future__ import annotations

import sys
import os

# Allow running from the repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import load_config
from api_client import ApiClient

DUPLICATE_TASK_ID = "287e5ab1"
CANONICAL_TASK_ID = "a9796100"

CANCEL_COMMENT = (
    f"[CANCELLED — DUPLICATE] This task is a duplicate of {CANONICAL_TASK_ID} "
    f"('Implement Credit Card financial instrument in finance-scripts'), which was created "
    f"during the same plan execution cycle. The duplicate arose from a STATUS_ALIASES bug "
    f"that caused the plan executor to run more than once. Closing this task; please use "
    f"{CANONICAL_TASK_ID} instead."
)


def main() -> None:
    cfg = load_config()
    if not cfg.api_url:
        print("ERROR: WORKPLANNER_API_URL not set. Configure your .env or environment.", file=sys.stderr)
        sys.exit(1)
    if not cfg.jwt and not cfg.internal_api_key:
        print("ERROR: WORKPLANNER_JWT or INTERNAL_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    api = ApiClient(
        base_url=cfg.api_url,
        jwt=cfg.jwt,
        internal_api_key=cfg.internal_api_key,
    )

    # Verify both tasks exist before modifying anything
    print(f"Fetching duplicate task {DUPLICATE_TASK_ID}...")
    try:
        dup = api.get_task(DUPLICATE_TASK_ID)
    except Exception as e:
        print(f"ERROR: Could not fetch duplicate task {DUPLICATE_TASK_ID}: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"  Title:  {dup.title!r}")
    print(f"  Status: {dup.status}")
    print(f"  aiStatus: {dup.props.get('aiStatus', 'N/A')}")

    print(f"\nFetching canonical task {CANONICAL_TASK_ID}...")
    try:
        canon = api.get_task(CANONICAL_TASK_ID)
    except Exception as e:
        print(f"ERROR: Could not fetch canonical task {CANONICAL_TASK_ID}: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"  Title:  {canon.title!r}")
    print(f"  Status: {canon.status}")

    if dup.status == "CLOSED":
        print(f"\nDuplicate task {DUPLICATE_TASK_ID} is already CLOSED. Nothing to do.")
        return

    # Post a comment explaining the cancellation, then close the task
    print(f"\nAdding cancellation comment to {DUPLICATE_TASK_ID}...")
    api.create_comment(
        task_id=DUPLICATE_TASK_ID,
        text=CANCEL_COMMENT,
        comment_type="COMMENT",
        created_by="user",
    )

    print(f"Closing task {DUPLICATE_TASK_ID}...")
    api.update_task(DUPLICATE_TASK_ID, status="CLOSED")

    print(f"\nDone. Task {DUPLICATE_TASK_ID} has been closed as a duplicate of {CANONICAL_TASK_ID}.")


if __name__ == "__main__":
    main()
