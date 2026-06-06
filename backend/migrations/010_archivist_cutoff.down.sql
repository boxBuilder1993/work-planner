-- Reverting the cutoff removes the archivist-reviewed marker from all
-- comments (both the migration backfill and any set by the archivist since).
UPDATE comments
SET props = props - 'archivist-reviewed'
WHERE props ? 'archivist-reviewed';
