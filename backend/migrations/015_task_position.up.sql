-- Fractional sibling ordering for the planner tree. NULL falls back to
-- created_at (COALESCE in the planner query), so existing and new tasks order
-- by creation until explicitly moved; a reorder writes a fractional position
-- between neighbours, so only the moved row changes.
ALTER TABLE tasks ADD COLUMN position NUMERIC;
