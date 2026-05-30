CREATE TABLE work_items (
    id                     UUID PRIMARY KEY,
    task_id                UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    triggering_comment_id  UUID REFERENCES comments(id) ON DELETE SET NULL,
    target_persona         TEXT NOT NULL,
    prompt_context         JSONB NOT NULL DEFAULT '{}'::jsonb,
    output                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    status                 TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','dispatched','completed','failed','cancelled')),
    retry_count            INT NOT NULL DEFAULT 0,
    max_retries            INT NOT NULL DEFAULT 5,
    attempts               JSONB NOT NULL DEFAULT '[]'::jsonb,
    last_error             TEXT,
    created_at             BIGINT NOT NULL,
    updated_at             BIGINT NOT NULL,
    dispatched_at          BIGINT,
    completed_at           BIGINT,
    props                  JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Pickup query: poller selects pending OR retry-eligible failed rows.
CREATE INDEX work_items_pickup_idx
    ON work_items (status, retry_count)
    WHERE status IN ('pending','failed');

-- Per-task concurrency cap + CLI listings.
CREATE INDEX work_items_task_idx ON work_items (task_id, status);

-- Idempotency guard: one WorkItem per triggering comment. Partial because
-- sweep-created WorkItems (future) have triggering_comment_id IS NULL and
-- shouldn't collide.
CREATE UNIQUE INDEX work_items_trigger_unique_idx
    ON work_items (triggering_comment_id)
    WHERE triggering_comment_id IS NOT NULL;
