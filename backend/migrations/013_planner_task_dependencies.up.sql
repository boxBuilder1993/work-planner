-- Planner: task dependency DAG. `task_id` is blocked by `depends_on_id`
-- (task_id cannot start until depends_on_id finishes). Cycle prevention is
-- enforced in the app/store layer (topological check on insert).

CREATE TABLE task_dependencies (
    id            UUID PRIMARY KEY,
    task_id       UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,  -- the blocked task
    depends_on_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,  -- the blocker
    created_at    BIGINT NOT NULL
);
CREATE UNIQUE INDEX task_dependencies_unique_idx ON task_dependencies (task_id, depends_on_id);
CREATE INDEX task_dependencies_dep_idx ON task_dependencies (depends_on_id);
