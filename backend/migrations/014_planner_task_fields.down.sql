DROP INDEX IF EXISTS tasks_assignee_idx;
ALTER TABLE tasks
    DROP COLUMN IF EXISTS assignee_id,
    DROP COLUMN IF EXISTS buffer_hours,
    DROP COLUMN IF EXISTS remaining_effort,
    DROP COLUMN IF EXISTS scheduled_start,
    DROP COLUMN IF EXISTS scheduled_end,
    DROP COLUMN IF EXISTS actual_start,
    DROP COLUMN IF EXISTS actual_end;
