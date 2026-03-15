-- Add level field (depth in task tree, auto-calculated by application).
ALTER TABLE tasks ADD COLUMN level INT;

-- Add index for status queries that include IN_PROGRESS and QUEUED.
CREATE INDEX idx_tasks_ai_enabled ON tasks(user_id, ai_enabled) WHERE ai_enabled = TRUE;
