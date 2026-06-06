-- Archivist cutoff.
--
-- The archivist reviews every NEW comment to keep the knowledge base current.
-- To avoid it churning through the entire historical backlog on first run,
-- mark every comment that already exists at this point as reviewed. The
-- archivist then only processes comments created from here forward.
--
-- On a fresh database (no comments yet) this is a no-op, so a brand-new
-- install starts archiving from its very first comment — exactly what we want.
UPDATE comments
SET props = jsonb_set(props, '{archivist-reviewed}', 'true'::jsonb)
WHERE (props->>'archivist-reviewed') IS NULL;
