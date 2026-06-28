-- Planner: one shared calendar + company holidays + people pool + per-person
-- time off. Simplified model (no inheritance/composition). See
-- docs/PLANNER_DESIGN.md (People & calendar model).

CREATE TABLE calendar (
    id           UUID PRIMARY KEY,
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    weekend_days SMALLINT NOT NULL DEFAULT 96,  -- bitmask Mon=1..Sun=64; Sat(32)+Sun(64)=96
    created_at   BIGINT NOT NULL,
    updated_at   BIGINT NOT NULL
);
-- One shared calendar per workspace (user).
CREATE UNIQUE INDEX calendar_user_unique_idx ON calendar (user_id);

CREATE TABLE company_holidays (
    id          UUID PRIMARY KEY,
    calendar_id UUID NOT NULL REFERENCES calendar(id) ON DELETE CASCADE,
    day         DATE NOT NULL,
    name        TEXT,
    created_at  BIGINT NOT NULL
);
CREATE UNIQUE INDEX company_holidays_unique_idx ON company_holidays (calendar_id, day);

CREATE TABLE people (
    id            UUID PRIMARY KEY,
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    email         TEXT,
    hours_per_day NUMERIC NOT NULL DEFAULT 8,
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    BIGINT NOT NULL,
    updated_at    BIGINT NOT NULL
);
CREATE INDEX people_user_idx ON people (user_id);

CREATE TABLE person_time_off (
    id         UUID PRIMARY KEY,
    person_id  UUID NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    start_day  DATE NOT NULL,
    end_day    DATE NOT NULL,            -- inclusive
    hours_off  NUMERIC,                  -- NULL = full day(s) off; else partial/half-day
    note       TEXT,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL
);
CREATE INDEX person_time_off_lookup_idx ON person_time_off (person_id, start_day, end_day);
