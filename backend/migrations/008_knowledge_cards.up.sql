-- Knowledge cards: a simple, searchable company knowledge base for the AI
-- personas (and humans). A card is freeform text + tags + a validity flag.
-- Source of truth is Postgres; retrieval is Postgres full-text search. No
-- vector store. See docs/KNOWLEDGE_CARDS_DESIGN.md.

CREATE TABLE knowledge_cards (
    id          TEXT PRIMARY KEY,         -- short human slug: "auth-jwt-flow"
    content     TEXT NOT NULL,            -- freeform text; references live inline
    tags        TEXT[] NOT NULL DEFAULT '{}',
    is_valid    BOOLEAN NOT NULL DEFAULT TRUE,  -- human retires a card without deleting
    created_at  BIGINT NOT NULL,
    updated_at  BIGINT NOT NULL
);

-- Tag filtering.
CREATE INDEX knowledge_cards_tags_idx ON knowledge_cards USING GIN (tags);

-- Full-text search over content. Explicit 'english' regconfig keeps
-- to_tsvector immutable so it's index-eligible; coalesce guards nulls.
CREATE INDEX knowledge_cards_fts_idx ON knowledge_cards
    USING GIN (to_tsvector('english', coalesce(content, '')));

-- Default search excludes invalid cards.
CREATE INDEX knowledge_cards_valid_idx ON knowledge_cards (is_valid);
