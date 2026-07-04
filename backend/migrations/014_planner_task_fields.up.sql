-- Planner: per-task scheduling fields. Inputs: assignee_id, buffer_hours
-- (reuse `duration` as estimate hours, `due_date` as deadline). Computed by
-- the scheduling engine: scheduled_start/end. Tracking: remaining_effort,
-- actual_start/end (auto-stamped on status transitions). `status` already
-- supports IN_PROGRESS (no enum constraint). See docs/PLANNER_DESIGN.md.

ALTER TABLE tasks
    ADD COLUMN assignee_id      UUID REFERENCES people(id) ON DELETE SET NULL,
    ADD COLUMN buffer_hours     NUMERIC,   -- optional parent reserve
    ADD COLUMN remaining_effort NUMERIC,   -- tracking
    ADD COLUMN scheduled_start  BIGINT,    -- computed (epoch ms)
    ADD COLUMN scheduled_end    BIGINT,    -- computed (epoch ms)
    ADD COLUMN actual_start     BIGINT,    -- auto-stamped
    ADD COLUMN actual_end       BIGINT;    -- auto-stamped

CREATE INDEX tasks_assignee_idx ON tasks (assignee_id);
