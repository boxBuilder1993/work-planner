-- Add threading and proposal support to comments.
ALTER TABLE comments ADD COLUMN parent_comment_id UUID REFERENCES comments(id) ON DELETE CASCADE;
ALTER TABLE comments ADD COLUMN comment_type TEXT NOT NULL DEFAULT 'COMMENT';
ALTER TABLE comments ADD COLUMN created_by TEXT NOT NULL DEFAULT 'user';
ALTER TABLE comments ADD COLUMN proposal_status TEXT;
ALTER TABLE comments ADD COLUMN proposal_feedback TEXT;

CREATE INDEX idx_comments_parent ON comments(parent_comment_id);
CREATE INDEX idx_comments_type ON comments(task_id, comment_type);
