-- Password login: a nullable bcrypt hash on users. NULL = no password set
-- (e.g. Google-only accounts until they set one from Settings).
ALTER TABLE users ADD COLUMN password_hash TEXT;
