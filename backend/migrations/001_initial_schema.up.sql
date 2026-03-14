CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE users (
    id                   UUID PRIMARY KEY,
    email                TEXT UNIQUE NOT NULL,
    name                 TEXT NOT NULL DEFAULT '',
    google_refresh_token TEXT,
    created_at           BIGINT NOT NULL
);

CREATE TABLE tasks (
    id           UUID PRIMARY KEY,
    user_id      UUID NOT NULL REFERENCES users(id),
    parent_id    UUID REFERENCES tasks(id) ON DELETE CASCADE,
    title        TEXT NOT NULL DEFAULT '',
    description  TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'PENDING',
    priority     INT NOT NULL DEFAULT 0,
    due_date     BIGINT,
    task_date    BIGINT,
    planned_time BIGINT,
    duration     DOUBLE PRECISION,
    created_at   BIGINT NOT NULL,
    updated_at   BIGINT NOT NULL
);

CREATE TABLE comments (
    id         UUID PRIMARY KEY,
    task_id    UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    text       TEXT NOT NULL DEFAULT '',
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL
);

CREATE TABLE repeating_tasks (
    id                  UUID PRIMARY KEY,
    task_id             UUID NOT NULL UNIQUE REFERENCES tasks(id) ON DELETE CASCADE,
    repetition_type     TEXT NOT NULL DEFAULT 'interval_days',
    repetition_props    JSONB NOT NULL DEFAULT '{}',
    start_date          BIGINT NOT NULL,
    last_created_at     BIGINT,
    created_at          BIGINT NOT NULL,
    updated_at          BIGINT NOT NULL
);

-- Indexes

CREATE INDEX idx_tasks_user_parent ON tasks(user_id, parent_id);
CREATE INDEX idx_tasks_user_status ON tasks(user_id, status);
CREATE INDEX idx_comments_task_created ON comments(task_id, created_at);
CREATE INDEX idx_tasks_title_trgm ON tasks USING gin (title gin_trgm_ops);
