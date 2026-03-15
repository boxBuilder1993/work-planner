DROP INDEX IF EXISTS idx_comments_type;
DROP INDEX IF EXISTS idx_comments_parent;
ALTER TABLE comments DROP COLUMN proposal_feedback;
ALTER TABLE comments DROP COLUMN proposal_status;
ALTER TABLE comments DROP COLUMN created_by;
ALTER TABLE comments DROP COLUMN comment_type;
ALTER TABLE comments DROP COLUMN parent_comment_id;
