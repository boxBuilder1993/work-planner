-- Idempotency for sweep-created (driver) WorkItems.
--
-- Mention-triggered items dedupe on triggering_comment_id (007). Sweep items
-- have no triggering comment, so they carry an explicit idempotency_key —
-- e.g. "driver:<task_id>:<5-min bucket>" — which makes repeated heartbeat
-- ticks collapse to one driver per task per window. Partial index so the many
-- rows with a NULL key (all mention-triggered items) never collide.
ALTER TABLE work_items ADD COLUMN idempotency_key TEXT;

CREATE UNIQUE INDEX work_items_idempotency_key_unique_idx
    ON work_items (idempotency_key)
    WHERE idempotency_key IS NOT NULL;
