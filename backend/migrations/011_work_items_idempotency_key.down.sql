DROP INDEX IF EXISTS work_items_idempotency_key_unique_idx;
ALTER TABLE work_items DROP COLUMN IF EXISTS idempotency_key;
